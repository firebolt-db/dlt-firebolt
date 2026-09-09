"""Client-level tests for FireboltCopyLoadJob location_url resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from dlt.common.exceptions import TerminalValueError
from dlt.common.schema import Schema
from dlt.destinations.job_impl import ReferenceFollowupJobRequest

from firebolt_dest.client import FireboltClient, FireboltCopyLoadJob
from firebolt_dest.configuration import FireboltClientConfiguration, FireboltCredentials
from firebolt_dest.factory import firebolt as firebolt_destination


def _ref_job_path(remote_s3_url: str) -> str:
    """Create a .reference file whose body is the staged object URL."""
    ref = ReferenceFollowupJobRequest(
        "orders.abc123.0.parquet",
        [remote_s3_url],
    )
    return ref._file_path


def _make_copy_job(
    *,
    bucket_path: str,
    s3_prefix: str,
    s3_location_url: str,
) -> FireboltCopyLoadJob:
    job = FireboltCopyLoadJob(
        _ref_job_path(bucket_path),
        location_name="firebolt_s3",
        s3_prefix=s3_prefix,
        s3_location_url=s3_location_url,
    )
    assert job._bucket_path == bucket_path
    job._load_table = {"name": "orders"}
    job._job_client = MagicMock()
    job._sql_client = MagicMock()
    job._sql_client.make_qualified_table_name.return_value = '"demo_orders"'
    return job


def test_copy_job_prefers_s3_location_url_over_s3_prefix() -> None:
    job = _make_copy_job(
        bucket_path="s3://example-bucket/tenant-a/dlt/staging/orders.abc123.0.parquet",
        s3_prefix="tenant-a",
        s3_location_url="s3://example-bucket/",
    )
    location_url = job._s3_location_url or job._s3_prefix
    assert location_url == "s3://example-bucket/"
    assert job._s3_prefix == "tenant-a"


def test_copy_job_falls_back_to_s3_prefix_when_location_url_empty() -> None:
    job = _make_copy_job(
        bucket_path="s3://example-bucket/dlt-landing/dlt/staging/orders.abc123.0.parquet",
        s3_prefix="dlt-landing",
        s3_location_url="",
    )
    location_url = job._s3_location_url or job._s3_prefix
    assert location_url == "dlt-landing"


def test_copy_load_job_wrong_bucket_is_terminal() -> None:
    """run() must raise TerminalValueError (not a retried bare ValueError)."""
    job = _make_copy_job(
        bucket_path="s3://example-bucket/tenant-a/dlt/staging/orders.abc123.0.parquet",
        s3_prefix="tenant-a",
        s3_location_url="s3://other-bucket/",
    )
    with pytest.raises(TerminalValueError, match="does not match LOCATION URL bucket"):
        job.run()
    job._sql_client.execute_sql.assert_not_called()


def test_copy_load_job_glob_prefix_is_terminal() -> None:
    job = _make_copy_job(
        bucket_path="s3://example-bucket/tenant-*/dlt/staging/orders.abc123.0.parquet",
        s3_prefix="tenant-*",
        s3_location_url="s3://example-bucket/",
    )
    with pytest.raises(TerminalValueError, match="glob metacharacters"):
        job.run()
    job._sql_client.execute_sql.assert_not_called()


def test_create_load_job_wires_s3_location_url_from_config() -> None:
    """create_load_job must pass config.s3_location_url / s3_prefix onto the copy job."""
    creds = FireboltCredentials()
    creds.database = "firebolt"
    cfg = FireboltClientConfiguration()
    cfg.credentials = creds
    cfg.dataset_name = "demo"
    cfg.staging_mode = "s3"
    cfg.s3_location_name = "firebolt_s3"
    cfg.s3_prefix = "tenant-b"
    cfg.s3_location_url = "s3://example-bucket/"
    caps = firebolt_destination()._raw_capabilities()
    schema = Schema("demo")
    client = FireboltClient(schema, cfg, caps)

    table = {"name": "orders", "columns": {}}
    ref_path = _ref_job_path(
        "s3://example-bucket/tenant-b/dlt/staging/orders.abc123.0.parquet"
    )
    with patch.object(
        FireboltClient.__mro__[1], "create_load_job", return_value=None
    ):
        job = client.create_load_job(table, ref_path, "load-1")  # type: ignore[arg-type]

    assert isinstance(job, FireboltCopyLoadJob)
    assert job._s3_location_url == "s3://example-bucket/"
    assert job._s3_prefix == "tenant-b"
