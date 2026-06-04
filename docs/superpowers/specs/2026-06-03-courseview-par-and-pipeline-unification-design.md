# Unplayed-Course Prep: Discovery + CourseView Par + Pipeline — Design (Theme B)

- Date: 2026-06-03
- Branch convention: per-task `superpowers/**` worktree → PR → `integration/v2`.
- Scope: the "real-data automation last-mile" gaps (Theme B) from the 2026-06-03 design-conformance
  review, reframed to the real goal — **end-to-end pre-round prep for a course the user has never
  played** — around two findings (both via the anonymous `omt.garmin.cn/CourseViewData` CDN): **Garmin
  serves exact per-hole par for any course**, and **course search (name→globalId) is an anonymous endpoint**.
  Two PRs, both buildable now, no auth needed: **#1** par + pipeline + cleanup, **#2** course search.

---

## Background & the discovery

The 2026-06-03 conformance review flagged three med gaps in the real-data-last-mile pillar:

- **B1** — the par ladder (`played → official → estimate`) only ever runs the `played` rung; the
  `official`/`estimate` rungs never fire in production (no caller supplies `golfpass_url`/`lengths_m`),
  so an **unplayed** course (a course the user is about to play for the first time — exactly the case
  pre-round prep exists for) gets no par.
- **B2** — no `name → GolfPass URL` auto-discovery; the plan itself flagged "matching the wrong course"
  as the hardest risk and framed web-lookup as best-effort.
- **B3** — two sync entrypoints each silently drop a step: the CLI `pipeline.sync()` does
  auth+fetch+course-ref but **not** geometry-sync; the server connector `sync()` does fetch+optional
  geometry but **not** course-ref.

**Discovery (verified by hand, 2026-06-03 — see memory `garmin-courseview-par`):** Garmin's CourseView
**release** protobuf carries **exact per-hole par + handicap index for any course, keyed by globalId,
with no play history required** — and this product **already fetches and caches that protobuf** for
geometry sync (`ai_caddie/geometry_sync.py` → `inspect_courseview_release.load_release_pb`, cached at
`data/courseview/{globalId}_releases.pb`, anonymous endpoint
`omt.garmin.cn/CourseViewData/course-layouts/{globalId}/releases/`).

Par lives at: top field **7** (repeated hole record) → sub-field **2** → nested field **1** (varint).
Handicap index at field **7** → sub **3** → field **1**. The earlier "Garmin has no par for unplayed
courses" conclusion was wrong — `inspect_release` decoded hole sub-fields 1/4/5/6/7/8 and **skipped 2/3**.

**Cross-validation (proof, not assertion):** a hand-rolled raw-protobuf walker decoded course **31870**
→ par `[5,4,3,4,4,4,5,3,4]` / hcap `[4,6,9,5,2,1,3,7,8]`, which **exactly matches** that nine's played
scorecard `holePars`/`holeHandicaps` (id 17409719). Course **31936** (钟山 ~ C Valley, **never played**)
→ par `[4,5,3,4,3,4,4,5,4]` (sum 36). So par is exact and reachable for unplayed courses.

**Consequence:** the risky GolfPass scrape path (B2) is **obsolete** — Garmin gives exact par by globalId,
all courses (incl. Chinese), zero wrong-course risk. B1 becomes "decode what we already fetch."

---

## Goals

**Primary goal — make pre-round prep work for a course the user has NEVER played, end to end:**
discover the course's globalId → resolve exact par → render prep (geometry already resolves on demand).
The "adjacent nine of a played club" case is not the point; a brand-new course is. Concretely:

1. **Discover a course by name/location → Garmin globalId** — the missing front door, now **SOLVED**: an
   anonymous CourseView search endpoint (`omt.garmin.cn/CourseViewData/courses?CourseName=`), deterministic,
   no auth. See "Course discovery" below.
2. **Par for any course, exact, Garmin-native** — add a `courseview` rung to the par ladder that decodes
   per-hole par (+ handicap) from the CourseView release protobuf by globalId. Given a globalId,
   unplayed-course prep returns exact par automatically.
3. **One idempotent command does all four steps** — auth-refresh → fetch → geometry-sync (missing-only,
   for played courses) → course-ref ingest. Neither the CLI nor the server entrypoint silently drops a step.
4. **Fix the hardcoded `par: 4`** in the mobile geometry-only course template.
5. **Delete GolfPass** — remove the now-dead scraper, its resolve_par branch, helpers, tests, and fixture.

**All five goals are buildable now — none needs fresh auth.** Shipped as two PRs for review cleanliness:
**PR #1** = Goals 2–5 (par + pipeline + cleanup); **PR #2** = Goal 1 (course search). See "Implementation phases".

## Non-goals

- iOS/web UI work (Themes A/D), interactive overlay, offline prep caching — separate.
- Real handicap/course-rating computation — we **surface** Garmin's stroke index, we don't compute a
  handicap.
- Pre-materializing Garmin's entire course DB. Played-course nines are materialized by the pipeline;
  unplayed courses resolve **on demand** when prep is requested.
- GolfPass, any third-party scrape, any AI on the data path.
- Building an **offline all-China course DB** / bulk-enumerating Garmin's whole course catalog. Discovery
  is an on-demand search per course the user is about to play, not a crawl.

## Course discovery — find an unplayed course's globalId (SOLVED, anonymous)

Discovery is a **deterministic, anonymous** CDN call — the same `omt.garmin.cn/CourseViewData` family as
par/geometry (found 2026-06-03 by reading the endpoint's own 400 error message). The Garmin **web** golf
app has no course search (it is entirely your-own-data; `/app/courses` is the cycling route creator) — that
was a dead end. The real endpoint:

**`GET https://omt.garmin.cn/CourseViewData/courses?CourseName=<query>`** — anonymous (no auth), returns a
**protobuf** list of matching course nines. Min query ≥3 ascii / ≥2 CJK chars; **CJK works** (`钟山` →
Zhongshan); `204` = no match. Each course record (top **field 4**, repeated) carries: **f7 = globalId,
f12 = name, f13 = holeCount (=9), f16 = province, f21 = city**, plus phone/postal/address/website and
f9/f10 raw lat/lon. (e.g. `钟山` → 31934 "A Mountain" / 31935 "B Lake" / 31936 "C Valley"; 31936's par
cross-checks the release-protobuf decode.)

- **`courseview_search(name, *, city=None, expected_holes=None) -> list[CourseMatch]`** — GET the endpoint,
  decode the protobuf (reuse the `inspect_courseview_release`-style varint walker), fuzzy-match the query
  against the course name (f12, stdlib `difflib`) **guarded by holeCount (f13) + city/province (f21/f16)**,
  and return ranked `CourseMatch{global_id, name, city, holes, ratio}` — weak matches logged, never
  silently accepted.
- Surface as **`GET /api/v2/courses/search?name=...&city=...`** → ranked matches; the chosen globalId flows
  into the existing `/courses/{global_id}/prep` (par + geometry). A record = one nine; an 18-hole course
  returns its A/B/C nines (e.g. Zhongshan 31934/31935/31936) for the user to pick the combo.
- **No auth, no browser, no app capture, no manual entry.** Deterministic and CI-testable offline.

**Fallback:** `204`/no-match (a course genuinely absent from Garmin's DB) → tell the user, allow manual
globalId entry; prep still works via the par+geometry path.

**Tests:** commit a captured search protobuf as a fixture (e.g. `courseview_search_zhongshan.pb`, public,
no private data); assert the protobuf decode (f7/f12/f13/f21) and the fuzzy-match + hole-count/city guard
offline (no live network in CI). Auth-refresh via Playwright/xvfb is **proven on this box** (2026-06-03,
fresh validated session) — useful for the played-data fetch pipeline (Goal 3), **not** needed for discovery.

## Implementation phases

- **PR #1 — par + pipeline + cleanup.** Goals 2–5: CourseView par decode + ladder, `build_played_store`
  extension, prep `resolve_par`, the single 4-step idempotent command, the `mobile_live` par:4 fix,
  GolfPass removal, and all CI fixtures/tests. Verifiable today against cached `data/` + committed fixtures.
- **PR #2 — course search.** Goal 1: `courseview_search` (decode the anonymous `CourseName` protobuf +
  fuzzy-match with holeCount/city guard) + `GET /api/v2/courses/search`. Also buildable now (anonymous, no
  auth); split out only for review cleanliness. Can land before or after PR #1.

Both are buildable now; each ships as its own `superpowers/**` worktree → PR → integration/v2.

---

## Architecture

### The par ladder (rewrite of `resolve_par`)

```
resolve_par(global_id, *, course_name=None, lengths_m=None, allow_fetch=True) -> CoursePar | None
  1. played      played_par_by_nine()[gid]      → source="played",     confidence="high"   (on disk, no decode)
  2. courseview  courseview_par(gid)            → source="courseview", confidence="high"   (Garmin release protobuf)
  3. estimate    [estimate_par_from_length(x)]  → source="estimate",   confidence="medium" (last resort only)
  4. None
  # allow_fetch=False keeps the courseview rung cache-only (no network) for request-time/offline paths
```

- `played` always wins (authoritative; the user's own card). `courseview` is the exact canonical course
  par for everything else. `estimate` only fires if a course has **no** CourseView release at all.
- `PAR_SOURCES` becomes `("played", "courseview", "estimate")`. The `golfpass_url`/`nine_name` params and
  the `official` source are **removed**.
- `lengths_m` stays as the optional estimate input (callers like prep can pass route lengths); when
  absent and a release exists, courseview supersedes it anyway.

### New unit: `courseview_par(global_id, *, allow_fetch=True) -> list[int] | None`

- **What:** returns the per-hole par list for a CourseView nine (or `None` if unavailable).
- **How:** loads the release protobuf (cache-first; fetch if absent and `allow_fetch`), decodes the par
  sub-field, returns `[hole.par for hole in release.holes]`.
- **Depends on:** `inspect_courseview_release.load_release_pb` + the extended `inspect_release`
  (below). No new network code — reuses the existing release fetch/cache used by geometry sync.
- Handicap/stroke index is decoded for free in the same pass. Surface it by persisting an optional
  `handicap: list[int] | None = None` field on the `CoursePar` record (decoded + stored, no consumer
  required by this spec). No separate handicap function is needed.

### Extend the release decoder

`inspect_courseview_release.inspect_release` (already imported by the engine via `geometry_sync`) gains
two per-hole fields in its sub-loop, additively (CLI behavior unchanged):

```python
elif sub_no == 2 and sub_wire == 2 and _sub_raw is not None:   # par
    hole["par"] = _nested_field1_varint(_sub_raw)
elif sub_no == 3 and sub_wire == 2 and _sub_raw is not None:   # stroke/handicap index
    hole["handicap"] = _nested_field1_varint(_sub_raw)
```

`_nested_field1_varint(raw)` parses field 1 (varint) out of the nested message. The existing loop
currently discards `_sub_raw`; it will now use it for sub-fields 2/3.

### Nine vs. 18-hole mapping (correctness-critical)

A CourseView `globalId` resolves to **one nine** (the release carries 9 hole records). The product
already models par per-nine keyed by front/back globalId (`aggregate_played_par`), so `courseview_par`
returns a 9-list per globalId and consumers index `local_hole` within it. An 18-hole round/prep uses two
globalIds (front + back), concatenated — identical to how played par already works. The plan must keep
this mapping exact (the 31870 cross-validation guards it).

### Store: extend `build_played_store()` in place (name unchanged)

The course-ref ingest step (`build_played_store`, name and callers unchanged) materializes
`data/courses/<gid>.json` for the **known played universe**:

1. Build played records (as today).
2. Collect every nine-globalId referenced by the synced scorecards (front + back gids).
3. For any referenced nine without a played record, `resolve_par(gid)` (→ courseview) and persist.

This fills par even for a played course's nine that lacked `holePars`. Unplayed prep courses are **not**
pre-materialized here; they resolve on demand via `resolve_par`/`courseview_par` when prep is requested.

### Consumer change: prep must resolve on demand

`course_prep.prep_nine` currently calls `load_course_par(global_id)` (read-only — returns `None` for an
unplayed course whose store file doesn't exist, so it would never trigger a courseview decode). Change
`prep_nine` to call `resolve_par(global_id)` (cache-first via `load_course_par`, then `courseview_par`
on miss) so **unplayed** prep courses get exact par on demand. `prep_hole`'s per-hole route-length
estimate stays as the final fallback when no par record/hole is available. `mobile_live` consumers get
par from the store / `courseview_par` the same way (see the geometry-only fix below).

### B3 — one idempotent 4-step command, no dropped steps

- **Canonical single command = CLI `ai_caddie/pipeline.py:sync()`.** It already does
  auth → fetch → course-ref. Add a **geometry-ensure-missing** step over the played courses' holes
  (idempotent: skips holes whose geometry is already `ready`; only downloads what's absent). The
  geometry-ensure logic is factored into a shared helper so it isn't duplicated.
- **Server `/sync/garmin` (connector `sync()`) must not drop course-ref.** After a successful
  fetch+snapshot, the connector calls `build_played_store()` (course-ref). Geometry-ensure stays
  available via its existing `ensure_geometry` path.
- Both entrypoints therefore run all four steps idempotently. Shared step helpers prevent drift.

### Fix: `mobile_live._geometry_only_course_template` (`mobile_live.py:1608`)

Replace the hardcoded `"par": 4` (line 1619) with par resolved from `courseview_par(global_id)` indexed
by `local_hole`, falling back to an estimate from geometry length, and only to a neutral default if a
course has neither a release nor geometry. Update
`test_server_v2_mobile.py::test_mobile_course_package_can_use_geometry_only_course_without_prior_round`
to assert real par (from a committed release fixture) instead of `4`.

### Delete GolfPass

- Delete `ai_caddie/scrapers/golfpass.py` (and the `scrapers/` package if it becomes empty — check
  `scrapers/__init__.py`).
- `course_reference.py`: remove the `golfpass` import, `official_par_from_golfpass`, `pick_course_link`,
  the `golfpass_url`/`nine_name` params, and the `official` branch + docstring lines.
- `tests/test_course_reference.py`: delete `GolfPassParserTests` and the `pick_course_link` tests;
  rewrite the `resolve_par` tests to exercise played → courseview → estimate against a release fixture.
- Delete `tests/fixtures/golfpass_zhongshan_mountain_lake.html`.

---

## Data flow

```
Garmin CN web session ─▶ fetch scorecards/shots ─▶ data/scorecards, data/shots   (played par via holePars)
                                                          │
CourseView release pb (anonymous, by globalId) ──────────┼─▶ decode par+hcap (field 7→sub2/3→f1)
   (already fetched/cached for geometry sync)             │
                                                          ▼
                                       resolve_par ladder: played ▶ courseview ▶ estimate
                                                          │
                                                          ▼
                                       data/courses/<gid>.json  (CoursePar: par, par_source, confidence, handicap?)
                                                          │
                          ┌───────────────────────────────┼────────────────────────────────┐
                          ▼                                ▼                                 ▼
                  course_prep (prep_hole)         mobile_live (package)            history/course stats
```

All deterministic Python; no AI; no third-party network.

## Error handling & degradation

- Release fetch fails / course absent from CourseView → fall to `estimate` (if lengths available) →
  else `None`. Prep already skips holes with no par/geometry; never crash.
- A release missing the par sub-field for some holes → return the holes that have it; caller degrades.
- Idempotent: re-running resolves identically; `played` always supersedes a prior `courseview`/`estimate`.
- `courseview_par(allow_fetch=False)` for request-time paths that must not block on network (serve from
  cache, let the pipeline warm it).

## Testing (CI = `unittest discover`, no network)

All tests are `unittest.TestCase` (per memory `ci-uses-unittest-not-pytest`); **no live network**.

- Commit real CourseView release protobufs as fixtures (public course-geometry index, no private data;
  ~a few KB each): `courseview_release_31936.pb` (unplayed course), plus `31870.pb` (front nine) and
  `31871.pb` (back nine) for the nine/18 mapping cross-validation.
- `test_courseview_par_decode`: decode 31936 → assert par `[4,5,3,4,3,4,4,5,4]` (sum 36) and hcap
  `[6,3,2,1,9,5,8,7,4]`.
- `test_courseview_nine_mapping` (guards the top risk): 31870 (front) par == a played scorecard's
  `holePars[:9]` = `[5,4,3,4,4,4,5,3,4]` **and** 31871 (back) par == `holePars[9:18]` =
  `[4,5,4,4,3,5,3,4,4]`. Both halves, so a silent front/back par-shift can't hide. (Both already verified
  by hand against `data/` on 2026-06-03; the fixture test locks it into CI.)
- `test_resolve_par_ladder`: played present → `played`; no played, release present → `courseview`;
  neither → `estimate` from `lengths_m`; nothing → `None`. (Patch the release loader to the fixture.)
- `test_geometry_only_template_uses_courseview_par`: the mobile geometry-only template yields real par,
  not 4 (patch release loader to fixture).
- Rewrite `test_course_reference.py` resolve_par tests; remove GolfPass tests.
- Verify locally: `uv run python -m unittest discover -s tests` and `py_compile` the touched files.
  (Real-data behavior — that 104 played nines still resolve and unplayed courses now get courseview par —
  is verified by symlinking `data/` and running the pipeline once; CI uses fixtures only.)

## Risks

- **Nine/18 globalId mapping** (highest): a release = one nine; an 18-hole round/prep concatenates two.
  Mis-mapping shifts par by a nine. Mitigated by the 31870 played-vs-release cross-validation test.
- **Release availability**: a few courses may lack a CourseView release → degrade to estimate/None.
- **`yardage_or_length` units (m vs yd)** only affect the rarely-used `estimate` fallback (par is exact
  from the release regardless). The plan should confirm units if it touches the estimate path.
- **Editing a root CLI script** (`inspect_courseview_release.py`, an engine dependency via geometry_sync):
  keep changes additive so its CLI output and geometry_sync's consumers are unaffected.
- **Course search (PR #2)**: relies on an undocumented CourseView protobuf shape (field numbers f7/f12/
  f13/f21) — pin it with a committed fixture test so a Garmin-side change fails loudly. Wrong-course match
  is mitigated by the holeCount + city/province guard (weak matches logged, never silent). A course absent
  from Garmin's DB returns `204` → surfaced as "not found", manual globalId entry still works.
