# History Statistics Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first complete backend history statistics core across time, scoring, course, hole, club, issue, and data quality, with drill-down references.

**Architecture:** Add a pure Python aggregation module that consumes existing `HistoryData` and returns a versioned dictionary contract. Keep this independent from Garmin raw JSON and frontend UI. Expose the contract through FastAPI using the existing fixture/local data source boundary.

**Tech Stack:** Python 3.12, existing `HistoryData`, FastAPI, unittest/TestClient.

---

## File Structure

Create:

- `ai_caddie/history_stats.py`  
  Pure statistics engine. No file reads, no FastAPI imports, no raw Garmin parsing.
- `tests/test_history_stats_core.py`  
  Unit tests for dimensions, drill-down references, and fixture output.
- `server_v2/history_stats.py`  
  API loader around the pure statistics engine and data source.
- `tests/test_server_v2_history_stats.py`  
  API contract tests.

Modify:

- `server_v2/models.py`  
  Add `HistoryStatsResponse` as a permissive versioned model for the stats contract.
- `server_v2/main.py`  
  Add `GET /api/v2/history/stats`.
- `tests/test_server_v2_health.py`  
  Add service index coverage for `historyStats`.

## Contract Shape

`GET /api/v2/history/stats` returns:

```json
{
  "schema": "ai-caddie-history-stats-v1",
  "dataMode": "local|fixture",
  "summary": {},
  "time": {},
  "scoring": {},
  "courses": [],
  "holes": [],
  "clubs": [],
  "issues": [],
  "dataQuality": [],
  "drillDown": {}
}
```

Every aggregate row includes source references using existing round ids and,
where possible, hole numbers or shot indices. The contract is intentionally
plain dictionaries in this plan because Web/API plans will decide exact
presentation DTOs.

## Task 1: Add Pure Statistics Engine

**Files:**

- Create: `ai_caddie/history_stats.py`
- Test: `tests/test_history_stats_core.py`

- [ ] **Step 1: Write failing statistics tests**

Create `tests/test_history_stats_core.py`:

```python
from __future__ import annotations

import unittest

from ai_caddie.fixtures import fixture_history_data
from ai_caddie.history_stats import build_history_stats


class HistoryStatsCoreTests(unittest.TestCase):
    def test_stats_cover_required_dimensions(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        self.assertEqual(stats["schema"], "ai-caddie-history-stats-v1")
        self.assertEqual(stats["dataMode"], "fixture")
        self.assertIn("summary", stats)
        self.assertIn("time", stats)
        self.assertIn("scoring", stats)
        self.assertIn("courses", stats)
        self.assertIn("holes", stats)
        self.assertIn("clubs", stats)
        self.assertIn("issues", stats)
        self.assertIn("dataQuality", stats)
        self.assertIn("drillDown", stats)

    def test_summary_and_time_stats_are_populated_from_fixture(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        self.assertEqual(stats["summary"]["totalRounds"], 3)
        self.assertEqual(stats["summary"]["eighteenHoleRounds"], 2)
        self.assertEqual(stats["summary"]["nineHoleRounds"], 1)
        self.assertEqual(stats["summary"]["courseCount"], 2)
        self.assertEqual(stats["summary"]["shotCount"], 6)
        self.assertEqual(stats["time"]["byYear"][0]["year"], "2026")
        self.assertEqual(stats["time"]["byYear"][0]["roundCount"], 3)
        self.assertGreaterEqual(len(stats["time"]["byMonth"]), 3)

    def test_scoring_bands_and_counts_have_drilldown_refs(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        band_labels = [row["label"] for row in stats["scoring"]["scoreBands"]]
        self.assertIn("70s", band_labels)
        self.assertIn("90s", band_labels)
        band_70s = next(row for row in stats["scoring"]["scoreBands"] if row["label"] == "70s")
        self.assertEqual(band_70s["roundIds"], ["900001"])
        self.assertGreater(stats["scoring"]["outcomes"]["parOrBetter"], 0)
        self.assertGreater(stats["scoring"]["outcomes"]["bogeyOrWorse"], 0)

    def test_course_hole_club_and_issue_stats_are_populated(self) -> None:
        stats = build_history_stats(fixture_history_data(), data_mode="fixture")

        course = next(row for row in stats["courses"] if row["courseKey"] == "black_knight")
        self.assertEqual(course["roundCount"], 2)
        self.assertEqual(course["bestScore"], 77)
        self.assertEqual(course["roundIds"], ["900001", "900002"])

        hole = next(row for row in stats["holes"] if row["courseKey"] == "black_knight" and row["hole"] == 7)
        self.assertEqual(hole["sampleCount"], 2)
        self.assertIn("900001:7", hole["refs"])

        driver = next(row for row in stats["clubs"] if row["club"] == "1D")
        self.assertEqual(driver["sampleCount"], 2)
        self.assertEqual(driver["confidence"], "medium")
        self.assertEqual(driver["roundIds"], ["900001", "900002"])

        issue_labels = [row["issue"] for row in stats["issues"]]
        self.assertIn("missing_shots", issue_labels)
        self.assertIn("hazard_result", issue_labels)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_history_stats_core -v
```

Expected:

```text
ModuleNotFoundError: No module named 'ai_caddie.history_stats'
```

- [ ] **Step 3: Implement statistics engine**

Create `ai_caddie/history_stats.py`:

```python
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any, Literal

from ai_caddie.history import HistoryData, average, percentile

DataModeName = Literal["local", "fixture"]


def _round_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


def _score_band(score: int) -> str:
    if score < 80:
        return "70s"
    if score < 90:
        return "80s"
    if score < 100:
        return "90s"
    return "100+"


def _confidence(sample_count: int) -> str:
    if sample_count >= 10:
        return "high"
    if sample_count >= 2:
        return "medium"
    return "low"


def _hole_to_par(hole: dict[str, Any], fallback_par: int | None) -> int | None:
    par = hole.get("par")
    if isinstance(par, int):
        return par
    return fallback_par


def _par_from_string(hole_pars: str, hole_number: int) -> int | None:
    if 1 <= hole_number <= len(hole_pars):
        try:
            return int(hole_pars[hole_number - 1])
        except ValueError:
            return None
    return None


def _summary(data: HistoryData) -> dict[str, Any]:
    rounds18 = [row for row in data.rounds if row.get("holesCompleted") == 18 and row.get("strokes") is not None]
    scores18 = [int(row["strokes"]) for row in rounds18]
    return {
        "totalRounds": len(data.rounds),
        "eighteenHoleRounds": len(rounds18),
        "nineHoleRounds": sum(1 for row in data.rounds if row.get("holesCompleted") == 9),
        "courseCount": len({row.get("courseKey") for row in data.rounds if row.get("courseKey")}),
        "shotCount": len(data.shots),
        "average18": average(scores18),
        "bestScore": min(scores18) if scores18 else None,
        "worstScore": max(scores18) if scores18 else None,
    }


def _time_stats(data: HistoryData) -> dict[str, Any]:
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        date = str(row.get("date") or "")
        year = date[:4] if len(date) >= 4 else "unknown"
        month = date[:7] if len(date) >= 7 else "unknown"
        by_year[year].append(row)
        by_month[month].append(row)

    def pack(key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        scores18 = [int(row["strokes"]) for row in rows if row.get("holesCompleted") == 18 and row.get("strokes") is not None]
        return {
            "key": key,
            "year": key if len(key) == 4 else None,
            "roundCount": len(rows),
            "average18": average(scores18),
            "bestScore": min(scores18) if scores18 else None,
            "roundIds": [_round_id(row) for row in rows],
        }

    return {
        "byYear": [pack(key, by_year[key]) for key in sorted(by_year, reverse=True)],
        "byMonth": [pack(key, by_month[key]) for key in sorted(by_month, reverse=True)],
    }


def _scoring(data: HistoryData) -> dict[str, Any]:
    bands: dict[str, list[str]] = {"70s": [], "80s": [], "90s": [], "100+": []}
    outcomes = Counter({"eagleOrBetter": 0, "birdie": 0, "par": 0, "bogey": 0, "doubleOrWorse": 0})
    for row in data.rounds:
        if row.get("holesCompleted") == 18 and row.get("strokes") is not None:
            bands[_score_band(int(row["strokes"]))].append(_round_id(row))
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if par is None or score is None:
                continue
            delta = int(score) - int(par)
            if delta <= -2:
                outcomes["eagleOrBetter"] += 1
            elif delta == -1:
                outcomes["birdie"] += 1
            elif delta == 0:
                outcomes["par"] += 1
            elif delta == 1:
                outcomes["bogey"] += 1
            else:
                outcomes["doubleOrWorse"] += 1
    return {
        "scoreBands": [
            {"label": label, "count": len(round_ids), "roundIds": round_ids}
            for label, round_ids in bands.items()
        ],
        "outcomes": {
            **dict(outcomes),
            "parOrBetter": outcomes["eagleOrBetter"] + outcomes["birdie"] + outcomes["par"],
            "bogeyOrWorse": outcomes["bogey"] + outcomes["doubleOrWorse"],
        },
    }


def _courses(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rounds:
        grouped[str(row.get("courseKey") or "unknown")].append(row)
    out = []
    for course_key, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda row: str(row.get("date") or ""), reverse=True)
        scores18 = [int(row["strokes"]) for row in rows if row.get("holesCompleted") == 18 and row.get("strokes") is not None]
        out.append({
            "courseKey": course_key,
            "courseName": str(rows_sorted[0].get("course") or rows_sorted[0].get("courseName") or "Unknown course"),
            "roundCount": len(rows),
            "average18": average(scores18),
            "bestScore": min(scores18) if scores18 else None,
            "worstScore": max(scores18) if scores18 else None,
            "recentRoundId": _round_id(rows_sorted[0]),
            "roundIds": [_round_id(row) for row in rows_sorted],
        })
    return sorted(out, key=lambda row: (-row["roundCount"], row["courseName"]))


def _holes(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row in data.rounds:
        course_key = str(row.get("courseKey") or "unknown")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            if number:
                grouped[(course_key, number)].append((row, hole))
    out = []
    for (course_key, number), pairs in grouped.items():
        deltas: list[int] = []
        refs: list[str] = []
        for row, hole in pairs:
            par = _hole_to_par(hole, _par_from_string(str(row.get("holePars") or ""), number))
            score = hole.get("strokes")
            if par is not None and score is not None:
                deltas.append(int(score) - int(par))
            refs.append(f"{_round_id(row)}:{number}")
        out.append({
            "courseKey": course_key,
            "hole": number,
            "sampleCount": len(pairs),
            "averageToPar": average(deltas),
            "worstToPar": max(deltas) if deltas else None,
            "refs": refs,
        })
    return sorted(out, key=lambda row: (row["courseKey"], row["hole"]))


def _clubs(data: HistoryData) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in data.shots:
        club = str(shot.get("club") or shot.get("clubName") or "Unknown")
        grouped[club].append(shot)
    out = []
    for club, shots in grouped.items():
        distances = [float(shot["distance"]) for shot in shots if shot.get("distance") is not None]
        round_ids = sorted({str(shot.get("roundId")) for shot in shots if shot.get("roundId") is not None})
        out.append({
            "club": club,
            "sampleCount": len(distances),
            "median": round(float(median(distances)), 1) if distances else None,
            "p10": percentile(distances, 0.1),
            "p90": percentile(distances, 0.9),
            "max": max(distances) if distances else None,
            "confidence": _confidence(len(distances)),
            "roundIds": round_ids,
        })
    return sorted(out, key=lambda row: row["club"])


def _issues(data: HistoryData) -> list[dict[str, Any]]:
    refs: dict[str, list[str]] = defaultdict(list)
    for row in data.rounds:
        if not row.get("hasShots"):
            refs["missing_shots"].append(_round_id(row))
        hole_pars = str(row.get("holePars") or "")
        for hole in row.get("holes") or []:
            number = int(hole.get("number") or 0)
            par = _hole_to_par(hole, _par_from_string(hole_pars, number))
            score = hole.get("strokes")
            if number and par is not None and score is not None and int(score) - int(par) >= 2:
                refs["double_or_worse"].append(f"{_round_id(row)}:{number}")
    for shot in data.shots:
        if str(shot.get("surface") or "").lower() in {"water", "bunker", "rough"}:
            refs["hazard_result"].append(f"{shot.get('roundId')}:{shot.get('hole')}")
    return [
        {"issue": issue, "count": len(items), "refs": items}
        for issue, items in sorted(refs.items())
    ]


def _data_quality(data: HistoryData) -> list[dict[str, Any]]:
    total = len(data.raw_rounds)
    shots_ready = sum(1 for row in data.raw_rounds if row.get("hasShots"))
    return [
        {
            "label": "shots",
            "state": "good" if total and shots_ready == total else "partial" if shots_ready else "missing",
            "ready": shots_ready,
            "total": total,
            "refs": [str(row.get("id")) for row in data.raw_rounds if not row.get("hasShots")],
        },
        {
            "label": "shot_rows",
            "state": "good" if data.shots else "missing",
            "ready": len(data.shots),
            "total": len(data.shots),
            "refs": [],
        },
    ]


def build_history_stats(data: HistoryData, *, data_mode: DataModeName) -> dict[str, Any]:
    return {
        "schema": "ai-caddie-history-stats-v1",
        "dataMode": data_mode,
        "summary": _summary(data),
        "time": _time_stats(data),
        "scoring": _scoring(data),
        "courses": _courses(data),
        "holes": _holes(data),
        "clubs": _clubs(data),
        "issues": _issues(data),
        "dataQuality": _data_quality(data),
        "drillDown": {
            "roundIds": [_round_id(row) for row in data.rounds],
            "shotRefs": [
                f"{shot.get('roundId')}:{shot.get('hole')}:{index}"
                for index, shot in enumerate(data.shots)
            ],
        },
    }
```

- [ ] **Step 4: Run statistics tests**

Run:

```bash
uv run python -m unittest tests.test_history_stats_core -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/history_stats.py tests/test_history_stats_core.py
git commit -m "feat: add history statistics core"
```

## Task 2: Add History Stats API

**Files:**

- Create: `server_v2/history_stats.py`
- Modify: `server_v2/models.py`
- Modify: `server_v2/main.py`
- Test: `tests/test_server_v2_history_stats.py`
- Modify: `tests/test_server_v2_health.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_server_v2_history_stats.py`:

```python
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.config import get_settings
from server_v2.main import app


class ServerV2HistoryStatsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_history_stats_endpoint_returns_fixture_statistics(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            response = TestClient(app).get("/api/v2/history/stats")
            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema"], "ai-caddie-history-stats-v1")
        self.assertEqual(payload["dataMode"], "fixture")
        self.assertEqual(payload["summary"]["totalRounds"], 3)
        self.assertGreater(len(payload["courses"]), 0)
        self.assertGreater(len(payload["clubs"]), 0)
        self.assertIn("drillDown", payload)

    def test_history_stats_endpoint_uses_public_schema_alias(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            payload = TestClient(app).get("/api/v2/history/stats").json()

        self.assertEqual(payload["schema"], "ai-caddie-history-stats-v1")
        self.assertNotIn("schema_", payload)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_history_stats -v
```

Expected:

```text
404
```

- [ ] **Step 3: Add permissive response model**

Append to `server_v2/models.py`:

```python
class HistoryStatsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["ai-caddie-history-stats-v1"] = Field(alias="schema")
    dataMode: ResolvedDataModeName
    summary: dict[str, Any]
    time: dict[str, Any]
    scoring: dict[str, Any]
    courses: list[dict[str, Any]]
    holes: list[dict[str, Any]]
    clubs: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    dataQuality: list[dict[str, Any]]
    drillDown: dict[str, Any]
```

If `Any` is not imported in `server_v2/models.py`, update the import to:

```python
from typing import Any, Literal
```

- [ ] **Step 4: Implement API loader**

Create `server_v2/history_stats.py`:

```python
from __future__ import annotations

from ai_caddie.history_stats import build_history_stats

from .data_source import load_history_data_for_mode
from .models import HistoryStatsResponse


def load_history_stats_response() -> HistoryStatsResponse:
    data, mode = load_history_data_for_mode()
    return HistoryStatsResponse(**build_history_stats(data, data_mode=mode))
```

- [ ] **Step 5: Expose endpoint**

Modify `server_v2/main.py`:

```python
from .history_stats import load_history_stats_response
```

Include `HistoryStatsResponse` in the model import:

```python
from .models import HistoryOverviewResponse, HistoryRoundsResponse, HistoryStatsResponse, SyncRunResponse, SyncStatusResponse
```

Add to service index:

```python
"historyStats": "/api/v2/history/stats",
```

Add endpoint:

```python
@app.get("/api/v2/history/stats", response_model=HistoryStatsResponse)
def history_stats() -> HistoryStatsResponse:
    return load_history_stats_response()
```

- [ ] **Step 6: Update service index test**

In `tests/test_server_v2_health.py`, add:

```python
self.assertEqual(payload["endpoints"]["historyStats"], "/api/v2/history/stats")
```

- [ ] **Step 7: Run API tests**

Run:

```bash
uv run python -m unittest tests.test_server_v2_history_stats tests.test_server_v2_health -v
```

Expected:

```text
OK
```

- [ ] **Step 8: Commit**

```bash
git add server_v2/history_stats.py server_v2/models.py server_v2/main.py tests/test_server_v2_history_stats.py tests/test_server_v2_health.py
git commit -m "feat: expose history statistics API"
```

## Task 3: Verification

**Files:**

- Verify all files changed by Tasks 1-2.

- [ ] **Step 1: Run history stats tests**

Run:

```bash
uv run python -m unittest tests.test_history_stats_core tests.test_server_v2_history_stats -v
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

Existing skipped local Garmin/prodgeometry tests are acceptable. Failures and
errors are not acceptable.

- [ ] **Step 3: Run syntax check**

Run:

```bash
uv run python -m py_compile ai_caddie/history_stats.py server_v2/history_stats.py server_v2/main.py server_v2/models.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: HTTP smoke**

If a stale server is running on 9000, restart it. Then run:

```bash
AI_CADDIE_DATA_MODE=fixture uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9001
```

In another terminal:

```bash
curl -s http://127.0.0.1:9001/api/v2/history/stats | uv run python -c 'import json,sys; d=json.load(sys.stdin); print(d["schema"], d["dataMode"], d["summary"]["totalRounds"], len(d["courses"]), len(d["clubs"]))'
```

Expected output:

```text
ai-caddie-history-stats-v1 fixture 3 2 5
```

Stop the temporary server.

- [ ] **Step 5: Final commit**

If Task 3 caused fixes, commit them:

```bash
git add ai_caddie/history_stats.py server_v2 tests
git commit -m "test: verify history statistics core"
```

If no files changed during Task 3, do not create an empty commit.

## Self-Review Checklist

- Statistics cover time, round summary, scoring, course, hole, club, issue, and data quality.
- Drill-down references exist for aggregates.
- The engine consumes `HistoryData` only and does not parse raw Garmin files.
- Fixture mode is enough to test every dimension.
- No connector/session/cookie logic appears in the stats engine.
