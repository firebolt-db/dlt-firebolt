#!/usr/bin/env python3
"""Validate Firebolt + S3 credentials and staging setup."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from firebolt_dest.configuration import (
    firebolt_url_from_env,
    s3_location_name_from_env,
    staging_bucket_url,
)

load_dotenv(ROOT / ".env")

REQUIRED = (
    "FIREBOLT_CLIENT_ID",
    "FIREBOLT_CLIENT_SECRET",
    "FIREBOLT_ACCOUNT_NAME",
    "FIREBOLT_DATABASE",
    "FIREBOLT_ENGINE",
    "S3_BUCKET",
)


def _mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}...{value[-2:]}"


def main() -> int:
    print("Firebolt / S3 environment check\n")

    missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        print("Missing required variables:")
        for name in missing:
            print(f"  - {name}")
        return 1

    for name in REQUIRED:
        print(f"  {name} = {_mask(os.environ[name])}")

    print(f"  FIREBOLT_S3_LOCATION_NAME = {s3_location_name_from_env()}")
    print(f"  S3_PREFIX = {os.environ.get('S3_PREFIX', 'dlt-landing')}")
    print(f"  staging bucket_url = {staging_bucket_url()}")
    print()

    url = firebolt_url_from_env()
    print("Testing Firebolt OAuth + SQL connection...")
    try:
        engine = sa.create_engine(url)
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        print("  OK: Firebolt credentials accepted.")
    except Exception as exc:
        print("  FAIL: Firebolt authentication or connection failed.")
        print(f"  {type(exc).__name__}: {exc}")
        print()
        print("Fix:")
        print("  1. Firebolt console → Settings → Service accounts")
        print("  2. Create a new service account or rotate the secret")
        print("  3. Update FIREBOLT_CLIENT_ID and FIREBOLT_CLIENT_SECRET in .env")
        print("  4. Confirm FIREBOLT_ACCOUNT_NAME, FIREBOLT_DATABASE, FIREBOLT_ENGINE")
        return 2

    location_name = s3_location_name_from_env()
    print(f"Testing Firebolt external location '{location_name}'...")
    try:
        engine = sa.create_engine(url)
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.locations "
                    "WHERE location_name = :name"
                ),
                {"name": location_name},
            ).fetchall()
        if not rows:
            print(f"  FAIL: Location '{location_name}' not found in this database.")
            print()
            print("Fix:")
            print("  1. Run CREATE LOCATION in Firebolt for your S3 bucket")
            print("  2. Set FIREBOLT_S3_LOCATION_NAME to that exact location name")
            return 4
        print(f"  OK: Location '{location_name}' exists.")
    except Exception as exc:
        print(f"  WARN: Could not verify location ({type(exc).__name__}: {exc})")

    print()
    print("Testing S3 staging access...")
    try:
        import fsspec

        fs, _ = fsspec.core.url_to_fs(staging_bucket_url())
        fs.ls(fs._strip_protocol(staging_bucket_url()), detail=False)
        print("  OK: S3 staging bucket reachable.")
    except Exception as exc:
        print("  FAIL: S3 staging not reachable with current AWS credentials.")
        print(f"  {type(exc).__name__}: {exc}")
        print()
        print("Fix:")
        print("  export AWS_PROFILE=sandbox")
        print("  aws sso login --profile sandbox")
        return 3

    print()
    print("All checks passed. You can run phase3/phase4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
