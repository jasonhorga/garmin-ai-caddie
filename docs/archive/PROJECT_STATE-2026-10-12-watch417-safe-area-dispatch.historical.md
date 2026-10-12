HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short authoritative live ledger. History is preserved in dated archives.

**Updated:** 2026-10-12 07:40 UTC
**Canonical baseline:** main 3e785b14 / product merge 95b5694e (#419)
**Current slice:** WATCH417-ELEMENT-AUDIT — in-progress

## Current state

- #417 owner audit6111380071/6111790655 and probe6117411661 read fully.
  Test scaffolding only; Claude implements product fixes. No new TestFlight.
- 36-finding report:2 P1/16 P2/18 P3;original35 published fdebb6f1/6117399134.
  docs/reviews/2026-10-12-watch417-wrist-ux-audit.md contains twelve element
  tables, physical/reference review and runtime/hardware boundaries.
- #418 draft codex/watch417-simulator-audit at477eaab6. Keep immutable W/C/I/M
  originals; collection green is not a UX pass. Temporary integration reused.
- #420 production bd2ec304; ordinary38190513760/Native38190513917 green.
  126 exact-source contracts passed;47 Watch/97 iOS images inspected.
  Review receipt10c949ce parents3e785b14+bd2ec304.
- First-tap run38202658425/fd40e821:41/46 centre/right8 pt5/5, immediate
  undo5/5;49 0/5,shots=0,pending=false.41/46 older-walking/cart/expired/no
  fix boundaries correct;49 remaining boundaries not run after failure.
- Probe38205917630/d0a0cf53 fully collected.30 traced trials/60 touches
  all at expected coordinates;41 menu trace-on cancelled, other terminals
  ended. Eight trace-off controls; full report:
  docs/reviews/2026-10-12-watch417-input-dispatch-probe.md.
- 49 rail centres reach app but NO menu/+ action. y-8/y-16 invoke correct
  actions; + sees eligible2.16/2.30 s fixes and enters pending.49 trace-off
  centres still fail. W01/W02 failure is before GPS/model; specific SwiftUI
  interception/recognizer cause not proved. Do not move only test coordinates.
- Hazard2x centres:41 action/transition,46/49 no action.46 y-8 works,
  49 centre/four offsets all fail. Success enters native pager subtree;
  failed points hit outer hosting view. Zoom/pan preserved in all trials.
- Published/deduped #4176118215955 and #4206118223337.
  #420 stale-fix source/contracts have no independent new blocker; original
  first-tap acceptance remains failed. HOLD claimed W01 fix/merge, await
  Claude correction or explicit split of stale-fix scope.
- Capability supplement method20 prepared:five fresh unsupported-setting
  centre/right8 pt taps per face, visible text/screenshot/off-state evidence.
  Nine collector tests1.681 s/126 mobile contracts15.960 s passed remotely.
- Capability38207654935/3d29e56e completed/collected. Each face remains
  correctly disabled/off5/5,visible reason0/5. All18 screenshots/contact
  sheet and calibrated mm/glare proxy checked. W36 P3 posted6118384187;
  docs/reviews/2026-10-12-watch417-capability-supplement.md. Capability is
  injected;not a hardware-support inference. No product edit.
- #417 delivery gap:installed collector excluded plain issues by default.
  Enabled existing per-instance GH_FEEDBACK_EXTENDED_EVENTS=1 at05:27;
  silent baseline confirmed05:30:42,complete scan/no failures05:39:02.
  Existing timer/toolkit/project waiter/cursor unchanged,no second monitor.
  Recovery:docs/operations/2026-10-12-watch417-feedback-collection.md.
  Catch-up read found no new external #417 reply. Issue delivery will be
  confirmed from completed feedback event;legacy summary may say prall.
- First feedback81342 returned old own #418 f0682202,already in477eaab6.
  Added attribution-based own comment/commit/head suppression in the existing
  waiter;unknown/Claude/unsigned messages retained,issue subject now explicit.
  Nineteen offline stream/provenance regressions passed30.108 s,zero skips.
  PR42162201d90 opened;CI38211176310 passed,await Claude review. #417
  notice6118815691 deduped;wait interface unchanged.
- Total-band supplement method21 prepared:90 fresh valid-start1..15 to
  target10..15 pairs per face,at most3 visible-band drags,then real Save and
  recorded total check;five separate16..20 boundaries. One trial/pair,
  not five-repeat acceptance. Production/scoring range unchanged.
  Collector/mobile contracts135 passed11.200 s,zero skips. Initial readonly
  data-lock setup8 errors retained;64 MiB container tmpfs corrected it.
  Native38214143769/437c6ca1 complete;68791 closed0,download44745 closed0.
  All285 pairs valid:10..15 targets within3 =72/90,77/90,77/90;
  actual saves for reached targets72/72,77/77,77/77. Capped16..20 stay15.
  Edge28pt short drag gives±2;matrix failures not classified before callback
  probe. #417 preliminary6119651495. Method22 prepared,not dispatched.
  Artifacts/source/analysis persistent;contact-sheet visual review partial.
- PRIORITY owner/Claude6119731901 at0727:root-before-ignore and hole-page
  safeAreaInsets/size plus full-width-row y cutoff. Method23 prepared;
  passive geometry/global frames/native window guide,temporary2pt button,
  0.5pt binary interval,five x points and five trace-off centre taps at each
  adjacent row. DEBUG simulation only;Claude owns layout fix. Do this next.
  #417 ack6119962970;135 collector/contracts passed21.259 s,zero skips.
- Feedback36723 ended gh_error061446 while skipping old own audit CI:
  one GitHub connection timeout,not external PR feedback. Catch-up0628
  found no new external #417/#420/#421 response;420 head unchangedbd2ec304.

## Unfinished queue

- WATCH417-ELEMENT-AUDIT — in-progress:remaining hardware/runtime gaps and
  numbered Claude feedback. Diagnostics/capability adjudication complete;
  wait for correction/new PR;do not recollect the same evidence.
- PR-420-MANUAL-SHOT — blocked:first-tap49 acceptance unresolved; stale-fix
  merits independent. Review exact new head or explicit scope correction.
- PR-418-AUDIT-SCAFFOLD — evidence-open:draft;diagnostics are not product fixes.
- ISSUE-FEEDBACK-WAITER — evidence-open:Claude review pending for operations
  PR421,head62201d90,branch
  codex/watch417-feedback-delivery-20261012,source matches09f8ecbb.
  Existing supported collection option enabled;owned runner updated after tests.
- PR-FEEDBACK-CONTINUOUS — queued:resume deduplicated feedback after audit.
- NATIVE-FIXTURE-LAYOUT-STABILITY — queued:nonblocking #416 variation.
- IOS-STATUS-CONTRAST — queued:nonblocking dark status/navigation text.
- OWNER-DEVICE-BUILD86 — evidence-open:paired physical-device validation.

## Retained verification baselines

- Picker38194936812/7155607d:repeated gestures/Done5/5 per picker/face;
  183/183 valid pairs within two gestures.4.5 s idle closes both. Exclude
  older timeout-raced failures; total-score full matrix still open.
- Map38197809368/32b45ba6:page swipe0/5 all;zoomed hazard pan0/5 changes
  page;plan pan0/5,15 settled pairs unchanged. Hazard element taps41=5/5,
  46/49=0/5 now supplemented by explicit probe. Plan chip4/5,5/5,5/5.
- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6;
  health/history,sync,prep/topo passed;sync ok/done. #404/#406237 tests,
  five existing skips; nine-hole35.49->22.93 s,two render workers.
- Internal TestFlight0.1.0(86):Apple VALID/IN_BETA_TESTING.
- #419 reviewed/merged;PASS6112715912,merge95b5694e.

## Evidence boundaries

- AX content/frame is not padded hit bounds. Each probe offset has one fresh
  launch;centre before-screenshot timing differs from offsets. Trace writes
  may perturb timing; trace-off controls retained. No other callbacks traced.
- XCTest duration includes synchronization. uiFeedbackMs=null is not300 ms
  visible feedback. Message/haptic,hardware Crown/gloves/wet wrist/AOD/
  sunlight/GPS/battery/notifications/WCSession remain unproved.
- One factual mapped-hole fixture cannot prove all-course caddie quality.

## Owned resources and cleanup

- One editing worktree:/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011;
  Codex,createdOct11 08:30 UTC,expiryOct18 08:30 UTC. Preserve primary dirty tree.
- Ref codex/pr420-wrist-recheck-20261012,expiryOct13 08:22 or after diagnosis;
  contains #420 production + audit scaffolding, no extra checkout.
- /dev/shm/garmin-ai-caddie-watch417-input-probe-20261012 removed(31 MiB);
  named --rm container gone. Source d0a0cf53;9/126 tests passed0.777/15.607 s.
  Persistent evidence:operations/watch417-input-probe-20261012 including
  runtime38205917630/artifacts,analysis,public reviews and owned manifest.
- /dev/shm/garmin-ai-caddie-watch417-capability-20261012 removed(31 MiB);
  no open files/named --rm container. Mount setup127 retained:mounting /app
  hid image venv;corrected to /review. No dependency install.
  Persistent operations/watch417-capability-20261012:manifest/test logs,
  runtime38207654935/artifacts,public review and physical-inspection proxy.
- operations/watch417-feedback-20261012 retains before instance env,
  change manifest and baseline receipt. One added option remains active;
  collector invocation25454 closed0,no persistent session was created.
- Feedback runner:operations/blocking-waits/codex-watch417-66000eba-wait_for_conclusion.sh,
  owned repository waiter;conventional top-level source path absent.
  Updated09f8ecbb/matches62201d90;expires goal cutoff,interface/cursor retained.
- /dev/shm/garmin-ai-caddie-watch417-feedbackwait-20261012 removed44 KiB;
  no open files/install/container/service. Offline tests/log/manifests retained
  in operations/watch417-feedback-20261012. Feedback81342 closed0;36723
  closed1(gh_error),posting50477 closed0. No pending feedback terminal.
- /dev/shm/garmin-ai-caddie-watch417-total-matrix-20261012 removed31 MiB;
  named --rm container gone,no open files/dependency install/test data.
  Manifest/logs persist operations/watch417-total-matrix-20261012.
  Verification terminals33139 failed setup,61136 passed,10389 cleanup closed;
  capacity54 GiB disk free. Hosted38214143769 closed;three simulators/video
  processes closed by workflow. Results persist;no Native currently in flight.
- /dev/shm/garmin-ai-caddie-watch417-safe-area-20261012 removed31 MiB;
  exact --rm container gone,no open files/test data/service/environment.
  Logs/manifest operations/watch417-safe-area-20261012.81716/26263 closed0.
- Other persistent evidence under /home/jason/garmin-ai-caddie-data/operations:
  watch417-simulator-audit-20261011,pr419-4cfb1588-20261011,
  watch417-wide-audit-20261012,watch417-control-recheck-20261012,
  watch417-picker-recheck-20261012,watch417-immediate-picker-20261012,
  watch417-map-recheck-20261012,pr420-bd2ec304-20261012.
  All originals/manifests/diagnostics retained; prior snapshots removed.
- Local /tmp/garmin-watch417-images-20261012-GCqa8Y:viewed copies only,
  expiryOct13 08:30 or after review;remote originals retained.
- Delegated waiter wait_release_38083089271 completed38207654935 success;
  terminal78491 closed0;download97940 closed0. Prior38205917630 waiter/
  download closed0. No live waiter/service/
  tunnel/container/volume/port/new environment;gh-feedback timer/cursor unchanged.
- Historical ledgers preserved verbatim in dated docs/archive files;
  latest PROJECT_STATE-2026-10-12-watch417-safe-area-request.historical.md.

## Next action and stop conditions

1. Verify DEBUG method23/observers,dispatch only safe-area-probe,block for
   result;report root/page insets and0.5pt cutoff interval to Claude on417.
   Then method22 short-band diagnostic and finish matrix screenshot review.
2. Process Claude reply/new #420 head once;exact-source/Native review and
   original five taps/undo required for W01. Keep #418 draft.
3. Continue independent audit gaps;when exhausted use one same-turn blocking
   feedback waiter. Ignore self bookkeeping CI;no main-thread status polling.

Continuous cutoff:2026-10-13 08:22:16 UTC,or earlier48 hours without external
PR events and no open PRs. Explicit #417 audit remains authorized;owner stop
overrides. GitHub comments end _Generated by Codex_;Codex commits end
Generated-by: Codex. Ledger<=200 lines;dated archives preserve detail verbatim.

