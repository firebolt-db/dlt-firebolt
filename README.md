# dlt-firebolt

Community [dlt](https://dlthub.com/) destination for [Firebolt](https://www.firebolt.io/).

Load data with **filesystem staging (Parquet on S3) and `COPY INTO`**, the same pattern used by dlt's Snowflake and Redshift destinations.

## Install

```bash
pip install dlt-firebolt
```

Requires Python 3.10+.

Register the destination once in your project:

```python
import firebolt_dest  # registers destination="firebolt"
```

## Prerequisites

1. **Firebolt service account** with access to your database and engine.
2. **S3 bucket** for dlt filesystem staging.
3. **Firebolt external location** for that bucket prefix:

```sql
CREATE LOCATION "your_location_name" WITH
  SOURCE = 'CLOUD_STORAGE'
  URL = 's3://your-bucket/your-prefix/'
  CREDENTIALS = (AWS_ROLE_ARN = 'arn:aws:iam::...:role/...');
```

Set `FIREBOLT_S3_LOCATION_NAME` (or `s3_location_name` in secrets) to the exact location name from `CREATE LOCATION`.

## Quick start

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

Tables are created as `{dataset}_{table}` (for example `my_dataset_orders`).

### Using `.dlt/secrets.toml`

```python
pipeline = make_firebolt_pipeline(
    pipeline_name="my_pipeline",
    dataset_name="my_dataset",
    from_secrets=True,
)
```

Example secrets file:

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

See `.dlt/secrets.toml.example` in the repository for a full template.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREBOLT_CLIENT_ID` | yes | Service account client ID |
| `FIREBOLT_CLIENT_SECRET` | yes | Service account secret |
| `FIREBOLT_ACCOUNT_NAME` | yes | Firebolt account name |
| `FIREBOLT_DATABASE` | yes | Target database |
| `FIREBOLT_ENGINE` | yes | Engine name |
| `FIREBOLT_S3_LOCATION_NAME` | yes | Firebolt external location name (must match `CREATE LOCATION`) |
| `S3_BUCKET` | yes | Staging bucket |
| `S3_PREFIX` | no | Key prefix (default: `dlt-landing`) |
| `DLT_DATASET_NAME` | no | Default dataset name (default: `demo`) |

Set credentials via environment variables or `.dlt/secrets.toml`. Do not commit secrets.

## Supported capabilities

| Feature | Support |
|---------|---------|
| Loader format | Parquet only |
| Staging | Filesystem (S3) required |
| `append` | Yes |
| `replace` | `truncate-and-insert`, `insert-from-staging` |
| `merge` | `delete-insert` (single-table and nested) |
| Transactions | Merge follow-up jobs run in an explicit transaction; ordinary loads use autocommit |

## Development

Clone the repository and install in editable mode with dev dependencies:

```bash
git clone https://github.com/firebolt-db/dlt-firebolt.git
cd dlt-firebolt
pip install -e ".[dev]"
cp .env.example .env   # fill in Firebolt and S3 credentials
pytest -m "not integration"
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
- [ ] Website integration docs
- [ ] Optional listing on dlt community destinations page
