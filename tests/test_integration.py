"""Optional live integration tests (Firebolt + S3).

Run with:
  export FIREBOLT_RUN_INTEGRATION=1
  export AWS_PROFILE=sandbox
  pytest -m integration -v
"""

from __future__ import annotations

import os
from typing import Iterator

import dlt
import pytest
from dotenv import load_dotenv

from firebolt_dest.configuration import make_firebolt_pipeline

load_dotenv()

pytestmark = pytest.mark.skipif(
    os.environ.get("FIREBOLT_RUN_INTEGRATION", "").lower() not in ("1", "true", "yes"),
    reason="Set FIREBOLT_RUN_INTEGRATION=1 to run live Firebolt tests",
)


@dlt.resource(
    name="integration_probe",
    write_disposition="merge",
    primary_key="id",
)
def integration_probe() -> Iterator[dict]:
    yield {"id": 42, "label": "integration-probe"}


@pytest.mark.integration
def test_merge_load_e2e() -> None:
    dataset = os.environ.get("DLT_DATASET_NAME", "demo")
    pipeline = make_firebolt_pipeline(
        pipeline_name="firebolt_integration_test",
        dataset_name=dataset,
    )
    info = pipeline.run(integration_probe(), loader_file_format="parquet")
    assert info.has_failed_jobs is False
