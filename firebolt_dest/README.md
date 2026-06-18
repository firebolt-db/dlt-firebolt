# Firebolt destination for dlt

Loads dlt pipelines into Firebolt using **direct HTTP upload (default)** or **S3 staging + `COPY INTO`**.

**Requires dlt-firebolt 0.2.0+** for upload mode. Earlier releases (0.1.x) support S3 staging only.

## Two ways to load

| Mode | Best for |
|------|----------|
| **`upload` (default)** | Firebolt Core, local dev, quick starts |
| **`s3`** | Managed Firebolt production, large bulk loads |

On **managed Firebolt** today, set `FIREBOLT_STAGING_MODE=s3`. Upload is the code default but the managed engine does not accept multipart upload yet.

## Prerequisites

### Upload mode (Core / local)

Firebolt Core running locally (default endpoint `http://localhost:3473`). No S3 bucket, external location, or AWS credentials for the Firebolt load step.

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

Set `FIREBOLT_S3_LOCATION_NAME` and `FIREBOLT_STAGING_MODE=s3`.

## Install

```bash
pip install "dlt-firebolt>=0.2.0"
```

Import once so dlt registers the destination:

```python
import firebolt_dest  # noqa: F401
```

## Configuration

### Firebolt Core

```
FIREBOLT_USE_CORE=1
FIREBOLT_CORE_URL=http://localhost:3473
FIREBOLT_STAGING_MODE=upload
```

### Managed Firebolt (S3)

```
FIREBOLT_CLIENT_ID=...
FIREBOLT_CLIENT_SECRET=...
FIREBOLT_ACCOUNT_NAME=...
FIREBOLT_DATABASE=...
FIREBOLT_ENGINE=...
FIREBOLT_STAGING_MODE=s3
S3_BUCKET=...
FIREBOLT_S3_LOCATION_NAME=...
```

The destination resolves the engine URL from your account on managed; you do not set an HTTP endpoint manually.

See the repository [README](https://github.com/firebolt-db/dlt-firebolt) and `.env.example` for the full reference.

## Usage

```python
import dlt
import firebolt_dest
from firebolt_dest.configuration import make_firebolt_pipeline

pipeline = make_firebolt_pipeline(
    pipeline_name="my_pipeline",
    dataset_name="my_dataset",
)

pipeline.run(my_resource(), loader_file_format="parquet")
```

Tables are created as `{dataset}_{table}` (e.g. `my_dataset_orders`).

## Supported capabilities

| Feature | Support |
|---------|---------|
| Loader format | Parquet only |
| Staging | `upload` (HTTP, default) or `s3` (COPY INTO) |
| `append` | Yes |
| `replace` | `truncate-and-insert`, `insert-from-staging` |
| `merge` | `delete-insert` (single-table and nested) |

## Upstream status

Community destination maintained in [firebolt-db/dlt-firebolt](https://github.com/firebolt-db/dlt-firebolt). Not part of core dlt.
