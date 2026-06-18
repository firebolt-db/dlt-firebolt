# Blog fact sheet & annotated outline

**Purpose:** Lock claims before redrafting `announcing-dlt-firebolt.md`.  
**Release target:** [dlt-firebolt 0.2.0 on PyPI](https://pypi.org/project/dlt-firebolt/0.2.0/) ships **with** the blog post — not after.

Benjamin’s DM (June 2026) is **reference only**. Do **not** quote or paraphrase into the public post: Leonard, ingress cost economics, managed upload timeline, “surface the error” as product direction. **Managed does not support upload today** — settled product fact from leadership; not a publish gate.

---

## Verified facts (safe to claim)

| Claim | Environment | Evidence |
|-------|-------------|----------|
| HTTP upload loads Parquet via `READ_PARQUET('upload://…')` | Firebolt Core | `scripts/core_e2e.sh` — nested merge v1/v2, spot-checks pass |
| GitHub stargazers example loads with merge | Firebolt Core, upload | `scripts/github_stars_core_e2e.sh` — `LOADED and contains no failed jobs` |
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
| “No endpoint URL to manage” (blanket) | Core requires `FIREBOLT_USE_CORE=1` + `FIREBOLT_CORE_URL` |
| Managed upload “coming soon” / timeline | Internal DM only |
| “Already checking with eng” | Benjamin confirmed managed behavior; optional internal follow-up only |
| Destination enforces upload size limits client-side | Code does not; cite Firebolt API spec only |
| Active collaboration with dlt team on core merge | Unless literally true; use community-package framing |

---

## Two-mode framing (Benjamin-aligned, public-safe)

| Mode | Audience | Staging | Firebolt load path |
|------|----------|---------|-------------------|
| **`upload` (default)** | Firebolt Core, local dev, quick starts | Local disk (`file://`) | HTTP multipart → `upload://` |
| **`s3`** | Managed Firebolt production, large bulk loads | S3 bucket | `COPY INTO` from external location |

**Managed note (README + blog, one sentence):** On managed Firebolt today, use `FIREBOLT_STAGING_MODE=s3`. Upload mode is the default in code but is not supported by the managed engine yet; the destination returns a clear error if you try.

---

## Upload size limit (spec-tied wording)

From [Upload and query local files](https://docs.firebolt.io/reference-api/uploading-files), Limits section — use verbatim in blog:

> The file parts of one request can hold at most 1 GB of data in total, measured after decompression.

Add: the destination does **not** enforce this client-side.

---

## Annotated outline

### 1. Intro
- Two modes upfront: upload for Core/local, S3 for managed production.

### 2. Two ways to load
- No “future managed support” in table.
- pip pin: `pip install "dlt-firebolt>=0.2.0"`.

### 3. Quick start + configuration
- Split managed vs Core; no blanket “no endpoint URL”.

### 4. Real example — GitHub stargazers
- Self-contained: `FIREBOLT_USE_CORE=1` inside the code block.
- Bounded: `MAX_PAGES = 1` to match verified run; note GitHub rate limits.
- Verified on Core (`scripts/github_stars_core_e2e.sh oss_analytics 1`).

### 5. Under the hood
- Upload: spec-tied 1 GB quote + link; S3 for larger loads.
- Note: `upload://` is documented on the upload API page, not the general `READ_PARQUET` S3 reference.

### 6. Merge
- Correctness / fixed order; show SQL sequence; no atomicity language.

### 7. Availability
- Community package framing only; no unverified dlt-core collaboration claim.
- Wording: "Install from PyPI" (publish package before the blog goes live).

---

## Pre-publish checklist

- [x] README updated (managed S3 note, Core env vars, transaction wording fixed)
- [x] `firebolt_dest/README.md` updated (no transaction overclaim)
- [x] `firebolt_dest/__version__` = `0.2.0`
- [ ] Manual twine publish → PyPI 0.2.0
- [x] Blog `pip install` and PyPI links point at 0.2.0
- [x] Merge section has no atomicity language
- [x] Wheel built; install-tested via `core_e2e.sh` + `github_stars_core_e2e.sh`
- [x] All upload code committed

---

## Internal note (do not publish)

Managed multipart upload on SaaS: optional follow-up with engine team. Not a blog or release gate — Benjamin confirmed current managed behavior.
