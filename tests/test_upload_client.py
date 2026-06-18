"""Unit tests for upload:// staging helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from firebolt_dest.upload_client import (
    gen_upload_insert_sql,
    resolve_local_parquet_path,
    sanitize_upload_part_name,
)


def test_sanitize_upload_part_name() -> None:
    assert sanitize_upload_part_name("orders-123.parquet") == "orders-123.parquet"
    assert sanitize_upload_part_name("bad name!") == "bad_name"


def test_gen_upload_insert_sql() -> None:
    sql = gen_upload_insert_sql('"demo_orders"', "orders_123")
    assert "INSERT INTO \"demo_orders\"" in sql
    assert "READ_PARQUET('upload://orders_123')" in sql


def test_resolve_local_parquet_path_file_url() -> None:
    path = resolve_local_parquet_path("file:///tmp/demo/file.parquet")
    assert path == Path("/tmp/demo/file.parquet")


def test_resolve_local_parquet_path_rejects_s3() -> None:
    with pytest.raises(ValueError, match="s3://"):
        resolve_local_parquet_path("s3://bucket/key.parquet")
