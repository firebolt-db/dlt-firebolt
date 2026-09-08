"""Unit tests for FireboltSqlClient transaction + schema-per-dataset behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dlt.common.data_writers.escape import escape_postgres_identifier
from dlt.common.destination import DestinationCapabilitiesContext

from firebolt_dest.configuration import FireboltCredentials
from firebolt_dest.sql_client import FireboltSqlClient

# Canonical dlt state table names — must resolve under the dataset schema when
# use_schema_per_dataset is on (not public).
_DLT_STATE_TABLES = ("_dlt_loads", "_dlt_pipeline_state", "_dlt_version")


def _caps() -> DestinationCapabilitiesContext:
    caps = DestinationCapabilitiesContext()
    caps.escape_identifier = escape_postgres_identifier
    caps.casefold_identifier = str.lower
    return caps


def _client(
    *,
    in_transaction: bool = False,
    use_schema_per_dataset: bool = False,
    dataset_name: str = "demo",
    staging_dataset_name: str = "demo_staging",
) -> FireboltSqlClient:
    creds = FireboltCredentials()
    creds.database = "db"
    client = FireboltSqlClient(
        dataset_name,
        staging_dataset_name,
        creds,
        _caps(),
        use_schema_per_dataset=use_schema_per_dataset,
    )
    client._conn = MagicMock()
    client._conn.in_transaction.return_value = in_transaction
    return client


def test_begin_transaction_commits_on_success() -> None:
    client = _client()
    with client.begin_transaction():
        pass
    client._conn.commit.assert_called_once()
    client._conn.rollback.assert_not_called()
    assert client._in_transaction is False


def test_begin_transaction_commits_existing_transaction_first() -> None:
    client = _client(in_transaction=True)
    with client.begin_transaction():
        pass
    assert client._conn.commit.call_count == 2
    assert client._in_transaction is False


def test_begin_transaction_rolls_back_on_error() -> None:
    client = _client()
    with pytest.raises(RuntimeError, match="boom"):
        with client.begin_transaction():
            raise RuntimeError("boom")
    client._conn.rollback.assert_called_once()
    client._conn.commit.assert_not_called()
    assert client._in_transaction is False


def test_execute_query_rolls_back_after_error_outside_transaction() -> None:
    client = _client()
    client._conn.execute.side_effect = RuntimeError("table missing")
    with pytest.raises(Exception):
        client.execute_sql("SELECT 1")
    client._conn.rollback.assert_called_once()


def test_execute_query_does_not_commit_outside_transaction() -> None:
    client = _client()
    client.execute_sql("SELECT 1")
    client._conn.commit.assert_not_called()


def test_execute_query_defers_rollback_to_begin_transaction() -> None:
    client = _client()
    client._conn.execute.side_effect = RuntimeError("fail")
    with pytest.raises(Exception):
        with client.begin_transaction():
            client.execute_sql("SELECT 1")
    client._conn.rollback.assert_called_once()


# --- schema-per-dataset (FB-3446) -------------------------------------------------


def test_make_qualified_table_name_path_flag_off_matches_original() -> None:
    """OFF mode must stay byte-identical to the historic public-prefix layout."""
    client = _client(use_schema_per_dataset=False)
    assert client.make_qualified_table_name_path(None) == ["public"]
    assert client.make_qualified_table_name_path(None, quote=False) == ["public"]
    assert client.make_qualified_table_name_path("orders") == ['"demo_orders"']
    assert client.make_qualified_table_name_path("orders", quote=False) == ["demo_orders"]
    assert client.make_qualified_table_name("orders") == '"demo_orders"'
    assert client.make_qualified_table_name_path("_dlt_loads") == ['"demo__dlt_loads"']


def test_make_qualified_table_name_path_flag_on_schema_qualified() -> None:
    client = _client(use_schema_per_dataset=True)
    assert client.make_qualified_table_name_path(None) == ['"demo"']
    assert client.make_qualified_table_name_path(None, quote=False) == ["demo"]
    assert client.make_qualified_table_name_path("orders") == ['"demo"', '"orders"']
    assert client.make_qualified_table_name_path("orders", quote=False) == ["demo", "orders"]
    assert client.make_qualified_table_name("orders") == '"demo"."orders"'
    # Must not touch public when the flag is on.
    for part in client.make_qualified_table_name_path("orders"):
        assert part.strip('"') != "public"


def test_make_qualified_schema_and_table_are_quoted() -> None:
    """Schema and table identifiers go through the existing escape_identifier path."""
    client = _client(use_schema_per_dataset=True, dataset_name="tenant_a")
    assert client.make_qualified_table_name_path("orders") == [
        '"tenant_a"',
        '"orders"',
    ]
    assert client.make_qualified_table_name("orders") == '"tenant_a"."orders"'


def test_information_schema_components_both_modes() -> None:
    off = _client(use_schema_per_dataset=False)
    assert off._get_information_schema_components("orders") == (
        None,
        "public",
        ["demo_orders"],
    )
    on = _client(use_schema_per_dataset=True)
    assert on._get_information_schema_components("orders") == (
        None,
        "demo",
        ["orders"],
    )


def test_create_drop_dataset_flag_off_are_noops() -> None:
    client = _client(use_schema_per_dataset=False)
    client.execute_sql = MagicMock()
    assert client.create_dataset() is None
    assert client.drop_dataset() is None
    assert client.has_dataset() is True
    client.execute_sql.assert_not_called()


def test_create_dataset_flag_on_emits_create_schema() -> None:
    client = _client(use_schema_per_dataset=True)
    client.execute_sql = MagicMock()
    client.create_dataset()
    client.execute_sql.assert_called_once_with('CREATE SCHEMA IF NOT EXISTS "demo"')


def test_drop_dataset_flag_on_emits_drop_schema_cascade() -> None:
    """Match dlt SqlClientBase: DROP SCHEMA ... CASCADE."""
    client = _client(use_schema_per_dataset=True)
    client.execute_sql = MagicMock()
    client.drop_dataset()
    client.execute_sql.assert_called_once_with('DROP SCHEMA "demo" CASCADE')


def test_has_dataset_flag_on_queries_schemata() -> None:
    client = _client(use_schema_per_dataset=True)
    client.execute_sql = MagicMock(return_value=[(1,)])
    assert client.has_dataset() is True
    sql, *params = client.execute_sql.call_args[0]
    assert "INFORMATION_SCHEMA.SCHEMATA" in sql.upper().replace(" ", "")
    assert "schema_name" in sql
    assert params == ["demo"]

    client.execute_sql = MagicMock(return_value=[])
    assert client.has_dataset() is False


def test_staging_dataset_becomes_schema_when_flag_on() -> None:
    client = _client(use_schema_per_dataset=True)
    client.execute_sql = MagicMock()
    with client.with_staging_dataset():
        assert client.dataset_name == "demo_staging"
        assert client.make_qualified_table_name_path("items") == [
            '"demo_staging"',
            '"items"',
        ]
        client.create_dataset()
        client.execute_sql.assert_called_with(
            'CREATE SCHEMA IF NOT EXISTS "demo_staging"'
        )
        client.drop_dataset()
        client.execute_sql.assert_called_with('DROP SCHEMA "demo_staging" CASCADE')


@pytest.mark.parametrize("use_schema_per_dataset", [False, True])
def test_state_tables_location(use_schema_per_dataset: bool) -> None:
    """Critical: dlt state tables follow make_qualified — dataset schema when on."""
    client = _client(use_schema_per_dataset=use_schema_per_dataset)
    for table in _DLT_STATE_TABLES:
        path = client.make_qualified_table_name_path(table)
        qualified = client.make_qualified_table_name(table)
        if use_schema_per_dataset:
            assert path == ['"demo"', f'"{table}"']
            assert qualified == f'"demo"."{table}"'
            assert "public" not in path
            assert "public" not in qualified
        else:
            # Historic public-prefix flatten (double underscore before _dlt_*).
            assert path == [f'"demo_{table}"']
            assert qualified == f'"demo_{table}"'


def test_truncate_table_sql_flag_off_emits_truncate() -> None:
    """Flag OFF: byte-identical to dlt default with supports_truncate_command=True."""
    client = _client(use_schema_per_dataset=False)
    assert client.capabilities.supports_truncate_command is True
    assert (
        client._truncate_table_sql('"demo_orders"')
        == 'TRUNCATE TABLE "demo_orders"'
    )


def test_truncate_table_sql_flag_on_emits_delete_where_1eq1() -> None:
    """Flag ON: DELETE ... WHERE 1=1 — not TRUNCATE, not bare DELETE."""
    client = _client(use_schema_per_dataset=True)
    sql = client._truncate_table_sql('"demo"."orders"')
    assert sql == 'DELETE FROM "demo"."orders" WHERE 1=1'
    assert "TRUNCATE" not in sql.upper()
    assert "WHERE 1=1" in sql
