# AI Caddie v2 Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first clean v2 vertical slice: FastAPI API, React/Vite/TypeScript Web app, and a Garmin Pro History Overview backed by existing Python engine data.

**Architecture:** Keep `ai_caddie/` as the Python engine and freeze `ai_caddie_web.py` as a prototype/debug surface. Add `server_v2/` as a versioned FastAPI adapter over engine functions, then add `web_v2/` as the new product frontend. The first slice exposes `/api/v2/health` and `/api/v2/history/overview`, renders empty-safe history UI, and does not refactor old engine internals unless a contract test requires it.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Uvicorn, unittest, React, Vite, TypeScript, Vitest, Testing Library.

---

## File Structure

Create:

- `server_v2/__init__.py`  
  Package marker.

- `server_v2/models.py`  
  Pydantic response contracts for v2 API DTOs.

- `server_v2/history_overview.py`  
  Adapter from `ai_caddie.history.HistoryData` to v2 overview DTOs. Owns score-strip semantics and empty-safe overview assembly.

- `server_v2/main.py`  
  FastAPI app, CORS, `/api/v2/health`, `/api/v2/history/overview`.

- `tests/test_server_v2_health.py`  
  API shell test.

- `tests/test_server_v2_history_overview.py`  
  Synthetic history contract tests independent of private Garmin fixtures.

- `web_v2/`  
  Vite React TypeScript app.

- `web_v2/src/types.ts`  
  Frontend copies of v2 history overview DTOs.

- `web_v2/src/api.ts`  
  Typed fetch helper.

- `web_v2/src/components/ScoreStrip.tsx`  
  Fixed-cell score strip.

- `web_v2/src/components/DataQualityChips.tsx`  
  Coverage/confidence chips.

- `web_v2/src/components/RoundCard.tsx`  
  Garmin-style compact round card.

- `web_v2/src/components/DistributionPanel.tsx`  
  Score distribution summary.

- `web_v2/src/components/HistoryOverview.tsx`  
  First v2 product screen.

- `web_v2/src/components/HistoryOverview.test.tsx`  
  Component smoke test with synthetic API response.

- `web_v2/src/styles.css`  
  Garmin Pro visual tokens and component styles.

Modify:

- `pyproject.toml`  
  Add FastAPI/Uvicorn dependencies.

- `package.json`  
  Keep existing root geometry scripts; no need to merge Web scripts into root in this slice.

Do not modify:

- `ai_caddie_web.py`, unless a compile/test failure unrelated to v2 blocks the work.

---

### Task 1: FastAPI Shell

**Files:**

- Modify: `pyproject.toml`
- Create: `server_v2/__init__.py`
- Create: `server_v2/main.py`
- Create: `tests/test_server_v2_health.py`

- [ ] **Step 1: Add backend API dependencies**

Run:

```bash
uv add fastapi "uvicorn[standard]"
```

Expected:

- `pyproject.toml` contains `fastapi` and `uvicorn`.
- `uv.lock` updates.

- [ ] **Step 2: Write failing health endpoint test**

Create `tests/test_server_v2_health.py`:

```python
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server_v2.main import app


class ServerV2HealthTests(unittest.TestCase):
    def test_health_endpoint_returns_versioned_status(self) -> None:
        client = TestClient(app)

        response = client.get("/api/v2/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "schema": "ai-caddie-health-v2",
            "status": "ok",
            "service": "server_v2",
        })


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the focused test and verify it fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_health -v
```

Expected:

- FAIL with `ModuleNotFoundError: No module named 'server_v2'` or import error for `server_v2.main`.

- [ ] **Step 4: Add the FastAPI app**

Create `server_v2/__init__.py`:

```python
"""Versioned FastAPI server for AI Caddie v2."""
```

Create `server_v2/main.py`:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="AI Caddie v2", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/v2/health")
def health() -> dict[str, str]:
    return {
        "schema": "ai-caddie-health-v2",
        "status": "ok",
        "service": "server_v2",
    }
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
uv run python -m unittest tests.test_server_v2_health -v
```

Expected:

- PASS, 1 test.

- [ ] **Step 6: Commit**

Run:

```bash
git add pyproject.toml uv.lock server_v2/__init__.py server_v2/main.py tests/test_server_v2_health.py
git commit -m "feat: add ai caddie v2 api shell"
```

---

### Task 2: History Overview Contract

**Files:**

- Create: `server_v2/models.py`
- Create: `server_v2/history_overview.py`
- Create: `tests/test_server_v2_history_overview.py`
- Modify: `server_v2/main.py`

- [ ] **Step 1: Write failing synthetic contract tests**

Create `tests/test_server_v2_history_overview.py`:

```python
from __future__ import annotations

import unittest

from ai_caddie.history import HistoryData
from server_v2.history_overview import (
    build_history_overview_response,
    score_class_for_hole,
    score_strip_for_round,
)


class ServerV2HistoryOverviewTests(unittest.TestCase):
    def test_score_class_uses_garmin_pro_semantics(self) -> None:
        self.assertEqual(score_class_for_hole(3, 5), "eagle")
        self.assertEqual(score_class_for_hole(3, 4), "birdie")
        self.assertEqual(score_class_for_hole(4, 4), "par")
        self.assertEqual(score_class_for_hole(5, 4), "bogey")
        self.assertEqual(score_class_for_hole(6, 4), "double")
        self.assertEqual(score_class_for_hole(None, 4), "missing")
        self.assertEqual(score_class_for_hole(4, None), "missing")

    def test_score_strip_for_round_returns_fixed_hole_cells(self) -> None:
        row = {
            "id": 1,
            "holePars": "454",
            "holes": [
                {"number": 1, "strokes": 4},
                {"number": 2, "strokes": 3},
                {"number": 3, "strokes": 6},
            ],
        }

        cells = [cell.model_dump() for cell in score_strip_for_round(row)]

        self.assertEqual(cells, [
            {"hole": 1, "par": 4, "score": 4, "toPar": 0, "className": "par"},
            {"hole": 2, "par": 5, "score": 3, "toPar": -2, "className": "eagle"},
            {"hole": 3, "par": 4, "score": 6, "toPar": 2, "className": "double"},
        ])

    def test_empty_history_overview_is_safe(self) -> None:
        response = build_history_overview_response(HistoryData(raw_rounds=[], rounds=[], shots=[]))
        payload = response.model_dump()

        self.assertEqual(payload["schema"], "ai-caddie-history-overview-v2")
        self.assertEqual(payload["metrics"]["totalRounds"], 0)
        self.assertEqual(payload["recentRounds"], [])
        self.assertEqual(payload["distribution"]["total"], 0)
        self.assertEqual(payload["emptyState"]["kind"], "no_rounds")

    def test_history_overview_builds_metrics_rounds_distribution_and_quality(self) -> None:
        data = HistoryData(
            raw_rounds=[
                {"id": 1, "hasShots": True},
                {"id": 2, "hasShots": False},
            ],
            rounds=[
                {
                    "id": 1,
                    "ids": [1],
                    "date": "2026-05-20",
                    "course": "Black Knight B",
                    "courseCanonical": "Black Knight",
                    "courseKey": "c_black",
                    "holesCompleted": 18,
                    "strokes": 82,
                    "par": 72,
                    "holePars": "444444444444444444",
                    "holes": [{"number": n, "strokes": 4} for n in range(1, 19)],
                    "hasShots": True,
                    "shotStatus": "ready",
                },
                {
                    "id": 2,
                    "ids": [2],
                    "date": "2026-05-10",
                    "course": "Pine Valley",
                    "courseCanonical": "Pine Valley",
                    "courseKey": "c_pine",
                    "holesCompleted": 18,
                    "strokes": 96,
                    "par": 72,
                    "holePars": "444444444444444444",
                    "holes": [{"number": n, "strokes": 5} for n in range(1, 19)],
                    "hasShots": False,
                    "shotStatus": "missing",
                },
            ],
            shots=[{"roundId": 1}, {"roundId": 1}],
        )

        payload = build_history_overview_response(data).model_dump()

        self.assertEqual(payload["metrics"]["totalRounds"], 2)
        self.assertEqual(payload["metrics"]["average18"], 89.0)
        self.assertEqual(payload["metrics"]["bestScore"], 82)
        self.assertEqual(payload["metrics"]["recent10Average"], 89.0)
        self.assertEqual(payload["metrics"]["courseCount"], 2)
        self.assertEqual(payload["recentRounds"][0]["id"], "1")
        self.assertEqual(payload["recentRounds"][0]["scoreStrip"][0]["className"], "par")
        self.assertEqual(payload["distribution"]["families"][1]["label"], "80s")
        self.assertEqual(payload["distribution"]["families"][1]["count"], 1)
        self.assertEqual(payload["distribution"]["families"][2]["label"], "90s")
        self.assertEqual(payload["distribution"]["families"][2]["count"], 1)
        self.assertEqual(payload["dataQuality"][0]["label"], "shots")
        self.assertEqual(payload["dataQuality"][0]["state"], "partial")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv run python -m unittest tests.test_server_v2_history_overview -v
```

Expected:

- FAIL with missing `server_v2.history_overview` or missing functions.

- [ ] **Step 3: Add v2 Pydantic models**

Create `server_v2/models.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DataQualityBadge(BaseModel):
    label: str
    state: str
    value: str
    reason: str


class ScoreStripCell(BaseModel):
    hole: int
    par: int | None
    score: int | None
    toPar: int | None
    className: str


class RoundCard(BaseModel):
    id: str
    date: str | None
    courseName: str
    courseKey: str | None
    holesCompleted: int | None
    score: int | None
    par: int | None
    toPar: int | None
    scoreStrip: list[ScoreStripCell]
    badges: list[DataQualityBadge]
    primaryIssue: str | None = None


class HistoryMetricSet(BaseModel):
    totalRounds: int
    eighteenHoleRounds: int
    nineHoleRounds: int
    courseCount: int
    shotCount: int
    average18: float | None
    recent10Average: float | None
    bestScore: int | None


class DistributionFamily(BaseModel):
    label: str
    count: int
    pct: float
    className: str


class DistributionBucket(BaseModel):
    label: str
    start: int
    count: int


class ScoreDistribution(BaseModel):
    total: int
    average: float | None
    best: int | None
    worst: int | None
    families: list[DistributionFamily]
    histogram: list[DistributionBucket]


class EmptyState(BaseModel):
    kind: str
    title: str
    detail: str


class HistoryOverviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema: str
    metrics: HistoryMetricSet
    recentRounds: list[RoundCard]
    distribution: ScoreDistribution
    dataQuality: list[DataQualityBadge]
    emptyState: EmptyState | None
```

- [ ] **Step 4: Add the history overview adapter**

Create `server_v2/history_overview.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any

from ai_caddie.history import HistoryData, average, load_history_data

from .models import (
    DataQualityBadge,
    DistributionBucket,
    DistributionFamily,
    EmptyState,
    HistoryMetricSet,
    HistoryOverviewResponse,
    RoundCard,
    ScoreDistribution,
    ScoreStripCell,
)


def score_class_for_hole(score: int | None, par: int | None) -> str:
    if score is None or par is None:
        return "missing"
    delta = int(score) - int(par)
    if delta <= -2:
        return "eagle"
    if delta == -1:
        return "birdie"
    if delta == 0:
        return "par"
    if delta == 1:
        return "bogey"
    return "double"


def _par_for_hole(hole_number: int, hole_pars: str | None) -> int | None:
    if not hole_pars or hole_number < 1 or hole_number > len(hole_pars):
        return None
    try:
        return int(hole_pars[hole_number - 1])
    except ValueError:
        return None


def score_strip_for_round(row: dict[str, Any]) -> list[ScoreStripCell]:
    hole_pars = str(row.get("holePars") or "")
    cells: list[ScoreStripCell] = []
    for index, hole in enumerate(row.get("holes") or [], start=1):
        hole_number = int(hole.get("number") or index)
        par = _par_for_hole(hole_number, hole_pars)
        score = hole.get("strokes")
        score_int = int(score) if score is not None else None
        to_par = score_int - par if score_int is not None and par is not None else None
        cells.append(ScoreStripCell(
            hole=hole_number,
            par=par,
            score=score_int,
            toPar=to_par,
            className=score_class_for_hole(score_int, par),
        ))
    return cells


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def _score_distribution(rounds18: list[dict[str, Any]]) -> ScoreDistribution:
    scores = [int(r["strokes"]) for r in rounds18 if r.get("strokes") is not None]
    families = Counter({"70s": 0, "80s": 0, "90s": 0, "100+": 0})
    histogram: Counter[int] = Counter()
    for score in scores:
        if score < 80:
            families["70s"] += 1
        elif score < 90:
            families["80s"] += 1
        elif score < 100:
            families["90s"] += 1
        else:
            families["100+"] += 1
        histogram[(score // 5) * 5] += 1
    total = len(scores)
    class_by_family = {
        "70s": "eagle",
        "80s": "birdie",
        "90s": "bogey",
        "100+": "double",
    }
    return ScoreDistribution(
        total=total,
        average=average(scores),
        best=min(scores) if scores else None,
        worst=max(scores) if scores else None,
        families=[
            DistributionFamily(
                label=label,
                count=families[label],
                pct=_pct(families[label], total),
                className=class_by_family[label],
            )
            for label in ("70s", "80s", "90s", "100+")
        ],
        histogram=[
            DistributionBucket(label=f"{start}-{start + 4}", start=start, count=histogram[start])
            for start in sorted(histogram)
        ],
    )


def _quality_badges(data: HistoryData) -> list[DataQualityBadge]:
    scorecards = len(data.raw_rounds)
    shots_ready = sum(1 for row in data.raw_rounds if row.get("hasShots"))
    shot_pct = _pct(shots_ready, scorecards)
    shot_state = "good" if shot_pct >= 90 else "partial" if shot_pct > 0 else "missing"
    return [
        DataQualityBadge(
            label="shots",
            state=shot_state,
            value=f"{shot_pct:.0f}%",
            reason=f"{shots_ready}/{scorecards} scorecards have usable shot files",
        ),
        DataQualityBadge(
            label="shot rows",
            state="good" if data.shots else "missing",
            value=str(len(data.shots)),
            reason="normalized Garmin shot rows loaded into history",
        ),
    ]


def _round_badges(row: dict[str, Any]) -> list[DataQualityBadge]:
    has_shots = bool(row.get("hasShots"))
    return [
        DataQualityBadge(
            label="shots",
            state="good" if has_shots else "missing",
            value="ready" if has_shots else "missing",
            reason=str(row.get("shotStatus") or ("ready" if has_shots else "missing")),
        )
    ]


def _round_card(row: dict[str, Any]) -> RoundCard:
    strokes = row.get("strokes")
    par = row.get("par")
    return RoundCard(
        id=str(row.get("id")),
        date=row.get("date"),
        courseName=str(row.get("course") or "Unknown course"),
        courseKey=row.get("courseKey"),
        holesCompleted=row.get("holesCompleted"),
        score=strokes,
        par=par,
        toPar=(int(strokes) - int(par)) if isinstance(strokes, int) and isinstance(par, int) else None,
        scoreStrip=score_strip_for_round(row),
        badges=_round_badges(row),
        primaryIssue=None if row.get("hasShots") else "missing_shots",
    )


def build_history_overview_response(data: HistoryData) -> HistoryOverviewResponse:
    rounds = list(data.rounds)
    rounds18 = [r for r in rounds if r.get("holesCompleted") == 18 and r.get("strokes")]
    scores18 = [int(r["strokes"]) for r in rounds18]
    recent10_scores = [int(r["strokes"]) for r in sorted(rounds18, key=lambda row: row.get("date") or "")[-10:]]
    recent_rounds = sorted(rounds, key=lambda row: row.get("date") or "", reverse=True)[:6]
    return HistoryOverviewResponse(
        schema="ai-caddie-history-overview-v2",
        metrics=HistoryMetricSet(
            totalRounds=len(rounds),
            eighteenHoleRounds=len(rounds18),
            nineHoleRounds=sum(1 for r in rounds if r.get("holesCompleted") == 9),
            courseCount=len({r.get("courseKey") for r in rounds if r.get("courseKey")}),
            shotCount=len(data.shots),
            average18=average(scores18),
            recent10Average=average(recent10_scores),
            bestScore=min(scores18) if scores18 else None,
        ),
        recentRounds=[_round_card(row) for row in recent_rounds],
        distribution=_score_distribution(rounds18),
        dataQuality=_quality_badges(data),
        emptyState=EmptyState(
            kind="no_rounds",
            title="No Garmin rounds loaded",
            detail="Fetch Garmin scorecards locally, then refresh this view.",
        ) if not rounds else None,
    )


def load_history_overview_response() -> HistoryOverviewResponse:
    return build_history_overview_response(load_history_data())
```

- [ ] **Step 5: Add the endpoint**

Modify `server_v2/main.py`:

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .history_overview import load_history_overview_response
from .models import HistoryOverviewResponse


app = FastAPI(title="AI Caddie v2", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/v2/health")
def health() -> dict[str, str]:
    return {
        "schema": "ai-caddie-health-v2",
        "status": "ok",
        "service": "server_v2",
    }


@app.get("/api/v2/history/overview", response_model=HistoryOverviewResponse)
def history_overview() -> HistoryOverviewResponse:
    return load_history_overview_response()
```

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
uv run python -m unittest tests.test_server_v2_health tests.test_server_v2_history_overview -v
```

Expected:

- PASS, 5 tests.

- [ ] **Step 7: Commit**

Run:

```bash
git add server_v2 tests/test_server_v2_health.py tests/test_server_v2_history_overview.py
git commit -m "feat: expose v2 history overview contract"
```

---

### Task 3: React/Vite v2 Scaffold

**Files:**

- Create: `web_v2/`
- Modify: `web_v2/package.json`
- Modify: `web_v2/vite.config.ts`
- Modify: `web_v2/src/main.tsx`
- Modify: `web_v2/src/App.tsx`

- [ ] **Step 1: Scaffold Vite React TypeScript**

Run:

```bash
npm create vite@latest web_v2 -- --template react-ts
cd web_v2
npm install
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Expected:

- `web_v2/package.json` exists.
- `web_v2/src/App.tsx` exists.
- `web_v2/vite.config.ts` exists.

- [ ] **Step 2: Configure Vite test and API proxy**

Replace `web_v2/vite.config.ts` with:

```typescript
/// <reference types="vitest" />

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
```

Create `web_v2/src/test/setup.ts`:

```typescript
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 3: Update Web scripts**

Ensure `web_v2/package.json` has these scripts:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "preview": "vite preview",
    "test": "vitest"
  }
}
```

Keep the dependencies generated by Vite and the dev dependencies installed in
Step 1.

- [ ] **Step 4: Run the empty scaffold build and tests**

Run:

```bash
cd web_v2
npm test -- --run --passWithNoTests
npm run build
```

Expected:

- `npm test -- --run --passWithNoTests` exits 0 with no tests or scaffold tests passing.
- `npm run build` exits 0.

- [ ] **Step 5: Commit**

Run:

```bash
git add web_v2
git commit -m "feat: scaffold ai caddie v2 web app"
```

---

### Task 4: Frontend API Types And Client

**Files:**

- Create: `web_v2/src/types.ts`
- Create: `web_v2/src/api.ts`
- Create: `web_v2/src/api.test.ts`

- [ ] **Step 1: Write failing API normalization tests**

Create `web_v2/src/api.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchHistoryOverview } from './api'

describe('fetchHistoryOverview', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the v2 history overview payload', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-overview-v2',
        metrics: {
          totalRounds: 0,
          eighteenHoleRounds: 0,
          nineHoleRounds: 0,
          courseCount: 0,
          shotCount: 0,
          average18: null,
          recent10Average: null,
          bestScore: null,
        },
        recentRounds: [],
        distribution: {
          total: 0,
          average: null,
          best: null,
          worst: null,
          families: [],
          histogram: [],
        },
        dataQuality: [],
        emptyState: {
          kind: 'no_rounds',
          title: 'No Garmin rounds loaded',
          detail: 'Fetch Garmin scorecards locally, then refresh this view.',
        },
      }),
    })))

    const payload = await fetchHistoryOverview()

    expect(payload.schema).toBe('ai-caddie-history-overview-v2')
    expect(payload.metrics.totalRounds).toBe(0)
    expect(fetch).toHaveBeenCalledWith('/api/v2/history/overview')
  })

  it('throws a useful error when the API request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    })))

    await expect(fetchHistoryOverview()).rejects.toThrow('GET /api/v2/history/overview failed: 500 Internal Server Error')
  })
})
```

- [ ] **Step 2: Run the focused frontend test and verify it fails**

Run:

```bash
cd web_v2
npm test -- --run src/api.test.ts
```

Expected:

- FAIL with missing `./api`.

- [ ] **Step 3: Add frontend DTO types**

Create `web_v2/src/types.ts`:

```typescript
export type DataQualityState = 'good' | 'partial' | 'missing'
export type ScoreClass = 'eagle' | 'birdie' | 'par' | 'bogey' | 'double' | 'missing'

export interface DataQualityBadge {
  label: string
  state: DataQualityState
  value: string
  reason: string
}

export interface ScoreStripCell {
  hole: number
  par: number | null
  score: number | null
  toPar: number | null
  className: ScoreClass
}

export interface RoundCard {
  id: string
  date: string | null
  courseName: string
  courseKey: string | null
  holesCompleted: number | null
  score: number | null
  par: number | null
  toPar: number | null
  scoreStrip: ScoreStripCell[]
  badges: DataQualityBadge[]
  primaryIssue: string | null
}

export interface HistoryMetricSet {
  totalRounds: number
  eighteenHoleRounds: number
  nineHoleRounds: number
  courseCount: number
  shotCount: number
  average18: number | null
  recent10Average: number | null
  bestScore: number | null
}

export interface DistributionFamily {
  label: string
  count: number
  pct: number
  className: Exclude<ScoreClass, 'missing'>
}

export interface DistributionBucket {
  label: string
  start: number
  count: number
}

export interface ScoreDistribution {
  total: number
  average: number | null
  best: number | null
  worst: number | null
  families: DistributionFamily[]
  histogram: DistributionBucket[]
}

export interface EmptyState {
  kind: string
  title: string
  detail: string
}

export interface HistoryOverviewResponse {
  schema: 'ai-caddie-history-overview-v2'
  metrics: HistoryMetricSet
  recentRounds: RoundCard[]
  distribution: ScoreDistribution
  dataQuality: DataQualityBadge[]
  emptyState: EmptyState | null
}
```

- [ ] **Step 4: Add typed fetch helper**

Create `web_v2/src/api.ts`:

```typescript
import type { HistoryOverviewResponse } from './types'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`GET ${path} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export function fetchHistoryOverview(): Promise<HistoryOverviewResponse> {
  return getJson<HistoryOverviewResponse>('/api/v2/history/overview')
}
```

- [ ] **Step 5: Run the focused frontend test and verify it passes**

Run:

```bash
cd web_v2
npm test -- --run src/api.test.ts
```

Expected:

- PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add web_v2/src/types.ts web_v2/src/api.ts web_v2/src/api.test.ts
git commit -m "feat: add v2 history api client"
```

---

### Task 5: Garmin Pro History Components

**Files:**

- Create: `web_v2/src/components/ScoreStrip.tsx`
- Create: `web_v2/src/components/DataQualityChips.tsx`
- Create: `web_v2/src/components/RoundCard.tsx`
- Create: `web_v2/src/components/DistributionPanel.tsx`
- Create: `web_v2/src/components/HistoryOverview.tsx`
- Create: `web_v2/src/components/HistoryOverview.test.tsx`
- Replace: `web_v2/src/styles.css`
- Modify: `web_v2/src/App.tsx`
- Modify: `web_v2/src/main.tsx`

- [ ] **Step 1: Write failing component smoke test**

Create `web_v2/src/components/HistoryOverview.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HistoryOverview } from './HistoryOverview'
import type { HistoryOverviewResponse } from '../types'

const payload: HistoryOverviewResponse = {
  schema: 'ai-caddie-history-overview-v2',
  metrics: {
    totalRounds: 2,
    eighteenHoleRounds: 2,
    nineHoleRounds: 0,
    courseCount: 2,
    shotCount: 42,
    average18: 89,
    recent10Average: 89,
    bestScore: 82,
  },
  recentRounds: [
    {
      id: '1',
      date: '2026-05-20',
      courseName: 'Black Knight B',
      courseKey: 'c_black',
      holesCompleted: 18,
      score: 82,
      par: 72,
      toPar: 10,
      primaryIssue: null,
      badges: [{ label: 'shots', state: 'good', value: 'ready', reason: 'ready' }],
      scoreStrip: [
        { hole: 1, par: 4, score: 4, toPar: 0, className: 'par' },
        { hole: 2, par: 5, score: 4, toPar: -1, className: 'birdie' },
      ],
    },
  ],
  distribution: {
    total: 2,
    average: 89,
    best: 82,
    worst: 96,
    families: [
      { label: '70s', count: 0, pct: 0, className: 'eagle' },
      { label: '80s', count: 1, pct: 50, className: 'birdie' },
      { label: '90s', count: 1, pct: 50, className: 'bogey' },
      { label: '100+', count: 0, pct: 0, className: 'double' },
    ],
    histogram: [
      { label: '80-84', start: 80, count: 1 },
      { label: '95-99', start: 95, count: 1 },
    ],
  },
  dataQuality: [{ label: 'shots', state: 'partial', value: '50%', reason: '1/2 scorecards have usable shot files' }],
  emptyState: null,
}

describe('HistoryOverview', () => {
  it('renders metrics, recent rounds, score strip, distribution, and quality chips', () => {
    render(<HistoryOverview data={payload} />)

    expect(screen.getByText('History Overview')).toBeInTheDocument()
    expect(screen.getByText('Total rounds')).toBeInTheDocument()
    expect(screen.getAllByText('2').length).toBeGreaterThan(0)
    expect(screen.getByText('Black Knight B')).toBeInTheDocument()
    expect(screen.getByLabelText('Hole 2: birdie')).toBeInTheDocument()
    expect(screen.getByText('80s')).toBeInTheDocument()
    expect(screen.getByText('shots')).toBeInTheDocument()
  })

  it('renders the empty state without round cards', () => {
    render(<HistoryOverview data={{ ...payload, metrics: { ...payload.metrics, totalRounds: 0 }, recentRounds: [], emptyState: { kind: 'no_rounds', title: 'No Garmin rounds loaded', detail: 'Fetch Garmin scorecards locally, then refresh this view.' } }} />)

    expect(screen.getByText('No Garmin rounds loaded')).toBeInTheDocument()
    expect(screen.queryByText('Black Knight B')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the focused component test and verify it fails**

Run:

```bash
cd web_v2
npm test -- --run src/components/HistoryOverview.test.tsx
```

Expected:

- FAIL with missing `HistoryOverview`.

- [ ] **Step 3: Add score strip component**

Create `web_v2/src/components/ScoreStrip.tsx`:

```tsx
import type { CSSProperties } from 'react'
import type { ScoreStripCell } from '../types'

interface ScoreStripProps {
  cells: ScoreStripCell[]
}

export function ScoreStrip({ cells }: ScoreStripProps) {
  return (
    <div className="score-strip" style={{ '--score-cells': Math.max(cells.length, 1) } as CSSProperties}>
      {cells.map((cell) => (
        <span
          key={cell.hole}
          className={`score-cell score-${cell.className}`}
          aria-label={`Hole ${cell.hole}: ${cell.className}`}
          title={`Hole ${cell.hole} · par ${cell.par ?? '-'} · score ${cell.score ?? '-'}`}
        >
          {cell.score ?? '-'}
        </span>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Add data quality chips component**

Create `web_v2/src/components/DataQualityChips.tsx`:

```tsx
import type { DataQualityBadge } from '../types'

interface DataQualityChipsProps {
  badges: DataQualityBadge[]
}

export function DataQualityChips({ badges }: DataQualityChipsProps) {
  if (badges.length === 0) {
    return null
  }
  return (
    <div className="quality-row">
      {badges.map((badge) => (
        <span key={`${badge.label}-${badge.value}`} className={`quality-chip quality-${badge.state}`} title={badge.reason}>
          <span>{badge.label}</span>
          <b>{badge.value}</b>
        </span>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Add round card component**

Create `web_v2/src/components/RoundCard.tsx`:

```tsx
import type { RoundCard as RoundCardType } from '../types'
import { DataQualityChips } from './DataQualityChips'
import { ScoreStrip } from './ScoreStrip'

function formatToPar(value: number | null) {
  if (value === null) return '-'
  if (value > 0) return `+${value}`
  return String(value)
}

interface RoundCardProps {
  round: RoundCardType
}

export function RoundCard({ round }: RoundCardProps) {
  return (
    <article className="round-card">
      <div className="round-card-head">
        <div>
          <h3>{round.courseName}</h3>
          <p>{round.date ?? 'Unknown date'} · {round.holesCompleted ?? '-'}H</p>
        </div>
        <div className="round-score">
          <strong>{round.score ?? '-'}</strong>
          <span>{formatToPar(round.toPar)}</span>
        </div>
      </div>
      <ScoreStrip cells={round.scoreStrip} />
      <DataQualityChips badges={round.badges} />
    </article>
  )
}
```

- [ ] **Step 6: Add distribution component**

Create `web_v2/src/components/DistributionPanel.tsx`:

```tsx
import type { ScoreDistribution } from '../types'

interface DistributionPanelProps {
  distribution: ScoreDistribution
}

export function DistributionPanel({ distribution }: DistributionPanelProps) {
  const maxFamily = Math.max(...distribution.families.map((family) => family.count), 1)
  const maxBucket = Math.max(...distribution.histogram.map((bucket) => bucket.count), 1)

  return (
    <section className="panel distribution-panel" aria-label="Score distribution">
      <div className="section-head">
        <div>
          <h2>Score Distribution</h2>
          <p>{distribution.total} eighteen-hole rounds · avg {distribution.average ?? '-'}</p>
        </div>
      </div>
      <div className="distribution-grid">
        <div className="pyramid">
          {distribution.families.map((family) => (
            <div key={family.label} className="pyramid-row">
              <span>{family.label}</span>
              <div className="pyramid-track">
                <i className={`score-${family.className}`} style={{ width: `${Math.max(6, (family.count / maxFamily) * 100)}%` }} />
              </div>
              <b>{family.count}</b>
            </div>
          ))}
        </div>
        <div className="histogram">
          {distribution.histogram.map((bucket) => (
            <div key={bucket.label} className="histogram-row">
              <span>{bucket.label}</span>
              <i style={{ width: `${Math.max(6, (bucket.count / maxBucket) * 100)}%` }} />
              <b>{bucket.count}</b>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 7: Add History Overview component**

Create `web_v2/src/components/HistoryOverview.tsx`:

```tsx
import type { HistoryOverviewResponse } from '../types'
import { DataQualityChips } from './DataQualityChips'
import { DistributionPanel } from './DistributionPanel'
import { RoundCard } from './RoundCard'

interface HistoryOverviewProps {
  data: HistoryOverviewResponse
}

function metricValue(value: number | null) {
  return value === null ? '-' : String(value)
}

export function HistoryOverview({ data }: HistoryOverviewProps) {
  const metrics = data.metrics

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true" />
        <nav>
          <a className="active">Overview</a>
          <a>History</a>
          <a>Rounds</a>
          <a>Courses</a>
          <a>Clubs</a>
          <a>Caddie</a>
        </nav>
      </header>

      <section className="overview-hero">
        <div>
          <p className="eyebrow">AI Caddie v2</p>
          <h1>History Overview</h1>
          <p className="lead">Round memory, scoring shape, and data confidence in one Garmin Pro surface.</p>
        </div>
        <DataQualityChips badges={data.dataQuality} />
      </section>

      {data.emptyState ? (
        <section className="panel empty-state">
          <h2>{data.emptyState.title}</h2>
          <p>{data.emptyState.detail}</p>
        </section>
      ) : null}

      <section className="metric-grid" aria-label="History metrics">
        <article className="metric-card"><span>Total rounds</span><b>{metrics.totalRounds}</b></article>
        <article className="metric-card"><span>18H average</span><b>{metricValue(metrics.average18)}</b></article>
        <article className="metric-card"><span>Recent 10</span><b>{metricValue(metrics.recent10Average)}</b></article>
        <article className="metric-card"><span>Best score</span><b>{metricValue(metrics.bestScore)}</b></article>
        <article className="metric-card"><span>Courses</span><b>{metrics.courseCount}</b></article>
        <article className="metric-card"><span>Shot rows</span><b>{metrics.shotCount}</b></article>
      </section>

      <section className="content-grid">
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Recent Rounds</h2>
              <p>Newest Garmin rounds with score shape and coverage.</p>
            </div>
          </div>
          <div className="round-list">
            {data.recentRounds.map((round) => (
              <RoundCard key={round.id} round={round} />
            ))}
          </div>
        </section>

        <DistributionPanel distribution={data.distribution} />
      </section>
    </main>
  )
}
```

- [ ] **Step 8: Wire App to API**

Replace `web_v2/src/App.tsx` with:

```tsx
import { useEffect, useState } from 'react'
import { fetchHistoryOverview } from './api'
import { HistoryOverview } from './components/HistoryOverview'
import type { HistoryOverviewResponse } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: HistoryOverviewResponse }
  | { status: 'error'; message: string }

export default function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetchHistoryOverview()
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (state.status === 'loading') {
    return <main className="app-shell"><section className="panel empty-state"><h1>Loading history</h1></section></main>
  }

  if (state.status === 'error') {
    return <main className="app-shell"><section className="panel empty-state"><h1>History API unavailable</h1><p>{state.message}</p></section></main>
  }

  return <HistoryOverview data={state.data} />
}
```

Replace `web_v2/src/main.tsx` with:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 9: Add Garmin Pro CSS**

Replace `web_v2/src/styles.css` with:

```css
:root {
  color: #18231f;
  background: #f4f6f2;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  --bg: #f4f6f2;
  --panel: #ffffff;
  --ink: #18231f;
  --muted: #66736d;
  --line: #d9ded7;
  --green: #1f6b4c;
  --eagle: #184a90;
  --birdie: #5aa8d8;
  --par: #2f8f5f;
  --bogey: #d39a45;
  --double: #b55349;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background: var(--bg);
}

a { color: inherit; text-decoration: none; }

.app-shell {
  width: min(1320px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 18px 0 32px;
}

.topbar {
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid var(--line);
}

.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  background: conic-gradient(from 210deg, var(--green), #7eb66a, #d7ba75, #477ea8, var(--green));
  box-shadow: inset 0 0 0 2px rgba(255,255,255,.82);
  flex: 0 0 auto;
}

nav {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

nav a {
  border-radius: 7px;
  padding: 7px 10px;
  white-space: nowrap;
}

nav a.active {
  color: var(--green);
  background: #e9f2ea;
}

.overview-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: end;
  padding: 28px 0 18px;
}

.eyebrow {
  margin: 0 0 6px;
  color: var(--green);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

h1, h2, h3, p { margin: 0; }
h1 { font-size: 34px; line-height: 1.1; letter-spacing: 0; }
h2 { font-size: 18px; line-height: 1.25; }
h3 { font-size: 15px; line-height: 1.25; }
p { color: var(--muted); line-height: 1.5; }
.lead { margin-top: 8px; max-width: 680px; }

.panel,
.metric-card,
.round-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16,24,40,.04);
}

.panel { padding: 16px; }

.empty-state {
  margin-bottom: 16px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  min-height: 86px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.metric-card span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.metric-card b {
  color: var(--ink);
  font-size: 28px;
  line-height: 1;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.18fr) minmax(360px, .82fr);
  gap: 14px;
  align-items: start;
  margin-top: 14px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.round-list {
  display: grid;
  gap: 10px;
}

.round-card {
  padding: 12px;
}

.round-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.round-card h3 {
  max-width: 100%;
}

.round-card p {
  margin-top: 3px;
  font-size: 12px;
}

.round-score {
  text-align: right;
  display: grid;
  gap: 2px;
}

.round-score strong {
  font-size: 32px;
  line-height: 1;
}

.round-score span {
  color: var(--muted);
  font-weight: 800;
}

.score-strip {
  --score-cells: 18;
  display: grid;
  grid-template-columns: repeat(var(--score-cells), minmax(18px, 1fr));
  gap: 3px;
  margin-top: 11px;
}

.score-cell {
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 4px;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  background: #94a3a0;
}

.score-eagle { background: var(--eagle); border-radius: 999px; }
.score-birdie { background: var(--birdie); border-radius: 999px; }
.score-par { background: var(--par); }
.score-bogey { background: var(--bogey); }
.score-double { background: var(--double); }
.score-missing { background: #94a3a0; }

.quality-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.quality-chip {
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 760;
}

.quality-chip span {
  color: inherit;
}

.quality-chip b {
  font-size: 11px;
}

.quality-good { color: #275542; background: #e6f2e9; }
.quality-partial { color: #7a4f16; background: #fff3d8; }
.quality-missing { color: #8f3028; background: #f8e5e2; }

.distribution-grid {
  display: grid;
  gap: 14px;
}

.pyramid,
.histogram {
  display: grid;
  gap: 8px;
}

.pyramid-row,
.histogram-row {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) 34px;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  font-weight: 760;
}

.pyramid-track,
.histogram-row i {
  height: 16px;
  border-radius: 999px;
  background: #e8ede9;
  overflow: hidden;
}

.pyramid-track i,
.histogram-row i {
  display: block;
  height: 16px;
  border-radius: 999px;
}

.histogram-row i {
  background: var(--green);
}

@media (max-width: 900px) {
  .overview-hero,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .app-shell {
    width: min(100vw - 20px, 1320px);
    padding-top: 10px;
  }

  .topbar {
    align-items: flex-start;
    height: auto;
    padding-bottom: 10px;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .score-strip {
    grid-template-columns: repeat(9, minmax(20px, 1fr));
  }
}
```

- [ ] **Step 10: Run focused component tests**

Run:

```bash
cd web_v2
npm test -- --run src/components/HistoryOverview.test.tsx
```

Expected:

- PASS.

- [ ] **Step 11: Run frontend build**

Run:

```bash
cd web_v2
npm run build
```

Expected:

- TypeScript and Vite build pass.

- [ ] **Step 12: Commit**

Run:

```bash
git add web_v2/src
git commit -m "feat: build garmin pro history overview"
```

---

### Task 6: Full Local Verification And Dev Server

**Files:**

- Verify all v2 files.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
uv run python -m unittest tests.test_server_v2_health tests.test_server_v2_history_overview -v
```

Expected:

- PASS.

- [ ] **Step 2: Run full backend suite**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected:

- Existing fixture-dependent tests may skip when private data is absent.
- No non-skipped test should fail.

- [ ] **Step 3: Compile v2 Python**

Run:

```bash
uv run python -m py_compile server_v2/__init__.py server_v2/models.py server_v2/history_overview.py server_v2/main.py
```

Expected:

- Exit code 0.

- [ ] **Step 4: Run frontend tests and build**

Run:

```bash
cd web_v2
npm test -- --run
npm run build
```

Expected:

- Vitest passes.
- TypeScript/Vite build passes.

- [ ] **Step 5: Start backend server**

Run:

```bash
uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000
```

Expected:

- Server listens on `http://127.0.0.1:9000`.
- In another shell, `curl http://127.0.0.1:9000/api/v2/health` returns the health JSON.

- [ ] **Step 6: Start frontend dev server**

Run:

```bash
cd web_v2
npm run dev -- --host 127.0.0.1 --port 5173
```

Expected:

- Vite serves `http://127.0.0.1:5173`.
- The page renders either the empty state or real History Overview.

- [ ] **Step 7: Commit verification adjustments if needed**

Only commit if verification required code changes:

```bash
git add server_v2 web_v2 tests pyproject.toml uv.lock
git commit -m "test: verify ai caddie v2 vertical slice"
```

---

## Self-Review

Spec coverage:

- Prototype freeze: Task 1-6 create v2 paths and do not modify `ai_caddie_web.py`.
- Python backend: Task 1-2 add FastAPI over existing engine.
- React frontend: Task 3-5 add Vite/React/TypeScript app.
- History/statistics priority: Task 2 and Task 5 implement History Overview.
- Garmin Pro visual language: Task 5 implements scoring colors, score strips,
  round cards, data chips, and distribution panel.
- Data quality: Task 2 creates quality badges; Task 5 renders them.
- Empty-safe remote behavior: Task 2 tests empty data; Task 5 renders empty
  state.

Marker scan:

- No implementation step uses unresolved marker language.
- All new files have concrete code or concrete commands.
- Follow-up pages are intentionally outside this first vertical slice and are
  not required to satisfy the plan.

Type consistency:

- Backend `className` maps directly to frontend `ScoreClass`.
- Backend `HistoryOverviewResponse` field names match frontend
  `HistoryOverviewResponse`.
- API path is consistently `/api/v2/history/overview`.

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-05-24-ai-caddie-v2-rebuild.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.
