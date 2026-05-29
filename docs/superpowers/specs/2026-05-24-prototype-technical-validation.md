# AI Caddie Prototype Technical Validation

Date: 2026-05-24

## Purpose

This document freezes the current repo as a technical validation record. The
existing one-file Web app and scripts proved that the private Garmin data and
course geometry can support an AI Caddie product, but they should not define the
final v2 application architecture or UI.

The v2 rebuild should reuse the validated engine capabilities and data
knowledge, while treating the current UI as a prototype.

## What The Prototype Proved

### Garmin CN Data Access

Validated:

- Garmin CN golf endpoints use `https://connect.garmin.cn/golf-api/...`.
- Golf endpoints require browser cookie plus `connect-csrf-token`, not the
  international Garmin OAuth/Bearer path.
- Scorecard summary, scorecard detail, and shot-by-shot files can be fetched
  locally and incrementally.
- Private authentication material can stay local under `.garmin_tokens/`.

Keep:

- `garmin_auth.py`
- `fetch.py`
- Garmin CN endpoint knowledge in `README.md`

Do not carry forward:

- UI flows that expose raw auth mechanics to the product surface.
- Any architecture that assumes a public hosted backend can read private Garmin
  tokens.

### Data Normalization

Validated:

- Garmin scorecards can be normalized into round, hole, par, stroke, FIR, GIR,
  putt, and penalty-like facts where available.
- Shot files can be normalized into WGS84 start/end points and club labels.
- Same-day 9-hole rounds can be merged into a useful 18-hole history object.
- Course names require canonicalization because 9-hole combinations and local
  naming vary.

Keep:

- `ai_caddie/data.py`
- `ai_caddie/history.py` aggregation logic, after refactoring into smaller
  v2-friendly units.

Improve:

- Define stable v2 data contracts before exposing API responses.
- Keep raw Garmin fields behind adapters rather than leaking them into the
  frontend.
- Add explicit availability/confidence states for every statistic.

### History Aggregation

Validated:

- History Review can compute round timeline, merged rounds, scorecards, monthly
  and quarterly trends, score distribution, course aggregation, club profiles,
  shot table, hole history, AI report archive, and data quality.
- History Review is not a secondary dashboard. It is one of the core product
  pillars.
- The current private dataset is rich enough for long-term review when present:
  hundreds of rounds, tens of thousands of shots, many unique courses, and
  partial prodgeometry coverage.

Keep:

- The idea of a shared history service.
- The aggregation semantics already validated in tests.

Rebuild:

- API response shape.
- Frontend presentation.
- Navigation and information architecture.

### Course Geometry

Validated:

- Garmin CourseView IMG is useful for coarse course knowledge, but the best
  short-term fine geometry source is Garmin Golf `prodgeometry`.
- Encrypted prodgeometry zip files can be downloaded, decrypted, extracted, and
  decoded into Draco meshes.
- Meshes such as fairway, green, bunker, water, rough, teebox, and tree area can
  be converted into local geometry and hazard indexes.
- Garmin shot coordinates can align to prodgeometry local coordinates closely
  enough for shot-to-surface and shot-to-hazard classification.

Keep:

- `fetch_courseview_geometry_key.js`
- `decode_courseview_geometry.js`
- `batch_prodgeometry_course.py`
- `export_prodgeometry_hazards.py`
- `ai_caddie/geometry_sync.py`
- `ai_caddie/analysis.py` geometry primitives, after cleanup.

Improve:

- Make geometry coverage a first-class API concept.
- Avoid making the frontend know which raw files exist.
- Separate online sync, local cache, and analysis-time read paths.

### Hole And Shot Analysis

Validated:

- A hole analysis can combine normalized Garmin data, shot paths, prodgeometry,
  route candidates, risk zones, and club profiles.
- Hole overlays can be generated from SVG, Esri satellite coordinates, Garmin
  raster references, and prodgeometry.
- The product can explain surfaces, near risks, carry distances, and strategy
  distances from real local geometry.

Keep:

- `ai_caddie/analysis.py` as the seed for an engine module.
- The geometry hit-test and route-candidate concepts.

Improve:

- Split analysis into smaller modules: geometry loading, shot enrichment, route
  generation, overlay DTOs, and data-quality checks.
- Keep map rendering and UI state out of the analysis engine.

### Decision Layer

Validated:

- A deterministic tee-shot decision object can be generated without an LLM.
- The decision can expose candidate options, selected option, recommended clubs,
  forbidden zones, evidence, confidence, and post-shot outcome judgment.
- Synthetic tests can cover strategy/execution/info-gap classification without
  private Garmin fixtures.

Keep:

- `ai_caddie/decision.py`
- `tests/test_decision_layer.py`
- The product principle that caddie advice must be falsifiable after the round.

Improve:

- Version the decision contract under `/api/v2`.
- Extend from tee-shot only to approach and recovery later, after the v2
  history/round/hole foundations are stable.

### Current Web MVP

Validated:

- A local browser UI is useful for rapid private data inspection.
- One-file Python server plus inline HTML/JS is fast for proving APIs and
  interactions.
- The current app helped validate history, overlay, manual round, and decision
  concepts.

Freeze:

- `ai_caddie_web.py` should remain a legacy/prototype entry unless a narrowly
  scoped debug capability needs it.

Do not continue:

- Styling the old UI into the final product.
- Adding v2 navigation into the old inline JavaScript.
- Treating the old component layout as a design constraint.

## Reuse Map

| Area | Current Files | v2 Treatment |
|---|---|---|
| Garmin fetch/auth | `garmin_auth.py`, `fetch.py` | Keep as local data ingestion tools |
| Raw data adapters | `ai_caddie/data.py` | Reuse, then split by responsibility |
| History engine | `ai_caddie/history.py` | Reuse algorithms, define v2 DTOs |
| Hole analysis | `ai_caddie/analysis.py` | Reuse geometry math, split modules |
| Geometry sync | `ai_caddie/geometry_sync.py`, JS decode scripts | Keep as local/cache workflow |
| Decision layer | `ai_caddie/decision.py` | Keep and version as API contract |
| Old Web app | `ai_caddie_web.py` | Freeze as prototype/debug surface |
| Static dashboards | `build_dashboard.py`, output scripts | Reference only |
| Visual companion | `visual_companion/history_review_v2.html` | Use for visual direction, not code |

## v2 Direction

The next product implementation should start from this boundary:

```text
ai_caddie/          core Python engine and local data access
server_v2/          FastAPI API layer and versioned contracts
web_v2/             React + Vite + TypeScript frontend
ai_caddie_web.py    frozen prototype/debug app
```

The engine remains Python because the hard parts are data normalization,
geometry, statistics, and deterministic analysis. Python already has the repo's
working implementation and test surface. TypeScript should own the frontend and
interaction model, not the golf engine.

## Non-Negotiable Lessons

- History Review and statistics must be first-class. They are not just support
  pages for live caddie decisions.
- Data quality must be visible wherever a recommendation or statistic appears.
- Course/hole geometry is the product's differentiator and should be presented
  as evidence, not hidden as an implementation detail.
- The product should combine Garmin's clean personal-data display with
  GolfLive's history breadth, then go beyond both with explainable decisions.
- v2 should be designed for future mobile and Apple Watch surfaces, but Web is
  the first implementation target.
