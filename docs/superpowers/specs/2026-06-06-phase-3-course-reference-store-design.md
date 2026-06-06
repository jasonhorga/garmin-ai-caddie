# Phase 3 Course Reference And Par Yardage Store - Design

- Date: 2026-06-06
- Branch: `integration/v2`
- Scope: Phase 3 in `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`.

## Background

Phase 3 outcome: every played or searched course gets source-labeled par and yardage metadata cached in
`data/courses/<gid>.json`.

The repo already has the core par ladder in `ai_caddie/course_reference.py`:

1. `played` from scorecard `holePars`
2. `courseview` from Garmin CourseView release protobuf
3. `estimate` from deterministic length thresholds

The remaining gap is product hardening: consistent persistence, provenance, coverage reporting, and
offline fixtures for any parser or lookup path that is not purely synthetic.

## Goals

1. Finish `resolve_course_par(globalId)` / `resolve_par(global_id)` behavior so played and searched
   course nines persist source, confidence, provenance, and optional yardage metadata.
2. Ensure every real played course reference that the product can identify produces a stored course
   reference or an explicit reason why it cannot.
3. Keep CourseView release par as the primary unplayed-course source.
4. Keep deterministic estimate fallback only for missing CourseView releases or incomplete geometry.
5. Add offline fixtures for any web/parser lookup path; CI must not call live third-party web pages.

## Non-Goals

- Do not reintroduce GolfPass as a required par source.
- Do not scrape live pages in CI.
- Do not bulk crawl Garmin's full course database.
- Do not hide provenance. Every persisted record must label source and confidence.
- Do not let estimated par silently override played or CourseView par.

## Data Model

`data/courses/<gid>.json` records should remain simple JSON objects that can be inspected by hand.
The minimum fields are:

- `global_id`
- `par`
- `par_source`
- `confidence`
- `provenance`
- `course_name`
- `handicap`

Phase 3 may add yardage-related fields when available:

- `yardages_m`
- `yardage_source`
- `yardage_confidence`
- `yardage_provenance`

If yardage is absent, the record remains valid as long as par source and provenance are explicit.

## Resolver Ladder

The resolver order is fixed:

1. Played scorecard `holePars`, confidence `high`, provenance `garmin_scorecard`.
2. Garmin CourseView release par, confidence `high`, provenance `courseview_release`.
3. Official or saved parser fixture, confidence `high` or `medium`, provenance naming the saved fixture.
4. Deterministic length estimate, confidence `medium`, provenance `length_estimate`.

Played data wins because it reflects the user's actual Garmin scorecard. CourseView wins over estimate
because it is Garmin-native par for the course. Official/parser data is only used when it is saved and
tested offline.

## Architecture

Keep the boundary in `ai_caddie/course_reference.py`:

- `played_par_by_nine(root=...)`
- `courseview_par(global_id, allow_fetch=..., root=...)`
- `resolve_par(global_id, course_name=..., lengths_m=..., allow_fetch=..., root=...)`
- `build_played_store(root=...)`

Do not add a separate service unless the file becomes hard to reason about during implementation.
If web parser support is needed, place parser-specific logic in a focused module and keep
`course_reference.py` as the resolver orchestrator.

## Error Handling

- Missing scorecards produce no played record, not a failure.
- Missing CourseView release falls through to parser or estimate.
- Parser mismatch returns no record unless the fixture proves the course identity.
- Estimate fallback must label itself as estimate and never claim high confidence.
- Corrupt persisted records should be ignored or rewritten by the resolver, not returned as trusted data.

## Testing

Add or extend targeted backend tests:

- `tests/test_course_reference.py`
  - played source persists high-confidence records.
  - CourseView source persists high-confidence records for unplayed nines.
  - cached stored CourseView records are reused.
  - estimate source labels medium confidence and never overrides played/CourseView.
  - persisted records include source, confidence, and provenance.
- Parser tests, if any parser path remains:
  - use saved fixture files under `tests/fixtures`.
  - assert no live network call in CI.
  - assert wrong-course or ambiguous parser results are rejected.
- Real-data smoke:
  - count played globalIds with stored course references.
  - report course-ref coverage in readiness or data-quality output.

Verification command:

```bash
uv run python -m unittest tests.test_course_reference tests.test_pipeline tests.test_server_v2_readiness -v
git diff --check
```

## Acceptance Criteria

- `resolve_par(global_id)` returns source-labeled par automatically for real played courses and searched
  CourseView results when data is available.
- `data/courses/<gid>.json` records include source, confidence, and provenance.
- Any parser lookup path has saved fixtures and no live network in CI.
- Course-reference coverage is visible in readiness, data quality, or sync output.
