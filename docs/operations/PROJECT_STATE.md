# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved verbatim in dated docs/archive files.

**Updated:** 2026-10-12 01:18 UTC
**Canonical baseline:** main 3e785b14 / product merge 95b5694e (#419)
**Current slice:** WATCH417-ELEMENT-AUDIT — in-progress

## Current state

- Owner widened #417 via comments 6111380071 / 6111790655: all Watch
  screens/states, element frames/fonts, five real gestures, 20/60 pt drags,
  adversarial input, real-round tempo, physical scale and S70/Golfshot comparison.
- Both comments read completely. Acknowledgement/reason for issue-only wake-up
  miss posted as issue comment 6114726773. PR-only waiting is not the active slice.
- Test scaffolding only. Claude implements production fixes after triage.
- #419 exact head 4cfb1588356cdde8aff5764616137af0a1b5a4ab merged as 95b5694e;
  full-screen putts/penalty pickers are the required current product baseline.
- #418 remains draft on codex/watch417-simulator-audit. Existing editing worktree
  is reused; no second implementation checkout. Exact pushed head
  1ef62984a00f30d67f34828183120e86954b79db corrects draft telemetry, transient
  capture, honest latency labels and expands to 16 UI methods. Eight remote
  preparation checks pass. Run 38182426066 failed before any UI methods:
  injectedAOD assignment was in teardown instead of launch (fixed locally).
  Full run 38182935895 completed: all faces ran 16 methods with zero skips;
  41/46/49 mm pass/fail 11/5, 14/2, 12/4; 252/343/334 PNGs. All artifacts,
  calibrated physical images and motion recordings downloaded remotely.
  Current scaffold fixes predicate sampling, immutable frame snapshots,
  page-specific viewport telemetry and adds immediate first-try shot/undo.
  Four-method control-recheck run 38188153210 is dispatched at
  8e6feee6c4e2e771f4675695bc31ba440b51878d; it is explicitly partial coverage.
  Nine remote preparation checks and 2 YAML / 30 Bash sections pass.
  Raw 0/5 flags cannot be product claims when recorded final values changed
  correctly. Preserve raw evidence and publish adjudication separately.
- Control recheck is terminal: 41/46/49 mm 3/1, 2/2, 4/0 pass/fail,
  four methods each, no skips; 51/39/63 PNGs. Exact head remains 8e6feee6.
  P1 manual-shot 49 mm 0/5 versus 41/46 mm 5/5 posted in #6115815445.
  Rechecked plan switch 5/5; page swipe 0/5 and zoomed hazard pan changes to
  green across all faces. 49 mm picker tap/20/60 pt/offset/double/edge 5/5;
  41/46 mm live-frame collection races auto-close, still a harness gap.
- Required CI 38188154661 failed only the exact-string viewport contract
  after DEBUG auditTag was added. A local one-line prefix assertion fix is
  pending remote verification, real audit/scaffold commit and push.
  Native CI 38188154664 terminal result is still to be collected via waiter.
- New scaffold caches measured picker frames for pointer gestures and adds
  every putts/penalty start/target pair. picker-recheck runs only methods 11/18.
  Remote preparation: 10 tests pass (0.480 s), 2 YAML / 30 Bash sections valid.
  Viewport contract fix verified. This is real scaffold work, not CI bookkeeping.
- Expanded runs 38179866784 / 38180807102 failed compilation, zero UI tests.
  String.putts / unsupported app.suspend were corrected. Preserve failures as
  harness diagnostics; neither is evidence of a product defect.
- Earlier flow audit at 715b6ddb and comment 6110771081 are historical evidence.
  Do not repeat its product verdicts without rechecking post-#419 source.
- #404–#416 review/deployment and Build 86 upload are already complete.

## Unfinished queue

- WATCH417-ELEMENT-AUDIT — in-progress: finish harness checks, dispatch the
  exact pushed head, collect all three faces, inspect physical aids and report
  per-screen tables plus distinct evidence-backed P1–P3 findings on #417.
- PR-418-AUDIT-SCAFFOLD — evidence-open: keep draft; coverage collection is
  separate from a product UX pass. Failures/coverage gaps must remain visible.
- PR-FEEDBACK-CONTINUOUS — queued: resume deduplicated feedback after #417 work.
- NATIVE-FIXTURE-LAYOUT-STABILITY — queued: nonblocking #416 variation.
- IOS-STATUS-CONTRAST — queued: nonblocking dark status/navigation text.
- OWNER-DEVICE-BUILD86 — evidence-open: physical paired-device validation.

## Verification boundaries

- DEBUG telemetry must read draftScore/draftPutts/draftPenalty while editing,
  not saved hole values. No product timers, hit targets or gestures changed.
- Picker idle is real 4 s / settled 2.5 s. Inventories and five-attempt trials
  are separate; explicitly count reopens and invalid preparations.
- XCTest action time is synchronization overhead, not visible feedback latency.
  Physical Crown, wrist/AOD sensing, OLED/sunlight, paired notifications,
  GPS accuracy, battery and real WCSession timing cannot be proved by simulator.
- Original-pixel captures and mm/DPI/calibration aids support scale inspection;
  distinguish printable geometry from actually wearing a watch.
- Audit fixture repeats a mapped review hole; it cannot prove all-course maps
  or caddie algorithm quality. No new TestFlight upload requested.

## Live verification baselines

- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6: health,
  history, sync, precise prep/topo gates passed; manual sync ok/done.
- #404/#406: 237 related tests, five existing geometry skips; nine-hole workload
  35.49 s -> 22.93 s; two render workers; deployment report retained.
- Internal TestFlight 0.1.0 (86): independently Apple-checked VALID /
  IN_BETA_TESTING. No physical-install claim.
- #419 review: required/Native 38159377877 / 38159377871; PASS 6112715912.
- Old flow audit: 38158983899, Xcode 26.3 / watchOS 26.2, 41/46/49 mm,
  ten methods each, zero skips, 8 pass / 2 fail each. Current recheck required.

## Owned resources and cleanup

- Local audit editing worktree:
  /home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011
  Codex, created 2026-10-11 08:30 UTC; expiry 2026-10-18 08:30 UTC.
- Persistent evidence:
  /home/jason/garmin-ai-caddie-data/operations/watch417-simulator-audit-20261011
  /home/jason/garmin-ai-caddie-data/operations/watch417-run38180807102/artifacts
  /home/jason/garmin-ai-caddie-data/operations/pr419-4cfb1588-20261011
  /home/jason/garmin-ai-caddie-data/operations/watch417-wide-audit-20261012
  (all 38182935895 artifacts, immutable raw JSON, adjudicated summary and
  fetched public comparison references; analysis helper retained there).
  Build failures and blocking-wait logs are retained under operations.
- Old /dev/shm verification snapshot and local contact-sheet copies removed
  2026-10-11 15:52 UTC. #419 screenshot copies moved to Trash.
- No live audit service, container, tunnel, timer or dependency environment.
  All CI/download/reference terminal handles are closed, including
  35376 / 49053 / 30556 / 88561. No pending waiter. Recheck artifacts are at
  operations/watch417-control-recheck-20261012. Local image-review copies under
  /tmp/garmin-watch417-images-20261012-GCqa8Y, owned by Codex; expiry
  2026-10-13 08:30 UTC or after review. Preserve remote originals.
  no feedback waiter. gh-feedback timer/cursor unchanged.
- Picker verification snapshot /dev/shm/garmin-ai-caddie-watch417-picker-verify-20261012
  removed after checks and persistent manifest/log retention. Temporary --rm
  container garmin-watch417-picker-verify-20261012 exited 0; no new resources.
  Evidence root operations/watch417-picker-recheck-20261012 is persistent.
- Shared remote checkout
  /home/jason/codex-runs/garmin-ai-caddie-claude-takeover-20261005 untouched.
- Pre-expansion state retained verbatim in
  docs/archive/PROJECT_STATE-2026-10-11-before-element-audit.historical.md.
  Historical archives are non-authoritative and are not startup reading.

## Next action and stop conditions

1. Verify the local contract fix remotely and supplement 41/46 mm picker
   gestures using cached coordinates, never changing production timers.
2. Preparation snapshot (56 KiB) was removed after eight passing checks and
   persistent log/manifest retention. Focused snapshot (124 KiB) is removed
   after nine checks / workflow validation and persistent manifest retention.
3. Finish every contact-sheet/physical-size review and source-font inventory,
   fetch valid S70 scoring/hazards and Apple Workout comparison references,
   publish per-screen tables and distinct P1-P3 findings on #417.
4. Keep #418 draft until coverage and triage are sufficient; return to feedback
   after this slice completes. Never commit CI-result bookkeeping alone.

Continuous review cutoff: 2026-10-13 08:22:16 UTC, or earlier after 48 hours
without external PR events and no open PRs. The explicitly requested #417
audit remains authorized; an owner stop instruction overrides ongoing work.
Every GitHub comment/review ends _Generated by Codex_; every Codex commit
ends Generated-by: Codex. Keep this file <=200 lines and archive historical
detail verbatim by date.

Publication note: docs/archive is Git-ignored. Force-add only the three owned
short historical ledgers (before-element-audit, before-control-recheck and
before-picker-coordinate-recheck)
with the real audit report commit; do not stage all historical files.
