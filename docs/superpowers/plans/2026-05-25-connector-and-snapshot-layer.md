# Connector And Snapshot Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing Garmin CN web-session fetch workflow in a typed connector that records secret-free sync status and versioned raw snapshot manifests.

**Architecture:** Keep `fetch.py` and `garmin_auth.py` as the low-level Garmin CN implementation. Add a connector layer under `ai_caddie/connectors/` that reports typed outcomes, writes a secret-free status file, and creates snapshot manifests from files in `data/`. FastAPI exposes a sync endpoint and status uses the persisted connector state without leaking cookies, CSRF tokens, OAuth tokens, or local secret paths.

**Tech Stack:** Python 3.12, dataclasses, FastAPI, unittest/TestClient, existing Garmin CN fetch/auth scripts.

---

## File Structure

Create:

- `ai_caddie/connectors/__init__.py`  
  Package marker and exported connector types.
- `ai_caddie/connectors/base.py`  
  Shared connector dataclasses and state names.
- `ai_caddie/connectors/snapshot.py`  
  Secret-free status file and snapshot manifest helpers.
- `ai_caddie/connectors/garmin_cn.py`  
  Garmin CN Web Session connector wrapper around existing fetch/auth code.
- `tests/test_connector_snapshot.py`  
  Tests manifest and persisted status behavior.
- `tests/test_garmin_cn_connector.py`  
  Tests connector success, reauth-required, and secret-redaction behavior.
- `tests/test_server_v2_sync_run.py`  
  Tests API sync endpoint without live network.

Modify:

- `server_v2/models.py`  
  Add sync-run response model.
- `server_v2/sync_status.py`  
  Read persisted connector status and snapshot manifest.
- `server_v2/main.py`  
  Add `POST /api/v2/sync/garmin`; allow POST in CORS.
- `tests/test_server_v2_sync_status.py`  
  Add persisted `reauth_required` status coverage.
- `tests/test_server_v2_health.py`  
  Add sync endpoint to service index coverage.

## Connector State Semantics

Use these states:

- `ready`: local Garmin snapshot data exists and no persisted error is active.
- `no_data`: no local scorecards have been synced.
- `reauth_required`: last sync attempt failed because Garmin auth/session was missing or expired.
- `error`: last sync attempt failed for a non-auth reason.

Persist only secret-free state to:

`data/sync/garmin_cn_status.json`

Persist snapshot manifests to:

`data/snapshots/{snapshot_id}.json`

Never write cookie, CSRF, OAuth token, Garmin password, Authorization header, or
`.garmin_tokens` path into either file.

## Task 1: Add Connector Base Types

**Files:**

- Create: `ai_caddie/connectors/__init__.py`
- Create: `ai_caddie/connectors/base.py`

- [ ] **Step 1: Create connector package and base types**

Create `ai_caddie/connectors/__init__.py`:

```python
from .base import ConnectorRunResult, ConnectorState, SnapshotManifest

__all__ = ["ConnectorRunResult", "ConnectorState", "SnapshotManifest"]
```

Create `ai_caddie/connectors/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ConnectorState = Literal["ready", "no_data", "reauth_required", "error"]


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_id: str
    scorecard_count: int
    shot_file_count: int
    summary_present: bool
    files: list[str]


@dataclass(frozen=True)
class ConnectorRunResult:
    connector: Literal["garmin_cn_web_session"]
    state: ConnectorState
    detail: str
    snapshot: SnapshotManifest | None = None
    error_code: str | None = None
    safe_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.state == "ready"
```

- [ ] **Step 2: Run syntax check**

Run:

```bash
uv run python -m py_compile ai_caddie/connectors/__init__.py ai_caddie/connectors/base.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Commit**

```bash
git add ai_caddie/connectors/__init__.py ai_caddie/connectors/base.py
git commit -m "feat: add connector base types"
```

## Task 2: Add Snapshot And Status Helpers

**Files:**

- Create: `ai_caddie/connectors/snapshot.py`
- Test: `tests/test_connector_snapshot.py`

- [ ] **Step 1: Write failing snapshot tests**

Create `tests/test_connector_snapshot.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    read_connector_status,
    write_connector_status,
    write_snapshot_manifest,
)


class ConnectorSnapshotTests(unittest.TestCase):
    def test_build_snapshot_manifest_counts_secret_free_data_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "summary.json").write_text("{}")
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            (root / "data" / "scorecards" / "2.json").write_text("{}")
            (root / "data" / "shots" / "1.json").write_text("{}")

            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_1")

        self.assertEqual(manifest.snapshot_id, "snap_1")
        self.assertEqual(manifest.scorecard_count, 2)
        self.assertEqual(manifest.shot_file_count, 1)
        self.assertTrue(manifest.summary_present)
        self.assertIn("data/scorecards/1.json", manifest.files)
        self.assertNotIn(".garmin_tokens", " ".join(manifest.files))

    def test_write_snapshot_manifest_persists_json(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            manifest = build_snapshot_manifest(root=root, snapshot_id="snap_2")

            path = write_snapshot_manifest(root=root, manifest=manifest)
            payload = json.loads(path.read_text())

        self.assertEqual(payload["snapshotId"], "snap_2")
        self.assertEqual(payload["scorecardCount"], 1)
        self.assertNotIn("cookie", json.dumps(payload).lower())
        self.assertNotIn("csrf", json.dumps(payload).lower())

    def test_connector_status_roundtrip_is_secret_free(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_connector_status(
                root=root,
                state="reauth_required",
                detail="Garmin session expired.",
                snapshot_id=None,
                error_code="auth_failed",
            )
            payload = read_connector_status(root=root)

        self.assertTrue(path.exists())
        self.assertEqual(payload["state"], "reauth_required")
        self.assertEqual(payload["errorCode"], "auth_failed")
        text = json.dumps(payload).lower()
        self.assertNotIn("cookie", text)
        self.assertNotIn("csrf", text)
        self.assertNotIn("token", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_connector_snapshot -v
```

Expected:

```text
ModuleNotFoundError: No module named 'ai_caddie.connectors.snapshot'
```

- [ ] **Step 3: Implement snapshot helper**

Create `ai_caddie/connectors/snapshot.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ai_caddie.data import ROOT

from .base import ConnectorState, SnapshotManifest

SYNC_DIR = Path("data") / "sync"
SNAPSHOT_DIR = Path("data") / "snapshots"
STATUS_FILE = SYNC_DIR / "garmin_cn_status.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _json_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file())


def build_snapshot_manifest(*, root: Path = ROOT, snapshot_id: str) -> SnapshotManifest:
    data_dir = root / "data"
    summary = data_dir / "summary.json"
    scorecards = _json_files(data_dir / "scorecards")
    shots = _json_files(data_dir / "shots")
    files: list[str] = []
    if summary.exists():
        files.append(_relative(summary, root))
    files.extend(_relative(path, root) for path in scorecards)
    files.extend(_relative(path, root) for path in shots)
    return SnapshotManifest(
        snapshot_id=snapshot_id,
        scorecard_count=len(scorecards),
        shot_file_count=len(shots),
        summary_present=summary.exists(),
        files=files,
    )


def write_snapshot_manifest(*, root: Path = ROOT, manifest: SnapshotManifest) -> Path:
    out_dir = root / SNAPSHOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{manifest.snapshot_id}.json"
    payload = {
        "schema": "ai-caddie-raw-snapshot-v1",
        "snapshotId": manifest.snapshot_id,
        "createdAt": _utc_now(),
        "scorecardCount": manifest.scorecard_count,
        "shotFileCount": manifest.shot_file_count,
        "summaryPresent": manifest.summary_present,
        "files": manifest.files,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def write_connector_status(
    *,
    root: Path = ROOT,
    state: ConnectorState,
    detail: str,
    snapshot_id: str | None,
    error_code: str | None = None,
) -> Path:
    out_dir = root / SYNC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = root / STATUS_FILE
    payload = {
        "schema": "ai-caddie-connector-status-v1",
        "connector": "garmin_cn_web_session",
        "state": state,
        "detail": detail,
        "snapshotId": snapshot_id,
        "errorCode": error_code,
        "updatedAt": _utc_now(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def read_connector_status(*, root: Path = ROOT) -> dict[str, Any] | None:
    path = root / STATUS_FILE
    if not path.exists():
        return None
    return json.loads(path.read_text())


def snapshot_to_payload(manifest: SnapshotManifest) -> dict[str, Any]:
    data = asdict(manifest)
    return {
        "snapshotId": data["snapshot_id"],
        "scorecardCount": data["scorecard_count"],
        "shotFileCount": data["shot_file_count"],
        "summaryPresent": data["summary_present"],
        "files": data["files"],
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run python -m unittest tests.test_connector_snapshot -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/connectors/snapshot.py tests/test_connector_snapshot.py
git commit -m "feat: add connector snapshot manifests"
```

## Task 3: Add Garmin CN Connector Wrapper

**Files:**

- Create: `ai_caddie/connectors/garmin_cn.py`
- Test: `tests/test_garmin_cn_connector.py`

- [ ] **Step 1: Write failing connector tests**

Create `tests/test_garmin_cn_connector.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector


class GarminCnConnectorTests(unittest.TestCase):
    def test_successful_sync_writes_ready_status_and_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "summary.json").write_text("{}")
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            (root / "data" / "shots" / "1.json").write_text("{}")
            connector = GarminCnWebSessionConnector(root=root)

            with patch("ai_caddie.connectors.garmin_cn.make_session", return_value=Mock()), \
                 patch("ai_caddie.connectors.garmin_cn.fetch_summary", return_value=[{"id": 1}]), \
                 patch("ai_caddie.connectors.garmin_cn.fetch_details") as fetch_details:
                result = connector.sync(with_shots=True, force_refresh_auth=False)

            self.assertTrue(result.ok)
            self.assertEqual(result.state, "ready")
            self.assertEqual(result.snapshot.scorecard_count, 1)
            fetch_details.assert_called_once()
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "ready")
            self.assertNotIn("cookie", json.dumps(status).lower())

    def test_auth_failure_returns_reauth_required_without_secret_leak(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with patch("ai_caddie.connectors.garmin_cn.make_session", side_effect=SystemExit("missing or expired Garmin web auth: secret cookie abc")):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertFalse(result.ok)
            self.assertEqual(result.state, "reauth_required")
            self.assertEqual(result.error_code, "auth_failed")
            self.assertNotIn("cookie", result.detail.lower())
            self.assertNotIn("secret", result.detail.lower())
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "reauth_required")

    def test_successful_sync_without_scorecards_returns_no_data_state(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with patch("ai_caddie.connectors.garmin_cn.make_session", return_value=Mock()), \
                 patch("ai_caddie.connectors.garmin_cn.fetch_summary", return_value=[]), \
                 patch("ai_caddie.connectors.garmin_cn.fetch_details"):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertEqual(result.state, "no_data")
            self.assertIsNotNone(result.snapshot)
            self.assertEqual(result.snapshot.scorecard_count, 0)
            status = json.loads((root / "data" / "sync" / "garmin_cn_status.json").read_text())
            self.assertEqual(status["state"], "no_data")

    def test_non_auth_failure_returns_error_without_secret_leak(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            connector = GarminCnWebSessionConnector(root=root)

            with patch("ai_caddie.connectors.garmin_cn.make_session", return_value=Mock()), \
                 patch("ai_caddie.connectors.garmin_cn.fetch_summary", side_effect=RuntimeError("network failed token abc")):
                result = connector.sync(with_shots=False, force_refresh_auth=False)

            self.assertFalse(result.ok)
            self.assertEqual(result.state, "error")
            self.assertEqual(result.error_code, "sync_failed")
            self.assertNotIn("token", result.detail.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_garmin_cn_connector -v
```

Expected:

```text
ModuleNotFoundError: No module named 'ai_caddie.connectors.garmin_cn'
```

- [ ] **Step 3: Implement connector wrapper**

Create `ai_caddie/connectors/garmin_cn.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from ai_caddie.data import ROOT
from fetch import fetch_details, fetch_summary, make_session

from .base import ConnectorRunResult
from .snapshot import build_snapshot_manifest, write_connector_status, write_snapshot_manifest

SECRET_PATTERNS = [
    re.compile(r"cookie[^\\s]*\\s*[^,;\\n]*", re.IGNORECASE),
    re.compile(r"csrf[^\\s]*\\s*[^,;\\n]*", re.IGNORECASE),
    re.compile(r"token[^\\s]*\\s*[^,;\\n]*", re.IGNORECASE),
    re.compile(r"secret[^\\s]*\\s*[^,;\\n]*", re.IGNORECASE),
    re.compile(r"authorization[^\\s]*\\s*[^,;\\n]*", re.IGNORECASE),
]


def sanitize_error(message: object) -> str:
    text = str(message)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    if ".garmin_tokens" in text:
        text = text.replace(".garmin_tokens", "<token-dir>")
    return text[:240]


def _snapshot_id() -> str:
    return "garmin_cn_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class GarminCnWebSessionConnector:
    def __init__(self, *, root: Path = ROOT) -> None:
        self.root = root

    def sync(self, *, with_shots: bool, force_refresh_auth: bool) -> ConnectorRunResult:
        try:
            session = make_session(force_refresh_auth=force_refresh_auth)
            cards = fetch_summary(session)
            fetch_details(session, cards, with_shots=with_shots)
            snapshot_id = _snapshot_id()
            manifest = build_snapshot_manifest(root=self.root, snapshot_id=snapshot_id)
            write_snapshot_manifest(root=self.root, manifest=manifest)
            state = "ready" if manifest.scorecard_count else "no_data"
            detail = (
                f"Synced {manifest.scorecard_count} scorecards and {manifest.shot_file_count} shot files."
                if state == "ready"
                else "Garmin sync completed, but no scorecards were returned."
            )
            write_connector_status(
                root=self.root,
                state=state,
                detail=detail,
                snapshot_id=snapshot_id,
            )
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state=state,
                detail=detail,
                snapshot=manifest,
                safe_meta={"withShots": with_shots, "cardCount": len(cards)},
            )
        except SystemExit as exc:
            detail = "Garmin CN session expired or missing. Reconnect Garmin and retry."
            write_connector_status(
                root=self.root,
                state="reauth_required",
                detail=detail,
                snapshot_id=None,
                error_code="auth_failed",
            )
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state="reauth_required",
                detail=detail,
                error_code="auth_failed",
                safe_meta={"sourceError": sanitize_error(exc)},
            )
        except Exception as exc:
            detail = "Garmin CN sync failed before a complete snapshot was written."
            write_connector_status(
                root=self.root,
                state="error",
                detail=detail,
                snapshot_id=None,
                error_code="sync_failed",
            )
            return ConnectorRunResult(
                connector="garmin_cn_web_session",
                state="error",
                detail=detail,
                error_code="sync_failed",
                safe_meta={"sourceError": sanitize_error(exc)},
            )
```

- [ ] **Step 4: Run connector tests**

Run:

```bash
uv run python -m unittest tests.test_garmin_cn_connector -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/connectors/garmin_cn.py tests/test_garmin_cn_connector.py
git commit -m "feat: add garmin cn connector wrapper"
```

## Task 4: Teach Sync Status To Read Persisted Connector State

**Files:**

- Modify: `server_v2/sync_status.py`
- Modify: `tests/test_server_v2_sync_status.py`

- [ ] **Step 1: Add failing persisted-status test**

Append to `tests/test_server_v2_sync_status.py`:

```python
    def test_build_sync_status_uses_persisted_reauth_required_state(self) -> None:
        from ai_caddie.connectors.snapshot import write_connector_status

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_connector_status(
                root=root,
                state="reauth_required",
                detail="Garmin session expired.",
                snapshot_id=None,
                error_code="auth_failed",
            )
            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["connector"]["state"], "reauth_required")
        self.assertTrue(payload["connector"]["reauthRequired"])
        self.assertFalse(payload["connector"]["canSync"])
        self.assertEqual(payload["connector"]["detail"], "Garmin session expired.")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_status -v
```

Expected failure:

```text
AssertionError: 'no_data' != 'reauth_required'
```

- [ ] **Step 3: Update sync status builder**

Modify `server_v2/sync_status.py`:

```python
from ai_caddie.connectors.snapshot import read_connector_status
```

Inside `build_sync_status_response()`, after `has_data = scorecard_count > 0`, add:

```python
    persisted = read_connector_status(root=root)
    persisted_state = persisted.get("state") if persisted else None
    if persisted_state in {"reauth_required", "error"}:
        state = persisted_state
        detail = str(persisted.get("detail") or "Garmin connector needs attention.")
    else:
        state = "ready" if has_data else "no_data"
        detail = (
            "Local Garmin snapshots are available."
            if has_data
            else "No local Garmin snapshots are loaded. Connect Garmin or use fixture mode."
        )
```

Replace the `ConnectorStatus(...)` call with:

```python
    connector = ConnectorStatus(
        name="garmin_cn_web_session",
        state=state,
        detail=detail,
        canSync=False,
        reauthRequired=state == "reauth_required",
    )
```

- [ ] **Step 4: Run sync status tests**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_status -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add server_v2/sync_status.py tests/test_server_v2_sync_status.py
git commit -m "feat: read persisted garmin connector status"
```

## Task 5: Add Sync Run API Endpoint

**Files:**

- Modify: `server_v2/models.py`
- Modify: `server_v2/main.py`
- Modify: `tests/test_server_v2_sync_run.py`
- Modify: `tests/test_server_v2_health.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_server_v2_sync_run.py`:

```python
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from ai_caddie.connectors.base import ConnectorRunResult, SnapshotManifest
from server_v2.main import app


class ServerV2SyncRunTests(unittest.TestCase):
    def test_sync_garmin_endpoint_returns_snapshot_payload(self) -> None:
        manifest = SnapshotManifest(
            snapshot_id="snap_api",
            scorecard_count=2,
            shot_file_count=1,
            summary_present=True,
            files=["data/summary.json", "data/scorecards/1.json"],
        )
        result = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="ready",
            detail="Garmin CN sync completed.",
            snapshot=manifest,
            safe_meta={"withShots": True},
        )
        connector = Mock()
        connector.sync.return_value = result

        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = TestClient(app).post("/api/v2/sync/garmin?with_shots=true")
            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-sync-run-v2")
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["snapshot"]["snapshotId"], "snap_api")
        connector.sync.assert_called_once_with(with_shots=True, force_refresh_auth=False)

    def test_sync_garmin_endpoint_returns_409_for_reauth_required(self) -> None:
        connector = Mock()
        connector.sync.return_value = ConnectorRunResult(
            connector="garmin_cn_web_session",
            state="reauth_required",
            detail="Garmin CN session expired or missing. Reconnect Garmin and retry.",
            error_code="auth_failed",
        )

        with patch("server_v2.main.GarminCnWebSessionConnector", return_value=connector):
            response = TestClient(app).post("/api/v2/sync/garmin")
            payload = response.json()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["schema"], "ai-caddie-sync-run-v2")
        self.assertEqual(payload["state"], "reauth_required")
        self.assertTrue(payload["reauthRequired"])
        self.assertNotIn("cookie", str(payload).lower())
        self.assertNotIn("csrf", str(payload).lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_run -v
```

Expected:

```text
404
```

- [ ] **Step 3: Add sync run response model**

Append to `server_v2/models.py`:

```python
class SyncSnapshotPayload(BaseModel):
    snapshotId: str
    scorecardCount: int
    shotFileCount: int
    summaryPresent: bool
    files: list[str]


class SyncRunResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-sync-run-v2"] = Field(alias="schema")
    connector: Literal["garmin_cn_web_session"]
    state: ConnectorState
    detail: str
    reauthRequired: bool
    errorCode: str | None
    snapshot: SyncSnapshotPayload | None
```

- [ ] **Step 4: Add endpoint implementation**

Modify `server_v2/main.py` imports:

```python
from fastapi import FastAPI, Response
from ai_caddie.connectors.garmin_cn import GarminCnWebSessionConnector
from ai_caddie.connectors.snapshot import snapshot_to_payload
from .models import HistoryOverviewResponse, HistoryRoundsResponse, SyncRunResponse, SyncStatusResponse
```

Change CORS methods:

```python
allow_methods=["GET", "POST"],
```

Add `"syncGarmin": "/api/v2/sync/garmin"` to the service index.

Add endpoint:

```python
@app.post("/api/v2/sync/garmin", response_model=SyncRunResponse)
def sync_garmin(
    response: Response,
    with_shots: bool = True,
    force_refresh_auth: bool = False,
) -> SyncRunResponse:
    result = GarminCnWebSessionConnector().sync(
        with_shots=with_shots,
        force_refresh_auth=force_refresh_auth,
    )
    if result.state == "reauth_required":
        response.status_code = 409
    elif result.state == "error":
        response.status_code = 500
    return SyncRunResponse(
        schema="ai-caddie-sync-run-v2",
        connector=result.connector,
        state=result.state,
        detail=result.detail,
        reauthRequired=result.state == "reauth_required",
        errorCode=result.error_code,
        snapshot=snapshot_to_payload(result.snapshot) if result.snapshot else None,
    )
```

- [ ] **Step 5: Update service index test**

In `tests/test_server_v2_health.py`, assert:

```python
self.assertEqual(payload["endpoints"]["syncGarmin"], "/api/v2/sync/garmin")
```

- [ ] **Step 6: Run API tests**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_run tests.test_server_v2_health -v
```

Expected:

```text
OK
```

- [ ] **Step 7: Commit**

```bash
git add server_v2/models.py server_v2/main.py tests/test_server_v2_sync_run.py tests/test_server_v2_health.py
git commit -m "feat: add garmin sync endpoint"
```

## Task 6: Verification

**Files:**

- Verify all files changed by Tasks 1-5.

- [ ] **Step 1: Run connector tests**

Run:

```bash
uv run python -m unittest tests.test_connector_snapshot tests.test_garmin_cn_connector tests.test_server_v2_sync_status tests.test_server_v2_sync_run -v
```

Expected:

```text
OK
```

- [ ] **Step 2: Run backend full tests**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected:

```text
OK
```

Existing skipped local Garmin/prodgeometry tests are acceptable. Failures and errors are not acceptable.

- [ ] **Step 3: Run syntax check**

Run:

```bash
uv run python -m py_compile ai_caddie/connectors/base.py ai_caddie/connectors/snapshot.py ai_caddie/connectors/garmin_cn.py server_v2/main.py server_v2/models.py server_v2/sync_status.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: HTTP smoke for status endpoint**

Start API on a free port:

```bash
AI_CADDIE_DATA_MODE=fixture uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9001
```

In another terminal:

```bash
curl -s http://127.0.0.1:9001/api/v2/sync/status | uv run python -m json.tool
```

Expected:

- `schema` is `ai-caddie-sync-status-v2`
- payload contains no `cookie`, `csrf`, `token`, `authorization`, or `secret`

Stop the temporary server.

- [ ] **Step 5: Final commit**

If Task 6 caused fixes, commit them:

```bash
git add ai_caddie/connectors server_v2 tests
git commit -m "test: verify connector snapshot layer"
```

If no files changed during Task 6, do not create an empty commit.

## Self-Review Checklist

- CN Web Session connector is the first implemented connector path.
- Official OAuth remains a separate feasibility track and is not required here.
- No Garmin username/password storage is introduced.
- Existing `fetch.py` and `garmin_auth.py` remain the low-level implementation.
- Cookie/CSRF/token values are never exposed in API models, manifests, status files, or test output.
- Expired or missing auth maps to `reauth_required`.
- Versioned raw snapshot manifests exist independently of current login state.
