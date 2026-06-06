# Phase 4 Private Pipeline Evidence

- Date: 2026-06-06
- Branch: `integration/v2`

## Scope

Implemented Phase 4 from `docs/superpowers/specs/2026-06-06-phase-4-private-pipeline-design.md`.

## Evidence

- `ai_caddie.pipeline` runs auth, fetch, geometry, and course-reference ingest behind one command.
- `SyncResult` reports geometry and course-reference coverage.
- Course-reference ingest failure is recorded as a degraded note instead of crashing sync.
- Readiness exposes sync freshness, session age, normalized shot count, shot counts, geometry coverage, and course-reference coverage.
- `ops/smoke_local_private_data.py` runs local-only endpoint smoke with secret-free evidence.

## Verification

```bash
uv run python -m unittest tests.test_pipeline tests.test_server_v2_readiness tests.test_server_v2_sync_status tests.test_local_private_smoke -v
```

Result: PASS, 33 tests in 99.673s.

```bash
git diff --check
```

Result: PASS.

```bash
AI_CADDIE_LOCAL_SMOKE_EVIDENCE=/tmp/ai-caddie-local-private-smoke.json uv run python ops/smoke_local_private_data.py
```

Result: PASS. Evidence schema `ai-caddie-local-private-smoke-evidence-v1`, `endpointCount=7`, `roundDetailChecked=true`.
