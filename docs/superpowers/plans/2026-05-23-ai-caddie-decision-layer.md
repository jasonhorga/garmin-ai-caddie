# AI Caddie Decision Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic tee-shot DecisionPlan and DecisionOutcome layer to the AI Caddie MVP.

**Architecture:** Create a focused `ai_caddie/decision.py` module that consumes existing hole-analysis dictionaries and returns testable JSON objects. Attach those objects to `build_hole_analysis()`, summarize them in round analysis, and render a compact card in the existing Web UI.

**Tech Stack:** Python 3.12, `unittest`, existing `ai_caddie` modules, plain HTML/CSS/JS inside `ai_caddie_web.py`.

---

### Task 1: Decision Engine Tests

**Files:**
- Create: `tests/test_decision_layer.py`

- [ ] **Step 1: Write failing tests**

Create synthetic tests for route selection, club recommendation, and outcome classification:

```python
from __future__ import annotations

import unittest

from ai_caddie.decision import build_decision_plan, judge_decision_outcome


def analysis_fixture(*, stock_risk=1, first_shot=None):
    return {
        "roundId": "round-1",
        "source": "garmin",
        "courseName": "Test Course",
        "hole": 1,
        "globalId": 100,
        "localHole": 1,
        "teeBox": "blue",
        "geometry": {"hasHazards": True, "hasMeshes": True, "hazardCount": 8},
        "dataQuality": {"confidence": "high", "issues": []},
        "clubProfiles": {
            "3H": {"clubName": "3H", "sampleSize": 44, "median": 178.0, "p10": 158.0, "p90": 198.0},
            "1W": {"clubName": "1W", "sampleSize": 81, "median": 220.0, "p10": 190.0, "p90": 248.0},
            "Putter": {"clubName": "Putter", "sampleSize": 200, "median": 8.0, "p10": 1.0, "p90": 20.0},
        },
        "candidateRoutes": [
            {
                "id": "conservative_layup",
                "label": "safe layup",
                "carry_m": 170.0,
                "landingLocal": [0.0, 170.0],
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": [],
                "riskScore": 0,
            },
            {
                "id": "stock_line",
                "label": "stock line",
                "carry_m": 180.0,
                "landingLocal": [0.0, 180.0],
                "expectedSurface": {"kind": "fairway"},
                "nearRisks": [],
                "lineRisks": [{"kind": "bunker", "id": "bunker_1"}] if stock_risk else [],
                "riskScore": stock_risk,
            },
            {
                "id": "aggressive_line",
                "label": "attack line",
                "carry_m": 220.0,
                "landingLocal": [0.0, 220.0],
                "expectedSurface": {"kind": "rough"},
                "nearRisks": [{"kind": "water", "distance_m": 9.0}],
                "lineRisks": [{"kind": "water", "id": "water_1"}],
                "riskScore": 4,
            },
        ],
        "shots": [first_shot] if first_shot else [],
    }


class DecisionLayerTests(unittest.TestCase):
    def test_selects_stock_when_nearly_as_safe_as_safe(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        self.assertEqual(plan["selectedOptionId"], "stock")
        self.assertEqual(plan["selectedOption"]["routeId"], "stock_line")

    def test_selects_safe_when_stock_is_materially_riskier(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=3))
        self.assertEqual(plan["selectedOptionId"], "safe")

    def test_recommends_clubs_near_option_carry(self) -> None:
        plan = build_decision_plan(analysis_fixture(stock_risk=1))
        clubs = [club["clubName"] for club in plan["selectedOption"]["clubRecommendation"]["clubs"]]
        self.assertIn("3H", clubs)
        self.assertNotIn("Putter", clubs)

    def test_outcome_execution_when_selected_plan_hits_known_risk(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "3H",
            "meters": 181.0,
            "end": {
                "lie": "Bunker",
                "feature": {
                    "surface": {"kind": "bunker"},
                    "nearRisks": [{"kind": "bunker", "distance_m": 0.0}],
                },
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["failureType"], "execution")
        self.assertTrue(outcome["executionMatch"]["riskTriggered"])

    def test_outcome_strategy_when_player_takes_riskier_option_and_hits_risk(self) -> None:
        shot = {
            "shotOrder": 1,
            "clubName": "1W",
            "meters": 221.0,
            "end": {
                "lie": "Water",
                "feature": {
                    "surface": {"kind": "water"},
                    "nearRisks": [{"kind": "water", "distance_m": 0.0}],
                },
            },
        }
        analysis = analysis_fixture(stock_risk=1, first_shot=shot)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["actualOptionId"], "attack")
        self.assertEqual(outcome["failureType"], "strategy")

    def test_outcome_info_gap_without_first_shot(self) -> None:
        analysis = analysis_fixture(stock_risk=1)
        plan = build_decision_plan(analysis)
        outcome = judge_decision_outcome(plan, analysis)
        self.assertEqual(outcome["failureType"], "info_gap")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_decision_layer -v`

Expected: fail with `ModuleNotFoundError: No module named 'ai_caddie.decision'`.

### Task 2: Decision Engine Implementation

**Files:**
- Create: `ai_caddie/decision.py`
- Test: `tests/test_decision_layer.py`

- [ ] **Step 1: Implement `build_decision_plan()` and `judge_decision_outcome()`**

Implement pure functions that satisfy the tests and return JSON-safe dictionaries.

- [ ] **Step 2: Run focused tests**

Run: `uv run python -m unittest tests.test_decision_layer -v`

Expected: all `DecisionLayerTests` pass.

### Task 3: Attach Decisions To Hole And Round Analysis

**Files:**
- Modify: `ai_caddie/analysis.py`
- Test: `tests/test_decision_layer.py`, `tests/test_ai_caddie.py`

- [ ] **Step 1: Attach decision objects in `build_hole_analysis()`**

After assembling the analysis dict, compute `decisionPlan` and `decisionOutcome`.

- [ ] **Step 2: Include decision facts in LLM brief and round hole summaries**

Expose selected option and failure type in `_hole_summary()` and round brief data.

- [ ] **Step 3: Run tests**

Run: `uv run python -m unittest tests.test_decision_layer tests.test_ai_caddie -v`

Expected: focused decision tests pass; existing fixture-dependent tests may skip when private data is absent.

### Task 4: Render Decision Card In Web MVP

**Files:**
- Modify: `ai_caddie_web.py`

- [ ] **Step 1: Add decision-card CSS and DOM target**

Add a compact card slot above the overlay in the review section.

- [ ] **Step 2: Render selected option, avoid list, evidence, confidence, and outcome**

Update `renderAnalysis()` to fill the card from `a.decisionPlan` and `a.decisionOutcome`.

- [ ] **Step 3: Add decision columns to round summary**

Show selected option and failure type in the round holes table.

### Task 5: Final Verification

**Files:**
- Verify all changed Python and Web files.

- [ ] **Step 1: Compile changed Python**

Run: `uv run python -m py_compile ai_caddie/decision.py ai_caddie/analysis.py ai_caddie_web.py`

Expected: exit code 0.

- [ ] **Step 2: Run full tests**

Run: `uv run python -m unittest discover -s tests -v`

Expected: all non-fixture tests pass; private-data tests may skip if fixtures are absent.
