# Garmin AI Caddie Project State

> This is the short, durable execution state for the current product push.
> Long reviews and historical plans remain reference material; they are not the
> live task queue.

**Updated:** 2026-08-25 UTC
**Branch:** `codex/p0-p1-p2-checkpoint-20260823`
**Source baseline:** `b2688f3c` (docs-only state commits after source CI run `32847741048` passed at `769e3609`)
**Release rule:** no TestFlight upload until every P0/P1/P2 release gate below
has runtime evidence and the owner approves the comparison.

## Objective

Close the smallest set of product and engineering gaps needed for a Garmin/S70
first round flow across Watch, iOS and Web: reliable start, live scoring,
course preparation, review, and synchronized history. Preserve existing working
code; do not restart the old multi-week plan tree.

## Current Slice

**`R2` — iOS/Web review parity and live evidence** (`evidence-open`)

`W1` and `S1` are closed with isolated current-head evidence. The public
service still runs revision `6a6080c6...`; no production deployment or data
synchronization was performed. R2 is now the only active slice.
Its Web HMB runtime evidence is complete; only the same-round iOS simulator
runtime and owner screenshot approval remain.

Only one task may become `in-progress` at a time. Update this file before
starting the next slice.

## Task Ledger

These IDs persist across sessions and context compactions. They are the only
project-level task list; historical plans are reference material.

| ID | State | Scope | Exit evidence |
|---|---|---|---|
| `W1` | `done` | Watch lifecycle, independent discovery, offline/restart, and 41/45/49 mm behavior. | Run `32806892801` watch-runtime job succeeded at head `8a3ee8ba`: 41/45/49 mm captures, real Cypress 18-hole install/restore, same-round 1–18 journey, hole-1 history edit while live on hole 10, finish confirmation, 57 queued records acknowledged, remote finish success, plus Cancel recovery and abandon/tombstone markers. |
| `S1` | `done` | Sync provenance, resumable background course download, real club-distance data, and Garmin-to-client consistency. | Focused backend/Web gates plus Native Mobile CI `32837705596` at `bf84ea8a`: iOS 257 tests, Watch 315 tests, iOS/Watch design snapshots, real iOS flow/video, 11 Watch runtime screenshots, secret scans, and non-empty runtime/build artifacts. |
| `R1` | `done` | Web map-first review editor/cache slice described above. | Focused tests plus remote add/drag/delete/reorder/save/reload evidence. |
| `R2` | `evidence-open` | iOS/Web review parity, first-frame/cache, overlay-first layout, and unified trend entry after `R1`; the known code slice is present, but real cross-client proof is still missing. | Half Moon Bay round-by-round facts, same-round iOS/Web request/first-frame evidence, and approved runtime screenshots. |
| `REL` | `blocked` | Release and TestFlight gate. | `W1`, `S1`, and `R1`/`R2` evidence complete, production provenance approved, then owner approval. |

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
  R2 remains open for same-round HMB iOS/Web runtime evidence, not backend club
  provenance or service recovery.

These are code/test facts, not proof of a physical Apple Watch Ultra session.

## Exact Next Actions

1. Close R2's remaining evidence gaps: use GitHub Actions macOS simulator for
   same-round Half Moon Bay iOS request/first-frame/screenshots, confirm the
   displayed club-distance/source values against the completed Web HMB evidence,
   then obtain owner approval of the cross-client screenshot comparison.
2. Keep production revision `6a6080c6...` unchanged until a deployment or
   synchronization operation is explicitly approved.
3. Run the P0/P1/P2 real-data evidence matrix, then resolve provenance and
   owner-approval gates before TestFlight.

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
