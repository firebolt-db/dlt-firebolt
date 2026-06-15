"""Unit tests for merge/replace SQL generation (no Firebolt connection)."""

from __future__ import annotations

import pytest
from dlt.common.data_writers.escape import escape_postgres_identifier
from dlt.common.destination import DestinationCapabilitiesContext
from dlt.destinations.sql_jobs import SqlStagingReplaceFollowupJob

from firebolt_dest.client import FireboltMergeJob
from firebolt_dest.configuration import FireboltCredentials
from firebolt_dest.sql_client import FireboltSqlClient


@pytest.fixture
def firebolt_sql_client() -> FireboltSqlClient:
    caps = DestinationCapabilitiesContext()
    caps.escape_identifier = escape_postgres_identifier
    caps.casefold_identifier = str.lower
    caps.supports_truncate_command = True
    caps.supported_merge_strategies = ["delete-insert"]
    creds = FireboltCredentials()
    creds.database = "db"
    return FireboltSqlClient("demo", "demo_staging", creds, caps)


def _items_table(*, write_disposition: str, replace_strategy: str | None = None) -> dict:
    table = {
        "name": "items",
        "write_disposition": write_disposition,
        "columns": {
            "id": {"name": "id", "data_type": "bigint", "primary_key": True},
            "value": {"name": "value", "data_type": "text"},
            "_dlt_id": {
                "name": "_dlt_id",
                "data_type": "text",
                "unique": True,
                "row_key": True,
            },
        },
    }
    if replace_strategy is not None:
        table["x-replace-strategy"] = replace_strategy
    return table


def test_merge_sql_delete_insert(firebolt_sql_client: FireboltSqlClient) -> None:
    sql = FireboltMergeJob.generate_sql([_items_table(write_disposition="merge")], firebolt_sql_client)
    joined = "\n".join(sql)

    assert 'DELETE FROM "demo_items"' in joined
    assert '"demo_staging_items"' in joined
    assert 'INSERT INTO "demo_items"' in joined
    assert "ROW_NUMBER() OVER" in joined


def test_replace_insert_from_staging_sql(firebolt_sql_client: FireboltSqlClient) -> None:
    table = _items_table(write_disposition="replace", replace_strategy="insert-from-staging")
    sql = SqlStagingReplaceFollowupJob.generate_sql([table], firebolt_sql_client)
    joined = "\n".join(sql)

    assert 'TRUNCATE TABLE "demo_items"' in joined
    assert 'INSERT INTO "demo_items"' in joined
    assert 'FROM "demo_staging_items"' in joined


def _orders_table_chain() -> list[dict]:
    root = {
        "name": "orders",
        "write_disposition": "merge",
        "columns": {
            "order_id": {"name": "order_id", "data_type": "bigint", "primary_key": True},
            "customer": {"name": "customer", "data_type": "text"},
            "_dlt_id": {
                "name": "_dlt_id",
                "data_type": "text",
                "unique": True,
                "row_key": True,
            },
        },
    }
    child = {
        "name": "orders__items",
        "parent": "orders",
        "write_disposition": "merge",
        "columns": {
            "sku": {"name": "sku", "data_type": "text"},
            "qty": {"name": "qty", "data_type": "bigint"},
            "_dlt_id": {
                "name": "_dlt_id",
                "data_type": "text",
                "unique": True,
                "row_key": True,
            },
            "_dlt_root_id": {"name": "_dlt_root_id", "data_type": "text", "root_key": True},
            "_dlt_parent_id": {
                "name": "_dlt_parent_id",
                "data_type": "text",
                "parent_key": True,
            },
        },
    }
    return [root, child]


def test_nested_merge_uses_regular_tables_not_temp(firebolt_sql_client: FireboltSqlClient) -> None:
    sql = FireboltMergeJob.generate_sql(_orders_table_chain(), firebolt_sql_client)
    joined = "\n".join(sql)

    assert "CREATE TEMPORARY TABLE" not in joined.upper()
    assert 'CREATE TABLE "demo_orders_delete_' in joined
    assert 'CREATE TABLE "demo_orders_insert_' in joined
    assert 'INSERT INTO "demo_orders__items"' in joined
    assert joined.count("DROP TABLE IF EXISTS") >= 4
