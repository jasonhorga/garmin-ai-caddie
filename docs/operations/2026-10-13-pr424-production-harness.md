# PR424 production element acceptance

Review base: `6eef9e13cfe191e2668dfd41cd80c5c94a6e9e97`.
Owner: Codex, findings/test scaffolding only. Claude implements product fixes.

The DEBUG fixture uses `WatchRoundContainerView` and `WatchRoundModel`
unchanged. It supplies synthetic course/GPS facts and a deterministic second-loop
loader; it does not replace score, navigation, gesture, persistence, or menu
callbacks. Existing sample map pixels are repeated and explicitly remain fixtures.

Run `watch-runtime.yml` on `codex/pr424-production-harness-20261013` with
`runtime_scope=simulator-audit`, `audit_selection=production-elements`.
Five hosted Watch simulator jobs cover 41/42/45/46/49 mm on the newest installed
watchOS. They retain screenshots, video, native AX metrics, requested pointer
coordinates, before/after model state, and exact production/harness revisions.

Five methods cover:

- Six score steppers and three row selectors on Par 4/Par 3.
- The fairway sheet, each side, clearing, back, score save/cancel, Par 3 visibility.
- Main-menu first taps, hazard-next, ten fresh first manual-shot/undo trials.
- Continue/same-nine/stop-after-nine, plus A/B `G:all` turn paths.
- Change/drop second-nine via the real menu, plus score persistence after relaunch.

Each target gets five fresh centre trials and five fresh centre+8 pt trials;
missing or unreachable controls are invalid attempts, never inferred successes.
Six bounded touch swipes may reveal scrolling controls; no AX implicit scroll
or injected recovery counts as acceptance. Pointer centres must be in the window
above the measured lower input band. This does not prove entire-row visibility.

The 46 mm job also runs two positive-expectation phone-reseed regression tests
and retains their separate failure log/result. A completed evidence-collection
method is not a passing interaction: evaluate every JSON receipt.

Real Crown, WCSession delivery, GPS reception, wrist motion, locked/background
behaviour, and sunlight visibility remain hardware evidence boundaries.
The physical-scale exports retain the original pixels and calibrated dimensions.

Remote Python preflight: existing release image, no dependency installation;
collector 11 tests, mobile contracts 126 tests, visual parity 12 tests passed.
Native CI on the production base: `38382863562`; ordinary CI: `38382863189`.

Initial runtime `38388376104` failed to compile the DEBUG fixture because its
new trace string incorrectly escaped a quote inside Swift interpolation.
It executed no control trials and supplies no product acceptance evidence.
The corrected trace is committed before rerunning the same production base.
