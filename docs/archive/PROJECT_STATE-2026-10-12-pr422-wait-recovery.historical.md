# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short authoritative live ledger. History is preserved in dated archives.

**Updated:** 2026-10-12 10:18 UTC
**Canonical baseline:** main 3e785b14 / product merge 95b5694e (#419)
**Current slice:** PR-422-PROTOTYPE-IA — in-progress

## Current state

- #417 owner audit6111380071/6111790655: test scaffolding/review only;
  Claude implements product fixes. No new TestFlight.
- 37 findings:2 P1/17 P2/18 P3;original35 fdebb6f1/6117399134.
  docs/reviews/2026-10-12-watch417-wrist-ux-audit.md is the audit report.
  W36 capability and W37 band-input supplements have independent evidence.
- #418 draft477eaab6;immutable W/C/I/M evidence retained. Do not merge.
- #420 OPEN production bd2ec304794d17dee644279df3e4d30f9f0dd544:
  exact-source126 contracts passed;ordinary38190513760/Native38190513917 green.
  First-tap38202658425/fd40e821:41/46 centre and+8pt5/5,undo5/5;
  49 0/5,shots0,pendingfalse. HOLD original W01 fix/merge until corrected
  original acceptance or Claude explicitly separates stale-GPS scope.
- Probe38205917630/d0a0cf53:49 rail centre reaches app but no action;
  y-8/y-16 works with eligible fixes. Trace-off centres still fail.
  Failure precedes GPS/model;recognizer cause unproved. Hazard centres
  41 work,46/49 fail. Do not replace original test coordinates to pass.
  Published #4176118215955/#4206118223337;input-dispatch report retained.
- W36 capability38207654935/3d29e56e:three faces each disabled/off5/5,
  visible reason0/5.18 images inspected;published6118384187.
  Capability injected;not physical hardware proof.
- Safe-area request completed6120644491/6121410222. Root/plan GeometryReader
  bottom26/36/39pt and native frames[2,46,172,143]/[2,53,204,159]/
  [2,55,201,157]. Hazard reader full-window,insets0.
  Root last→first fail41=188.5→189;46/49=211.5→212pt.
  Hazard41=192.5→193;46/49=215.5→216pt.
  Five horizontal points and trace-off centre retries5/5 below,0/5 above.
  Temporary2pt buttons measure cutoff,not original control acceptance.
  Native38219857642/a9cd76e0 and38225977002/a968220f;34 images inspected.
  docs/reviews/2026-10-12-watch417-safe-area-measurement.md.
- Total matrix38214143769/437c6ca1:90 valid1..15→10..15 pairs per face;
  within3 drags72/90,77/90,77/90. All reached totals actually saved
  72/72,77/77,77/77. Unreached groups didn't save;not save failures.
  One trial/pair,not five-repeat acceptance.16..20 capped15(existingW03).
  All ten sheets inspected;published6119651495.
- W37 P2 published6122137499,Native38229912952/4e8ce25c:
  five fresh trace-off trials/path,all faces centre-left20/28=10(expected11),
  right-left20/28=12(expected11);41 left-right28=8(expected9).
  Other left/long/full sweeps correct5/5.105 untraced+21 diagnostics.
  Short failures invoke neighbour tap,no drag-ended;long paths correct.
  Native diagnostic coordinates exact/terminal;recognizer cause unproved.
  All147 images/nine sheets inspected;band-input-dispatch report retained.
- #422 latest reviewed request6121553830;DEBUG-only,Jason approved,
  keep DRAFT and DO NOT MERGE. Latest head a913758a0460dccc24ab76ce34ea4bcd753288be,
  Native38235401034 success/exacta913 verified by blocking waiter.
  Priorc9/38232707265 and70f/38230498891 green;use latest source.
  Next run seven proto-* routes(including new proto-score-stack) at41/42/45/46/49:five fresh centre/+8pt
  taps per control,frames,clipping,42/45 safe-area/cutoff,physical review.
  Crown needs a genuine input mechanism;do not substitute binding injection.
  Menu Text/no actions and empty save/turn closures are DEBUG placeholders;
  distinguish geometry/hit evidence from implemented product functionality.
  Proto source excludes #420;candidate773e9d836bd22974058ee8e1512af5fd3e308b52
  has direct parenta913 and prototype-only scaffolding.137 remote tests passed
  (11 collector0.443s+126 mobile6.175s),zero skips. Snapshot/container removed.
  Native simulator audit38237977234 in flight;five faces,seven routes.
  Start comment6122637453 posted;save/turn callbacks measured separately.
  Native a913 watch-snapshots artifact11741400980:35 family-size renders,
  three sheets all inspected;original-pixel/DPI/5mm physical exports retained.
  PIA01 P2:menu Settings/End omitted on every face;PIA02 P2:stack bottom
  crosses guide41(+9pt)/42(+5pt estimate). Precheck6122881278 posted.
  docs/reviews/2026-10-12-pr422-ia-prototype-element-audit.md is the receipt;
  runtime clock/touch conclusions and real42 inset remain pending.
- Issue delivery option GH_FEEDBACK_EXTENDED_EVENTS=1 enabled05:27.
  Existing collector/timer/cursor unchanged;no second monitor.
  #42162201d90057a5efa8df415416dadd0e96eccd604 wait-event attribution fix,
  nineteen offline regressions passed30.108s;CI38211176310 green.
  Await Claude review;do not self-merge. Own signed audit receipts suppressed.

## Unfinished queue

- PR-422-PROTOTYPE-IA — in-progress:audit38237977234 running;review Native
  a913 design artifacts in parallel,then runtime outcomes and physical images.
- WATCH417-ELEMENT-AUDIT — evidence-open:hardware/runtime gaps and replies;
  diagnostics/capability/band adjudicated;do not recollect unchanged evidence.
- PR-420-MANUAL-SHOT — blocked:original49 first-tap unresolved;stale-fix
  merits independent. Review new exact head or explicit scope correction.
- PR-418-AUDIT-SCAFFOLD — evidence-open:draft,not a product fix.
- ISSUE-FEEDBACK-WAITER — evidence-open:#421 pending Claude review.
- PR-FEEDBACK-CONTINUOUS — queued:deduplicated feedback after active audit.
- NATIVE-FIXTURE-LAYOUT-STABILITY — queued:nonblocking #416 variation.
- IOS-STATUS-CONTRAST — queued:nonblocking dark status/navigation text.
- OWNER-DEVICE-BUILD86 — evidence-open:paired physical-device validation.

## Retained verification baselines

- Picker38194936812/7155607d:immediate gestures/Done5/5 per picker/face;
  183/183 valid pairs within two gestures.4.5s idle closes both.
- Map38197809368/32b45ba6:page swipe0/5 all;zoomed hazard pan0/5
  changes page;plan pan0/5,15 settled pairs unchanged. Plan chip4/5,5/5,5/5.
- Safe-area135 tests passed1.930s/26.180s,zero skips. Method22 source
  unchanged from that verification;collector1 executed/passed per face
  does not sign off the observed interactions.
- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6;
  health/history/sync/prep/topo passed,sync ok/done. #404/#406237 tests,
  five existing skips;nine-hole35.49→22.93s,two render workers.
- Internal TestFlight0.1.0(86):Apple VALID/IN_BETA_TESTING.
- #419 reviewed/merged;PASS6112715912,merge95b5694e.

## Evidence boundaries

- AX frame isn't padded hit bounds. Fresh launches separate trials;
  trace-on timing may differ;trace-off controls retained.
- Root frames already exclude safe-area;do not subtract bottom twice.
- xctestActionMs includes synchronization;uiFeedbackMs=null isn't≤300ms.
  Crown/gloves/wet wrist/sunlight/AOD/GPS/battery/notification/WCSession
  hardware behavior remains open. One fixture cannot prove all courses.

## Owned resources and cleanup

- One editing worktree:/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011;
  Codex,createdOct11 08:30,expiryOct18 08:30 UTC. Preserve primary dirty tree.
- Current branch codex/pr422-prototype-harness-20261012 based exacta913;
  no #420 product changes. Prior f34c94bd band review committed/pushed.
- All owned /dev/shm review snapshots and named --rm test containers removed.
  No dependency installs,services,tunnels,ports or volumes.
- Persistent originals/manifests under /home/jason/garmin-ai-caddie-data/operations:
  watch417-simulator-audit-20261011,watch417-wide-audit-20261012,
  watch417-control/picker/immediate-picker/map-recheck-20261012,
  pr419-4cfb1588-20261011,pr420-bd2ec304-20261012,
  watch417-input-probe/capability/feedback/total-matrix/safe-area/band-input-20261012.
  Total-matrix and band/contact artifacts retained;no pending download.
- Owned waiter runner:operations/blocking-waits/
  codex-watch417-66000eba-wait_for_conclusion.sh(matches #42162201d90).
  Expires goal cutoff;existing collector/timer/feedback-cursor untouched.
- Delegated wait_release_38083089271 now waits38237977234/exact773e9d83;
  completed38235401034/exacta913 earlier.
  Handles78560/13464 closed0;no resources or cleanup pending.
  Handles12393/41660 closed0;log retained;no resources or cleanup pending.
  Older80096/43231/3178/50266/93158/8953 closed. No active feedback waiter.
  Remote /dev/shm/garmin-ai-caddie-pr422-prototype-20261012 removed;
  named garmin-pr422-prototype-20261012 container absent/no open files.
  Manifest/tests/script persist operations/pr422-prototype-audit-20261012.
  Capacity54GiB disk,4.7GiB available memory before verification.
  Native comparison container garmin-pr422-native-sheets-20261012 removed;
  no install/source snapshot/service. Scripts/manifest/design+physical outputs
  persist in pr422-prototype-audit-20261012/native38235401034.
- Local /tmp/garmin-watch417-images-20261012-GCqa8Y holds viewed copies;
  expiryOct13 08:30/after review;remote originals retained.
- Historical ledgers verbatim in dated docs/archive files;latest
  PROJECT_STATE-2026-10-12-watch417-band-complete.historical.md.

## Next action and stop conditions

1. Review already-green a913 Native design snapshots during delegated wait.
2. After38237977234 returns,collect all five-face interaction results,
   geometry/cutoffs/screens/physical exports;comment findings on#422.
   Read genuine input capability files before adjudicating the Crown gap;
   try a verified native simulator mechanism if available,never binding injection.
3. Keep#422/#418 draft;process corrected#420 acceptance/Claude replies once.
4. Resume same-turn blocking feedback when active evidence is adjudicated.

Continuous cutoff:2026-10-13 08:22:16 UTC,or earlier48 hours without external
PR events and no open PRs. Owner stop overrides. Comments end
_Generated by Codex_;commits end Generated-by: Codex. Ledger≤200 lines.
