# History Review v2 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first Garmin Pro History Review v2 UI pass in the existing local Web app.

**Architecture:** Keep existing Python service functions in `ai_caddie/history.py` where possible. Add presentation-focused helpers inside `ai_caddie_web.py` for score strips, data badges, round cards, distribution bands, and annual/quarterly panels. Avoid changing the data model unless a specific UI cannot be supported by existing history APIs.

**Tech Stack:** Python 3.12, `unittest`, existing `ThreadingHTTPServer` app, plain HTML/CSS/JS.

---

### Task 1: Score Semantics And Round Card Tests

**Files:**
- Create: `tests/test_history_ui_contract.py`
- Modify later: `ai_caddie/history.py`

- [ ] **Step 1: Write failing tests for score semantics**

Add tests that validate the history layer can expose per-hole score classes for a round:

```python
from __future__ import annotations

import unittest

from ai_caddie.history import score_class_for_hole, round_score_strip


class HistoryUiContractTests(unittest.TestCase):
    def test_score_class_for_hole_uses_garmin_pro_semantics(self) -> None:
        self.assertEqual(score_class_for_hole(3, 5), "eagle")
        self.assertEqual(score_class_for_hole(3, 4), "birdie")
        self.assertEqual(score_class_for_hole(4, 4), "par")
        self.assertEqual(score_class_for_hole(5, 4), "bogey")
        self.assertEqual(score_class_for_hole(6, 4), "double")

    def test_round_score_strip_returns_cells_with_score_and_class(self) -> None:
        row = {
            "holes": [
                {"number": 1, "strokes": 4},
                {"number": 2, "strokes": 3},
                {"number": 3, "strokes": 6},
            ],
            "holePars": "454",
        }
        strip = round_score_strip(row)
        self.assertEqual(strip, [
            {"hole": 1, "score": 4, "par": 4, "toPar": 0, "class": "par"},
            {"hole": 2, "score": 3, "par": 5, "toPar": -2, "class": "eagle"},
            {"hole": 3, "score": 6, "par": 4, "toPar": 2, "class": "double"},
        ])
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `uv run python -m unittest tests.test_history_ui_contract -v`

Expected: fail because `score_class_for_hole` and `round_score_strip` do not exist.

### Task 2: History UI Contract Helpers

**Files:**
- Modify: `ai_caddie/history.py`
- Test: `tests/test_history_ui_contract.py`

- [ ] **Step 1: Implement `score_class_for_hole()` and `round_score_strip()`**

Add helpers near existing score/hole utility functions in `ai_caddie/history.py`.

- [ ] **Step 2: Include `scoreStrip` in `_round_public()` when holes are included**

When `include_holes=True`, add `scoreStrip`.

- [ ] **Step 3: Run focused tests**

Run: `uv run python -m unittest tests.test_history_ui_contract -v`

Expected: pass.

### Task 3: Web Visual System CSS

**Files:**
- Modify: `ai_caddie_web.py`

- [ ] **Step 1: Add Garmin Pro CSS tokens**

Add CSS variables and component classes for:

- score strip cells
- history hero metrics
- history module tiles
- round cards
- distribution bands
- data quality chips

- [ ] **Step 2: Run JS syntax check**

Run:

```bash
uv run python - <<'PY' | node --check -
from ai_caddie_web import INDEX_HTML
start = INDEX_HTML.index('<script>') + len('<script>')
end = INDEX_HTML.index('</script>', start)
print(INDEX_HTML[start:end])
PY
```

Expected: exit code 0.

### Task 4: History Overview v2

**Files:**
- Modify: `ai_caddie_web.py`

- [ ] **Step 1: Add JS helpers**

Add functions:

- `scoreClassCell(cell)`
- `scoreStripHtml(strip)`
- `dataBadge(label, state)`
- `historyRoundCard(round)`
- `historyModuleTile(label, value, sub, view)`

- [ ] **Step 2: Update `renderHistoryOverview()`**

Render:

- top metrics
- recent form
- recent round cards
- score distribution mini panel
- data quality chips
- module tiles

- [ ] **Step 3: Run syntax check**

Use the same `node --check` command from Task 3.

### Task 5: Timeline v2

**Files:**
- Modify: `ai_caddie_web.py`
- Possibly modify: `ai_caddie/history.py` if `scoreStrip` is needed in API output

- [ ] **Step 1: Update `renderHistoryRounds()` for month grouping**

Replace the plain table timeline with month sections and round cards.

- [ ] **Step 2: Keep scorecards view separate**

Do not remove the scorecard table/detail view. Timeline should become visual; scorecards can remain denser.

- [ ] **Step 3: Run syntax check**

Use the same `node --check` command from Task 3.

### Task 6: Distribution v2

**Files:**
- Modify: `ai_caddie_web.py`

- [ ] **Step 1: Render pyramid + histogram**

Use Garmin Pro color semantics:

- 70s: deep blue
- 80s: light blue
- 90s: amber
- 100+: red

- [ ] **Step 2: Add selected-band round list if API data is available**

If existing APIs do not include round lists by band, show a clear placeholder
and leave a follow-up task rather than over-expanding scope.

- [ ] **Step 3: Run syntax check**

Use the same `node --check` command from Task 3.

### Task 7: Annual / Quarterly Summary

**Files:**
- Modify: `ai_caddie/history.py`
- Modify: `ai_caddie_web.py`
- Test: `tests/test_history_ui_contract.py`

- [ ] **Step 1: Add or extend history API data for annual/quarterly scoring events**

If current `history_trends()` quarterly data lacks birdie/par/bogey/double
counts, add a focused helper that computes these from hole scores.

- [ ] **Step 2: Write failing tests for scoring event aggregation**

Add synthetic tests in `tests/test_history_ui_contract.py`.

- [ ] **Step 3: Implement the aggregation**

Keep it pure and testable.

- [ ] **Step 4: Render annual/quarterly cards**

Update the History tab annual/trends view to show the cards.

- [ ] **Step 5: Run focused and full tests**

Run:

```bash
uv run python -m unittest tests.test_history_ui_contract -v
uv run python -m unittest discover -s tests -v
```

### Task 8: Final Verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Compile changed Python**

Run:

```bash
uv run python -m py_compile ai_caddie/history.py ai_caddie_web.py
```

Expected: exit code 0.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected: all non-fixture tests pass; private-data tests may skip if fixtures are absent.

- [ ] **Step 3: Run JS syntax check**

Run:

```bash
uv run python - <<'PY' | node --check -
from ai_caddie_web import INDEX_HTML
start = INDEX_HTML.index('<script>') + len('<script>')
end = INDEX_HTML.index('</script>', start)
print(INDEX_HTML[start:end])
PY
```

Expected: exit code 0.
