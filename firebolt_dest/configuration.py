from __future__ import annotations

import dataclasses
import os
import tempfile
import urllib.parse
from pathlib import Path
from typing import ClassVar, Final, Literal

from dlt.common.configuration import configspec
from dlt.common.configuration.specs import ConnectionStringCredentials
from dlt.common.destination.client import DestinationClientDwhWithStagingConfiguration
from dlt.common.utils import digest128


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@configspec(init=False)
class FireboltCredentials(ConnectionStringCredentials):
    drivername: Final[str] = dataclasses.field(
        default="firebolt", init=False, repr=False, compare=False
    )
    database: str = None
    host: str = None  # Firebolt database name in the connection URL
    account_name: str = None

    __query_params__: ClassVar[list[str]] = ["account_name"]

    def is_core_connection(self) -> bool:
        return bool(self.query and "url" in self.query)

    def parse_native_representation(self, native_value: object) -> None:
        super().parse_native_representation(native_value)
        if self.is_core_connection():
            # firebolt://{database}?url=... (Firebolt Core; no service account)
            core_db = self.host or "firebolt"
            self.database = core_db
            self.host = core_db
            self.account_name = self.account_name or "core"
        elif "account_name" in (self.query or {}):
            self.account_name = self.query.get("account_name")

    def on_resolved(self) -> None:
        super().on_resolved()
        if self.is_core_connection():
            self.account_name = self.account_name or "core"
            return
        if self.account_name and "account_name" not in (self.query or {}):
            self.query = dict(self.query or {})
            self.query["account_name"] = self.account_name

    def to_native_representation(self) -> str:
        if self.is_core_connection():
            db = self.database or self.host or "firebolt"
            url = self.query["url"]
            return f"firebolt://{db}?url={url}"
        return super().to_native_representation()


@configspec
class FireboltClientConfiguration(DestinationClientDwhWithStagingConfiguration):
    destination_type: Final[str] = dataclasses.field(
        default="firebolt", init=False, repr=False, compare=False
    )
    credentials: FireboltCredentials = None
    staging_mode: Literal["upload", "s3"] = "upload"
    """upload: HTTP multipart upload (no S3). s3: Parquet on S3 + COPY INTO."""
    use_core: bool = False
    """When True, target local Firebolt Core instead of managed service."""
    core_url: str = "http://localhost:3473"
    """Firebolt Core HTTP endpoint when use_core is True."""
    s3_location_name: str = "firebolt_s3"
    """Firebolt external location name (CREATE LOCATION ...). Required for s3 mode."""
    s3_prefix: str = "dlt-landing"
    """Object key prefix inside the location URL, used to build COPY PATTERN."""

    def fingerprint(self) -> str:
        if self.credentials and self.credentials.database:
            return digest128(self.credentials.database)
        return ""


def firebolt_url_from_env() -> str:
    client_id = _require_env("FIREBOLT_CLIENT_ID")
    secret = urllib.parse.quote_plus(_require_env("FIREBOLT_CLIENT_SECRET"))
    database = _require_env("FIREBOLT_DATABASE")
    engine = _require_env("FIREBOLT_ENGINE")
    account = _require_env("FIREBOLT_ACCOUNT_NAME")
    return (
        f"firebolt://{client_id}:{secret}@{database}/{engine}"
        f"?account_name={account}"
    )


def firebolt_core_credentials() -> FireboltCredentials:
    """Structured credentials for Firebolt Core (passes dlt config resolution)."""
    database = os.environ.get("FIREBOLT_CORE_DATABASE", "firebolt").strip()
    creds = FireboltCredentials(
        {
            "host": database,
            "database": database,
            "account_name": "core",
            "query": {"url": core_url_from_env()},
        }
    )
    creds.on_resolved()
    return creds


def firebolt_core_url_from_env() -> str:
    """SQLAlchemy URL for Firebolt Core (no service account)."""
    return firebolt_core_credentials().to_native_representation()


def s3_location_name_from_env() -> str:
    return os.environ.get("FIREBOLT_S3_LOCATION_NAME", "firebolt_s3").strip()


def s3_prefix_from_env() -> str:
    return os.environ.get("S3_PREFIX", "dlt-landing").strip().strip("/")


def s3_bucket_from_env() -> str:
    return _require_env("S3_BUCKET").strip()


def staging_mode_from_env() -> Literal["upload", "s3"]:
    mode = os.environ.get("FIREBOLT_STAGING_MODE", "upload").strip().lower()
    if mode not in ("upload", "s3"):
        raise RuntimeError(
            f"Invalid FIREBOLT_STAGING_MODE={mode!r}. Expected 'upload' or 's3'."
        )
    return mode  # type: ignore[return-value]


def use_core_from_env() -> bool:
    return os.environ.get("FIREBOLT_USE_CORE", "").strip().lower() in ("1", "true", "yes")


def core_url_from_env() -> str:
    return os.environ.get("FIREBOLT_CORE_URL", "http://localhost:3473").strip()


def local_staging_bucket_url() -> str:
    base = os.environ.get(
        "DLT_LOCAL_STAGING_DIR",
        str(Path(tempfile.gettempdir()) / "dlt-firebolt-staging"),
    )
    Path(base).mkdir(parents=True, exist_ok=True)
    return f"file://{base}"


def staging_bucket_url() -> str:
    return f"s3://{s3_bucket_from_env()}/{s3_prefix_from_env()}/dlt/staging"


def resolve_staging_bucket_url(staging_mode: Literal["upload", "s3"]) -> str:
    if staging_mode == "upload":
        return local_staging_bucket_url()
    return staging_bucket_url()


def register_firebolt_destination() -> None:
    """Ensure destination=\"firebolt\" is registered with dlt."""
    import firebolt_dest  # noqa: F401


def make_firebolt_pipeline(
    pipeline_name: str,
    dataset_name: str,
    *,
    from_secrets: bool = False,
    staging_mode: Literal["upload", "s3"] | None = None,
    **kwargs: object,
):
    """Build a dlt pipeline with Firebolt destination + filesystem staging."""
    import dlt

    register_firebolt_destination()
    mode = staging_mode or staging_mode_from_env()
    use_core = use_core_from_env()
    if from_secrets:
        return dlt.pipeline(
            pipeline_name=pipeline_name,
            destination="firebolt",
            staging="filesystem",
            dataset_name=dataset_name,
            **kwargs,
        )
    from firebolt_dest.factory import firebolt

    credentials = (
        firebolt_core_credentials() if use_core else firebolt_url_from_env()
    )
    dest_kwargs: dict[str, object] = {
        "credentials": credentials,
        "staging_mode": mode,
        "s3_prefix": s3_prefix_from_env(),
        "use_core": use_core,
        "core_url": core_url_from_env(),
    }
    if mode == "s3":
        dest_kwargs["s3_location_name"] = s3_location_name_from_env()

    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination=firebolt(**dest_kwargs),
        staging=dlt.destinations.filesystem(bucket_url=resolve_staging_bucket_url(mode)),
        dataset_name=dataset_name,
        **kwargs,
    )
