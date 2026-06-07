# AI Caddie Roadmap And Test Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep AI Caddie v2 on the shortest path from implemented skeleton to real-data, single-user production use, with a repeatable local and CI test plan.

**Architecture:** The product is already built as backend APIs, Web v2, iOS/Watch source/contracts, deterministic caddie decisions, and optional fact-bound prose. The remaining roadmap is not a rebuild; it is real-data hardening, automated ingestion, geometry/course-reference coverage, and deployment readiness.

**Tech Stack:** Python 3.12, FastAPI, unittest, uv, React/Vite/TypeScript/Vitest/Playwright, SwiftUI iOS/Watch, XcodeGen/Xcode on macOS, GitHub Actions.

---

## Roadmap Sources

- Master roadmap: `docs/superpowers/plans/2026-05-25-ai-caddie-master-plan-tree.md`
- Current execution plan: `docs/superpowers/plans/2026-05-30-real-data-last-mile.md`
- CourseView par/search design: `docs/superpowers/specs/2026-06-03-courseview-par-and-pipeline-unification-design.md`
- On-device course prep design: `docs/superpowers/specs/2026-05-30-course-prep-on-device-design.md`
- Phase 5 course-prep productization spec: `docs/superpowers/specs/2026-06-06-phase-5-course-prep-productization-design.md`
- Phase 5 course-prep productization plan: `docs/superpowers/plans/2026-06-06-phase-5-course-prep-productization.md`
- Phase 6 deployment/native trial spec: `docs/superpowers/specs/2026-06-06-phase-6-deployment-native-trial-hardening-design.md`
- Phase 6 deployment/native trial plan: `docs/superpowers/plans/2026-06-06-phase-6-deployment-native-trial-hardening.md`

## Current State As Of 2026-06-05

- `integration/v2` contains the implemented v2 skeleton and the CI-minute reduction changes.
- Branch/worktree cleanup is complete: the repo has one worktree and only `integration/v2` / `main` local and remote branches.
- Real Garmin data exists locally:
  - `data/scorecards`: 461 files
  - `data/shots`: 461 files
  - Normalized history: 435 merged rounds, 21,251 shot rows, 70 courses
- Real-data smoke found and fixed one loader bug:
  - pin-only shot JSON files are no longer marked `hasShots=True`
  - six current scorecards are `shotStatus=pin_only`
- Biggest known product gap:
  - Played geometry backfill has exhausted the processable current-release set.
  - Real played shot-hole geometry coverage is 1,465/1,501 pairs, 97.6%.
  - The remaining 36 missing pairs are currently blocked by release availability or current-release shape:
    `release_missing_hole` for `31765`/`31776`, and `release_unavailable` for `31636`/`31637`.

## Roadmap

### Phase 1: Real-Data Spine And Geometry Coverage

**Outcome:** History, stats, round detail, course/hole detail, clubs, data quality, and geometry evidence work on the user's real Garmin data.

- [x] Land real scorecards and shots locally.
- [x] Smoke real history endpoints and direct history functions.
- [x] Fix pin-only shot files being reported as ready shots.
- [x] Decode/sync geometry for played course globalIds so real shot-hole pairs overlap with CourseView geometry.
- [x] Add sanitized regression fixtures for real-data shapes:
  - pin-only shot files
  - partial/incomplete rounds
  - same-day 9-hole merge
  - non-ASCII course names
  - missing geometry degradation
- [x] Make data-quality output explicitly show geometry coverage for real played courses.

**Done when:** Real-data smoke reports the current round count, shot coverage, club profiles, round detail, and at least representative real played holes with geometry evidence.

### Phase 2: Auth Refresh And Fetch Automation

**Outcome:** The data pipeline refreshes Garmin session material and fetches scorecards/shots without manual Claude/browser handoff.

- [x] Productize headless Garmin CN login into connector code.
- [x] On 401, refresh web cookie/csrf and retry once.
- [x] Add `--refresh-auth` and cron-compatible trigger.
- [x] Mock browser/auth tests assert no cookie, csrf, password, or local private path leaks.

**Done when:** An expired Garmin session self-heals locally and the status API reports a clean refresh state.

### Phase 3: Course Reference And Par/Yardage Store

**Outcome:** Every played or searched course gets source-labeled par and yardage metadata cached in `data/courses/<gid>.json`.

- [x] CourseView par decode and course search exist.
- [x] Build or finish the resolver ladder:
  - played `holePars`
  - CourseView release par
  - official/scraped source when available
  - deterministic length estimate fallback
- [x] Persist source, confidence, and provenance for every resolved course reference.
- [x] Add saved-HTML/parser fixtures for any web lookup path; no live network in CI.

**Done when:** `resolve_course_par(globalId)` returns labeled par automatically for real played courses and unplayed CourseView search results.

### Phase 4: End-To-End Private Pipeline

**Outcome:** One command runs the private single-user sync path idempotently.

- [x] Wire auth refresh -> fetch history/shots -> geometry sync -> course-reference ingest.
- [x] Add readiness fields for last sync, session age, data freshness, shot coverage, geometry coverage, and course-ref coverage.
- [x] Add a local private smoke that runs against real data without logging secrets.

**Done when:** The user can trigger one command and the product reflects current Garmin data with visible coverage/confidence.

### Phase 5: Fold Course Prep Prototype Into Product Surfaces

**Outcome:** The standalone `course_review/*.html` prototype becomes generated product UI/API data.

- [x] Promote renderer/route/hazard carry math into engine modules with tests.
- [x] Expose course-prep DTOs through Web and mobile APIs.
- [x] Add Web v2 course-prep page with interactive hole map.
- [x] Feed iOS/Watch course prep package fields for offline use.

**Done when:** Pre-round prep is browsable in `web_v2`, cached by iOS, and summarized by Watch without standalone generated HTML.

### Phase 6: Deployment, Native Release, And Trial Hardening

**Outcome:** The private single-user product can run unattended and ship to the user's phone/watch.

- [x] Prepare reachable-backend deployment manifests for Render/Fly/container hosting.
- [x] Add a home-only NAS VM runbook using outbound Cloudflare Tunnel or
  Tailscale Funnel so the backend can be phone-reachable without exposing SSH
  or opening home-router inbound ports.
- [x] Add manual GitHub Fly deploy workflow that can deploy the backend, set
  `AI_CADDIE_API_BASE_URL`, run remote private-trial smoke, and emit Phase 6
  preflight artifacts after `FLY_API_TOKEN` and `AI_CADDIE_ADMIN_TOKEN` are
  configured.
- [x] Add manual GitHub Phase 6 readiness workflow that reruns external
  preflight and roadmap completion evidence after backend, review, or install
  state changes.
- [x] Add TestFlight build-time native API base URL wiring.
- [x] Deploy a phone-reachable backend host and point the native app at it.
  Evidence: NAS VM Docker API is healthy on `127.0.0.1:9000`, repo variable
  `AI_CADDIE_API_BASE_URL` points at a Cloudflare Quick Tunnel HTTPS origin,
  and GitHub Actions run `27088479370` proved `phone_reachable_backend_url`
  plus authenticated `backend_probe` ready. The Quick Tunnel is temporary; use
  a named Cloudflare Tunnel or Tailscale Funnel before relying on a long-lived
  connected TestFlight backend.
- [x] Configure admin token, backup, import/export, and redaction checks.
- [x] Run native mobile CI only on native changes or manual dispatch.
- [x] Run TestFlight signing/bootstrap and CD only when explicitly needed.
- [x] Upload signed iOS + watch build `0.1.0 (3)` to TestFlight.
- [x] Verify TestFlight build status through App Store Connect API:
  `VALID`, `IN_BETA_TESTING`, `usesNonExemptEncryption=false`.
- [x] Create/list external TestFlight group `Private Trial`.
- [x] Add a Phase 6 external release preflight that reports missing backend URL,
  repo variables, external-review feedback email/submission, tester coverage,
  and device install verification without printing secret values.
- [x] Confirm App Store Connect reports build `0.1.0 (3)` ready for external
  Beta App Review submission: `READY_FOR_BETA_SUBMISSION`. Evidence:
  `iOS TestFlight Testers` run `27088348501`.
- [ ] Submit external Beta App Review.
- [x] Add/confirm target tester emails for the external group or confirm the
  user is covered by the existing internal group.
  Evidence: GitHub Actions run `27082080178` assigned 2 external testers to
  `Private Trial`.
- [ ] Verify installation from TestFlight on iPhone/watch.

**Done when:** Backend is reachable, mobile can install via TestFlight, and private-trial smoke/readiness evidence is current.

## Test Strategy

### Test Lanes

| Lane | Scope | Command | Environment | Gate |
| --- | --- | --- | --- | --- |
| Python compile | Syntax/import surface for tracked Python files | `uv run python -m py_compile $(git ls-files '*.py')` | local Linux / CI | Required before commit |
| Backend fixture unit suite | Full deterministic backend tests without private Garmin data | `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests -v` | local Linux / CI | Required for broad backend changes |
| Backend targeted | Faster tests for touched modules | Example: `uv run python -m unittest tests.test_ai_caddie tests.test_server_v2_history_overview -v` | local Linux | Required for narrow changes |
| Real-data smoke | Real local Garmin data shape and key API behavior | ad hoc Python TestClient smoke, `AI_CADDIE_DATA_MODE=local` | local only | Required before claiming real-data phase progress |
| Frontend unit | React/API client behavior | `npm test -- --run` in `web_v2` | Node 24 | Required for Web changes |
| Frontend lint | ESLint | `npm run lint` in `web_v2` | Node 24 | Required for Web changes |
| Frontend build | TypeScript/Vite production build | `npm run build` in `web_v2` | Node 24 | Required for Web changes |
| Frontend visual smoke | Playwright browser smoke | `npm run test:e2e` in `web_v2` | Node 24 + Chromium | Required before Web release or visual claims |
| Private trial smoke | Fixture/private API security and redaction | `ops/smoke_private_trial.sh http://127.0.0.1:<port>` | API running with admin token | Required before deploy/trial |
| Phase 6 external preflight | GitHub config, public backend URL, backend probe, tester/review/install gates | `uv run python ops/phase6_external_readiness.py --api-base-url https://<api-host> --probe-backend --output logs/phase6_external_readiness_latest.json` | deployed API + GH token + admin token | Required before connected TestFlight trial |
| Native source/contracts | iOS/Watch contracts and source expectations | Python tests under `tests/test_mobile_contracts.py`, `tests/test_native_build_evidence.py` | local Linux / CI | Required for mobile contract changes |
| Native simulator | Actual iOS/Watch build and tests | `xcodegen generate ...` then `xcodebuild test ...` | macOS/Xcode only | Required for native source release |
| CI workflow contract | GitHub Actions minute controls and path filters | `uv run python -m unittest tests.test_ci_workflow -v` | local Linux / CI | Required for workflow changes |

### Real-Data Smoke Requirements

The local real-data smoke must verify:

- `cached_load_history_data()` loads non-zero raw scorecards, merged rounds, and normalized shots.
- `/api/v2/health`, `/history/overview`, `/history/rounds`, `/history/stats`, and `/sync/status` return 200.
- A latest any-round detail returns 200 and exposes `holeDetails`.
- At least one 18-hole and one 9-hole round detail returns 200 when available.
- `history_status`, `history_courses`, `history_clubs`, and `history_data_quality` return coherent counts.
- `shotStatus=pin_only` scorecards are not counted as usable shot rows.
- Shot-hole pairs and geometry coverage are measured and reported, even when coverage is zero.

### Known Test Constraints

- Use manually dispatched GitHub Actions for heavyweight validation; keep local
  checks targeted to touched code unless a broad local check is explicitly needed.
- If the local shell only has Node 18, use `npm exec --yes --package=node@24 -- npm ...` for Web verification.
- General CI no longer runs on push. It runs on PR or `workflow_dispatch`.
- Native mobile CI is isolated to `workflow_dispatch` and native path PRs.
- Linux cannot run real Xcode simulator tests; native simulator verification requires macOS.
- Some caddie context fixture tests are slow because context generation builds full decision/stat context.
- Full backend discovery should use `AI_CADDIE_DATA_MODE=fixture`; default `local_or_fixture` may select private local data and make fixture-ref assertions invalid.

## Execution Plan For This Run

- [x] Commit the current real-data last-mile plan into the repo.
- [x] Commit this roadmap and test plan into the repo.
- [x] Execute Python compile.
- [x] Execute backend fixture suite with a 20 minute cap; record the timeout and targeted reruns.
- [x] Fix the discovered backend fixture-suite settings-cache order dependency.
- [x] Rerun backend fixture suite with a 60 minute cap and record the final passing result.
- [x] Execute real-data smoke.
- [x] Execute frontend unit, lint, build, and visual smoke under Node 24.
- [x] Execute private-trial smoke against a local fixture API.
- [x] Record results in `docs/superpowers/reviews/2026-06-05-test-execution.md`.
