# Phase 6 Deployment Native Release And Trial Hardening - Design

- Date: 2026-06-06
- Branch: `integration/v2`
- Scope: Phase 6 in `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`.

## Background

Phase 6 outcome: the private single-user product can run unattended and ship to the user's phone/watch.

The repo already has deployment and operations artifacts:

- `render.yaml`
- `fly.toml`
- `Dockerfile`
- `docker-compose.yml`
- `ops/smoke_private_trial.sh`
- `ops/backup_data.sh`
- `ops/export_snapshot.py`
- `ops/import_snapshot.py`
- native build evidence tooling
- readiness endpoint and tests

The remaining gap is to turn those artifacts into a verified private-trial release path.

## Goals

1. Deploy a reachable backend using existing Render, Fly, or container manifests.
2. Configure admin token, private runtime root, CORS, backup, import/export, and redaction checks.
3. Keep native mobile CI gated to native changes or manual dispatch.
4. Run TestFlight signing/bootstrap only when explicitly needed.
5. Keep private-trial smoke/readiness evidence current and secret-free.

## Non-Goals

- Do not make this a public multi-user SaaS deployment.
- Do not store Garmin credentials in deployment manifests.
- Do not run expensive native CI on routine backend/docs changes.
- Do not perform TestFlight signing or distribution without explicit user instruction.
- Do not move private local data into the repo.

## Deployment Contract

Backend deployment must provide:

- private security profile
- admin token configured as a secret
- persistent private runtime root
- local_or_fixture or local data mode, depending on deployment stage
- readiness endpoint
- health endpoint
- backup/import/export path
- CORS configured for the private Web origin

Web deployment must point to the private backend through `VITE_AI_CADDIE_API_BASE_URL`.

## Operations Contract

Operational scripts should remain local/private and secret-safe:

- `ops/smoke_private_trial.sh`
- `ops/backup_data.sh`
- `ops/export_snapshot.py`
- `ops/import_snapshot.py`

Readiness should report:

- backup freshness
- smoke freshness
- private snapshot acceptance state
- native build evidence state
- sync/readiness degraded reasons

All paths and credential values must be redacted before API exposure.

## Native Release Contract

Native release is gated:

- Linux CI verifies source/contracts only.
- macOS/Xcode simulator tests are required before native release claims.
- TestFlight signing/bootstrap happens only when explicitly requested.
- Native build evidence is written as sanitized JSON and consumed by readiness.

## Error Handling

- Missing backup or smoke evidence makes readiness degraded, not failed.
- Missing native build evidence makes native readiness degraded.
- Missing admin token blocks private deployment readiness.
- Import/export rejects unsafe paths and excludes credentials.
- Smoke failures are recorded as evidence without leaking response secrets.

## Testing

Add or extend:

- `tests/test_deployment_manifests.py`
  - manifests define private runtime root, health checks, admin token placeholders, and no credentials.
- `tests/test_snapshot_import_export.py`
  - export excludes secrets and import rejects unsafe paths.
- `tests/test_server_v2_readiness.py`
  - readiness reflects backup, smoke, native evidence, and redaction.
- `tests/test_ci_workflow.py`
  - CI path filters preserve native minute controls.
- `tests/test_native_build_evidence.py`
  - native evidence schema remains secret-free.

Verification command:

```bash
uv run python -m unittest tests.test_deployment_manifests tests.test_snapshot_import_export tests.test_server_v2_readiness tests.test_ci_workflow tests.test_native_build_evidence -v
git diff --check
```

## Acceptance Criteria

- Backend is reachable in the chosen private deployment target.
- Private trial smoke evidence is current and secret-free.
- Backup/import/export flow is verified.
- Mobile can install through TestFlight only after explicit native release steps are run.
- Readiness accurately reports private-trial state and residual gaps.
