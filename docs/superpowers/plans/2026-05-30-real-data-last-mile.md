# Real-Data Last Mile — Finish AI Caddie v2

Date: 2026-05-30
Branch convention: per task → isolated `superpowers/**` worktree → PR → `integration/v2`.

> **Scope discipline:** This is **finish the last mile**, NOT rebuild. The skeleton
> is built and CI-green (all 12 master plans implemented). Do not re-spec pillars or
> re-run product brainstorming — the design lives in
> `docs/superpowers/specs/2026-05-24-ai-caddie-v2-product-design.md` and the master
> spec. This plan only closes the gap between "Claude did it by hand" and "the system
> does it automatically, on the user's real data."

> **Operating assumption (settled, not a question):** Private, **single-user**.
> "服务/service" here = *a pipeline that runs itself for the user* (scheduled +
> on-demand), **not** multi-tenant SaaS. No cloud multi-user hosting, no auth
> redesign — both are explicit v2 MVP non-goals. State once, proceed.

---

## Goal

Make AI Caddie v2 run on the user's **real Garmin history (~460 rounds / ~90 courses
+ shot traces + course geometry)** through an **automated ingestion pipeline**, and
fold the hand-built pre-round course-review prototype into the product — so nothing on
the critical path requires Claude-in-the-loop.

## Grounding evidence (verified this session, not from memory)

- `server_v2` boots and serves the v2 contract (`/api/v2/health`, `/history/overview`,
  …) — **but on 3 fixture rounds**. `totalRounds = 3`.
- **Real history is not landed anywhere:** `data/scorecards` and `data/shots` do not
  exist; only `data/courseview/prodgeometry/` (geometry) is cached. The course-review's
  authoritative `holePars` were fetched ad-hoc into `output/`, not the canonical data dir.
- Garmin web cookie + csrf are **fresh (2026-05-30)** → fetching is possible right now.
- Engine modules, `server_v2` endpoints, `web_v2`, `mobile/ios`, Watch all exist; the
  AI layer is already abstracted behind `ai_caddie/llm_providers.py` with a static stub.

**Conclusion:** the spine is *land real data → harden engine on real shapes*, with two
"by-hand" gaps to productize (auth refresh; par/course-ref ingestion), then fold in the
prototype. The engine has never seen messy real data (dedup, 9-hole merges, partial
shots/putts, missing geometry, odd course names) — expect breakage there, not in the API.

## How it generates "as a service" (the architecture answer, encoded)

```
[ cron schedule  OR  manual trigger ]
        │
        ▼
 1. auth-refresh        Playwright headless login → web cookie + csrf      [AUTO · cron · AI: none]
        │               (self-heals on 401; creds in .garmin_tokens, never logged)
        ▼
 2. fetch history       golf-api → data/scorecards/*.json, data/shots/*    [AUTO · AI: none]
        │
        ▼
 3. geometry-sync       CourseView search → release → prodgeometry decode  [ON-DEMAND per course · AI: none]
        │               (already wired: /geometry/hole/.../ensure)
        ▼
 4. course-ref ingest   par/yardage/meta, source-labeled, cached forever:  [ONE-TIME per course · cacheable · AI: NONE]
        │                 played holePars  >  scraped official            (name → fuzzy-match → fixed-selector
        │                 >  deterministic length-estimate                  HTML parse; pure Python, proven)
        ▼
 5. engine facts        history / round / course+hole / clubs / data-qual  [DETERMINISTIC Python]
        │
        ▼
 6. caddie decision     safe/stock/attack, carry, avoid-zones, confidence  [DETERMINISTIC · auditable]
        │
        ▼
 7. fact-bound prose    natural-language review of (5)+(6)'s facts         [LLM via llm_providers · OPTIONAL]
        │               (never invents numbers; static stub in tests)
        ▼
 8. surfaces            /api/v2/* → web_v2 / mobile / watch                [DETERMINISTIC]
```

**AI touches exactly ONE step (7, the prose), and even that is optional and fact-bound.**
Step 4 (par/course-ref) is **fully deterministic** — name → fuzzy-match → fixed-selector
HTML parse, proven this session (see Phase 3). Everything else is plain Python that already
exists. This is the literal answer to "做成服务该怎么生成 / 还需要 AI 提供东西吗": **no AI
for the data** — the decision is computed and auditable; AI only optionally writes prose
from already-computed facts.

---

## Phase 1 — Land & validate real history *(THE SPINE; blocks everything)*

Dependency: none (cookie is fresh). Automation: this becomes step 2 of the pipeline.

Files: `fetch.py` (entrypoints `fetch`/`main` exist), `ai_caddie/data.py`,
`ai_caddie/history*.py`, `tests/` (new real-shape regression fixtures, sanitized).

- [ ] Fetch real scorecards + shots into `data/scorecards/` + `data/shots/` via the
      connector (`uv run python fetch.py --shots`); record counts (expect ~418 deduped
      rounds, ~90 courses, N shot files).
- [ ] Boot `AI_CADDIE_DATA_MODE=local uv run uvicorn server_v2.main:app` and probe with
      real data: `/history/overview`, `/history/rounds`, one `/rounds/{id}`, one
      `/courses/{key}`, one `/holes/{gid}/{local}`, `/clubs`, `/data-quality`.
- [ ] Capture every break/wrong-value into a checklist (real-data failure modes:
      same-day 9-hole merge, partial/missing shots & putts, missing geometry, duplicate
      rounds, non-ASCII course names, tee/par gaps).
- [ ] Harden the engine against those shapes (parse/aggregate fixes only — **no
      re-spec**). Add a sanitized real-shape regression fixture per fixed bug.
- [ ] Done when: `totalRounds` reflects the real count and overview/round/course/hole/
      clubs render correctly end-to-end on local real data.

## Phase 2 — Productize auth-refresh *(Gap #1: "Claude ran Playwright by hand")*

Dependency: Phase 1 (proves fetch works). Automation: this becomes step 1 (scheduled).

Files: new `ai_caddie/connectors/garmin_cn_login.py` (productize the /tmp Playwright
script), `ai_caddie/connectors/garmin_cn.py`, `tests/test_garmin_cn_login.py`.

- [ ] Move the headless Playwright CAS login into `connectors/`, secret-free
      (creds from `.garmin_tokens/garmin_login.json`; never print/commit cookie/csrf/pw).
- [ ] Self-heal seam: on golf-api 401 → re-login → rewrite `web_cookie.txt`/`csrf.txt`
      → retry once. Surface a clean "auth expired, refreshing" status, not a stack trace.
- [ ] A `--refresh-auth` / cron-style trigger that refreshes proactively.
- [ ] Tests with a mocked browser seam (no live login in CI); redaction asserted.
- [ ] Done when: an expired cookie auto-refreshes headlessly with no manual step.

## Phase 3 — Course-reference ingestion *(Gap #2: a deterministic scraper, NOT AI)*

Dependency: Phase 1. Automation: this becomes step 4 (per-course, cached forever).
**No AI** — par lookup is name → fuzzy-match → fixed-selector HTML parse. Proven below.

Files: new `ai_caddie/course_reference.py` (the 3-step pipeline + `data/courses/<gid>.json`
store), new `ai_caddie/scrapers/golfpass.py`, integrate with `ai_caddie/geometry_evidence.py`
and `server_v2/geometry.py`, `tests/` (parser fixtures from saved HTML).

The pipeline = the user's three steps, all plain Python:

1. **Get the name** — from the played scorecard `courseName` / the CourseView course object
   already fetched for the globalId. No new source needed.
2. **Fuzzy-match to a course page** — query the course DB by name, rank candidates with
   `rapidfuzz` against the Garmin name + city, guard by hole-count, pick the best (or log a
   low-confidence miss and fall back). This is the "模糊查询" step.
3. **Fetch & parse par** — GET the course page, parse the **server-rendered** scorecard with
   fixed CSS selectors. GolfPass renders `CourseScorecardsItem-hole1..9` / `-out` / `-in` /
   `-total`; the par row is the hole-row whose nine values are all 3–5 and sum ≈36 (yardage
   rows are large; the stroke-index row sums to 81). Store per-hole par + per-tee yardages +
   handicap index.

- [ ] **Proven (this session):** a 6-line regex over live GolfPass HTML extracted Mountain
      par `[4,5,3,4,4,4,5,3,4]=36`, all four tee-yardage rows, and the stroke index — zero
      AI. Productize into `scrapers/golfpass.py` (`requests` + fixed-selector parse, e.g.
      `selectolax`/`bs4`); auto-pick the par row by the 3–5/sum≈36 rule.
- [ ] Resolver priority ladder: played `holePars` (authoritative) → scraped official →
      deterministic length-estimate (validated 18/18) as the only fallback. Each result
      carries `par_source` ∈ {`played`,`official`,`estimate`} + provenance URL + confidence.
- [ ] Nail the name→course path: GolfPass per-province `course-directory` listing (fetch
      once, fuzzy-match) or a search-results parse — guarded by hole-count + city; the two
      naive `?q=` guesses 404'd, so this is real (small) work, not assumed.
- [ ] Persist to `data/courses/<gid>.json`; seed-migrate 银杏湖 + 钟山 (already resolved).
      Cache permanently; never re-scrape a resolved course.
- [ ] Parser/fuzzy tests run against **saved HTML fixtures** — no live network in CI.
- [ ] Done when: `resolve_course_par(globalId)` returns labeled par fully automatically (no
      AI, no manual lookup) and played courses auto-upgrade to authoritative.

### Risk to call out on this phase
The genuinely hard bit is **step 2 matching the wrong course** (similar names; English-DB
name vs Garmin's `…~ A Mountain`; or the DB simply not carrying a small Chinese course).
Mitigation is in the tasks: hole-count + city guard, low-confidence logging (never silent),
and the deterministic length-estimate as a guaranteed fallback so the product never blocks.

## Phase 4 — Fold the course-review prototype into `web_v2` *(later, not the spine)*

Dependency: Phases 1 & 3. Automation: served from the engine, not a static file.

Files: promote `/tmp/render_hole.py` + `/tmp/gen_review.py` logic into
`ai_caddie/` (geometry render + route/hazard/strategy already partly in
`geometry_evidence.py`, `decision.py`), `server_v2` (`/geometry/hole/.../map` exists),
`web_v2/src/` (new pre-round prep + interactive hole-map component).

- [ ] Move the route-driven strategy + styled geometry render + hazard-carry math from
      /tmp into engine modules with tests (corridor clip, mirror fix, par-3 ball default,
      yards display — all the gotchas recorded in `[[garmin-auth-reality]]`).
- [ ] React interactive hole map (draggable ball, club chips, live yardage) as a
      `web_v2` component fed by the geometry/decision API.
- [ ] Pre-round course-prep view in the Caddie/Course pillar (per-hole par + strategy +
      map), offline-capable, replacing the standalone `course_review/*.html`.
- [ ] Done when: pre-round prep is a product page in `web_v2`, generated from the API.

## Phase 5 — End-to-end pipeline + data-quality + hardening

Dependency: Phases 1–3. Automation: wire steps 1–4 into one runnable pipeline.

Files: a pipeline entrypoint (cron-style) tying refresh→fetch→geometry→course-ref;
`ai_caddie/` data-quality, `server_v2/readiness.py`, private-trial hardening.

- [ ] Single command/cron that runs auth-refresh → fetch → geometry-sync (for played
      courses) → course-ref ingest, idempotently.
- [ ] Data-quality chips reflect **real** coverage (missing shots/putts/geometry, weak
      club samples) per the spec's "Data Quality Is Product UI" principle.
- [ ] `readiness` reports the pipeline freshness (last sync, cookie age, coverage).
- [ ] Run `web_v2` against the full real dataset; fix empty/partial states.
- [ ] Done when: the user can trigger one command and the whole product reflects current
      real data, with confidence/coverage visible.

---

## Risks / unknowns

- **Real-data shape surprises (highest):** 460 messy rounds vs 3 clean fixtures — Phase 1
  is where the real work hides; budget for engine hardening, not just wiring.
- **Fetch volume/time:** ~460 rounds + shots may be slow / rate-limited; may need
  incremental/resumable fetch.
- **Web-lookup fragility:** Chinese course sites block/cert-fail; English DBs (GolfPass/
  18Birdies) work but are inconsistent — keep the deterministic estimate as the contract,
  web-lookup as best-effort enrichment.
- **Geometry coverage:** not every played course has prodgeometry; the UI must degrade.

## Sequencing summary

`Phase 1 (spine)` → then `2` and `3` in parallel (both depend only on 1) → `5` (pipeline
glue, needs 1–3) → `4` (UI fold-in, can trail). Each phase ships as its own PR into
`integration/v2`.
