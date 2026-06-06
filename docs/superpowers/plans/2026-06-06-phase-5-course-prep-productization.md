# Phase 5 Course Prep Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make course prep a structured product API, Web surface, and offline mobile contract instead of relying on standalone `course_review/*.html`.

**Architecture:** Keep course-prep math in `ai_caddie.course_prep`, backed by `geometry_evidence` and `course_reference`. Backend endpoints return source-bound DTOs with explicit missing-data rows; Web, iOS, and Watch consume those DTOs without owning route, hazard, or par-source rules.

**Tech Stack:** Python 3.12, FastAPI, unittest, uv, React/Vite/TypeScript/Vitest, SwiftUI source contracts, JSON Schema.

---

## Current Baseline

- Existing spec: `docs/superpowers/specs/2026-06-06-phase-5-course-prep-productization-design.md`.
- Existing backend engine/API: `ai_caddie/course_prep.py`, `server_v2/main.py:/api/v2/courses/{global_id}/prep`.
- Existing Web surface: `web_v2/src/components/CoursePrepPanel.tsx`.
- Existing iOS source contracts: `mobile/ios/AICaddie/Models/CoursePrep.swift`, `mobile/ios/AICaddie/Views/CourseReviewView.swift`.
- Existing mobile package path: `/api/v2/mobile/courses/{global_id}/package`.
- Preflight issue already fixed in this run: fixture mobile package tests now isolate `stats_cache` and local geometry cache.
- Verification baseline:
  - `uv run python -m unittest tests.test_course_prep tests.test_course_prep_api tests.test_mobile_contracts tests.test_server_v2_mobile -v`
  - `npm exec --yes --package=node@24 -- npm test -- --run CoursePrepPanel MobilePackagePrepPanel`

Use the Node 24 prefix above when the machine default is Node 18.

## File Structure

- Modify `ai_caddie/course_prep.py`
  - Add stable DTO fields: `globalId`, `localHole`, `route`, `geometryCoverage`, `sourceRefs`, `missingData`, `candidateRoutes`, `carryTargets`.
  - Keep route/hazard/carry math here; Web and mobile render only.
- Modify `tests/test_course_prep.py`
  - Add pure DTO tests for source refs, route, carry targets, candidate routes, and missing geometry rows.
- Modify `tests/test_course_prep_api.py`
  - Assert API does not skip requested holes when geometry is missing.
  - Assert response is secret-free and source-bound.
- Modify `server_v2/main.py`
  - Keep endpoint path stable.
  - Return DTO rows from `course_prep.prep_nine(... include_missing=True)`.
- Modify `ai_caddie/mobile_live.py`
  - Include compact `coursePrep` rows in live round and course package responses.
  - Reuse existing caddie seeds and offline options rather than duplicating recommendation logic.
- Modify `mobile/contracts/live_round_package.schema.json`
  - Add optional `coursePrep` object accepted by v1 packages.
- Modify `tests/test_mobile_contracts.py` and `tests/test_server_v2_mobile.py`
  - Contract-test mobile package `coursePrep` fields and missing-data degradation.
- Modify `web_v2/src/types.ts`
  - Add new Course Prep DTO fields.
- Modify `web_v2/src/components/CoursePrepPanel.tsx`
  - Render source refs, missing-data rows, candidate routes, and carry targets.
  - Keep interactive route map behavior.
- Modify `web_v2/src/components/CoursePrepPanel.test.tsx`
  - Assert no holes disappear when geometry is missing.
  - Assert source refs and route/carry readouts are rendered.
- Modify `mobile/ios/AICaddie/Models/CoursePrep.swift`
  - Add Codable fields for the new DTO members with backward-compatible optional decoding.
- Modify `mobile/ios/AICaddie/Models/LiveRoundPackage.swift`
  - Add optional `coursePrep`.
- Modify `mobile/ios/AICaddieTests/CoursePrepTests.swift`
  - Decode new fields and keep legacy fixture decode valid.
- Modify `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
  - Mark Phase 5 items complete only after verification and evidence are recorded.
- Create `docs/superpowers/reviews/2026-06-06-phase-5-course-prep-productization.md`
  - Record commands, results, and residual non-Linux/native constraints.

### Task 1: Course Prep DTO Completeness

**Files:**
- Modify: `ai_caddie/course_prep.py`
- Modify: `tests/test_course_prep.py`

- [ ] **Step 1: Write failing DTO test**

Add to `tests/test_course_prep.py`:

```python
def test_prep_hole_returns_source_refs_route_carry_targets_and_candidate_routes(self) -> None:
    md = {"hole": {
        "TeeLocations": [{"Sets": [2], "X": 0.0, "Y": 0.0}],
        "Doglegs": [{"Line": [{"X": 0.0, "Y": 0.0}, {"X": 0.0, "Y": 320.0}]}],
    }}
    with patch.object(cp.hole_render, "load_mesh", return_value=(md, {})), \
            patch("ai_caddie.course_prep.geometry_coverage_for_hole", return_value={
                "coverage": "ready",
                "evidence": [{"label": "hazards", "ref": "output/prodgeometry_hazards/gid99999_h01_hazards.json"}],
                "missingData": [],
            }):
        prep = cp.prep_hole(
            99999,
            1,
            ladder=[("1W", 200), ("7I", 128)],
            par_record=CoursePar(global_id=99999, par=[4], par_source="courseview", confidence="high"),
            render=False,
        )

    self.assertIsNotNone(prep)
    row = prep if isinstance(prep, dict) else prep.to_dict()
    self.assertEqual(row["globalId"], 99999)
    self.assertEqual(row["localHole"], 1)
    self.assertEqual(row["geometryCoverage"], "ready")
    self.assertEqual(row["sourceRefs"], ["course:99999", "geometry:99999:1"])
    self.assertEqual(row["missingData"], [])
    self.assertEqual(row["route"][0], [0.0, 0.0, 0.0])
    self.assertEqual(row["route"][-1], [0.0, 320.0, 320.0])
    self.assertEqual([row["id"] for row in row["candidateRoutes"]], ["safe", "stock", "attack"])
    self.assertTrue(any(target["kind"] == "landing" for target in row["carryTargets"]))
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
uv run python -m unittest tests.test_course_prep.PureLogicTests.test_prep_hole_returns_source_refs_route_carry_targets_and_candidate_routes -v
```

Expected: FAIL because the new DTO fields do not exist.

- [ ] **Step 3: Implement minimal DTO fields**

In `ai_caddie/course_prep.py`:

```python
from ai_caddie.geometry_evidence import geometry_coverage_for_hole

@dataclass
class HolePrep:
    globalId: int
    localHole: int
    hole: int
    par: int
    par_source: str
    blue_yards: int
    route_len_m: float
    route: list[list[float]] = field(default_factory=list)
    geometryCoverage: str = "missing"
    sourceRefs: list[str] = field(default_factory=list)
    missingData: list[dict] = field(default_factory=list)
    candidateRoutes: list[dict] = field(default_factory=list)
    carryTargets: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    landing_m: float | None = None
    tee_club: str | None = None
    hazards: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
```

Add helpers:

```python
def _route_with_cumulative(route: list[tuple[float, float]]) -> list[list[float]]:
    out: list[list[float]] = []
    cumulative = 0.0
    for index, point in enumerate(route):
        if index:
            previous = route[index - 1]
            cumulative += math.hypot(point[0] - previous[0], point[1] - previous[1])
        out.append([round(point[0], 1), round(point[1], 1), round(cumulative, 1)])
    return out

def _candidate_routes(ladder: list[tuple[str, int]], hazards: dict) -> list[dict]:
    if not ladder:
        return []
    longest_name, longest_m = ladder[0]
    safe_name, safe_m = next((row for row in ladder[1:] if row[1] >= 120), ladder[0])
    risk = 3 if (hazards.get("water_carry") or hazards.get("bunkers")) else 1
    return [
        {"id": "safe", "club": safe_name, "carryM": float(safe_m), "riskScore": 0, "source": "course_prep"},
        {"id": "stock", "club": longest_name, "carryM": float(longest_m), "riskScore": 1, "source": "course_prep"},
        {"id": "attack", "club": longest_name, "carryM": float(longest_m), "riskScore": risk, "source": "course_prep"},
    ]

def _carry_targets(landing_m: float | None, hazards: dict) -> list[dict]:
    rows: list[dict] = []
    if landing_m is not None:
        rows.append({"kind": "landing", "distanceM": round(landing_m, 1)})
    for start, end in hazards.get("water_carry") or []:
        rows.append({"kind": "water_clear", "enterM": float(start), "clearM": float(end)})
    for distance, side in hazards.get("bunkers") or []:
        rows.append({"kind": "bunker", "distanceM": float(distance), "sideM": float(side)})
    return rows
```

Update `prep_hole()` to populate the new fields and return `prep.to_dict()` when `render=False`.

- [ ] **Step 4: Run DTO test to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_course_prep.PureLogicTests.test_prep_hole_returns_source_refs_route_carry_targets_and_candidate_routes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/course_prep.py tests/test_course_prep.py
git commit -m "feat: expose structured course prep dto fields"
```

### Task 2: Preserve Missing Holes In Prep Responses

**Files:**
- Modify: `ai_caddie/course_prep.py`
- Modify: `tests/test_course_prep.py`
- Modify: `tests/test_course_prep_api.py`

- [ ] **Step 1: Write failing missing-hole tests**

Add to `tests/test_course_prep.py`:

```python
def test_prep_nine_keeps_requested_missing_geometry_rows(self) -> None:
    rec = CoursePar(99999, [4, 5], "courseview", "high")
    with patch.object(course_reference, "load_course_par", return_value=rec), \
            patch.object(course_prep, "prep_hole", side_effect=[None, {"hole": 2, "missingData": []}]):
        rows = course_prep.prep_nine(99999, holes=[1, 2], render=False, include_missing=True)

    self.assertEqual([row["hole"] for row in rows], [1, 2])
    self.assertEqual(rows[0]["geometryCoverage"], "missing")
    self.assertEqual(rows[0]["missingData"][0]["label"], "geometry")
```

Add to `tests/test_course_prep_api.py`:

```python
def test_prep_endpoint_keeps_missing_geometry_rows(self) -> None:
    with patch.object(course_reference, "load_course_par", return_value=_PAR_31870), \
            patch("ai_caddie.course_prep.prep_nine", return_value=[
                {
                    "globalId": 31870,
                    "localHole": 1,
                    "hole": 1,
                    "par": 5,
                    "par_source": "played",
                    "blue_yards": 0,
                    "route_len_m": 0.0,
                    "route": [],
                    "geometryCoverage": "missing",
                    "sourceRefs": ["course:31870", "geometry:31870:1"],
                    "missingData": [{"label": "geometry", "reason": "prodgeometry mesh file missing"}],
                    "candidateRoutes": [],
                    "carryTargets": [],
                    "steps": [],
                    "cautions": [],
                    "landing_m": None,
                    "tee_club": None,
                    "hazards": {"water_carry": [], "bunkers": []},
                }
            ]):
        resp = self.client.get("/api/v2/courses/31870/prep?holes=1&render=false")

    self.assertEqual(resp.status_code, 200)
    body = resp.json()
    self.assertEqual(body["holeCount"], 1)
    self.assertEqual(body["holes"][0]["geometryCoverage"], "missing")
    self.assertEqual(body["holes"][0]["missingData"][0]["label"], "geometry")
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run python -m unittest tests.test_course_prep.PrepResolvesParTests.test_prep_nine_keeps_requested_missing_geometry_rows tests.test_course_prep_api.CoursePrepApiTests.test_prep_endpoint_keeps_missing_geometry_rows -v
```

Expected: FAIL because `include_missing` does not exist and missing holes are skipped.

- [ ] **Step 3: Implement missing-hole row**

In `ai_caddie/course_prep.py`:

```python
def _missing_hole(global_id: int, local_hole: int, par_record=None) -> dict:
    par_idx = int(local_hole) - 1
    par = par_record.par[par_idx] if par_record is not None and 0 <= par_idx < len(par_record.par) else 4
    par_source = par_record.par_source if par_record is not None and 0 <= par_idx < len(par_record.par) else "estimate"
    return {
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "hole": int(local_hole),
        "par": int(par),
        "par_source": par_source,
        "blue_yards": 0,
        "route_len_m": 0.0,
        "route": [],
        "geometryCoverage": "missing",
        "sourceRefs": [f"course:{int(global_id)}", f"geometry:{int(global_id)}:{int(local_hole)}"],
        "missingData": [{"label": "geometry", "reason": "prodgeometry geometry is missing for this hole"}],
        "candidateRoutes": [],
        "carryTargets": [],
        "steps": [],
        "cautions": [],
        "landing_m": None,
        "tee_club": None,
        "hazards": {"water_carry": [], "bunkers": []},
    }
```

Change signature:

```python
def prep_nine(global_id: int, holes=range(1, 10), *, ladder=None, render=True, include_missing: bool = False) -> list:
```

When `prep_hole()` returns `None`, append `_missing_hole(...)` only if `include_missing` is true.

In `server_v2/main.py`, call:

```python
nine = course_prep.prep_nine(global_id, requested, ladder=ladder, render=render, include_missing=True)
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_course_prep tests.test_course_prep_api -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/course_prep.py server_v2/main.py tests/test_course_prep.py tests/test_course_prep_api.py
git commit -m "feat: keep missing course prep holes in api"
```

### Task 3: Feed Course Prep Into Mobile Packages

**Files:**
- Modify: `ai_caddie/mobile_live.py`
- Modify: `mobile/contracts/live_round_package.schema.json`
- Modify: `tests/test_mobile_contracts.py`
- Modify: `tests/test_server_v2_mobile.py`

- [ ] **Step 1: Write failing mobile package tests**

Add to `tests/test_server_v2_mobile.py`:

```python
def test_mobile_course_package_includes_compact_course_prep(self) -> None:
    client = TestClient(app)
    prep_rows = [{
        "globalId": 31795,
        "localHole": 1,
        "hole": 1,
        "par": 4,
        "par_source": "courseview",
        "blue_yards": 410,
        "route_len_m": 375.0,
        "route": [[0.0, 0.0, 0.0], [0.0, 375.0, 375.0]],
        "geometryCoverage": "ready",
        "sourceRefs": ["course:31795", "geometry:31795:1"],
        "missingData": [],
        "candidateRoutes": [{"id": "stock", "carryM": 200.0, "riskScore": 1}],
        "carryTargets": [{"kind": "landing", "distanceM": 200.0}],
        "steps": [{"club": "1W", "note": "stock tee"}],
        "cautions": [],
        "landing_m": 200.0,
        "tee_club": "1W",
        "hazards": {"water_carry": [], "bunkers": []},
    }]
    with patch.dict("os.environ", {"AI_CADDIE_DATA_MODE": "fixture"}), \
            patch("ai_caddie.mobile_live.course_prep.prep_nine", return_value=prep_rows):
        response = client.get("/api/v2/mobile/courses/31795/package", params={"round_id": "live-31795"})

    self.assertEqual(response.status_code, 200)
    course_prep = response.json()["coursePrep"]
    self.assertEqual(course_prep["schema"], "ai-caddie-course-prep-package-v1")
    self.assertEqual(course_prep["globalId"], 31795)
    self.assertEqual(course_prep["holes"][0]["candidateRoutes"][0]["id"], "stock")
    self.assertEqual(course_prep["holes"][0]["sourceRefs"], ["course:31795", "geometry:31795:1"])
```

Add a schema assertion to `tests/test_mobile_contracts.py` fixture payload:

```python
"coursePrep": {
    "schema": "ai-caddie-course-prep-package-v1",
    "globalId": 31795,
    "holes": [{"hole": 1, "geometryCoverage": "ready", "candidateRoutes": [], "carryTargets": [], "missingData": []}],
}
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run python -m unittest tests.test_server_v2_mobile.ServerV2MobileTests.test_mobile_course_package_includes_compact_course_prep tests.test_mobile_contracts.MobileContractTests.test_live_round_package_schema_accepts_fixture -v
```

Expected: FAIL because `coursePrep` is not present/accepted yet.

- [ ] **Step 3: Implement compact package**

In `ai_caddie/mobile_live.py`, import `course_prep`:

```python
from ai_caddie import course_prep
```

Add:

```python
def _course_prep_package(global_id: int, holes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not global_id:
        return None
    hole_numbers = [int(row["number"]) for row in holes if row.get("number")]
    try:
        prep_rows = course_prep.prep_nine(int(global_id), holes=hole_numbers, render=False, include_missing=True)
    except Exception:
        return {
            "schema": "ai-caddie-course-prep-package-v1",
            "globalId": int(global_id),
            "holes": [],
            "missingData": [{"label": "course_prep", "reason": "course prep package could not be built"}],
        }
    return {
        "schema": "ai-caddie-course-prep-package-v1",
        "globalId": int(global_id),
        "holes": prep_rows,
        "missingData": [row for hole in prep_rows for row in (hole.get("missingData") or [])],
    }
```

In `build_live_round_package()`, add:

```python
course_prep_package = _course_prep_package(int(round_row.get("globalId") or 0), holes)
```

and include:

```python
"coursePrep": course_prep_package,
```

Update JSON schema with optional `coursePrep` property of type object. Keep it optional for legacy package compatibility.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run python -m unittest tests.test_server_v2_mobile tests.test_mobile_contracts -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/mobile_live.py mobile/contracts/live_round_package.schema.json tests/test_mobile_contracts.py tests/test_server_v2_mobile.py
git commit -m "feat: include course prep in mobile packages"
```

### Task 4: Web Course Prep Product Surface

**Files:**
- Modify: `web_v2/src/types.ts`
- Modify: `web_v2/src/components/CoursePrepPanel.tsx`
- Modify: `web_v2/src/components/CoursePrepPanel.test.tsx`
- Modify: `web_v2/src/components/coursePrepPanelLogic.ts` only if route/carry formatting needs shared helpers.

- [ ] **Step 1: Write failing Web rendering test**

In `web_v2/src/components/CoursePrepPanel.test.tsx`, add to the response fixture:

```typescript
{
  hole: 2,
  par: 4,
  par_source: 'estimate',
  blue_yards: 0,
  route_len_m: 0,
  route: [],
  geometryCoverage: 'missing',
  sourceRefs: ['course:31870', 'geometry:31870:2'],
  missingData: [{ label: 'geometry', reason: 'prodgeometry geometry is missing for this hole' }],
  candidateRoutes: [],
  carryTargets: [],
  steps: [],
  cautions: [],
  landing_m: null,
  tee_club: null,
  hazards: { water_carry: [], bunkers: [] },
}
```

Assert:

```typescript
expect(screen.getByText('2 洞')).toBeInTheDocument()
expect(screen.getByText('geometry missing')).toBeInTheDocument()
expect(screen.getByText('course:31870')).toBeInTheDocument()
expect(screen.getByText('stock')).toBeInTheDocument()
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm test -- --run CoursePrepPanel
```

Expected: FAIL because the new DTO fields are not typed/rendered.

- [ ] **Step 3: Add types and render rows**

In `web_v2/src/types.ts`, extend `CoursePrepHole`:

```typescript
  route: Array<[number, number, number]>
  geometryCoverage: GeometryCoverageState
  sourceRefs: string[]
  missingData: Array<{ label?: string; reason?: string }>
  candidateRoutes: Array<{ id: string; club?: string; carryM?: number; riskScore?: number }>
  carryTargets: Array<{ kind: string; distanceM?: number; enterM?: number; clearM?: number; sideM?: number }>
```

In `CoursePrepPanel.tsx`, render below the map/readout:

```tsx
{hole.candidateRoutes.length ? (
  <div className="course-prep-route-list" aria-label={`Hole ${hole.hole} route options`}>
    {hole.candidateRoutes.map((route) => (
      <span key={route.id}>{route.id}{route.carryM ? ` ${Math.round(route.carryM * 1.09361)}y` : ''}</span>
    ))}
  </div>
) : null}
{hole.missingData.length ? (
  <div className="course-prep-missing-list" aria-label={`Hole ${hole.hole} missing data`}>
    {hole.missingData.map((row, index) => (
      <span key={`${row.label ?? 'missing'}-${index}`}>{row.label ?? 'missing'} missing</span>
    ))}
  </div>
) : null}
{hole.sourceRefs.length ? (
  <div className="course-prep-source-list" aria-label={`Hole ${hole.hole} source refs`}>
    {hole.sourceRefs.map((ref) => <span key={ref}>{ref}</span>)}
  </div>
) : null}
```

- [ ] **Step 4: Run Web tests**

Run:

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm test -- --run CoursePrepPanel MobilePackagePrepPanel
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web_v2/src/types.ts web_v2/src/components/CoursePrepPanel.tsx web_v2/src/components/CoursePrepPanel.test.tsx web_v2/src/components/coursePrepPanelLogic.ts
git commit -m "feat: render product course prep dto"
```

### Task 5: iOS And Watch Course Prep Contract

**Files:**
- Modify: `mobile/ios/AICaddie/Models/CoursePrep.swift`
- Modify: `mobile/ios/AICaddie/Models/LiveRoundPackage.swift`
- Modify: `mobile/ios/AICaddieTests/CoursePrepTests.swift`
- Modify: `tests/test_mobile_contracts.py`

- [ ] **Step 1: Write failing source contract tests**

In `tests/test_mobile_contracts.py`, extend `test_swift_models_define_codable_contract_types`:

```python
course_prep = _read_required_source(self, IOS_DIR / "Models" / "CoursePrep.swift")
package_swift = _read_required_source(self, IOS_DIR / "Models" / "LiveRoundPackage.swift")
self.assertIn("let geometryCoverage: String", course_prep)
self.assertIn("let sourceRefs: [String]", course_prep)
self.assertIn("let missingData: [CoursePrepMissingData]", course_prep)
self.assertIn("let candidateRoutes: [CoursePrepCandidateRoute]", course_prep)
self.assertIn("let carryTargets: [CoursePrepCarryTarget]", course_prep)
self.assertIn("let coursePrep: CoursePrepPackage?", package_swift)
```

In `mobile/ios/AICaddieTests/CoursePrepTests.swift`, add JSON decode assertions for the new fields.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run python -m unittest tests.test_mobile_contracts.MobileContractTests.test_swift_models_define_codable_contract_types -v
```

Expected: FAIL because Swift source lacks these fields.

- [ ] **Step 3: Implement Swift Codable fields**

In `CoursePrep.swift`:

```swift
public struct CoursePrepMissingData: Codable, Equatable {
    public let label: String?
    public let reason: String?
}

public struct CoursePrepCandidateRoute: Codable, Equatable {
    public let id: String
    public let club: String?
    public let carryM: Double?
    public let riskScore: Double?
}

public struct CoursePrepCarryTarget: Codable, Equatable {
    public let kind: String
    public let distanceM: Double?
    public let enterM: Double?
    public let clearM: Double?
    public let sideM: Double?
}

public struct CoursePrepPackage: Codable, Equatable {
    public let schema: String
    public let globalId: Int
    public let holes: [CoursePrepHole]
    public let missingData: [CoursePrepMissingData]?
}
```

Extend `CoursePrepHole` with optional-safe decode for the new fields. In `LiveRoundPackage.swift`, add `public let coursePrep: CoursePrepPackage?` and decode with `decodeIfPresent`.

- [ ] **Step 4: Run source contract tests**

Run:

```bash
uv run python -m unittest tests.test_mobile_contracts.MobileContractTests.test_swift_models_define_codable_contract_types tests.test_mobile_contracts.MobileContractTests.test_ios_course_review_product_copy_and_route_yardage_contract -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/ios/AICaddie/Models/CoursePrep.swift mobile/ios/AICaddie/Models/LiveRoundPackage.swift mobile/ios/AICaddieTests/CoursePrepTests.swift tests/test_mobile_contracts.py
git commit -m "feat: extend native course prep contracts"
```

### Task 6: Phase 5 Verification And Evidence

**Files:**
- Modify: `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`
- Create: `docs/superpowers/reviews/2026-06-06-phase-5-course-prep-productization.md`

- [ ] **Step 1: Run backend/mobile verification**

Run:

```bash
uv run python -m unittest tests.test_course_prep tests.test_course_prep_api tests.test_mobile_contracts tests.test_server_v2_mobile -v
```

Expected: PASS.

- [ ] **Step 2: Run Web verification**

Run:

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm test -- --run CoursePrepPanel MobilePackagePrepPanel
cd web_v2 && npm exec --yes --package=node@24 -- npm run lint
cd web_v2 && npm exec --yes --package=node@24 -- npm run build
```

Expected: PASS. If a native Node 24 install is available, use plain `npm`; otherwise keep the `npm exec --package=node@24` prefix.

- [ ] **Step 3: Run formatting check**

Run:

```bash
git diff --check
```

Expected: PASS.

- [ ] **Step 4: Record evidence**

Create `docs/superpowers/reviews/2026-06-06-phase-5-course-prep-productization.md`:

```markdown
# Phase 5 Course Prep Productization Evidence

- Date: 2026-06-06
- Branch: `integration/v2`

## Scope

Implemented Phase 5 from `docs/superpowers/specs/2026-06-06-phase-5-course-prep-productization-design.md`.

## Evidence

- Course prep API returns structured DTO rows with source refs, missing-data rows, route data, candidate routes, and carry targets.
- Web v2 renders missing holes and source-bound route/carry readouts.
- Mobile packages include compact course-prep fields for offline use.
- iOS source contracts decode the product course-prep DTO.

## Verification

```bash
uv run python -m unittest tests.test_course_prep tests.test_course_prep_api tests.test_mobile_contracts tests.test_server_v2_mobile -v
```

Result: PASS.

```bash
cd web_v2 && npm exec --yes --package=node@24 -- npm test -- --run CoursePrepPanel MobilePackagePrepPanel
```

Result: PASS.

```bash
git diff --check
```

Result: PASS.
```

- [ ] **Step 5: Mark roadmap Phase 5 complete**

In `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`, change the four Phase 5 checkboxes to `[x]` only after the verification above is complete.

- [ ] **Step 6: Commit evidence**

```bash
git add docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md docs/superpowers/reviews/2026-06-06-phase-5-course-prep-productization.md
git commit -m "docs: record phase 5 course prep completion"
```

## Final Verification

Run:

```bash
uv run python -m unittest tests.test_course_prep tests.test_course_prep_api tests.test_mobile_contracts tests.test_server_v2_mobile -v
cd web_v2 && npm exec --yes --package=node@24 -- npm test -- --run CoursePrepPanel MobilePackagePrepPanel
git diff --check
```

Expected: all commands exit 0.
