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
- No live parser path was added; CI uses saved CourseView protobuf fixtures and mocks.
- Readiness exposes course-reference coverage for referenced played nines.

## Verification

```bash
uv run python -m unittest tests.test_course_reference tests.test_pipeline tests.test_server_v2_readiness -v
```

Result: PASS, 32 tests in 77.995s.

```bash
git diff --check
```

Result: PASS.
