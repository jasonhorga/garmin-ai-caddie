# MAP1 / integration-v2 branch reconciliation

Date: 2026-09-04 UTC
Owner: Codex
Review: Fable 5.1 (read-only; handoff recorded in the session)
Reconciliation branch: `integration/map1-reconcile-20260904`
Expiry review: 2026-09-11 UTC, or immediately after the PR is merged or closed

## Purpose

Record the old `integration/v2` ancestry without changing the tested MAP1
product tree. The merge commit intentionally carries no product-code port. Any
old behavior that remains valuable must arrive later as a small, independently
tested PR.

## Pre-merge refs at decision time

- GitHub default: `integration/v2` -> `b5e17d316f63a82de2c67ecfda271997370f3fe5`
- MAP1 candidate: `codex/p0-p1-p2-checkpoint-20260823` -> `d26feaba91a81e66ba3ff8a6d293a37d563a926a`
- Original line: `main` -> `0f696b8817abcf589e666de6e9ef7d4fcb223b38`
- Merge base of MAP1 and old integration: `a0c0fca8f07b888722561f28b2a10cdf45f84d33`
- Divergence: MAP1 has 287 unique commits; old integration has 46.
- Release anchors: `release/testflight-0.1.0-build-47` -> `d189b3b4`; `deploy/backend-2026-09-02` -> `c1648891`.

After PR #331, the target `integration/v2` points through reconciliation
merge `1775d87a`. Its actual parents are old integration `b5e17d31` (first)
and reconciliation/MAP1 line `a331281a` (second). See
`branch-strategy-20260904.md` for the post-merge policy and ref inventory.

## Merge decision

`79ee08cd` is a history-only merge with parents MAP1 `d26feaba` and old
integration `b5e17d31`. Its tree is exactly the MAP1 tree. It must be reviewed
and merged with a normal merge commit; do not force-reset, squash, or rebase
the target branch.

### Authority correction found during CI

The first full PR scan correctly exposed that `contracts/canonical/authority.json`
had incorrectly listed `mobile/contracts/live_round_event.schema.json` as a
`v1_compatibility_only` legacy adapter. That schema has been the active live-round
wire contract since `69afb323`, and the old `integration/v2` tip already contains
`clientId` and `sync_marker`; MAP1 only adds the target-coordinate fields. Fable's
review therefore recommends removing the erroneous legacy declaration rather than
deleting working fields or weakening the checker. The Watch input schema remains
the only declared frozen adapter. A separate contract-migration decision is still
needed for the historical `sync_marker`/`serverSequence` design debt identified by
the canonical spec; this reconciliation does not claim that migration is done.

## Old integration-only non-merge commits

The 46 old commits include 21 merge commits and the 25 decisions below. No
entry marked `port-later` or `defer` is included in `79ee08cd`.

| Commit | Decision | Reason |
| --- | --- | --- |
| `a9351548` | port-later | Watch green-slope display; MAP1 has backend data but needs a new Watch integration. |
| `000e5af4` | evidence-only | Old moving-GPS recording lane; current Native workflow supersedes it. |
| `e0912d98` | port-later | Green-break arrow projection; verify against the MAP1 map renderer. |
| `e0ff6b9a` | evidence-only | Old Watch touch recording lane. |
| `a860f697` | evidence-only | Old Web video capture lane. |
| `a09223db` | evidence-only | Old GPS-route UI-test workaround. |
| `efda9a3c` | evidence-only | Old demo wait-time tightening. |
| `d9af1db5` | evidence-only | Old single-session recording workaround. |
| `6ae51f30` | port-later | Full prep-response prewarming may improve first-open latency; test cache keys first. |
| `37ce670b` | port-later | iOS review/map loading polish; compare with current review flow. |
| `4c88edb4` | evidence-only | Paced Web demo flow. |
| `69a3f636` | evidence-only | Demo spec consolidation. |
| `bd862256` | evidence-only | Demo-only CI guard. |
| `86cada7e` | port-later | Low-risk user-facing Chinese copy cleanup. |
| `318bd6d4` | superseded | MAP1 viewport/clamp implementation covers the old Watch pill fix. |
| `fa7bbd81` | evidence-only | Debug WatchConnectivity video lane. |
| `10cf7fef` | evidence-only | Debug-only WatchConnectivity hooks. |
| `2de5ef75` | defer | Cache-warmer flake fix; latest canonical CI is already green. |
| `03990bc5` | superseded | Historical board note; `PROJECT_STATE.md` is the live source of truth. |
| `633c71a6` | port-later | Preserve the explicit scorecard pin/green-center contract and tests. |
| `69f0957f` | defer | Broad per-putt green-read feature; requires a separate product decision. |
| `734ae00b` | defer | Hazards/course-updates schemas and live access were not authoritative. |
| `7016a462` | superseded | Old fairway picker; MAP1 has the newer persisted fairway flow. |
| `b98b347f` | defer | Compile-only support for the old fairway picker; revisit only with a new implementation. |
| `16470f8c` | superseded | Old board checklist; retain as history, not current status. |

## Required post-merge checks

1. The target default branch product/runtime tree equals `d26feaba^{tree}`.
   The only intentional additions are this reconciliation record plus the
   authority-manifest correction and its focused regression test; no unrelated
   product code is introduced.
2. Both `d26feaba` and `b5e17d31` are ancestors of the target merge commit.
3. The two release tags still point to the exact release/backend commits.
4. Source CI and Native Mobile CI run against the merge SHA and pass.
5. No TestFlight upload, external distribution, backend deployment, or data write
   is triggered by this reconciliation.
6. Keep old refs and PRs until the later Cloud whole-repository audit is complete.
