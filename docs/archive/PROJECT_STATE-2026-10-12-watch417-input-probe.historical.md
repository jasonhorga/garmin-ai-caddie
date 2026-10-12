HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Verbatim live ledger before input-probe adjudication and capability supplement.
Use docs/operations/PROJECT_STATE.md for current status.

# Garmin AI Caddie Project State

> Short authoritative live ledger. History is preserved in dated archives.

**Updated:** 2026-10-12 04:48 UTC
**Canonical baseline:** main 3e785b14 / product merge 95b5694e (#419)
**Current slice:** WATCH417-ELEMENT-AUDIT — in-progress

## Current state

- #417 widened owner audit (6111380071 / 6111790655) read and acted on.
  Scaffolding only; Claude implements product fixes. No new TestFlight.
- Substantive 35-finding report (2 P1 / 16 P2 / 17 P3) published in fdebb6f1:
  docs/reviews/2026-10-12-watch417-wrist-ux-audit.md; issue comment 6117399134.
  Twelve screen tables, gesture rates, task counts, physical/reference review
  and hardware gaps are in that report; do not recollect completed evidence.
- #418 remains draft on codex/watch417-simulator-audit. Raw W/C/I/M evidence
  is immutable; collection pass is not product UX approval.
- #420 production head bd2ec304 reviewed; required/Native CI green,
  126 mobile contracts pass (13.429 s), nine collector regressions pass
  (1.207 s). Native receipt 10c949ce parents 3e785b14 + bd2ec304 checked;
  47 Watch and 97 iOS screenshots inspected.
- #420 runtime 38202658425 at test integration fd40e821 failed 49 mm:
  first pointer taps center x3 / right-offset8 pt x2, 41/46 mm 5/5 with
  immediate undo 5/5; 49 mm 0/5, shots=0 and pending=false before/after.
  Supplemental 20-second walking fix accepted on41/46 but fails49;
  remaining three fix states not executed49. Transient-message AX evidence
  cannot establish absence of feedback; real haptics remain unproved.
- P1 review posted on #420 as 6117777245. HOLD MERGE; no timer/hit-area/gate
  production edits or injected pending in the actual-tap evidence.
  Tracked review: docs/reviews/2026-10-12-pr420-bd2ec304-first-tap-review.md.
  Review checkpoint retained on #418 at 477eaab6; reuse temporary
  integration ref for opt-in DEBUG raw-event/action probe (6117411661).

## Unfinished queue

- WATCH417-ELEMENT-AUDIT — in-progress: diagnose49 root-button input with
  test-only callback/fix trace; explicitly recheck hazard visual-center and
  boundary taps. Continue remaining runtime gaps and numbered Claude feedback.
- PR-420-MANUAL-SHOT — blocked: bd2ec304 fails first-tap49 validation;
  await Claude fix, then review exact new head and repeat five real taps/undo.
- PR-418-AUDIT-SCAFFOLD — evidence-open: keep draft; trace is evidence only.
- PR-FEEDBACK-CONTINUOUS — queued: resume deduplicated feedback after audit.
- NATIVE-FIXTURE-LAYOUT-STABILITY — queued: nonblocking #416 variation.
- IOS-STATUS-CONTRAST — queued: nonblocking dark status/navigation text.
- OWNER-DEVICE-BUILD86 — evidence-open: paired physical-device validation.

## Retained verification baseline

- Immediate picker run38194936812 / 7155607d: repeated gestures and Done
  5/5 per picker/face; 183/183 valid start/target pairs within two gestures.
  Idle4.5 s closes both on all faces. Old timeout-raced failures excluded.
- Map run38197809368 / 32b45ba6: unzoomed page swipe0/5 all faces;
  zoomed hazard pans0/5 all faces, up changes to果岭/down to方案.
  Zoomed plan pans0/5 all faces, 15 settled pairs show zero map movement.
  Hazard-next element taps41=5/5,46/49=0/5; explicit center still pending.
  Latest plan chip41=4/5,46/49=5/5. Do not extrapolate to other gestures.
- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6;
  health/history, incremental sync, prep/topo gates passed; sync ok/done.
- #404/#406:237 related tests, five existing skips; nine-hole workload
  35.49 s ->22.93 s, two render workers; deployment evidence retained.
- Internal TestFlight0.1.0 (86): Apple VALID/IN_BETA_TESTING verified.
- #419 reviewed/merged; PASS6112715912, merge95b5694e.

## Evidence boundaries

- AX content is not padded hit bounds; explicit visual-center/boundary input
  and callback dispatch must be distinguished from stale GPS and undo timeout.
- XCTest action durations include synchronization; uiFeedbackMs=null is not
  a measured300 ms pass. Short-lived GPS message/haptic evidence remains open.
- Crown/gloves/wet fingers/wrist/AOD/sunlight/GPS/battery/notifications/
  WCSession require hardware. Calibrated mm exports are rendered review aids.
- One factual mapped-hole fixture cannot establish all-course caddie quality.

## Owned resources and cleanup

- Editing worktree:
  /home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011;
  Codex, createdOct11 08:30 UTC, expiryOct18 08:30 UTC. One checkout reused.
- Temporary ref codex/pr420-wrist-recheck-20261012 at fd40e821;
  expiryOct13 08:22 UTC or after diagnosis. No extra implementation checkout.
- Input-probe source d0a0cf53 pushed; runtime38205917630 dispatched.
  Nine collector regressions pass (0.777 s),126 mobile contracts pass
  (15.607 s). Initial mountpoint error retained as setup diagnostic.
  Input-probe read-only snapshot:
  /dev/shm/garmin-ai-caddie-watch417-input-probe-20261012;
  31 MiB removed after checks/open-file check; named --rm container
  garmin-watch417-input-probe-20261012 gone. Manifest recorded before creation;
  persistent evidence root operations/watch417-input-probe-20261012.
- Persistent evidence under /home/jason/garmin-ai-caddie-data/operations:
  watch417-simulator-audit-20261011, pr419-4cfb1588-20261011,
  watch417-wide-audit-20261012, watch417-control-recheck-20261012,
  watch417-picker-recheck-20261012, watch417-immediate-picker-20261012,
  watch417-map-recheck-20261012, pr420-bd2ec304-20261012.
  Originals/artifacts/manifests/references/diagnostics/waiter logs retained.
- PR420 read-only /dev/shm snapshot removed after checks/open-file check
  (30 MiB); named --rm container gone. Earlier mount failures are retained
  environment diagnostics. Prior audit snapshots also removed.
- Local /tmp/garmin-watch417-images-20261012-GCqa8Y contains viewed copies;
  expiryOct13 08:30 UTC or after review; remote originals retained.
- One delegated blocking waiter: wait_release_38083089271 waits only for
  input-probe38205917630; main continues independent audit work. No other
  live service/tunnel/container/volume/port/dependency environment.
  Agent wait_release_38083089271 completed38202658425 wait; handle88036
  closed1 with failure summary retained. Publish/switch handle69759 closed0.
  Shared checkout, gh-feedback timer and feedback cursor unchanged.
- History archived verbatim in
  docs/archive/PROJECT_STATE-2026-10-12-pr420-first-tap-review.historical.md.

## Next action and stop conditions

1. Build opt-in DEBUG simulator input probe without adding SwiftUI gesture
   recognizers. Tap root controls center/vertical +/-8 and16 pt on49,
   explicitly probe hazard-next at2x on46/49, with41 and trace-off controls.
   Preserve dispatch-point/action/fix/model receipts; Claude fixes production.
2. Process Claude replies/new #420 head once; exact-head CI/Native review
   and genuine five first taps required. Keep #420 unmerged meanwhile.
3. Keep #418 draft until coverage/triage sufficient. Use one same-turn
   blocking feedback waiter when independent audit work is exhausted.
   Ignore Codex bookkeeping CI; no ad-hoc main-thread status polling.

Continuous cutoff: 2026-10-13 08:22:16 UTC, or earlier after48 hours without
external PR events and no open PRs. Explicit #417 audit remains authorized;
owner stop overrides work. GitHub comments end _Generated by Codex_;
Codex commits end Generated-by: Codex. Ledger<=200 lines; dated archives
preserve historical detail verbatim.

