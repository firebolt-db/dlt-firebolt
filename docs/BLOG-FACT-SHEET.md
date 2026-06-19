# Blog fact sheet & annotated outline

**Purpose:** Lock claims before redrafting `announcing-dlt-firebolt.md`.  
**Release target:** [dlt-firebolt 0.3.0 on PyPI](https://pypi.org/project/dlt-firebolt/0.3.0/) ships **with** the blog post — not after.

Benjamin’s DM (June 2026) is **reference only**. Do **not** quote or paraphrase into the public post: Leonard, ingress cost economics, managed upload timeline, “surface the error” as product direction. **Managed does not support upload today** — settled product fact from leadership; not a publish gate.

---

## Verified facts (safe to claim)

| Claim | Environment | Evidence |
|-------|-------------|----------|
| HTTP upload loads Parquet via `READ_PARQUET('upload://…')` | Firebolt Core | `scripts/core_e2e.sh` — nested merge v1/v2, spot-checks pass |
| HN top stories example loads with merge | Firebolt Core, upload | `scripts/hn_core_e2e.sh hn_blog 30` |
| S3 + `COPY INTO` append and nested merge | Managed Firebolt | Earlier session (`allhands` dataset) |
| Upload returns 400 on managed | Managed Firebolt | Engine: multipart upload not supported; S3/GCS only — expected, not a bug |
| Default staging mode is `upload` when unset | Code | `staging_mode_from_env()` default `"upload"` |
| Merge delete-insert for nested tables | Core (upload) + managed (S3) | Core e2e; managed merge runs |
| PyPI 0.1.3 has **no** upload mode | PyPI | Upload shipped in 0.2.0 |
| Public SQL reference documents `READ_PARQUET` for S3 only | Firebolt docs | `upload://` is on the separate [upload API page](https://docs.firebolt.io/reference-api/uploading-files) |

---

## Do NOT claim (removed from draft)

| ❌ Claim | Why |
|---------|-----|
| Phase 2 merge runs in “one transaction” / atomic rollback | SDK path uses `supports_transactions=False`; atomicity not proven at engine layer |
| “Works across Firebolt offerings” without qualification | Managed production must use S3 today; upload is Core/local |
| “No endpoint URL to manage” (blanket) | Core requires `FIREBOLT_CORE_URL` |
| Managed upload “coming soon” / timeline | Internal DM only |
| “Already checking with eng” | Benjamin confirmed managed behavior; optional internal follow-up only |
| Destination enforces upload size limits client-side | Code does not; cite Firebolt API spec only |
| Active collaboration with dlt team on core merge | Unless literally true; use community-package framing |
| “Nested merge verified on Core + managed” | Benjamin removed; managed S3 nested merge not E2E-verified |

---

## Two-mode framing (Benjamin-aligned, public-safe)

| Mode | Audience | Staging | Firebolt load path |
|------|----------|---------|-------------------|
| **`upload` (default)** | Firebolt Core, local dev, quick starts | Local disk (`file://`) | HTTP multipart → `upload://` |
| **`s3`** | Managed Firebolt production, large bulk loads | S3 bucket | `COPY INTO` from external location |

**Managed note (README + blog, one sentence):** On managed Firebolt today, use `FIREBOLT_STAGING_MODE=s3`. Upload mode is the default in code but is not supported by the managed engine yet; the destination returns a clear error if you try.

---

## Upload size limit (blog wording — Benjamin, June 2026)

Use plain English in the blog (not the API quote):

> Upload supports files up to 1 GB each, measured after decompression. For larger files, use S3 mode.

Per-file wording is correct for this destination: `upload_client.py` sends one multipart POST per file. Do **not** restore the verbatim API quote; Benjamin closed that comment.

---

## Annotated outline

Benjamin asked for **code-first** order (June 2026): install, config, HN example, **then** two-modes paragraph + table, **then** Under the hood. Do not move modes back to the intro.

### 1. Intro
- Gap statement only; no modes table here.

### 2. What it does + configuration
- `pip install "dlt-firebolt>=0.3.0"` + Requires 0.3.0+ line.
- Split managed vs Core; `FIREBOLT_CORE_URL` auto-selects Core (0.3.0).

### 3. Real example — Hacker News top stories
- Self-contained: `FIREBOLT_CORE_URL` in block; flat fields (no nested surprise).
- Real public API, no auth; not GitHub / not MotherDuck parallel.
- Verified on Core (`scripts/hn_core_e2e.sh`).

### 4. Two ways to load (after example, before Under the hood)
- Two-modes paragraph + table + managed uses `s3` today.
- No “future managed support” in table.

### 5. Under the hood
- Upload: plain-English 1 GB per file; S3 for larger loads.

### 6. Merge
- Correctness / fixed order; show SQL sequence; no atomicity language.
- Closing sentence: MERGE is single-table; nested uses uniform delete-insert.
- Do **not** re-add “Nested merge verified on Core + managed” (Benjamin deleted; managed E2E not run).

### 7. Availability
- Community package framing only; no unverified dlt-core collaboration claim.
- Wording: "Install from PyPI" (publish package before the blog goes live).

---

## Pre-publish checklist

- [x] README updated (managed S3 note, Core env vars, transaction wording fixed)
- [x] `firebolt_dest/README.md` updated (no transaction overclaim)
- [x] `firebolt_dest/__version__` = `0.3.0`
- [ ] Manual twine publish → PyPI 0.3.0
- [x] Blog `pip install` and PyPI links point at 0.3.0
- [x] Merge section has no atomicity language
- [x] Wheel built; install-tested via `core_e2e.sh` + `hn_core_e2e.sh`
- [x] All upload code committed

---

## Internal note (do not publish)

Managed multipart upload on SaaS: optional follow-up with engine team. Not a blog or release gate — Benjamin confirmed current managed behavior.
