from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Tuple

import requests
from firebolt.client.auth import ClientCredentials
from firebolt.db import connect

from firebolt_dest.configuration import FireboltCredentials

_PART_NAME_RE = re.compile(r"^[_0-9a-zA-Z.-]+$")
_MAX_PART_NAME_LEN = 64


def sanitize_upload_part_name(raw: str) -> str:
    """Return a part name valid for Firebolt upload:// references."""
    name = re.sub(r"[^_0-9a-zA-Z.-]", "_", raw).strip("._")
    if not name:
        name = "dlt_file"
    return name[:_MAX_PART_NAME_LEN]


def resolve_local_parquet_path(remote_ref: str) -> Path:
    """Resolve a dlt staging reference to a local Parquet file path."""
    if remote_ref.startswith("s3://"):
        raise ValueError(
            "upload staging mode received an s3:// reference. "
            "Set FIREBOLT_STAGING_MODE=s3 or use local file staging."
        )
    if remote_ref.startswith("file://"):
        path = urllib.parse.unquote(urllib.parse.urlparse(remote_ref).path)
        return Path(path)
    return Path(remote_ref)


def gen_upload_insert_sql(qualified_table_name: str, part_name: str) -> str:
    if not _PART_NAME_RE.match(part_name):
        raise ValueError(f"Invalid upload part name: {part_name!r}")
    return (
        f"INSERT INTO {qualified_table_name} "
        f"SELECT * FROM READ_PARQUET('upload://{part_name}')"
    )


def _engine_url_with_database(engine_url: str, database: str) -> str:
    separator = "&" if "?" in engine_url else "?"
    return f"{engine_url.rstrip('/')}{separator}database={urllib.parse.quote(database)}"


def _resolve_managed_user_engine_url(
    credentials: FireboltCredentials,
) -> Tuple[str, str, str]:
    auth = ClientCredentials(
        credentials.username,
        credentials.password,
        use_token_cache=False,
    )
    with connect(
        auth=auth,
        account_name=credentials.account_name,
        database=credentials.host,
        engine_name=credentials.database,
    ) as conn:
        token = auth.token
        if not token:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            token = auth.token
        if not token:
            raise RuntimeError("Failed to obtain Firebolt access token for upload.")

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT url FROM information_schema.engines "
                "WHERE engine_name = %s LIMIT 1",
                (credentials.database,),
            )
            row = cursor.fetchone()
        if not row or not row[0]:
            raise RuntimeError(
                f"Could not resolve HTTP endpoint for engine {credentials.database!r}."
            )
        raw_url = str(row[0]).strip()
        if not raw_url.startswith("http"):
            raw_url = f"https://{raw_url.lstrip('/')}"
        return raw_url, credentials.host, token


def _resolve_core_engine_url(core_url: str | None, database: str) -> Tuple[str, str, str]:
    url = (core_url or "http://localhost:3473").strip()
    if not url.startswith("http"):
        url = f"http://{url}"
    return url, database or "firebolt", ""


def resolve_engine_endpoint(
    credentials: FireboltCredentials,
    *,
    core_url: str | None = None,
    use_core: bool = False,
) -> Tuple[str, str, str]:
    """Return user engine URL, database name, and bearer token for HTTP upload."""
    if use_core:
        return _resolve_core_engine_url(core_url, credentials.host or "firebolt")

    if not credentials.username or not credentials.password:
        raise RuntimeError("Firebolt credentials require client id and secret.")
    if not credentials.account_name:
        raise RuntimeError("Firebolt credentials require account_name.")
    if not credentials.host or not credentials.database:
        raise RuntimeError("Firebolt credentials require database and engine.")

    return _resolve_managed_user_engine_url(credentials)


def upload_parquet_insert(
    *,
    engine_url: str,
    database: str,
    token: str,
    sql: str,
    part_name: str,
    file_path: Path,
    timeout_seconds: int = 600,
) -> None:
    """POST multipart upload request to Firebolt user engine."""
    url = _engine_url_with_database(engine_url, database)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with file_path.open("rb") as handle:
        response = requests.post(
            url,
            headers=headers,
            files={
                "sql": (None, sql),
                part_name: (file_path.name, handle, "application/octet-stream"),
            },
            timeout=timeout_seconds,
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Firebolt upload failed ({response.status_code}): {response.text.strip()}"
        )
