from __future__ import annotations

from typing import Any, Dict, Optional, Type, Union

from dlt.common.arithmetics import DEFAULT_NUMERIC_PRECISION, DEFAULT_NUMERIC_SCALE
from dlt.common.data_writers.escape import escape_postgres_identifier
from dlt.common.destination import Destination, DestinationCapabilitiesContext
from dlt.common.destination.typing import PreparedTableSchema
from dlt.common.schema.typing import TColumnSchema

from dlt.destinations.type_mapping import TypeMapperImpl
from firebolt_dest.configuration import (
    FireboltClientConfiguration,
    FireboltCredentials,
)


class FireboltTypeMapper(TypeMapperImpl):
    sct_to_unbound_dbt = {
        "json": "TEXT",
        "text": "TEXT",
        "double": "DOUBLE",
        "bool": "BOOLEAN",
        "date": "DATE",
        "timestamp": "TIMESTAMP",
        "bigint": "BIGINT",
        "binary": "TEXT",
        "time": "TEXT",
        "decimal": "DOUBLE",
        "wei": "TEXT",
    }

    sct_to_dbt = {
        "decimal": "DOUBLE",
        "wei": "TEXT",
    }

    dbt_to_sct = {
        "TEXT": "text",
        "DOUBLE": "double",
        "BOOLEAN": "bool",
        "DATE": "date",
        "TIMESTAMP": "timestamp",
        "BIGINT": "bigint",
        "DECIMAL": "decimal",
    }

    def to_db_datetime_type(
        self,
        column: TColumnSchema,
        table: PreparedTableSchema = None,
    ) -> str:
        return "TIMESTAMP"


class firebolt(Destination[FireboltClientConfiguration, "FireboltClient"]):
    spec = FireboltClientConfiguration

    def _raw_capabilities(self) -> DestinationCapabilitiesContext:
        caps = DestinationCapabilitiesContext()
        caps.preferred_loader_file_format = "parquet"
        caps.supported_loader_file_formats = ["parquet"]
        caps.preferred_staging_file_format = "parquet"
        caps.supported_staging_file_formats = ["parquet"]
        caps.type_mapper = FireboltTypeMapper
        caps.escape_identifier = escape_postgres_identifier
        caps.casefold_identifier = str.lower
        caps.has_case_sensitive_identifiers = False
        caps.decimal_precision = (DEFAULT_NUMERIC_PRECISION, DEFAULT_NUMERIC_SCALE)
        caps.wei_precision = (DEFAULT_NUMERIC_PRECISION, 0)
        caps.max_identifier_length = 255
        caps.max_column_identifier_length = 255
        caps.max_query_length = 256 * 1024
        caps.is_max_query_length_in_bytes = True
        caps.max_text_data_type_length = 65535
        caps.is_max_text_data_type_length_in_bytes = True
        caps.supports_ddl_transactions = True
        caps.supports_transactions = False
        caps.alter_add_multi_column = False
        caps.supported_merge_strategies = ["delete-insert"]
        caps.supported_replace_strategies = ["truncate-and-insert", "insert-from-staging"]
        caps.supports_truncate_command = True
        caps.timestamp_precision = 6
        caps.max_timestamp_precision = 6
        caps.sqlglot_dialect = "firebolt"
        return caps

    @property
    def client_class(self) -> Type["FireboltClient"]:
        from firebolt_dest.client import FireboltClient

        return FireboltClient

    def __init__(
        self,
        credentials: Union[FireboltCredentials, Dict[str, Any], str] = None,
        s3_location_name: str = "firebolt_s3",
        s3_prefix: str = "dlt-landing",
        destination_name: str = None,
        environment: str = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            credentials=credentials,
            s3_location_name=s3_location_name,
            s3_prefix=s3_prefix,
            destination_name=destination_name,
            environment=environment,
            **kwargs,
        )


firebolt.register()

from firebolt_dest.client import FireboltClient  # noqa: E402,F401
