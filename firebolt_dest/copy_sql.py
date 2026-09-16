from __future__ import annotations

import logging
from typing import Literal

from dlt.common.exceptions import TerminalValueError

# Child of the dlt logger so diagnostics inherit dlt's handler/level
# (plain __name__ loggers are silent when dlt's logger has propagate=False).
logger = logging.getLogger("dlt.firebolt_dest")

# Characters that must not appear in a resolved COPY PATTERN:
# - * ? [  — Firebolt/glob wildcards (tenant-isolation hazard)
# - #      — URL fragment delimiter; must stay literal key bytes, but we reject
#            it so a fragment-like suffix cannot be confused with a key segment
# - :      — SQLAlchemy bind-parameter marker inside sa.text(...) literals
# - \      — can become a wildcard under standard_conforming_strings=false
_GLOB_METACHARS = frozenset("*?[")
_PATTERN_FORBIDDEN = _GLOB_METACHARS | frozenset("#:\\")

LocationSource = Literal["s3_location_url", "s3_prefix"]


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


def resolve_copy_location(
    s3_location_url: str,
    s3_prefix: str,
) -> tuple[str, LocationSource]:
    """Normalize LOCATION settings once; return ``(location_url, provenance)``.

    - Whitespace-only / empty ``s3_location_url`` → classic ``s3_prefix`` fallback
      (``strip("/")`` so ``dlt-landing//`` matches main's behaviour).
    - Non-empty ``s3_location_url`` must be ``scheme://bucket[/...]``; scheme-less
      values like ``my-bucket/`` raise naming ``s3_location_url``.
    """
    raw = (s3_location_url or "").strip()
    if not raw:
        return (s3_prefix or "").strip().strip("/"), "s3_prefix"
    if "://" not in raw:
        raise TerminalValueError(
            f"Firebolt s3_location_url / FIREBOLT_S3_LOCATION_URL={s3_location_url!r} "
            "must be a full LOCATION URL with scheme and bucket "
            "(e.g. s3://bucket/ or s3://bucket/prefix/). "
            "Bare path prefixes belong in s3_prefix / S3_PREFIX."
        )
    _, bucket, _ = _split_opaque_url(raw)
    if not bucket:
        raise TerminalValueError(
            f"Firebolt s3_location_url / FIREBOLT_S3_LOCATION_URL={s3_location_url!r} "
            "is not a valid LOCATION URL (missing bucket). "
            "Expected s3://bucket/ or s3://bucket/prefix/."
        )
    return raw, "s3_location_url"


def _location_path_prefix(location_url: str) -> str:
    """Return the LOCATION URL path as an object-key prefix ('' = bucket root).

    ``location_url`` may be a full S3 URL (``s3://bucket/prefix/``) or a bare
    path/prefix (``prefix`` / ``prefix/``). A single trailing slash is
    normalized on when the path is non-empty. Does not strip interior or
    doubled slashes from the key of a full URL.
    """
    raw = (location_url or "").strip()
    if not raw:
        return ""
    _, netloc, key = _split_opaque_url(raw)
    if "://" in raw and not netloc:
        # Degenerate URLs (s3://, s3:///) are rejected by resolve_copy_location;
        # treat as empty path if somehow reached.
        return ""
    if not key:
        return ""
    return key if key.endswith("/") else key + "/"


def _location_authority(location_url: str) -> tuple[str | None, str | None]:
    """Return ``(scheme, netloc)`` for a full LOCATION URL, else ``(None, None)``."""
    raw = (location_url or "").strip()
    if "://" not in raw:
        return None, None
    scheme, netloc, _ = _split_opaque_url(raw)
    return scheme, netloc


def _mismatch_message(
    location_url: str,
    *,
    location_source: LocationSource,
    detail: str,
) -> str:
    """Name the setting the user actually configured."""
    if location_source == "s3_location_url":
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


def s3_url_to_copy_pattern(
    file_url: str,
    location_url: str = "",
    *,
    location_source: LocationSource = "s3_prefix",
) -> str:
    """Return COPY PATTERN: object key relative to the LOCATION URL path.

    PATTERN is anchored to the Firebolt LOCATION URL, not to the staging
    ``s3_prefix``. ``s3_prefix`` only affects where dlt writes objects.

    ``location_source`` records which setting supplied ``location_url`` so
    error messages name that setting (do not re-infer from ``://``).

    Examples (``key`` = object key from bucket root):

    - LOCATION ``s3://example-bucket/`` + key ``tenant-a/dlt/staging/foo.parquet``
      → ``tenant-a/dlt/staging/foo.parquet`` (multi-tenant / bucket-root LOCATION)
    - LOCATION ``s3://example-bucket/tenant-a/`` + key ``tenant-a/dlt/staging/foo.parquet``
      → ``dlt/staging/foo.parquet`` (classic single-tenant)
    - LOCATION ``s3://example-bucket/`` + key ``foo.parquet`` → ``foo.parquet``
    - key not under LOCATION path, object bucket/scheme ≠ LOCATION, or PATTERN
      contains ``* ? [ # : \\`` → raises ``TerminalValueError`` (never basename /
      silent truncation)
    """
    loc_raw = (location_url or "").strip()
    if location_source == "s3_location_url":
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
        if not file_bucket:
            raise TerminalValueError(
                "Firebolt COPY PATTERN: object URL has no bucket; cannot verify it "
                f"matches LOCATION URL bucket. LOCATION URL={location_url!r} "
                f"(bucket={loc_bucket!r}), object URL={file_url!r}. "
                "Refusing to emit a PATTERN that could resolve against the wrong bucket."
            )
        if file_bucket != loc_bucket:
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
                location_source=location_source,
                detail=f"path prefix {loc_path!r}, object key={key!r}.",
            )
        )

    pattern = key[len(loc_path) :] if loc_path else key
    # Reject glob / fragment / bind / escape metacharacters in the resolved
    # PATTERN. Silently escaping would still leave an ambiguous intent; a
    # wildcard matching a sibling tenant prefix is a data-isolation bug.
    # Opaque-key parsing ensures '?' and '#' reach this guard instead of being
    # truncated by urlparse.
    bad = sorted({ch for ch in pattern if ch in _PATTERN_FORBIDDEN})
    if bad:
        raise TerminalValueError(
            "Firebolt COPY PATTERN: resolved PATTERN contains forbidden characters "
            f"{bad} (glob metacharacters * ? [ , '#', ':', or '\\\\'). Refusing to "
            f"emit a wildcard / truncated / bind-parameter PATTERN that could match "
            f"another tenant's objects or alter SQL. pattern={pattern!r}."
        )

    logger.debug(
        "Firebolt COPY PATTERN: file_url=%s location_url=%s location_source=%s "
        "loc_path=%s pattern=%s",
        file_url,
        location_url,
        location_source,
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
