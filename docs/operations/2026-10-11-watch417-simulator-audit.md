# Watch whole-round simulator audit (#417)

Findings-only audit, refreshed on main 3e785b14 / #419 merge 95b5694e.
Build 86 is the released baseline, not the source of the new picker. No product fixes belong in this pass.
The branch adds opt-in DEBUG fixtures, UI-test actions and a separate runtime workflow mode.

One audit dispatch:

```sh
gh workflow run watch-runtime.yml --repo jasonhorga/garmin-ai-caddie \
  --ref codex/watch417-simulator-audit -f runtime_scope=simulator-audit
```

The called workflow selects the newest installed stable Xcode and the numerically newest available
watchOS runtime. It creates independent 41 mm Series 9, 46 mm Series 10 and 49 mm Ultra simulators;
an unavailable required face fails visibly instead of silently using a different runtime/canvas.
No backend URL or account credential is supplied. Only isolated review fixtures are mutated.

`WatchWholeRoundAuditUITests` drives production controls through phone-seeded 9/18-hole rounds,
Watch cached-course setup, nine-to-eighteen turn, scoring, scorecard edits, shots, undo, save/finish,
abandon and offline restoration. It also captures plan/hazard/green paging, zoomed pan/long-press,
measurement, flag drag, cold/stale range states, AOD, late maps and stale phone snapshots.

Each screenshot has step metadata distinguishing `ui-action` from `injected-state`. The fixture
repeats the existing review hole across a canonical synthetic round; it does not prove real-course
geometry or caddie quality. A steady location feed and hole-end/shot/phone events are injected.
Crown zoom levels and luminance reduction are injected display states. Heading telemetry verifies
the application's requested service state, not real compass accuracy or power consumption.

Artifacts (30-day retention): `watch-audit-41mm`, `watch-audit-46mm`, `watch-audit-49mm`, and
`watch-audit-contact-sheets`. The first three contain real simulator PNGs, action/state metadata,
a motion recording, exact source/runtime receipts and sanitized test logs. Comparisons retain
missing-face cells explicitly. Failures preserve their last visible step and accessibility hierarchy.

Report P1/P2/P3 findings in #417 with face, step, evidence and expected behavior. README §3 and
watch.html are references; the October 10 full-bleed map/floating F/M/B direction takes precedence.
List physical GPS, battery, physical Crown/wrist motion and actual WCSession delivery timing as gaps.

Preparation checks on the remote test snapshot passed: 6 audit-tool regressions, 12 native visual
contracts and 126 mobile contracts (144 tests total); both workflow files parse as YAML. The mobile
suite used the existing API image with a read-only source mount and fixture-only in-memory data.
Its first attempt exposed a read-only test-data mount error; the isolated fixture mount resolved it.
The temporary test container was removed automatically. No simulator verdict has been claimed yet.

The follow-up source repeats the 144 preparation tests successfully (mobile contracts: 7.297 s).
It adds actual measurement-ring clearing, two flag edge drags, hazard switching while zoomed,
both named nine-hole choices beside the 18-hole venue, and consistent 220-yard fixture movement.
The first scaffold source's ordinary CI and Native CI passed; exact final-head simulator evidence
is still required. No opt-in audit test execution is inferred from ordinary Native CI.

First dispatch: [38136927473](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38136927473),
source `678eca1b`, Xcode 26.3 / watchOS 26.2. Ten methods executed on every face; 41/46 mm
had six failures and 49 mm seven. The artifact gallery is partial, not a passed whole-round audit.
Ordinary CI `38136912931` and Native CI `38136912932` succeeded; both artifact sets were retained.

Test corrections use the actual Switch for auto-shot, directional drags on the actual ScrollView,
and explicit visual-centre pointer taps. A failed product page transition is preserved as an
observation with screenshots; any fixture recovery is explicitly named before later pages run.
DEBUG-only viewport telemetry distinguishes injected zoom from the state actually shown.
The collector records terminal test counts and rejects missing, skipped or empty audit evidence.
The corrected source needs a new documented dispatch; the first failed attempt remains evidence.

Follow-up preparation: 7 audit-tool regressions, 12 visual contracts and 126 mobile contracts
passed (145 total; mobile 7.181 s). A collection pass is distinct from a product UX pass:
`observation--*.json` retains failed expectations; named recovery screenshots identify injected
boundaries. Actual viewport/page metadata accompanies each screenshot where instrumented.

Second dispatch: [38140105793](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38140105793),
source `ab1732e5`. Every face executed ten methods with zero skips; 41/46/49 mm retained
101/171/122 PNGs and 12/12/13 recorded observations. Six/seven/five methods passed respectively.
46 mm completed nine-hole scoring/save and reached the ninth-hole offline restore in the 18-hole flow.
Ordinary CI `38140032223` and Native CI `38140032219` succeeded. Remaining coverage is partial.

The next driver revision uses real slow scroll flicks and stops as soon as a target is hittable,
uses the actual “继续本场” restore control, and captures transient wheels/undo windows without
slow control enumeration. An unresponsive manual + is retained as a finding before a named
pending-candidate injection allows the remaining controls to be inspected. This does not prove
manual admission on that face or change product behavior. Follow-up preparation: 145 tests passed
(mobile contracts 10.293 s); actual new-source Native/runtime evidence is still required.

Owner expansion (#417 comments 6111380071 / 6111790655) requires element-level evidence, realistic
20–60 s tempo, adversarial gestures, physical-size inspection and comparison with wrist golf UI.
The driver now has sixteen methods: the original ten flows plus picker repetitions, background
resume, repeated page/plan/map gestures, navigation/settings recovery, score-band/fairway/cancel
and hole-grid/scorecard/finish/turn controls. Fixtures may seed a screen or draft for coverage, but
never change production timers, hit targets, gestures or callbacks. Actual navigation recovery and
injected recovery are named separately.

The #419 picker uses real 4 s idle / 2.5 s settled closure. Whole-tree inventories occur once per
distinct stable screen; transient picker measurements and gestures explicitly reopen when needed.
Per-attempt JSON stores expected and actual drafts, gesture, validity, frames and exact step outcome.
An unavailable prepared control is not a dispatched gesture failure. XCTest action duration is
named xctestActionMs: it includes synchronization and cannot prove 300 ms visible feedback.
Crown, wrist detection, glove/wet-finger operation and paired-phone notifications remain hardware
boundaries. Source font tokens are cross-checked with actual frames/images; a nominal font size is
not a measurement of its scaled rendered glyph.

The physical artifact preserves simulator pixels, records actual pixels-to-mm dimensions and
includes physical-review.html, print-at-100% instructions and a 5 mm calibration ruler. DPI tags
and enlarged chat images alone are not evidence of physically wearing the watch. Bright/glare
versions are review aids, not photometric sunlight tests.

Expanded preparation on homeserver: eight collector/physical-export checks passed, including
unmodified pixels and actual-mm HTML sizing. Two earlier expanded attempts (38179866784 /
38180807102) failed compilation before any UI method ran; they are retained harness diagnostics,
not product findings. Corrected exact-head runtime evidence is still required.

Expanded source 2f746a23 / run 38182426066 also stopped before any UI method: a DEBUG AOD
metadata assignment was incorrectly in teardown (no aod parameter). It is moved into launch.
The exact failure log/artifacts are retained at operations/watch417-run38182426066; no product
verdict is inferred from that compile failure. Other new Swift declarations produced no errors.

The corrected full run 38182935895 / exact scaffold head 1ef62984 completed all sixteen methods
on every face, with zero skips. 41/46/49 mm retained 252/343/334 PNGs and 11/14/12 passed methods.
Failures and 132/131/61 raw observations remain visible. Evidence, motion, physical/glare exports
and public comparison receipts live under operations/watch417-wide-audit-20261012.

Before publishing product success rates, the follow-up fixes three collection errors: sub-second
predicate waits produced false negatives despite correct recorded final values; repeated live frame
queries outlasted the 49 mm picker timeout; identical viewport identifiers could read the other page.
The new driver uses immediate state checks, immutable accessibility snapshots, rejects non-finite
frames, names each page's telemetry and tries shot/undo without spending the undo window on capture.
An explicit control-recheck runs four methods (09/11/13/17) and is recorded as partial coverage;
it cannot pass the full seventeen-method collector gate. Timers/product controls remain unchanged.
Nine remote preparation checks pass; two workflow YAML files and thirty Bash sections validate.

Control recheck 38188153210 at 8e6feee6 ran four methods on each face, no skips:
41/46/49 mm 3/1, 2/2, 4/0 pass/fail and 51/39/63 PNGs. P1 first-pointer manual
shot 49 mm 0/5 (41/46 mm 5/5) is published in #417 comment 6115815445.
The small-face picker coverage still raced automatic closure during a live-frame query.
The follow-up caches measured frames for real pointer taps/drags and adds every
putts/penalty start/target pair. `picker-recheck` explicitly collects only methods
11/18, never claims a complete eighteen-method run, and keeps production timers.
Preparation: nine audit regressions plus the viewport contract pass (10 tests,
0.480 s) in the existing API image; two YAML files / thirty Bash sections validate.

Picker supplement 38191363704 / c1d5c876 executed both selected methods on all faces,
no skips, all passed; 58/60/58 PNGs. Valid start/target reachability was 61/61 on
41/46 mm and 60/60 on 49 mm, with one invalid preparation. Repeated gesture trials
still spent the production timeout sampling state between opening and input, so
their partial rates are not confirmed product defects. The follow-up makes each
trial a fresh production chip tap followed immediately by pointer input, sampling
state beforehand. It does not change any product timer, gesture or hit region.
Nine remote collector/physical-export regressions pass (1.120 s). Scoped native
evidence is required before claiming those first-try gesture rates are complete.
