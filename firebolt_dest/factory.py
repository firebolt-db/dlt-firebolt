from __future__ import annotations

import re
from typing import Any, Dict, Optional, Type, Union

from dlt.common.arithmetics import DEFAULT_NUMERIC_PRECISION, DEFAULT_NUMERIC_SCALE
from dlt.common.data_writers.escape import escape_postgres_identifier
from dlt.common.destination import Destination, DestinationCapabilitiesContext
from dlt.common.destination.typing import PreparedTableSchema
from dlt.common.exceptions import TerminalValueError
from dlt.common.schema.typing import TColumnSchema, TColumnType

from dlt.destinations.type_mapping import TypeMapperImpl
from firebolt_dest.configuration import (
    FireboltClientConfiguration,
    FireboltCredentials,
)

# https://docs.firebolt.io/reference-sql/data-types/numeric
FIREBOLT_MAX_NUMERIC_PRECISION = 38


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
        # NUMERIC without parameters defaults to NUMERIC(38, 9) in Firebolt.
        "decimal": "NUMERIC",
        "wei": "TEXT",
    }

    sct_to_dbt = {
        "decimal": "NUMERIC(%i,%i)",
        # "wei" must not appear here: templates in sct_to_dbt are %-formatted
        # with a precision tuple, and wei always resolves one via
        # capabilities.wei_precision. It maps to unbound TEXT instead since
        # Firebolt NUMERIC (max precision 38) cannot hold full uint256 values.
    }

    dbt_to_sct = {
        "TEXT": "text",
        "DOUBLE": "double",
        "DOUBLE PRECISION": "double",
        "BOOLEAN": "bool",
        "DATE": "date",
        "TIMESTAMP": "timestamp",
        "BIGINT": "bigint",
        "DECIMAL": "decimal",
        "NUMERIC": "decimal",
    }

    def to_db_datetime_type(
        self,
        column: TColumnSchema,
        table: PreparedTableSchema = None,
    ) -> str:
        return "TIMESTAMP"

    def to_db_decimal_type(self, column: TColumnSchema) -> str:
        precision_tup = self.decimal_precision(
            column.get("precision"), column.get("scale")
        )
        if not precision_tup:
            return self.sct_to_unbound_dbt["decimal"]
        precision, scale = precision_tup
        if precision < 1 or precision > FIREBOLT_MAX_NUMERIC_PRECISION:
            raise TerminalValueError(
                f"Firebolt NUMERIC supports precision 1 to"
                f" {FIREBOLT_MAX_NUMERIC_PRECISION}, but decimal column"
                f" `{column.get('name')}` was declared with {precision=:}."
                " Adjust the column hint or cast the source column."
            )
        if scale < 0 or scale > precision:
            raise TerminalValueError(
                f"Firebolt NUMERIC requires 0 <= scale <= precision, but decimal"
                f" column `{column.get('name')}` was declared with"
                f" {precision=:}, {scale=:}."
                " Adjust the column hint or cast the source column."
            )
        return self.sct_to_dbt["decimal"] % (precision, scale)

    def from_destination_type(
        self, db_type: str, precision: Optional[int], scale: Optional[int]
    ) -> TColumnType:
        # Firebolt's information_schema reports parameterized types verbatim,
        # e.g. "NUMERIC(12, 2)". Strip the parameters so the base type matches
        # dbt_to_sct; precision and scale arrive via the dedicated
        # numeric_precision / numeric_scale columns.
        base_type = re.sub(r"\(.+\)$", "", db_type).strip()
        if base_type not in ("NUMERIC", "DECIMAL"):
            # Parameters are only meaningful for numeric types in Firebolt.
            precision = scale = None
        return super().from_destination_type(base_type, precision, scale)


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
        staging_mode: str = "upload",
        destination_name: str = None,
        environment: str = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            credentials=credentials,
            s3_location_name=s3_location_name,
            s3_prefix=s3_prefix,
            staging_mode=staging_mode,
            destination_name=destination_name,
            environment=environment,
            **kwargs,
        )


firebolt.register()

from firebolt_dest.client import FireboltClient  # noqa: E402,F401
