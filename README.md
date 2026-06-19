# dlt-firebolt

Community [dlt](https://dlthub.com/) destination for [Firebolt](https://www.firebolt.io/).

Load data into Firebolt with dlt using **direct HTTP upload (default)** or **S3 staging + `COPY INTO`** for large loads.

**Requires [dlt-firebolt 0.2.0+](https://pypi.org/project/dlt-firebolt/0.2.0/)** for upload mode. Earlier PyPI releases (0.1.x) support S3 staging only.

## Two ways to load

| Mode | Best for | Firebolt load path |
|------|----------|-------------------|
| **`upload` (default)** | Firebolt Core, local dev, quick starts | HTTP multipart → `READ_PARQUET('upload://…')` |
| **`s3`** | **Managed Firebolt production**, large bulk loads | Parquet on S3 → `COPY INTO` |

On **managed Firebolt** today, set `FIREBOLT_STAGING_MODE=s3`. Upload is the code default but the managed engine does not accept multipart upload yet; you will get a clear error if you use upload mode there. Upload mode is verified on **Firebolt Core** and local workflows.

## Install

```bash
pip install "dlt-firebolt>=0.2.0"
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

## Quick start

### Firebolt Core (upload, no S3)

```bash
export FIREBOLT_USE_CORE=1
export FIREBOLT_CORE_URL=http://localhost:3473
export FIREBOLT_STAGING_MODE=upload   # default
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

Tables are created as `{dataset}_{table}` (for example `my_dataset_orders`).

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

The destination resolves the engine URL from your account; you do not set an HTTP endpoint manually.

### Firebolt Core

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREBOLT_USE_CORE` | yes | Set to `1` |
| `FIREBOLT_CORE_URL` | no | Core HTTP endpoint (default: `http://localhost:3473`) |
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
- [x] HTTP upload mode (0.2.0+, Firebolt Core)
- [ ] Website integration docs
- [ ] Optional listing on dlt community destinations page
