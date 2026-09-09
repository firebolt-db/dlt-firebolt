"""Unit tests for merge/replace SQL generation (no Firebolt connection)."""

from __future__ import annotations

import pytest
from dlt.common.data_writers.escape import escape_postgres_identifier
from dlt.common.destination import DestinationCapabilitiesContext
from dlt.destinations.sql_jobs import SqlStagingReplaceFollowupJob

from firebolt_dest.client import FireboltMergeJob
from firebolt_dest.configuration import FireboltCredentials
from firebolt_dest.sql_client import FireboltSqlClient


def _sql_client(
    *,
    use_schema_per_dataset: bool = False,
    dataset_name: str = "demo",
) -> FireboltSqlClient:
    caps = DestinationCapabilitiesContext()
    caps.escape_identifier = escape_postgres_identifier
    caps.casefold_identifier = str.lower
    caps.supports_truncate_command = True
    caps.supported_merge_strategies = ["delete-insert"]
    creds = FireboltCredentials()
    creds.database = "db"
    staging = f"{dataset_name}_staging"
    return FireboltSqlClient(
        dataset_name,
        staging,
        creds,
        caps,
        use_schema_per_dataset=use_schema_per_dataset,
    )


@pytest.fixture
def firebolt_sql_client() -> FireboltSqlClient:
    """Default (flag off) client — preserves historic public-prefix assertions."""
    return _sql_client(use_schema_per_dataset=False)


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


def test_merge_sql_delete_insert_schema_per_dataset() -> None:
    client = _sql_client(use_schema_per_dataset=True)
    sql = FireboltMergeJob.generate_sql([_items_table(write_disposition="merge")], client)
    joined = "\n".join(sql)

    assert 'DELETE FROM "demo"."items"' in joined
    assert '"demo_staging"."items"' in joined
    assert 'INSERT INTO "demo"."items"' in joined
    assert "ROW_NUMBER() OVER" in joined
    assert "public" not in joined
    assert "demo_items" not in joined


def test_replace_insert_from_staging_sql(firebolt_sql_client: FireboltSqlClient) -> None:
    table = _items_table(write_disposition="replace", replace_strategy="insert-from-staging")
    sql = SqlStagingReplaceFollowupJob.generate_sql([table], firebolt_sql_client)
    joined = "\n".join(sql)

    assert 'TRUNCATE TABLE "demo_items"' in joined
    assert 'INSERT INTO "demo_items"' in joined
    assert 'FROM "demo_staging_items"' in joined


def test_replace_insert_from_staging_sql_schema_per_dataset() -> None:
    client = _sql_client(use_schema_per_dataset=True)
    table = _items_table(write_disposition="replace", replace_strategy="insert-from-staging")
    sql = SqlStagingReplaceFollowupJob.generate_sql([table], client)
    joined = "\n".join(sql)

    # Schema mode must not emit TRUNCATE (Core silent no-op on schema-qualified
    # tables on older builds); replace uses DELETE ... WHERE 1=1 instead.
    assert 'DELETE FROM "demo"."items" WHERE 1=1' in joined
    assert "TRUNCATE" not in joined.upper()
    assert 'INSERT INTO "demo"."items"' in joined
    assert 'FROM "demo_staging"."items"' in joined
    assert "public" not in joined


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
    # CREATE is embedded in "DROP ...; CREATE TABLE <name> AS ..." statements.
    delete_name = next(
        s.split("CREATE TABLE ", 1)[1].split(" AS ", 1)[0].strip()
        for s in sql
        if "CREATE TABLE " in s and "_delete_" in s
    )
    insert_name = next(
        s.split("CREATE TABLE ", 1)[1].split(" AS ", 1)[0].strip()
        for s in sql
        if "CREATE TABLE " in s and "_insert_" in s
    )
    # One DROP before CREATE (same stmt) + one trailing cleanup DROP.
    assert sum(1 for s in sql if f"DROP TABLE IF EXISTS {delete_name}" in s) == 2
    assert sum(1 for s in sql if f"DROP TABLE IF EXISTS {insert_name}" in s) == 2
    assert set(sql[-2:]) == {
        f"DROP TABLE IF EXISTS {delete_name}",
        f"DROP TABLE IF EXISTS {insert_name}",
    }


def test_nested_merge_schema_per_dataset() -> None:
    client = _sql_client(use_schema_per_dataset=True)
    sql = FireboltMergeJob.generate_sql(_orders_table_chain(), client)
    joined = "\n".join(sql)

    assert "CREATE TEMPORARY TABLE" not in joined.upper()
    assert 'CREATE TABLE "demo"."orders_delete_' in joined
    assert 'CREATE TABLE "demo"."orders_insert_' in joined
    assert 'INSERT INTO "demo"."orders__items"' in joined
    assert "public" not in joined
    delete_name = next(
        s.split("CREATE TABLE ", 1)[1].split(" AS ", 1)[0].strip()
        for s in sql
        if "CREATE TABLE " in s and "_delete_" in s
    )
    insert_name = next(
        s.split("CREATE TABLE ", 1)[1].split(" AS ", 1)[0].strip()
        for s in sql
        if "CREATE TABLE " in s and "_insert_" in s
    )
    assert delete_name.startswith('"demo"."orders_delete_')
    assert insert_name.startswith('"demo"."orders_insert_')
    assert sum(1 for s in sql if f"DROP TABLE IF EXISTS {delete_name}" in s) == 2
    assert sum(1 for s in sql if f"DROP TABLE IF EXISTS {insert_name}" in s) == 2
    assert set(sql[-2:]) == {
        f"DROP TABLE IF EXISTS {delete_name}",
        f"DROP TABLE IF EXISTS {insert_name}",
    }


def test_nested_merge_schema_per_dataset_whitespace_dataset_drops_helpers() -> None:
    """Whitespace in the schema name must not orphan helper tables (no regex recovery)."""
    client = _sql_client(use_schema_per_dataset=True, dataset_name="tenant a")
    sql = FireboltMergeJob.generate_sql(_orders_table_chain(), client)
    joined = "\n".join(sql)

    assert 'CREATE TABLE "tenant a"."orders_delete_' in joined
    assert 'CREATE TABLE "tenant a"."orders_insert_' in joined
    delete_name = next(
        s.split("CREATE TABLE ", 1)[1].split(" AS ", 1)[0].strip()
        for s in sql
        if "CREATE TABLE " in s and "_delete_" in s
    )
    insert_name = next(
        s.split("CREATE TABLE ", 1)[1].split(" AS ", 1)[0].strip()
        for s in sql
        if "CREATE TABLE " in s and "_insert_" in s
    )
    assert delete_name.startswith('"tenant a"."orders_delete_')
    assert insert_name.startswith('"tenant a"."orders_insert_')
    assert set(sql[-2:]) == {
        f"DROP TABLE IF EXISTS {delete_name}",
        f"DROP TABLE IF EXISTS {insert_name}",
    }
    assert sum(1 for s in sql if f"DROP TABLE IF EXISTS {delete_name}" in s) == 2
    assert sum(1 for s in sql if f"DROP TABLE IF EXISTS {insert_name}" in s) == 2
