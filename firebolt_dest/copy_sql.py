from __future__ import annotations

from urllib.parse import urlparse


def s3_url_to_copy_pattern(file_url: str, s3_prefix: str) -> str:
    """Return PATTERN relative to the Firebolt location URL prefix."""
    path = urlparse(file_url).path.lstrip("/")
    prefix = s3_prefix.strip("/") + "/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return path.split("/")[-1]


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
