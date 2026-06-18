#!/usr/bin/env bash
# Verify GitHub stargazers → Firebolt Core (upload mode) for blog example.
set -euo pipefail

export FIREBOLT_USE_CORE=1
export FIREBOLT_STAGING_MODE=upload
export FIREBOLT_CORE_URL="${FIREBOLT_CORE_URL:-http://localhost:3473}"
export FIREBOLT_CORE_DATABASE="${FIREBOLT_CORE_DATABASE:-firebolt}"

DATASET="${1:-oss_analytics_blog}"
MAX_PAGES="${2:-1}"
VENV="${VENV:-$HOME/sprinto-connectors/.venv}"
REPO="${REPO:-$HOME/dlt-firebolt}"

echo "=== GitHub stargazers → Core (upload) dataset=$DATASET max_pages=$MAX_PAGES ==="
if [[ -n "${WHEEL_PATH:-}" ]]; then
  "$VENV/bin/pip" install -q "$WHEEL_PATH"
else
  "$VENV/bin/pip" install -e "$REPO" -q
fi

"$VENV/bin/python" - "$DATASET" "$MAX_PAGES" <<'PY'
import sys

import dlt
import firebolt_dest  # noqa: F401
import requests
from firebolt_dest.configuration import make_firebolt_pipeline

dataset, max_pages = sys.argv[1], int(sys.argv[2])
GITHUB_REPO = "dlt-hub/dlt"


@dlt.resource(
    name="github_stars",
    write_disposition="merge",
    primary_key="user_login",
)
def github_stars():
    for page in range(1, max_pages + 1):
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/stargazers",
            headers={"Accept": "application/vnd.github.v3.star+json"},
            params={"page": page, "per_page": 100},
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            break
        for row in rows:
            yield {
                "user_login": row["user"]["login"],
                "starred_at": row["starred_at"],
            }


pipeline = make_firebolt_pipeline(
    pipeline_name="github_to_firebolt",
    dataset_name=dataset,
)
info = pipeline.run(github_stars(), loader_file_format="parquet")
print(info)
assert not info.has_failed_jobs, info
print("OK: github_stars loaded on Core via upload mode")
PY
