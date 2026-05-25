# Foundation And Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish stable config, fixture data, connector status contracts, and test helpers so AI Caddie can be developed and tested without live Garmin credentials or private data.

**Architecture:** Add a small configuration layer, a deterministic synthetic history fixture, and a server-side data-source boundary that can load either local Garmin data or fixture data. Add sync/status contracts now without implementing full Garmin sync, so later connector work plugs into a typed API instead of leaking cookie logic into history or UI.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, unittest/TestClient, React/Vite/TypeScript, Vitest.

---

## File Structure

Create:

- `ai_caddie/config.py`  
  Owns environment-backed settings used by backend and CLI code.
- `ai_caddie/fixtures.py`  
  Owns deterministic synthetic `HistoryData` for tests and development.
- `server_v2/data_source.py`  
  Chooses local Garmin data or synthetic fixture data for API responses.
- `server_v2/sync_status.py`  
  Builds connector/snapshot status responses without performing live sync.
- `tests/test_config.py`  
  Tests settings defaults and env overrides.
- `tests/test_fixtures.py`  
  Tests synthetic data shape and metric usefulness.
- `tests/test_server_v2_data_source.py`  
  Tests data source mode behavior.
- `tests/test_server_v2_sync_status.py`  
  Tests sync status contracts.
- `web_v2/src/components/SyncStatusPanel.tsx`  
  Displays connector state.
- `web_v2/src/components/SyncStatusPanel.test.tsx`  
  Tests connector state rendering.

Modify:

- `server_v2/models.py`  
  Add data mode and sync status response models.
- `server_v2/history_overview.py`  
  Load through `server_v2.data_source`.
- `server_v2/history_rounds.py`  
  Load through `server_v2.data_source`.
- `server_v2/main.py`  
  Expose `/api/v2/sync/status` and service index metadata.
- `tests/test_server_v2_history_overview.py`  
  Keep direct builder tests; add fixture-mode endpoint test.
- `tests/test_server_v2_history_rounds.py`  
  Add fixture-mode endpoint test.
- `web_v2/src/types.ts`  
  Add sync status types.
- `web_v2/src/api.ts`  
  Add `fetchSyncStatus()`.
- `web_v2/src/api.test.ts`  
  Test sync status fetch path.
- `web_v2/src/App.tsx`  
  Fetch and render sync status near the current product shell.
- `web_v2/src/App.test.tsx`  
  Test app renders populated fixture and sync state.
- `web_v2/src/styles.css`  
  Add compact sync status styles using existing Garmin Pro tokens.

## Data Mode Semantics

Use this enum everywhere:

- `local`: read existing `data/` Garmin files only.
- `fixture`: use synthetic data only.
- `local_or_fixture`: read local Garmin files; if no normalized rounds exist, use synthetic data and report `dataMode="fixture"`.

Default for application runtime:

- `AI_CADDIE_DATA_MODE=local_or_fixture`

Default for tests:

- tests set the mode explicitly with `patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"})` or call pure functions directly.

This keeps the app useful on an empty remote workspace while still making the
active data mode visible in API responses.

## Task 1: Add Config Settings

**Files:**

- Create: `ai_caddie/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai_caddie.config import get_settings


class ConfigTests(unittest.TestCase):
    def test_settings_default_to_local_or_fixture(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.data_mode, "local_or_fixture")
        self.assertEqual(settings.llm_provider, "static")
        self.assertEqual(settings.static_llm_reply, "AI Caddie fixture response")

    def test_settings_read_env_overrides(self) -> None:
        with patch.dict(os.environ, {
            "AI_CADDIE_DATA_MODE": "fixture",
            "AI_CADDIE_LLM_PROVIDER": "nvidia_nim",
            "AI_CADDIE_STATIC_LLM_REPLY": "fixture ok",
        }, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.data_mode, "fixture")
        self.assertEqual(settings.llm_provider, "nvidia_nim")
        self.assertEqual(settings.static_llm_reply, "fixture ok")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_config -v
```

Expected:

```text
ImportError: cannot import name 'get_settings'
```

- [ ] **Step 3: Implement config module**

Create `ai_caddie/config.py`:

```python
from __future__ import annotations

from functools import lru_cache
from typing import Literal
import os

DataMode = Literal["local", "fixture", "local_or_fixture"]
LLMProviderName = Literal[
    "static",
    "anthropic",
    "nvidia_nim",
    "gemini_api_key",
    "gemini_cli_oauth",
]


class Settings:
    def __init__(self) -> None:
        self.data_mode: DataMode = _data_mode(os.getenv("AI_CADDIE_DATA_MODE", "local_or_fixture"))
        self.llm_provider: LLMProviderName = _llm_provider(os.getenv("AI_CADDIE_LLM_PROVIDER", "static"))
        self.static_llm_reply = os.getenv("AI_CADDIE_STATIC_LLM_REPLY", "AI Caddie fixture response")
        self.nvidia_api_key_present = bool(os.getenv("NVIDIA_API_KEY"))
        self.nvidia_nim_base_url = os.getenv("NVIDIA_NIM_BASE_URL", "").rstrip("/")
        self.nvidia_nim_model = os.getenv("NVIDIA_NIM_MODEL", "")
        self.gemini_api_key_present = bool(os.getenv("GEMINI_API_KEY"))
        self.anthropic_api_key_present = bool(os.getenv("ANTHROPIC_API_KEY"))


def _data_mode(value: str) -> DataMode:
    if value in {"local", "fixture", "local_or_fixture"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported AI_CADDIE_DATA_MODE: {value}")


def _llm_provider(value: str) -> LLMProviderName:
    if value in {"static", "anthropic", "nvidia_nim", "gemini_api_key", "gemini_cli_oauth"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unsupported AI_CADDIE_LLM_PROVIDER: {value}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run python -m unittest tests.test_config -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/config.py tests/test_config.py
git commit -m "feat: add ai caddie settings"
```

## Task 2: Add Synthetic History Fixture

**Files:**

- Create: `ai_caddie/fixtures.py`
- Test: `tests/test_fixtures.py`

- [ ] **Step 1: Write failing fixture tests**

Create `tests/test_fixtures.py`:

```python
from __future__ import annotations

import unittest

from ai_caddie.fixtures import fixture_history_data
from server_v2.history_overview import build_history_overview_response


class FixtureTests(unittest.TestCase):
    def test_fixture_has_useful_history_shape(self) -> None:
        data = fixture_history_data()

        self.assertGreaterEqual(len(data.rounds), 3)
        self.assertGreaterEqual(len(data.shots), 6)
        self.assertTrue(any(row.get("holesCompleted") == 18 for row in data.rounds))
        self.assertTrue(any(row.get("hasShots") for row in data.rounds))
        self.assertTrue(all(row.get("courseKey") for row in data.rounds))

    def test_fixture_drives_non_empty_overview(self) -> None:
        payload = build_history_overview_response(fixture_history_data()).model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-history-overview-v2")
        self.assertGreaterEqual(payload["metrics"]["totalRounds"], 3)
        self.assertGreater(payload["metrics"]["shotCount"], 0)
        self.assertIsNone(payload["emptyState"])
        self.assertGreater(len(payload["recentRounds"]), 0)
        self.assertGreater(payload["distribution"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_fixtures -v
```

Expected:

```text
ModuleNotFoundError: No module named 'ai_caddie.fixtures'
```

- [ ] **Step 3: Implement fixture data**

Create `ai_caddie/fixtures.py`:

```python
from __future__ import annotations

from ai_caddie.history import HistoryData


def _holes(scores: list[int], pars: list[int]) -> list[dict[str, object]]:
    return [
        {
            "number": index + 1,
            "strokes": score,
            "par": pars[index],
            "putts": 2 if score <= pars[index] + 1 else 3,
            "gir": score <= pars[index],
            "fairway": "hit" if index % 3 else "right",
        }
        for index, score in enumerate(scores)
    ]


def fixture_history_data() -> HistoryData:
    pars18 = [4, 5, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 3, 4, 4, 5, 3, 4]
    black_scores_good = [4, 5, 4, 3, 5, 4, 6, 3, 4, 4, 5, 5, 3, 4, 5, 5, 4, 4]
    black_scores_bad = [5, 6, 5, 4, 6, 5, 7, 4, 5, 5, 6, 6, 4, 5, 6, 7, 4, 5]
    bay_scores = [4, 4, 5, 3, 4, 5, 5, 4, 4]
    pars9 = pars18[:9]

    rounds = [
        {
            "id": 900001,
            "ids": [900001],
            "date": "2026-05-18",
            "course": "Black Knight B/C",
            "courseCanonical": "Black Knight",
            "courseKey": "black_knight",
            "globalId": 31795,
            "holesCompleted": 18,
            "strokes": sum(black_scores_good),
            "par": sum(pars18),
            "holePars": "".join(str(p) for p in pars18),
            "holes": _holes(black_scores_good, pars18),
            "hasShots": True,
            "shotStatus": "fixture shots ready",
        },
        {
            "id": 900002,
            "ids": [900002],
            "date": "2026-04-26",
            "course": "Black Knight B/C",
            "courseCanonical": "Black Knight",
            "courseKey": "black_knight",
            "globalId": 31795,
            "holesCompleted": 18,
            "strokes": sum(black_scores_bad),
            "par": sum(pars18),
            "holePars": "".join(str(p) for p in pars18),
            "holes": _holes(black_scores_bad, pars18),
            "hasShots": True,
            "shotStatus": "fixture shots ready",
        },
        {
            "id": 900003,
            "ids": [900003],
            "date": "2026-03-09",
            "course": "Bay Practice Nine",
            "courseCanonical": "Bay Practice",
            "courseKey": "bay_practice",
            "globalId": 41825,
            "holesCompleted": 9,
            "strokes": sum(bay_scores),
            "par": sum(pars9),
            "holePars": "".join(str(p) for p in pars9),
            "holes": _holes(bay_scores, pars9),
            "hasShots": False,
            "shotStatus": "fixture missing shots",
        },
    ]
    shots = [
        {"roundId": 900001, "hole": 1, "club": "1D", "distance": 238, "surface": "fairway"},
        {"roundId": 900001, "hole": 1, "club": "8I", "distance": 142, "surface": "green"},
        {"roundId": 900001, "hole": 2, "club": "3W", "distance": 211, "surface": "fairway"},
        {"roundId": 900001, "hole": 2, "club": "58", "distance": 76, "surface": "green"},
        {"roundId": 900002, "hole": 5, "club": "1D", "distance": 225, "surface": "rough"},
        {"roundId": 900002, "hole": 7, "club": "5I", "distance": 168, "surface": "water"},
    ]
    raw_rounds = [{"id": row["id"], "hasShots": row["hasShots"]} for row in rounds]
    return HistoryData(raw_rounds=raw_rounds, rounds=rounds, shots=shots)
```

- [ ] **Step 4: Run fixture tests**

Run:

```bash
uv run python -m unittest tests.test_fixtures -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/fixtures.py tests/test_fixtures.py
git commit -m "feat: add synthetic history fixture"
```

## Task 3: Add Server Data Source Boundary

**Files:**

- Create: `server_v2/data_source.py`
- Modify: `server_v2/history_overview.py`
- Modify: `server_v2/history_rounds.py`
- Test: `tests/test_server_v2_data_source.py`
- Modify: `tests/test_server_v2_history_overview.py`
- Modify: `tests/test_server_v2_history_rounds.py`

- [ ] **Step 1: Write failing data source tests**

Create `tests/test_server_v2_data_source.py`:

```python
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ai_caddie.config import get_settings
from ai_caddie.history import HistoryData
from server_v2.data_source import load_history_data_for_mode


class ServerV2DataSourceTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_fixture_mode_returns_fixture_data_and_mode(self) -> None:
        data, mode = load_history_data_for_mode("fixture")

        self.assertEqual(mode, "fixture")
        self.assertGreaterEqual(len(data.rounds), 3)

    def test_local_mode_returns_local_mode_even_when_empty(self) -> None:
        with patch("server_v2.data_source.load_history_data", return_value=HistoryData(raw_rounds=[], rounds=[], shots=[])):
            data, mode = load_history_data_for_mode("local")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds, [])

    def test_local_or_fixture_uses_fixture_when_local_has_no_rounds(self) -> None:
        with patch("server_v2.data_source.load_history_data", return_value=HistoryData(raw_rounds=[], rounds=[], shots=[])):
            data, mode = load_history_data_for_mode("local_or_fixture")

        self.assertEqual(mode, "fixture")
        self.assertGreaterEqual(len(data.rounds), 3)

    def test_local_or_fixture_keeps_local_when_rounds_exist(self) -> None:
        local = HistoryData(raw_rounds=[{"id": 1}], rounds=[{"id": 1}], shots=[])
        with patch("server_v2.data_source.load_history_data", return_value=local):
            data, mode = load_history_data_for_mode("local_or_fixture")

        self.assertEqual(mode, "local")
        self.assertEqual(data.rounds, [{"id": 1}])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_data_source -v
```

Expected:

```text
ModuleNotFoundError: No module named 'server_v2.data_source'
```

- [ ] **Step 3: Implement data source module**

Create `server_v2/data_source.py`:

```python
from __future__ import annotations

from typing import Literal

from ai_caddie.config import DataMode, get_settings
from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history import HistoryData, load_history_data

ResolvedDataMode = Literal["local", "fixture"]


def load_history_data_for_mode(mode: DataMode | None = None) -> tuple[HistoryData, ResolvedDataMode]:
    selected = mode or get_settings().data_mode
    if selected == "fixture":
        return fixture_history_data(), "fixture"
    local_data = load_history_data()
    if selected == "local":
        return local_data, "local"
    if local_data.rounds:
        return local_data, "local"
    return fixture_history_data(), "fixture"
```

- [ ] **Step 4: Modify API loaders to use data source**

In `server_v2/history_overview.py`, change the imports and loader:

```python
from .data_source import load_history_data_for_mode
```

Replace `load_history_overview_response()` with:

```python
def load_history_overview_response() -> HistoryOverviewResponse:
    data, _mode = load_history_data_for_mode()
    return build_history_overview_response(data)
```

In `server_v2/history_rounds.py`, import `load_history_data_for_mode` and replace its loader with:

```python
def load_history_rounds_response() -> HistoryRoundsResponse:
    data, _mode = load_history_data_for_mode()
    return build_history_rounds_response(data)
```

- [ ] **Step 5: Add fixture-mode endpoint tests**

Append to `tests/test_server_v2_history_overview.py`:

```python
    def test_history_overview_endpoint_can_use_fixture_mode(self) -> None:
        import os
        from unittest.mock import patch
        from ai_caddie.config import get_settings

        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            client = TestClient(app)
            response = client.get("/api/v2/history/overview")
            payload = response.json()
        get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(payload["metrics"]["totalRounds"], 3)
        self.assertIsNone(payload["emptyState"])
```

Add equivalent fixture-mode coverage to `tests/test_server_v2_history_rounds.py`:

```python
    def test_history_rounds_endpoint_can_use_fixture_mode(self) -> None:
        import os
        from unittest.mock import patch
        from ai_caddie.config import get_settings

        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            client = TestClient(app)
            response = client.get("/api/v2/history/rounds")
            payload = response.json()
        get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(payload["total"], 3)
        self.assertGreater(len(payload["groups"]), 0)
        self.assertIsNone(payload["emptyState"])
```

- [ ] **Step 6: Run data source and history endpoint tests**

Run:

```bash
uv run python -m unittest tests.test_server_v2_data_source tests.test_server_v2_history_overview tests.test_server_v2_history_rounds -v
```

Expected:

```text
OK
```

- [ ] **Step 7: Commit**

```bash
git add server_v2/data_source.py server_v2/history_overview.py server_v2/history_rounds.py tests/test_server_v2_data_source.py tests/test_server_v2_history_overview.py tests/test_server_v2_history_rounds.py
git commit -m "feat: add fixture-backed history data source"
```

## Task 4: Add Sync Status Contract

**Files:**

- Modify: `server_v2/models.py`
- Create: `server_v2/sync_status.py`
- Modify: `server_v2/main.py`
- Test: `tests/test_server_v2_sync_status.py`
- Modify: `tests/test_server_v2_health.py`

- [ ] **Step 1: Write failing sync status tests**

Create `tests/test_server_v2_sync_status.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from server_v2.main import app
from server_v2.sync_status import build_sync_status_response


class ServerV2SyncStatusTests(unittest.TestCase):
    def test_build_sync_status_reports_no_data_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-sync-status-v2")
        self.assertEqual(payload["connector"]["name"], "garmin_cn_web_session")
        self.assertEqual(payload["connector"]["state"], "no_data")
        self.assertEqual(payload["snapshot"]["scorecardCount"], 0)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 0)
        self.assertNotIn("cookie", str(payload).lower())
        self.assertNotIn("csrf", str(payload).lower())

    def test_build_sync_status_reports_snapshot_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "scorecards").mkdir(parents=True)
            (root / "data" / "shots").mkdir(parents=True)
            (root / "data" / "scorecards" / "1.json").write_text("{}")
            (root / "data" / "scorecards" / "2.json").write_text("{}")
            (root / "data" / "shots" / "1.json").write_text("{}")
            payload = build_sync_status_response(root=root, data_mode="local").model_dump()

        self.assertEqual(payload["connector"]["state"], "ready")
        self.assertEqual(payload["snapshot"]["scorecardCount"], 2)
        self.assertEqual(payload["snapshot"]["shotFileCount"], 1)

    def test_build_sync_status_reports_fixture_mode_when_local_or_fixture_has_no_data(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = build_sync_status_response(root=root, data_mode="local_or_fixture").model_dump()

        self.assertEqual(payload["connector"]["state"], "no_data")
        self.assertEqual(payload["snapshot"]["dataMode"], "fixture")

    def test_sync_status_endpoint_uses_public_schema_alias(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/sync/status")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-sync-status-v2")
        self.assertNotIn("schema_", payload)
        self.assertIn(payload["connector"]["state"], ["ready", "no_data", "reauth_required", "error"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_status -v
```

Expected:

```text
ModuleNotFoundError: No module named 'server_v2.sync_status'
```

- [ ] **Step 3: Add sync status models**

Append these models to `server_v2/models.py`:

```python
ConnectorState = Literal["ready", "no_data", "reauth_required", "error"]
ResolvedDataModeName = Literal["local", "fixture"]


class ConnectorStatus(BaseModel):
    name: Literal["garmin_cn_web_session"]
    state: ConnectorState
    detail: str
    canSync: bool
    reauthRequired: bool


class SnapshotStatus(BaseModel):
    dataMode: ResolvedDataModeName
    scorecardCount: int
    shotFileCount: int
    summaryPresent: bool
    lastSuccessfulSyncAt: str | None


class SyncStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-sync-status-v2"] = Field(alias="schema")
    connector: ConnectorStatus
    snapshot: SnapshotStatus
```

- [ ] **Step 4: Implement sync status builder**

Create `server_v2/sync_status.py`:

```python
from __future__ import annotations

from pathlib import Path

from ai_caddie.config import DataMode, get_settings
from ai_caddie.data import ROOT

from .models import ConnectorStatus, SnapshotStatus, SyncStatusResponse


def _count_json_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def _last_sync_at(paths: list[Path]) -> str | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    newest = max(existing, key=lambda p: p.stat().st_mtime)
    return newest.stat().st_mtime_ns.__str__()


def build_sync_status_response(*, root: Path = ROOT, data_mode: DataMode | None = None) -> SyncStatusResponse:
    selected_mode = data_mode or get_settings().data_mode
    data_dir = root / "data"
    scorecard_dir = data_dir / "scorecards"
    shot_dir = data_dir / "shots"
    summary = data_dir / "summary.json"
    scorecard_count = _count_json_files(scorecard_dir)
    shot_file_count = _count_json_files(shot_dir)
    has_data = scorecard_count > 0
    resolved_mode = "fixture" if selected_mode == "fixture" or (selected_mode == "local_or_fixture" and not has_data) else "local"
    connector = ConnectorStatus(
        name="garmin_cn_web_session",
        state="ready" if has_data else "no_data",
        detail=(
            "Local Garmin snapshots are available."
            if has_data
            else "No local Garmin snapshots are loaded. Connect Garmin or use fixture mode."
        ),
        canSync=False,
        reauthRequired=False,
    )
    return SyncStatusResponse(
        schema="ai-caddie-sync-status-v2",
        connector=connector,
        snapshot=SnapshotStatus(
            dataMode=resolved_mode,
            scorecardCount=scorecard_count,
            shotFileCount=shot_file_count,
            summaryPresent=summary.exists(),
            lastSuccessfulSyncAt=_last_sync_at([summary, scorecard_dir, shot_dir]),
        ),
    )


def load_sync_status_response() -> SyncStatusResponse:
    return build_sync_status_response()
```

Note: `lastSuccessfulSyncAt` is a monotonic sortable placeholder string in Plan 1. Plan 2 replaces it with real `SyncRun` timestamps.

- [ ] **Step 5: Expose endpoint**

In `server_v2/main.py`, import the model and loader:

```python
from .models import HistoryOverviewResponse, HistoryRoundsResponse, SyncStatusResponse
from .sync_status import load_sync_status_response
```

Add `"syncStatus": "/api/v2/sync/status"` to the service index endpoints.

Add endpoint:

```python
@app.get("/api/v2/sync/status", response_model=SyncStatusResponse)
def sync_status() -> SyncStatusResponse:
    return load_sync_status_response()
```

- [ ] **Step 6: Update health/index test**

In `tests/test_server_v2_health.py`, extend the service index assertion:

```python
self.assertEqual(payload["endpoints"]["syncStatus"], "/api/v2/sync/status")
```

- [ ] **Step 7: Run sync status tests**

Run:

```bash
uv run python -m unittest tests.test_server_v2_sync_status tests.test_server_v2_health -v
```

Expected:

```text
OK
```

- [ ] **Step 8: Commit**

```bash
git add server_v2/models.py server_v2/sync_status.py server_v2/main.py tests/test_server_v2_sync_status.py tests/test_server_v2_health.py
git commit -m "feat: add sync status contract"
```

## Task 5: Add Frontend Sync Status Types And API

**Files:**

- Modify: `web_v2/src/types.ts`
- Modify: `web_v2/src/api.ts`
- Modify: `web_v2/src/api.test.ts`

- [ ] **Step 1: Write failing API test**

Append to `web_v2/src/api.test.ts`:

```typescript
  it('fetches sync status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-sync-status-v2',
        connector: {
          name: 'garmin_cn_web_session',
          state: 'no_data',
          detail: 'No local Garmin snapshots are loaded.',
          canSync: false,
          reauthRequired: false,
        },
        snapshot: {
          dataMode: 'fixture',
          scorecardCount: 0,
          shotFileCount: 0,
          summaryPresent: false,
          lastSuccessfulSyncAt: null,
        },
      }),
    }))

    const data = await fetchSyncStatus()

    expect(fetch).toHaveBeenCalledWith('/api/v2/sync/status')
    expect(data.schema).toBe('ai-caddie-sync-status-v2')
    expect(data.connector.state).toBe('no_data')
  })
```

Add `fetchSyncStatus` to the test import from `./api`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd web_v2
npm test -- --run src/api.test.ts
```

Expected:

```text
ReferenceError: fetchSyncStatus is not defined
```

- [ ] **Step 3: Add TypeScript types**

Append to `web_v2/src/types.ts`:

```typescript
export type ConnectorState = 'ready' | 'no_data' | 'reauth_required' | 'error'
export type ResolvedDataMode = 'local' | 'fixture'

export interface ConnectorStatus {
  name: 'garmin_cn_web_session'
  state: ConnectorState
  detail: string
  canSync: boolean
  reauthRequired: boolean
}

export interface SnapshotStatus {
  dataMode: ResolvedDataMode
  scorecardCount: number
  shotFileCount: number
  summaryPresent: boolean
  lastSuccessfulSyncAt: string | null
}

export interface SyncStatusResponse {
  schema: 'ai-caddie-sync-status-v2'
  connector: ConnectorStatus
  snapshot: SnapshotStatus
}
```

- [ ] **Step 4: Add API function**

Modify the import in `web_v2/src/api.ts`:

```typescript
import type { HistoryOverviewResponse, HistoryRoundsResponse, SyncStatusResponse } from './types'
```

Append:

```typescript
export function fetchSyncStatus(): Promise<SyncStatusResponse> {
  return getJson<SyncStatusResponse>('/api/v2/sync/status')
}
```

- [ ] **Step 5: Run API test**

Run:

```bash
cd web_v2
npm test -- --run src/api.test.ts
```

Expected:

```text
PASS src/api.test.ts
```

- [ ] **Step 6: Commit**

```bash
git add web_v2/src/types.ts web_v2/src/api.ts web_v2/src/api.test.ts
git commit -m "feat: add frontend sync status API"
```

## Task 6: Render Sync Status In Web App

**Files:**

- Create: `web_v2/src/components/SyncStatusPanel.tsx`
- Create: `web_v2/src/components/SyncStatusPanel.test.tsx`
- Modify: `web_v2/src/App.tsx`
- Modify: `web_v2/src/App.test.tsx`
- Modify: `web_v2/src/styles.css`

- [ ] **Step 1: Write component test**

Create `web_v2/src/components/SyncStatusPanel.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SyncStatusPanel } from './SyncStatusPanel'
import type { SyncStatusResponse } from '../types'

const baseStatus: SyncStatusResponse = {
  schema: 'ai-caddie-sync-status-v2',
  connector: {
    name: 'garmin_cn_web_session',
    state: 'ready',
    detail: 'Local Garmin snapshots are available.',
    canSync: false,
    reauthRequired: false,
  },
  snapshot: {
    dataMode: 'local',
    scorecardCount: 12,
    shotFileCount: 8,
    summaryPresent: true,
    lastSuccessfulSyncAt: '2026-05-25T00:00:00Z',
  },
}

describe('SyncStatusPanel', () => {
  it('renders ready local snapshot counts', () => {
    render(<SyncStatusPanel status={baseStatus} />)

    expect(screen.getByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getByText('12 scorecards')).toBeInTheDocument()
    expect(screen.getByText('8 shot files')).toBeInTheDocument()
    expect(screen.getByText('local data')).toBeInTheDocument()
  })

  it('renders reauth required state', () => {
    render(<SyncStatusPanel status={{
      ...baseStatus,
      connector: {
        ...baseStatus.connector,
        state: 'reauth_required',
        detail: 'Garmin session expired.',
        reauthRequired: true,
      },
    }} />)

    expect(screen.getByText('reauth required')).toBeInTheDocument()
    expect(screen.getByText('Garmin session expired.')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd web_v2
npm test -- --run src/components/SyncStatusPanel.test.tsx
```

Expected:

```text
Failed to resolve import "./SyncStatusPanel"
```

- [ ] **Step 3: Implement component**

Create `web_v2/src/components/SyncStatusPanel.tsx`:

```typescript
import type { SyncStatusResponse } from '../types'

const stateLabel = {
  ready: 'ready',
  no_data: 'no data',
  reauth_required: 'reauth required',
  error: 'error',
}

interface SyncStatusPanelProps {
  status: SyncStatusResponse
}

export function SyncStatusPanel({ status }: SyncStatusPanelProps) {
  return (
    <section className="sync-panel" aria-label="Garmin sync status">
      <div>
        <p className="eyebrow">Garmin CN</p>
        <h2>{stateLabel[status.connector.state]}</h2>
        <p>{status.connector.detail}</p>
      </div>
      <div className="sync-panel__facts">
        <span>{status.snapshot.scorecardCount} scorecards</span>
        <span>{status.snapshot.shotFileCount} shot files</span>
        <span>{status.snapshot.dataMode} data</span>
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Wire into app**

In `web_v2/src/App.tsx`, fetch sync status alongside existing overview/rounds data. Use this state shape:

```typescript
const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null)
```

Add `fetchSyncStatus` to imports from `./api` and `SyncStatusResponse` to type imports.

Inside the existing data loading effect, call:

```typescript
const [overviewPayload, roundsPayload, syncPayload] = await Promise.all([
  fetchHistoryOverview(),
  fetchHistoryRounds(),
  fetchSyncStatus(),
])
setOverview(overviewPayload)
setRounds(roundsPayload)
setSyncStatus(syncPayload)
```

Render below the product navigation and above the active page content:

```tsx
{syncStatus ? <SyncStatusPanel status={syncStatus} /> : null}
```

- [ ] **Step 5: Add styles**

Append to `web_v2/src/styles.css`:

```css
.sync-panel {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 8px;
  padding: 14px 16px;
  margin: 0 0 18px;
}

.sync-panel h2 {
  margin: 2px 0 4px;
  font-size: 16px;
  line-height: 1.2;
  letter-spacing: 0;
}

.sync-panel p {
  margin: 0;
  color: var(--muted);
}

.sync-panel__facts {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.sync-panel__facts span {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

@media (max-width: 760px) {
  .sync-panel {
    align-items: flex-start;
    flex-direction: column;
  }

  .sync-panel__facts {
    justify-content: flex-start;
  }
}
```

- [ ] **Step 6: Update app tests**

In `web_v2/src/App.test.tsx`, make the fetch mock return three responses in order: overview, rounds, sync status. Assert:

```typescript
expect(await screen.findByText('Garmin CN')).toBeInTheDocument()
expect(screen.getByText('ready')).toBeInTheDocument()
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
cd web_v2
npm test -- --run src/components/SyncStatusPanel.test.tsx src/App.test.tsx
```

Expected:

```text
PASS src/components/SyncStatusPanel.test.tsx
PASS src/App.test.tsx
```

- [ ] **Step 8: Commit**

```bash
git add web_v2/src/components/SyncStatusPanel.tsx web_v2/src/components/SyncStatusPanel.test.tsx web_v2/src/App.tsx web_v2/src/App.test.tsx web_v2/src/styles.css
git commit -m "feat: show garmin sync status"
```

## Task 7: Verification

**Files:**

- Verify all files changed by Tasks 1-6.

- [ ] **Step 1: Run backend unit tests**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected:

```text
OK
```

Skipped tests are acceptable only if they were already intentionally skipped for missing optional local dependencies. No failed or errored tests are acceptable.

- [ ] **Step 2: Run backend syntax check**

Run:

```bash
uv run python -m py_compile ai_caddie/config.py ai_caddie/fixtures.py server_v2/data_source.py server_v2/sync_status.py server_v2/main.py server_v2/models.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd web_v2
npm test -- --run
```

Expected:

```text
Test Files  all passed
Tests       all passed
```

- [ ] **Step 4: Run frontend build and lint**

Run:

```bash
cd web_v2
npm run lint
npm run build
```

Expected:

```text
✓ built
```

`npm run lint` must exit 0.

- [ ] **Step 5: Manual API smoke with fixture mode**

Run:

```bash
AI_CADDIE_DATA_MODE=fixture uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

In another terminal:

```bash
curl -s http://127.0.0.1:9000/api/v2/history/overview | python -m json.tool | head -40
curl -s http://127.0.0.1:9000/api/v2/sync/status | python -m json.tool
```

Expected:

- overview has `schema` equal to `ai-caddie-history-overview-v2`
- overview `metrics.totalRounds` is at least `3`
- sync status has `schema` equal to `ai-caddie-sync-status-v2`
- sync status contains no cookie, csrf, token, or secret string

Stop the server after the smoke test.

- [ ] **Step 6: Final commit**

If Task 7 caused any fixes, commit them:

```bash
git add ai_caddie server_v2 tests web_v2
git commit -m "test: verify foundation fixtures"
```

If no files changed during Task 7, do not create an empty commit.

## Self-Review Checklist

- Spec coverage: this plan implements foundation/config, fixture data, connector status semantics, and no-secret automated tests from the master spec.
- No external Garmin credentials are required.
- No Garmin username/password storage is introduced.
- Data acquisition itself is deferred to Plan 2 through a typed connector contract.
- Empty remote data no longer blocks development because fixture mode can populate API/UI.
- The active data mode is visible, so fixture data cannot be mistaken for private Garmin data.
