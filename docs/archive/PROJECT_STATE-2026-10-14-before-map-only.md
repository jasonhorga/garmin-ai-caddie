HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved verbatim in dated `docs/archive/` files.

**Updated:** 2026-10-14, nearby/cold-map backend implementation
**Canonical baseline:** main `4e2d938a` (Build 87 source `bfe850b7`)
**Current slice:** `BACKEND-NEARBY-MAP-STARTUP` — `in-progress`

## Current state

- #404–#416 reviewed and merged; #417 remains an evidence issue with findings
  already posted. #418 remains draft/evidence-open. #420 remains
  evidence-open for the 49 mm first-tap rail. #421 awaits external review.
- #422 is draft/test-only and must not be merged. Its exact-head review is
  complete; do not treat prototype callbacks as production evidence.
- #423 was reviewed, fixed, merged as `46f9c8ff`, and its branch was deleted.
- #424 passed the P2 recheck and was merged as `6bb684fa`; implementation
  branch `claude/watch-production-ia-20261013` and the temporary audit branch
  were deleted. Pass comment:
  https://github.com/jasonhorga/garmin-ai-caddie/pull/424#issuecomment-6154831834.
- The merged #424 source covers revision acknowledgement, phone tee-landing
  fallback, inline 开球左/中/右, and the 45 mm score-row hit-target fix.
  No unresolved P1/P2 finding remains for #424.
- Internal iPhone + Watch Build 87 is uploaded and Apple-verified, both
  0.1.0 (87). #424 release replies `6162864583`, `6163465026`,
  `6164079823` are handled; do not redispatch on duplicate release requests.
  Full diagnosis/package/device handoff: `2026-10-14-internal-testflight87.md`.

## Unfinished queue

- `BACKEND-NEARBY-MAP-STARTUP` — `in-progress`: issue #426 records the
  owner target (nearby map in seconds; unseen usable map <30 s) and backend/
  Watch ownership. Implement low-priority regional all-hole prep/topo within
  30 km and first-package priority-hole vectors before raster work. Verify
  cold, warm and contended timings; retain ordered loops, Tee, release binding
  and player isolation. Claude owns Watch vector rendering/nearby downloads.
  Implementation now queues all nearby rows, reserves a foreground geometry
  lane, yields the durable coordinator after 1 nearby/2 selected holes, and
  persists factual route/surface/FMB vectors independently of rasters. Latest
  targeted tests: 229 pass (2 data-dependent skips). Genuine cold 28263:
  vector ready 6.844 s, drawable first package 14.125 s, repeat 0.615 s;
  nine-hole full install 63 s after enqueue. Contended 30189 run is in flight.
- `PR-425-COLD-WATCH-MAP` — `evidence-open`: exact head `c4fdddc9`;
  ordinary and Native `38594117897` green; 126 contracts + 12 parity passed.
  All 47 Watch + 97 iPhone/design PNGs match the reviewed #424 baseline.
  P1 `6172993813`: route-only map.image null rejected by required Watch String.
  P2 `6173026392`: status-only retries miss geometry/generation progress.
  Timeline `6173093641`: front nine ready 08:15:54 (~76 s); all 18 ready
  08:16:55 (~125 s from whole-course enqueue). Both precede final Watch retry.
  Server prep has no raster gate; original response bodies/start times absent.
  Present loopback first package 110.098 s; warm repeat 3.255 s.
  Hold comment `6173187157`; Claude implements fixes. Do not merge until
  blockers and exact-head gates clear. Detailed evidence/limitations:
  `2026-10-14-pr425-cold-watch-map-review.md`.
- `PR-418-AUDIT-477EAAB6` — `evidence-open`: hold the draft for the
  author's P1/P2 fixes and exact-head rerun.
- `PR-420-W01-49MM` — `evidence-open`: 49 mm first manual-shot rail still
  needs five successful first-try transitions.
- `WATCH-IDLE-PHYSICAL-ACCEPTANCE` — `evidence-open`: owner device
  validation remains required for #423.
- `PR-421-FEEDBACK-DELIVERY` — `evidence-open`: awaiting external review.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: process external events once,
  ignore Codex-owned CI/comments, and retain one same-turn feedback waiter.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` and `IOS-STATUS-CONTRAST` —
  `queued`; `OWNER-DEVICE-BUILD87` — `evidence-open`: Crown score row,
  45-min idle pause, <30-min relaunch, second-nine sync, tee preselection.

## Exact-head #424 evidence

- Fixed head `5ac993ef8970db809390d19e7d27ba92c8d368b0`: ordinary CI
  `38446895152` and Native CI `38446895372` passed.
- Native artifacts `11839047414` (97 design/iPhone snapshots),
  `11838888102` (47 Watch snapshots), and `11839187866` (build evidence)
  were downloaded and inspected. Only the score-row pixels changed as
  expected; no clock, safe-area, crop, or layout regression appeared.
- Test-only harness `799762d0`, runtime `38453004091`, evidence
  `/home/jason/garmin-ai-caddie-data/operations/pr424-5ac993ef-native-20261013`.
  Fresh-launch production taps: 41/42/45/46/49 mm each 390/390.
- The fixed 45 mm `fairway-open` first tap has AX frame
  `[10,174,86,37]`, interactive bottom `211`, and succeeds on attempt 1.
  First-try manual record and undo are 10/10 on every face; Watch→phone
  second-nine sync is 2/2. Native logs report the complete audit green.
- Simulator evidence still does not establish physical Crown, GPS, WCSession
  transport, OLED brightness, or wrist-motion behavior.

## Live verification baselines

- Production API/sync baseline: `cbc17f4e`; health, history, sync, precise
  prep and topo gates passed; manual sync ended `sync ok` and `done`.
- #404/#406 deployment evidence remains recorded: 237 related tests and
  nine-hole workload 35.49 s → 22.93 s.
- Internal TestFlight 0.1.0 (87): CD `38529901074`, Apple `38532148335`,
  `VALID/IN_BETA_TESTING`, existing internal group explicitly contains 87.
  Source `bfe850b7`, backend `cbc17f4e`, IPA provenance/upload flags match.
- Build 87 signed IPA SHA-256:
  `b847f3fdc2c461f176494c732f92a32322b0bdf3da3a3fc313b2bbc782596b0a`.

## Owned resources and cleanup

- #425 read-only snapshot `/dev/shm/garmin-ai-caddie-pr425-c4fdddc9-20261014`
  was removed after evidence was saved; test container auto-removed. Health 200.
  No service, port, tunnel, environment or production configuration changed.
  Persistent evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr425-c4fdddc9-20261014`.
  Manifest/scripts/comments retained there; cleanup receipt closes this review.
  Prior live/in-flight ledgers preserved verbatim in dated 2026-10-14 archives.
- Persistent #424 evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr424-5ac993ef-native-20261013`
  and `/home/jason/garmin-ai-caddie-data/operations/pr424-5ac993ef-native-ci-20261013`.
  Temporary harness branch is deleted; no container, service, tunnel, port,
  volume, or dependency environment was created by this recheck.
- Review worktree:
  `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011`,
  Codex-owned, back on `codex/pr424-production-harness-20261013`, expires
  2026-10-18 08:30 UTC.
- That clean-tracked worktree is now reused for backend implementation on
  `codex/backend-nearby-map-startup-20261014`, owner Codex, created
  2026-10-14, expires 2026-10-21. Historical untracked audit controls remain.
- Backend verification snapshot `/dev/shm/garmin-ai-caddie-map-startup-20261014`
  is active/read-only, expires 2026-10-15. Persistent evidence and manifests:
  `/home/jason/garmin-ai-caddie-data/operations/map-startup-20261014`.
  Test containers are auto-removed. Probe container
  `codex-map-startup-probe-20261014` is in-flight (terminal `27283`), reuses
  the existing API image and protected private volume; no service, port, DB
  migration, dependency environment or token clone. Verification journals
  live under evidence/jobs, isolated from production jobs. Preserve new course
  assets; drain/cancel only verification regional workers when probe ends.
- Existing untracked `.codex-*` evidence is historical and must remain.
  Archives for this closeout are
  `docs/archive/PROJECT_STATE-2026-10-13-pr424-before-close.md` and
  `docs/archive/2026-10-13-pr424-review-6eef9e13-before-close.md`.
- Feedback `19026` returned the already-reviewed c4fdddc9 Native CI event;
  deduplicated. Terminal `85049` continues the untouched cursor. No second
  monitor. All Build 87 release/Apple waiters returned terminal conclusions.
- Build 87 persistent evidence:
  `/home/jason/garmin-ai-caddie-data/operations/release87-20261014`.
  Release controls are backed up there and closed with checksums/allow-list.
  Used existing API Python/token without logging credentials; no new
  container, dependency environment, port, service, tunnel or worktree.

## Next action and stop conditions

1. Implement and verify #426 backend cold/nearby map path, publish measured
   phase timings, and deploy the verified API plus matching sync image.
   Collect contended probe `27283`, push implementation PR, wait exact-head
   full CI, then complete deployment/public readiness and warm/cold probes.
2. On #425 author fixes, recheck null-image decode plus real upgrade progress,
   geometry/generation polling, exact-head tests/Native artifacts; merge/delete
   the branch only when blockers clear. Re-delivered c4fdddc9 CI is handled.
3. End the goal after 48 hours with no external PR events and no open PRs, or
   earlier on an explicit owner stop instruction. Every Codex GitHub
   comment/review ends `_Generated by Codex_`; every Codex commit ends
   `Generated-by: Codex`.
