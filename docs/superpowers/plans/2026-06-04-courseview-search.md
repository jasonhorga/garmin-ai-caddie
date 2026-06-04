# Course Search (name → globalId) Implementation Plan (Theme B, PR #2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discover a Garmin course's globalId from a name/location via the anonymous CourseView search endpoint, so pre-round prep works for a course the user has never played — closing Goal 1 of the Theme-B design.

**Architecture:** A new deterministic module `ai_caddie/course_search.py` GETs `https://omt.garmin.cn/CourseViewData/courses?CourseName=<q>` (anonymous, no auth), decodes the protobuf (reusing `inspect_courseview_release.parse_fields`) into course records (`f7`=globalId, `f12`=name, `f13`=holeCount, `f16`=province, `f21`=city), fuzzy-matches the query against the name (stdlib `difflib`) with a hole-count + city/province guard, and returns ranked matches. A `GET /api/v2/courses/search` endpoint surfaces them; the chosen globalId flows into the existing `/api/v2/courses/{global_id}/prep` (PR #1 par + geometry).

**Tech Stack:** Python 3, `uv`, `unittest` (CI runs `uv run python -m unittest discover -s tests` — NOT pytest), FastAPI, protobuf hand-decoded via the existing `inspect_courseview_release` varint walker.

**Conventions:** TDD. Tests are `unittest.TestCase` (module-level `def test_*` / pytest fixtures are invisible to CI). **No live network in tests** — patch the fetch/parse seam; the endpoint is exercised via FastAPI `TestClient` with the search function patched. Verify each test with `uv run python -m unittest tests.<module> -v`.

**Scope:** Backend search endpoint + module only. (Web/iOS already understand `par_source:"courseview"` from PR #1; a client *search UI* is a later follow-up, not this PR.)

---

## File Structure

- `ai_caddie/course_search.py` — **create**: `CourseMatch` dataclass, `parse_course_search(pb)` (decode), `courseview_search(name, *, city, expected_holes, allow_fetch)` (fetch + fuzzy + guard). Single responsibility: name→globalId discovery. Reuses `inspect_courseview_release.{BASE, parse_fields, fetch_bytes}`.
- `server_v2/main.py` — **modify**: add `GET /api/v2/courses/search` route; add its path to `_requires_admin_token` (admin-gated, like `/courses/{id}/prep`).
- `tests/fixtures/courseview_search_zhongshan.pb` — **create**: a captured search response (public course list; no PII).
- `tests/test_course_search.py` — **create**: decode + fuzzy/guard + endpoint tests.

---

### Task 1: Decode the course-search protobuf

**Files:**
- Create: `ai_caddie/course_search.py` (decode half), `tests/fixtures/courseview_search_zhongshan.pb`, `tests/test_course_search.py`

- [ ] **Step 1: Capture the fixture (anonymous, public data)**

Run:
```bash
uv run python -c "
import requests
r = requests.get('https://omt.garmin.cn/CourseViewData/courses', params={'CourseName':'钟山'}, headers={'User-Agent':'Mozilla/5.0'}, timeout=20)
r.raise_for_status()
open('tests/fixtures/courseview_search_zhongshan.pb','wb').write(r.content)
print('saved', len(r.content), 'bytes')
"
```
Expected: saves ~700 bytes. (The Zhongshan nines 31934/31935/31936 are stable; this fixture is read offline by the tests.)

- [ ] **Step 2: Write the failing test** — `tests/test_course_search.py`

```python
import unittest
from pathlib import Path

from ai_caddie import course_search as cs

FIX = Path(__file__).parent / "fixtures"


class ParseCourseSearchTests(unittest.TestCase):
    def test_parses_records_from_fixture(self) -> None:
        records = cs.parse_course_search((FIX / "courseview_search_zhongshan.pb").read_bytes())
        by_gid = {r["global_id"]: r for r in records}
        # the three Zhongshan nines are stable
        self.assertIn(31936, by_gid)
        c = by_gid[31936]
        self.assertEqual(c["name"], "Nanjing Zhongshan International Golf Club ~ C Valley")
        self.assertEqual(c["holes"], 9)
        self.assertEqual(c["province"], "jiangsu")
        self.assertIn("Nanjing", c["city"])
        self.assertEqual({31934, 31935, 31936} & set(by_gid), {31934, 31935, 31936})

    def test_empty_bytes_yields_no_records(self) -> None:
        self.assertEqual(cs.parse_course_search(b""), [])
```

- [ ] **Step 3: Run it — expect FAIL** (`ModuleNotFoundError: ai_caddie.course_search`)

Run: `uv run python -m unittest tests.test_course_search.ParseCourseSearchTests -v`

- [ ] **Step 4: Implement the decode half** — `ai_caddie/course_search.py`

```python
"""Course search: name/location -> Garmin globalId via the anonymous CourseView search
endpoint (``omt.garmin.cn/CourseViewData/courses?CourseName=``). NO auth, NO AI. Deterministic
protobuf decode + stdlib fuzzy match, guarded by hole-count + city/province.

Per-course record (top field 4, repeated): f7=globalId, f12=name, f13=holeCount,
f16=province, f21=city. (Records may be a single nine (9 holes) or a whole 18-hole course.)
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from inspect_courseview_release import BASE, fetch_bytes, parse_fields

_MIN_QUERY = 2  # the endpoint requires >=3 ascii or >=2 CJK chars


@dataclass
class CourseMatch:
    global_id: int
    name: str
    holes: int | None
    city: str | None
    province: str | None
    ratio: float


def parse_course_search(pb: bytes) -> list[dict]:
    """Decode the search protobuf into a list of course records (best-effort, never raises)."""
    out: list[dict] = []
    try:
        for field_no, wire_type, _value, raw in parse_fields(pb):
            if field_no != 4 or wire_type != 2 or raw is None:
                continue
            rec: dict = {}
            for sub_no, sub_wire, sub_value, _sub_raw in parse_fields(raw):
                if sub_no == 7 and sub_wire == 0:
                    rec["global_id"] = sub_value
                elif sub_no == 12 and sub_wire == 2:
                    rec["name"] = sub_value
                elif sub_no == 13 and sub_wire == 0:
                    rec["holes"] = sub_value
                elif sub_no == 16 and sub_wire == 2:
                    rec["province"] = sub_value
                elif sub_no == 21 and sub_wire == 2:
                    rec["city"] = sub_value
            if rec.get("global_id") is not None and rec.get("name"):
                rec.setdefault("holes", None)
                rec.setdefault("city", None)
                rec.setdefault("province", None)
                out.append(rec)
    except Exception:
        return out
    return out
```

(Note: `parse_fields` yields `(field_no, wire_type, value, raw)` where `value` is the utf-8-decoded string for wire type 2, or the int for wire type 0; `raw` is the bytes for wire type 2.)

- [ ] **Step 5: Run it — expect PASS**

Run: `uv run python -m unittest tests.test_course_search.ParseCourseSearchTests -v`

- [ ] **Step 6: Commit**

```bash
git add ai_caddie/course_search.py tests/test_course_search.py tests/fixtures/courseview_search_zhongshan.pb
git commit -m "feat: decode the anonymous CourseView course-search protobuf"
```

---

### Task 2: `courseview_search` — fetch + fuzzy-match + hole-count/city guard

**Files:**
- Modify: `ai_caddie/course_search.py` (add `courseview_search` + a fetch helper)
- Test: `tests/test_course_search.py` (append)

- [ ] **Step 1: Write the failing test** — append to `tests/test_course_search.py`

```python
from unittest.mock import patch


class CourseviewSearchTests(unittest.TestCase):
    def _fixture(self) -> bytes:
        return (FIX / "courseview_search_zhongshan.pb").read_bytes()

    def test_ranks_and_returns_matches(self) -> None:
        with patch.object(cs, "_fetch_search", return_value=self._fixture()):
            matches = cs.courseview_search("Zhongshan C Valley")
        self.assertTrue(matches)
        self.assertEqual(matches[0].global_id, 31936)  # best fuzzy match ranked first
        self.assertTrue(all(isinstance(m, cs.CourseMatch) for m in matches))
        self.assertTrue(matches[0].ratio >= matches[-1].ratio)  # ranked desc

    def test_hole_count_guard_filters(self) -> None:
        with patch.object(cs, "_fetch_search", return_value=self._fixture()):
            matches = cs.courseview_search("Zhongshan", expected_holes=18)
        self.assertEqual(matches, [])  # all Zhongshan records are 9-hole nines

    def test_city_guard_filters(self) -> None:
        with patch.object(cs, "_fetch_search", return_value=self._fixture()):
            hit = cs.courseview_search("Zhongshan", city="Nanjing")
            miss = cs.courseview_search("Zhongshan", city="Shanghai")
        self.assertTrue(hit)
        self.assertEqual(miss, [])

    def test_short_query_returns_empty_without_fetch(self) -> None:
        with patch.object(cs, "_fetch_search") as fetch:
            self.assertEqual(cs.courseview_search("z"), [])
        fetch.assert_not_called()
```

- [ ] **Step 2: Run it — expect FAIL** (`AttributeError: _fetch_search` / `courseview_search`)

Run: `uv run python -m unittest tests.test_course_search.CourseviewSearchTests -v`

- [ ] **Step 3: Implement** — add to `ai_caddie/course_search.py`

```python
def _fetch_search(query: str) -> bytes:
    """GET the anonymous CourseView search endpoint. The only networked call here."""
    import urllib.parse
    url = f"{BASE}/courses?CourseName={urllib.parse.quote(query)}"
    return fetch_bytes(url)


def _location_blob(rec: dict) -> str:
    return f"{rec.get('city') or ''} {rec.get('province') or ''}".lower()


def courseview_search(
    name: str,
    *,
    city: str | None = None,
    expected_holes: int | None = None,
    allow_fetch: bool = True,
) -> list[CourseMatch]:
    """Search Garmin's course DB by name; return ranked CourseMatch list.

    Fuzzy-ranks each candidate's name against ``name`` (stdlib difflib) and applies a guard:
    drop a candidate whose hole count != ``expected_holes`` (when given) or whose city/province
    doesn't contain ``city`` (when given). Empty list on a too-short query, no results, or fetch
    failure — never raises, never silently returns a wrong course (the guard filters).
    """
    q = (name or "").strip()
    if len(q) < _MIN_QUERY:
        return []
    if not allow_fetch:
        return []
    try:
        pb = _fetch_search(q)
    except Exception:
        return []
    ql = q.lower()
    matches: list[CourseMatch] = []
    for rec in parse_course_search(pb):
        if expected_holes is not None and rec.get("holes") != expected_holes:
            continue
        if city and city.strip().lower() not in _location_blob(rec):
            continue
        ratio = difflib.SequenceMatcher(None, ql, (rec["name"] or "").lower()).ratio()
        matches.append(CourseMatch(
            global_id=int(rec["global_id"]), name=rec["name"], holes=rec.get("holes"),
            city=rec.get("city"), province=rec.get("province"), ratio=round(ratio, 3),
        ))
    matches.sort(key=lambda m: m.ratio, reverse=True)
    return matches
```

- [ ] **Step 4: Run it — expect PASS**

Run: `uv run python -m unittest tests.test_course_search.CourseviewSearchTests -v`

- [ ] **Step 5: Commit**

```bash
git add ai_caddie/course_search.py tests/test_course_search.py
git commit -m "feat: courseview_search() — fuzzy name match + hole-count/city guard"
```

---

### Task 3: `GET /api/v2/courses/search` endpoint (admin-gated)

**Files:**
- Modify: `server_v2/main.py` (add route + admin-gating entry)
- Test: `tests/test_course_search.py` (append endpoint test)

- [ ] **Step 1: Write the failing test** — append to `tests/test_course_search.py`

```python
class CourseSearchEndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from server_v2.main import app
        return TestClient(app)

    def test_search_endpoint_returns_matches(self) -> None:
        from ai_caddie import course_search
        canned = [course_search.CourseMatch(31936, "Nanjing Zhongshan ~ C Valley", 9, "Nanjing", "jiangsu", 0.9)]
        with patch("server_v2.main.course_search.courseview_search", return_value=canned):
            r = self._client().get("/api/v2/courses/search", params={"name": "zhongshan"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["schema"], "ai-caddie-course-search-v1")
        self.assertEqual(body["query"], "zhongshan")
        self.assertEqual(body["matches"][0]["globalId"], 31936)
        self.assertEqual(body["matches"][0]["holes"], 9)

    def test_search_endpoint_empty_on_no_match(self) -> None:
        with patch("server_v2.main.course_search.courseview_search", return_value=[]):
            r = self._client().get("/api/v2/courses/search", params={"name": "nope"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["matches"], [])
```

(Note: the default test profile does not enforce the admin token, so no header is needed; the admin-gating change in Step 3 only takes effect under a security profile. If the suite runs with a profile that enforces it, add `headers={"X-AI-Caddie-Admin-Token": "<token>"}`.)

- [ ] **Step 2: Run it — expect FAIL** (404, route not defined)

Run: `uv run python -m unittest tests.test_course_search.CourseSearchEndpointTests -v`

- [ ] **Step 3: Implement** in `server_v2/main.py`

(a) Add the route (place it right after the `course_prep_nine` route, ~line 415):

```python
@app.get("/api/v2/courses/search")
def course_search_endpoint(
    name: str,
    city: str | None = None,
    holes: int | None = None,
) -> dict:
    """Search Garmin's course DB by name (+ optional city / hole-count guard); returns ranked
    matches with globalId. Feed a chosen globalId into /api/v2/courses/{global_id}/prep."""
    from ai_caddie import course_search

    matches = course_search.courseview_search(name, city=city, expected_holes=holes)
    return {
        "schema": "ai-caddie-course-search-v1",
        "query": name,
        "matches": [
            {"globalId": m.global_id, "name": m.name, "holes": m.holes,
             "city": m.city, "province": m.province, "ratio": m.ratio}
            for m in matches
        ],
    }
```

Also add a module-level alias so the test's patch target (`server_v2.main.course_search`) resolves — at the top of `server_v2/main.py` with the other imports, add:
```python
from ai_caddie import course_search
```
(and the route body can then use the module-level `course_search` instead of the local import; either is fine, but the module-level import is what the endpoint test patches).

(b) Admin-gate it consistently with `/courses/{id}/prep` — in `_requires_admin_token`, in the GET branch, add a clause:
```python
            or path == "/api/v2/courses/search"
```
(next to the existing `path.startswith("/api/v2/courses/") and path.endswith("/prep")` line).

- [ ] **Step 4: Run it — expect PASS**

Run: `uv run python -m unittest tests.test_course_search.CourseSearchEndpointTests -v`

- [ ] **Step 5: Full module + CI-safety**

Run: `uv run python -m unittest tests.test_course_search -v` → all PASS.
Audit: `grep -rn "courseview_search\|_fetch_search\|parse_course_search" tests/` — every test must patch `_fetch_search` or `course_search.courseview_search` (never hit the live omt endpoint in CI). Confirm none is unguarded.

- [ ] **Step 6: Commit**

```bash
git add server_v2/main.py tests/test_course_search.py
git commit -m "feat: GET /api/v2/courses/search (admin-gated course discovery)"
```

---

## Self-Review (run before handing off)

1. **Spec coverage (Goal 1):** name/location → globalId via the anonymous CourseView search → Tasks 1–3 (`parse_course_search`, `courseview_search` with fuzzy + hole-count/city guard, `/api/v2/courses/search`). The chosen globalId flows into the existing `/courses/{id}/prep`. ✓
2. **Placeholder scan:** every step has real code + exact commands. The only conditional note is the endpoint test's admin header (depends on the active security profile) — flag to the implementer.
3. **Type consistency:** `parse_course_search(pb) -> list[dict]` (keys `global_id/name/holes/city/province`); `CourseMatch(global_id, name, holes, city, province, ratio)`; `courseview_search(name, *, city, expected_holes, allow_fetch)`; `_fetch_search(query)`. Endpoint maps `holes` query → `expected_holes`. Referenced consistently.

## Notes for the implementer

- **CI is `unittest discover`, not pytest.** All tests are `unittest.TestCase` methods.
- **No live network in tests:** patch `_fetch_search` (decode/rank tests) or `course_search.courseview_search` (endpoint test). The Task-1 fixture-capture in Step 1 is the only network call, run once by you to create the committed fixture.
- The fixture `courseview_search_zhongshan.pb` is public course-list data (course names/cities/globalIds) — no PII; safe to commit.
- Real-data sanity (optional, not CI): `uv run python -c "from ai_caddie.course_search import courseview_search; print([(m.global_id,m.name) for m in courseview_search('zhongshan')])"` should list the Zhongshan nines (needs network to omt.garmin.cn).
