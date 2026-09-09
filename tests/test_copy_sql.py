"""Tests for firebolt_dest COPY PATTERN helpers (no Firebolt connection required)."""

from urllib.parse import urlparse

import pytest
from dlt.common.exceptions import TerminalValueError

from firebolt_dest.copy_sql import (
    gen_firebolt_copy_sql,
    s3_url_to_copy_pattern,
)


def _legacy_prefix_relative_pattern(file_url: str, s3_prefix: str) -> str:
    """Historic classic behavior: strip matching s3_prefix; else basename fallback."""
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
        assert got == _legacy_prefix_relative_pattern(url, "dlt-landing")


def test_s3_url_to_copy_pattern_bucket_root_keeps_tenant() -> None:
    """Bucket-root LOCATION + tenant key → PATTERN keeps tenant-a/."""
    url = "s3://example-bucket/tenant-a/dlt/staging/my_dataset/file.parquet"
    assert (
        s3_url_to_copy_pattern(url, "s3://example-bucket/")
        == "tenant-a/dlt/staging/my_dataset/file.parquet"
    )
    # Empty / root location_url also means bucket root.
    assert (
        s3_url_to_copy_pattern(url, "")
        == "tenant-a/dlt/staging/my_dataset/file.parquet"
    )
    assert (
        s3_url_to_copy_pattern(url, "s3://example-bucket")
        == "tenant-a/dlt/staging/my_dataset/file.parquet"
    )


def test_s3_url_to_copy_pattern_location_at_tenant_prefix() -> None:
    """LOCATION at s3://bucket/tenant-a/ → strip loc path only (classic per-tenant LOCATION)."""
    url = "s3://my-bucket/tenant-a/dlt/staging/foo.parquet"
    assert (
        s3_url_to_copy_pattern(url, "s3://my-bucket/tenant-a/")
        == "dlt/staging/foo.parquet"
    )


def test_s3_url_to_copy_pattern_bucket_root_no_prefix() -> None:
    url = "s3://my-bucket/foo.parquet"
    assert s3_url_to_copy_pattern(url, "s3://my-bucket/") == "foo.parquet"
    assert s3_url_to_copy_pattern(url, "") == "foo.parquet"


def test_s3_url_to_copy_pattern_double_slash_key_preserved() -> None:
    """Opaque-key parse strips exactly one leading '/'; doubled slashes stay in the key."""
    url = "s3://example-bucket//tenant-a/file.parquet"
    assert s3_url_to_copy_pattern(url, "s3://example-bucket/") == "/tenant-a/file.parquet"
    assert s3_url_to_copy_pattern(url, "") == "/tenant-a/file.parquet"


def test_s3_url_to_copy_pattern_not_under_location_raises() -> None:
    url = "s3://my-bucket/tenant-a/dlt/staging/file.parquet"
    with pytest.raises(TerminalValueError, match="not under the LOCATION URL path"):
        s3_url_to_copy_pattern(url, "s3://my-bucket/other-prefix/")
    with pytest.raises(TerminalValueError, match="s3_prefix"):
        s3_url_to_copy_pattern(url, "other-prefix")
    # Still a ValueError subclass so broad handlers remain compatible.
    with pytest.raises(ValueError, match="Refusing basename fallback"):
        s3_url_to_copy_pattern(url, "other-prefix")


def test_s3_url_to_copy_pattern_wrong_bucket_raises() -> None:
    """LOCATION on a different bucket than the staged object must not silently pattern."""
    url = "s3://example-bucket/tenant-a/dlt/staging/file.parquet"
    with pytest.raises(TerminalValueError, match="does not match LOCATION URL bucket"):
        s3_url_to_copy_pattern(url, "s3://other-bucket/")
    with pytest.raises(ValueError, match="wrong bucket"):
        s3_url_to_copy_pattern(url, "s3://other-bucket/")


def test_s3_url_to_copy_pattern_wrong_scheme_raises() -> None:
    url = "s3://example-bucket/tenant-a/dlt/staging/file.parquet"
    with pytest.raises(TerminalValueError, match="scheme"):
        s3_url_to_copy_pattern(url, "gs://example-bucket/")


def test_s3_url_to_copy_pattern_degenerate_location_url_raises() -> None:
    """Non-empty LOCATION URLs with no bucket must not skip the cross-bucket guard."""
    url = "s3://example-bucket/tenant-a/dlt/staging/file.parquet"
    for bad in ("s3://", "s3:///", "https://"):
        with pytest.raises(TerminalValueError, match="missing bucket"):
            s3_url_to_copy_pattern(url, bad)
    # Unset location_url still falls back (bucket-root / full key).
    assert s3_url_to_copy_pattern(url, "") == "tenant-a/dlt/staging/file.parquet"


def test_s3_url_to_copy_pattern_rejects_glob_and_fragment_chars() -> None:
    """Opaque keys keep ?/#; those and glob metacharacters must raise (no silent truncate)."""
    root = "s3://example-bucket/"
    cases = [
        ("s3://example-bucket/tenant-*/dlt/staging/file.parquet", r"\*"),
        ("s3://example-bucket/tenant-?/dlt/staging/file.parquet", r"\?"),
        ("s3://example-bucket/tenant-[ab]/dlt/staging/file.parquet", r"\["),
        ("s3://example-bucket/tenant-a/rev#2.parquet", "#"),
    ]
    for url, match in cases:
        with pytest.raises(TerminalValueError, match=match):
            s3_url_to_copy_pattern(url, root)
        # Also a ValueError subclass.
        with pytest.raises(ValueError, match="forbidden characters"):
            s3_url_to_copy_pattern(url, root)


def test_gen_firebolt_copy_sql_escapes_apostrophe_in_pattern() -> None:
    sql = gen_firebolt_copy_sql(
        "my_dataset_orders",
        location_name="firebolt_s3",
        pattern="tenant-a/dlt/staging/o'brien.parquet",
        file_format="parquet",
    )
    assert "PATTERN = 'tenant-a/dlt/staging/o''brien.parquet'" in sql
    assert "CREDENTIALS" not in sql


def test_gen_firebolt_copy_sql() -> None:
    sql = gen_firebolt_copy_sql(
        "demo_hubspot_contacts",
        location_name="firebolt_s3",
        pattern="dlt/staging/file.parquet",
        file_format="parquet",
    )
    assert "COPY INTO demo_hubspot_contacts" in sql
    assert "FROM firebolt_s3" in sql
    assert "TYPE = PARQUET" in sql
    assert "dlt/staging/file.parquet" in sql
    assert "CREDENTIALS" not in sql
