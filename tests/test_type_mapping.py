"""Type mapping regression tests.

Covers the dlt >= 1.29 regression where static (non-template) strings in
``sct_to_dbt`` raised ``TypeError: not all arguments converted during string
formatting`` when %-formatted with a precision tuple. Both "decimal" and
"wei" had that bug.
"""

from __future__ import annotations

import pytest
from dlt.common.exceptions import TerminalValueError

from firebolt_dest.factory import FireboltTypeMapper, firebolt


@pytest.fixture()
def mapper() -> FireboltTypeMapper:
    return FireboltTypeMapper(firebolt().capabilities())


def col(data_type: str, precision: int = None, scale: int = None) -> dict:
    return {
        "name": "test_col",
        "data_type": data_type,
        "precision": precision,
        "scale": scale,
    }


table = {"name": "test_table"}


class TestDecimalMapping:
    def test_decimal_with_precision_and_scale(self, mapper):
        assert mapper.to_destination_type(col("decimal", 12, 2), table) == "NUMERIC(12,2)"

    def test_numeric_10_4(self, mapper):
        assert mapper.to_destination_type(col("decimal", 10, 4), table) == "NUMERIC(10,4)"

    def test_decimal_max_precision(self, mapper):
        assert mapper.to_destination_type(col("decimal", 38, 9), table) == "NUMERIC(38,9)"

    def test_decimal_without_precision_uses_dlt_default(self, mapper):
        # dlt default decimal precision is (38, 9), within Firebolt's limit
        assert mapper.to_destination_type(col("decimal"), table) == "NUMERIC(38,9)"

    def test_decimal_scale_only_default_precision(self, mapper):
        assert mapper.to_destination_type(col("decimal", None, 4), table) == "NUMERIC(38,4)"

    def test_money_shape_19_4(self, mapper):
        # SQL Server MONEY reflects as DECIMAL(19, 4) via sql_database source
        assert mapper.to_destination_type(col("decimal", 19, 4), table) == "NUMERIC(19,4)"

    def test_smallmoney_shape_10_4(self, mapper):
        assert mapper.to_destination_type(col("decimal", 10, 4), table) == "NUMERIC(10,4)"

    def test_decimal_scale_zero(self, mapper):
        assert mapper.to_destination_type(col("decimal", 20, 0), table) == "NUMERIC(20,0)"

    def test_precision_above_firebolt_limit_raises(self, mapper):
        with pytest.raises(TerminalValueError, match="precision"):
            mapper.to_destination_type(col("decimal", 39, 2), table)

    def test_precision_below_one_raises(self, mapper):
        with pytest.raises(TerminalValueError, match="precision"):
            mapper.to_destination_type(col("decimal", 0, 0), table)

    def test_scale_greater_than_precision_raises(self, mapper):
        with pytest.raises(TerminalValueError, match="scale"):
            mapper.to_destination_type(col("decimal", 5, 6), table)


class TestOtherParameterizedTypes:
    def test_wei_maps_to_unbound_text(self, mapper):
        # Regression: "wei": "TEXT" in sct_to_dbt was %-formatted with
        # wei_precision (38, 0) and raised TypeError.
        assert mapper.to_destination_type(col("wei"), table) == "TEXT"

    def test_text_with_length_ignores_length(self, mapper):
        # VARCHAR(n) length hint; Firebolt TEXT is unbounded
        assert mapper.to_destination_type(col("text", 255), table) == "TEXT"

    def test_timestamp_with_precision(self, mapper):
        assert mapper.to_destination_type(col("timestamp", 6), table) == "TIMESTAMP"

    def test_time_with_precision(self, mapper):
        assert mapper.to_destination_type(col("time", 6), table) == "TEXT"

    def test_binary_with_length(self, mapper):
        assert mapper.to_destination_type(col("binary", 16), table) == "TEXT"

    def test_unparameterized_types(self, mapper):
        for source, expected in {
            "text": "TEXT",
            "double": "DOUBLE",
            "bool": "BOOLEAN",
            "date": "DATE",
            "bigint": "BIGINT",
            "json": "TEXT",
        }.items():
            assert mapper.to_destination_type(col(source), table) == expected


class TestFromDestinationType:
    """Firebolt information_schema reports parameterized types verbatim."""

    def test_parameterized_numeric(self, mapper):
        assert mapper.from_destination_type("NUMERIC(12, 2)", 12, 2) == {
            "data_type": "decimal",
            "precision": 12,
            "scale": 2,
        }

    def test_bare_numeric(self, mapper):
        assert mapper.from_destination_type("NUMERIC", 38, 9) == {
            "data_type": "decimal",
            "precision": 38,
            "scale": 9,
        }

    def test_double_precision_spelling(self, mapper):
        assert mapper.from_destination_type("DOUBLE PRECISION", None, None) == {
            "data_type": "double"
        }

    def test_non_numeric_types_drop_parameters(self, mapper):
        assert mapper.from_destination_type("TEXT", None, None) == {"data_type": "text"}
        assert mapper.from_destination_type("TIMESTAMP", None, None) == {
            "data_type": "timestamp"
        }

    def test_round_trip_decimal(self, mapper):
        """DDL emitted by to_destination_type must reflect back as decimal."""
        db_type = mapper.to_destination_type(col("decimal", 12, 2), table)
        assert db_type == "NUMERIC(12,2)"
        # Firebolt reports it back as "NUMERIC(12, 2)" with the precision
        # in the dedicated information_schema columns
        reflected = mapper.from_destination_type("NUMERIC(12, 2)", 12, 2)
        assert reflected["data_type"] == "decimal"
        assert (reflected["precision"], reflected["scale"]) == (12, 2)
