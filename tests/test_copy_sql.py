"""Tests for firebolt_dest (no Firebolt connection required)."""

from urllib.parse import urlparse

import pytest

from firebolt_dest.copy_sql import (
    gen_firebolt_copy_sql,
    s3_url_to_copy_pattern,
)


def _original_s3_url_to_copy_pattern(file_url: str, s3_prefix: str) -> str:
    """Pre-CHANGE-2 behavior (strip s3_prefix / basename fallback)."""
    path = urlparse(file_url).path.lstrip("/")
    prefix = s3_prefix.strip("/") + "/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return path.split("/")[-1]


def test_s3_url_to_copy_pattern_classic_matches_original() -> None:
    """LOCATION path = s3_prefix → relative PATTERN, byte-identical to original."""
    url = "s3://my-bucket/dlt-landing/dlt/staging/hubspot/file.parquet"
    # Bare prefix (fallback when s3_location_url unset) and full LOCATION URL.
    for location_url in ("dlt-landing", "s3://my-bucket/dlt-landing/"):
        got = s3_url_to_copy_pattern(url, location_url)
        assert got == "dlt/staging/hubspot/file.parquet"
        assert got == _original_s3_url_to_copy_pattern(url, "dlt-landing")


def test_s3_url_to_copy_pattern_fieldassist_bucket_root_keeps_tenant() -> None:
    """Bucket-root LOCATION + tenant key → PATTERN keeps colpal/ (FA acceptance)."""
    url = "s3://fieldassist-firebolt-staging/colpal/dlt/staging/tenant_colpal/file.parquet"
    assert (
        s3_url_to_copy_pattern(url, "s3://fieldassist-firebolt-staging/")
        == "colpal/dlt/staging/tenant_colpal/file.parquet"
    )
    # Empty / root location_url also means bucket root.
    assert (
        s3_url_to_copy_pattern(url, "")
        == "colpal/dlt/staging/tenant_colpal/file.parquet"
    )
    assert (
        s3_url_to_copy_pattern(url, "s3://fieldassist-firebolt-staging")
        == "colpal/dlt/staging/tenant_colpal/file.parquet"
    )


def test_s3_url_to_copy_pattern_location_at_tenant_prefix() -> None:
    """LOCATION at s3://bucket/colpal/ → strip loc path only (classic per-tenant LOCATION)."""
    url = "s3://my-bucket/colpal/dlt/staging/foo.parquet"
    assert (
        s3_url_to_copy_pattern(url, "s3://my-bucket/colpal/")
        == "dlt/staging/foo.parquet"
    )


def test_s3_url_to_copy_pattern_bucket_root_no_prefix() -> None:
    url = "s3://my-bucket/foo.parquet"
    assert s3_url_to_copy_pattern(url, "s3://my-bucket/") == "foo.parquet"
    assert s3_url_to_copy_pattern(url, "") == "foo.parquet"


def test_s3_url_to_copy_pattern_not_under_location_raises() -> None:
    url = "s3://my-bucket/tenant-a/dlt/staging/file.parquet"
    with pytest.raises(ValueError, match="not under the LOCATION URL path"):
        s3_url_to_copy_pattern(url, "s3://my-bucket/other-prefix/")
    with pytest.raises(ValueError, match="Refusing basename fallback"):
        s3_url_to_copy_pattern(url, "other-prefix")


def test_gen_firebolt_copy_sql() -> None:
    sql = gen_firebolt_copy_sql(
        "demo_hubspot_contacts",
        location_name="firebolt_s3",
        pattern="dlt/staging/*.parquet",
        file_format="parquet",
    )
    assert "COPY INTO demo_hubspot_contacts" in sql
    assert "FROM firebolt_s3" in sql
    assert "TYPE = PARQUET" in sql
    assert "dlt/staging/*.parquet" in sql
    assert "CREDENTIALS" not in sql
