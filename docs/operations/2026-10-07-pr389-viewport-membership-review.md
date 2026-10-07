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
