from __future__ import annotations

import logging

from dlt.common.exceptions import TerminalValueError

# Child of the dlt logger so diagnostics inherit dlt's handler/level
# (plain __name__ loggers are silent when dlt's logger has propagate=False).
logger = logging.getLogger("dlt.firebolt_dest")

# Characters that must not appear in a resolved COPY PATTERN:
# - * ? [  — Firebolt/glob wildcards (tenant-isolation hazard)
# - #      — URL fragment delimiter; must stay literal key bytes, but we reject
#            it so a fragment-like suffix cannot be confused with a key segment
_GLOB_METACHARS = frozenset("*?[")
_PATTERN_FORBIDDEN = _GLOB_METACHARS | frozenset("#")


def _split_opaque_url(url: str) -> tuple[str | None, str | None, str]:
    """Split ``scheme://netloc/key`` by string ops; keep the key opaque.

    Unlike ``urllib.parse.urlparse``, this does **not** treat ``?`` / ``#`` as
    query/fragment delimiters — those bytes stay in the key (legal in S3).
    Exactly one leading ``/`` is stripped from the key portion when present;
    further leading slashes (double-slash keys) are preserved.
    """
    raw = url or ""
    if "://" not in raw:
        key = raw[1:] if raw.startswith("/") else raw
        return None, None, key
    scheme, rest = raw.split("://", 1)
    slash = rest.find("/")
    if slash < 0:
        return scheme or None, rest or None, ""
    netloc = rest[:slash]
    key_raw = rest[slash:]  # includes the leading '/'
    key = key_raw[1:] if key_raw.startswith("/") else key_raw
    return scheme or None, netloc or None, key


def _location_path_prefix(location_url: str) -> str:
    """Return the LOCATION URL path as an object-key prefix ('' = bucket root).

    ``location_url`` may be a full S3 URL (``s3://bucket/prefix/``) or a bare
    path/prefix (``prefix`` / ``prefix/``). A single trailing slash is
    normalized on when the path is non-empty. Does not strip interior or
    doubled slashes from the key.
    """
    raw = (location_url or "").strip()
    if not raw:
        return ""
    _, netloc, key = _split_opaque_url(raw)
    if "://" in raw and not netloc:
        # Degenerate URLs (s3://, s3:///) are rejected by the caller; treat as
        # empty path if somehow reached.
        return ""
    if not key:
        return ""
    return key if key.endswith("/") else key + "/"


def _location_authority(location_url: str) -> tuple[str | None, str | None]:
    """Return ``(scheme, netloc)`` for a full LOCATION URL, else ``(None, None)``.

    Bare ``s3_prefix`` fallbacks have neither — callers skip the cross-bucket
    check. A non-empty URL with ``://`` but no netloc is invalid (see caller).
    """
    raw = (location_url or "").strip()
    if "://" not in raw:
        return None, None
    scheme, netloc, _ = _split_opaque_url(raw)
    return scheme, netloc


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
    - key not under LOCATION path, object bucket/scheme ≠ LOCATION, or PATTERN
      contains ``* ? [ #`` → raises ``TerminalValueError`` (never basename /
      silent truncation)
    """
    loc_raw = (location_url or "").strip()
    # Non-empty LOCATION URL that carries a scheme but no bucket is never valid
    # (s3://, s3:///). Reject up front so the cross-bucket guard cannot be
    # silently skipped. Empty loc_raw is the unset → s3_prefix fallback case.
    if loc_raw and "://" in loc_raw:
        loc_scheme, loc_bucket = _location_authority(loc_raw)
        if not loc_bucket:
            raise TerminalValueError(
                "Firebolt COPY PATTERN: s3_location_url / FIREBOLT_S3_LOCATION_URL "
                f"is not a valid LOCATION URL (missing bucket): {location_url!r}. "
                "Expected s3://bucket/ or s3://bucket/prefix/."
            )
    else:
        loc_scheme, loc_bucket = None, None

    file_scheme, file_bucket, key = _split_opaque_url(file_url)

    if loc_bucket is not None:
        if file_bucket and file_bucket != loc_bucket:
            raise TerminalValueError(
                "Firebolt COPY PATTERN: object bucket does not match LOCATION URL "
                f"bucket. LOCATION URL={location_url!r} (bucket={loc_bucket!r}), "
                f"object URL={file_url!r} (bucket={file_bucket!r}). "
                "Refusing to emit a PATTERN that could resolve against the wrong bucket."
            )
        if (
            loc_scheme
            and file_scheme
            and loc_scheme.casefold() != file_scheme.casefold()
        ):
            raise TerminalValueError(
                "Firebolt COPY PATTERN: object URL scheme does not match LOCATION "
                f"URL scheme. LOCATION URL={location_url!r} (scheme={loc_scheme!r}), "
                f"object URL={file_url!r} (scheme={file_scheme!r})."
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
    # Reject glob / fragment metacharacters in the resolved PATTERN. Silently
    # escaping would still leave an ambiguous intent; a wildcard matching a
    # sibling tenant prefix is a data-isolation bug. Opaque-key parsing ensures
    # '?' and '#' reach this guard instead of being truncated by urlparse.
    bad = sorted({ch for ch in pattern if ch in _PATTERN_FORBIDDEN})
    if bad:
        raise TerminalValueError(
            "Firebolt COPY PATTERN: resolved PATTERN contains forbidden characters "
            f"{bad} (glob metacharacters * ? [ or '#'). Refusing to emit a "
            f"wildcard / truncated PATTERN that could match another tenant's "
            f"objects. pattern={pattern!r}."
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
    # PATTERN was already checked for forbidden characters in s3_url_to_copy_pattern;
    # still escape quotes so a key segment with an apostrophe cannot break the literal.
    safe_pattern = _escape_sql_string_literal(pattern)
    return f"""COPY INTO {qualified_table_name}
FROM {location_name}
WITH (
  PATTERN = '{safe_pattern}',
  TYPE = PARQUET
)"""
