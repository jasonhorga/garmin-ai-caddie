# Phase 2 Auth Refresh And Fetch Automation - Design

- Date: 2026-06-06
- Branch: `integration/v2`
- Scope: Phase 2 in `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`.

## Background

Phase 2 outcome: the data pipeline refreshes Garmin session material and fetches scorecards/shots
without manual Claude/browser handoff.

The repo already has the raw capabilities:

- `garmin_auth.py` reads cached Garmin CN web session material, refreshes browser cookies, and falls
  back to Playwright when browser cookies are unavailable.
- `garmin_playwright_login.py` can mint web cookies and CSRF from a real Chromium session using local
  `.garmin_tokens/garmin_login.json` credentials.
- `fetch.py` can fetch summary/details/shots, has `--refresh-auth`, and retries after 401/403 in several
  paths.
- `ai_caddie/connectors/garmin_cn.py` wraps the legacy fetch workflow and writes connector status and
  durable snapshots.
- `/api/v2/sync/garmin` already exposes `force_refresh_auth`, and `ai_caddie.pipeline` already has a
  CLI with `--refresh-auth`.

The gap is not a new login strategy. The gap is a productized connector contract with explicit retry,
refresh, cron, status, and secret-safety behavior covered by deterministic tests.

## Goals

1. Productize headless Garmin CN login by making the connector call a small auth-refresh boundary instead
   of relying on raw script behavior.
2. Guarantee one safe auth refresh and retry when summary/detail/shot fetch receives 401/403.
3. Keep `--refresh-auth` and the server `force_refresh_auth=true` path cron-compatible and documented.
4. Add mock browser/auth tests that prove no cookie, CSRF, password, token, authorization header, local
   private path, or `.garmin_tokens` path leaks through status, API responses, or `safe_meta`.
5. Preserve cached snapshots when auth refresh fails.

## Non-Goals

- Do not replace Garmin CN web-session auth with official OAuth. `garmin_oauth` remains a feasibility
  track.
- Do not redesign the private credential store. The local credential source remains
  `.garmin_tokens/garmin_login.json`.
- Do not run live Playwright or live Garmin network calls in CI.
- Do not print or return secret values, even in failure details.
- Do not remove the manual session import path; it remains useful for recovery and mobile/iOS handoff.

## Chosen Approach

Keep the existing login/fetch mechanics, but move the product contract into connector-level units:

- An auth helper boundary that exposes `ensure_session(force_refresh: bool)` and `refresh_session()`.
- A fetch transport that uses this boundary for initial session creation and one retry after 401/403.
- Connector `safe_meta` that reports only sanitized facts such as refresh attempted, refresh source,
  retry count, and last stage.
- Tests that mock auth/session/browser behavior directly.

This approach avoids rewriting a working Garmin flow and makes the Phase 2 guarantee testable.

## Credential And Secret Policy

The supported headless login credential source is:

```text
.garmin_tokens/garmin_login.json
```

Expected keys are `email` and `password`. The file stays local, is never committed, and is only read by
the Playwright minting path. The connector and API may report that Playwright or browser-cookie refresh
was used, but must never expose:

- cookie values
- CSRF values
- passwords
- OAuth or session tokens
- `Authorization` headers
- `.garmin_tokens`
- `/home/...`, `/Users/...`, or Windows user-profile paths

## Architecture

### Auth Boundary

Add a small connector-local wrapper around existing `garmin_auth` behavior:

```python
class GarminCnAuthProvider:
    def make_session(self, *, force_refresh_auth: bool) -> requests.Session
    def refresh_session(self, session: requests.Session) -> bool
```

Default implementation delegates to existing `fetch.make_session()` and `fetch.refresh_session_auth()`
inside `_fetch_runtime(root)`, so root-specific `.garmin_tokens` and `data/` paths keep working.

Tests can inject a fake provider to drive:

- cached auth succeeds
- forced refresh succeeds
- first request 401/403, refresh succeeds, retry succeeds
- refresh fails, connector returns `reauth_required`
- secret-bearing exception messages are sanitized

### Fetch Transport

Keep `GarminCnFetchTransport.run()` as the connector entrypoint, but make retry behavior explicit and
testable. The transport should track stage metadata:

- `lastStage`
- `forceRefreshAuth`
- `authRefreshAttempted`
- `authRefreshSucceeded`
- `authRetryCount`

Only sanitized stage names and booleans/counts may enter `safe_meta`.

The legacy fetch functions can remain as implementation helpers. If a direct call to `fetch.py` is used,
its current `--refresh-auth` behavior stays intact.

### Connector And API

`GarminCnWebSessionConnector.sync()` remains the product sync contract:

```python
sync(with_shots=True, force_refresh_auth=False, ensure_geometry=False)
```

Rules:

- `force_refresh_auth=True` forces the auth provider to refresh before fetching.
- A recoverable 401/403 refresh retry that succeeds returns `state="ready"`.
- A refresh failure returns `state="reauth_required"` and `error_code="auth_failed"`.
- Non-auth failures return `state="error"` and `error_code="sync_failed"`.
- Last successful durable snapshot remains available when a later run becomes `reauth_required`.

`/api/v2/sync/garmin?force_refresh_auth=true` and `python -m ai_caddie.pipeline --shots --refresh-auth`
are the supported cron-compatible trigger forms.

### Sync Status

`/api/v2/sync/status` already preserves last successful snapshot metadata when the current connector
state is `reauth_required`. Phase 2 will keep that behavior and may add safe last-run details only if
needed. The status payload must continue to use:

- `connector.state`
- `connector.reauthRequired`
- `connector.nextAction`
- `lastRun.state`
- `lastRun.errorCode`
- snapshot counts and last successful snapshot metadata

## Error Handling

- Missing `.garmin_tokens/garmin_login.json`, Playwright failures, browser-cookie failures, and repeated
  401/403 after retry all become `reauth_required` when they prevent sync.
- The connector detail uses a generic user-facing message.
- Raw exception text is only surfaced after `sanitize_secret_text()`.
- A retry loop is bounded to one refresh retry per failed request stage.

## Testing

Add or extend targeted unittest coverage:

- `tests/test_garmin_cn_connector.py`
  - connector passes `force_refresh_auth=True` into the auth/session boundary.
  - 401/403 refresh retry succeeds and returns `ready`.
  - refresh failure returns `reauth_required` without writing a ready snapshot.
  - `safe_meta` and status are secret-free.
- `tests/test_garmin_playwright_login.py`
  - existing fake Playwright tests remain CI-only and do not launch a browser.
  - forced Playwright path does not touch browser-cookie loaders.
- `tests/test_server_v2_sync_run.py`
  - endpoint passes `force_refresh_auth=true` to the connector.
  - response redacts secret-bearing connector details and safe metadata.
- `tests/test_pipeline.py`
  - CLI/pipeline passes `force_refresh=True` into `_ensure_auth`.
  - cron command behavior is documented and covered at function level.

Verification command:

```bash
uv run python -m unittest tests.test_garmin_cn_connector tests.test_garmin_playwright_login tests.test_server_v2_sync_run tests.test_pipeline tests.test_server_v2_sync_status -v
git diff --check
```

## Documentation

Update the roadmap/test execution docs after implementation:

- Check the Phase 2 items that are actually completed.
- Record the targeted test commands and results.
- Document the recommended cron-safe command:

```bash
AI_CADDIE_AUTH_REFRESH=playwright uv run python -m ai_caddie.pipeline --shots --refresh-auth --geometry-limit 50
```

The command is local/private only and must not be added to CI.

## Acceptance Criteria

- Phase 2 headless auth refresh and fetch automation are covered by mock tests.
- The connector can force auth refresh and can recover once from 401/403.
- Status/API responses remain secret-free.
- The documented cron-compatible command exists and maps to tested code paths.
- Existing manual session import and local snapshot usability remain intact.
