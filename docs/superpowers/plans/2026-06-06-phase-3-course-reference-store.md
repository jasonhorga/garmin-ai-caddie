# Phase 3 Course Reference Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish source-labeled course par and yardage references in `data/courses/<gid>.json`, with visible coverage.

**Architecture:** Keep `ai_caddie/course_reference.py` as the resolver boundary and persist simple JSON records. The resolver ladder remains played scorecard par, CourseView release par, and deterministic length estimate; no live parser path is added in this phase. Coverage is computed from referenced played nines versus valid stored course-reference records and exposed through readiness.

**Tech Stack:** Python 3.12, unittest, FastAPI TestClient, Garmin CourseView protobuf fixtures, JSON file-backed stores.

---

## File Structure

- Modify `ai_caddie/course_reference.py`: extend `CoursePar`, harden `load_course_par()`, persist yardage metadata, add coverage helper.
- Modify `tests/test_course_reference.py`: add TDD coverage for persisted records, corrupt caches, CourseView yardages, estimate yardages, and coverage counts.
- Modify `server_v2/readiness.py`: add a `course_reference` readiness check based on the new coverage helper.
- Modify `tests/test_server_v2_readiness.py`: assert readiness exposes course-reference coverage and redacts nothing private.
- Modify `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`: check completed Phase 3 items after implementation passes.
- Create `docs/superpowers/reviews/2026-06-06-phase-3-course-reference-store.md`: record verification evidence.

## Task 1: CoursePar Persistence And Bad Cache Handling

**Files:**
- Modify: `tests/test_course_reference.py`
- Modify: `ai_caddie/course_reference.py`

- [ ] **Step 1: Write failing persistence tests**

Add imports to `tests/test_course_reference.py`:

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory
```

Add this test class:

```python
class PersistenceTests(unittest.TestCase):
    def test_save_and_load_preserves_source_confidence_provenance_and_yardage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = cr.CoursePar(
                global_id=31936,
                par=[4, 5, 3, 4, 3, 4, 4, 5, 4],
                par_source="courseview",
                confidence="high",
                provenance="courseview_release",
                course_name="Fixture C",
                handicap=[6, 3, 2, 1, 9, 5, 8, 7, 4],
                yardages_m=[360, 470, 160, 380, 155, 390, 410, 455, 370],
                yardage_source="courseview",
                yardage_confidence="high",
                yardage_provenance="courseview_release",
            )

            cr.save_course_par(rec, root=root)
            loaded = cr.load_course_par(31936, root=root)

        self.assertEqual(loaded, rec)

    def test_load_course_par_ignores_corrupt_or_incomplete_records(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data" / "courses" / "31936.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"global_id": 31936, "par": "not-a-list", "par_source": "courseview"}), encoding="utf-8")

            self.assertIsNone(cr.load_course_par(31936, root=root))
```

- [ ] **Step 2: Run course-reference tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_course_reference -v
```

Expected: failure because `CoursePar` does not accept yardage fields and bad persisted records are not ignored.

- [ ] **Step 3: Extend `CoursePar` and validate cached records**

In `ai_caddie/course_reference.py`, extend the dataclass by appending optional yardage fields:

```python
    yardages_m: list[float] | None = None
    yardage_source: str | None = None
    yardage_confidence: str | None = None
    yardage_provenance: str | None = None
```

Add a validator helper:

```python
def _valid_par_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, int) for item in value)


def _valid_optional_number_list(value: object) -> bool:
    return value is None or (
        isinstance(value, list)
        and all(isinstance(item, (int, float)) for item in value)
    )
```

Replace `load_course_par()` with:

```python
def load_course_par(global_id: int, *, root: Path = ROOT) -> CoursePar | None:
    path = _store_path(global_id, root=root)
    if not path.exists():
        return None
    try:
        payload = read_json(path)
        if not isinstance(payload, dict):
            return None
        if int(payload.get("global_id")) != int(global_id):
            return None
        if not _valid_par_list(payload.get("par")):
            return None
        if not str(payload.get("par_source") or "").strip():
            return None
        if not str(payload.get("confidence") or "").strip():
            return None
        if payload.get("provenance") is None:
            return None
        if not _valid_optional_number_list(payload.get("yardages_m")):
            return None
        return CoursePar(**payload)
    except (TypeError, ValueError, KeyError):
        return None
```

- [ ] **Step 4: Run course-reference tests and commit**

Run:

```bash
uv run python -m unittest tests.test_course_reference -v
git diff --check
```

Expected: all course-reference tests pass and diff check exits 0.

Commit:

```bash
git add ai_caddie/course_reference.py tests/test_course_reference.py
git commit -m "test: harden course reference persistence"
```

## Task 2: CourseView And Estimate Yardage Metadata

**Files:**
- Modify: `tests/test_course_reference.py`
- Modify: `ai_caddie/course_reference.py`

- [ ] **Step 1: Write failing yardage tests**

Add tests to `ResolveLadderTests`:

```python
def test_courseview_record_persists_yardage_metadata(self) -> None:
    holes = [
        {"par": p, "handicap": h, "yardage_or_length": y}
        for p, h, y in zip(
            [4, 5, 3, 4, 3, 4, 4, 5, 4],
            [6, 3, 2, 1, 9, 5, 8, 7, 4],
            [360, 470, 160, 380, 155, 390, 410, 455, 370],
        )
    ]
    saved: dict[int, cr.CoursePar] = {}
    with patch.object(cr, "played_par_by_nine", return_value={}), \
            patch.object(cr, "_release_holes", return_value=holes), \
            patch.object(cr, "save_course_par", side_effect=lambda record, **_: saved.__setitem__(record.global_id, record)):
        rec = cr.resolve_par(31936)

    self.assertEqual(rec.yardages_m, [360, 470, 160, 380, 155, 390, 410, 455, 370])
    self.assertEqual(rec.yardage_source, "courseview")
    self.assertEqual(rec.yardage_confidence, "high")
    self.assertEqual(rec.yardage_provenance, "courseview_release")
    self.assertEqual(saved[31936].yardages_m, rec.yardages_m)


def test_estimate_persists_length_yardage_metadata_without_overriding_courseview(self) -> None:
    lengths = [150, 460, 300, 300, 300, 300, 300, 300, 300]
    with patch.object(cr, "played_par_by_nine", return_value={}), \
            patch.object(cr, "_release_holes", return_value=None), \
            patch.object(cr, "save_course_par") as save:
        rec = cr.resolve_par(99999, lengths_m=lengths)

    self.assertEqual(rec.par_source, "estimate")
    self.assertEqual(rec.confidence, "medium")
    self.assertEqual(rec.yardages_m, lengths)
    self.assertEqual(rec.yardage_source, "length_estimate")
    self.assertEqual(rec.yardage_confidence, "medium")
    self.assertEqual(rec.yardage_provenance, "length_estimate")
    save.assert_called_once()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_course_reference -v
```

Expected: failure because CourseView and estimate records do not fill yardage metadata.

- [ ] **Step 3: Persist yardage metadata**

Add helper in `ai_caddie/course_reference.py`:

```python
def _hole_yardages(holes: list[dict]) -> list[float] | None:
    values = [hole.get("yardage_or_length") for hole in holes]
    if values and all(isinstance(value, (int, float)) for value in values):
        return [float(value) for value in values]
    return None
```

Update `_courseview_record()`:

```python
    yardages = _hole_yardages(holes)
    rec = CoursePar(
        gid, pars, "courseview", "high",
        provenance="courseview_release", course_name=course_name,
        handicap=hcaps if all(isinstance(h, int) for h in hcaps) else None,
        yardages_m=yardages,
        yardage_source="courseview" if yardages else None,
        yardage_confidence="high" if yardages else None,
        yardage_provenance="courseview_release" if yardages else None,
    )
```

Update estimate fallback in `resolve_par()`:

```python
        rec = CoursePar(
            gid,
            est,
            "estimate",
            "medium",
            provenance="length_estimate",
            course_name=course_name,
            yardages_m=[float(x) for x in lengths_m],
            yardage_source="length_estimate",
            yardage_confidence="medium",
            yardage_provenance="length_estimate",
        )
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run python -m unittest tests.test_course_reference -v
git diff --check
```

Expected: all course-reference tests pass and diff check exits 0.

Commit:

```bash
git add ai_caddie/course_reference.py tests/test_course_reference.py
git commit -m "test: persist course reference yardages"
```

## Task 3: Course-Reference Coverage In Readiness

**Files:**
- Modify: `tests/test_course_reference.py`
- Modify: `ai_caddie/course_reference.py`
- Modify: `tests/test_server_v2_readiness.py`
- Modify: `server_v2/readiness.py`

- [ ] **Step 1: Write failing coverage tests**

Add this test to `BuildStoreTests`:

```python
def test_course_reference_coverage_counts_referenced_and_stored_nines(self) -> None:
    rounds = [
        {"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434453444544", "name": "X"},
    ]
    with patch.object(cr, "_rounds_from_files", return_value=rounds), \
            patch.object(cr, "load_course_par", side_effect=lambda gid, **_: cr.CoursePar(gid, [4] * 9, "played", "high", provenance="garmin_scorecard") if gid == 40590 else None):
        coverage = cr.course_reference_coverage()

    self.assertEqual(coverage["schema"], "ai-caddie-course-reference-coverage-v1")
    self.assertEqual(coverage["total"], 2)
    self.assertEqual(coverage["ready"], 1)
    self.assertEqual(coverage["missing"], 1)
    self.assertEqual(coverage["pct"], 50.0)
    self.assertEqual(coverage["missingGlobalIds"], [31936])
```

Add this test to `ServerV2ReadinessTests` in `tests/test_server_v2_readiness.py`:

```python
def test_readiness_reports_course_reference_coverage(self) -> None:
    with patch("server_v2.readiness.course_reference_coverage", return_value={
        "schema": "ai-caddie-course-reference-coverage-v1",
        "total": 2,
        "ready": 1,
        "missing": 1,
        "pct": 50.0,
        "missingGlobalIds": [31936],
    }):
        response = TestClient(app).get("/api/v2/readiness")

    self.assertEqual(response.status_code, 200)
    checks = {row["label"]: row for row in response.json()["checks"]}
    self.assertEqual(checks["course_reference"]["state"], "degraded")
    self.assertEqual(checks["course_reference"]["evidence"]["pct"], 50.0)
    self.assertEqual(checks["course_reference"]["evidence"]["missingGlobalIds"], [31936])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest tests.test_course_reference tests.test_server_v2_readiness -v
```

Expected: failure because `course_reference_coverage` and readiness import/check do not exist.

- [ ] **Step 3: Add coverage helper**

In `ai_caddie/course_reference.py`, add:

```python
def referenced_course_ids(*, root: Path = ROOT) -> list[int]:
    ids: set[int] = set()
    for rnd in _rounds_from_files(root=root):
        for key in ("front_gid", "back_gid"):
            gid = rnd.get(key)
            if gid:
                ids.add(int(gid))
    return sorted(ids)


def course_reference_coverage(*, root: Path = ROOT) -> dict[str, object]:
    referenced = referenced_course_ids(root=root)
    ready: list[int] = []
    missing: list[int] = []
    for gid in referenced:
        if load_course_par(gid, root=root) is None:
            missing.append(gid)
        else:
            ready.append(gid)
    total = len(referenced)
    pct = round(len(ready) * 100.0 / total, 1) if total else 0.0
    return {
        "schema": "ai-caddie-course-reference-coverage-v1",
        "total": total,
        "ready": len(ready),
        "missing": len(missing),
        "pct": pct,
        "readyGlobalIds": ready[:25],
        "missingGlobalIds": missing[:25],
    }
```

- [ ] **Step 4: Add readiness check**

In `server_v2/readiness.py`, import the helper:

```python
from ai_caddie.course_reference import course_reference_coverage
```

After the sync check block in `build_readiness_response()`, add:

```python
    try:
        coverage = course_reference_coverage()
        total = int(coverage.get("total") or 0)
        ready = int(coverage.get("ready") or 0)
        state = "ready" if total and ready == total else "degraded"
        checks.append(
            _check(
                "course_reference",
                state,
                "Course-reference cache covers played course nines."
                if state == "ready"
                else "Course-reference cache is incomplete for played course nines.",
                coverage,
            )
        )
    except Exception as exc:
        checks.append(_check("course_reference", "error", exc.__class__.__name__))
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
uv run python -m unittest tests.test_course_reference tests.test_server_v2_readiness -v
git diff --check
```

Expected: all listed tests pass and diff check exits 0.

Commit:

```bash
git add ai_caddie/course_reference.py server_v2/readiness.py tests/test_course_reference.py tests/test_server_v2_readiness.py
git commit -m "test: report course reference coverage"
```

## Task 4: Phase 3 Documentation, Verification, And Push

**Files:**
- Modify: `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
- Create: `docs/superpowers/reviews/2026-06-06-phase-3-course-reference-store.md`

- [ ] **Step 1: Run full Phase 3 verification**

Run:

```bash
uv run python -m unittest tests.test_course_reference tests.test_pipeline tests.test_server_v2_readiness -v
git diff --check
```

Expected: all listed unittest modules pass and diff check exits 0.

- [ ] **Step 2: Check Phase 3 roadmap items**

In `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`, change these Phase 3 items to done:

```markdown
- [x] Build or finish the resolver ladder:
- [x] Persist source, confidence, and provenance for every resolved course reference.
- [x] Add saved-HTML/parser fixtures for any web lookup path; no live network in CI.
```

The parser-fixture item is done because Phase 3 does not add or retain a live web/parser path.

- [ ] **Step 3: Record evidence**

Create `docs/superpowers/reviews/2026-06-06-phase-3-course-reference-store.md`:

```markdown
# Phase 3 Course Reference Store Evidence

- Date: 2026-06-06
- Branch: `integration/v2`

## Scope

Implemented Phase 3 from `docs/superpowers/specs/2026-06-06-phase-3-course-reference-store-design.md`.

## Evidence

- `CoursePar` persisted records include source, confidence, provenance, handicap, and optional yardage metadata.
- Corrupt or incomplete `data/courses/<gid>.json` records are ignored instead of trusted.
- Resolver ladder remains played -> CourseView -> estimate.
- CourseView records persist high-confidence yardage metadata when release holes provide length values.
- Estimate fallback labels yardages as `length_estimate` with medium confidence.
- No live parser path was added; CI uses only saved CourseView protobuf fixtures and mocks.
- Readiness exposes course-reference coverage for referenced played nines.

## Verification

```bash
uv run python -m unittest tests.test_course_reference tests.test_pipeline tests.test_server_v2_readiness -v
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
git add docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md docs/superpowers/reviews/2026-06-06-phase-3-course-reference-store.md
git commit -m "docs: record phase 3 course reference completion"
git push origin integration/v2
```

## Self-Review

- Spec coverage: the plan covers source/confidence/provenance persistence, CourseView and estimate yardage metadata, corrupt cache handling, no live parser path, and visible course-reference coverage.
- Placeholder scan: no deferred implementation instructions are present; every task names concrete files, code, commands, and expected results.
- Type consistency: `CoursePar.yardages_m`, `yardage_source`, `yardage_confidence`, `yardage_provenance`, `course_reference_coverage()`, and readiness `course_reference` evidence are used consistently.
