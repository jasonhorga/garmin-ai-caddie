# Watch whole-round simulator audit (#417)

Findings-only audit of main `0882c41c` / Build 86. No product fixes belong in this pass.
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
