# Phase 4 End-To-End Private Pipeline - Design

- Date: 2026-06-06
- Branch: `integration/v2`
- Scope: Phase 4 in `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`.

## Background

Phase 4 outcome: one command runs the private single-user sync path idempotently.

The product already has pieces of the path:

- Garmin CN auth and fetch
- durable snapshots
- played geometry dependency discovery and sync
- course-reference ingest
- sync status and readiness endpoints
- real-data smoke patterns

The remaining gap is a single private pipeline contract that ties them together and reports coverage
without leaking local secrets.

## Goals

1. Wire auth refresh, history/shots fetch, geometry sync, and course-reference ingest into one idempotent
   command.
2. Add readiness fields for last sync, session age, data freshness, shot coverage, geometry coverage, and
   course-reference coverage.
3. Add a local private smoke that runs against real data without logging secrets.
4. Preserve last successful local data when a later sync fails or requires reauth.
5. Make the command safe for repeated cron-style execution.

## Non-Goals

- Do not require GitHub Actions or live cloud CI for private data validation.
- Do not print raw Garmin files, cookies, CSRF, passwords, tokens, or local private paths.
- Do not delete or overwrite existing snapshots unless explicitly requested by an import/export workflow.
- Do not require a full geometry crawl; geometry sync remains missing-only and bounded.

## Command Contract

The canonical command is:

```bash
AI_CADDIE_AUTH_REFRESH=playwright uv run python -m ai_caddie.pipeline --shots --refresh-auth --geometry-limit 50
```

The command should be idempotent:

- cached scorecards and shots are skipped or rewritten safely
- geometry uses missing dependency discovery
- course references are rebuilt deterministically
- a failed run updates connector status but does not invalidate previous snapshots

The server endpoint `/api/v2/sync/garmin` remains a product API wrapper for the same connector behavior.

## Readiness And Coverage

Readiness must expose safe coverage summaries:

- last successful sync time
- last connector state and error code
- scorecard count
- shot file count
- normalized shot count when available
- played geometry coverage
- course-reference coverage
- session/auth state without credential values

Coverage is useful even when degraded. A degraded readiness state should tell the user what is missing,
not block access to already-synced history.

## Local Private Smoke

Add or maintain a local-only smoke command that verifies:

- `AI_CADDIE_DATA_MODE=local`
- `/api/v2/health`
- `/api/v2/history/overview`
- `/api/v2/history/rounds`
- `/api/v2/history/stats`
- `/api/v2/sync/status`
- one round detail when a round exists
- readiness output contains no credential terms or local private paths

The smoke writes a small evidence JSON with sanitized counts and timestamps.

## Error Handling

- Auth failure returns `reauth_required`.
- Fetch failure returns `error`.
- Geometry failures are reported as coverage debt and do not fail the whole sync unless every dependency
  path is unusable.
- Course-reference failures are reported as coverage debt and do not erase existing references.
- All user-facing details pass through redaction before status/API exposure.

## Testing

Add or extend targeted tests:

- `tests/test_pipeline.py`
  - all steps run in order when auth succeeds.
  - auth failure short-circuits fetch and preserves result shape.
  - geometry-limit is passed through.
  - course-reference ingest runs after fetch.
- `tests/test_server_v2_readiness.py`
  - readiness includes sync freshness, shot coverage, geometry coverage, and course-reference coverage.
  - readiness redacts secrets and private paths.
- local-only smoke:
  - runs outside CI against real data.
  - records sanitized evidence in docs or logs.

Verification command:

```bash
uv run python -m unittest tests.test_pipeline tests.test_server_v2_readiness tests.test_server_v2_sync_status -v
git diff --check
```

## Acceptance Criteria

- One local command can run the private sync pipeline end to end.
- The command is idempotent and bounded.
- Readiness shows data freshness and coverage/confidence.
- Local private smoke evidence is current and secret-free.
