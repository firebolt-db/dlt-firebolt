#!/usr/bin/env bash
# Core e2e: upload mode, no S3. Run on your machine with Core Docker up on :3473.
set -euo pipefail

export FIREBOLT_USE_CORE=1
export FIREBOLT_STAGING_MODE=upload
export FIREBOLT_CORE_URL="${FIREBOLT_CORE_URL:-http://localhost:3473}"
export FIREBOLT_CORE_DATABASE="${FIREBOLT_CORE_DATABASE:-firebolt}"

DATASET="${1:-core_e2e}"
VENV="${VENV:-$HOME/sprinto-connectors/.venv}"
REPO="${REPO:-$HOME/dlt-firebolt}"

echo "=== Core e2e dataset=$DATASET upload mode, no S3 ==="
if [[ -n "${WHEEL_PATH:-}" ]]; then
  "$VENV/bin/pip" install -q "$WHEEL_PATH"
else
  "$VENV/bin/pip" install -e "$REPO" -q
fi

run_load() {
  local mode="$1" version="$2"
  echo ""
  echo "--- $mode $version ---"
  "$VENV/bin/python" - "$mode" "$version" "$DATASET" <<'PY'
import sys
import dlt
import firebolt_dest
from firebolt_dest.configuration import make_firebolt_pipeline

mode, version, dataset = sys.argv[1], sys.argv[2], sys.argv[3]

def contact_rows():
    acme_status = "churned" if version == "v2" else "active"
    return [
        {"id": 1, "name": "Acme", "plan": "enterprise", "status": acme_status},
        {"id": 2, "name": "Beta", "plan": "pro", "status": "active"},
        {"id": 3, "name": "Gamma", "plan": "pro", "status": "churned"},
    ]

def order_rows():
    acme_qty = 9 if version == "v2" else 2
    return [
        {
            "order_id": 1,
            "customer": "Acme",
            "items": [
                {"sku": "A1", "qty": acme_qty, "price": 50},
                {"sku": "A2", "qty": 1, "price": 30},
            ],
        },
        {
            "order_id": 2,
            "customer": "Beta",
            "items": [{"sku": "B1", "qty": 5, "price": 12}],
        },
    ]

@dlt.resource(name="contacts", write_disposition=mode, primary_key="id")
def contacts():
    yield contact_rows()

@dlt.resource(name="orders", write_disposition=mode, primary_key="order_id")
def orders():
    yield order_rows()

pipeline = make_firebolt_pipeline(
    pipeline_name=f"core_e2e_{dataset}",
    dataset_name=dataset,
)
info = pipeline.run([contacts(), orders()], loader_file_format="parquet")
print(info)
if info.has_failed_jobs:
    raise SystemExit("FAILED JOBS")
print("OK: LOADED with no failed jobs")
PY
}

# Merge-only: do not run append first on the same dataset (schema switch breaks on Core).
run_load merge v1
run_load merge v2

echo ""
echo "=== Spot-check SQL (paste output back) ==="
"$VENV/bin/python" - "$DATASET" <<'PY'
import sys
from firebolt.client.auth import FireboltCore
from firebolt.db import connect

dataset = sys.argv[1]
prefix = f"{dataset}_"

with connect(
    auth=FireboltCore(),
    database="firebolt",
    url="http://localhost:3473",
) as conn:
    cur = conn.cursor()
    for table in ("contacts", "orders", "orders__items"):
        t = prefix + table
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        print(f"{t} count:", cur.fetchone()[0])
    cur.execute(
        f'SELECT id, status FROM "{prefix}contacts" WHERE id = 1'
    )
    print("Acme status (expect churned after v2):", cur.fetchone())
    cur.execute(
        f'''SELECT o.order_id, i.sku, i.qty FROM "{prefix}orders" o
            JOIN "{prefix}orders__items" i ON i._dlt_root_id = o._dlt_id
            WHERE o.order_id = 1 AND i.sku = 'A1' '''
    )
    print("Acme A1 qty (expect 9 after v2):", cur.fetchone())
PY

echo ""
echo "Done. Paste full output for blog sign-off."
