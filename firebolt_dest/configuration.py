from __future__ import annotations

import dataclasses
import os
import urllib.parse
from typing import ClassVar, Final

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
    host: str = None  # engine name in the URL path
    account_name: str = None

    __query_params__: ClassVar[list[str]] = ["account_name"]

    def parse_native_representation(self, native_value: object) -> None:
        super().parse_native_representation(native_value)
        if "account_name" in self.query:
            self.account_name = self.query.get("account_name")

    def on_resolved(self) -> None:
        super().on_resolved()
        if self.account_name and "account_name" not in (self.query or {}):
            self.query = dict(self.query or {})
            self.query["account_name"] = self.account_name


@configspec
class FireboltClientConfiguration(DestinationClientDwhWithStagingConfiguration):
    destination_type: Final[str] = dataclasses.field(
        default="firebolt", init=False, repr=False, compare=False
    )
    credentials: FireboltCredentials = None
    s3_location_name: str = "firebolt_s3"
    """Firebolt external location name (CREATE LOCATION ...)."""
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


def s3_location_name_from_env() -> str:
    return os.environ.get("FIREBOLT_S3_LOCATION_NAME", "firebolt_s3").strip()


def s3_prefix_from_env() -> str:
    return os.environ.get("S3_PREFIX", "dlt-landing").strip().strip("/")


def s3_bucket_from_env() -> str:
    return _require_env("S3_BUCKET").strip()


def staging_bucket_url() -> str:
    return f"s3://{s3_bucket_from_env()}/{s3_prefix_from_env()}/dlt/staging"


def register_firebolt_destination() -> None:
    """Ensure destination=\"firebolt\" is registered with dlt."""
    import firebolt_dest  # noqa: F401


def make_firebolt_pipeline(
    pipeline_name: str,
    dataset_name: str,
    *,
    from_secrets: bool = False,
    **kwargs: object,
):
    """Build a dlt pipeline with Firebolt destination + filesystem staging."""
    import dlt

    register_firebolt_destination()
    if from_secrets:
        return dlt.pipeline(
            pipeline_name=pipeline_name,
            destination="firebolt",
            staging="filesystem",
            dataset_name=dataset_name,
            **kwargs,
        )
    from firebolt_dest.factory import firebolt

    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination=firebolt(
            credentials=firebolt_url_from_env(),
            s3_location_name=s3_location_name_from_env(),
            s3_prefix=s3_prefix_from_env(),
        ),
        staging=dlt.destinations.filesystem(bucket_url=staging_bucket_url()),
        dataset_name=dataset_name,
        **kwargs,
    )
