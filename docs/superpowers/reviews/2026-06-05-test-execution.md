# Test Execution Record — 2026-06-05

Branch: `integration/v2`

Purpose: Execute the roadmap test plan for the current AI Caddie v2 real-data last-mile state without triggering GitHub Actions.

## Planned Commands

| Area | Command | Result |
| --- | --- | --- |
| Git status | `git status --short --branch` | Ran; tracked worktree clean before docs were staged, with known untracked local docs/data artifacts |
| Python compile | `uv run python -m py_compile $(git ls-files '*.py')` | PASS |
| CI workflow tests | `uv run python -m unittest tests.test_ci_workflow -v` | PASS: 14 tests |
| Backend fixture suite, 20 min cap | `timeout 1200 bash -c 'AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests -v'` | INCOMPLETE: timed out at 20 minutes with exit 124 |
| Backend fixture suite, 60 min cap before isolation fix | `timeout 3600 bash -c 'AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests -v'` | FAIL: 622 tests in 1469.604s, 1 failure, 4 skipped |
| Settings-cache order regression | poisoned `get_settings()` to `local_or_fixture`, then ran `tests.test_private_acceptance_flow.PrivateAcceptanceFlowTests.test_sanitized_private_round_fixture_drives_end_to_end_flow` | RED before fix; PASS after fix |
| Backend fixture suite, 60 min cap after isolation fix | `timeout 3600 bash -c 'AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests -v'` | PASS: 622 tests in 1498.641s, 4 skipped |
| Backend targeted: private acceptance | `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_private_acceptance_flow -v` | PASS: 1 test |
| Backend targeted: caddie context/decision API | `timeout 720 bash -c 'AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_server_v2_caddie -v'` | PASS: 13 tests in 485.286s |
| Real-data smoke | local TestClient smoke with `AI_CADDIE_DATA_MODE=local` | PASS |
| Frontend unit | `cd web_v2 && npx -y -p node@24 node node_modules/vitest/vitest.mjs --run` | PASS: 24 files, 180 tests |
| Frontend lint | `cd web_v2 && npx -y -p node@24 node node_modules/eslint/bin/eslint.js .` | PASS |
| Frontend build | `cd web_v2 && npx -y -p node@24 node node_modules/typescript/bin/tsc -b && npx -y -p node@24 node node_modules/vite/bin/vite.js build` | PASS |
| Frontend visual smoke | `cd web_v2 && npx -y -p node@24 node node_modules/@playwright/test/cli.js test` | PASS: 2 tests |
| Private smoke | `AI_CADDIE_ADMIN_TOKEN=local-smoke-token AI_CADDIE_SMOKE_LOG_DIR=/tmp/ai-caddie-smoke-2026-06-05 ops/smoke_private_trial.sh http://127.0.0.1:9010` | PASS |

## Results

### Backend

- Python compile passed with no output and exit 0.
- CI workflow contract tests passed: 14 tests in 0.097s.
- Full backend fixture discovery did not finish within the first 20 minute local cap:
  - Command exit: 124 from `timeout`.
  - It had progressed through connector, course prep/reference/search/par, decision layer, reports, Garmin connector/login/session, geometry evidence, history drilldown, history rounds filters, history stats core, LLM, media, mobile contracts, mobile reconciliation, native evidence, pipeline, and into server caddie tests.
  - One `FAIL` line appeared for `test_sanitized_private_round_fixture_drives_end_to_end_flow` during the long discovery run, but the single-module rerun immediately after passed.
- A second 60 minute full backend fixture run completed but failed one test:
  - 622 tests ran in 1469.604s.
  - Failure: `test_sanitized_private_round_fixture_drives_end_to_end_flow`.
  - Assertion: `package["sourceCoverage"]["state"]` was `degraded`, expected `ready`.
  - Root cause: `get_settings()` had cached `AI_CADDIE_DATA_MODE=local_or_fixture` from an earlier test environment, so the acceptance test's patched fixture environment was ignored and the mobile package endpoint looked at local real data instead of fixture round `900001`.
- Fixed the test isolation issue in `tests/test_private_acceptance_flow.py` by clearing `get_settings()` before and after the test and after the fixture env patch is active.
- Regression verification:
  - Before the fix, a poisoned-cache targeted run failed with the same `degraded` vs `ready` assertion.
  - After the fix, the same poisoned-cache targeted run passed.
- Final full backend fixture discovery passed:
  - 622 tests ran in 1498.641s.
  - Result: `OK (skipped=4)`.
- Targeted reruns:
  - `tests.test_private_acceptance_flow`: 1 test passed in 1.323s after the isolation fix.
  - `tests.test_server_v2_caddie`: 13 tests passed in 485.286s.

### Real-Data Smoke

Local real-data smoke passed with these measured values:

```json
{
  "raw_rounds": 461,
  "rounds_after_merge": 435,
  "shots": 21251,
  "hasShots_raw": 455,
  "pinOnly_raw": 6,
  "endpoint_statuses": {
    "/api/v2/health": 200,
    "/api/v2/history/overview": 200,
    "/api/v2/history/rounds": 200,
    "/api/v2/history/stats": 200,
    "/api/v2/sync/status": 200
  },
  "first_round_detail_status": 200,
  "courses": 70,
  "clubs": 28,
  "data_quality_summary": {
    "scorecards": 461,
    "shotsReady": 455,
    "missingShots": 6,
    "missingGeometryHoles": 7314,
    "reports": 0,
    "missingReports": 455,
    "lowClubSamples": 2
  },
  "shot_hole_pairs": 1501,
  "pairs_with_geometry": 0
}
```

The real-data result keeps the next roadmap blocker explicit: geometry for played shot-hole pairs is still not aligned.

### Frontend

- The default system Node is `v18.19.1`; `web_v2` requires Node 24.
- Running `npm test -- --run` under Node 18 failed at startup because `node:util` does not export `styleText`.
- Running `npm run build` under Node 18 failed because Vite requires Node 20.19+ / 22.12+.
- Retesting with temporary Node 24 (`npx -y -p node@24`) passed:
  - Vitest: 24 test files, 180 tests, duration 90.88s.
  - ESLint: exit 0.
  - Build: Vite built `dist/` successfully.
  - Playwright visual smoke: 2 tests passed in 14.4s.

### Private Trial Smoke

- Started local fixture/private API:
  - `AI_CADDIE_DATA_MODE=fixture`
  - `AI_CADDIE_SECURITY_PROFILE=private`
  - `AI_CADDIE_ADMIN_TOKEN=local-smoke-token`
  - URL: `http://127.0.0.1:9010`
- Health probe returned 200.
- `ops/smoke_private_trial.sh` passed and wrote evidence under `/tmp/ai-caddie-smoke-2026-06-05`.
- The local API process was stopped after smoke.

## Known Constraints

- No GitHub Actions run is required for this record.
- Native iOS/Watch simulator tests require macOS/Xcode and are not executable in this Linux workspace.
- Full backend discovery is slow locally: the passing 60 minute-cap run took 1498.641s.

## Follow-Up: Played Geometry Data Quality

Purpose: make the Phase 1 geometry blocker visible from data-quality output, not only from an ad hoc smoke script.

Change:

- Added `playedGeometryCoverage` to `history_data_quality()`.
- The new block groups unique played `(globalId, localHole)` shot-hole pairs by course, reports ready/partial/missing pair counts, reports ready/partial/missing shot counts, and sorts `topMissingCourses` by affected shot volume.

Commands:

| Area | Command | Result |
| --- | --- | --- |
| TDD red | `uv run python -m unittest tests.test_history_data_quality -v` before implementation | RED: `KeyError: 'playedGeometryCoverage'` |
| Targeted data-quality test | `uv run python -m unittest tests.test_history_data_quality -v` | PASS: 1 test |
| Adjacent backend tests | `uv run python -m unittest tests.test_ai_caddie tests.test_history_stats_core tests.test_history_data_quality -v` | PASS: 51 tests, 4 skipped |
| Python compile | `uv run python -m py_compile ai_caddie/history.py tests/test_history_data_quality.py` | PASS |
| Real-data played geometry smoke | local Python smoke with `AI_CADDIE_DATA_MODE=local` | PASS |

Real-data smoke values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 0,
  "partialPairs": 0,
  "missingPairs": 1501,
  "coverage": {"ready": 0, "total": 1501, "pct": 0.0},
  "topMissingCourseGlobalIds": [31794, 41825, 31796, 31795, 39315]
}
```

This does not resolve geometry coverage yet. It turns the blocker into a ranked, product-readable dependency list for the next sync step.

## Follow-Up: Ranked Played Geometry Sync

Purpose: make geometry sync prioritize the real played holes with the highest shot volume, then prove the path can download and decode at least one currently missing played hole.

Change:

- Added `discover_played_geometry_dependencies()` to rank unique played `(globalId, localHole)` pairs by affected shot count.
- Changed `ai_caddie.pipeline._ensure_geometry(limit=...)` to prefer ranked played shot dependencies when normalized shots exist.
- Added `--geometry-limit` parsing for bounded local sync probes.

Commands:

| Area | Command | Result |
| --- | --- | --- |
| Targeted backend tests | `uv run python -m unittest tests.test_connector_snapshot tests.test_pipeline -v` | PASS: 22 tests in 52.852s |
| Python compile | `uv run python -m py_compile ai_caddie/connectors/snapshot.py ai_caddie/pipeline.py tests/test_connector_snapshot.py tests/test_pipeline.py` | PASS |
| Diff whitespace check | `git diff --check` | PASS |
| Real-data dependency smoke | local Python smoke with `discover_played_geometry_dependencies(data, limit=5)` | PASS |
| Top-1 geometry sync probe | local Python smoke with `ensure_geometry_dependencies(discover_played_geometry_dependencies(data, limit=1))` | PASS: attempted 1, downloaded 1, failed 0 |
| Post-sync geometry evidence | `geometry_coverage_for_hole(31796, 4)` | PASS: coverage `ready`, hazards and meshes present |
| Post-sync data-quality smoke | `history_data_quality()["playedGeometryCoverage"]` after `stats_cache.clear()` | PASS |

Top ranked dependency before sync:

```json
{
  "globalId": 31796,
  "localHole": 4,
  "status": "missing",
  "shotCount": 391,
  "profileIdAvailable": true
}
```

Generated local geometry cache files are ignored by git:

```text
data/courseview/prodgeometry/31796/hole04_220572.zip
output/prodgeometry/gid31796_h04_meshes.json
output/prodgeometry/gid31796_h04_stats.json
output/prodgeometry/gid31796_h04_tee_distances.json
output/prodgeometry_hazards/gid31796_h04_hazards.json
```

Post-sync real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 1,
  "partialPairs": 0,
  "missingPairs": 1500,
  "coverage": {"ready": 1, "total": 1501, "pct": 0.1},
  "readyGlobalId": 31796,
  "readyLocalHole": 4,
  "readyShotCount": 391
}
```

This proves the missing-geometry blocker is actionable through the current local CourseView/prodgeometry path. It does not complete the Phase 1 geometry item yet; 1,500 played shot-hole pairs remain missing.
