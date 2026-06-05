# Test Execution Record — 2026-06-05

Branch: `integration/v2`

Purpose: Execute the roadmap test plan for the current AI Caddie v2 real-data last-mile state without triggering GitHub Actions.

## Planned Commands

| Area | Command | Result |
| --- | --- | --- |
| Git status | `git status --short --branch` | Ran; tracked worktree clean before docs were staged, with known untracked local docs/data artifacts |
| Python compile | `uv run python -m py_compile $(git ls-files '*.py')` | PASS |
| CI workflow tests | `uv run python -m unittest tests.test_ci_workflow -v` | PASS: 14 tests |
| Backend fixture suite | `timeout 1200 bash -c 'AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests -v'` | INCOMPLETE: timed out at 20 minutes with exit 124 |
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
- Full backend fixture discovery did not finish within the 20 minute local cap:
  - Command exit: 124 from `timeout`.
  - It had progressed through connector, course prep/reference/search/par, decision layer, reports, Garmin connector/login/session, geometry evidence, history drilldown, history rounds filters, history stats core, LLM, media, mobile contracts, mobile reconciliation, native evidence, pipeline, and into server caddie tests.
  - One `FAIL` line appeared for `test_sanitized_private_round_fixture_drives_end_to_end_flow` during the long discovery run, but the single-module rerun immediately after passed.
  - This record does not claim full backend discovery passed.
- Targeted reruns:
  - `tests.test_private_acceptance_flow`: 1 test passed in 3.988s.
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
- The long backend discovery command did not complete inside the local cap, so this record relies on targeted backend reruns plus the CI-style and real-data smoke lanes rather than claiming full discovery success.
