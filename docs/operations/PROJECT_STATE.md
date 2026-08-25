# Garmin AI Caddie Project State

> This is the short, durable execution state for the current product push.
> Long reviews and historical plans remain reference material; they are not the
> live task queue.

**Updated:** 2026-08-25 UTC
**Branch:** `codex/p0-p1-p2-checkpoint-20260823`
**HEAD:** `8a3ee8ba` (runtime-verified code baseline: `8a3ee8ba`)
**Release rule:** no TestFlight upload until every P0/P1/P2 release gate below
has runtime evidence and the owner approves the comparison.

## Objective

Close the smallest set of product and engineering gaps needed for a Garmin/S70
first round flow across Watch, iOS and Web: reliable start, live scoring,
course preparation, review, and synchronized history. Preserve existing working
code; do not restart the old multi-week plan tree.

## Current Slice

**`S1` — Sync provenance and resumable course delivery** (`in-progress`)

`W1` is closed with isolated current-head runtime evidence. The public service
still runs revision `6a6080c6...`; no production deployment or data
synchronization was performed. S1 is currently limited to a read-only audit of
sync provenance, resumable downloads, and real club-distance data.

Only one task may become `in-progress` at a time. Update this file before
starting the next slice.

## Task Ledger

These IDs persist across sessions and context compactions. They are the only
project-level task list; historical plans are reference material.

| ID | State | Scope | Exit evidence |
|---|---|---|---|
| `W1` | `done` | Watch lifecycle, independent discovery, offline/restart, and 41/45/49 mm behavior. | Run `32806892801` watch-runtime job succeeded at head `8a3ee8ba`: 41/45/49 mm captures, real Cypress 18-hole install/restore, same-round 1–18 journey, hole-1 history edit while live on hole 10, finish confirmation, 57 queued records acknowledged, remote finish success, plus Cancel recovery and abandon/tombstone markers. |
| `S1` | `in-progress` | Sync provenance, resumable background course download, real club-distance data, and Garmin-to-client consistency. | Metadata → preparing → precise → offline-installed is resumable and the real package distance table matches every client. |
| `R1` | `done` | Web map-first review editor/cache slice described above. | Focused tests plus remote add/drag/delete/reorder/save/reload evidence. |
| `R2` | `implementation-partial` | iOS/Web review parity, first-frame/cache, overlay-first layout, and unified trend entry after `R1`. | Half Moon Bay round-by-round facts and approved iOS/Web runtime screenshots. |
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

These are code/test facts, not proof of a physical Apple Watch Ultra session.

## Exact Next Actions

1. Finish the bounded S1 read-only contract/data-flow audit; identify the
   minimum implementation slice for resumable download and Garmin club-distance
   provenance before changing code.
2. Re-run Web live evidence through a stable, CORS-valid endpoint as part of
   the Web/R2 track; do not treat the failed Quick Tunnel as product proof.
3. Keep production revision `6a6080c6...` unchanged until a deployment or
   synchronization operation is explicitly approved.
4. Run the P0/P1/P2 real-data evidence matrix, then resolve provenance and
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
  returned 200. The public backend remains `6a6080c6...`; the current-head
  candidate was used only through an isolated, now-cleaned test route.
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
