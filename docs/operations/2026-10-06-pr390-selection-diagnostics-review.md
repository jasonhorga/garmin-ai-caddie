# PR #390 exact-head diagnostics review

Reviewed head: `dbd23b6a7c9b3c463cd6dc444357416b546fa405`.
Native run: `37534418849`; Source run: `37534418658`, both green.
This is independent of #389's product enrollment fix and remaining tee-tap P2.

The journey now asserts that its selected course exists and is selected before
looking for the back half. Its test class stops on the first failure. The
selection helper captures a PNG and tree before returning an unselected tile.
Original back-half and complete-prep assertions remain unchanged. No waits,
acceptance weakening or product/UI behavior changes are introduced.

Homeserver's independent `tests.test_mobile_contracts` and
`tests.test_native_visual_parity`: **129 tests / 11.478 s / OK**, including the
new order/evidence contract. PR description says 131; this review uses the
actual exact-head count. Downloaded tested files match Git source hashes:

- RealFlowUITests.swift: `df60d5ff6c85d9bfed9ebe74dd1616fda1a333d10050998c4c59689e633875fe`.
- test_mobile_contracts.py: `80f5c4ee46ee14d279759c0de346cc997b44d4823c458729bd861e804332c8ba`.

Native's verified build artifact names compiled merge
`4e8d90165f11c3df9ed189d902a15c3aa3ce0aa4`; its mobile/ios tree equals
the PR head. All three ZIP SHA-256 digests pass; every one of 89 iOS and 47
Watch design PNGs equals the individually reviewed #387 design baseline.
The automatic Native run does not exercise the full-live failure branch;
there is no new runtime/physical-device acceptance claim.

Evidence root: `/home/jason/garmin-ai-caddie-data/operations/pr390-dbd23b6a-20261006`.
Artifact IDs/digests/PNG hashes, Native log, source archive, test log and
snapshot-cleanup receipts are retained there. The named read-only snapshot
and --rm test container are closed. No worktree, dependency installation,
service, tunnel, port or named volume was created.

Verdict posted in comment `6027263370`: no blocking findings. Merged at
23:22:49 UTC as `469f0d5de2977985cc5ff1749a62bb2cf9b1fd5a`; branch deletion
verified with Git ls-remote. Snapshot/container closed at 23:21:30 UTC; local
helpers removed after byte-identical backup and open-handle checks. Cleanup
allow-list and recoverable originals remain in the persistent evidence root.
This does not close #389's separately reported P2 6026685168.
