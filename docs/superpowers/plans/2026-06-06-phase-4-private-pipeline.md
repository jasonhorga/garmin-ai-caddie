# Phase 4 End-To-End Private Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one local private command run auth refresh, Garmin fetch, missing geometry sync, course-reference ingest, and safe coverage reporting.

**Architecture:** Keep `ai_caddie.pipeline` as the command boundary and keep network-heavy pieces behind patchable functions. Add safe coverage fields to `SyncResult`, expose sync/course-reference/geometry freshness in readiness, and add a local-only smoke script that uses FastAPI `TestClient` against `AI_CADDIE_DATA_MODE=local` without logging private data.

**Tech Stack:** Python 3.12, unittest, FastAPI TestClient, uv, JSON evidence files.

---

## File Structure

- Modify `ai_caddie/pipeline.py`: enrich `SyncResult`, tolerate course-reference coverage failures, and print safe JSON.
- Modify `tests/test_pipeline.py`: cover run order, geometry-limit propagation, course-reference coverage, and degraded course-reference failure behavior.
- Modify `server_v2/readiness.py`: enrich the `sync` readiness evidence with freshness and coverage fields.
- Modify `tests/test_server_v2_readiness.py`: assert sync freshness, shot counts, geometry coverage, course-reference coverage, and redaction.
- Create `ops/smoke_local_private_data.py`: local-only real-data endpoint smoke with sanitized evidence JSON.
- Modify `tests/test_local_private_smoke.py`: test smoke evidence building with a fake client and redaction guard.
- Modify `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`: check completed Phase 4 items after verification.
- Create `docs/superpowers/reviews/2026-06-06-phase-4-private-pipeline.md`: record verification evidence.

## Task 1: Pipeline Result Coverage Contract

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `ai_caddie/pipeline.py`

- [ ] **Step 1: Write failing pipeline coverage tests**

Add these tests to `PipelineSyncTests`:

```python
def test_sync_reports_geometry_and_course_reference_coverage(self) -> None:
    coverage = {
        "schema": "ai-caddie-course-reference-coverage-v1",
        "total": 4,
        "ready": 3,
        "missing": 1,
        "pct": 75.0,
    }
    with patch.object(pipeline, "_ensure_auth", return_value=True), \
            patch.object(pipeline, "_fetch_history", return_value=12), \
            patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 2, "downloaded": 1, "failed": 1}) as geo, \
            patch.object(pipeline.course_reference, "build_played_store", return_value={1: object(), 2: object()}), \
            patch.object(pipeline.course_reference, "course_reference_coverage", return_value=coverage), \
            patch.object(pipeline, "_on_disk", return_value=(12, 9)):
        result = pipeline.sync(with_shots=True, geometry_limit=50)

    geo.assert_called_once_with(limit=50)
    self.assertTrue(result.auth_ok)
    self.assertEqual(result.geometry_attempted, 2)
    self.assertEqual(result.geometry_failed, 1)
    self.assertEqual(result.course_reference_total, 4)
    self.assertEqual(result.course_reference_ready, 3)
    self.assertEqual(result.course_reference_missing, 1)
    self.assertEqual(result.course_reference_coverage_pct, 75.0)
    self.assertTrue(any("1 hole(s) missing geometry" in note for note in result.notes))


def test_sync_reports_course_reference_failure_as_degraded_note(self) -> None:
    with patch.object(pipeline, "_ensure_auth", return_value=True), \
            patch.object(pipeline, "_fetch_history", return_value=3), \
            patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0, "failed": 0}), \
            patch.object(pipeline.course_reference, "build_played_store", side_effect=RuntimeError("course ref failed")), \
            patch.object(pipeline, "_on_disk", return_value=(3, 0)):
        result = pipeline.sync(with_shots=False)

    self.assertTrue(result.auth_ok)
    self.assertEqual(result.course_nines, 0)
    self.assertEqual(result.course_reference_total, 0)
    self.assertTrue(any("course-reference ingest failed" in note for note in result.notes))
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_pipeline -v
```

Expected: failures because `SyncResult` lacks coverage fields and course-reference exceptions still break sync.

- [ ] **Step 3: Extend `SyncResult` and sync behavior**

In `ai_caddie/pipeline.py`, extend `SyncResult`:

```python
    geometry_attempted: int = 0
    geometry_failed: int = 0
    course_reference_total: int = 0
    course_reference_ready: int = 0
    course_reference_missing: int = 0
    course_reference_coverage_pct: float = 0.0
```

In `sync()`, replace direct course-reference ingest with:

```python
    course_nines = 0
    course_reference_total = 0
    course_reference_ready = 0
    course_reference_missing = 0
    course_reference_coverage_pct = 0.0
    try:
        store = course_reference.build_played_store()
        course_nines = len(store)
        coverage = course_reference.course_reference_coverage()
        course_reference_total = int(coverage.get("total") or 0)
        course_reference_ready = int(coverage.get("ready") or 0)
        course_reference_missing = int(coverage.get("missing") or 0)
        course_reference_coverage_pct = float(coverage.get("pct") or 0.0)
    except Exception:
        notes.append("course-reference ingest failed (will retry on next sync)")
```

Make sure `notes` is initialized before the try block. Return:

```python
        course_nines=course_nines,
        geometry_attempted=int(geometry.get("attempted") or 0),
        geometry_failed=int(geometry.get("failed") or 0),
        course_reference_total=course_reference_total,
        course_reference_ready=course_reference_ready,
        course_reference_missing=course_reference_missing,
        course_reference_coverage_pct=course_reference_coverage_pct,
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run python -m unittest tests.test_pipeline -v
git diff --check
```

Expected: pipeline tests pass and diff check exits 0.

Commit:

```bash
git add ai_caddie/pipeline.py tests/test_pipeline.py
git commit -m "test: report private pipeline coverage"
```

## Task 2: Readiness Sync Freshness And Coverage Evidence

**Files:**
- Modify: `tests/test_server_v2_readiness.py`
- Modify: `server_v2/readiness.py`

- [ ] **Step 1: Write failing readiness tests**

Add this test to `ServerV2ReadinessTests`:

```python
def test_readiness_sync_evidence_includes_freshness_and_coverage(self) -> None:
    class Snapshot:
        scorecardCount = 12
        shotFileCount = 9
        lastSuccessfulSyncAt = "2026-06-06T10:00:00Z"
        geometryDependencyCount = 10
        geometryReadyCount = 7
        geometryMissingCount = 3

    class Connector:
        name = "garmin_cn_web_session"
        state = "ready"

    class LastRun:
        state = "ready"
        errorCode = None
        updatedAt = "2026-06-06T10:01:00Z"

    class Sync:
        connector = Connector()
        snapshot = Snapshot()
        lastRun = LastRun()

    with patch("server_v2.readiness.load_sync_status_response", return_value=Sync()), \
            patch("server_v2.readiness.course_reference_coverage", return_value={
                "schema": "ai-caddie-course-reference-coverage-v1",
                "total": 4,
                "ready": 3,
                "missing": 1,
                "pct": 75.0,
                "missingGlobalIds": [31936],
            }):
        response = TestClient(app).get("/api/v2/readiness")

    checks = {row["label"]: row for row in response.json()["checks"]}
    sync_evidence = checks["sync"]["evidence"]
    self.assertEqual(sync_evidence["lastSuccessfulSyncAt"], "2026-06-06T10:00:00Z")
    self.assertEqual(sync_evidence["lastRunState"], "ready")
    self.assertIsNone(sync_evidence["lastRunErrorCode"])
    self.assertIn("lastRunAgeHours", sync_evidence)
    self.assertIn("dataFreshness", sync_evidence)
    self.assertEqual(sync_evidence["dataFreshness"]["lastSuccessfulSyncAt"], "2026-06-06T10:00:00Z")
    self.assertIn("normalizedShotCount", sync_evidence)
    self.assertEqual(sync_evidence["geometryCoverage"], {"ready": 7, "total": 10, "missing": 3, "pct": 70.0})
    self.assertEqual(sync_evidence["shotCoverage"], {"scorecards": 12, "shotFiles": 9})
    self.assertEqual(checks["course_reference"]["evidence"]["pct"], 75.0)
    self.assertNotIn("cookie", str(response.json()).lower())
    self.assertNotIn("/home/", str(response.json()).lower())
```

- [ ] **Step 2: Run readiness tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_server_v2_readiness -v
```

Expected: failure because sync readiness evidence does not include freshness, last run, shot coverage, or geometry coverage.

- [ ] **Step 3: Enrich sync readiness evidence**

Add helper in `server_v2/readiness.py`:

```python
def _coverage(ready: int, total: int, *, missing: int = 0) -> dict[str, Any]:
    return {
        "ready": ready,
        "total": total,
        "missing": missing,
        "pct": round(ready * 100.0 / total, 1) if total else 0.0,
    }


def _age_hours(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return round((datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds() / 3600.0, 2)


def _summary_int(stats: Any, key: str) -> int | None:
    summary = getattr(stats, "summary", None)
    if not isinstance(summary, dict):
        return None
    try:
        return int(summary.get(key))
    except (TypeError, ValueError):
        return None
```

In the sync check evidence inside `build_readiness_response()`, add:

```python
                    "lastSuccessfulSyncAt": sync.snapshot.lastSuccessfulSyncAt,
                    "lastRunState": sync.lastRun.state if sync.lastRun else None,
                    "lastRunErrorCode": sync.lastRun.errorCode if sync.lastRun else None,
                    "lastRunUpdatedAt": sync.lastRun.updatedAt if sync.lastRun else None,
                    "lastRunAgeHours": _age_hours(sync.lastRun.updatedAt if sync.lastRun else None),
                    "normalizedShotCount": _summary_int(stats, "shotCount"),
                    "dataFreshness": {
                        "lastSuccessfulSyncAt": sync.snapshot.lastSuccessfulSyncAt,
                        "lastRunUpdatedAt": sync.lastRun.updatedAt if sync.lastRun else None,
                    },
                    "shotCoverage": {
                        "scorecards": sync.snapshot.scorecardCount,
                        "shotFiles": sync.snapshot.shotFileCount,
                    },
                    "geometryCoverage": _coverage(
                        sync.snapshot.geometryReadyCount,
                        sync.snapshot.geometryDependencyCount,
                        missing=sync.snapshot.geometryMissingCount,
                    ),
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run python -m unittest tests.test_server_v2_readiness -v
git diff --check
```

Expected: readiness tests pass and diff check exits 0.

Commit:

```bash
git add server_v2/readiness.py tests/test_server_v2_readiness.py
git commit -m "test: expose private pipeline readiness coverage"
```

## Task 3: Local Real-Data Smoke Evidence

**Files:**
- Create: `ops/smoke_local_private_data.py`
- Create: `tests/test_local_private_smoke.py`

- [ ] **Step 1: Write failing smoke tests**

Create `tests/test_local_private_smoke.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ops.smoke_local_private_data import build_smoke_evidence, assert_secret_free


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict[str, object]:
        return self._payload


class FakeClient:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def get(self, path: str) -> FakeResponse:
        self.paths.append(path)
        if path == "/api/v2/history/rounds":
            return FakeResponse({"schema": "rounds", "rounds": [{"id": "round-1"}]})
        if path == "/api/v2/history/rounds/round-1":
            return FakeResponse({"schema": "detail", "holeDetails": []})
        return FakeResponse({"schema": path.strip("/").replace("/", "-"), "count": 1})


class LocalPrivateSmokeTests(unittest.TestCase):
    def test_build_smoke_evidence_checks_local_history_endpoints(self) -> None:
        client = FakeClient()
        evidence = build_smoke_evidence(client, base_url="testclient")

        self.assertEqual(evidence["schema"], "ai-caddie-local-private-smoke-evidence-v1")
        self.assertEqual(evidence["dataMode"], "local")
        self.assertIn("GET /api/v2/health", evidence["checks"])
        self.assertIn("GET /api/v2/history/rounds/round-1", evidence["checks"])
        self.assertEqual(evidence["roundDetailChecked"], True)
        self.assertIn("/api/v2/sync/status", client.paths)

    def test_assert_secret_free_rejects_private_terms(self) -> None:
        with self.assertRaises(AssertionError):
            assert_secret_free({"path": "/home/private/.garmin_tokens/token.json"})

    def test_main_writes_evidence_file(self) -> None:
        from ops import smoke_local_private_data as smoke

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "smoke.json"
            client = FakeClient()
            smoke.write_smoke_evidence(client=client, output=output, base_url="testclient")
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], "ai-caddie-local-private-smoke-evidence-v1")
        self.assertNotIn("/home/", json.dumps(payload).lower())
```

- [ ] **Step 2: Run smoke tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_local_private_smoke -v
```

Expected: failure because `ops/smoke_local_private_data.py` does not exist.

- [ ] **Step 3: Implement local smoke script**

Create `ops/smoke_local_private_data.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

FORBIDDEN_TERMS = (
    "cookie",
    "csrf",
    "connect-csrf-token",
    "access_token",
    "refresh_token",
    "password",
    "authorization",
    "/home/",
    "/users/",
    ".garmin_tokens",
    ".env",
)

DEFAULT_OUTPUT = Path("logs/local_private_smoke_latest.json")


def assert_secret_free(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    for term in FORBIDDEN_TERMS:
        if term in text:
            raise AssertionError(f"secret-like term leaked: {term}")


def _get_json(client: Any, path: str) -> dict[str, Any]:
    response = client.get(path)
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned HTTP {response.status_code}")
    payload = response.json()
    assert_secret_free(payload)
    return payload


def build_smoke_evidence(client: Any, *, base_url: str) -> dict[str, Any]:
    checks: list[str] = []
    endpoints = [
        "/api/v2/health",
        "/api/v2/readiness",
        "/api/v2/history/overview",
        "/api/v2/history/rounds",
        "/api/v2/history/stats",
        "/api/v2/sync/status",
    ]
    payloads: dict[str, dict[str, Any]] = {}
    for path in endpoints:
        payloads[path] = _get_json(client, path)
        checks.append(f"GET {path}")
    round_detail_checked = False
    rounds = payloads["/api/v2/history/rounds"].get("rounds")
    if isinstance(rounds, list) and rounds:
        round_id = str((rounds[0] or {}).get("id") or "").strip()
        if round_id:
            path = f"/api/v2/history/rounds/{round_id}"
            _get_json(client, path)
            checks.append(f"GET {path}")
            round_detail_checked = True
    evidence = {
        "schema": "ai-caddie-local-private-smoke-evidence-v1",
        "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "baseUrl": base_url,
        "dataMode": "local",
        "checks": checks,
        "roundDetailChecked": round_detail_checked,
        "endpointCount": len(checks),
    }
    assert_secret_free(evidence)
    return evidence


def write_smoke_evidence(*, client: Any, output: Path = DEFAULT_OUTPUT, base_url: str = "testclient") -> dict[str, Any]:
    evidence = build_smoke_evidence(client, base_url=base_url)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    os.environ["AI_CADDIE_DATA_MODE"] = "local"
    from fastapi.testclient import TestClient
    from server_v2.main import app

    output = Path(os.environ.get("AI_CADDIE_LOCAL_SMOKE_EVIDENCE", str(DEFAULT_OUTPUT)))
    write_smoke_evidence(client=TestClient(app), output=output, base_url="testclient")
    print(f"local private smoke ok: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run smoke tests and commit**

Run:

```bash
uv run python -m unittest tests.test_local_private_smoke -v
git diff --check
```

Expected: local smoke tests pass and diff check exits 0.

Commit:

```bash
git add ops/smoke_local_private_data.py tests/test_local_private_smoke.py
git commit -m "test: add local private data smoke evidence"
```

## Task 4: Phase 4 Documentation, Verification, And Push

**Files:**
- Modify: `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
- Create: `docs/superpowers/reviews/2026-06-06-phase-4-private-pipeline.md`

- [ ] **Step 1: Run full Phase 4 verification**

Run:

```bash
uv run python -m unittest tests.test_pipeline tests.test_server_v2_readiness tests.test_server_v2_sync_status tests.test_local_private_smoke -v
git diff --check
```

Expected: all listed tests pass and diff check exits 0.

- [ ] **Step 2: Check Phase 4 roadmap items**

In `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`, change Phase 4 items to:

```markdown
- [x] Wire auth refresh -> fetch history/shots -> geometry sync -> course-reference ingest.
- [x] Add readiness fields for last sync, session age, data freshness, shot coverage, geometry coverage, and course-ref coverage.
- [x] Add a local private smoke that runs against real data without logging secrets.
```

- [ ] **Step 3: Record evidence**

Create `docs/superpowers/reviews/2026-06-06-phase-4-private-pipeline.md`:

```markdown
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

Result: PASS.

```bash
git diff --check
```

Result: PASS.
```

- [ ] **Step 4: Commit docs and push**

Run:

```bash
git add docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md docs/superpowers/reviews/2026-06-06-phase-4-private-pipeline.md
git commit -m "docs: record phase 4 private pipeline completion"
git push origin integration/v2
```

## Self-Review

- Spec coverage: the plan covers the single pipeline command, bounded geometry sync, course-reference ingest, readiness freshness/session age/coverage, auth failure short-circuit preservation, local-only smoke evidence, and redaction.
- Placeholder scan: no deferred implementation instructions are present; every task names files, code, commands, and expected results.
- Type consistency: `SyncResult.geometry_attempted`, `geometry_failed`, `course_reference_total`, `course_reference_ready`, `course_reference_missing`, `course_reference_coverage_pct`, readiness `geometryCoverage`, and local smoke schema names are used consistently.
