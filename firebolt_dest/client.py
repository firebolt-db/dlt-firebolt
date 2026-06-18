from __future__ import annotations

import re
from typing import List, Optional, Sequence

from dlt.common.destination import DestinationCapabilitiesContext
from dlt.common.destination.client import (
    CredentialsConfiguration,
    LoadJob,
    PreparedTableSchema,
    SupportsStagingDestination,
)
from dlt.common.schema import Schema, TColumnSchema
from dlt.common.schema.typing import TColumnType
from dlt.common.destination.client import FollowupJobRequest
from dlt.destinations.insert_job_client import InsertValuesJobClient
from dlt.destinations.job_client_impl import CopyRemoteFileLoadJob
from dlt.destinations.job_impl import ReferenceFollowupJobRequest
from dlt.destinations.sql_jobs import SqlMergeFollowupJob
from dlt.destinations.path_utils import get_file_format_and_compression
from dlt.destinations.sql_client import SqlClientBase

from firebolt_dest.configuration import FireboltClientConfiguration
from firebolt_dest.copy_sql import gen_firebolt_copy_sql, s3_url_to_copy_pattern
from firebolt_dest.sql_client import FireboltSqlClient
from firebolt_dest.upload_client import (
    gen_upload_insert_sql,
    resolve_engine_endpoint,
    resolve_local_parquet_path,
    sanitize_upload_part_name,
    upload_parquet_insert,
)


class FireboltCopyLoadJob(CopyRemoteFileLoadJob):
    def __init__(
        self,
        file_path: str,
        staging_credentials: Optional[CredentialsConfiguration] = None,
        *,
        location_name: str,
        s3_prefix: str,
    ) -> None:
        super().__init__(file_path, staging_credentials)
        self._location_name = location_name
        self._s3_prefix = s3_prefix
        self._job_client: FireboltClient = None

    def run(self) -> None:
        self._sql_client = self._job_client.sql_client
        file_name = self._bucket_path.rsplit("/", 1)[-1]
        file_format, _ = get_file_format_and_compression(file_name)
        pattern = s3_url_to_copy_pattern(self._bucket_path, self._s3_prefix)
        copy_sql = gen_firebolt_copy_sql(
            self._sql_client.make_qualified_table_name(self.load_table_name),
            location_name=self._location_name,
            pattern=pattern,
            file_format=file_format,
        )
        self._sql_client.execute_sql(copy_sql)


class FireboltUploadLoadJob(CopyRemoteFileLoadJob):
    """Load Parquet into Firebolt via HTTP multipart upload (upload://)."""

    def __init__(
        self,
        file_path: str,
        staging_credentials: Optional[CredentialsConfiguration] = None,
    ) -> None:
        super().__init__(file_path, staging_credentials)
        self._job_client: FireboltClient = None

    def run(self) -> None:
        config = self._job_client.config
        credentials = config.credentials
        local_path = resolve_local_parquet_path(self._bucket_path)
        if not local_path.is_file():
            raise FileNotFoundError(f"Upload staging file not found: {local_path}")

        part_name = sanitize_upload_part_name(local_path.stem)
        qualified_table = self._job_client.sql_client.make_qualified_table_name(
            self.load_table_name
        )
        sql = gen_upload_insert_sql(qualified_table, part_name)
        engine_url, database, token = self._job_client._upload_endpoint_cached()
        upload_parquet_insert(
            engine_url=engine_url,
            database=database,
            token=token,
            sql=sql,
            part_name=part_name,
            file_path=local_path,
        )


class FireboltMergeJob(SqlMergeFollowupJob):
    """Merge follow-up SQL for staged COPY loads (delete-insert strategy).

    Firebolt does not support CREATE TEMPORARY TABLE. Multi-table merges use
    helper tables that are created and dropped inside a single explicit
    transaction (see FireboltSqlClient.begin_transaction).
    """

    _CREATE_TABLE_PATTERN = re.compile(
        r'CREATE TABLE ("[^"]+"|\S+) AS',
        re.IGNORECASE,
    )

    @classmethod
    def _new_temp_table_name(
        cls, table_name: str, op: str, sql_client: SqlClientBase
    ) -> str:
        base = super()._new_temp_table_name(table_name, op, sql_client)
        return sql_client.make_qualified_table_name(base)

    @classmethod
    def _to_temp_table(
        cls,
        select_sql: str,
        temp_table_name: str,
        unique_column: str,
        sql_client: SqlClientBase,
    ) -> str:
        return (
            f"DROP TABLE IF EXISTS {temp_table_name}; "
            f"CREATE TABLE {temp_table_name} AS {select_sql}"
        )

    @classmethod
    def generate_sql(
        cls,
        table_chain: Sequence[PreparedTableSchema],
        sql_client: SqlClientBase,
    ) -> List[str]:
        sql = super().generate_sql(table_chain, sql_client)
        drops = [
            f"DROP TABLE IF EXISTS {match.group(1)}"
            for stmt in sql
            if (match := cls._CREATE_TABLE_PATTERN.search(stmt))
        ]
        return sql + drops


class FireboltClient(InsertValuesJobClient, SupportsStagingDestination):
    def __init__(
        self,
        schema: Schema,
        config: FireboltClientConfiguration,
        capabilities: DestinationCapabilitiesContext,
    ) -> None:
        dataset_name, staging_dataset_name = InsertValuesJobClient.create_dataset_names(
            schema, config
        )
        sql_client = FireboltSqlClient(
            dataset_name,
            staging_dataset_name,
            config.credentials,
            capabilities,
        )
        super().__init__(schema, config, sql_client)
        self.config: FireboltClientConfiguration = config
        self.sql_client: FireboltSqlClient = sql_client  # type: ignore[assignment]
        self.type_mapper = self.capabilities.get_type_mapper()
        self._upload_endpoint: tuple[str, str, str] | None = None

    def _upload_endpoint_cached(self) -> tuple[str, str, str]:
        if self._upload_endpoint is None:
            self._upload_endpoint = resolve_engine_endpoint(
                self.config.credentials,
                core_url=self.config.core_url,
                use_core=self.config.use_core,
            )
        return self._upload_endpoint

    def _create_merge_followup_jobs(
        self, table_chain: Sequence[PreparedTableSchema]
    ) -> List[FollowupJobRequest]:
        return [FireboltMergeJob.from_table_chain(table_chain, self.sql_client)]

    def create_load_job(
        self, table: PreparedTableSchema, file_path: str, load_id: str, restore: bool = False
    ) -> LoadJob:
        job = super().create_load_job(table, file_path, load_id, restore)
        if not job:
            assert ReferenceFollowupJobRequest.is_reference_job(file_path), (
                "Firebolt destination requires filesystem staging for file loads"
            )
            if self.config.staging_mode == "upload":
                job = FireboltUploadLoadJob(
                    file_path,
                    staging_credentials=(
                        self.config.staging_config.credentials
                        if self.config.staging_config
                        else None
                    ),
                )
            else:
                job = FireboltCopyLoadJob(
                    file_path,
                    staging_credentials=(
                        self.config.staging_config.credentials
                        if self.config.staging_config
                        else None
                    ),
                    location_name=self.config.s3_location_name,
                    s3_prefix=self.config.s3_prefix,
                )
        return job

    def _from_db_type(
        self, db_type: str, precision: Optional[int], scale: Optional[int]
    ) -> TColumnType:
        return self.type_mapper.from_destination_type(db_type, precision, scale)

    def should_truncate_table_before_load_on_staging_destination(self, table_name: str) -> bool:
        return self.config.truncate_tables_on_staging_destination_before_load
