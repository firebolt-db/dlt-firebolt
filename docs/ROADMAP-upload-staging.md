# Roadmap: two-mode staging (`upload://` + S3)

**Status:** `upload` mode implemented in **0.2.0** (default). S3 mode unchanged from 0.1.x. Blog ships with this release — not as a fast follow.

Benjamin’s design: easy to use and working across offerings is core to the story. Default to direct HTTP upload; reserve S3 for scale.

| Mode | Status | When to use |
|------|--------|-------------|
| **`upload` (default)** | **Shipped in 0.2.0** | Local dev, Firebolt Core, quick starts; see Firebolt upload API for per-request size limits |
| **`s3`** | Shipped in 0.1.x | Large bulk loads, multi-GB datasets, maximum throughput |

---

## Shipped in 0.2.0

- `FIREBOLT_STAGING_MODE=upload|s3` (default: `upload`)
- `FireboltUploadLoadJob`: multipart HTTP POST + `INSERT INTO … SELECT FROM READ_PARQUET('upload://…')`
- Local filesystem staging (`file://`) — no S3 bucket or external location in upload mode
- S3 + `COPY INTO` path preserved for `staging_mode=s3`
- Merge follow-up SQL and transactional upsert unchanged

---

## Remaining work before blog publish

| Item | Priority | Notes |
|------|----------|-------|
| Live test upload mode on managed Firebolt | **Blocker** | Run `FIREBOLT_STAGING_MODE=upload pytest -m integration` |
| Live test upload mode on Firebolt Core | **Blocker** | Validates “works across offerings” claim |
| GitHub example copy-paste verify | High | Run blog snippet end-to-end |
| Firebolt integration docs page | Medium | Modeled on Airbyte/dbt pages |
| Additional loader formats on upload path | Medium | 0.2.0 is Parquet-only (same as S3 path today); map CSV/Avro to `READ_CSV` / `READ_AVRO` later |
| Auto-fallback upload → S3 when > 1 GB | Nice-to-have | Clear error today; auto-switch later |

---

## Architecture (reference)

### Upload mode flow

1. dlt normalizes to Parquet under local `file://` staging.
2. For each load file, destination POSTs multipart form to engine URL:
   - `sql` part: `INSERT INTO {table} SELECT * FROM READ_PARQUET('upload://{part}')`
   - file part: Parquet bytes
3. Merge/replace follow-up jobs run as today (DDL transaction on upsert block).

### S3 mode flow (unchanged)

1. dlt writes Parquet to S3.
2. `COPY INTO` from Firebolt external location.
3. Merge/replace follow-up as today.

### Firebolt constraint

`upload://` works only in table-valued read functions, not in `COPY FROM`. See [Upload and query local files](https://docs.firebolt.io/reference-api/uploading-files).

---

## Future (post-launch)

- **0.2.x:** Additional formats on upload path; clearer errors when exceeding 1 GB
- **0.3.x:** Auto-fallback to S3 for large packages; optional `upload` default tuning based on Core production feedback
- **Docs:** dlt community destinations listing; Firebolt website integration page
