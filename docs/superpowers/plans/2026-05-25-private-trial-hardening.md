# Private Trial Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the product for personal daily use and limited friends trial with deployment, backup, import/export, secret handling, and observability.

**Architecture:** Add operational scripts and docs without changing core product behavior. Prefer explicit local commands and smoke checks over hidden automation.

**Tech Stack:** Python scripts, shell scripts, FastAPI health/status endpoints, docs.

---

## Files

Create:

- `ops/run_local_fixture.sh`
- `ops/run_local_private.sh`
- `ops/backup_data.sh`
- `ops/export_snapshot.py`
- `ops/import_snapshot.py`
- `tests/test_snapshot_import_export.py`
- `docs/deployment/private-trial.md`
- `docs/security/secrets.md`
- `docs/operations/runbook.md`

Modify:

- `.gitignore`
- `README.md`

## Task 1: Import/Export

- [ ] Implement `ops/export_snapshot.py` to create a tarball containing:
  - `data/summary.json`
  - `data/scorecards`
  - `data/shots`
  - `data/snapshots`
  - `data/sync`
- [ ] Explicitly exclude:
  - `.garmin_tokens`
  - `.env`
  - `clubs.json` unless `--include-clubs` is passed
- [ ] Implement `ops/import_snapshot.py` to restore into a target data root.
- [ ] Add tests that export/import fixture temp data and assert secrets are excluded.
- [ ] Commit:

```bash
git add ops/export_snapshot.py ops/import_snapshot.py tests/test_snapshot_import_export.py
git commit -m "feat: add private data import export"
```

## Task 2: Local Run Scripts

- [ ] Add `ops/run_local_fixture.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
AI_CADDIE_DATA_MODE=fixture uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

- [ ] Add `ops/run_local_private.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
AI_CADDIE_DATA_MODE=local_or_fixture uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

- [ ] Add `ops/backup_data.sh` calling `ops/export_snapshot.py`.
- [ ] Commit:

```bash
git add ops/run_local_fixture.sh ops/run_local_private.sh ops/backup_data.sh
git commit -m "chore: add private run scripts"
```

## Task 3: Security And Runbook Docs

- [ ] Write `docs/security/secrets.md` covering:
  - no Garmin password in cloud
  - cookie/CSRF storage
  - NIM/Gemini/OpenAI/Anthropic keys
  - snapshot export exclusions
- [ ] Write `docs/deployment/private-trial.md` covering:
  - Render/Vercel-style staging
  - NAS/private server option
  - SSH tunnel dev
  - offline-first mobile caveat
- [ ] Write `docs/operations/runbook.md` covering:
  - start/stop services
  - refresh Garmin session
  - run tests
  - backup/restore
  - inspect sync status
- [ ] Update README with pointers.
- [ ] Commit:

```bash
git add docs/security/secrets.md docs/deployment/private-trial.md docs/operations/runbook.md README.md
git commit -m "docs: add private trial operations runbook"
```

## Task 4: Verification

- [ ] Run backend full tests.
- [ ] Run import/export tests.
- [ ] Run fixture API and Web smoke.
- [ ] Verify `git status --ignored --short .garmin_tokens .env data output logs clubs.json` does not show trackable secret files.
