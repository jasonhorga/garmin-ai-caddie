# Garmin AI Caddie Project State

> This is the short, durable execution state for the current product push.
> Long reviews and historical plans remain reference material; they are not the
> live task queue.

**Updated:** 2026-08-27 UTC
**Branch:** `codex/p0-p1-p2-checkpoint-20260823`
**Source baseline:** `cc2ad861` (canonical cherry-pick of candidate `1aed8f50e46b49a9f56dcc98fdf242a0bbd51a30`)
**Release rule:** no TestFlight upload until every P0/P1/P2 release gate below
has runtime evidence and the owner approves the comparison.

## Objective

Close the smallest set of product and engineering gaps needed for a Garmin/S70
first round flow across Watch, iOS and Web: reliable start, live scoring,
course preparation, review, and synchronized history. Preserve existing working
code; do not restart the old multi-week plan tree.

## Current Slice

**`REL` — release readiness and TestFlight gate** (`in-progress`)

`W1` and `S1` are closed with isolated current-head evidence. The public
service still runs revision `6a6080c6...`; no production deployment or data
synchronization was performed. R2 Web HMB and same-round iOS simulator runtime
evidence are complete, and the owner's `go` instruction on 2026-08-26 is
recorded as approval to advance the evidence gate. REL now checks the external
release prerequisites; no TestFlight upload is performed by this transition.
Candidate artifacts and production uploads are separate gates. Release provenance
binds commit, workflow/build, API origin host, backend revision, IPA hash, and upload
flag; tester/install assertions are manual and build-number-bound.
The artifact-only build is green. A fresh homeserver probe found the existing
candidate and production upstreams, Caddy, and the public Funnel all returning
200; the earlier ingress timeout was transient. The candidate remains the
public upstream, but its revision is not yet proven identical to the IPA and
the first GitHub-runner readiness probe timed out once; a strict rerun passed.

Canonical now includes the full release candidate chain through `cc2ad861`.
Opus supplied a final GO verdict in the handoff; no repository report path or
report hash was supplied, so none is claimed here. The release-specific
homeserver suite passed 100 tests, with remote Python compilation and
`git diff --check` also passing. External GitHub API, macOS native/TestFlight
execution, IPA signing/upload, and App Store Connect facts remain unverified.
Release-preflight verification on canonical HEAD `cc2ad861200f4c4aee74a8063aff4f57948a8b09`
used a short-lived homeserver scratch checkout with Git metadata: the focused
release suite passed 100/100, and full Python test discovery passed 1,974 tests
with 13 skips. Full-tree Python compilation passed. The real fixture-based
artifact-only provenance dry run produced a hashed IPA and exercised both
pre-upload and post-upload evidence contracts without network or production
writes. Source CI, Native Mobile CI, Phase 6 GitHub-runner validation, and
macOS/TestFlight artifact signing/upload remain to be run externally.
The same Linux scratch ran full Python discovery successfully; `web_v2` Vitest
reported 608 passed, 7 skipped, and one timeout in the existing stale-trends
refresh test (`src/App.test.tsx:1622`). Web lint passed with two existing
Fast Refresh warnings, and the production Vite build passed. The repository
root `npm test` remains a historical placeholder that exits with
`Error: no test specified`; the actual `web_v2` checks were run separately.
An external Actions orchestration attempt on 2026-08-27 listed available
workflows, but GitHub returned `No commit found for SHA` for canonical
`cc2ad861200f4c4aee74a8063aff4f57948a8b09`. Pushing this local-only candidate
was not authorized, so no source CI, Native Mobile CI, or Phase 6 run was
dispatched and no run ID or artifact is claimed. TestFlight, release, deploy,
and signing workflows were not dispatched.
After the owner-authorized push of `91d91694ea1bd3d2318bd93f62fe851e19204ffc`
to `codex/p0-p1-p2-checkpoint-20260823`, source CI run `33071951190` completed
successfully (backend, frontend, Docker, and visual smoke). Native Mobile CI
run `33071953908` completed failure at `Real-simulator screenshots (iOS,
XCUITest against live backend)`; its small artifacts were retained only long
enough to verify: `real-flow.mp4` 760,395 bytes,
SHA256 `96f345d980c7c81194d0a8089f8dc4764112ba74b4ff997c45117e4097eecc6c`,
and `ios-app.log` 88 bytes,
SHA256 `d0b53e2a719d60b6dbcd54eba0b8286a2b494eb7b3f8de8de5b6cdc8b8ecba38`.
Phase 6 dispatch run `33071919393` failed before execution because GitHub
rejected the workflow expression `runner.temp`; no Phase 6 evidence was
produced. TestFlight/release/deploy/signing workflows remain unrun.

Only one task may become `in-progress` at a time. Update this file before
starting the next slice.

The current release-hardening candidate requires a fresh remote verification
of the focused readiness/provenance/workflow suites. No production service,
TestFlight upload, or signing resource is created by this source transition.

## Task Ledger

These IDs persist across sessions and context compactions. They are the only
project-level task list; historical plans are reference material.

| ID | State | Scope | Exit evidence |
|---|---|---|---|
| `W1` | `done` | Watch lifecycle, independent discovery, offline/restart, and 41/45/49 mm behavior. | Run `32806892801` watch-runtime job succeeded at head `8a3ee8ba`: 41/45/49 mm captures, real Cypress 18-hole install/restore, same-round 1–18 journey, hole-1 history edit while live on hole 10, finish confirmation, 57 queued records acknowledged, remote finish success, plus Cancel recovery and abandon/tombstone markers. |
| `S1` | `done` | Sync provenance, resumable background course download, real club-distance data, and Garmin-to-client consistency. | Focused backend/Web gates plus Native Mobile CI `32837705596` at `bf84ea8a`: iOS 257 tests, Watch 315 tests, iOS/Watch design snapshots, real iOS flow/video, 11 Watch runtime screenshots, secret scans, and non-empty runtime/build artifacts. |
| `R1` | `done` | Web map-first review editor/cache slice described above. | Focused tests plus remote add/drag/delete/reorder/save/reload evidence. |
| `R2` | `done` | iOS/Web review parity, first-frame/cache, overlay-first layout, and unified trend entry after `R1`. | Half Moon Bay round-by-round facts, same-round iOS/Web request/first-frame evidence, public comparison page, and owner `go` approval. |
| `REL` | `in-progress` | Release and TestFlight gate; artifact-only readiness first. | Verify source/native gates, production provenance, signing/TestFlight readiness, then request explicit upload confirmation. Revision consistency and manual tester/device gates remain before upload. |

### Status vocabulary

`queued` means defined but not started; `in-progress` means the current slice;
`evidence-open` means code exists but runtime proof is missing;
`ci-green-runtime-open` means CI is green but production/runtime proof is
missing; `implementation-partial` means more code is required; `blocked`
means a named external decision or prerequisite is missing; `done` and
`cancelled` are terminal.

## Completed Evidence

- `10d56855`: Watch provisional shot acceptance/completion is idempotent; Native
  Mobile CI run `32684985178` passed.
- `ca3fa89`: caddie tiers are distinct (`稳妥`, `标准`, `进攻`); focused remote
  tests reported 106 passed, 2 skipped.
- `bbc865af`: FIR denominator excludes unknown/empty tokens while preserving
  real `0` as a miss; XCTest coverage added (GitHub verification pending).
- CI run `32689037776` was run against `a1b88a2e`: Docker passed; frontend failed
  because an older `App.test.tsx` mock omits install status; backend failed two
  assertions that still encode pre-`ca3fa89` strategy/readiness expectations.
- The three CI fixes are now integrated at `2ca27720`; rerun `ci.yml` before
  starting the next product slice.
- CI run `32690177548` then passed backend, Docker, component tests, lint and
  build, but failed only visual smoke because two E2E fixtures still used the
  old `phase:'complete', holes:[]` shape. That fixture correction is `edf41054`.
- CI run `32690671928` at head `b6ecee8f` is green across backend, frontend
  visual smoke and Docker.
- R1 is complete across `3eed2c56`, `82538984`, `bfc6bb57`, `de11b5db`, and
  `b1b86af7`: focused Web 38 passed; full Vitest 600 passed/7 skipped; build
  passed; lint 0 errors/2 existing warnings; history visual smoke 1 passed;
  final remote review-editor interaction passed in 11.8s on homeserver after
  temporary browser install, which was removed with no persistent service or
  tunnel left behind.
- Watch runtime run `32707001002` succeeded at head `ca2b2d7a` (artifact
  `9513235658`), covering 41/45/49 mm runtime boundaries and all five stateful
  recovery markers.
- Watch recovery-only run `32791049667` succeeded at head `84a53752` in 20m12s;
  artifact `watch-runtime-evidence` ID `9543591961`, digest
  `sha256:395ecdfdbadba578257737c0f90b667eef9f38c324da257fc02d4bd8e216e381`.
  Its markers prove the Cancel recovery location event is persisted and the
  abandoned round's stale seed is rejected after relaunch. Web evidence was
  correctly skipped.
- CI run `32796906679` at head `8a3ee8ba` passed frontend, backend, and Docker;
  this advances the verified code baseline but does not close W1's production
  18-hole/current-head journey evidence.
- 2026-08-25 public Funnel verification passed: `/`, `/api/v2/health`,
  `/sat/`, `/yoyo/`, `/demos/`, and `/yoyo-api/health` each returned HTTP 200
  after the root route was restored from `127.0.0.1:443` to `:8080`. The
  before/after route backups are under
  `/home/jason/garmin-ai-caddie-data/operations/funnel-backups` (before SHA
  `6f1bc4...`, after SHA `3ea52c...`).
- Watch runtime run `32801079395` at head `8a3ee8ba` passed the 41/49 mm
  coverage, but Preflight live course discovery failed because the public API
  is on backend revision `6a6080c6...` while the expected current-head
  candidate is `8a3ee8ba`; at that point this did not close W1.
- Watch runtime run `32806892801` at head `8a3ee8ba` succeeded for the complete
  W1 journey. Artifact `watch-runtime-evidence` ID `9549422683`, digest
  `sha256:554bbace81931ba65ec47a08a91249fc9ee95d1e8a6d3ae3bc3b55c472b676fc`.
  The Watch job's evidence was scanned for secrets before upload.
- The same run's optional `web-live-evidence` job failed before receiving
  `/api/v2/history/overview` (`net::ERR_FAILED`) through the temporary Quick
  Tunnel; this is a separate Web transport/evidence gap, not a Watch W1
  failure, and produced no Web artifact.
- S1 read-only audit (snapshot `e8JaMj`, cleaned after handoff) found that the
  backend install journal, iOS prep queue, and Watch course store each track a
  different readiness model; there is no shared `precise/offline-installed`
  contract. The iOS queue has finite background grace rather than a durable OS
  transfer, while the backend journal itself is resumable.
- The same audit traced club distances to Garmin advice/average, AutoShot
  history medians, manual bag, and catalog fallback. `/prep` currently drops
  the distance source, and iOS/Web do not normalize spaced Garmin names such as
  `3 Wood`/`3 Iron`; this is the confirmed minimum explanation for the 3-wood/
  3-iron inconsistency. No production runtime mutation was used.
- S1 implementation commits `85acb022`, `bc9ab55e`, and `fb1c1287` now add spaced Garmin
  name normalization, `/prep` distance provenance (`history_median`, Garmin,
  manual, catalog, or explicit `unresolved`), propagation to iOS/Watch/Web,
  and cache invalidation when a manual bag changes. Focused remote verification
  reports 78 backend tests passed with 2 geometry skips; Web focused tests and
  build passed on the delegated worktree. iOS/Watch XCTest has not yet run.
- S1 Watch install-status commit `11c28972` (delegated source `b4688e8a`) adds
  the Watch-side journal contract, 404-as-missing behavior, and focused
  request/decode tests; it has not yet received macOS XCTest evidence.
- Native Mobile CI run `32817814200` at source head `5462f59f` passed XcodeGen,
  iOS XCTest, SwiftJCS boundaries, and design snapshots, but failed the real
  iOS flow at `RealFlowUITests.swift:292`: the search keyboard remained present
  after tapping the manual search button. Watch XCTest and Watch runtime
  screenshots were skipped by that failure.
- Keyboard-focus fix `bf944100` synchronously clears `focusedField` before
  launching manual, nearby, or submit-triggered searches. Review-scope Native
  run `32821984671` completed: `RealFlowUITests.testCaptureRealAppFlow` passed,
  but `ReviewEditUITests.testCaptureReviewEditFlow` failed at line 289 when the
  last reorder handle did not change the preceding visible shot. Full Native
  verification remains blocked on that bounded reorder gate.
- Test-only reorder commit `5fdb9fff` moves the XCUITest drag destination to
  the preceding row's content center. Edit-scope run `32826478232` passed the
  real reorder flow; no production reorder code changed.
- Full Native Mobile CI run `32827910559` was dispatched at `e43a00bf` with
  `capture_scope=full` and the live-revision preflight disabled. XcodeGen,
  iOS XCTest (257 tests), SwiftJCS boundaries, design snapshots, and the real
  iOS flow passed. The Watch test target failed to compile in
  `WatchBackendClientTests.swift` because a multiline raw JSON fixture used
  single-line raw-string delimiters; Watch XCTest and runtime screenshots were
  skipped. Test-only correction `c5f871b6` changes the fixture to a valid
  multiline raw string. No production Watch code changed.
- Full Native Mobile CI run `32832956274` was dispatched at `aa9f9616` with
  `capture_scope=full` and `require_live_preflight=false`. iOS XCTest (257
  tests), SwiftJCS boundaries, iOS snapshots, real iOS flow/video, and Watch
  simulator boot all passed. Watch target compilation then failed because the
  multiline fixture's opening/closing delimiters were on the same lines as
  JSON content (`WatchBackendClientTests.swift:334,351`); Watch XCTest and
  runtime screenshots were skipped. Correction `9bd4ce64` places both
  delimiters on their own lines. No production code changed.
- Full Native Mobile CI run `32837705596` at `bf84ea8a` passed. iOS XCTest
  executed 257 tests and Watch XCTest executed 315 tests, all with zero
  failures. XcodeGen, SwiftJCS boundary checks, iOS/Watch design snapshots,
  real iOS flow/video, and 11 Watch runtime seed/restore/interaction
  screenshots all passed secret-byte scans and uploaded successfully. The
  `watch-real-screenshots` artifact (ID `9561062102`, 289,202 bytes) and
  `native-build-evidence` artifact (ID `9561063172`, 452 bytes) are present
  and non-empty; runtime artifact zip digest is
  `4aa5db2479484c95d120b3cd0def14260c35d616387c4fc07472a909653d7f4d`.
- Read-only Half Moon Bay evidence was collected against revision
  `6a6080c6...` for rounds `17603881` (Ocean, 102, 58 shots) and `17601656`
  (Old, 96, 53 shots). Both have 18/18 hole details and shotmaps, matching
  shot counts/refs and sequential order; all maps are `prodgeometry`, GPS is
  complete, and no hole reports missing data or synthetic shots. The detailed
  checksums and remaining cross-client limits are in
  `docs/reviews/2026-08-25-r2-half-moon-bay-cross-client-evidence.md`; raw
  responses remain private under the homeserver project data directory.
- Current-head source CI run `32843227361` at `a4f80eb9` exposed two bounded
  integration regressions: one backend source-contract assertion still expects
  the pre-reorder XCUITest string, and Web build rejects a test fixture whose
  optional `map.image` no longer satisfies `CoursePrepHole`. Docker passed;
  Web component tests (601 passed, 7 skipped) and lint passed. No release or
  production state changed.
- Source CI run `32844906468` at `1f0bc607` passed all jobs: backend tests and
  private trial smoke, Web component tests (601 passed, 7 skipped), lint,
  TypeScript/Vite build, Playwright visual smoke, and both Docker image/health/
  geometry checks. The two fixes are test/fixture-only in `cf06d587`; production
  code and production revision were unchanged.
- Web-only runtime run `32845282260` at `1f0bc607` passed the real CI-player
  journey through the stable Funnel endpoint. Overview, time trends,
  performance, rounds list, review workbench, and round review all rendered;
  protected overview/detail/shotmap/topo requests returned 200, and the first
  live topo was course `3881` hole 1. The six PNGs are 1440x980 and non-empty;
  artifact `9562076813` is 828,730 bytes with zip SHA256
  `c7993aa100be4c4fbb12be135ed90c473fb5e76d6e5b744dc6a9f09871b8efe7`.
  Secret-byte scanning passed. This proves the stable Web transport and real
  player journey, not an iOS runtime or an HMB-specific cross-client match.
- Web ReviewWorkbench cache slice `6a865217` now persists only successful
  `found=true` maps for a short bounded window (player + round + hole key,
  geometry revision, 5-minute TTL, 24-entry/1.5 MB cap). Storage failures and
  malformed entries are ignored; failed/no-geometry responses are never stored;
  a successful correction evicts both persistent and in-memory entries. Focused
  Vitest was 24/24, lint had 0 errors with 2 pre-existing warnings, and build
  passed on homeserver.
- Source CI run `32847741048` at `769e3609` passed all jobs after that slice:
  backend/private trial, Web component tests (601 passed, 7 skipped), lint,
  TypeScript/Vite build, Playwright visual smoke, and Docker image/health/
  geometry checks.
- Current-head Web-only runtime run `32847990023` passed through the stable
  Funnel endpoint: overview/detail/shotmap/topo all returned 200, Playwright
  1/1 passed, and six 1440x980 PNGs passed secret-byte scanning. Artifact
  `9563119622` is 828,730 bytes with zip SHA256
  `81954f0a9065668fb6bbaac7885d709f9f33e3bdfa15f5d2c2a81b39abc850ec`.
- HMB Web runtime evidence completed on 2026-08-26 against the public Funnel
  revision `6a6080c6...`: owner-admin Playwright with `REVIEW_ROUND_REF=17603881`
  passed 1/1 in 25.6s. Overview, round detail, hole-1 shotmap (`found=true`,
  `globalId=6022`) and topo responses were all 200; six non-empty 1440x980 PNGs
  were 116,548--177,241 bytes and the admin-token secret-byte scan passed. The
  first browser attempt used the non-Funnel container token and got a protected
  endpoint 401/`net::ERR_FAILED`; the Funnel revision's candidate-container
  token resolved that revision mismatch. No token was logged or placed in URLs/
  screenshots, and no production write, deploy, restart, sync, or Funnel change
  occurred. The isolated remote directory, dependencies, outputs, and newly
  downloaded browser cache were removed; pre-existing shared cache remains.

- HMB iOS runtime run `32919313329` at head `e484ac37` passed: iOS XCTest
  257/257, RealFlow 1/1 (324.514s), ReviewEdit 1/1 (208.151s), TeeSelection
  7/7 (475.026s), selected 9/9 (1007.692s). Resolver evidence is round
  `17603881`, Half Moon Bay Ocean hole 1, `globalId/localHole=6022/1`,
  `shotCount=3`, clubs Driver/5I. The real-screenshots artifact contains 32
  non-empty PNGs; the separate design-snapshots artifact contains 30 files,
  and all native secret scans passed. Event-latency files are only
  `round-home.appear` proxies
  (pending=-1, course=31796, about 1.38--1.65s), not topo first-frame proof.
  ReviewEdit used default Cancel and RealFlow disabled event sync; no correction,
  sync, or other write occurred. Preflight was intentionally skipped by input.
- HMB club provenance is now proved read-only against the production data volume.
  Garmin Driver/3W/3H each have `adviceDistance=0` and `averageDistance=0`, and
  no manual bag is present. Current HEAD canonicalizes aliases and selects
  AutoShot history medians: Driver 197m/215yd (n=3155), 3W 171m/187yd (n=535),
  and 3H 159m/174yd (n=236), all `history_median` with high confidence. The
  production image's old ladder retains duplicate `3W`/`3号木杆` rows, uses
  `3号小鸡腿` for hybrid3, includes Putter, and has no provenance fields. The
  private evidence SHA is `04ef01cca74b075882abe43cff25a4791f58857c8017086bc0d99e9f7ea44e2e`.
- The production API recovered without intervention: on 2026-08-25 the
  `garmin-ai-caddie-api-1` container was `healthy`, local and public health GETs
  returned 200, and its `StartedAt` remained `2026-08-04T18:59:17Z`. No restart,
  deployment, synchronization, Funnel change, or production write occurred.
  R2 remains open only for owner screenshot approval, not backend club provenance
  or runtime technical evidence.
- GitHub Web-only HMB runtime run `32944143003` at head `8419840b` passed: job
  `98101156667` completed `1/1` in 39.8s and artifact `9597641080` contains
  six files (821,477 bytes). Overview/detail/shotmap/topo returned 200;
  shotmap found `true` with `globalId=6022`, `localHole=1`; topo holes 1/2
  were `image/png`. Secret scanning passed and the artifact zip SHA-256 is
  `d321b5816904214abcc37c1f231e02fb844ed7dc2a47e667d83d0b04f454f375`.
  Earlier runs `32942764978` and `32943661246` failed at the overview 60s
  transport wait; service diagnosis found no 5xx. Those failures are transport
  evidence gaps, not product errors. The successful GitHub run supersedes the
  homeserver owner-only run as the Web evidence source; that run remains
  supplementary history. R2 remains `evidence-open`, with only owner visual
  approval remaining; `REL` remains `blocked`.
- The R2 owner review page is publicly published at
  `https://caddie.taile36706.ts.net/demos/garmin-r2-owner-review-20260826/`.
  It contains exactly 39 public files (the index plus 38 PNGs); external
  verification returned HTTP 200 for the index and all image URLs, and the
  image SHA-256 values match the private staging copy. No production app route,
  data, or Funnel configuration was changed; this is a static evidence
  publication only. Watch evidence remains separate and is not implied by this
  page.
- Artifact-only release workflow `33024982596` at `ec73527f` passed on the
  GitHub macOS runner. XcodeGen, signing-secret presence, fastlane archive and
  IPA export all passed; the signed IPA artifact is `9628147722` (9,915,969
  bytes; zip digest `1eb0a823692db8bd72fc322fa3ca4437f844fb7764633e272b7970079798fc6d`).
  The log explicitly says `TestFlight upload was not requested`; no binary was
  uploaded to TestFlight.
- Phase 6 read-only audit `33024993745` passed as a workflow but reported an
  incomplete readiness state: all six signing secrets, the public HTTPS URL,
  App Store Connect metadata/review observations were ready, while the backend
  probe timed out and tester coverage/device installation remain manual. Direct
  read-only probes showed the production API at `127.0.0.1:9000` healthy, but
  the public Caddy `:8080` route and candidate host port `:39055` timed out.
  Caddy's current `/api/*` upstream is `127.0.0.1:39055` (candidate image
  `6a6080c0-candidate`, started 2026-08-21); no restart, route switch, or
  production write was performed. At that point REL remained blocked on ingress
  stability and the two manual gates; the later re-audit below supersedes the
  ingress portion of that observation.
- Homeserver ingress re-audit on 2026-08-27 was read-only: candidate `:39055`
  (20/20 HTTP 200, p50 19 ms, p95 37.5 ms), production `:9000` (20/20,
  p50 12 ms, p95 33.5 ms), Caddy `:8080` (20/20, p50 26.4 ms, p95 69.5 ms),
  and public Funnel (10/10, p50 219 ms, p95 579 ms). Candidate authenticated
  overview/round/shotmap requests returned 200. Caddy validation was `Valid`,
  no upstream errors appeared in the last 30 minutes, and no route/container/
  database mutation occurred. Candidate has no Docker healthcheck and uses a
  restart entrypoint that runs Alembic/identity seed against a writable shared
  database, so it was intentionally not restarted or replaced.
- Strict Phase 6 rerun `33029186839` at `10e1a7be` preserved the honest result:
  signing, URL, App Store metadata, and review gates were ready, but the
  GitHub-runner backend probe again returned `TimeoutError`; target tester
  assignment and physical iPhone/Watch installation remain manual-required.
  The run did not upload TestFlight. This runner-only timeout is now a separate
  evidence gap from the healthy homeserver/public probes and must be resolved
  or explicitly bounded before release; the successful rerun below supplies
  that additional evidence.
- Strict Phase 6 rerun `33029475105` at `30ab509f` passed the backend probe:
  the GitHub runner received HTTP 200 and the expected health/readiness schemas
  from `caddie.taile36706.ts.net`. Signing, URL, metadata, and review gates
  were ready; only target tester assignment and physical iPhone/Watch
  installation remained `manual_required`. The workflow failed solely because
  `fail_when_incomplete=true`; it did not upload TestFlight.

These are code/test facts, not proof of a physical Apple Watch Ultra session.

## Exact Next Actions

1. Add/verify a strict revision and API-origin match between the signed IPA,
   public candidate, and backend before release; keep the healthy route and
   candidate untouched unless a new failure is observed.
2. Record target tester coverage and physical iPhone/Watch installation against
   the exact signed artifact.
3. Keep production revision `6a6080c6...` unchanged until a deployment or
   synchronization operation is explicitly approved.
4. Request a separate explicit confirmation before setting
   `upload_to_testflight=true`; a readiness pass alone never uploads a binary.

## Open Blockers / Facts

- Local machine is an editing/control plane; builds, Xcode, Playwright and
  other heavy work run on homeserver or GitHub Actions.
- No immutable production revision has been approved for a deployment/sync
  operation; do not trigger production synchronization as a test.
- The focused green baked fixture is still 1024 px; do not stretch it and call
  it a 1280 px evidence asset.
- The public Funnel root route was restored on 2026-08-25 from
  `127.0.0.1:443` to `:8080` under user authorization; the route backup
  directory and before/after SHAs are recorded above. Public endpoint checks
  returned 200. The public backend remains `6a6080c6...`; the pre-existing
  loopback-only candidate on `127.0.0.1:39055` was inspected but not changed.
- One runtime evidence boundary remains open: deferred-finish network retry is
  still unit-test-only. Cancel completion and old-seed tombstone rejection are
  covered by run `32791049667`.
- Existing user files `.codex-tmp/` and
  `.mockups/watch-shot-tracking.html` are untracked and must be preserved.
- Keep historical Claude/superpowers worktrees unless a separate allow-list
  cleanup is explicitly authorized.
- The temporary current-head candidate, proxy, Quick Tunnel, overlay mount,
  and scratch directory from run `32806892801` were removed after evidence
  collection; public `39055`/Caddy/Funnel health remained unchanged.

## Operating Rules

- At most one modifying implementation agent and one read-only review snapshot.
- Every delegated task returns its worktree, commit, tests, resources and
  cleanup result. Temporary resources are removed by their creator.
- Update this file only when a task changes state, evidence, blocker, or the
  current slice changes. Add a dated one-line entry below; do not paste full
  command logs here.
- After context compression, read this file first, then run lightweight
  `git status`, `git log -8`, and agent-status checks. Do not recreate a new
  master checklist from memory.

## State Changes

- 2026-08-24: Replaced the chat-sized plan with stable task IDs and set `R1`
  as the only queued next slice. Echo-style shell output is intentionally not
  tracked as project state.
- 2026-08-24: Started bounded `R1`; no other modifying task is active.
- 2026-08-24: Integrated `a1b88a2e`; CI `32689037776` passed Docker but exposed
  one Web fixture failure and two backend assertion failures. Fixes are queued
  one modifying agent at a time.
- 2026-08-25: Integrated bounded CI contract fix `cf06d587` as `1f0bc607`,
  pushed the canonical branch, and passed source CI `32844906468`; R2 now has
  a green source baseline and remains open only for real Web/iOS evidence and
  the documented parity/cache gaps.
- 2026-08-25: Stable Funnel Web runtime evidence passed in run `32845282260`;
  the prior Quick Tunnel transport failure is closed for Web. R2 remains open
  for HMB cross-client parity, iOS runtime evidence, and the explicitly scoped
  cache/provenance gaps.
- 2026-08-25: Integrated Web review cache `6a865217` as `769e3609`; source CI
  `32847741048` and current-head stable Web runtime `32847990023` both passed.
  R2 remains open only for the documented HMB/iOS cross-client and provenance
  evidence, plus owner visual approval.
- 2026-08-26: GitHub Web-only HMB run `32944143003` passed at head `8419840b`
  (job `98101156667`, artifact `9597641080`, `1/1` in 39.8s). The first two
  runs failed at the overview 60s transport wait, with no service 5xx found;
  the third run is successful Web evidence, while owner visual approval stays
  open and `REL` stays blocked.
- 2026-08-24: Integrated backend test-contract fix `46aad448` and Web fixture
  fix `2ca27720`; awaiting a matching green CI run.
- 2026-08-24: Integrated visual fixture correction `edf41054`; CI
  `32690671928` at `b6ecee8f` is green across all three jobs. The code batch is
  closed; runtime/product evidence remains open.
- 2026-08-24: Closed `R1` as done with commits `3eed2c56`, `82538984`,
  `bfc6bb57`, `de11b5db`, and `b1b86af7`; focused/full Web tests, build/lint,
  history visual smoke, and final remote review-editor interaction passed;
  temporary browser resources were cleaned up. Started `W1` as the sole
  in-progress slice.
- 2026-08-24: W1 runtime code reached `evidence-open`: run `32707001002` at
  head `ca2b2d7a` succeeded for 41/45/49 mm and five recovery markers, while
  the production journey remained open after an external API 502 and the
  three evidence boundaries listed above.
- 2026-08-24: Read-only homeserver diagnosis confirmed the 502 is caused by
  Funnel root -> `127.0.0.1:443` while project Caddy listens on `:8080`; no
  routing change was made.
- 2026-08-25: Integrated `84a53752` and verified its bounded recovery harness
  in GitHub run `32791049667`; W1 remains evidence-open because production
  18-hole/current-head evidence and deferred-finish network retry runtime
  evidence are still open.
- 2026-08-25: CI run `32796906679` passed frontend, backend, and Docker at
  `8a3ee8ba`; W1 remains evidence-open with the external API 502 blocker and
  current-head production journey still required.
- 2026-08-25: Under user authorization, restored the public Funnel root from
  `127.0.0.1:443` to `:8080`; backups are in
  `/home/jason/garmin-ai-caddie-data/operations/funnel-backups` (before
  `6f1bc4...`, after `3ea52c...`). Public `/`, `/api/v2/health`, `/sat/`,
  `/yoyo/`, `/demos/`, and `/yoyo-api/health` checks returned 200; W1 can
  continue its production 18-hole journey, with deferred-finish retry still
  unit-test-only.
- 2026-08-25: Watch runtime run `32801079395` at `8a3ee8ba` passed 41/49 mm,
  but Preflight live course discovery failed on backend revision mismatch
  (`6a6080c6...` public vs `8a3ee8ba` expected). W1 remains evidence-open and
  requires user authorization to deploy/switch the current-head candidate;
  deferred-finish retry remains unit-test-only.
- 2026-08-25: Run `32806892801` closed the W1 Watch runtime journey at
  `8a3ee8ba`; 18-hole/install/restore/history-edit/finish evidence and Cancel
  plus abandon recovery markers passed. The optional Web job failed through
  the temporary Quick Tunnel with `net::ERR_FAILED`; W1 is nevertheless done,
  and S1 is now the queued next slice. All run-created remote resources were
  cleaned up and public revision/route checks remained unchanged.
- 2026-08-25: Closed W1 and started S1 as the sole in-progress slice; the first
  S1 action is a read-only data-flow audit, with no implementation or
  production synchronization authorized yet.
- 2026-08-25: S1 audit completed without code changes. It confirmed the
  cross-client readiness-contract gap and the spaced Garmin club-name/source
  gap; the next work is two bounded implementation slices with focused tests.
- 2026-08-25: S1 provenance slice merged as `85acb022`; manual-bag cache,
  unresolved-source correction, and history-alias tie-break merged as
  `bc9ab55e`/`fb1c1287`. Delegated homeserver gates passed (78 backend focused
  tests, 2 geometry skips; Web focused tests/build);
  native iOS/Watch evidence is still pending.
- 2026-08-25: Integrated Watch install-status slice `11c28972` from delegated
  commit `b4688e8a`. Native run `32817814200` passed the iOS unit/design gates
  but failed the real search flow at line 292 because the keyboard remained
  visible; Watch stages were skipped. A bounded focus-dismissal fix is now the
  sole active implementation task before the next native run.
- 2026-08-25: Integrated keyboard-focus fix `bf944100` from delegated commit
  `44ba73fb`; it synchronously clears the search field before all three search
  entry paths. Review-scope run `32821984671` passed the complete RealFlow
  search/review journey but failed the ReviewEdit reorder assertion at line
  289; a second bounded delegated worktree is investigating that behavior.
- 2026-08-25: Test-only reorder fix `5fdb9fff` (delegated `ef5261d2`) changed
  the XCUITest drag destination from a second reorder handle to the preceding
  row content. Edit-scope run `32826478232` passed; the full native Watch gate
  is next.
- 2026-08-25: Pushed integrated head `e43a00bf` and dispatched full Native run
  `32827910559` with `capture_scope=full` and `require_live_preflight=false`;
  production revision remains unchanged. The run passed all iOS stages but
  failed Watch compilation on the malformed multiline raw JSON fixture, so no
  Watch XCTest/runtime claim was made.
- 2026-08-25: Integrated test-only Watch fixture correction `c5f871b6` from a
  delegated worktree. The fixture now uses valid multiline raw-string
  delimiters; the next action is a fresh full Native run.
- 2026-08-25: Full Native run `32832956274` at `aa9f9616` passed all iOS
  stages and Watch simulator boot, but Watch compilation still rejected the
  fixture because Swift requires multiline content and closing delimiters to
  start on their own lines. Integrated the bounded test-only correction
  `9bd4ce64`; no Watch runtime evidence is claimed until the next run.
- 2026-08-25: Full Native run `32837705596` at `bf84ea8a` passed all iOS and
  Watch tests, design/runtime screenshot gates, secret scans, and artifact
  uploads. Closed S1 and started R2 as the sole in-progress slice; production
  revision and TestFlight state remain unchanged.
- 2026-08-25: Collected read-only HMB round/shotmap evidence for `17603881`
  and `17601656`; both are complete and `prodgeometry`-backed. Added the
  durable summary in `docs/reviews/2026-08-25-r2-half-moon-bay-cross-client-evidence.md`.
  Current-head CI `32843227361` then found one stale backend contract assertion
  and one Web fixture type error; a single bounded fix agent is handling those
  before R2 runtime evidence continues.
- 2026-08-25: Corrected the bounded HMB provenance probe with a current-HEAD,
  network-disabled container over the production volume mounted read-only. The
  Garmin bag is non-empty but its Driver/3W/3H advice/average values are zero;
  current HEAD selects the real AutoShot medians with provenance, while the
  production image's old ladder has alias duplication, Putter contamination,
  and no provenance. The production API also returned to healthy without a
  restart (`StartedAt` unchanged). R2 stays `evidence-open` only for real HMB
  iOS/Web parity and owner approval; no production/Funnel/sync mutation occurred.
- 2026-08-26: Owner said `go` after the public R2 comparison page was verified;
  interpreted as approval of the R2 evidence gate. Closed R2 and started REL
  as the sole active slice. The next action is an artifact-only release audit;
  no TestFlight upload, production deployment, synchronization, or Funnel
  change is authorized by this state transition.
- 2026-08-27: Artifact-only release run `33024982596` passed and produced a
  signed IPA without uploading. The initial Phase 6 run `33024993745` reported
  an ingress timeout; the subsequent read-only homeserver audit showed the
  route healthy. Strict rerun `33029186839` reproduced a runner timeout once,
  while `33029475105` passed the backend probe. No route/container/data
  mutation was made; REL remains open only for revision consistency and the
  manual tester/device gates.
