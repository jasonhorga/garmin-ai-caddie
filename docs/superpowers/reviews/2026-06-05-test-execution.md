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

### Continued Local Geometry Backfill

After the top-1 probe, ran three bounded local batches against ranked played dependencies:

- Batch 1: 12 attempted, 12 downloaded, 0 failed.
- Batch 2: 12 attempted, 12 downloaded, 0 failed.
- Batch 3: 15 attempted, 15 downloaded, 0 failed.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 40,
  "partialPairs": 0,
  "missingPairs": 1461,
  "coverage": {"ready": 40, "total": 1501, "pct": 2.7},
  "completePlayedNineGlobalIds": [31794, 31795, 31796],
  "globalId41825": {"playedPairs": 18, "readyPairs": 12, "missingPairs": 6},
  "globalId39315": {"playedPairs": 18, "readyPairs": 1, "missingPairs": 17}
}
```

Local ignored geometry cache size after these batches:

```text
data/courseview/prodgeometry  64M
output/prodgeometry           167M
output/prodgeometry_hazards   14M
```

The first representative real played course groups now have full geometry overlap for their played holes:

- `31794`: 9/9 ready, 2,428 ready shots.
- `31795`: 9/9 ready, 2,106 ready shots.
- `31796`: 9/9 ready, 2,362 ready shots.

### Continued Backfill And First Mapping Blocker

Ran two more bounded local batches:

- Batch 4: 20 attempted, 20 downloaded, 0 failed.
- Batch 5: 20 attempted, 19 downloaded, 1 failed.
- Batch 6: skipped known `31765` back-nine release-missing dependencies, then 25 attempted, 25 downloaded, 0 failed.

The single failure was:

```json
{
  "globalId": 31765,
  "localHole": 12,
  "status": "failed",
  "error": "hole not found in CourseView release"
}
```

Root-cause evidence:

- Current CourseView release `31765` (`Beijing Fragrant Hills International Golf Club ~ A`, release `006-D7351-25`) exposes holes `1..9` only.
- Historical scorecards for this course store `courseGlobalId=31765`, `frontNineGlobalCourseId=31765`, no back-nine global id, and an 18-char `holePars` string.
- Historical shot files include `gid031765/hole10..hole18` raster URLs, so the historical 18-hole scorecard and current 9-hole CourseView release disagree.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 104,
  "partialPairs": 0,
  "missingPairs": 1397,
  "coverage": {"ready": 104, "total": 1501, "pct": 6.9},
  "completePlayedGlobalIds": [31794, 31795, 31796, 39315, 41825],
  "globalId39270": {"playedPairs": 18, "readyPairs": 14, "missingPairs": 4},
  "globalId31692": {"playedPairs": 18, "readyPairs": 8, "missingPairs": 10},
  "globalId31765": {"playedPairs": 18, "readyPairs": 7, "missingPairs": 11}
}
```

Local ignored geometry cache size after these batches:

```text
data/courseview/prodgeometry  106M
output/prodgeometry           286M
output/prodgeometry_hazards   25M
```

The next implementation issue is a historical-geometry fallback for scorecards whose shot/raster URLs reference holes that are no longer present in the current CourseView release.

### Continued Backfill With Known Blocker Skipped

Skipped `31765` back-nine dependencies in the local batch runner after the root-cause check above, then ran one additional bounded batch:

- Batch 7: 30 attempted, 30 downloaded, 0 failed.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 134,
  "partialPairs": 0,
  "missingPairs": 1367,
  "coverage": {"ready": 134, "total": 1501, "pct": 8.9},
  "globalId40590": {"playedPairs": 18, "readyPairs": 12, "missingPairs": 6},
  "globalId31692": {"playedPairs": 18, "readyPairs": 14, "missingPairs": 4},
  "globalId39270": {"playedPairs": 18, "readyPairs": 15, "missingPairs": 3}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  128M
output/prodgeometry           352M
output/prodgeometry_hazards   31M
```

### Additional Backfill And Repeated Release-Missing Pattern

Ran one more bounded local batch:

- Batch 8: 40 attempted, 39 downloaded, 1 failed.

The new failure has the same root-cause pattern:

```json
{
  "globalId": 31776,
  "localHole": 14,
  "status": "failed",
  "error": "hole not found in CourseView release"
}
```

Root-cause evidence:

- Current CourseView release `31776` (`Beijing Honghua International Golf Club ~ A`, release `006-D2419-44`) exposes holes `1..9` only.
- This repeats the historical scorecard/current CourseView mismatch first observed for `31765`.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 173,
  "partialPairs": 0,
  "missingPairs": 1328,
  "coverage": {"ready": 173, "total": 1501, "pct": 11.5},
  "globalId40590": {"playedPairs": 18, "readyPairs": 13, "missingPairs": 5},
  "globalId31692": {"playedPairs": 18, "readyPairs": 15, "missingPairs": 3}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  157M
output/prodgeometry           445M
output/prodgeometry_hazards   38M
```

### Dynamic Release-Capability Skip Batch

Ran one additional bounded local batch with a preflight check that loads the current CourseView release and skips any dependency whose `localHole` is not present in the release.

- Batch 9: 50 attempted, 50 downloaded, 0 failed.
- Preflight skipped 13 release-missing dependencies before selecting the 50 processable rows.
- The skipped high-priority dependencies were all current-release nine-hole mismatches for `31765` and `31776`.

Representative skipped rows:

```json
[
  {"globalId": 31765, "localHole": 12, "shotCount": 49, "releaseHoles": [1, 2, 3, 4, 5, 6, 7, 8, 9]},
  {"globalId": 31765, "localHole": 10, "shotCount": 39, "releaseHoles": [1, 2, 3, 4, 5, 6, 7, 8, 9]},
  {"globalId": 31776, "localHole": 14, "shotCount": 20, "releaseHoles": [1, 2, 3, 4, 5, 6, 7, 8, 9]}
]
```

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 223,
  "partialPairs": 0,
  "missingPairs": 1278,
  "coverage": {"ready": 223, "total": 1501, "pct": 14.9},
  "completePlayedCourseCount": 7,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692]
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  190M
output/prodgeometry           544M
output/prodgeometry_hazards   46M
```

### Continued Dynamic Release-Capability Backfill

Ran one more bounded local batch with the same current-release preflight.

- Batch 10: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 16 dependencies before selection.
- All skipped rows were `release_missing_hole`; the representative release mismatch remained `31765` / `31776` current CourseView releases exposing only holes `1..9`.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 298,
  "partialPairs": 0,
  "missingPairs": 1203,
  "coverage": {"ready": 298, "total": 1501, "pct": 19.9},
  "completePlayedCourseCount": 8,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 39668]
}
```

Representative partially covered played course groups after this batch:

```json
{
  "31765": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "40590": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "31702": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "31776": {"playedPairs": 18, "readyPairs": 7, "missingPairs": 11},
  "32871": {"playedPairs": 18, "readyPairs": 11, "missingPairs": 7},
  "39592": {"playedPairs": 18, "readyPairs": 8, "missingPairs": 10}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  246M
output/prodgeometry           725M
output/prodgeometry_hazards   60M
```

Disk remained sufficient:

```text
/dev/root  58G size, 27G used, 31G available
```

### Additional Dynamic Backfill With Growing Unavailable Set

Ran one more bounded local batch with current-release preflight.

- Batch 13: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 25 dependencies before selection:
  - `release_missing_hole`: 17
  - `release_unavailable`: 8
- `release_unavailable` remained concentrated on `31636` and `31637`.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 523,
  "partialPairs": 0,
  "missingPairs": 978,
  "coverage": {"ready": 523, "total": 1501, "pct": 34.8},
  "completePlayedCourseCount": 15,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 40590, 31702, 31793, 39668, 46249, 31829, 31833, 31596]
}
```

New complete played course groups:

```json
{
  "31702": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 357},
  "31596": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 109}
}
```

Representative partially covered played course groups after this batch:

```json
{
  "31765": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "31776": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "31777": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "31791": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "31789": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "32871": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "39659": {"playedPairs": 18, "readyPairs": 5, "missingPairs": 13}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  401M
output/prodgeometry           1.2G
output/prodgeometry_hazards   102M
```

Disk remained sufficient:

```text
/dev/root  58G size, 28G used, 30G available
```

### Additional Dynamic Backfill Near Half Coverage

Ran one more bounded local batch with current-release preflight.

- Batch 16: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 31 dependencies before selection:
  - `release_missing_hole`: 18
  - `release_unavailable`: 13
- `release_unavailable` remained concentrated on `31636` and `31637`.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 748,
  "partialPairs": 0,
  "missingPairs": 753,
  "coverage": {"ready": 748, "total": 1501, "pct": 49.8},
  "completePlayedCourseCount": 21,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 40590, 31702, 31793, 39668, 31777, 31791, 31792, 31789, 46249, 31829, 31833, 31834, 31596, 31597]
}
```

No new played course group became fully complete in this batch, but several high-shot groups moved close to completion:

```json
{
  "32871": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "31835": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "32870": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "31778": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "39592": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "31779": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "39293": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2}
}
```

Top missing course ids now show unavailable rows rising in priority:

```json
[31765, 31776, 31636, 31744, 41319, 31695, 31637, 31673, 31875, 38642, 31669, 31800]
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  551M
output/prodgeometry           1.7G
output/prodgeometry_hazards   140M
```

### Additional Dynamic Backfill Past Half Coverage

Ran one more bounded local batch with current-release preflight.

- Batch 17: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 35 dependencies before selection:
  - `release_missing_hole`: 18
  - `release_unavailable`: 17
- `release_unavailable` remained concentrated on `31636` and `31637`.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 823,
  "partialPairs": 0,
  "missingPairs": 678,
  "coverage": {"ready": 823, "total": 1501, "pct": 54.8},
  "completePlayedCourseCount": 25,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 40590, 31702, 31793, 39668, 31777, 31791, 31792, 31789, 46249, 31778, 31829, 31833, 31834, 31596, 31597, 31806, 31805, 31827]
}
```

New complete played course groups:

```json
{
  "31778": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 154},
  "31806": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 55},
  "31805": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 51},
  "31827": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 49}
}
```

Representative partially covered played course groups after this batch:

```json
{
  "31765": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "31776": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "32871": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "31835": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "32870": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "39293": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "39247": {"playedPairs": 18, "readyPairs": 8, "missingPairs": 10}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  605M
output/prodgeometry           1.8G
output/prodgeometry_hazards   153M
```

### Additional Dynamic Backfill Toward Forty Percent Coverage

Ran one more bounded local batch with current-release preflight.

- Batch 14: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 29 dependencies before selection:
  - `release_missing_hole`: 18
  - `release_unavailable`: 11
- `release_unavailable` remained concentrated on `31636` and `31637`.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 598,
  "partialPairs": 0,
  "missingPairs": 903,
  "coverage": {"ready": 598, "total": 1501, "pct": 39.8},
  "completePlayedCourseCount": 18,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 40590, 31702, 31793, 39668, 31777, 31791, 46249, 31829, 31833, 31834, 31596]
}
```

New complete played course groups:

```json
{
  "31777": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 265},
  "31791": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 246},
  "31834": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 121}
}
```

Representative partially covered played course groups after this batch:

```json
{
  "31765": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "31776": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "31792": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "31789": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "32871": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "39592": {"playedPairs": 18, "readyPairs": 14, "missingPairs": 4},
  "39659": {"playedPairs": 18, "readyPairs": 10, "missingPairs": 8}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  449M
output/prodgeometry           1.4G
output/prodgeometry_hazards   114M
```

### Additional Dynamic Backfill Past Forty Percent

Ran one more bounded local batch with current-release preflight.

- Batch 15: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 31 dependencies before selection:
  - `release_missing_hole`: 18
  - `release_unavailable`: 13
- `release_unavailable` remained concentrated on `31636` and `31637`.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 673,
  "partialPairs": 0,
  "missingPairs": 828,
  "coverage": {"ready": 673, "total": 1501, "pct": 44.8},
  "completePlayedCourseCount": 21,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 40590, 31702, 31793, 39668, 31777, 31791, 31792, 31789, 46249, 31829, 31833, 31834, 31596, 31597]
}
```

New complete played course groups:

```json
{
  "31792": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 238},
  "31789": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 222},
  "31597": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 81}
}
```

Representative partially covered played course groups after this batch:

```json
{
  "31765": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "31776": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "32871": {"playedPairs": 18, "readyPairs": 16, "missingPairs": 2},
  "39592": {"playedPairs": 18, "readyPairs": 15, "missingPairs": 3},
  "31778": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "39623": {"playedPairs": 18, "readyPairs": 14, "missingPairs": 4},
  "31687": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  503M
output/prodgeometry           1.5G
output/prodgeometry_hazards   127M
```

Disk remained sufficient:

```text
/dev/root  58G size, 28G used, 30G available
```

### Additional Dynamic Backfill

Ran one more bounded local batch with the same preflight.

- Batch 11: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 16 dependencies before selection.
- All skipped rows were again `release_missing_hole` for the known current-release mismatch shape.

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 373,
  "partialPairs": 0,
  "missingPairs": 1128,
  "coverage": {"ready": 373, "total": 1501, "pct": 24.9},
  "completePlayedCourseCount": 9,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 40590, 39668]
}
```

New complete played course group:

```json
{
  "40590": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 432}
}
```

Representative partially covered played course groups after this batch:

```json
{
  "31765": {"playedPairs": 18, "readyPairs": 9, "missingPairs": 9},
  "31702": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "31776": {"playedPairs": 18, "readyPairs": 8, "missingPairs": 10},
  "31777": {"playedPairs": 18, "readyPairs": 17, "missingPairs": 1},
  "31789": {"playedPairs": 18, "readyPairs": 15, "missingPairs": 3},
  "32871": {"playedPairs": 18, "readyPairs": 12, "missingPairs": 6},
  "39592": {"playedPairs": 18, "readyPairs": 11, "missingPairs": 7}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  300M
output/prodgeometry           898M
output/prodgeometry_hazards   74M
```

### Additional Dynamic Backfill With Release-Unavailable Rows

Ran one more bounded local batch with current-release preflight.

- Batch 12: 75 attempted, 75 downloaded, 0 failed.
- Preflight skipped 19 dependencies before selection:
  - `release_missing_hole`: 16
  - `release_unavailable`: 3
- A post-batch skip diagnostic found the same new unavailable course ids expanding in priority: `31636` and `31637` (`Shenzhen Golf Club` A/B and B/A shapes). Both had no local release protobuf and live CourseView returned HTTP 404.

Representative `release_unavailable` evidence:

```json
[
  {
    "globalId": 31636,
    "localHole": 2,
    "course": "深圳高尔夫俱乐部 ~ A/B",
    "error": "cache: no 31636_releases.pb; live: HTTP Error 404: Not Found"
  },
  {
    "globalId": 31637,
    "localHole": 3,
    "course": "深圳高尔夫俱乐部 ~ A/B",
    "error": "cache: no 31637_releases.pb; live: HTTP Error 404: Not Found"
  }
]
```

Post-batch real-data coverage values:

```json
{
  "shotCount": 21251,
  "totalPairs": 1501,
  "readyPairs": 448,
  "partialPairs": 0,
  "missingPairs": 1053,
  "coverage": {"ready": 448, "total": 1501, "pct": 29.8},
  "completePlayedCourseCount": 13,
  "completePlayedGlobalIds": [31794, 41825, 31796, 31795, 39315, 39270, 31692, 40590, 31793, 39668, 46249, 31829, 31833]
}
```

New complete played course groups:

```json
{
  "31793": {"playedPairs": 18, "readyPairs": 18, "missingPairs": 0, "shotCount": 284},
  "46249": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 160},
  "31829": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 134},
  "31833": {"playedPairs": 9, "readyPairs": 9, "missingPairs": 0, "shotCount": 130}
}
```

Local ignored geometry cache size after this batch:

```text
data/courseview/prodgeometry  348M
output/prodgeometry           1.1G
output/prodgeometry_hazards   87M
```

Disk remained sufficient:

```text
/dev/root  58G size, 27G used, 31G available
```
