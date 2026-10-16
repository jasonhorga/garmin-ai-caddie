HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved verbatim in dated `docs/archive/` files.

**Updated:** 2026-10-14 21:14 UTC, #425 exact-head review posted; merge blocked
**Canonical baseline:** main `128798fd` (Build 87 source `bfe850b7`)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and unfinished work

- `PR-425-COLD-WATCH-MAP` — `evidence-open`: exact head
  `8747966053271be197e15a269d287d6f92d6621a`; ordinary CI
  `38633795787`, Native Mobile CI `38633795743`, and cold-start
  `38632757426` are green. The 97 iPhone/design + 47 Watch screenshots
  match the reviewed #424 baseline. The nullable-image and
  geometry/topo/generation fixes are present, but review
  `pullrequestreview-5524736287` records two P1 blockers:
  1. Watch decodes only `w/h/route` and drops non-empty
     `map.overlay.surfaces` (bunker/lake/fairway polygons); its fixture has
     only an empty green surface.
  2. A player bearer receives 403 from `install/status`; the Watch converts
     that to nil and forces another full package fetch, so the status hint
     never works for the release auth model.
  Re-review comment `6179488143` answers Claude's timing questions: 42231 was
  genuinely cold for geometry/topo (the first 2026 course asset was created
  at 20:36:12.521Z; first vector-prep output at 20:36:18.480Z; first topo at
  20:36:21.297Z; all nine by 20:37:00.743Z). The `install_before: none` field
  is not evidence because the player status probe returned 403. Production
  logged that 403 repeatedly at 20:36:12.808Z, 20:36:22.291Z, 20:36:32.419Z,
  and 20:36:47.084Z.
  Do not merge until non-empty surface rendering and 403 behavior tests pass
  on a new exact head, followed by Native artifact and cold-start checks.
- #425 incident evidence: timeline comment `6173093641` records front-nine
  ready at about 76 s and all 18 at about 125 s; both preceded the final
  Watch retry. Server prep has no raster gate. Present loopback first package
  was 110.098 s, warm repeat 3.255 s. Prior P1/P2 comments are `6172993813`
  and `6173026392`; hold comment `6173187157` remains historical context.
- `BACKEND-NEARBY-MAP-STARTUP` — `evidence-open`: #427 merged/deployed at
  `128798fd`. Public cold 28214 first drawable package was 6.453 s and
  nearby 28242 was 3.241 s through the homeserver Funnel; low-priority
  prewarm journals for all 17 nearby courses were verified. Owner target is
  seconds for nearby courses and under 30 s for an unseen course; Claude still
  owns the Watch start-screen download/vector integration in #426.
- #404–#416 reviewed/merged. #417 remains an evidence issue with findings
  posted; #418 is draft/evidence-open; #420 awaits five 49 mm first-try
  transitions; #421 awaits external review. #422 remains draft/test-only and
  must not be merged. #423 (`46f9c8ff`) and #424 (`6bb684fa`) are merged.
- Build 87 iOS/watchOS 0.1.0 (87) is Apple-verified and already in the
  internal group. Do not redispatch duplicate release requests.

## Live verification baselines

- Production revision `128798fd8fd638227c8668a05de02c15eb3787a7`, container
  `aicaddie-release-128798fd-production-20261014`, public
  `https://caddie.taile36706.ts.net`; matching sync image exists. Health,
  history, sync, prep, and topo gates passed; manual incremental sync ended
  `sync ok` and `done`.
- #427 exact-head full CI `38612115537` passed at `b9cf540a`; production
  image verification passed with 258 tests and 2 data-dependent skips, plus
  39 supplemental map/auth tests.
- Cold 28214 had no release/ZIP/mesh before start: release/Tee 0.674 s plus
  public drawable package 5.779 s; immediate public repeat 0.224 s. First
  map had route, surface rings, F/M/B, GPS, geometry 1/9 and topo 0/9.
  These are homeserver-to-Funnel timings, not wrist/Tokyo/Austria timings.
- Internal TestFlight: CD `38529901074`, Apple `38532148335`,
  `VALID/IN_BETA_TESTING`; source `bfe850b7`, backend `cbc17f4e` for Build
  87. IPA SHA-256 is
  `b847f3fdc2c461f176494c732f92a32322b0bdf3da3a3fc313b2bbc782596b0a`.

## Owned resources and cleanup

- Exact-head #425 snapshot
  `/dev/shm/garmin-ai-caddie-pr425-87479660-20261014` was removed after
  review. The prior snapshot and test container are also closed. No service,
  port, tunnel, dependency environment, or production configuration was
  created or changed by this review. Persistent evidence remains at
  `/home/jason/garmin-ai-caddie-data/operations/pr425-c4fdddc9-20261014`.
- Existing Codex review worktree:
  `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011`,
  expires 2026-10-18 08:30 UTC. Historical untracked `.codex-*` evidence is
  retained; it is not a cleanup target.
- Feedback terminal `19026` retains the cursor; `79608` and `50622` were
  already deduplicated. Do not create another monitor, edit the cursor, or
  use ad-hoc CI/ps polling. All Build 87 release/Apple waiters are terminal.
- Persistent evidence: #424 native artifacts under
  `/home/jason/garmin-ai-caddie-data/operations/pr424-5ac993ef-native-20261013`,
  release evidence under
  `/home/jason/garmin-ai-caddie-data/operations/release87-20261014`, and
  backend deployment evidence under
  `/home/jason/garmin-ai-caddie-data/operations/map-startup-20261014`. The
  #425 cold-start artifact is retained at
  `/home/jason/garmin-ai-caddie-data/operations/pr425-c4fdddc9-20261014/watch-cold-start-38632757426`.

## Next action and stop conditions

1. When Claude posts a new #425 head, inspect the non-empty polygon path and
   the player-token 403 fallback, run exact-head tests, wait for Native CI,
   inspect its artifacts, and rerun cold-start timing. Merge/delete only when
   both blockers are closed.
2. Continue #426 nearby Watch integration and stale-course identity checks;
   preserve active-play priority and player isolation. Keep the backend
   deployment evidence and public timing limitations explicit.
3. Resume the retained feedback waiter in the same control turn; process each
   external event once and ignore CI caused only by Codex state/docs commits.
   Do not create CI-result-only commits.
4. End this goal at 2026-10-09 23:59 UTC (already elapsed in this simulated
   timeline), or earlier after 48 hours with no new external PR events and no
   open PRs, or on explicit owner stop. Every Codex GitHub comment/review ends
  `_Generated by Codex_`; every Codex commit ends `Generated-by: Codex`.
