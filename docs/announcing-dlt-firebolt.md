# Announcing dlt-firebolt: a native dlt destination for Firebolt

dlt (data load tool) has become one of the most widely adopted open-source libraries for moving data into analytical systems. It handles schema inference, normalization, and incremental loading through a simple embedded Python library, and it has become a go-to for both hand-written and agent-generated data workflows.

Until now, dlt could already read from Firebolt through its standard SQL source, but had no native write destination. Teams who wanted to land data in Firebolt through dlt had to assemble the staging and load steps themselves. dlt-firebolt closes that gap. It is a native dlt destination for Firebolt that you install with a single command and select like any other warehouse target.

## What it does

Install the package:

```bash
pip install "dlt-firebolt>=0.3.0"
```

Requires dlt-firebolt 0.3.0+

On Firebolt Core, set `FIREBOLT_CORE_URL` to your Core endpoint (for example, `http://localhost:3473`). That uses **upload mode** by default: dlt writes Parquet locally, then the destination uploads each file over HTTP and loads it with `INSERT INTO … SELECT FROM READ_PARQUET('upload://…')`.

### Configuration

**Managed Firebolt (stage data through S3):**

```
FIREBOLT_ACCOUNT_NAME=your-account
FIREBOLT_ENGINE=your-engine
FIREBOLT_DATABASE=your-database
FIREBOLT_CLIENT_ID=your-service-account-id
FIREBOLT_CLIENT_SECRET=your-service-account-secret
FIREBOLT_STAGING_MODE=s3
S3_BUCKET=your-staging-bucket
FIREBOLT_S3_LOCATION_NAME=your-location-name
```

The destination resolves the engine URL from your account. The machine running dlt needs AWS credentials that can write to the staging bucket (environment variables, an AWS profile, or an attached IAM role); Firebolt reads the staged files through the external location you configured, not the runner's AWS identity. Staging Parquet is not deleted automatically after `COPY INTO`, so add an S3 lifecycle rule or periodic cleanup if you don't want objects to accumulate.

**Firebolt Core (upload data over HTTP):**

```
FIREBOLT_CORE_URL=http://localhost:3473
```

Setting `FIREBOLT_CORE_URL` selects Core; the account variables above select managed. There is no separate flag, and upload is the default staging mode so you don't need to set it.

See the [README](https://github.com/firebolt-db/dlt-firebolt) for the full reference.

### A real pipeline example

Here is a short pipeline that loads Hacker News top stories with merge, so reruns refresh scores and comment counts without duplicating rows. Verified on Firebolt Core with upload mode (`scripts/hn_core_e2e.sh`).

```python
import os

import dlt
import firebolt_dest
import requests
from firebolt_dest.configuration import make_firebolt_pipeline

os.environ.setdefault("FIREBOLT_CORE_URL", "http://localhost:3473")

@dlt.resource(name="hn_top_stories", write_disposition="merge", primary_key="id")
def hn_top_stories():
    ids = requests.get(
        "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=30
    ).json()
    for story_id in ids[:30]:
        item = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=30
        ).json()
        yield {
            k: item.get(k)
            for k in ("id", "title", "by", "score", "descendants", "url", "time")
        }

pipeline = make_firebolt_pipeline(pipeline_name="hackernews", dataset_name="hn")
pipeline.run(hn_top_stories(), loader_file_format="parquet")
```

The destination supports two staging modes. **Upload mode** sends Parquet straight to Firebolt over HTTP, with no S3 bucket, no external location, and no AWS credentials for the load step. It is the default and works today on **Firebolt Core** and local dev. **S3 mode** stages Parquet in your bucket and loads with `COPY INTO`; use it for **managed Firebolt production** and large bulk loads.

## Two ways to load

| Mode | Best for | What you need |
|------|----------|---------------|
| **`upload` (default)** | Firebolt Core, local dev, quick starts | Core endpoint; no object storage for the Firebolt load |
| **`s3`** | **Managed Firebolt production**, large bulk loads | Service account plus S3 bucket and Firebolt external location |

Set the mode with `FIREBOLT_STAGING_MODE=upload` or `FIREBOLT_STAGING_MODE=s3`. On managed Firebolt today, use `s3`.

## Under the hood

**Upload mode.** dlt normalizes data to Parquet on local disk. For each file, the destination sends a multipart HTTP request to your Firebolt engine: the SQL statement and the Parquet bytes travel together. Firebolt reads the file with the `upload://` scheme through `READ_PARQUET` and inserts into the target table. Upload supports files up to 1 GB each, measured after decompression. For larger files, use S3 mode.

**S3 mode** follows the familiar staging-then-COPY pattern: Parquet lands in your S3 bucket, then Firebolt loads with `COPY INTO` from an external location you configure once. Tables land as `{dataset}_{table}`. Connection details come from environment variables or a standard dlt secrets file.

## Append, replace, and merge

The destination supports the three write dispositions dlt users expect:

- **append** adds new rows on each run.
- **replace** rebuilds the table from the latest load.
- **merge** performs an upsert, and it works for both single tables and nested, multi-table records.

## How merge works

A merge is not a single statement. It runs in two phases.

**Phase 1: stage the batch.** dlt writes Parquet and loads it into Firebolt staging tables (via upload or `COPY INTO`, depending on mode).

**Phase 2: apply the upsert.** The destination runs a follow-up block in a fixed order so nested child rows stay aligned with their parent keys. The emitted SQL follows this shape (temp table names include hash suffixes in practice, and inserts enumerate columns):

```sql
-- Snapshot the keys being replaced
CREATE TABLE orders_delete_tmp AS
  SELECT d._dlt_id FROM orders AS d
  WHERE EXISTS (SELECT 1 FROM orders_staging AS s WHERE d.order_id = s.order_id);

-- Delete old rows: nested children first, then parents
DELETE FROM orders__items WHERE _dlt_root_id IN (SELECT * FROM orders_delete_tmp);
DELETE FROM orders        WHERE _dlt_id      IN (SELECT * FROM orders_delete_tmp);

-- Snapshot insert keys, deduped to one row per key
CREATE TABLE orders_insert_tmp AS
  SELECT _dlt_id FROM (
    SELECT ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY (SELECT NULL)) AS rn, _dlt_id
    FROM orders_staging
  ) WHERE rn = 1;

-- Insert new versions: parents, then children
INSERT INTO orders        SELECT ... FROM orders_staging        WHERE _dlt_id      IN (SELECT * FROM orders_insert_tmp);
INSERT INTO orders__items SELECT ... FROM orders__items_staging WHERE _dlt_root_id IN (SELECT * FROM orders_insert_tmp);

-- Drop helper tables
DROP TABLE IF EXISTS orders_delete_tmp;
DROP TABLE IF EXISTS orders_insert_tmp;
```

Ordinary appends and replaces skip the merge follow-up and use the simpler load path. Firebolt has a native `MERGE` statement, but a single `MERGE` targets one table. Because a nested record spans a parent and its child tables, the destination uses one uniform delete-insert path that keeps parent and child rows aligned.

## Availability

dlt-firebolt is a community package maintained by Firebolt, released under the Apache 2.0 license and supporting Python 3.10 and above. The source is public at [github.com/firebolt-db/dlt-firebolt](https://github.com/firebolt-db/dlt-firebolt). Install from [PyPI](https://pypi.org/project/dlt-firebolt/0.3.0/) with `pip install "dlt-firebolt>=0.3.0"`.
