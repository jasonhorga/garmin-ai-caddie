# PR #422 Watch IA prototype element audit

Status: `a913758a` full audit and `3a8b2af2` targeted evidence preserved; exact `9e03df30` clock/selection remeasurement is complete on all five requested faces. This is a DEBUG prototype review, not a production fix or merge approval. Keep #422 draft.

Source: `a913758a0460dccc24ab76ce34ea4bcd753288be`; [exact Native CI 38235401034](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38235401034) passed. Prototype audit candidate `773e9d836bd22974058ee8e1512af5fd3e308b52` has that direct parent and only audit instrumentation/workflows/docs. It does not carry #420 production changes. [Five-face runtime run 38237977234](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38237977234) completed successfully; five collector methods executed/passed with zero skips on each face. Functional outcomes below are assessed separately from collector success.

The element method uses five independent launches per control at the visual/AX centre, and another five at centre+8pt horizontally. Functional controls use state outcomes with native event tracing off; a separate diagnostic traces native touches/actions. Empty save/continue/finish closures are measured for callback dispatch with tracing, without claiming score persistence or round navigation. Menu Text rows have no callbacks; no synthetic gesture/action is added to them. Setup for modal/selection controls uses actual taps and verifies the starting state.

Seven runtime routes: `proto-face`, `proto-face-autoshot`, `proto-score`, `proto-score-par3`, newly added `proto-score-stack`, `proto-turn`, `proto-menu`. On the latest source, penalty is an inline third score field and the older extras sheet is replaced by a fairway sheet. +/- controls no longer have the old IDs; the harness queries their actual distinct labels.

42/45mm cutoff measurement uses a temporary full-width 2pt row in the route root and the prototype canvas, binary search at0.5pt resolution, and five trace-off confirmations below/above plus a separate native diagnostic. This measurement cannot sign off original controls. Passive root/outer/full geometry receipts and native safe frames are retained. No injected Crown binding or touch swipe is represented as Crown rotation.

Remote verification at exact candidate:11 collector tests0.443s and126 mobile contracts6.175s, zero skips. Read-only31MiB snapshot/container removed; no installs/services/volumes/ports/tunnels. Persistent evidence lives under `/home/jason/garmin-ai-caddie-data/operations/pr422-prototype-audit-20261012`.

## Completed design-render check

Native artifact [11741400980](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38235401034/artifacts/11741400980), `watch-snapshots`:35 requested-family images covering seven rendered states across41/42/45/46/49. All three original-pixel contact sheets inspected. These are ImageRenderer snapshots with a red bottom guide; they do not contain the real system clock or establish native touch acceptance. Physical exports retain pixels/DPI and a5mm ruler;326DPI for41/42/45/46 and338 for49. Browser CSSmm/enlarged chat images do not prove physical calibration or sunlight readability.

| Prototype finding | Evidence | Expected before production wiring |
|---|---|---|
| PIA01 — P2: menu drops Settings and End on all five faces | `proto-menu-{41,42,45,46,49}mm.png` contains only计分卡/换洞/本洞记录. `rows.prefix(fitting)` renders three; there is no ScrollView/page continuation. Runtime swipe reachability is pending. | Keep every menu action reachable without reducing the primary hit area. The absence is independent of the intentional Text/no-action placeholder. |
| PIA02 — P2: stack bottom row intrudes into the guide on41/42 | `proto-score-stack-41mm.png` and42mm show开球/保存 backgrounds crossing the red strip. The38pt minimum line height produces an end at198pt:9pt below the measured41 safe bottom189;5pt below the estimated42 bottom193. Real42 inset and actual control outcomes are pending. | Fit all controls inside the measured interactive area for each face; retain meaningful height and avoid fixing only test coordinates. |

The row-score layout, fairway choices and turn choices are fully visible in these design renders. This does not yet establish clock/corner safety, touch success or Crown behavior. Face controls lie above the red guide, but active plan lines are static sample content; cycling the label is not a caddie-route algorithm verification.

## Runtime results and unresolved scope

The collector preserves400 control records and426 screenshots per face (2,000 records/2,130 screenshots total). Each of30 implemented control cases succeeds5/5 at the centre and5/5 at centre+8pt on every face:1,500/1,500 trace-off functional taps. Five intentionally empty callback cases dispatch50/50 per face with native tracing:250/250 callback receipts, not persistence/navigation acceptance. Menu Settings/End are absent in all100 planned records for those two rows; they are not failed taps. All three real upward swipes still show only the original three menu rows on all faces, confirming PIA01 on this source.

The [control table](2026-10-12-pr422-prototype-controls.tsv) contains all400 face/control/offset groups, frames and outcomes. AX frames do not establish padded hit bounds. There are150 independent functional native-input diagnostics; every hook is available and every terminal coordinate is within0.25pt of the requested point. Clock-free synthetic renders did not establish these results. Seven baseline sheets, the route sheet and the three-swipe menu sheet have been inspected (200 baseline/control-state images +15 route +15 swipe images); repeated after-tap screenshots remain preserved for detailed comparison.

| Face / actual simulator | Full window (pt) | Root/outer safe frame (pt) | Top / bottom inset (pt) | Functional taps | Placeholder callbacks |
|---|---|---|---|---|---|
|41 / Series9|176×215|2,46,172,143|46 /26|300/300|50/50|
|42 / Series10|187×223|2,48,183,144|48 /31|300/300|50/50|
|45 / Series9|198×242|2,51,194,164|51 /27|300/300|50/50|
|46 / Series10|208×248|2,53,204,159|53 /36|300/300|50/50|
|49 / Ultra2|205×251|2,55,201,157|55 /39|300/300|50/50|

The runtime inset is31pt on42 and27pt on45, replacing the snapshot estimates30/35. Runtime canvas reads the measured outer inset; the explicit snapshot helper still needs correction by the author. The full canvas is0,0,width,height with zero own insets. Do not subtract the bottom inset again from the already-safe root frame.

Cutoff qualification: both root and canvas temporary2pt probes fired at y222 on42 and y241 on45 (window height−1). The original bracketing therefore reports `boundaryLocated=false, upperWorks=true`; it does **not** locate a dead strip or prove five-repeat acceptance at those endpoints. Recheck will confirm the endpoints five times without tracing and once with native diagnostics. Earlier production root/hazard cutoffs stay valid for their measured hierarchy; a safe-area inset alone is not proof of a universal watchOS touch cutoff.

| Additional prototype finding | Actual evidence | Expected before production wiring |
|---|---|---|
|PIA03 — P2: top score/turn content encroaches on the native clock|`proto-route--score-crown-boundary.png`, `proto-baseline--stack-save.png` and `proto-baseline--turn-continue.png`. Score boxes and the stack first + start at y28; the native clock lies over their upper-right area, especially46/49. The41 turn summary+6 runs into the clock. Design renders omit the clock.|Reserve the real clock region on every face, retaining the measured bottom fit and usable controls; check live-window screenshots after the change. Centre tap success does not clear visual overlap.|
|PIA04 — P2: stack selection is invisible|Five-repeat `stack-select-total` / `stack-select-penalty` state receipts confirm selection changes, but `stackRow` has no selected style. After-tap screenshots show the same three rows, while the Crown handler uses `selected`.|Show which field Crown input will change. This finding concerns visible selection; it does not claim a tested Crown gesture.|
|PIA05 — nonblocking:42/45 design insets differ from runtime|Snapshot helper30/35 versus measured31/27.42 design bottom193 versus actual192;45 design bottom207 versus actual215.|Update `WatchProtoFace.bottomInset` for representative owner renders; runtime nil-inset path already reads actual geometry.|

Physical artifacts retain original pixels, recorded326/338DPI,5mm rulers and print-at100% instructions. Stack labels are11pt versus13pt in row layout; centre/+8pt success does not prove wet/gloved or wrist-distance readability. Printed/device calibration and genuine Crown rotation remain open. `simctl io … help` lists enumerate/poll/video/screenshot; `simctl help` has no Crown input. No binding injection, AX adjustment or touch swipe is counted as Crown rotation.

Author replies6122683856/6123342194 advance #422 to `3a8b2af244646b40194a83c89e87ba15e32017aa`: stack height split and ScrollView menu only, plus design snapshots. Exact-head Native38242810064 is green. PIA01/PIA02 are author-fixed and await targeted runtime checks; unchanged routes retain the `a913758a` evidence. Latest acknowledgement6124133593. No merge or release approval.

## Revised source follow-up

All40 family-size design renders from exact3a Native [watch-snapshots11743844433](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38242810064/artifacts/11743844433) inspected across three contact sheets. The new stack bottom stays above the guide; menu top and `proto-menu-end` show every row and a visible End at the final position. These are ImageRenderer projections of the two states, not evidence that live scrolling works. Revised physical exports preserve40 originals and40 glare aids under `operations/pr422-prototype-recheck-20261012/native38242810064`; no source snapshot/install/service, graphics container removed.

Targeted instrumented source `69539a5bc9ba7ef1c52fb5f0147572990f675e34` descends from exact3a; the only conflict resolution retains the author's ScrollView and puts the passive menu-state anchor outside it.137 remote tests passed (11 collector0.439s +126 contracts6.217s), zero skips; read-only snapshot/container removed. [Targeted runtime38251740277](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38251740277) measures11 stack controls +5 menu rows, five fresh centre and five+8pt taps each on41/42/45/46/49. Real bounded swipes must put the entire menu row between the original34pt top gap and measured interactive bottom before a tap is valid. Text rows retain no callbacks; independent native touch diagnostics do not manufacture an action. Three methods and32 control/offset groups per face explicitly distinguish the recheck from full coverage.

The run is **red**, with2 passed/1 failed collector methods and zero skips on every face. `test04TurnAndMenuControls` fails after all planned tap records, at the first swipe inventory: reading live index21 after the AX tree changes throws `Failed to get matching snapshot` at harness line104. This is a collector defect, not a menu action failure. All160 planned tap records and203 screenshots per face are retained; analysis correctly refuses `collectionComplete=true`. Do not relabel the red run green. The next collector must enumerate one immutable native snapshot rather than dereference a changing query index.

Of500 trace-off functional stack taps,499 reach their expected state. The superseded42mm centre selector `stack-select-total-x0-1` remains selected=putts; the other four centre and five+8pt trials succeed. Do not erase this miss by rerunning. The50 deliberately empty Save callbacks dispatch50/50; all250 Text menu trials have a fully visible row and native coordinate taps, with no implemented action or persistence claim.75 independent control diagnostics have native hooks and terminal coordinate error≤0.25pt.

PIA01 is resolved for row reachability on3a: all five rows, including Settings/End, are brought wholly into the target area by bounded real swipes. Baseline and swipe/failure images show End. PIA02 is resolved for bottom fit on3a: Save bottoms are189/192/215/212/212pt on41/42/45/46/49, at the measured interactive bottom. Save dispatches5/5 centre and5/5+8pt per face. Clock overlap and the missing selected style remain visible on this superseded source.

Both root and canvas temporary2pt probes fire5/5 trace-off at each sampled endpoint on every face. Low/high y pairs are143/214,151/222,170/241,176/247,179/250pt for41/42/45/46/49. All20 independent native endpoint diagnostics receive exact requested coordinates and dispatch the probe callback. No cutoff is bracketed. These points do not establish every intervening pixel, original control acceptance, a physical-watch result, or the cause of W01 in production.

Visual comparison is complete for the original a913 after-tap set:1,900 valid images grouped into312 unmasked representatives across16 inspected sheets. Only clock and right4px indicator were masked for deduplication; originals stay unmasked. Some immediate plan images contain transitioning text, without evidence of a prolonged defect. The3a recheck's800 valid images yield94 unmasked representatives across four inspected sheets. Its three baseline sheets, real swipe/failure, route and four endpoint sheets are inspected. Persistent3a receipts, red logs and physical artifacts are under `operations/pr422-prototype-recheck-20261012/runtime38251740277`; analysis/graphics container removed.

Claude request [6124535353](https://github.com/jasonhorga/garmin-ai-caddie/pull/422#issuecomment-6124535353) advances the prototype to exact `9e03df3072248dd03b0e3915ca413d5c185edaaa`. [Exact Native38251072892](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38251072892) is green; watch-snapshots11749246424. Recheck score/stack/turn/menu at centre/+8pt on all five faces, and several bottom-inset y positions five times trace-off plus native diagnostics. Acknowledgement [6125615938](https://github.com/jasonhorga/garmin-ai-caddie/pull/422#issuecomment-6125615938) records the collector fault and preserves the old42mm miss. New-head runtime/visual adjudication remains open; #420 production first-tap acceptance remains separate.

Artifacts: [contact sheets11745969268](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38237977234/artifacts/11745969268), [physical11746519142](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38237977234/artifacts/11746519142). Face artifacts:41=11743167946,42=11744230723,45=11743208092,46=11743710858,49=11746278840. Raw receipts/analysis/control table persist under `operations/pr422-prototype-audit-20261012/runtime38237977234` on homeserver. API EOF ended one waiter; restarting the same run returned success. Collection/analysis container removed; no new environments or services.

## Clock revision measurement protocol

The `codex/pr422-clock-harness-20261012` candidate retains exact9e product layout, including clock band, selected outline, turn row height and measured insets. It changes only DEBUG scaffolding and test collection. Inventories now traverse one immutable native `XCUIElementSnapshot`, avoiding changing live indices after scrolling. Menu target validation uses the author's measured top/bottom geometry.

`prototype-clock-recheck` selects four collector methods: row/par3 score, stack score, turn/menu, and temporary bottom probes. It expects74 control/offset groups and370 tap records per face (37 cases at five fresh centre and five fresh+8pt trials), explicitly excluding unchanged hole-face controls from the recheck. Planned functional taps, placeholder callback dispatch and Text-only menu touches are reported separately. The new bottom probes use `proto-score-stack`, not the unchanged map hierarchy: two probe scopes, five trace-off confirmations plus one native diagnostic at measured bottom−1, bottom+1, inset midpoint and endpoints. Interior samples are collected even if the upper endpoint rejects the initial probe; bracketing does not substitute for their independent receipts. Genuine Crown rotation remains unexecuted.

Exact candidate `c345ae15473fc48826f49cb1785026a91d0ca78f` passed137 remote tests (11 collector1.324s/126 contracts16.510s), zero skips. The temporary source snapshot and verification container were removed. [Runtime38267523735](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38267523735) completed successfully with the exact candidate and no skipped methods. All40 exact9e Native design renders from artifact11749246424 are inspected across three sheets: the selected stack outline is visible, initial score/turn controls avoid the clock guide, and End is visible in the menu end-state projection. This does not sign off live clock/scrolling/touches.40 originals and40 glare aids with retained pixels/DPI/5mm ruler remain under `operations/pr422-prototype-clock-20261012/native38251072892`; Native graphics container removed.

## Exact-head element recheck — `9e03df30` / runtime `38267523735`

The hosted runtime ran four methods on every `41/42/45/46/49 mm` face: `4/4` passed, zero skips, `370/370` tap records valid per face. The 54 state-changing control groups are `270/270` successful per face at centre and +8 pt. The ten deliberately empty Save/Continue callback groups dispatch `50/50` per face; this is callback delivery only, not persistence or round navigation. The ten menu-row groups are layout/coordinate placeholders and have no product callback. The 32 independent native input diagnostics per face all have a hook and terminal coordinate error ≤0.25 pt; no diagnostic is Crown input.

The exact runtime geometry and bottom sampling are below. `Interactive bottom` is the measured bottom edge of the safe root (`window height − bottom inset`). Every listed y was sampled five times with tracing disabled and fired `5/5`; the separate native diagnostic at each listed point received the requested coordinate. Because the highest point is window-height−1 and still fires, this hierarchy does not locate an exact “tap stops firing” y. It must not be generalized to production W01 or to a physical watch.

| Face | Window pt | Root frame pt | Insets top/bottom | Interactive bottom | Sampled y (each 5/5) |
|---|---:|---|---:|---:|---|
|41 mm|176×215|2,46,172,143|46 / 26|189|143, 188, 190, 202, 214|
|42 mm|187×223|2,48,183,144|48 / 31|192|151, 191, 193, 207.5, 222|
|45 mm|198×242|2,51,194,164|51 / 27|215|170, 214, 216, 228.5, 241|
|46 mm|208×248|2,53,204,159|53 / 36|212|176, 211, 213, 230, 247|
|49 mm|205×251|2,55,201,157|55 / 39|212|179, 211, 213, 231.5, 250|

The nine runtime visual sheets (`visual-review/after-tap-01..09.png`) were generated remotely from the unmasked after-tap images and inspected. The five faces keep the title/control content below the reserved clock band; the stack’s selected row is visibly outlined green; score, par3, fairway and turn controls remain visible and fit the measured root. The menu’s bounded scroll reaches Settings and End; initial 41/42 mm menu images clipping the lower rows are the pre-scroll state, not missing actions. No new P1/P2 product finding was found on this exact prototype. The remaining review boundary is P3/evidence: genuine Crown rotation, physical-watch input, glare/gloves, persistence/navigation behind placeholder callbacks and actual production controls are unverified.

Persistent runtime evidence is under `/home/jason/garmin-ai-caddie-data/operations/pr422-prototype-clock-20261012/runtime38267523735/` (`analysis.json`, `controls.tsv`, `analysis-summary.log`, raw face artifacts and `visual-review`). #422 remains a draft and is intentionally not merged.

_Generated by Codex_
