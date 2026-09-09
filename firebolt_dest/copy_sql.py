from __future__ import annotations

import logging
from urllib.parse import urlparse

from dlt.common.exceptions import TerminalValueError

# Child of the dlt logger so diagnostics inherit dlt's handler/level
# (plain __name__ loggers are silent when dlt's logger has propagate=False).
logger = logging.getLogger("dlt.firebolt_dest")

# Glob metacharacters that would turn PATTERN into a wildcard match across
# tenant prefixes if allowed into the COPY PATTERN string.
_GLOB_METACHARS = frozenset("*?[")


def _location_path_prefix(location_url: str) -> str:
    """Return the LOCATION URL path as an object-key prefix ('' = bucket root).

    ``location_url`` may be a full S3 URL (``s3://bucket/prefix/``) or a bare
    path/prefix (``prefix`` / ``prefix/``). Trailing slash is normalized on.
    """
    raw = (location_url or "").strip()
    if not raw or raw in ("/", "s3://", "s3:///"):
        return ""
    if "://" in raw:
        path = urlparse(raw).path.lstrip("/")
    else:
        path = raw.lstrip("/")
    path = path.strip("/")
    if not path:
        return ""
    return path + "/"


def _location_bucket(location_url: str) -> str | None:
    """Return the LOCATION bucket (netloc) when ``location_url`` is a full URL.

    Bare path / ``s3_prefix`` fallbacks have no netloc — return None so callers
    skip the cross-bucket check.
    """
    raw = (location_url or "").strip()
    if "://" not in raw:
        return None
    netloc = urlparse(raw).netloc
    return netloc or None


def _mismatch_message(location_url: str, *, detail: str) -> str:
    """Name the actual setting the user configured (LOCATION URL vs s3_prefix)."""
    raw = (location_url or "").strip()
    if "://" in raw:
        return (
            "Firebolt COPY PATTERN: object key is not under the LOCATION URL path. "
            f"FIREBOLT_S3_LOCATION_URL / s3_location_url={location_url!r}, {detail} "
            "Refusing basename fallback."
        )
    return (
        "Firebolt COPY PATTERN: object key is not under the s3_prefix path used as "
        "the LOCATION fallback. "
        f"s3_prefix={location_url!r}, {detail} "
        "Set FIREBOLT_S3_LOCATION_URL / s3_location_url to the real LOCATION URL "
        "(e.g. s3://bucket/ or s3://bucket/prefix/) when it differs from s3_prefix. "
        "Refusing basename fallback."
    )


def s3_url_to_copy_pattern(file_url: str, location_url: str = "") -> str:
    """Return COPY PATTERN: object key relative to the LOCATION URL path.

    PATTERN is anchored to the Firebolt LOCATION URL, not to the staging
    ``s3_prefix``. ``s3_prefix`` only affects where dlt writes objects.

    Examples (``key`` = object key from bucket root):

    - LOCATION ``s3://example-bucket/`` + key ``tenant-a/dlt/staging/foo.parquet``
      → ``tenant-a/dlt/staging/foo.parquet`` (multi-tenant / bucket-root LOCATION)
    - LOCATION ``s3://example-bucket/tenant-a/`` + key ``tenant-a/dlt/staging/foo.parquet``
      → ``dlt/staging/foo.parquet`` (classic single-tenant)
    - LOCATION ``s3://example-bucket/`` + key ``foo.parquet`` → ``foo.parquet``
    - key not under LOCATION path, or object bucket ≠ LOCATION bucket → raises
      ``TerminalValueError`` (never basename)
    """
    parsed_file = urlparse(file_url)
    key = parsed_file.path.lstrip("/")
    loc_bucket = _location_bucket(location_url)
    if loc_bucket is not None:
        file_bucket = parsed_file.netloc
        if file_bucket and file_bucket != loc_bucket:
            raise TerminalValueError(
                "Firebolt COPY PATTERN: object bucket does not match LOCATION URL "
                f"bucket. LOCATION URL={location_url!r} (bucket={loc_bucket!r}), "
                f"object URL={file_url!r} (bucket={file_bucket!r}). "
                "Refusing to emit a PATTERN that could resolve against the wrong bucket."
            )

    loc_path = _location_path_prefix(location_url)

    if loc_path and not key.startswith(loc_path):
        raise TerminalValueError(
            _mismatch_message(
                location_url,
                detail=f"path prefix {loc_path!r}, object key={key!r}.",
            )
        )

    pattern = key[len(loc_path) :] if loc_path else key
    # Reject glob metacharacters in the resolved PATTERN. Silently escaping
    # would still leave an ambiguous intent; a wildcard matching a sibling
    # tenant prefix is a data-isolation bug.
    bad = sorted({ch for ch in pattern if ch in _GLOB_METACHARS})
    if bad:
        raise TerminalValueError(
            "Firebolt COPY PATTERN: resolved PATTERN contains glob metacharacters "
            f"{bad} (from the object key / staging prefix). Refusing to emit a "
            f"wildcard PATTERN that could match another tenant's objects. "
            f"pattern={pattern!r}."
        )

    logger.debug(
        "Firebolt COPY PATTERN: file_url=%s location_url=%s loc_path=%s pattern=%s",
        file_url,
        location_url,
        loc_path or "(bucket-root)",
        pattern,
    )
    return pattern


def _escape_sql_string_literal(value: str) -> str:
    """Escape a value for embedding in a single-quoted SQL string literal."""
    return value.replace("'", "''")


def gen_firebolt_copy_sql(
    qualified_table_name: str,
    *,
    location_name: str,
    pattern: str,
    file_format: str,
) -> str:
    if file_format != "parquet":
        raise TerminalValueError(
            f"Firebolt prototype only supports parquet, got {file_format!r}"
        )
    # PATTERN was already checked for glob metacharacters in s3_url_to_copy_pattern;
    # still escape quotes so a key segment with an apostrophe cannot break the literal.
    safe_pattern = _escape_sql_string_literal(pattern)
    return f"""COPY INTO {qualified_table_name}
FROM {location_name}
WITH (
  PATTERN = '{safe_pattern}',
  TYPE = PARQUET
)"""
