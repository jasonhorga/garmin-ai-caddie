# PR #389 viewport exemption review

Reviewed head `854f4e0f8fd375aef4f6900626bb5f216c362259`, rebased on main
`6b6a6caa` with #390's selection diagnostics retained.
Source run `37563682442` green; automatic Native `37563682445` pending at intake.

The product acquisition code and its behavior tests are unchanged from the
accepted `56022d32` live run. The only new App delta is the padded footer's
accessibility container. Both UI test helpers share the new viewport rule;
pre-tap visibility, White selection, white-T action label and remaining on
the start page are asserted. Selection-failure PNG/tree evidence from #390
survives the rebase. No waits or acceptance assertions are weakened.

P2 comment `6030036864`: `UITestViewport.swift:37` exempts a target when its
frame is contained in the footer frame. Geometric containment does not prove
accessibility-tree ownership. With an 852pt window, ordinary viewport bottom
818, footer y=749.7–818 and a covered White row y=755.7–812, that exemption
leaves bottom=818 and returns fullyVisible=true. This is a static control-flow
counterexample; it does not claim a new reproduced simulator tap.

Restrict the exemption to the pinned area itself or an actual descendant,
and check partial/full occlusion separately from a legitimate Start child.
The string contract currently asserts `frame.contains(target)` exists and
therefore cannot establish the intended behavior. Preserve the White,
white-T and start-page assertions; run targeted live only after correction.
No unchanged/current-head full live is dispatched while this P2 is open.

Independent homeserver mobile-contract/native-parity tests:
**132 tests / 10.020 s / OK**, including the new source contract. Automatic
Native `37563682445` reached terminal success. All three ZIP digests pass;
89 iOS / 47 Watch PNGs each match the individually reviewed #387 baseline.
Compiled merge `d95bf0f69afdbc62d40fc89a38441b0a5ad4f615` has no mobile/ios
differences from the PR head. No new runtime/physical-device acceptance claim.
The exact source archive, test log, cleanup receipt
and backed-up helpers live at
`/home/jason/garmin-ai-caddie-data/operations/pr389-854f4e0f-20261007`.
Snapshot and --rm test container are closed; no worktree, dependency install,
service, port, tunnel or named volume was created. Six local helper/body
copies were removed after backup/hash/open-handle checks; all originals and
the exact cleanup allow-list/receipt remain in the persistent evidence root.
P2 6030036864 was updated in place with the completed validation; no merge.

## Final exact-head review — 6fea0239

The correction was reviewed at exact head
`6fea02399ab4136455cf333ebf1660388c372211`. Independent remote checks passed
(132 tests / 6.398 s), Source `37565345697` and automatic Native
`37565345670` passed; the Native design artifacts matched the reviewed #387
baseline (89 iOS / 47 Watch PNGs).

Targeted live Native `37567463537` used `capture_scope=review`,
`fixture_mode=false`, live preflight, and backend revision
`3614bf6f3805479f8d13de65eeec4f0ad7871f22`. The one bounded observer resumed
after a transient GitHub TLS timeout and ended with
`status=completed conclusion=success failed_jobs=none`. Its 114 health samples,
API access log and closure receipt are retained under
`/home/jason/garmin-ai-caddie-data/operations/pr389-6fea0239-20261007/`.

The review-scope run executed 10 selected tests with 0 failures, including
`testViewportExemptsOnlyTheBandsOwnChildrenNotRowsScrolledBehindIt` (pure
behavior check) and all TeeSelection tests. Runtime artifact `real-screenshots`
was verified by ZIP digest (`be78c688…e27d77`), with 34 PNGs and accessibility
trees. `04-white-tee-selected.png` shows White selected; its tree reports
`start-round-tee-white` as Selected and the actual descendant
`start-round-primary-action` label as `从 前九 开始 · 白 T`. The footer is
`start-round-pinned-actions` at y=749.7–852, while the Start button is its
child at y=759.7–810.0. The run remained on `开始一场`; no implicit Start tap
occurred. `03-tee-row` retains the pre-tap state and `04-white-tee-selected`
provides the post-tap proof. No P1/P2 remains for this head.
