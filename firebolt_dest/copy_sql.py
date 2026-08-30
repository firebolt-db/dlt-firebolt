from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


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


def s3_url_to_copy_pattern(file_url: str, location_url: str = "") -> str:
    """Return COPY PATTERN: object key relative to the LOCATION URL path.

    PATTERN is anchored to the Firebolt LOCATION URL, not to the staging
    ``s3_prefix``. ``s3_prefix`` only affects where dlt writes objects.

    Examples (``key`` = object key from bucket root):

    - LOCATION ``s3://bucket/`` + key ``colpal/dlt/staging/foo.parquet``
      → ``colpal/dlt/staging/foo.parquet`` (multi-tenant / FieldAssist)
    - LOCATION ``s3://bucket/colpal/`` + key ``colpal/dlt/staging/foo.parquet``
      → ``dlt/staging/foo.parquet`` (classic single-tenant)
    - LOCATION ``s3://bucket/`` + key ``foo.parquet`` → ``foo.parquet``
    - key not under LOCATION path → raises ``ValueError`` (never basename)
    """
    key = urlparse(file_url).path.lstrip("/")
    loc_path = _location_path_prefix(location_url)

    if loc_path and not key.startswith(loc_path):
        raise ValueError(
            "Firebolt COPY PATTERN: object key is not under the LOCATION URL path. "
            f"LOCATION URL={location_url!r} (path prefix {loc_path!r}), "
            f"object key={key!r}. Refusing basename fallback."
        )

    pattern = key[len(loc_path) :] if loc_path else key
    logger.info(
        "Firebolt COPY PATTERN: file_url=%s location_url=%s loc_path=%s pattern=%s",
        file_url,
        location_url,
        loc_path or "(bucket-root)",
        pattern,
    )
    return pattern


def gen_firebolt_copy_sql(
    qualified_table_name: str,
    *,
    location_name: str,
    pattern: str,
    file_format: str,
) -> str:
    if file_format != "parquet":
        raise ValueError(f"Firebolt prototype only supports parquet, got {file_format!r}")
    return f"""COPY INTO {qualified_table_name}
FROM {location_name}
WITH (
  PATTERN = '{pattern}',
  TYPE = PARQUET
)"""
