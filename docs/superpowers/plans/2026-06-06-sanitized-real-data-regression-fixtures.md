# Sanitized Real-Data Regression Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CI-safe sanitized regression tests for real Garmin data shapes without committing private Garmin files.

**Architecture:** Add one focused unittest module that creates Garmin-like scorecard, shot, and geometry files inside `TemporaryDirectory`. The tests drive existing snapshot/history/data-quality functions; production changes are limited to the snapshot shot-file classifier if the pin-only RED test exposes the current ready/missing distinction gap.

**Tech Stack:** Python 3.12, unittest, temporary filesystem fixtures, `ai_caddie.connectors.snapshot`, `ai_caddie.history`.

---

## Files

- Create: `tests/test_real_data_shape_regressions.py`
  - Owns all sanitized real-data shape tests and small test-only fixture builders.
- Modify: `ai_caddie/connectors/snapshot.py`
  - Only if the pin-only RED test fails because `_shot_file_ready()` marks empty/pin-only shot files as ready.
- Modify: `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
  - Check off the Phase 1 sanitized regression fixtures item after tests pass.
- Modify: `docs/superpowers/reviews/2026-06-05-test-execution.md`
  - Record the new targeted test run and implementation evidence.

## Task 1: Pin-Only RED Regression

**Files:**
- Create: `tests/test_real_data_shape_regressions.py`

- [ ] **Step 1: Write the failing pin-only regression test**

Create `tests/test_real_data_shape_regressions.py` with this initial content:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    load_latest_snapshot_history,
    write_durable_snapshot,
)


def _write_scorecard(
    root: Path,
    scorecard_id: int,
    *,
    date: str = "2026-06-06T08:00:00",
    course: str = "Sanitized Links",
    hole_numbers: list[int] | None = None,
    hole_pars: str = "444444444444444444",
    strokes: int | None = None,
    course_global_id: int = 50100,
    front_global_id: int | None = None,
    back_global_id: int | None = None,
) -> None:
    hole_numbers = hole_numbers or [1]
    strokes = strokes if strokes is not None else len(hole_numbers) * 4
    holes = [
        {"number": number, "strokes": 4, "par": int(hole_pars[index]), "putts": 2}
        for index, number in enumerate(hole_numbers)
    ]
    scorecard = {
        "id": scorecard_id,
        "formattedStartTime": date,
        "courseGlobalId": course_global_id,
        "frontNineGlobalCourseId": front_global_id or course_global_id,
        "backNineGlobalCourseId": back_global_id,
        "holesCompleted": len(hole_numbers),
        "strokes": strokes,
        "holes": holes,
    }
    payload = {
        "scorecardDetails": [
            {
                "scorecard": scorecard,
                "scorecardStats": {"round": {"putts": len(hole_numbers) * 2}},
            }
        ],
        "courseSnapshots": [
            {
                "name": course,
                "holePars": hole_pars[: len(hole_numbers)] if len(hole_pars) > len(hole_numbers) else hole_pars,
                "roundPar": sum(int(item) for item in hole_pars[: len(hole_numbers)]),
            }
        ],
    }
    target = root / "data" / "scorecards" / f"{scorecard_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_shot_file(root: Path, scorecard_id: int, payload: dict[str, object]) -> None:
    target = root / "data" / "shots" / f"{scorecard_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _snapshot_history(root: Path):
    manifest = build_snapshot_manifest(root=root, snapshot_id="snap_real_shapes")
    write_durable_snapshot(root=root, manifest=manifest)
    history = load_latest_snapshot_history(root=root)
    if history is None:
        raise AssertionError("expected durable snapshot history")
    return history


def _assert_secret_free_tree(root: Path) -> None:
    forbidden = ("cookie", "csrf", "token", "authorization", "/home/", "/users/")
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.json")).lower()
    for term in forbidden:
        if term in rendered:
            raise AssertionError(f"sanitized fixture leaked forbidden term: {term}")


class RealDataShapeRegressionTests(unittest.TestCase):
    def test_pin_only_shot_file_is_not_marked_ready_in_snapshot_history(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(root, 8001, course="Pin Only Links", hole_numbers=[1], hole_pars="4")
            _write_shot_file(
                root,
                8001,
                {
                    "clubDetails": [{"clubId": 10, "name": "8I"}],
                    "holeShots": [{"holeNumber": 1, "pinLocation": {"lat": 31_100_000, "lon": 121_100_000}, "shots": []}],
                },
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        self.assertEqual(len(history.raw_rounds), 1)
        round_row = history.raw_rounds[0]
        self.assertTrue(round_row["hasShotFile"])
        self.assertFalse(round_row["hasShots"])
        self.assertEqual(round_row["shotStatus"], "pin_only")
        self.assertEqual(history.shots, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the pin-only test to verify RED**

Run:

```bash
uv run python -m unittest tests.test_real_data_shape_regressions -v
```

Expected: FAIL in `test_pin_only_shot_file_is_not_marked_ready_in_snapshot_history` because the current snapshot loader marks the existing non-`_no_data` shot file as ready.

## Task 2: Snapshot Pin-Only Classifier

**Files:**
- Modify: `ai_caddie/connectors/snapshot.py`
- Test: `tests/test_real_data_shape_regressions.py`

- [ ] **Step 1: Implement the minimal classifier change**

In `ai_caddie/connectors/snapshot.py`, replace the current `_shot_file_ready()` helper with these helpers:

```python
def _shot_payload_has_usable_rows(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("_no_data"):
        return False
    for hole in payload.get("holeShots", []) or []:
        if isinstance(hole, dict) and hole.get("shots"):
            return True
    return False


def _shot_file_status(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        payload = _read_json(path)
    except Exception:
        return False, "no_data"
    if not isinstance(payload, dict) or payload.get("_no_data"):
        return False, "no_data"
    if _shot_payload_has_usable_rows(payload):
        return True, "ready"
    return False, "pin_only"


def _shot_file_ready(path: Path) -> bool:
    ready, _status = _shot_file_status(path)
    return ready
```

In `_normalize_scorecard()`, replace:

```python
has_shots = _shot_file_ready(shot_path)
```

with:

```python
has_shots, shot_status = _shot_file_status(shot_path)
```

Then replace the returned `shotStatus` expression:

```python
"shotStatus": "ready" if has_shots else "no_data" if shot_path.exists() else "missing",
```

with:

```python
"shotStatus": shot_status,
```

- [ ] **Step 2: Run the pin-only test to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_real_data_shape_regressions -v
```

Expected: PASS.

- [ ] **Step 3: Run existing snapshot tests touched by the classifier**

Run:

```bash
uv run python -m unittest tests.test_connector_snapshot -v
```

Expected: PASS.

- [ ] **Step 4: Commit the pin-only regression and classifier**

Run:

```bash
git add tests/test_real_data_shape_regressions.py ai_caddie/connectors/snapshot.py
git commit -m "test: cover sanitized pin-only shot snapshots"
```

Expected: commit succeeds and does not include `_data_aside`, `course_review/`, or `docs/superpowers/reviews/2026-06-02-design-conformance-review.md`.

## Task 3: Remaining Real-Data Shape Regressions

**Files:**
- Modify: `tests/test_real_data_shape_regressions.py`

- [ ] **Step 1: Add imports for the remaining tests**

Update the import section of `tests/test_real_data_shape_regressions.py` to include:

```python
from unittest.mock import patch

from ai_caddie.connectors.snapshot import (
    build_snapshot_manifest,
    discover_played_geometry_dependencies,
    load_latest_snapshot_history,
    write_durable_snapshot,
)
from ai_caddie.history import HistoryData, course_key, history_course_detail, history_data_quality
```

- [ ] **Step 2: Add the four remaining regression tests**

Add these methods to `RealDataShapeRegressionTests`:

```python
    def test_incomplete_round_is_preserved_without_becoming_nine_or_eighteen(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                8002,
                course="Partial Round Links",
                hole_numbers=list(range(1, 8)),
                hole_pars="4444444",
                strokes=29,
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        self.assertEqual(len(history.rounds), 1)
        round_row = history.rounds[0]
        self.assertEqual(round_row["holesCompleted"], 7)
        detail = history_course_detail(round_row["courseKey"], data=history)["course"]
        self.assertEqual(detail["incompleteRounds"], 1)
        self.assertEqual(detail["rounds9"], 0)
        self.assertEqual(detail["rounds18"], 0)
        self.assertEqual(detail["totalHoles"], 7)

    def test_same_day_nine_hole_halves_merge_with_sanitized_raw_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                8003,
                date="2026-06-06T08:00:00",
                course="Merge Test Club ~ Front",
                hole_numbers=list(range(1, 10)),
                hole_pars="444444444",
                strokes=42,
                course_global_id=50103,
                front_global_id=50103,
                back_global_id=50104,
            )
            _write_scorecard(
                root,
                8004,
                date="2026-06-06T10:30:00",
                course="Merge Test Club ~ Back",
                hole_numbers=list(range(1, 10)),
                hole_pars="555555555",
                strokes=41,
                course_global_id=50104,
                front_global_id=50104,
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        self.assertEqual([row["id"] for row in history.raw_rounds], [8003, 8004])
        self.assertEqual(len(history.rounds), 1)
        merged = history.rounds[0]
        self.assertEqual(merged["id"], "merged_8003_8004")
        self.assertEqual(merged["ids"], [8003, 8004])
        self.assertEqual(merged["holesCompleted"], 18)
        self.assertEqual(merged["strokes"], 83)
        self.assertEqual(merged["par"], 81)
        self.assertEqual(merged["holePars"], "444444444555555555")
        self.assertEqual([hole["number"] for hole in merged["holes"]], list(range(1, 19)))
        self.assertEqual(merged["shotStatus"], "partial")

    def test_non_ascii_course_name_is_canonicalized_and_visible_in_history_views(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scorecard(
                root,
                8005,
                course="钟山国际高尔夫 ~ A Mountain",
                hole_numbers=list(range(1, 10)),
                hole_pars="454434454",
                strokes=40,
                course_global_id=50105,
            )

            history = _snapshot_history(root)
            _assert_secret_free_tree(root)

        round_row = history.rounds[0]
        self.assertEqual(round_row["course"], "钟山国际高尔夫 ~ A Mountain")
        self.assertEqual(round_row["courseCanonical"], "钟山国际高尔夫")
        self.assertEqual(round_row["courseKey"], course_key("钟山国际高尔夫"))
        detail = history_course_detail(round_row["courseKey"], data=history)["course"]
        self.assertEqual(detail["name"], "钟山国际高尔夫")
        self.assertEqual(detail["variants"], [{"name": "钟山国际高尔夫 ~ A Mountain", "rawScorecards": 1}])

    def test_missing_and_partial_geometry_degrade_in_dependencies_and_data_quality(self) -> None:
        data = HistoryData(
            raw_rounds=[],
            rounds=[],
            shots=[
                {"id": "partial-shot", "scorecardId": "shape-1", "course": "Shape Links", "globalId": 50106, "localHole": 1},
                {"id": "missing-shot", "scorecardId": "shape-2", "course": "Shape Links", "globalId": 50106, "localHole": 2},
            ],
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hazard_dir = root / "output" / "prodgeometry_hazards"
            mesh_dir = root / "output" / "prodgeometry"
            hazard_dir.mkdir(parents=True)
            mesh_dir.mkdir(parents=True)
            (hazard_dir / "gid50106_h01_hazards.json").write_text("{}", encoding="utf-8")

            dependencies = discover_played_geometry_dependencies(data, root=root, include_ready=True)

            def hazard_path(global_id: int, local_hole: int) -> Path:
                return hazard_dir / f"gid{global_id}_h{local_hole:02d}_hazards.json"

            def mesh_path(global_id: int, local_hole: int) -> Path:
                return mesh_dir / f"gid{global_id}_h{local_hole:02d}_meshes.json"

            with (
                patch("ai_caddie.history.hazard_path", side_effect=hazard_path),
                patch("ai_caddie.history.mesh_path", side_effect=mesh_path),
                patch("ai_caddie.history.history_reports", return_value={"reports": []}),
            ):
                quality = history_data_quality(data)

        by_key = {(row["globalId"], row["localHole"]): row for row in dependencies}
        self.assertEqual(by_key[(50106, 1)]["status"], "partial")
        self.assertEqual(by_key[(50106, 2)]["status"], "missing")

        coverage = quality["playedGeometryCoverage"]
        self.assertEqual(coverage["partialPairs"], 1)
        self.assertEqual(coverage["missingPairs"], 1)
        self.assertEqual(coverage["readyPairs"], 0)
        self.assertEqual(coverage["coverage"], {"ready": 0, "total": 2, "pct": 0.0})
        self.assertEqual(coverage["topMissingCourses"][0]["partialLocalHoles"], [1])
        self.assertEqual(coverage["topMissingCourses"][0]["missingLocalHoles"], [2])
```

- [ ] **Step 3: Run the expanded real-data shape regression suite**

Run:

```bash
uv run python -m unittest tests.test_real_data_shape_regressions -v
```

Expected: PASS. If a test fails because a documented existing behavior differs, inspect the output and either tighten the test to the real supported contract or add the smallest production change needed.

- [ ] **Step 4: Commit the remaining regression tests**

Run:

```bash
git add tests/test_real_data_shape_regressions.py
git commit -m "test: cover sanitized real-data history shapes"
```

Expected: commit succeeds.

## Task 4: Targeted Verification

**Files:**
- Test-only verification.

- [ ] **Step 1: Run the targeted backend suite**

Run:

```bash
uv run python -m unittest tests.test_real_data_shape_regressions tests.test_connector_snapshot tests.test_history_data_quality -v
```

Expected: PASS.

- [ ] **Step 2: Run diff whitespace validation**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

## Task 5: Roadmap And Evidence Update

**Files:**
- Modify: `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
- Modify: `docs/superpowers/reviews/2026-06-05-test-execution.md`

- [ ] **Step 1: Check off the roadmap item**

In `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`, change:

```markdown
- [ ] Add sanitized regression fixtures for real-data shapes:
```

to:

```markdown
- [x] Add sanitized regression fixtures for real-data shapes:
```

- [ ] **Step 2: Append test-execution evidence**

Append this section to `docs/superpowers/reviews/2026-06-05-test-execution.md`, adjusting command results only if the actual run output differs:

````markdown
## Sanitized Real-Data Shape Regression Fixtures

Added focused sanitized regression tests that create Garmin-like raw scorecard, shot, and geometry files
inside temporary directories. The tests cover pin-only shot files, incomplete rounds, same-day 9-hole
merge, non-ASCII course names, and missing/partial geometry degradation without committing private Garmin
data.

Verification:

```bash
uv run python -m unittest tests.test_real_data_shape_regressions tests.test_connector_snapshot tests.test_history_data_quality -v
git diff --check
```

Result: PASS.
````

- [ ] **Step 3: Run documentation diff validation**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit docs and push all new commits**

Run:

```bash
git add docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md docs/superpowers/reviews/2026-06-05-test-execution.md
git commit -m "docs: record sanitized real-data fixture coverage"
git push origin integration/v2
```

Expected: push succeeds. Do not stage `_data_aside`, `course_review/`, or `docs/superpowers/reviews/2026-06-02-design-conformance-review.md`.

## Self-Review

- Spec coverage: Task 1 and Task 2 cover pin-only shot files; Task 3 covers incomplete rounds, same-day
  merge, non-ASCII course names, and missing geometry degradation; Task 5 updates roadmap and evidence.
- Data safety: every test builds synthetic data under `TemporaryDirectory`; Task 1 includes a secret-free
  tree assertion.
- Verification: Task 4 runs the targeted suite from the approved spec, plus `git diff --check`.
