# Phase 2 Auth Refresh And Fetch Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Garmin CN auth refresh and fetch automation a tested connector-level product contract.

**Architecture:** Keep the existing Garmin CN web-session mechanics in `fetch.py` and `garmin_auth.py`, but add an injectable auth-provider boundary inside `ai_caddie/connectors/garmin_cn.py`. The connector transport owns one explicit auth-refresh retry per failed fetch stage, status/API exposure owns redaction, and the pipeline CLI passes refresh intent through deterministic function boundaries.

**Tech Stack:** Python 3.12, unittest, FastAPI TestClient, uv, requests-compatible session doubles.

---

## File Structure

- Modify `ai_caddie/connectors/garmin_cn.py`: add `GarminCnAuthProvider`, auth-failure detection, explicit refresh retry metadata, and a public `sanitize_safe_meta()`.
- Modify `ai_caddie/connectors/redaction.py`: redact credential directory names and local private paths in addition to secret terms.
- Modify `server_v2/main.py`: sanitize `safeMeta` before returning mocked or real connector output.
- Modify `ai_caddie/pipeline.py`: pass refresh intent from `sync()` into the fetch session path.
- Modify `tests/test_garmin_cn_connector.py`: cover auth provider injection, force refresh, 401/403 retry, refresh failure, and local-path redaction.
- Modify `tests/test_server_v2_sync_run.py`: cover `force_refresh_auth=true` and API `safeMeta` redaction.
- Modify `tests/test_pipeline.py`: cover cron-compatible CLI/function refresh behavior.
- Modify `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`: check Phase 2 roadmap items after implementation passes.
- Create `docs/superpowers/reviews/2026-06-06-phase-2-auth-refresh-fetch-automation.md`: record targeted test evidence.

## Task 1: Connector Auth Boundary And Retry Contract

**Files:**
- Modify: `tests/test_garmin_cn_connector.py`
- Modify: `ai_caddie/connectors/garmin_cn.py`
- Modify: `ai_caddie/connectors/redaction.py`

- [ ] **Step 1: Write failing connector tests**

Add these imports near the top of `tests/test_garmin_cn_connector.py`:

```python
from requests import HTTPError

from ai_caddie.connectors.garmin_cn import GarminCnFetchTransport, GarminCnWebSessionConnector
```

Extend `SECRET_TERMS` so the test helper rejects all Phase 2 leak classes:

```python
SECRET_TERMS = ("cookie", "csrf", "token", "secret", "authorization", "password", ".garmin_tokens", "/home/", "/users/")
```

Add these helpers above `GarminCnConnectorTests`:

```python
class AuthFailureResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def auth_http_error(status_code: int = 401) -> HTTPError:
    return HTTPError(f"{status_code} auth failed cookie abc csrf def token ghi /home/private/.garmin_tokens", response=AuthFailureResponse(status_code))


class FakeAuthProvider:
    def __init__(self, *, refresh_result: bool = True) -> None:
        self.session = Mock()
        self.make_calls: list[bool] = []
        self.refresh_calls = 0
        self.refresh_result = refresh_result

    def make_session(self, *, force_refresh_auth: bool):
        self.make_calls.append(force_refresh_auth)
        return self.session

    def refresh_session(self, session):
        self.refresh_calls += 1
        self.refreshed_session = session
        return self.refresh_result
```

Add these test methods to `GarminCnConnectorTests`:

```python
def test_transport_uses_injected_auth_provider_and_force_refresh_metadata(self) -> None:
    provider = FakeAuthProvider()
    transport = GarminCnFetchTransport(auth_provider=provider)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with (
            patch("fetch.fetch_summary", return_value=[]),
            patch("fetch.fetch_details") as details,
        ):
            run = transport.run(root=root, with_shots=False, force_refresh_auth=True)

    self.assertEqual(provider.make_calls, [True])
    self.assertEqual(provider.refresh_calls, 0)
    self.assertEqual(run.cards, [])
    self.assertEqual(run.safe_meta["forceRefreshAuth"], True)
    self.assertFalse(run.safe_meta["authRefreshAttempted"])
    self.assertFalse(run.safe_meta["authRefreshSucceeded"])
    self.assertEqual(run.safe_meta["authRetryCount"], 0)
    self.assertEqual(run.safe_meta["lastStage"], "fetch_details")
    details.assert_called_once_with(provider.session, [], with_shots=False)
    assert_secret_free(self, run.safe_meta)


def test_transport_retries_summary_once_after_auth_failure(self) -> None:
    provider = FakeAuthProvider(refresh_result=True)
    transport = GarminCnFetchTransport(auth_provider=provider)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with (
            patch("fetch.fetch_summary", side_effect=[auth_http_error(401), [{"id": 1}]]) as summary,
            patch("fetch.fetch_details") as details,
        ):
            run = transport.run(root=root, with_shots=True, force_refresh_auth=False)

    self.assertEqual(summary.call_count, 2)
    details.assert_called_once_with(provider.session, [{"id": 1}], with_shots=True)
    self.assertEqual(provider.refresh_calls, 1)
    self.assertTrue(run.safe_meta["authRefreshAttempted"])
    self.assertTrue(run.safe_meta["authRefreshSucceeded"])
    self.assertEqual(run.safe_meta["authRetryCount"], 1)
    self.assertEqual(run.safe_meta["lastStage"], "fetch_details")
    assert_secret_free(self, run.safe_meta)


def test_transport_retries_details_once_after_auth_failure(self) -> None:
    provider = FakeAuthProvider(refresh_result=True)
    transport = GarminCnFetchTransport(auth_provider=provider)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with (
            patch("fetch.fetch_summary", return_value=[{"id": 1}]),
            patch("fetch.fetch_details", side_effect=[auth_http_error(403), None]) as details,
        ):
            run = transport.run(root=root, with_shots=True, force_refresh_auth=False)

    self.assertEqual(details.call_count, 2)
    self.assertEqual(provider.refresh_calls, 1)
    self.assertTrue(run.safe_meta["authRefreshAttempted"])
    self.assertTrue(run.safe_meta["authRefreshSucceeded"])
    self.assertEqual(run.safe_meta["authRetryCount"], 1)
    self.assertEqual(run.safe_meta["lastStage"], "fetch_details")
    assert_secret_free(self, run.safe_meta)


def test_sync_refresh_failure_returns_reauth_required_with_retry_metadata(self) -> None:
    provider = FakeAuthProvider(refresh_result=False)
    transport = GarminCnFetchTransport(auth_provider=provider)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        connector = GarminCnWebSessionConnector(root=root, transport=transport)
        with patch("fetch.fetch_summary", side_effect=auth_http_error(401)):
            result = connector.sync(with_shots=False, force_refresh_auth=False)

        self.assertEqual(result.state, "reauth_required")
        self.assertEqual(result.error_code, "auth_failed")
        self.assertIsNone(result.snapshot)
        self.assertTrue(result.safe_meta["authRefreshAttempted"])
        self.assertFalse(result.safe_meta["authRefreshSucceeded"])
        self.assertEqual(result.safe_meta["authRetryCount"], 0)
        self.assertEqual(result.safe_meta["lastStage"], "fetch_summary")
        self.assertFalse((root / "data" / "snapshots").exists())
        assert_secret_free(self, result.safe_meta)
```

- [ ] **Step 2: Run connector tests and verify they fail for missing implementation**

Run:

```bash
uv run python -m unittest tests.test_garmin_cn_connector -v
```

Expected: failure mentioning `GarminCnFetchTransport.__init__()` does not accept `auth_provider`, missing retry metadata, or `cookie`/path terms leaking.

- [ ] **Step 3: Add redaction for local private paths**

In `ai_caddie/connectors/redaction.py`, replace the pattern block with:

```python
SECRET_PATTERNS = [
    re.compile(r"\b(cookie\w*|csrf\w*|token\w*|secret\w*|authorization\w*|password\w*)\b[^,;\n]*", re.IGNORECASE),
    re.compile(r"(/home/[^,;\n\s]+|/Users/[^,;\n\s]+|[A-Za-z]:\\Users\\[^,;\n]+)", re.IGNORECASE),
]
```

Keep `sanitize_secret_text()` as the single redaction function:

```python
def sanitize_secret_text(message: object, *, limit: int = 240) -> str:
    text = str(message).replace(".garmin_tokens", "<credential-dir>")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text[:limit]
```

- [ ] **Step 4: Implement connector auth provider and retry metadata**

In `ai_caddie/connectors/garmin_cn.py`, stop importing fetch helpers directly except for the exception type:

```python
from fetch import GarminAuthExpired
```

Add these classes and helpers above `GarminCnFetchTransport`:

```python
class GarminCnTransportAuthError(GarminAuthExpired):
    def __init__(self, message: str, *, safe_meta: dict[str, Any]) -> None:
        super().__init__(message)
        self.safe_meta = safe_meta


class GarminCnAuthProvider:
    def make_session(self, *, force_refresh_auth: bool):
        return fetch_module.make_session(force_refresh_auth=force_refresh_auth)

    def refresh_session(self, session) -> bool:
        return fetch_module.refresh_session_auth(session)


def sanitize_safe_meta(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = str(key)
            if any(term in safe_key.lower() for term in SECRET_META_KEY_TERMS):
                safe_key = "redacted"
            sanitized[safe_key] = sanitize_safe_meta(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_safe_meta(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_safe_meta(item) for item in value]
    if isinstance(value, str):
        return sanitize_error(value)
    return value


def _is_auth_failure(exc: BaseException) -> bool:
    if isinstance(exc, GarminAuthExpired):
        return True
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code in (401, 403)
```

Keep `_sanitize_safe_meta = sanitize_safe_meta` for compatibility if existing code still calls the private name.

Update `GarminCnFetchTransport`:

```python
class GarminCnFetchTransport:
    """Secret-safe adapter around the legacy Garmin CN fetch.py workflow."""

    def __init__(self, *, auth_provider: GarminCnAuthProvider | None = None) -> None:
        self.auth_provider = auth_provider or GarminCnAuthProvider()

    def run(
        self,
        *,
        root: Path,
        with_shots: bool,
        force_refresh_auth: bool,
    ) -> GarminCnFetchRun:
        stdout_buffer = io.StringIO()
        safe_meta: dict[str, Any] = {
            "transport": "fetch_py_adapter",
            "forceRefreshAuth": force_refresh_auth,
            "authRefreshAttempted": False,
            "authRefreshSucceeded": False,
            "authRetryCount": 0,
            "lastStage": "make_session",
        }
        with _fetch_runtime(root), redirect_stdout(stdout_buffer):
            session = self.auth_provider.make_session(force_refresh_auth=force_refresh_auth)
            safe_meta["lastStage"] = "fetch_summary"
            cards = self._run_stage(lambda: fetch_module.fetch_summary(session), session=session, safe_meta=safe_meta)
            safe_meta["lastStage"] = "fetch_details"
            self._run_stage(lambda: fetch_module.fetch_details(session, cards, with_shots=with_shots), session=session, safe_meta=safe_meta)
        stdout_text = stdout_buffer.getvalue()
        line_count = len([line for line in stdout_text.splitlines() if line.strip()])
        safe_meta["stdoutCaptured"] = bool(stdout_text)
        safe_meta["stdoutLineCount"] = line_count
        return GarminCnFetchRun(cards=cards, safe_meta=sanitize_safe_meta(safe_meta))

    def _run_stage(self, operation, *, session, safe_meta: dict[str, Any]):
        try:
            return operation()
        except BaseException as exc:
            if not _is_auth_failure(exc):
                raise
            if safe_meta["authRefreshAttempted"]:
                raise GarminCnTransportAuthError(
                    "Garmin CN session still failed after one auth refresh retry.",
                    safe_meta=safe_meta,
                ) from exc
            safe_meta["authRefreshAttempted"] = True
            safe_meta["authRefreshSucceeded"] = bool(self.auth_provider.refresh_session(session))
            if not safe_meta["authRefreshSucceeded"]:
                raise GarminCnTransportAuthError(
                    "Garmin CN auth refresh failed during fetch.",
                    safe_meta=safe_meta,
                ) from exc
            safe_meta["authRetryCount"] = int(safe_meta["authRetryCount"]) + 1
            return operation()
```

In `GarminCnWebSessionConnector.sync()`, replace calls to `_sanitize_safe_meta(...)` with `sanitize_safe_meta(...)`. In the auth failure branch, merge transport metadata:

```python
safe_meta = {"sourceError": sanitize_error(exc)}
safe_meta.update(getattr(exc, "safe_meta", {}))
return ConnectorRunResult(
    connector="garmin_cn_web_session",
    state="reauth_required",
    detail=detail,
    error_code="auth_failed",
    safe_meta=sanitize_safe_meta(safe_meta),
)
```

Do the same public sanitizer replacement in the non-auth error branch.

- [ ] **Step 5: Update existing connector tests to patch `fetch.*`**

Change connector-test patches from module aliases to the legacy module names now used by the transport:

```python
patch("fetch.make_session", return_value=Mock())
patch("fetch.fetch_summary", return_value=[{"id": 1}])
patch("fetch.fetch_details")
```

When assertions check `result.safe_meta`, expect the new base keys to be present:

```python
self.assertEqual(result.safe_meta["transport"], "fetch_py_adapter")
self.assertFalse(result.safe_meta["authRefreshAttempted"])
self.assertEqual(result.safe_meta["authRetryCount"], 0)
```

- [ ] **Step 6: Run connector tests and commit**

Run:

```bash
uv run python -m unittest tests.test_garmin_cn_connector -v
git diff --check
```

Expected: all connector tests pass and diff check exits 0.

Commit:

```bash
git add ai_caddie/connectors/garmin_cn.py ai_caddie/connectors/redaction.py tests/test_garmin_cn_connector.py
git commit -m "test: cover garmin cn auth refresh retry"
```

## Task 2: Sync API Force Refresh And Safe Metadata Redaction

**Files:**
- Modify: `tests/test_server_v2_sync_run.py`
- Modify: `server_v2/main.py`

- [ ] **Step 1: Write failing server API tests**

Add these test methods to `ServerV2SyncRunTests`:

```python
def test_sync_garmin_endpoint_passes_force_refresh_auth_query(self) -> None:
    connector = Mock()
    connector.sync.return_value = ConnectorRunResult(
        connector="garmin_cn_web_session",
        state="no_data",
        detail="Garmin sync completed, but no scorecards were returned.",
        safe_meta={"forceRefreshAuth": True},
    )

    with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
        response = TestClient(app).post("/api/v2/sync/garmin?force_refresh_auth=true&with_shots=false")
        payload = response.json()

    self.assertEqual(response.status_code, 200)
    self.assertEqual(payload["safeMeta"]["forceRefreshAuth"], True)
    connector.sync.assert_called_once_with(with_shots=False, force_refresh_auth=True, ensure_geometry=False)


def test_sync_garmin_endpoint_redacts_secret_terms_from_safe_meta(self) -> None:
    connector = Mock()
    connector.sync.return_value = ConnectorRunResult(
        connector="garmin_cn_web_session",
        state="error",
        detail="Failed with token abc cookie xyz csrf q secret s authorization bearer",
        error_code="sync_failed",
        safe_meta={
            "cookie": "SESSIONID=abc",
            "nested": {"csrf": "csrf-value", "path": "/home/private/.garmin_tokens/garmin_login.json"},
            "authorizationHeader": "bearer abc",
        },
    )

    with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
        response = TestClient(app).post("/api/v2/sync/garmin")
        payload = response.json()

    self.assertEqual(response.status_code, 500)
    text = str(payload).lower()
    for term in ("cookie", "csrf", "token", "secret", "authorization", ".garmin_tokens", "/home/"):
        self.assertNotIn(term, text)
```

- [ ] **Step 2: Run server tests and verify the safe-meta test fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_run -v
```

Expected: force-refresh query test may already pass; safe-meta redaction fails because `server_v2/main.py` returns mocked `safe_meta` directly.

- [ ] **Step 3: Sanitize API safe metadata**

In `server_v2/main.py`, update the connector import:

```python
from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector, sanitize_error, sanitize_safe_meta
```

Update the response construction in `sync_garmin()`:

```python
safeMeta=sanitize_safe_meta(result.safe_meta),
```

- [ ] **Step 4: Run server tests and commit**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_run -v
git diff --check
```

Expected: all server sync-run tests pass and diff check exits 0.

Commit:

```bash
git add server_v2/main.py tests/test_server_v2_sync_run.py
git commit -m "test: redact garmin sync api metadata"
```

## Task 3: Pipeline Cron Refresh Contract

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `ai_caddie/pipeline.py`

- [ ] **Step 1: Write failing pipeline tests**

In `PipelineSyncTests`, update existing `_fetch_history` assertions to include the new keyword:

```python
fetch_history.assert_called_once_with(False, force_refresh_auth=False)
```

and:

```python
fetch_history.assert_called_once_with(True, force_refresh_auth=False)
```

Add this test:

```python
def test_sync_passes_force_refresh_into_auth_and_fetch_session(self) -> None:
    with patch.object(pipeline, "_ensure_auth", return_value=True) as ensure_auth, \
            patch.object(pipeline, "_fetch_history", return_value=10) as fetch_history, \
            patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}) as geo, \
            patch.object(pipeline.course_reference, "build_played_store", return_value={}), \
            patch.object(pipeline, "_on_disk", return_value=(10, 10)):
        result = pipeline.sync(with_shots=True, force_refresh=True, geometry_limit=50)

    self.assertTrue(result.auth_ok)
    ensure_auth.assert_called_once_with(True)
    fetch_history.assert_called_once_with(True, force_refresh_auth=True)
    geo.assert_called_once_with(limit=50)
```

Add this direct `_fetch_history` test:

```python
def test_fetch_history_passes_force_refresh_auth_to_fetch_session(self) -> None:
    session = object()
    with patch("fetch.make_session", return_value=session) as make_session, \
            patch("fetch.fetch_summary", return_value=[{"id": 1}]) as summary, \
            patch("fetch.fetch_details") as details:
        rounds = pipeline._fetch_history(True, force_refresh_auth=True)

    self.assertEqual(rounds, 1)
    make_session.assert_called_once_with(force_refresh_auth=True)
    summary.assert_called_once_with(session)
    details.assert_called_once_with(session, [{"id": 1}], with_shots=True)
```

Add this CLI parsing test:

```python
def test_main_parses_refresh_auth_shots_and_geometry_limit(self) -> None:
    with patch.object(pipeline, "sync", return_value=pipeline.SyncResult(auth_ok=True, rounds=1)) as sync_call:
        code = pipeline.main(["--shots", "--refresh-auth", "--geometry-limit", "50"])

    self.assertEqual(code, 0)
    sync_call.assert_called_once_with(with_shots=True, force_refresh=True, geometry_limit=50)
```

- [ ] **Step 2: Run pipeline tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_pipeline -v
```

Expected: failures show `_fetch_history()` does not accept `force_refresh_auth` or existing mocks were called without the keyword.

- [ ] **Step 3: Implement refresh pass-through**

In `ai_caddie/pipeline.py`, update `_fetch_history()`:

```python
def _fetch_history(with_shots: bool, *, force_refresh_auth: bool = False) -> int:
    """Fetch summary + details (+ shots). Returns the number of rounds in the summary."""
    import fetch

    session = fetch.make_session(force_refresh_auth=force_refresh_auth)
    cards = fetch.fetch_summary(session)
    fetch.fetch_details(session, cards, with_shots=with_shots)
    return len(cards)
```

Update `sync()`:

```python
rounds = _fetch_history(with_shots, force_refresh_auth=force_refresh)
```

- [ ] **Step 4: Run pipeline tests and commit**

Run:

```bash
uv run python -m unittest tests.test_pipeline -v
git diff --check
```

Expected: all pipeline tests pass and diff check exits 0.

Commit:

```bash
git add ai_caddie/pipeline.py tests/test_pipeline.py
git commit -m "test: cover pipeline auth refresh command"
```

## Task 4: Phase 2 Documentation And Test Evidence

**Files:**
- Modify: `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
- Create: `docs/superpowers/reviews/2026-06-06-phase-2-auth-refresh-fetch-automation.md`

- [ ] **Step 1: Run the full Phase 2 target verification**

Run:

```bash
uv run python -m unittest tests.test_garmin_cn_connector tests.test_garmin_playwright_login tests.test_server_v2_sync_run tests.test_pipeline tests.test_server_v2_sync_status -v
git diff --check
```

Expected: all listed unittest modules pass and diff check exits 0.

- [ ] **Step 2: Check Phase 2 roadmap items**

In `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`, change Phase 2 checkboxes to:

```markdown
- [x] Productize headless Garmin CN login into connector code.
- [x] On 401, refresh web cookie/csrf and retry once.
- [x] Add `--refresh-auth` and cron-compatible trigger.
- [x] Mock browser/auth tests assert no cookie, csrf, password, or local private path leaks.
```

- [ ] **Step 3: Record implementation evidence**

Create `docs/superpowers/reviews/2026-06-06-phase-2-auth-refresh-fetch-automation.md`:

```markdown
# Phase 2 Auth Refresh And Fetch Automation Evidence

- Date: 2026-06-06
- Branch: `integration/v2`
- Commit range: Phase 2 implementation commits after `c832146`

## Scope

Implemented Phase 2 from `docs/superpowers/specs/2026-06-06-phase-2-auth-refresh-fetch-automation-design.md`.

## Evidence

- Connector auth provider boundary added in `ai_caddie/connectors/garmin_cn.py`.
- Connector transport performs one explicit refresh retry for 401/403 or `GarminAuthExpired` stages.
- `/api/v2/sync/garmin?force_refresh_auth=true` passes refresh intent into the connector.
- `ai_caddie.pipeline` passes `--refresh-auth` into auth and fetch session creation.
- Status/API/safe metadata redaction covers cookie, csrf, password, token, authorization, `.garmin_tokens`, and local private paths.
- Cached snapshots are not written on auth-refresh failure.

## Verification

```bash
uv run python -m unittest tests.test_garmin_cn_connector tests.test_garmin_playwright_login tests.test_server_v2_sync_run tests.test_pipeline tests.test_server_v2_sync_status -v
```

Result: PASS.

```bash
git diff --check
```

Result: PASS.
```

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md docs/superpowers/reviews/2026-06-06-phase-2-auth-refresh-fetch-automation.md
git commit -m "docs: record phase 2 auth refresh completion"
```

## Task 5: Phase 2 Final Verification And Push

**Files:**
- No new files unless verification reveals a defect.

- [ ] **Step 1: Run final Phase 2 verification**

Run:

```bash
uv run python -m unittest tests.test_garmin_cn_connector tests.test_garmin_playwright_login tests.test_server_v2_sync_run tests.test_pipeline tests.test_server_v2_sync_status -v
git diff --check
git status --short --branch
```

Expected:

```text
OK
```

for the unittest command, no output from `git diff --check`, and only known unrelated untracked entries remain:

```text
?? _data_aside
?? course_review/
?? docs/superpowers/reviews/2026-06-02-design-conformance-review.md
```

- [ ] **Step 2: Push Phase 2 commits**

Run:

```bash
git push origin integration/v2
```

Expected: remote `integration/v2` advances to the latest Phase 2 commit.

## Self-Review

- Spec coverage: the plan covers connector auth boundary, one retry on 401/403, cron-compatible `--refresh-auth`, API/status/safe-meta redaction, snapshot preservation on auth failure, mock-only browser/auth tests, and documentation evidence.
- Placeholder scan: no deferred implementation instructions are present; every task names concrete files, commands, and expected results.
- Type consistency: `GarminCnAuthProvider.make_session(force_refresh_auth=...)`, `GarminCnAuthProvider.refresh_session(session)`, `GarminCnFetchTransport(auth_provider=...)`, `sanitize_safe_meta()`, and `pipeline._fetch_history(with_shots, force_refresh_auth=...)` are used consistently across tests and implementation steps.
