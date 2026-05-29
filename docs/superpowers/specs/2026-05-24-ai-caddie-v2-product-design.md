# AI Caddie v2 Product And Architecture Design

Date: 2026-05-24

## Goal

Rebuild AI Caddie as a coherent private golf intelligence product, not as an
incremental skin over the prototype Web UI.

v2 should help the user answer four recurring questions:

1. How has my golf changed over time?
2. Why did a specific round or hole go well or badly?
3. What do my course, hole, and club histories say I should do next time?
4. How confident is the system, and what data is missing?

## Source Inputs

- `COMPETITOR_RESEARCH.md`
- `HISTORY_REVIEW_RESEARCH_SUMMARY.md`
- `docs/superpowers/specs/2026-05-24-history-review-v2-ui-design.md`
- `visual_companion/history_review_v2.html`
- `docs/superpowers/specs/2026-05-23-ai-caddie-decision-layer-design.md`
- `docs/superpowers/specs/2026-05-24-prototype-technical-validation.md`
- Existing engine modules under `ai_caddie/`

## Product Position

AI Caddie v2 is a private personal caddie and history-review system built on
Garmin golf data, Garmin shot traces, course geometry, and deterministic
analysis.

It should not become:

- a generic Garmin dashboard clone
- a GolfLive social/tournament clone
- a public booking/course-commerce product
- a swing-video AI product
- a social feed

The product advantage is the connection between long-term personal history and
course-aware decisions.

## Core Product Principles

### 1. History Is A First-Class Product

History Review is not a reporting appendix. It is the main memory surface:

- round timeline
- annual/quarterly/monthly summary
- score distribution
- course map
- course review
- hole review
- club model
- data quality

Garmin is strong at clean personal round display. GolfLive is strong at broad
history navigation and long-term summaries. v2 should combine both, then add
shot geometry and explanation.

### 2. Every Recommendation Must Be Auditable

A caddie decision should state:

- selected plan
- viable alternatives
- target carry or landing window
- recommended clubs
- avoid zones
- evidence used
- confidence
- what happened after the round, when actual shot data exists

Advice that cannot later be judged should be labeled as low confidence or not
shown.

### 3. Data Quality Is Product UI

Missing shots, missing putts, missing geometry, weak club samples, and missing
reports are not backend details. They must appear as chips, badges, and warning
states next to the affected statistic or decision.

### 4. Geometry Is Evidence

Course geometry should be part of the explanation:

- hazards near the intended line
- actual finish surface
- repeated miss zones
- common route vs recommended route
- carry/clear distances

The final fairway map should use real Esri/Garmin/prodgeometry data. Abstract
fairway drawings are acceptable only in visual companions or loading/empty
states.

### 5. Beautiful Means Quiet, Dense, And Golf-Native

The chosen visual direction is Garmin Pro:

- precise
- calm
- information-dense
- strong score strips and maps
- restrained panels
- visible data confidence

Avoid:

- mini-program module clutter
- marketing landing-page composition
- large decorative gradients
- one-note purple/blue, beige, or dark-slate themes
- rebuilding the old prototype UI layout

## Product Pillars

### 1. History Review

Primary question:

- What is the story of my golf over time?

P0 capabilities:

- overview metrics: total rounds, 18H average, recent 10 average, best score,
  courses played, shot count
- recent round cards with score strip
- data coverage chips: shots, putts, geometry, AI reports
- annual, quarterly, and monthly summaries
- score distribution pyramid and histogram
- timeline grouped by month
- course map

P1 capabilities:

- play frequency
- tags and favorites
- exportable review summaries

### 2. Round Review

Primary question:

- Why did this round produce this score?

P0 capabilities:

- Garmin-style scorecard-first round header
- hole-by-hole score strip
- expanded scorecard rows with FIR, GIR, putts, penalties when available
- high-cost hole list
- issue tags: tee miss, approach miss, penalty, three-putt, bunker, water,
  recovery, missing shots
- shot route map when shots exist
- structured AI review generated from facts, not raw hallucination
- round data quality

P1 capabilities:

- share/export image
- round-to-round comparison
- personal/course expectation model

### 3. Course And Hole Review

Primary question:

- What usually happens to me on this course and this hole?

P0 capabilities:

- course list and map
- rounds, average, best/worst, recent form by course
- hole ranking by scoring cost
- `globalId + localHole` aggregation
- hole score distribution
- repeated shot patterns
- overlay with route and hazards when geometry exists
- caddie route suggestion only when confidence is enough

P1 capabilities:

- tee-box comparison
- repeated hazard-miss trend
- recommended practice or course-management note per hole

### 4. Club Model

Primary question:

- Which club distances can I trust?

P0/P1 boundary:

- Basic club model can appear in v2 early because the Decision Layer needs it.
- Full club page can be P1 after History Overview and Round Review.

Capabilities:

- valid shot count
- median distance
- p10/p90
- max distance, clearly de-emphasized
- sample confidence
- shot drill-down
- optional left/right and short/long miss pattern

### 5. Caddie Decision

Primary question:

- What should I do here, and why?

P0 capabilities:

- tee-shot decision card
- safe/stock/attack options
- selected option
- carry and recommended clubs
- forbidden zones
- evidence
- confidence
- outcome audit when actual data exists

P1 capabilities:

- approach decision
- recovery decision
- round-level strategy summary
- model update suggestions after repeated outcomes

### 6. Data Quality

Primary question:

- Can I trust this statistic or recommendation?

P0 capabilities:

- global data health summary
- per-round coverage
- per-course geometry coverage
- per-hole confidence
- club sample warnings
- report availability

## Information Architecture

Primary navigation for Web v2:

```text
Overview
History
Rounds
Courses
Clubs
Caddie
Data Quality
```

Recommended first-screen experience:

- land on `Overview`, not a marketing page
- show history metrics, recent rounds, score trend, data quality, and entry
  points into round/course/hole review
- keep maps and score strips as the visual identity

Page roles:

| Page | Role | First Release Depth |
|---|---|---|
| Overview | Main memory and health dashboard | P0 |
| History | Timeline, annual/quarterly summary, distribution | P0 |
| Rounds | Round list and individual round review | P0 |
| Courses | Course list/map and course detail | P0 |
| Clubs | Distance model and confidence | P1, with summary in P0 |
| Caddie | Current hole/decision workspace | P0/P1 depending data |
| Data Quality | Coverage and missing-data action list | P0 |

## Visual System

### Base Direction

Use Garmin Pro:

- warm gray-white page background
- white panels with subtle borders
- dark green-black text
- gray-green secondary text
- 8px or smaller border radius for cards/panels
- score strips, maps, and compact charts as primary visual texture
- no ornamental orb/blob backgrounds

### Color Semantics

Scoring:

- eagle or better: deep blue
- birdie: light blue
- par: green
- bogey: amber
- double+ or worse: red

Course features:

- fairway: medium green
- green: brighter green
- rough/tree: muted olive
- bunker: sand gold
- water: blue
- risk/penalty: red
- unknown/missing data: neutral gray

Confidence:

- good: green
- partial: amber
- missing/low confidence: red or gray depending severity

### Core Components

- round card
- score strip
- data quality chip
- score distribution pyramid
- annual/quarterly summary card
- course map marker
- hole review overlay
- decision card
- club confidence row

Component requirements:

- score strip cells have stable dimensions
- round cards use compact hierarchy, not oversized hero typography
- charts and maps must remain readable on mobile widths
- text must not overflow buttons, chips, or tiles
- maps should use real data when available and explicit empty states otherwise

## Cross-Platform Roles

### Web v2

Primary build target.

Best for:

- full history review
- rich stats
- course/hole overlays
- data quality
- debugging local data and geometry
- planning before or after a round

### Mobile App

Future, not first.

Best for:

- same product language in a smaller shell
- quick round lookup
- current course/hole context
- scorecard and route review

Build only after Web v2 stabilizes the information architecture and contracts.

### Apple Watch

Future companion, not a full app.

Best for:

- current-hole decision card
- club/carry target
- avoid zones
- confidence indicator
- maybe one-tap post-shot outcome annotation

Do not put full History Review or complex maps on Watch.

## Backend Architecture

### Decision

Keep the backend/engine in Python.

Reason:

- the current data ingestion, geometry, statistics, and decision work already
  exists in Python
- Python is stronger for data analysis and geometry experimentation
- deterministic tests are already in place
- the product is private/local first, so Python deployment complexity is
  acceptable

Alternatives considered:

- TypeScript/Node: useful for a unified frontend/backend language, but weaker
  fit for existing data/geometry work and would require rewriting validated
  engine logic.
- Go: strong for a packaged server, but slower for data-science iteration and
  geometry experiments.
- Swift/iOS-first: attractive if Watch/mobile were primary, but premature
  before the product model and API contracts stabilize.

### Target Layout

```text
ai_caddie/          core engine: data, history, analysis, decision, geometry
server_v2/          FastAPI API layer, DTOs, error mapping
web_v2/             React + Vite + TypeScript frontend
ai_caddie_web.py    frozen prototype/debug app
```

### Engine Boundary

`ai_caddie/` should expose product facts, not HTML:

- history overview data
- round summaries
- round detail facts
- course summaries
- hole history facts
- club profiles
- data quality states
- decision plans and outcomes

The engine may read local files, decode geometry, and run deterministic
analysis. It should not know about React components or browser state.

### API Boundary

`server_v2/` should:

- expose versioned JSON endpoints under `/api/v2`
- convert engine facts into stable API contracts
- keep private path/token details out of responses
- support empty/private-data-missing states cleanly
- provide testable schemas
- avoid business logic that belongs in `ai_caddie/`

Initial endpoints:

```text
GET /api/v2/health
GET /api/v2/history/overview
GET /api/v2/history/rounds
GET /api/v2/history/distribution
GET /api/v2/rounds/{round_id}
GET /api/v2/courses
GET /api/v2/courses/{course_key}
GET /api/v2/holes/{global_id}/{local_hole}
GET /api/v2/clubs
GET /api/v2/data-quality
```

Later endpoints:

```text
POST /api/v2/sync/garmin
POST /api/v2/geometry/sync
GET /api/v2/caddie/decision
POST /api/v2/reports/round/{round_id}
```

### Frontend Boundary

`web_v2/` should:

- own visual system and layout
- use typed API clients
- render empty and partial data states
- keep maps and charts as reusable components
- never parse raw Garmin JSON directly

Recommended stack:

- React
- Vite
- TypeScript
- CSS modules or a small local CSS token system
- Vitest for frontend logic tests
- Playwright for smoke/screenshot checks when UI becomes substantial

## Data Contracts

### Common Types

Data quality state:

```json
{
  "state": "good | partial | missing",
  "label": "shots",
  "value": "92%",
  "reason": "448 scorecards, 412 usable shot files"
}
```

Score strip cell:

```json
{
  "hole": 1,
  "par": 4,
  "score": 5,
  "toPar": 1,
  "class": "bogey"
}
```

Round card:

```json
{
  "id": 17368475,
  "date": "2026-05-17",
  "courseName": "Example Course",
  "courseKey": "c_123",
  "holesCompleted": 18,
  "score": 86,
  "toPar": 14,
  "scoreStrip": [],
  "badges": [],
  "primaryIssue": "tee_miss"
}
```

History overview:

```json
{
  "schema": "ai-caddie-history-overview-v2",
  "metrics": {},
  "recentRounds": [],
  "recentTrend": [],
  "distribution": {},
  "dataQuality": [],
  "emptyState": null
}
```

## MVP Scope

First vertical slice:

1. Keep existing engine modules.
2. Add `server_v2` FastAPI app.
3. Add `web_v2` React/Vite/TypeScript app.
4. Expose `/api/v2/health` and `/api/v2/history/overview`.
5. Render a Garmin Pro History Overview with empty-safe data.
6. Include score strips, recent rounds, score distribution summary, and data
   quality chips if data exists.
7. Keep old `ai_caddie_web.py` running only as prototype/debug.

Second slice:

1. History timeline.
2. Score distribution drill-down.
3. Annual/quarterly summary.
4. Round detail shell.

Third slice:

1. Course list/map.
2. Course detail.
3. Hole review overlay.
4. Decision card integration.

## Non-Goals For v2 MVP

- social comparison
- friends/team/tournament workflows
- booking or course commerce
- swing video AI
- native iOS app
- Apple Watch app
- full every-shot strategy
- cloud multi-user hosting
- large authentication redesign

## Migration Policy

- Do not delete old prototype code during the first v2 slice.
- Do not keep adding product UI to `ai_caddie_web.py`.
- Keep tests for validated engine behavior.
- Add v2 contract tests before frontend depends on an endpoint.
- Prefer adapters around existing engine functions over broad refactors in the
  first slice.
- Move functionality only when there is a test and a clean boundary.

## Success Criteria

v2 MVP succeeds when:

- the app can start from `web_v2` and `server_v2`, not `ai_caddie_web.py`
- empty/private-data-missing remote environments render cleanly
- real local data renders as a polished History Overview
- score strips and scoring colors match the selected Garmin Pro semantics
- every visible statistic has an availability/confidence signal
- `/api/v2/history/overview` has a stable schema covered by tests
- the old prototype remains available but is not the product path
