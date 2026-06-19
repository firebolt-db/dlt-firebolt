#!/usr/bin/env bash
# Hacker News top stories → Firebolt Core (upload mode). Blog example verification.
set -euo pipefail

export FIREBOLT_CORE_URL="${FIREBOLT_CORE_URL:-http://localhost:3473}"
export FIREBOLT_STAGING_MODE=upload
unset FIREBOLT_ACCOUNT_NAME 2>/dev/null || true

DATASET="${1:-hn_blog}"
LIMIT="${2:-30}"
VENV="${VENV:-$HOME/sprinto-connectors/.venv}"
REPO="${REPO:-$HOME/dlt-firebolt}"

echo "=== HN top stories → Core dataset=$DATASET limit=$LIMIT ==="
if [[ -n "${WHEEL_PATH:-}" ]]; then
  "$VENV/bin/pip" install -q "$WHEEL_PATH"
else
  "$VENV/bin/pip" install -e "$REPO" -q
fi

"$VENV/bin/python" - "$DATASET" "$LIMIT" <<'PY'
import sys

import dlt
import firebolt_dest  # noqa: F401
import requests
from firebolt_dest.configuration import make_firebolt_pipeline

dataset, limit = sys.argv[1], int(sys.argv[2])


@dlt.resource(name="hn_top_stories", write_disposition="merge", primary_key="id")
def hn_top_stories():
    ids = requests.get(
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        timeout=30,
    ).json()
    for story_id in ids[:limit]:
        item = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
            timeout=30,
        ).json()
        yield {
            k: item.get(k)
            for k in ("id", "title", "by", "score", "descendants", "url", "time")
        }


pipeline = make_firebolt_pipeline(
    pipeline_name="hackernews",
    dataset_name=dataset,
)
info = pipeline.run(hn_top_stories(), loader_file_format="parquet")
print(info)
assert not info.has_failed_jobs, info
print(f"OK: hn_top_stories loaded on Core ({limit} stories)")
PY
