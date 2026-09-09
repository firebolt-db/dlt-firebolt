# dlt-firebolt

Community [dlt](https://dlthub.com/) destination for [Firebolt](https://www.firebolt.io/).

Load data into Firebolt with dlt using **direct HTTP upload (default)** or **S3 staging + `COPY INTO`** for large loads.

**Requires [dlt-firebolt 0.3.0+](https://pypi.org/project/dlt-firebolt/0.3.0/)** for upload mode and simplified Core/managed configuration.

## Two ways to load

| Mode | Best for | Firebolt load path |
|------|----------|-------------------|
| **`upload` (default)** | Firebolt Core, local dev, quick starts | HTTP multipart → `READ_PARQUET('upload://…')` |
| **`s3`** | **Managed Firebolt production**, large bulk loads | Parquet on S3 → `COPY INTO` |

On **managed Firebolt** today, set `FIREBOLT_STAGING_MODE=s3`. Upload is the code default but the managed engine does not accept multipart upload yet; you will get a clear error if you use upload mode there.

## Install

```bash
pip install "dlt-firebolt>=0.3.0"
```

Requires Python 3.10+.

Register the destination once in your project:

```python
import firebolt_dest  # registers destination="firebolt"
```

## Prerequisites

### Upload mode (Core / local)

1. **Firebolt Core** running locally (or another environment that supports `upload://`), **or** a managed account once upload is supported there.

No S3 bucket, external location, or AWS credentials required for the Firebolt load step. dlt still writes Parquet to a local staging directory during normalize.

### S3 mode (managed production)

1. **Firebolt service account** with access to your database and engine.
2. **S3 bucket** for dlt filesystem staging.
3. **Firebolt external location** for that bucket prefix:

```sql
CREATE LOCATION "your_location_name" WITH
  SOURCE = 'CLOUD_STORAGE'
  URL = 's3://your-bucket/your-prefix/'
  CREDENTIALS = (AWS_ROLE_ARN = 'arn:aws:iam::...:role/...');
```

Set `FIREBOLT_S3_LOCATION_NAME` (or `s3_location_name` in secrets) to the exact location name from `CREATE LOCATION`. Set `FIREBOLT_STAGING_MODE=s3`.

The machine running dlt needs AWS credentials that can write to the staging bucket (via environment variables, an AWS profile, or an attached IAM role). Firebolt reads the staged files from the external location you configured, not the runner's AWS identity. Staging Parquet is not automatically deleted after `COPY INTO`, so add an S3 lifecycle rule or a periodic cleanup if you don't want objects to accumulate.

## Quick start

### Firebolt Core (upload, no S3)

```bash
export FIREBOLT_CORE_URL=http://localhost:3473
```

```python
import dlt
import firebolt_dest
from firebolt_dest.configuration import make_firebolt_pipeline

@dlt.resource(name="orders", write_disposition="append")
def orders():
    yield {"order_id": 1, "customer": "Acme"}

pipeline = make_firebolt_pipeline(
    pipeline_name="my_pipeline",
    dataset_name="my_dataset",
)

pipeline.run(orders(), loader_file_format="parquet")
```

### Managed Firebolt (S3)

Set service-account credentials and `FIREBOLT_STAGING_MODE=s3` (see [Configuration](#configuration)). The same pipeline code applies; only env vars change.

Tables are created as `{dataset}_{table}` in the `public` schema (for example `my_dataset_orders`). To use a real Firebolt schema instead (`my_dataset.orders`), set `FIREBOLT_USE_SCHEMA_PER_DATASET=true` — see [Configuration](#configuration).

### Using `.dlt/secrets.toml`

Environment variables are the primary path used in the e2e scripts. You can also load configuration from `.dlt/secrets.toml` with `from_secrets=True` (verified on Firebolt Core with upload mode; see `.dlt/secrets.toml.example`).

**Note:** In dlt's credential block, `host` is the Firebolt **database** name and `database` is the Firebolt **engine** name (matching `FIREBOLT_DATABASE` and `FIREBOLT_ENGINE`, not swapped).

```python
pipeline = make_firebolt_pipeline(
    pipeline_name="my_pipeline",
    dataset_name="my_dataset",
    from_secrets=True,
)
```

Example for managed Firebolt (S3 mode):

```toml
[destination.firebolt]
staging_mode = "s3"
s3_location_name = "your_location_name"
s3_prefix = "dlt-landing"
# use_schema_per_dataset = false  # opt-in real schemas (FB-3446); default off

[destination.firebolt.credentials]
host = "YOUR_FIREBOLT_DATABASE"
database = "YOUR_FIREBOLT_ENGINE"
username = "YOUR_CLIENT_ID"
password = "YOUR_CLIENT_SECRET"
account_name = "YOUR_ACCOUNT_NAME"

[destination.filesystem]
bucket_url = "s3://your-bucket/dlt-landing/dlt/staging"
```

See `.dlt/secrets.toml.example` for a Firebolt Core upload template.

With `from_secrets=True` (or a plain `destination="firebolt"` pipeline), set the flag in TOML as `use_schema_per_dataset = true` under `[destination.firebolt]`, or via the dlt env alias `DESTINATION__FIREBOLT__USE_SCHEMA_PER_DATASET=true`. `FIREBOLT_USE_SCHEMA_PER_DATASET` is read only when `make_firebolt_pipeline(..., from_secrets=False)` builds the destination from env.

## Configuration

### Managed Firebolt

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREBOLT_CLIENT_ID` | yes | Service account client ID |
| `FIREBOLT_CLIENT_SECRET` | yes | Service account secret |
| `FIREBOLT_ACCOUNT_NAME` | yes | Firebolt account name |
| `FIREBOLT_DATABASE` | yes | Target database |
| `FIREBOLT_ENGINE` | yes | Engine name |
| `FIREBOLT_STAGING_MODE` | no | `s3` for managed production (recommended) |
| `FIREBOLT_S3_LOCATION_NAME` | s3 mode | Firebolt external location name |
| `S3_BUCKET` | s3 mode | Staging bucket |
| `S3_PREFIX` | no | Key prefix (default: `dlt-landing`) |
| `FIREBOLT_USE_SCHEMA_PER_DATASET` | no | `true` to map `dataset_name` to a real Firebolt schema (default: off — tables stay `public.{dataset}_{table}`) |

The destination resolves the engine URL from your account; you do not set an HTTP endpoint manually.

#### Schema-per-dataset (opt-in, FB-3446)

**Default is off.** Existing pipelines keep writing `public.{dataset}_{table}` and store dlt state tables (`_dlt_loads`, `_dlt_pipeline_state`, `_dlt_version`) under that public-prefix naming. Enabling the flag is a **deliberate breaking change** for that layout:

| | Flag off (default) | Flag on |
|--|--------------------|---------|
| Table name | `public.tenant_a_orders` | `tenant_a.orders` |
| Staging | `public.tenant_a_staging_*` | schema `tenant_a_staging` |
| dlt state | `public.{dataset}__dlt_*` | `{dataset}._dlt_*` |

**dlt state freshness depends on whether the dataset schema already exists** when the pipeline first runs with the flag on (`has_dataset()` checks `information_schema.schemata`):

- If the schema does **not** exist yet, the first run creates it and dlt state under that schema starts **fresh** (nothing is copied from `public.{dataset}__dlt_*`).
- If you **pre-create** the schema (for example `CREATE SCHEMA IF NOT EXISTS …` before CLONE/CTAS), `has_dataset()` is already true, so existing destination state tables in that schema are **retained** — not reset.

Do **not** set `dataset_name="public"` with the flag on. Remote wipe via `pipeline.destination_client().drop_storage()` (or `drop_dataset()`) emits `DROP SCHEMA "public" CASCADE`, which removes the shared public schema. Prefer a dedicated dataset/schema name such as `tenant_a` or `demo`.

**Replace disposition:** in schema mode, truncate/replace uses `DELETE … WHERE 1=1` (not `TRUNCATE`) on **both** Core and managed, so older Core builds that silently no-op schema-qualified `TRUNCATE` stay correct. The destination role therefore needs `DELETE` privilege, and full-table deletes create delete logs.

Firebolt does **not** support `ALTER TABLE … SET SCHEMA`, and `ALTER TABLE … RENAME TO` cannot rename across schemas. To bring **existing data** from the old public-prefix layout into the new schema, Firebolt’s recommended path is a **zero-copy** [`CREATE TABLE … CLONE`](https://docs.firebolt.io/reference-sql/commands/data-definition/create-table-clone) (metadata-level; near-instant; no extra storage), then drop the old table:

```sql
-- Pre-creating the schema retains destination state if state tables already
-- exist there; omit this and let the pipeline create the schema if you want
-- fresh dlt state on first flag-ON run.
CREATE SCHEMA IF NOT EXISTS tenant_a;
CREATE TABLE tenant_a.orders CLONE public.tenant_a_orders;
-- verify row counts / spot-check, then:
DROP TABLE public.tenant_a_orders;
```

Repeat per table you want to keep. External tables cannot be cloned — recreate them in the target schema. **Firebolt Core does not support `CLONE`** (verified on Core 5.0.1); on Core use CTAS instead:

```sql
CREATE TABLE tenant_a.orders AS SELECT * FROM public.tenant_a_orders;
DROP TABLE public.tenant_a_orders;
```

If you migrate only data tables and want a clean incremental cursor, drop any `{dataset}._dlt_*` state tables in the new schema (or avoid pre-creating the schema) before the first flag-ON run.

### Firebolt Core

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREBOLT_CORE_URL` | yes | Core HTTP endpoint (selects Core when set) |
| `FIREBOLT_CORE_DATABASE` | no | Database name (default: `firebolt`) |
| `FIREBOLT_STAGING_MODE` | no | `upload` (default) |

| Variable | Description |
|----------|-------------|
| `DLT_LOCAL_STAGING_DIR` | Local path for upload-mode normalize staging |
| `DLT_DATASET_NAME` | Default dataset name (default: `demo`) |

Set credentials via environment variables or `.dlt/secrets.toml`. Do not commit secrets.

## Supported capabilities

| Feature | Support |
|---------|---------|
| Loader format | Parquet only |
| Staging | `upload` (HTTP, default) or `s3` (COPY INTO) |
| `append` | Yes |
| `replace` | `truncate-and-insert`, `insert-from-staging` |
| `merge` | `delete-insert` (single-table and nested) |

## Development

Clone the repository and install in editable mode with dev dependencies:

```bash
git clone https://github.com/firebolt-db/dlt-firebolt.git
cd dlt-firebolt
pip install -e ".[dev]"
cp .env.example .env   # fill in Firebolt credentials (and S3 for integration tests)
pytest -m "not integration"
```

**Core e2e (upload, no S3):**

```bash
bash scripts/core_e2e.sh my_dataset          # nested merge
bash scripts/hn_core_e2e.sh hn_blog 30     # blog example
```

Optional live integration tests (requires Firebolt, S3, and AWS credentials):

```bash
FIREBOLT_RUN_INTEGRATION=1 pytest -m integration -v
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

## Status

Community package maintained by [Firebolt](https://github.com/firebolt-db/dlt-firebolt). Not part of core dlt.

- [x] Published on PyPI (`pip install dlt-firebolt`)
- [x] Append, merge, and replace dispositions
- [x] Nested multi-table merge
- [x] HTTP upload mode (0.3.0+, Firebolt Core)
- [ ] Website integration docs
- [ ] Optional listing on dlt community destinations page
