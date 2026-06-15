# Firebolt destination for dlt

Loads dlt pipelines into Firebolt using **filesystem staging (Parquet on S3) + `COPY INTO`**.

## Prerequisites

1. **Firebolt service account** (Settings → Service accounts) with access to your database and engine.
2. **S3 bucket** for dlt filesystem staging.
3. **Firebolt external location** pointing at that bucket prefix:

```sql
CREATE LOCATION "your_location_name" WITH
  SOURCE = 'CLOUD_STORAGE'
  URL = 's3://your-bucket/your-prefix/'
  CREDENTIALS = (AWS_ROLE_ARN = 'arn:aws:iam::...:role/...');
```

Set `FIREBOLT_S3_LOCATION_NAME` (or `s3_location_name` in secrets) to the exact location name above.

## Install

```bash
pip install dlt-firebolt
```

Import once so dlt registers the destination:

```python
import firebolt_dest  # noqa: F401
```

## Configuration

### `.dlt/secrets.toml`

```toml
[destination.firebolt]
s3_location_name = "your_location_name"
s3_prefix = "dlt-landing"

[destination.firebolt.credentials]
host = "YOUR_DATABASE"
database = "YOUR_ENGINE"
username = "YOUR_CLIENT_ID"
password = "YOUR_CLIENT_SECRET"
account_name = "YOUR_ACCOUNT_NAME"

[destination.filesystem]
bucket_url = "s3://your-bucket/dlt-landing/dlt/staging"
```

### Environment variables

See the repository `.env.example` for the full list. Minimum:

- `FIREBOLT_CLIENT_ID`, `FIREBOLT_CLIENT_SECRET`
- `FIREBOLT_ACCOUNT_NAME`, `FIREBOLT_DATABASE`, `FIREBOLT_ENGINE`
- `FIREBOLT_S3_LOCATION_NAME`, `S3_BUCKET`, `S3_PREFIX`
- AWS credentials for S3 staging (`AWS_PROFILE` or standard env vars)

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
| Staging | Filesystem (S3) required |
| `append` | Yes |
| `replace` | `truncate-and-insert`, `insert-from-staging` |
| `merge` | `delete-insert` |
| Transactions | Merge follow-up jobs run in an explicit transaction; ordinary loads use autocommit |

## Upstream status

Community destination maintained in [firebolt-db/dlt-firebolt](https://github.com/firebolt-db/dlt-firebolt). Not merged into core dlt.
