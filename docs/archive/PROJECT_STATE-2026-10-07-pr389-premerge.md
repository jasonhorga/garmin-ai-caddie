# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

The following ledger detail was current before PR #389 merged. It is retained
verbatim for audit reference; the live ledger and final review document are
authoritative.

Prior head 854f4e0f Source/Native evidence below remains distinct.
Author **6029824432 / 6029848118** read; superseded `666495f0` needs no review.
Four acquisition-lifetime fixes and their behavior tests equal accepted
`56022d32`; only new App delta is padded footer accessibility grouping.
Original full-live **37534118109** passed back-nine→front-nine / relaunch /
complete prep journey (**253.888 s**), main flow **1,065.894 s**.
All **91 iOS / 13 Watch runtime PNGs** reviewed; transport samples/closure
retained. That original enrollment proof remains accepted.
Prior 854f4e0f exact-head independent **132 tests / 10.020 s / OK**.
Source **37563682442** / automatic Native **37563682445** passed.
All three Native ZIP digests pass; every **89 iOS / 47 Watch** design PNG
equals individually reviewed #387 baseline. Compiled merge
`d95bf0f69afdbc62d40fc89a38441b0a5ad4f615` has no mobile/ios diff from head.
**P2 6030036864, old head:** `UITestViewport.swift:37` uses
`frame.contains(target)` to exempt supposed footer children. A scroll row
fully behind the footer gets the same exemption and is marked fullyVisible.
Static counterexample: viewport bottom 818, padded footer y749.7–818,
covered White y755.7–812. This is source logic proof, not a new simulator tap.
Require actual AX membership/identity, partial/full occlusion behavior checks;
preserve White-selected / white-T action / no implicit Start assertions.
Code correction accepted in 6fea0239; live verification now in flight. Existing
review scope includes shared RealFlow helper, edit and all TeeSelection tests.
P2 updated in place with completed validation. No merge.
Review: `2026-10-07-pr389-viewport-membership-review.md`.
Prior direction reply **6027404675** answered author **6026596438**:
separate viewport fix, not unchanged-head rerun. Both handled.
#390 review **6027263370**, exact head `dbd23b6a…`, 129/11.478 s OK,
Native 37534418849 / Source 37534418658; merged `469f0d5d`.
Old heads/runs/comments deduplicated in dated archives; new substantive
feedback/head actionable. Own events/duplicates never reset quiet time.
