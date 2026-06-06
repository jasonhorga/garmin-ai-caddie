# Sanitized Real-Data Regression Fixtures — Design

- Date: 2026-06-06
- Branch: `integration/v2`
- Scope: Phase 1 real-data hardening in `docs/superpowers/plans/2026-06-05-roadmap-and-test-plan.md`.

## Background

The local Garmin data backfill exposed several real-data shapes that the product must keep handling
without relying on private files during routine tests. The roadmap item is:

- pin-only shot files
- partial/incomplete rounds
- same-day 9-hole merge
- non-ASCII course names
- missing geometry degradation

Existing tests already cover parts of the loader, durable snapshot, same-day merge, and played geometry
coverage. The gap is a small, explicit regression layer that proves these private-data shapes stay
supported by public, deterministic tests.

## Goals

1. Add focused regression tests for the five real-data shapes listed above.
2. Keep the tests secret-free and CI-safe.
3. Exercise the loader/snapshot/data-quality path closest to raw Garmin JSON.
4. Avoid broad fixture churn that could destabilize unrelated product tests.

## Non-Goals

- Do not copy or commit private Garmin scorecards, shot files, cookies, tokens, local paths, or account
  identifiers.
- Do not turn the default `fixture_history_data()` into a large edge-case fixture.
- Do not add live network calls.
- Do not change product behavior unless a regression test exposes an actual implementation gap.

## Chosen Approach

Use transient sanitized fixtures built inside `TemporaryDirectory` during unit tests.

The tests will generate small Garmin-like JSON structures under temporary `data/scorecards`,
`data/shots`, and `output/prodgeometry*` folders, then run existing snapshot/history functions against
that temporary root. The sample values will use synthetic round ids, course ids, names, coordinates, and
shot ids.

This keeps the examples close to the real raw-file contract while leaving no persistent private test
data on disk.

## Test Coverage

The implementation will add a focused backend unittest module, tentatively
`tests/test_real_data_shape_regressions.py`, with one test per shape:

1. **Pin-only shot files**
   A shot JSON file exists and contains pin or empty hole-shot metadata but no usable `shots` rows.
   The normalized round must not report usable shots, and the status must degrade to a non-ready state
   such as `pin_only` or `no_data`, depending on the loader path under test.

2. **Partial/incomplete rounds**
   A scorecard with fewer than 9 completed holes is preserved in normalized history and counted as an
   incomplete round in course detail. It must not be forced into 9-hole or 18-hole scoring metrics.

3. **Same-day 9-hole merge**
   Two sanitized 9-hole scorecards on the same day and canonical course merge into one 18-hole round
   with combined holes, strokes, par, source ids, and shot readiness semantics.

4. **Non-ASCII course names**
   A sanitized course name containing Chinese characters remains intact in canonical course display,
   receives a stable `courseKey`, and appears correctly in history/course views.

5. **Missing geometry degradation**
   Played shot-hole pairs with missing or partial geometry are reported as missing or partial in
   data-quality output and snapshot geometry dependencies. The test must assert graceful degradation,
   not failure.

## Architecture

The tests will reuse existing production helpers instead of introducing a new fixture framework:

- `ai_caddie.connectors.snapshot.build_snapshot_manifest`
- `ai_caddie.connectors.snapshot.write_durable_snapshot`
- `ai_caddie.connectors.snapshot.load_latest_snapshot_history`
- `ai_caddie.history.history_course_detail`
- `ai_caddie.history.history_data_quality`
- `ai_caddie.connectors.snapshot.discover_played_geometry_dependencies`

Shared helper functions inside the test module may create sanitized scorecards and shot files. These
helpers are test-only and should stay small enough to read at the call site.

## Data Safety

Each test must satisfy these constraints:

- All ids, names, coordinates, and shot payloads are synthetic.
- No fixture text contains `cookie`, `csrf`, `token`, `authorization`, `/home/`, or `/users/`.
- No test reads from the repository's private `data/` or `output/` directories.
- Temporary directories are cleaned up by the test runner.

## Verification

After implementation, run:

```bash
uv run python -m unittest tests.test_real_data_shape_regressions tests.test_connector_snapshot tests.test_history_data_quality -v
git diff --check
```

If the tests expose a behavior gap, apply the smallest production change needed and rerun the same
targeted suite. Once passing, update the roadmap and test-execution review with the new evidence.

## Acceptance Criteria

- The Phase 1 roadmap item for sanitized real-data regression fixtures is checked off.
- The new tests cover all five listed shapes.
- The targeted backend suite passes locally.
- The committed diff contains no private data.
