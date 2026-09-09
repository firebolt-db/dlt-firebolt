# Changelog

## Unreleased

- Added: opt-in `use_schema_per_dataset` / `FIREBOLT_USE_SCHEMA_PER_DATASET`.
  When enabled, `dataset_name` maps to a real Firebolt schema
  (`tenant_a.orders`) instead of the default `public.{dataset}_{table}`
  layout. Staging uses `{dataset}_staging`, and dlt state tables live under
  the dataset schema. Default remains **off** so existing pipelines are
  unchanged.
- Migration: enabling the flag is a deliberate layout break. Fresh vs retained
  incremental state is driven by **local** pipeline state (and optionally
  cloned destination `_dlt_*` tables), not by whether you ran
  `CREATE SCHEMA IF NOT EXISTS` before CLONE/CTAS. On a fresh machine a
  pre-created schema still yields a fresh local cursor. Do **not** use
  `dataset_name="public"` (or a staging layout of `public`) with the flag on —
  those names are rejected.
- Note: schema-mode `replace` uses `DELETE … WHERE 1=1` (not `TRUNCATE`) on
  both Core and managed for older-Core compatibility; the destination role
  needs `DELETE` privilege and full-table deletes create delete logs.

## 0.3.1

- Fixed: `TypeError: not all arguments converted during string formatting` on
  DECIMAL(precision, scale) columns when used with dlt >= 1.29. The `decimal`
  entry in `sct_to_dbt` was a static `"DOUBLE"` string; dlt 1.29 %-formats
  that template with `(precision, scale)`. Decimals now map to Firebolt
  `NUMERIC(p, s)`, preserving source precision instead of coercing to DOUBLE.
  Unbound decimals default to dlt's `(38, 9)`, matching Firebolt's own
  `NUMERIC` default. Precision outside Firebolt's 1–38 range or scale >
  precision raises a clear `TerminalValueError`.
- Fixed: the `wei` entry in `sct_to_dbt` had the same latent bug (static
  `"TEXT"` template formatted with `wei_precision`). `wei` now maps to
  unbound `TEXT` (Firebolt NUMERIC's max precision of 38 cannot hold uint256).
- Fixed: reverse type mapping (`from_destination_type`) now handles Firebolt's
  parameterized `information_schema` type strings such as `NUMERIC(12, 2)`
  and the `DOUBLE PRECISION` spelling, so existing tables reflect correctly
  on subsequent runs instead of falling back to `text`.
- Added regression tests for parameterized type mapping (decimal bounds,
  defaults, wei, text/timestamp/time/binary hints, and information_schema
  reflection round-trip).

## 0.3.0

- Simplify Core/managed config: auto-detect via `FIREBOLT_CORE_URL`.
- HTTP upload staging mode for Firebolt Core.

## 0.2.0

- HTTP upload staging for Firebolt Core.

## 0.1.x

- Initial public release: S3 staging + `COPY INTO`, merge/append/replace.
