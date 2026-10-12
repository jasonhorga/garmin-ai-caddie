HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before the clock-revision harness/resource state changed. The short operations ledger is authoritative.

# Garmin AI Caddie Project State

> Short authoritative live ledger. Dated archives preserve history verbatim.

**Updated:** 2026-10-12 13:52 UTC
**Canonical baseline:** main 3e785b14 / product merge95b5694e (#419)
**Current slice:** PR-422-PROTOTYPE-IA — in-progress

## Current state

- #417 owner audit6111380071/6111790655: test scaffolding/review only;
  Claude implements product fixes. No new TestFlight.
- Full wrist audit37 findings (2 P1/17 P2/18 P3), plus measured supplements.
  docs/reviews/2026-10-12-watch417-wrist-ux-audit.md is the audit receipt.
- #422 DEBUG-only IA prototypes: Jason approved evaluation, KEEP DRAFT,
  DO NOT MERGE. Latest request6124535353, acknowledgement6125615938.
  Exact head9e03df3072248dd03b0e3915ca413d5c185edaaa;
  Native38251072892 success;watch-snapshots11749246424.
  Recheck score/stack/turn/menu centre/+8pt on41/42/45/46/49;
  several bottom-inset y values five trace-off trials plus native diagnostic.
- Original a913 audit38237977234/773e9d83:25 collector methods passed,
  no skips;1,500/1,500 functional taps,250/250 empty callback dispatches.
  Original menu Settings/End absent;PIA01/02 P2 menu/stack fit.
  PIA03 P2 clock overlap;PIA04 P2 invisible stack selection;
  PIA05 nonblocking snapshot inset estimates42/45 differ from runtime.
  All1,900 valid after-tap images compared,312 unmasked representatives
  across16 inspected sheets;baseline/route/swipe evidence inspected.
  Immediate plan transitions do not prove a settled/latency defect.
- Targeted3a audit38251740277/exact69539a5b is RED:
  every face3 methods=2 passed/1 failed,zero skips. Live AX index inventory
  throws after first menu swipe(line104);collector fault,not action failure.
  All160 tap records/203 screenshots per face retained;complete=false.
  Functional499/500:42 stack-select-total centre trial1 misses;retain it.
  Save placeholders50/50 callbacks;250 Text rows visible/tapped,no actions.
  75 independent input diagnostics hooks available,coordinates≤0.25pt.
  PIA01 reachability/PIA02 bottom fit resolved on3a. Save bottoms
  189/192/215/212/212pt;centre/+8pt callbacks5/5 each on every face.
  800 valid images compared,94 representatives/four sheets inspected;
  three baseline,swipe/failure,route/four endpoint sheets inspected.
- 3a root/canvas temporary2pt probes:low/high endpoints
  143/214,151/222,170/241,176/247,179/250pt on41/42/45/46/49;
  each5/5 trace-off;20 diagnostics exact coordinate/action dispatch.
  No cutoff bracket;does not sample all pixels or clear production W01.
- 3a exact Native38242810064 artifact11743844433:40 design images,
  all three sheets inspected;physical originals/DPI/5mm exports retained.
  New9e clock/selected/inset changes need native visual/runtime check.
- docs/reviews/2026-10-12-pr422-ia-prototype-element-audit.md and
  2026-10-12-pr422-prototype-controls.tsv contain original findings.
  Persistent3a analysis/red logs retain all partial evidence.
- #420 OPEN production bd2ec304794d17dee644279df3e4d30f9f0dd544:
  Native38190513917 green;original49 first-tap0/5 remains HOLD.
  Probe38205917630:centre reaches app/no action;y-8/-16 work with eligible
  fixes;trace-off centres fail. Cause unproved;new prototypes don't clear it.
  Published#4176118215955/#4206118223337;original coordinates unchanged.
- #418 draft477eaab6;immutable W/C/I/M evidence retained. Do not merge.
- Issue delivery GH_FEEDBACK_EXTENDED_EVENTS=1 enabled05:27;
  existing collector/timer/cursor unchanged. #42162201d90 attribution fix,
  19 offline regressions/CI38211176310 passed;await Claude review.
  Own signed audit receipts suppressed. Do not self-merge.

## Unfinished queue

- PR-422-PROTOTYPE-IA — in-progress:repair immutable screenshot inventory,
  rebase scaffolding onto exact9e,verify and dispatch requested four routes.
- WATCH417-ELEMENT-AUDIT — evidence-open:hardware/Crown/replies;
  completed diagnostic/capability/band/safe-area evidence must not be repeated.
- PR-420-MANUAL-SHOT — blocked:original49 acceptance unresolved;
  review changed exact source or explicit stale-fix scope correction.
- PR-418-AUDIT-SCAFFOLD — evidence-open:draft,not a product fix.
- ISSUE-FEEDBACK-WAITER — evidence-open:#421 pending Claude review.
- PR-FEEDBACK-CONTINUOUS — queued:deduplicated feedback after active audit.
- NATIVE-FIXTURE-LAYOUT-STABILITY — queued:nonblocking#416 variation.
- IOS-STATUS-CONTRAST — queued:nonblocking dark status/navigation text.
- OWNER-DEVICE-BUILD86 — evidence-open:paired physical-device validation.

## Retained verification baselines

- Safe-area6120644491/6121410222:41/46/49 bottom26/36/39pt;
  root last→first188.5→189/211.5→212;hazard192.5→193/215.5→216.
  Five horizontal points and trace-off5/5 below,0/5 above. Temporary probes;
  native38219857642/a9cd76e0 and38225977002/a968220f,34 images inspected.
- W37 P2 short band drags6122137499,Native38229912952/4e8ce25c:
  105 untraced+21 diagnostics/147 images;neighbour-tap failures retained.
- Picker38194936812/7155607d:183/183 valid pairs≤two gestures;
  immediate/Done5/5 per face;4.5s idle closes. Map38197809368/32b45ba6:
  page/zoomed-hazard/plan pan0/5 changes page,15 settled pairs unchanged.
- Total matrix38214143769/437c6ca1:valid pairs90/face;≤3 drags72/77/77;
  reached totals saved72/72,77/77,77/77;unreached≠save failures.
- W36 capability38207654935/3d29e56e:three faces disabled/off5/5,
  visible reason0/5;injected capability,not physical proof.
- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6:
  health/history/sync/prep/topo verified,sync ok/done.
  #404/#406237 tests,5 existing skips;nine-hole35.49→22.93s,two workers.
- TestFlight0.1.0(86):Apple VALID/IN_BETA_TESTING. #419 reviewed/merged.
- Full preceding metrics and receipts remain in dated archives/review files.

## Evidence boundaries

- AX frame≠padded hit bounds;five fresh launches separate trials.
  Trace-on may change timing;trace-off acceptance stays independent.
- Root frame already excludes safe-area;do not subtract inset twice.
- xctestActionMs includes synchronization;null uiFeedbackMs≠≤300ms.
- Empty callbacks/Text placeholders≠persistence/navigation success.
- Genuine Crown/gloves/wet/sunlight/AOD/GPS/battery/notification/WCSession
  hardware remains open. simctl help exposes no Crown input;
  binding injection/AX adjustment/touch swipes never count as Crown rotation.

## Owned resources and cleanup

- Sole editing worktree:/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011;
  Codex,createdOct11 08:30,expiresOct18 08:30 UTC. Preserve primary dirty tree.
- Branch codex/pr422-revised-harness-20261012 at69539a5b;
  next preserve receipts then rebase onto9e on a new named branch.
  Previous312e4272/f34c94bd reviews pushed/retained.
- All owned source snapshots and test/analysis/graphics --rm containers removed.
  No installs,private environments,services,ports,tunnels or volumes.
- Persistent evidence under /home/jason/garmin-ai-caddie-data/operations:
  watch417-* audit/control/picker/map/input-probe/capability/feedback/
  total-matrix/safe-area/band-input-20261012,pr419-4cfb1588-20261011,
  pr420-bd2ec304-20261012,pr422-prototype-audit-20261012,
  pr422-prototype-recheck-20261012(native38242810064/runtime38251740277).
  Originals,physical exports,red logs,analysis/control tables retained.
- Wait runner:operations/blocking-waits/codex-watch417-66000eba-wait_for_conclusion.sh
  matches#421;expires goal cutoff. Collector/timer/feedback-cursor untouched.
- wait_release_38083089271 completed runtime38251740277 RED and latest
  Native38251072892 GREEN/exact9e. Latest handles64314/91690/47911 closed0.
  Red log wait-ci-38251740277-20261012T131238Z-3484111.log;
  Green log wait-ci-38251072892-20261012T134219Z-3567821.log.
  Exact cleanup check found no surviving interrupted38251740277 waiter.
  No pending Native wait/redispatch or active feedback waiter.
- Runtime collection23500 lost SSH255;artifacts and analysis completed on
  remote,complete=false intentionally. Visual53524 closed0;downloads
  31929/27106 closed0. Remote scripts/manifests persist;container absent.
- Latest capacity53GiB free/4.8GiB available memory.
- Local /tmp/garmin-watch417-images-20261012-GCqa8Y viewed copies;
  expiryOct13 08:30/after review;remote originals retained.
- Superseded ledger preserved verbatim in
  docs/archive/PROJECT_STATE-2026-10-12-pr422-recheck-complete.historical.md.

## Next action and stop conditions

1. Preserve substantive review receipts;repair inventory using one snapshot.
2. Rebase audit onto9e;verify exact source remotely;dispatch four changed
   routes and bottom-inset sampling on all five faces. No layout/hit repair.
3. Wait with installed blocker;inspect Native/live/physical artifacts;
   adjudicate PIA03–05 and requested bottom sampling on#422.
4. Keep#422/#418 draft;#420 HOLD until original acceptance corrected.
5. Resume same-turn blocking feedback after active evidence adjudicated.

Continuous cutoff:2026-10-13 08:22:16 UTC,or earlier48h without external
PR events and no open PRs. Owner stop overrides. Comments end
_Generated by Codex_;commits end Generated-by: Codex. Ledger≤200 lines.
