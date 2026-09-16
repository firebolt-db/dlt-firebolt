"""Tests for firebolt_dest COPY PATTERN helpers (no Firebolt connection required)."""

from urllib.parse import urlparse

import pytest
from dlt.common.exceptions import TerminalValueError

from firebolt_dest.copy_sql import (
    gen_firebolt_copy_sql,
    resolve_copy_location,
    s3_url_to_copy_pattern,
)


def _legacy_prefix_relative_pattern(file_url: str, s3_prefix: str) -> str:
    """Historic classic behavior: strip matching s3_prefix; else basename fallback."""
    path = urlparse(file_url).path.lstrip("/")
    prefix = s3_prefix.strip("/") + "/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return path.split("/")[-1]


def test_resolve_copy_location_scheme_less_raises() -> None:
    with pytest.raises(TerminalValueError, match="s3_location_url"):
        resolve_copy_location("my-bucket/", "dlt-landing")


def test_resolve_copy_location_whitespace_falls_back_to_prefix() -> None:
    url, source = resolve_copy_location("   ", "dlt-landing")
    assert url == "dlt-landing"
    assert source == "s3_prefix"


def test_resolve_copy_location_empty_strips_doubled_slash_prefix() -> None:
    """Match main: s3_prefix.strip('/') so dlt-landing// still strips correctly."""
    url, source = resolve_copy_location("", "dlt-landing//")
    assert url == "dlt-landing"
    assert source == "s3_prefix"


def test_resolve_copy_location_valid_url() -> None:
    url, source = resolve_copy_location("s3://example-bucket/", "tenant-a")
    assert url == "s3://example-bucket/"
    assert source == "s3_location_url"


def test_resolve_copy_location_degenerate_bucket_raises() -> None:
    with pytest.raises(TerminalValueError, match="missing bucket"):
        resolve_copy_location("s3://", "dlt-landing")


def test_s3_url_to_copy_pattern_classic_matches_original() -> None:
    """LOCATION path = s3_prefix → relative PATTERN, byte-identical to original."""
    url = "s3://my-bucket/dlt-landing/dlt/staging/hubspot/file.parquet"
    got_bare = s3_url_to_copy_pattern(
        url, "dlt-landing", location_source="s3_prefix"
    )
    got_full = s3_url_to_copy_pattern(
        url, "s3://my-bucket/dlt-landing/", location_source="s3_location_url"
    )
    assert got_bare == "dlt/staging/hubspot/file.parquet"
    assert got_full == "dlt/staging/hubspot/file.parquet"
    assert got_bare == _legacy_prefix_relative_pattern(url, "dlt-landing")


def test_s3_url_to_copy_pattern_doubled_slash_prefix_via_resolve() -> None:
    """Bare prefix with extra slashes works after resolve_copy_location strip."""
    url = "s3://example-bucket/dlt-landing/dlt/staging/file.parquet"
    loc, source = resolve_copy_location("", "dlt-landing//")
    assert s3_url_to_copy_pattern(url, loc, location_source=source) == (
        "dlt/staging/file.parquet"
    )


def test_s3_url_to_copy_pattern_bucket_root_keeps_tenant() -> None:
    """Bucket-root LOCATION + tenant key → PATTERN keeps tenant-a/."""
    url = "s3://example-bucket/tenant-a/dlt/staging/my_dataset/file.parquet"
    assert (
        s3_url_to_copy_pattern(
            url, "s3://example-bucket/", location_source="s3_location_url"
        )
        == "tenant-a/dlt/staging/my_dataset/file.parquet"
    )
    # Empty location_url with s3_prefix source means bucket-root / full key.
    assert (
        s3_url_to_copy_pattern(url, "", location_source="s3_prefix")
        == "tenant-a/dlt/staging/my_dataset/file.parquet"
    )
    assert (
        s3_url_to_copy_pattern(
            url, "s3://example-bucket", location_source="s3_location_url"
        )
        == "tenant-a/dlt/staging/my_dataset/file.parquet"
    )


def test_s3_url_to_copy_pattern_location_at_tenant_prefix() -> None:
    """LOCATION at s3://bucket/tenant-a/ → strip loc path only (classic per-tenant LOCATION)."""
    url = "s3://my-bucket/tenant-a/dlt/staging/foo.parquet"
    assert (
        s3_url_to_copy_pattern(
            url, "s3://my-bucket/tenant-a/", location_source="s3_location_url"
        )
        == "dlt/staging/foo.parquet"
    )


def test_s3_url_to_copy_pattern_bucket_root_no_prefix() -> None:
    url = "s3://my-bucket/foo.parquet"
    assert (
        s3_url_to_copy_pattern(
            url, "s3://my-bucket/", location_source="s3_location_url"
        )
        == "foo.parquet"
    )
    assert s3_url_to_copy_pattern(url, "", location_source="s3_prefix") == "foo.parquet"


def test_s3_url_to_copy_pattern_double_slash_key_preserved() -> None:
    """Opaque-key parse strips exactly one leading '/'; doubled slashes stay in the key."""
    url = "s3://example-bucket//tenant-a/file.parquet"
    assert (
        s3_url_to_copy_pattern(
            url, "s3://example-bucket/", location_source="s3_location_url"
        )
        == "/tenant-a/file.parquet"
    )
    assert (
        s3_url_to_copy_pattern(url, "", location_source="s3_prefix")
        == "/tenant-a/file.parquet"
    )


def test_s3_url_to_copy_pattern_not_under_location_raises() -> None:
    url = "s3://my-bucket/tenant-a/dlt/staging/file.parquet"
    with pytest.raises(TerminalValueError, match="not under the LOCATION URL path"):
        s3_url_to_copy_pattern(
            url, "s3://my-bucket/other-prefix/", location_source="s3_location_url"
        )
    with pytest.raises(TerminalValueError, match="s3_prefix"):
        s3_url_to_copy_pattern(url, "other-prefix", location_source="s3_prefix")
    with pytest.raises(ValueError, match="Refusing basename fallback"):
        s3_url_to_copy_pattern(url, "other-prefix", location_source="s3_prefix")


def test_s3_url_to_copy_pattern_wrong_bucket_raises() -> None:
    """LOCATION on a different bucket than the staged object must not silently pattern."""
    url = "s3://example-bucket/tenant-a/dlt/staging/file.parquet"
    with pytest.raises(TerminalValueError, match="does not match LOCATION URL bucket"):
        s3_url_to_copy_pattern(
            url, "s3://other-bucket/", location_source="s3_location_url"
        )


def test_s3_url_to_copy_pattern_bucket_less_object_raises() -> None:
    """Object URL without a bucket must fail closed when LOCATION has a bucket."""
    with pytest.raises(TerminalValueError, match="object URL has no bucket"):
        s3_url_to_copy_pattern(
            "s3:///tenant-a/file.parquet",
            "s3://expected/tenant-a/",
            location_source="s3_location_url",
        )


def test_s3_url_to_copy_pattern_wrong_scheme_raises() -> None:
    url = "s3://example-bucket/tenant-a/dlt/staging/file.parquet"
    with pytest.raises(TerminalValueError, match="scheme"):
        s3_url_to_copy_pattern(
            url, "gs://example-bucket/", location_source="s3_location_url"
        )


def test_s3_url_to_copy_pattern_degenerate_location_url_raises() -> None:
    """Non-empty LOCATION URLs with no bucket must not skip the cross-bucket guard."""
    url = "s3://example-bucket/tenant-a/dlt/staging/file.parquet"
    for bad in ("s3://", "s3:///", "https://"):
        with pytest.raises(TerminalValueError, match="missing bucket"):
            s3_url_to_copy_pattern(url, bad, location_source="s3_location_url")
    assert (
        s3_url_to_copy_pattern(url, "", location_source="s3_prefix")
        == "tenant-a/dlt/staging/file.parquet"
    )


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
            s3_url_to_copy_pattern(url, root, location_source="s3_location_url")
        with pytest.raises(ValueError, match="forbidden characters"):
            s3_url_to_copy_pattern(url, root, location_source="s3_location_url")


def test_s3_url_to_copy_pattern_rejects_colon_and_backslash() -> None:
    root = "s3://example-bucket/"
    with pytest.raises(TerminalValueError, match=":"):
        s3_url_to_copy_pattern(
            "s3://example-bucket/t/:seg/file.parquet",
            root,
            location_source="s3_location_url",
        )
    with pytest.raises(TerminalValueError, match=r"\\\\"):
        s3_url_to_copy_pattern(
            r"s3://example-bucket/t/\seg/file.parquet",
            root,
            location_source="s3_location_url",
        )


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
