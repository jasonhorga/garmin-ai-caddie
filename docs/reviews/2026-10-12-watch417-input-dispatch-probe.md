# #417 input dispatch supplement / #420 review

Production source: #420 `bd2ec304794d17dee644279df3e4d30f9f0dd544`.
Test integration: `d0a0cf538e1857808d171fe029f41a925e6f82a1`.
[Runtime 38205917630](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38205917630).
Collection/build passed; the interaction results below are separate.

## Conclusion

W01/W02 are reproduced before the GPS/model gate: both 49 mm rail centres
receive the expected touch but neither button action fires. Moving the touch
up 8 or 16 pt activates the correct action, and the + then enters pending with
an eligible raw fix. Do not diagnose these centre failures as stale GPS.

#420's independent stale-fix implementation remains supported by code/contracts
and the earlier 41/46 boundary checks. The owner's original five first-tap and
immediate-undo acceptance is still 49 mm 0/5; these offset diagnostic successes
do not replace it. Hold the claim that #420 resolves W01 and the merge pending
that acceptance, or explicitly separate the stale-fix fix from the W01 fix.

W34's explicit coordinates reproduce a lower-screen hit-path failure. On
46 mm, the centre fails but y−8 succeeds; on49 none of the five probe points
fires hazard-next. The failed hazard touches hit the outer SwiftUI hosting
view; successful ones enter the native pager cell's hosting subtree. This is
evidence of differing hit paths, not proof of a particular invisible overlay
or recognizer being responsible. Claude owns the product correction.

## Instrumentation and limits

- Native `SPApplication.sendEvent:` observer, DEBUG simulator and explicit
  opt-in only. No new SwiftUI recognizer or hit-test view; original dispatch
  forwarded exactly once. Existing control/model callbacks append receipts.
- 30 traced trials / 60 touch records: every recorded begin and terminal point
  equals the requested window point, with zero x/y difference. The hook was
  available on all three faces. Window sizes match the XCTest app frame:
  176×215,208×248,205×251 pt for41/46/49.
- All terminal phases are ended(3), except41 menu centre cancelled(4).
  Callback timing and synchronous diagnostic writes may perturb timing. That
  isolated41 failure is not a new W02 finding: trace-off centre succeeds and
  the prior five trials succeeded.
- Eight trace-off controls reproduce the49 rail and46/49 hazard failures;
  the observer has not repaired these centre failures. Trace-off intentionally
  has no raw-input receipt, not evidence of missing input.
- Each point below has one fresh launch. The five offsets are spatial probes,
  not five repeats at one point or a measured general success probability.
  The first traced centre also captures a before screenshot; other offsets do
  not. A timing race is not excluded. No other map/menu/long-press action was
  instrumented, so an absent named button action does not prove no other
  recognizer ran. Hardware, Crown and haptics remain open.

## 49 mm rail: received touch and action per point

AX menu frame `[10,191,50,50]`, + frame `[145,191,50,50]`.
Every point is inside its AX frame, but AX frame is not proof of a hit region.
Raw points below equal expected points at begin and end.

| Offset y | Menu point / action / state | + point / action / state |
|---|---|---|
| 0 | `(35,216)` / none / home | `(170,216)` / none / no pending |
| −8 | `(35,208)` / menu enter+exit / menu | `(170,208)` / button+model enter / pending |
| +8 | `(35,224)` / none / home | `(170,224)` / none / no pending |
| −16 | `(35,200)` / menu enter+exit / menu | `(170,200)` / button+model enter / pending |
| +16 | `(35,232)` / none / home | `(170,232)` / none / no pending |
| trace-off centre | `(35,216)` requested / no menu transition | `(170,216)` requested / no pending |

The two successful + callbacks see `eligibleShotOrigin=true`, accuracy5 m,
raw ages2.162 s/2.298 s, and `pendingBefore=false`; exits report pending=true.
Both successful and failed rail points have the same native outer hosting
ancestry. Native ancestry alone cannot name the SwiftUI element swallowing it.

## Root centre controls

| Face | Menu trace-on / trace-off | + trace-on / trace-off |
|---|---|---|
| 41 | `(35,180)`: cancelled, no action / opens | `(141,180)`: button+model, pending / pending |
| 46 | `(35,213)`: opens / opens | `(173,213)`: button+model, pending / pending |
| 49 | `(35,216)`: ended, no action / no transition | `(170,216)`: ended, no action / no pending |

41/46 successful + raw ages2.729 s/2.849 s, eligible fixes. Do not replace
the earlier genuine five-repeat acceptance with this one-centre control set.

## Hazard-next at2×

Every traced point arrives exactly as requested and ends normally. AX frames
are55×32 pt with centre y189/222/225 for41/46/49. A successful action changes
1/2 to2/2, stays on障碍 and preserves viewport `zoom=2;panX=0;panY=0`.
Every failed action keeps1/2 and the same page/viewport.

| Requested point relative to centre | 41 centre `(88,189)` | 46 centre `(104,222)` | 49 centre `(102.5,225)` |
|---|---|---|---|
| Centre | fires / switches | no action | no action |
| y−8 | fires / switches | fires / switches | no action |
| y+8 | no action | no action | no action |
| x−8 | fires / switches | no action | no action |
| x+8 | fires / switches | no action | no action |
| Trace-off centre | switches | no transition | no transition |

46 centre/down/horizontal failures and49 failures hit outer
`_UIHostingView<AnyView>`;46 y−8 and41 successful points hit
`_UIHostingView<_ViewList_View>` with `PUICPageViewCell` and
`PUICTouchAvoidingCollectionView` ancestors.41 y+8 hits the outer host too.
This narrows investigation to native pager reachability and the hit-testing
relationship with the full-screen/root layers. It does not prove clipping or
gesture competition as the exact cause.

## Evidence and acceptance

[49 mm](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38205917630/artifacts/11728020322),
[46 mm](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38205917630/artifacts/11727197874),
[41 mm](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38205917630/artifacts/11727152973),
[contact sheets](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38205917630/artifacts/11727940824),
[physical-size renders](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38205917630/artifacts/11728115001).

Per-tap pairs: `*input-probe--rail-menu-1..6-*.json`,
`*input-probe--rail-shot-1..6-*.json`, `*input-probe--hazard-1..6-*.json`
and corresponding `input-events--<trial>.json`. First centre before screenshots
and all after screenshots are retained.49 menu/+ centres visibly sit in their
circles; hazard1/2 visibly sits at the recorded bottom point. Inspected originals
and the up8 menu after screenshot; no screenshot was modified to define a pass.

Product fix acceptance: repeat the original five fresh-launch centre/right8
taps on + and immediate undo on41/46/49. Recheck menu and hazard centres and
boundaries with real taps, preserving zoom/pan. Do not move only test coordinates
to the successful upper sliver, inject pending or call the model directly.

_Generated by Codex_
