# Phase 5 Course Prep Productization - Design

- Date: 2026-06-06
- Branch: `integration/v2`
- Scope: Phase 5 in `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`.

## Background

Phase 5 outcome: the standalone `course_review/*.html` prototype becomes generated product UI/API data.

The repo already contains product pieces:

- `ai_caddie/mobile_live.py` builds round/course prep packages and route evidence seeds.
- `ai_caddie/geometry_evidence.py` builds hole map DTOs and route geometry evidence.
- `web_v2` has course prep and mobile package prep components/tests.
- iOS/Watch contracts already consume offline package concepts.

The remaining gap is to promote prototype-specific rendering and carry math into reusable engine/API
modules and product surfaces.

## Goals

1. Promote renderer, route, hazard, and carry calculations into tested engine modules.
2. Expose course-prep DTOs through backend APIs instead of standalone generated HTML.
3. Add or finish Web v2 course-prep page behavior with interactive hole maps.
4. Feed iOS/Watch package fields needed for offline pre-round prep.
5. Stop depending on `course_review/*.html` as the product surface.

## Non-Goals

- Do not delete the untracked `course_review/` prototype unless explicitly requested.
- Do not rebuild the whole web app layout.
- Do not require live Garmin network calls during course-prep UI tests.
- Do not hand-roll a separate geometry model when existing `geometry_evidence` DTOs can be reused.
- Do not make unsupported AI claims in prep output.

## Product Contract

Course prep output must be structured data first:

- course and nine identifiers
- hole number, par, handicap when available
- route length and route local coordinates
- hazards and clearances
- candidate routes and carry targets
- missing-data rows
- source references
- offline package metadata

The HTML/UI consumes DTOs. It does not own scoring, hazard math, route math, or source/provenance rules.

## Backend Architecture

Keep calculations in Python engine modules:

- `ai_caddie/geometry_evidence.py` for map and route evidence
- `ai_caddie/mobile_live.py` for package assembly
- a new focused module only if route/carry math needs separation

Backend APIs should use existing `/api/v2/mobile/.../package` and course package paths where possible.
If a dedicated course-prep endpoint is added, it should return source-bound DTOs and no raw private files.

## Web Architecture

Web v2 should show the actual usable prep experience:

- course/nine selection or loaded course context
- hole list
- interactive or inspectable hole map
- route/hazard/carry readouts
- missing-data state
- source evidence links when available

Frontend tests should cover DTO rendering and route-yardage math. Visual or Playwright smoke is required
before claiming a visual course-prep release.

## iOS And Watch Contract

The mobile package must include enough fields for offline use:

- selected course/nine/hole ids
- par and yardage metadata
- route candidates
- selected safe/stock/attack option seeds
- missing-data rows
- expiration/prepared-at timestamps

Watch summaries should be compact and deterministic: par, carry target, avoid zone, and selected route
confidence.

## Error Handling

- Missing geometry produces degraded map/prep state, not a crash.
- Missing par shows source-labeled missing data.
- Missing weather or history remains explicit in `missingData`.
- Unsupported route evidence does not produce confident recommendations.

## Testing

Add or extend:

- Python tests for route/hazard/carry DTOs.
- Server API tests for course-prep package response shape and missing-data degradation.
- Web unit tests for course-prep rendering and route readouts.
- Playwright visual smoke only after Web UI changes.
- Mobile contract tests for offline package fields.

Verification command for a backend-only slice:

```bash
uv run python -m unittest tests.test_mobile_contracts tests.test_server_v2_geometry tests.test_geometry_evidence -v
git diff --check
```

Verification command for a Web slice:

```bash
cd web_v2 && npm test -- --run && npm run lint && npm run build
```

## Acceptance Criteria

- Pre-round prep is browsable in `web_v2`.
- The backend serves structured course-prep DTOs with source and missing-data evidence.
- iOS/Watch package fields are contract-tested.
- Standalone `course_review/*.html` is no longer required for product use.
