# Garmin AI Caddie Project State

> This is the short, durable execution state for the current product push.
> Long reviews and historical plans remain reference material; they are not the
> live task queue.

**Updated:** 2026-08-24 UTC
**Branch:** `codex/p0-p1-p2-checkpoint-20260823`
**HEAD:** `edf41054`
**Release rule:** no TestFlight upload until every P0/P1/P2 release gate below
has runtime evidence and the owner approves the comparison.

## Objective

Close the smallest set of product and engineering gaps needed for a Garmin/S70
first round flow across Watch, iOS and Web: reliable start, live scoring,
course preparation, review, and synchronized history. Preserve existing working
code; do not restart the old multi-week plan tree.

## Live Queue

| Track | State | What is true now | Exit evidence |
|---|---|---|---|
| P0 Watch | `evidence-open` | Provisional next-tee shot completion is idempotent (`10d56855`). Core lifecycle, independent discovery, offline/restart, and 41/45/49 mm runtime flow are not fully proven. | One real round (or simulator equivalent) covering start, hole advance/Cancel, edit, finish/recover, and all three sizes. |
| P1 Sync / Prep / Caddie | `ci-green-runtime-open` | Strategy tiers are deduplicated and ordered (`ca3fa89`). Web prep has the four-state readiness gate (`a1b88a2e`); backend, navigation and visual fixtures are aligned (`46aad448`, `2ca27720`, `edf41054`). CI `32690671928` is green. Production sync provenance and durable background download remain open. | Metadata → preparing → precise → offline-installed is resumable; real package distance table and Garmin-to-client sync are consistent. |
| P2 Review / Stats | `implementation-partial` | FIR unknown-token semantics merged (`bbc865af`). iOS review editing is largely present; Web editor, first-frame/cache, overlay-first layout, and cross-surface trend entry still need closure. | Half Moon Bay round-by-round facts plus iOS/Web runtime screenshots and edit/save/reload evidence. |
| Release | `blocked` | Native runtime and production provenance evidence are incomplete. | P0, P1 and P2 gates above, then explicit owner approval. |

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

These are code/test facts, not proof of a physical Apple Watch Ultra session.

## Exact Next Actions

1. Keep the CI-green batch intact; do not add unrelated fixture or UI changes
   before the next evidence slice.
2. Implement one P2 Web review editor/cache slice, then one evidence run; do not
   combine unrelated UI redesign work into that slice.
3. Run the P0/P1/P2 real-data evidence matrix for the two Half Moon Bay rounds.
4. Resolve remaining native runtime/provenance gates, obtain owner approval, and
   only then prepare TestFlight.

## Open Blockers / Facts

- Local machine is an editing/control plane; builds, Xcode, Playwright and
  other heavy work run on homeserver or GitHub Actions.
- No immutable production revision has been approved for a deployment/sync
  operation; do not trigger production synchronization as a test.
- The focused green baked fixture is still 1024 px; do not stretch it and call
  it a 1280 px evidence asset.
- Existing user files `.codex-tmp/` and
  `.mockups/watch-shot-tracking.html` are untracked and must be preserved.
- Keep historical Claude/superpowers worktrees unless a separate allow-list
  cleanup is explicitly authorized.

## Operating Rules

- At most one modifying implementation agent and one read-only review snapshot.
- Every delegated task returns its worktree, commit, tests, resources and
  cleanup result. Temporary resources are removed by their creator.
- Update this file only when a task changes state or the next action changes.
  Add a dated one-line entry below; do not paste full command logs here.
- After context compression, read this file first, then run lightweight
  `git status`, `git log -8`, and agent-status checks. Do not recreate a new
  master checklist from memory.

## State Changes

- 2026-08-24: Integrated `bbc865af`; started the bounded Web prep readiness
  task. Echo-style shell output is not a project task or process.
- 2026-08-24: Integrated `a1b88a2e`; CI `32689037776` passed Docker but exposed
  one Web fixture failure and two backend assertion failures. Fixes are queued
  one modifying agent at a time.
- 2026-08-24: Integrated backend test-contract fix `46aad448` and Web fixture
  fix `2ca27720`; awaiting a matching green CI run.
- 2026-08-24: Integrated visual fixture correction `edf41054`; CI
  `32690671928` at `b6ecee8f` is green across all three jobs. The code batch is
  closed; runtime/product evidence remains open.
