# CourseView Par + Pipeline Unification Implementation Plan (PR #1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make per-hole par exact for ANY course (played or not) by decoding it from the already-cached Garmin CourseView release protobuf, wire it through the resolver/store/prep/mobile, unify the sync pipeline so neither entrypoint drops a step, and delete the now-dead GolfPass scraper.

**Architecture:** Par flows through one resolver `course_reference.resolve_par`, whose ladder becomes `played → courseview → estimate`. The `courseview` rung decodes `field 7 → sub 2 → field 1` (par) and `sub 3 → field 1` (handicap) of the release protobuf the geometry layer already fetches/caches. Both sync entrypoints (CLI `pipeline.sync`, server connector `sync`) run auth→fetch→geometry-ensure(missing)→course-ref via shared helpers. GolfPass is removed entirely.

**Tech Stack:** Python 3, `uv`, `unittest` (CI runs `uv run python -m unittest discover -s tests` — NOT pytest), protobuf hand-decoded with a varint walker.

**Conventions:** TDD (test first, watch it fail, implement, watch it pass, commit). Tests are `unittest.TestCase` subclasses (module-level `def test_*` and pytest fixtures are INVISIBLE to CI). No live network in tests — patch the release loader. Verify each test with `uv run python -m unittest tests.<module> -v`.

---

## File Structure

- `inspect_courseview_release.py` (root; imported by the engine via `ai_caddie/geometry_sync.py`) — **modify**: `inspect_release` also decodes per-hole `par` + `handicap`; add `_nested_field1` helper. Keep CLI output additive.
- `ai_caddie/course_reference.py` — **modify**: add `_release_holes` + `courseview_par`; add `handicap` to `CoursePar`; rewrite `resolve_par` ladder; extend `build_played_store`; remove all GolfPass code.
- `ai_caddie/scrapers/golfpass.py` — **delete**.
- `ai_caddie/course_prep.py` — **modify**: `prep_nine` resolves via `resolve_par` (not read-only `load_course_par`).
- `ai_caddie/mobile_live.py` — **modify**: `_geometry_only_course_template` uses courseview par instead of hardcoded `4`.
- `ai_caddie/connectors/snapshot.py` — **modify**: add shared `ensure_geometry_dependencies(dependencies, *, root)`.
- `ai_caddie/connectors/garmin_cn.py` — **modify**: `_ensure_geometry_dependencies` delegates to the shared helper; `sync` runs the course-ref step (`build_played_store`) after a ready snapshot.
- `ai_caddie/pipeline.py` — **modify**: `sync` adds an idempotent geometry-ensure-missing step.
- `tests/fixtures/courseview_release_3193{4,5,6}.pb`, `..._31870.pb`, `..._31871.pb` — **create** (public course-index protobufs; ~3.7KB each).
- `tests/test_courseview_par.py` — **create**.
- `tests/test_course_reference.py` — **modify**: drop GolfPass tests; rewrite resolve_par ladder tests; add courseview + build-store tests.
- `tests/fixtures/golfpass_zhongshan_mountain_lake.html` — **delete**.
- `tests/test_server_v2_mobile.py` — **modify**: the geometry-only-course test asserts real par.
- `tests/test_garmin_cn_connector.py`, `tests/test_pipeline.py` (create if absent) — **modify/create**: assert course-ref + geometry-ensure run.

---

### Task 1: Decode par + handicap from the CourseView release protobuf

**Files:**
- Create: `tests/fixtures/courseview_release_31936.pb`, `_31870.pb`, `_31871.pb`
- Modify: `inspect_courseview_release.py` (the `inspect_release` hole loop, ~lines 89-105; add a helper near `read_varint`)
- Test: `tests/test_courseview_par.py`

- [ ] **Step 1: Copy real release protobufs into fixtures (public, no PII)**

```bash
cp data/courseview/31936_releases.pb tests/fixtures/courseview_release_31936.pb
cp data/courseview/31870_releases.pb tests/fixtures/courseview_release_31870.pb
cp data/courseview/31871_releases.pb tests/fixtures/courseview_release_31871.pb
```

- [ ] **Step 2: Write the failing test** — `tests/test_courseview_par.py`

```python
import unittest
from pathlib import Path

from inspect_courseview_release import inspect_release

FIX = Path(__file__).parent / "fixtures"


def _release(name: str) -> dict:
    return inspect_release((FIX / name).read_bytes())


class ReleaseParDecodeTests(unittest.TestCase):
    def test_decodes_par_and_handicap_for_unplayed_course(self) -> None:
        info = _release("courseview_release_31936.pb")  # 钟山 C Valley (never played)
        pars = [h["par"] for h in info["holes"]]
        hcaps = [h["handicap"] for h in info["holes"]]
        self.assertEqual(pars, [4, 5, 3, 4, 3, 4, 4, 5, 4])
        self.assertEqual(sum(pars), 36)
        self.assertEqual(hcaps, [6, 3, 2, 1, 9, 5, 8, 7, 4])

    def test_nine_mapping_front_and_back_match_played_card(self) -> None:
        # Guards the top risk: release hole records -> local_hole 1..9 for BOTH nines.
        front = [h["par"] for h in _release("courseview_release_31870.pb")["holes"]]
        back = [h["par"] for h in _release("courseview_release_31871.pb")["holes"]]
        self.assertEqual(front, [5, 4, 3, 4, 4, 4, 5, 3, 4])   # == a played card's holePars[:9]
        self.assertEqual(back, [4, 5, 4, 4, 3, 5, 3, 4, 4])    # == that card's holePars[9:18]
```

- [ ] **Step 3: Run it — expect FAIL** (`KeyError: 'par'`)

Run: `uv run python -m unittest tests.test_courseview_par -v`
Expected: FAIL (holes have no `par`/`handicap` key yet).

- [ ] **Step 4: Add the nested-field decoder + decode par/handicap** in `inspect_courseview_release.py`

Add this helper just below `read_varint`:

```python
def _nested_field1(buf: bytes) -> int | None:
    """First varint (field 1) of a nested protobuf message; None if absent."""
    for field_no, wire_type, _value, _raw in parse_fields(buf):
        if field_no == 1 and wire_type == 0:
            return _value
    return None
```

Inside `inspect_release`, in the per-hole sub-loop (`for sub_no, sub_wire, sub_value, _sub_raw in parse_fields(raw):`), add two branches alongside the existing `sub_no == 6/7/8` ones:

```python
                elif sub_no == 2 and sub_wire == 2 and _sub_raw is not None:
                    hole["par"] = _nested_field1(_sub_raw)
                elif sub_no == 3 and sub_wire == 2 and _sub_raw is not None:
                    hole["handicap"] = _nested_field1(_sub_raw)
```

(Additive only — existing keys/CLI output are unchanged.)

- [ ] **Step 5: Run it — expect PASS**

Run: `uv run python -m unittest tests.test_courseview_par -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add inspect_courseview_release.py tests/test_courseview_par.py tests/fixtures/courseview_release_*.pb
git commit -m "feat: decode per-hole par + handicap from CourseView release protobuf"
```

---

### Task 2: `courseview_par()` resolver primitive

**Files:**
- Modify: `ai_caddie/course_reference.py` (add imports + `_release_holes` + `courseview_par`)
- Test: `tests/test_courseview_par.py` (append)

- [ ] **Step 1: Write the failing test** — append to `tests/test_courseview_par.py`

```python
from unittest.mock import patch
from ai_caddie import course_reference as cr


class CourseviewParTests(unittest.TestCase):
    def test_courseview_par_from_cached_release(self) -> None:
        holes = inspect_release((FIX / "courseview_release_31936.pb").read_bytes())["holes"]
        with patch.object(cr, "_release_holes", return_value=holes):
            self.assertEqual(cr.courseview_par(31936), [4, 5, 3, 4, 3, 4, 4, 5, 4])

    def test_courseview_par_none_when_no_release(self) -> None:
        with patch.object(cr, "_release_holes", return_value=None):
            self.assertIsNone(cr.courseview_par(99999, allow_fetch=False))
```

- [ ] **Step 2: Run it — expect FAIL** (`AttributeError: _release_holes`)

Run: `uv run python -m unittest tests.test_courseview_par.CourseviewParTests -v`

- [ ] **Step 3: Implement** in `ai_caddie/course_reference.py`

Add near the top imports (the `from ai_caddie.scrapers import golfpass` line is removed in Task 4):

```python
from inspect_courseview_release import COURSEVIEW, inspect_release, load_release_pb
```

Add these functions (place above `resolve_par`):

```python
def _release_holes(global_id: int, *, allow_fetch: bool = True) -> list[dict] | None:
    """Per-hole records from the CourseView release protobuf (cache-first, then fetch+cache)."""
    gid = int(global_id)
    path = COURSEVIEW / f"{gid}_releases.pb"
    if path.exists():
        pb = path.read_bytes()
    elif allow_fetch:
        try:
            pb = load_release_pb(gid, True)  # live fetch (anonymous)
        except Exception:
            return None
        COURSEVIEW.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pb)
    else:
        return None
    try:
        return inspect_release(pb).get("holes") or None
    except Exception:
        return None


def courseview_par(global_id: int, *, allow_fetch: bool = True) -> list[int] | None:
    """Exact per-hole par for a course nine from Garmin's CourseView release (any course)."""
    holes = _release_holes(global_id, allow_fetch=allow_fetch)
    if not holes:
        return None
    pars = [h.get("par") for h in holes]
    return pars if pars and all(isinstance(p, int) for p in pars) else None
```

- [ ] **Step 4: Run it — expect PASS**

Run: `uv run python -m unittest tests.test_courseview_par.CourseviewParTests -v`

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/course_reference.py tests/test_courseview_par.py
git commit -m "feat: courseview_par() — exact par for any course nine from the release protobuf"
```

---

### Task 3: `CoursePar.handicap` + rewrite `resolve_par` ladder (played → courseview → estimate); drop GolfPass code

**Files:**
- Modify: `ai_caddie/course_reference.py` (`PAR_SOURCES`, `CoursePar`, `resolve_par`; delete `official_par_from_golfpass`, `pick_course_link`, golfpass import + docstring line)
- Test: `tests/test_course_reference.py` (rewrite `ResolveLadderTests`)

- [ ] **Step 1: Rewrite the ladder tests** in `tests/test_course_reference.py` — replace the existing `ResolveLadderTests` class with:

```python
class ResolveLadderTests(unittest.TestCase):
    def test_played_supersedes(self) -> None:
        played = {31870: cr.CoursePar(31870, [5, 4, 3, 4, 4, 4, 5, 3, 4], "played", "high", rounds=2)}
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(31870, lengths_m=[400] * 9)
        self.assertEqual(rec.par_source, "played")

    def test_courseview_when_unplayed(self) -> None:
        holes = [{"par": p, "handicap": h} for p, h in
                 zip([4, 5, 3, 4, 3, 4, 4, 5, 4], [6, 3, 2, 1, 9, 5, 8, 7, 4])]
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(31936)
        self.assertEqual(rec.par_source, "courseview")
        self.assertEqual(rec.par, [4, 5, 3, 4, 3, 4, 4, 5, 4])
        self.assertEqual(rec.handicap, [6, 3, 2, 1, 9, 5, 8, 7, 4])

    def test_estimate_when_no_release(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par"):
            rec = cr.resolve_par(99999, lengths_m=[150, 460, 300, 300, 300, 300, 300, 300, 300])
        self.assertEqual(rec.par_source, "estimate")
        self.assertEqual(rec.par[:2], [3, 5])

    def test_none_when_nothing(self) -> None:
        with patch.object(cr, "played_par_by_nine", return_value={}), \
                patch.object(cr, "_release_holes", return_value=None), \
                patch.object(cr, "save_course_par"):
            self.assertIsNone(cr.resolve_par(99999))
```

- [ ] **Step 2: Run it — expect FAIL** (old `resolve_par` has no courseview rung; `handicap` kwarg missing)

Run: `uv run python -m unittest tests.test_course_reference.ResolveLadderTests -v`

- [ ] **Step 3: Implement** in `ai_caddie/course_reference.py`

(a) Change the constant:

```python
PAR_SOURCES = ("played", "courseview", "estimate")
```

(b) Add the field to `CoursePar` (after `course_name`):

```python
    handicap: list[int] | None = None
```

(c) Delete these now-dead members entirely: the module docstring line mentioning `official -> ... GolfPass scrape` (reword to the new ladder), the `from ai_caddie.scrapers import golfpass` import, the `official_par_from_golfpass(...)` function, and the `pick_course_link(...)` function.

(d) Replace `resolve_par` with:

```python
def resolve_par(
    global_id: int,
    *,
    course_name: str | None = None,
    lengths_m: list[float] | None = None,
    allow_fetch: bool = True,
) -> CoursePar | None:
    """Resolve par for a nine via the ladder: played -> courseview -> estimate. Persists the result.

    ``allow_fetch=False`` keeps the courseview rung cache-only (no network) for request-time paths.
    """
    gid = int(global_id)
    played = played_par_by_nine().get(gid)
    if played:
        save_course_par(played)
        return played
    holes = _release_holes(gid, allow_fetch=allow_fetch)
    if holes:
        pars = [h.get("par") for h in holes]
        if pars and all(isinstance(p, int) for p in pars):
            hcaps = [h.get("handicap") for h in holes]
            rec = CoursePar(
                gid, pars, "courseview", "high",
                provenance="courseview_release", course_name=course_name,
                handicap=hcaps if all(isinstance(h, int) for h in hcaps) else None,
            )
            save_course_par(rec)
            return rec
    if lengths_m:
        est = [estimate_par_from_length(x) for x in lengths_m]
        rec = CoursePar(gid, est, "estimate", "medium",
                        provenance="length_estimate", course_name=course_name)
        save_course_par(rec)
        return rec
    return None
```

- [ ] **Step 4: Run it — expect PASS**

Run: `uv run python -m unittest tests.test_course_reference.ResolveLadderTests -v`

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/course_reference.py tests/test_course_reference.py
git commit -m "feat: resolve_par ladder played->courseview->estimate; add handicap; drop GolfPass branch"
```

---

### Task 4: Materialise courseview par for referenced-but-unplayed nines in `build_played_store`

**Files:**
- Modify: `ai_caddie/course_reference.py` (`build_played_store`)
- Test: `tests/test_course_reference.py` (add `BuildStoreTests`)

- [ ] **Step 1: Write the failing test**

```python
class BuildStoreTests(unittest.TestCase):
    def test_fills_courseview_for_referenced_unplayed_nine(self) -> None:
        rounds = [{"front_gid": 40590, "back_gid": 31936, "hole_pars": "453444434", "name": "X"}]
        played = {40590: cr.CoursePar(40590, [4, 5, 3, 4, 4, 4, 4, 3, 4], "played", "high")}
        holes = [{"par": p} for p in [4, 5, 3, 4, 3, 4, 4, 5, 4]]
        saved = {}
        with patch.object(cr, "played_par_by_nine", return_value=played), \
                patch.object(cr, "_rounds_from_files", return_value=rounds), \
                patch.object(cr, "_release_holes", return_value=holes), \
                patch.object(cr, "load_course_par", return_value=None), \
                patch.object(cr, "save_course_par", side_effect=lambda r: saved.__setitem__(r.global_id, r)):
            store = cr.build_played_store()
        self.assertEqual(store[40590].par_source, "played")
        self.assertEqual(store[31936].par_source, "courseview")
```

- [ ] **Step 2: Run it — expect FAIL** (31936 not in store)

Run: `uv run python -m unittest tests.test_course_reference.BuildStoreTests -v`

- [ ] **Step 3: Implement** — replace `build_played_store` with:

```python
def build_played_store() -> dict[int, CoursePar]:
    """Materialise par for every played nine (authoritative), then fill courseview par for any
    nine referenced by a scorecard that has no played record. Idempotent."""
    records = played_par_by_nine()
    for record in records.values():
        save_course_par(record)
    referenced: set[int] = set()
    for rnd in _rounds_from_files():
        for key in ("front_gid", "back_gid"):
            gid = rnd.get(key)
            if gid:
                referenced.add(int(gid))
    for gid in sorted(referenced):
        if gid in records or load_course_par(gid) is not None:
            continue
        rec = resolve_par(gid)  # -> courseview (or estimate/None)
        if rec is not None:
            records[gid] = rec
    return records
```

- [ ] **Step 4: Run it — expect PASS**, then commit

Run: `uv run python -m unittest tests.test_course_reference.BuildStoreTests -v`
```bash
git add ai_caddie/course_reference.py tests/test_course_reference.py
git commit -m "feat: build_played_store fills courseview par for referenced unplayed nines"
```

---

### Task 5: `prep_nine` resolves par on demand (so unplayed prep gets courseview par)

**Files:**
- Modify: `ai_caddie/course_prep.py` (`prep_nine`, line ~257)
- Test: `tests/test_course_prep.py` (add a focused test)

- [ ] **Step 1: Write the failing test** (add to `tests/test_course_prep.py`)

```python
import unittest
from unittest.mock import patch
from ai_caddie import course_prep, course_reference


class PrepResolvesParTests(unittest.TestCase):
    def test_prep_nine_resolves_when_not_cached(self) -> None:
        rec = course_reference.CoursePar(31936, [4, 5, 3, 4, 3, 4, 4, 5, 4], "courseview", "high")
        seen = {}
        with patch.object(course_reference, "load_course_par", return_value=None), \
                patch.object(course_reference, "resolve_par", return_value=rec) as rp, \
                patch.object(course_prep, "prep_hole",
                             side_effect=lambda gid, h, **kw: seen.update(kw) or None):
            course_prep.prep_nine(31936, holes=range(1, 2))
        rp.assert_called_once_with(31936)
        self.assertIs(seen.get("par_record"), rec)

    def test_prep_nine_uses_cached_store_without_recompute(self) -> None:
        rec = course_reference.CoursePar(40590, [4, 5, 3, 4, 4, 4, 4, 3, 4], "played", "high")
        with patch.object(course_reference, "load_course_par", return_value=rec), \
                patch.object(course_reference, "resolve_par") as rp, \
                patch.object(course_prep, "prep_hole", side_effect=lambda *a, **k: None):
            course_prep.prep_nine(40590, holes=range(1, 2))
        rp.assert_not_called()  # cached store hit -> no recompute, no network
```

- [ ] **Step 2: Run it — expect FAIL** (`prep_nine` still calls `load_course_par`)

Run: `uv run python -m unittest tests.test_course_prep.PrepResolvesParTests -v`

- [ ] **Step 3: Implement** — in `prep_nine`, make par lookup **cache-first** (stored store, then resolve on miss):

```python
    par_record = course_reference.load_course_par(global_id)
    if par_record is None:
        par_record = course_reference.resolve_par(global_id)
```

(replacing the single `par_record = course_reference.load_course_par(global_id)` line.) This keeps played courses cheap (no recompute, no network — the stored record wins) and only resolves (courseview, may fetch) for an uncached/unplayed course. Leave `prep_hole`'s per-hole route-length estimate fallback unchanged.

- [ ] **Step 4: Run it — expect PASS**, then commit

Run: `uv run python -m unittest tests.test_course_prep.PrepResolvesParTests -v`
```bash
git add ai_caddie/course_prep.py tests/test_course_prep.py
git commit -m "feat: prep_nine resolves par on demand (courseview for unplayed courses)"
```

---

### Task 6: Fix hardcoded `par: 4` in the mobile geometry-only course template

**Files:**
- Modify: `ai_caddie/mobile_live.py` (`_geometry_only_course_template`, lines 1608-1633)
- Test: `tests/test_server_v2_mobile.py` (`test_mobile_course_package_can_use_geometry_only_course_without_prior_round`, ~line 345)

- [ ] **Step 1: Update the existing test** to assert real par. After the package is built, assert the first hole's par equals the patched courseview value rather than the blanket 4. Wrap the existing call with a patch and add an assertion:

```python
        from ai_caddie import course_reference
        with patch.object(course_reference, "courseview_par",
                          return_value=[4, 5, 3, 4, 3, 4, 4, 5, 4]):
            # ... existing call that builds the geometry-only package ...
            pass
        # holes 1..9 take courseview par; hole 1 must be 4 from courseview, NOT a blanket default
        self.assertEqual(package["holes"][0]["par"], 4)
        self.assertEqual(package["holes"][1]["par"], 5)  # would be 4 under the old hardcode
```

(Adapt variable names to the existing test; the key new assertion is `holes[1]["par"] == 5`, impossible under the old hardcoded `4`.)

- [ ] **Step 2: Run it — expect FAIL** (hole 2 par is currently 4)

Run: `uv run python -m unittest tests.test_server_v2_mobile -v`

- [ ] **Step 3: Implement** in `ai_caddie/mobile_live.py`, `_geometry_only_course_template`:

Add near the top of the function (after `holes = []`). **`allow_fetch=False`** — this is an offline-first mobile package path (master Rule #7); it must NOT block on a network fetch. The release pb is normally cached alongside the geometry that gates this template, so par is real for geometry-backed courses; otherwise it falls to `4`.

```python
    from ai_caddie import course_reference
    cv_par = course_reference.courseview_par(int(global_id), allow_fetch=False)
```

Replace the append line:

```python
        holes.append({"number": local_hole, "par": 4, "yards": None, "geometryCoverage": state})
```

with:

```python
        par = cv_par[local_hole - 1] if (cv_par and local_hole - 1 < len(cv_par)) else 4
        holes.append({"number": local_hole, "par": par, "yards": None, "geometryCoverage": state})
```

- [ ] **Step 4: Run it — expect PASS**, then commit

Run: `uv run python -m unittest tests.test_server_v2_mobile -v`
```bash
git add ai_caddie/mobile_live.py tests/test_server_v2_mobile.py
git commit -m "fix: geometry-only mobile course template uses courseview par, not hardcoded 4"
```

---

### Task 7: Unify the sync pipeline — shared geometry-ensure helper; no entrypoint drops a step

**Files:**
- Modify: `ai_caddie/connectors/snapshot.py` (add `ensure_geometry_dependencies`)
- Modify: `ai_caddie/connectors/garmin_cn.py` (`_ensure_geometry_dependencies` delegates; `sync` runs course-ref)
- Modify: `ai_caddie/pipeline.py` (`sync` adds geometry-ensure-missing)
- Test: `tests/test_garmin_cn_connector.py`, `tests/test_pipeline.py` (create)

- [ ] **Step 1: Write failing tests**

In `tests/test_pipeline.py` (create):

```python
import unittest
from unittest.mock import patch
from ai_caddie import pipeline


class PipelineRunsAllStepsTests(unittest.TestCase):
    def test_sync_runs_geometry_ensure_and_course_ref(self) -> None:
        with patch.object(pipeline, "_ensure_auth", return_value=True), \
                patch.object(pipeline, "_fetch_history", return_value=5), \
                patch.object(pipeline, "_ensure_geometry", return_value={"attempted": 0}) as geo, \
                patch("ai_caddie.course_reference.build_played_store", return_value={1: object()}) as store, \
                patch.object(pipeline, "_on_disk", return_value=(5, 0)):
            result = pipeline.sync(with_shots=False)
        self.assertTrue(result.auth_ok)
        geo.assert_called_once()
        store.assert_called_once()
```

In `tests/test_garmin_cn_connector.py`: **first read the file** to find its existing test that drives a
`state == "ready"` sync (it constructs `GarminCnWebSessionConnector` with a mocked `GarminCnFetchTransport`
that returns scorecards, then calls `.sync(...)` and asserts `result.state == "ready"`). Add a new test
method that reuses that exact transport-mock setup, wrapped in a `build_played_store` patch, and assert it
ran once. Concretely (substitute the file's real transport-mock construction for the `# <ready-sync setup>`
line — do not invent a helper):

```python
    def test_sync_runs_course_ref_after_ready_snapshot(self) -> None:
        with patch("ai_caddie.course_reference.build_played_store") as store:
            connector = self._ready_connector()  # build exactly as the existing ready-sync test does
            result = connector.sync(with_shots=False, force_refresh_auth=False)
            self.assertEqual(result.state, "ready")
        store.assert_called_once()
```

If the existing test builds the connector inline rather than via a helper, inline the same construction
here instead of `self._ready_connector()`.

- [ ] **Step 2: Run them — expect FAIL**

Run: `uv run python -m unittest tests.test_pipeline tests.test_garmin_cn_connector -v`

- [ ] **Step 3a: Add the shared helper** to `ai_caddie/connectors/snapshot.py`

```python
def ensure_geometry_dependencies(dependencies: list[dict[str, object]], *, root: Path = ROOT) -> dict[str, int]:
    """Idempotently download any MISSING per-hole prodgeometry. Skips rows already 'ready'."""
    from ai_caddie.geometry_sync import ensure_prodgeometry
    profile_id = geometry_player_profile_id(root=root)
    summary = {"attempted": 0, "cached": 0, "downloaded": 0, "failed": 0, "skipped": 0}
    for row in dependencies:
        if row.get("status") == "ready":
            summary["cached"] += 1
            continue
        global_id, local_hole = row.get("globalId"), row.get("localHole")
        if profile_id is None or global_id is None or local_hole is None:
            summary["skipped"] += 1
            continue
        summary["attempted"] += 1
        result = ensure_prodgeometry(int(global_id), int(local_hole), profile_id=profile_id, force=False)
        status = str(result.get("status") or "failed")
        summary["downloaded" if status == "downloaded" else "cached" if status == "cached" else "failed"] += 1
    return summary
```

- [ ] **Step 3b: Delegate from the connector** — in `ai_caddie/connectors/garmin_cn.py`, import it and replace the body of `GarminCnWebSessionConnector._ensure_geometry_dependencies` with:

```python
    def _ensure_geometry_dependencies(self, dependencies: list[dict[str, object]]) -> dict[str, int]:
        from .snapshot import ensure_geometry_dependencies
        return ensure_geometry_dependencies(dependencies, root=self.root)
```

- [ ] **Step 3c: Run the course-ref step in the connector** — in `GarminCnWebSessionConnector.sync`, immediately after `write_durable_snapshot(root=self.root, manifest=manifest)` and only when `state == "ready"`, add a failure-isolated course-ref build:

```python
            if state == "ready":
                try:
                    from ai_caddie import course_reference
                    course_reference.build_played_store()
                except Exception:
                    pass  # course-ref is best-effort; never fail the sync on it
```

- [ ] **Step 3d: Add the geometry step to the CLI pipeline** — in `ai_caddie/pipeline.py`:

Add an import at top: `from ai_caddie.data import ROOT` (alongside the existing `SCORECARD_DIR, SHOT_DIR`).

Add a module-level helper:

```python
def _ensure_geometry() -> dict:
    """Idempotently download missing prodgeometry for played courses (skips already-ready)."""
    from ai_caddie.connectors.snapshot import discover_geometry_dependencies, ensure_geometry_dependencies
    return ensure_geometry_dependencies(discover_geometry_dependencies(root=ROOT), root=ROOT)
```

In `sync`, after `rounds = _fetch_history(with_shots)` and before `store = course_reference.build_played_store()`, add:

```python
    geometry = _ensure_geometry()
```

and add `geometry` to the returned `SyncResult` notes, e.g. append:

```python
    if geometry.get("failed"):
        notes.append(f"{geometry['failed']} hole(s) missing geometry (will retry on demand)")
```

(Add a `geometry: dict | None = None` field to `SyncResult` and set it, if you want it in the JSON output; optional.)

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run python -m unittest tests.test_pipeline tests.test_garmin_cn_connector -v`

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/connectors/snapshot.py ai_caddie/connectors/garmin_cn.py ai_caddie/pipeline.py tests/test_pipeline.py tests/test_garmin_cn_connector.py
git commit -m "feat: unify sync pipeline (shared geometry-ensure; both entrypoints run course-ref)"
```

---

### Task 8: Delete GolfPass entirely + final suite

**Files:**
- Delete: `ai_caddie/scrapers/golfpass.py`, `tests/fixtures/golfpass_zhongshan_mountain_lake.html`
- Modify: `tests/test_course_reference.py` (remove `GolfPassParserTests` + `pick_course_link` tests + the `from ai_caddie.scrapers import golfpass` import)
- Maybe modify: `ai_caddie/scrapers/__init__.py` (if it re-exports golfpass)

- [ ] **Step 1: Remove the GolfPass tests + import** from `tests/test_course_reference.py` (delete the `GolfPassParserTests` class entirely and the top-level `from ai_caddie.scrapers import golfpass` line).

- [ ] **Step 2: Delete the scraper, its fixture, and clean the package init**

```bash
git rm ai_caddie/scrapers/golfpass.py tests/fixtures/golfpass_zhongshan_mountain_lake.html
```

Run: `grep -rn "golfpass\|GolfPass\|pick_course_link\|official_par_from_golfpass" ai_caddie server_v2 tests` — expected: **no matches**. If `ai_caddie/scrapers/__init__.py` imports golfpass, remove that line; if `scrapers/` is now empty of modules, leave the package (harmless) or `git rm` the dir if truly empty.

- [ ] **Step 3: CI network-safety audit (no hidden fetches)**

`resolve_par`/`build_played_store`/`prep_nine` now reach `_release_holes(..., allow_fetch=True)`, which on a
cache miss does a 30s `urlopen` — fatal in CI (no `data/`, no `omt.garmin.cn` egress). Audit every test call site:

Run: `grep -rn "resolve_par\|build_played_store\|prep_nine\|courseview_par" tests/`
For each hit, confirm it **either** patches `_release_holes`/`courseview_par`/`resolve_par`, **or** is a
geometry-gated test that skips without `data/`+geometry (so it never runs in CI). If any unguarded call
remains, patch `_release_holes` (→ `None`) in that test. (Existing `test_course_prep.py` GeometryBackedTests
skip in CI; locally they hit the release-pb cache, so no network either way.)

- [ ] **Step 3b: Run the existing tests touched by behavior changes**

Run: `uv run python -m unittest tests.test_course_reference tests.test_course_prep tests.test_server_v2_mobile -v`
Expected: PASS. (Tasks 3/5 changed `resolve_par`/`prep_nine` for **played** courses too — confirm any
`par_source == "played"` assertions still hold; cache-first `prep_nine` should preserve them.)

- [ ] **Step 3c: Full suite + compile**

Run: `uv run python -m unittest discover -s tests`
Expected: OK. (On this dev box the gitignored `data/` symlink + `output/` geometry cause ~unrelated env-dependent failures per memory `ci-uses-unittest-not-pytest`; the authoritative check is **push-CI on the branch**. The new/edited tests above must pass.)

Also: `uv run python -m py_compile $(git ls-files '*.py')` — expected: clean.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove dead GolfPass scraper (superseded by CourseView par)"
```

---

## Self-Review (run before handing off)

1. **Spec coverage:** Goal 2 (courseview par) → Tasks 1-4; prep consumer → Task 5; Goal 4 (par:4 fix) → Task 6; Goal 3 (pipeline unify) → Task 7; Goal 5 (delete GolfPass) → Tasks 3+8. (Goal 1 / course search is PR #2, separate plan.)
2. **Placeholder scan:** every code step shows real code; commands are exact; the only "adapt to existing helper" notes are in Task 6/7 tests where the file's own fixtures/helpers must be reused — flag these to the implementer.
3. **Type consistency:** `courseview_par(gid, *, allow_fetch=True)`, `_release_holes(gid, *, allow_fetch=True)`, `resolve_par(global_id, *, course_name=None, lengths_m=None, allow_fetch=True)`, `CoursePar(..., handicap=...)`, `ensure_geometry_dependencies(dependencies, *, root)`, `_ensure_geometry()` are referenced consistently across tasks. `allow_fetch` is threaded resolver→`_release_holes`; mobile passes `False` (offline-first), prep/store/pipeline use the default `True`.
4. **No hidden network in CI:** Task 8 Step 3 audits all test call sites of the resolver path (the one behavioral risk the network-touching courseview rung introduces).

## Notes for the implementer

- **CI is `unittest discover`, not pytest** (memory `ci-uses-unittest-not-pytest`): every test is a `unittest.TestCase` method; no module-level `test_*`, no pytest fixtures.
- **No live network in tests:** always patch `_release_holes` / `courseview_par` (never let `resolve_par` hit `load_release_pb(..., True)` in a test).
- **Real-data sanity (optional, not CI):** with `data/` symlinked, `uv run python -c "from ai_caddie.course_reference import resolve_par; print(resolve_par(31936).par_source, resolve_par(31936).par)"` should print `courseview [4, 5, 3, 4, 3, 4, 4, 5, 4]` (31936 is unplayed).
- Fixtures `courseview_release_*.pb` are public Garmin course indexes (no PII) — safe to commit.
