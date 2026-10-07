# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-07 04:28 UTC
**Canonical branch:** `main`
**Latest integrated code:** `469f0d5de2977985cc5ff1749a62bb2cf9b1fd5a` (#390)
**Latest review:** exact-head 854f4e0f source/Native review and resource closure.
**Current slice:** `PR-389-HALF-START-ENROLLMENT-REVIEW` — `evidence-open`

## Current state and deduplication

Claude restored. #389 is open; #387/#388/#390 merged and branches deleted.
#389 current head **6fea02399ab4136455cf333ebf1660388c372211**, branch
`claude/half-start-queue-whole-course-20261006`, rebased on main/#390.
Author **6030082845** read: exemption now queries AX subtree, pure bottom
rule and partial/full White/real Start behavior test added. Code confirms
geometric containment removed, original acceptance assertions intact.
Source **37565345697** passed; independent **132 / 6.398 s / OK**.
Snapshot/container closed. Automatic Native **37565345670** passed,
terminal **87600** closed; all three ZIP digests/136 PNG comparison pass.
Compiled merge `d756a6ec97e9a80b253c3b710599f66756199b56` has no mobile/ios diff.
Live **37567463537** dispatched 03:35:35 UTC, exact head 6fea0239,
`capture_scope=review`, fixture=false/preflight=true against retained Build80.
White + white-T + start-page assertions intact; no full nine-loop rerun.
Origin/tunnel preflight 200: 0.007 s / HTTP/2 1.179 s. Observer manifest backed up.
Progress comment **6030396620** posted; posting terminal **5195** closed.
Live Native terminal **66412** ended `status=completed conclusion=success
failed_jobs=none` after the first observer hit a transient GitHub TLS timeout.
Review scope executed 10 tests / 0 failures (TeeSelection 8 tests / 521.913 s),
including the pure viewport ownership test. Live artifacts `real-screenshots`
ZIP digest `sha256:be78c68896c31d1cf9e53c7c0b86f4a8cd8d7b0d7872dbc7063e590ee0e27d77`
verified: 34 PNGs plus trees. White selected tree and screenshot show
`start-round-primary-action` = `从 前九 开始 · 白 T`; the app remains on
`开始一场` until explicit Start. No P1/P2 remains for this head.
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
When reading a waiter receipt, use its **last matched event**: it can ignore
an earlier own CI event before accepting a different PR event.
Preserve dirty `ops/pr_feedback_monitor.sh` and unrelated older `.codex-*`.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume existing feedback cursor;
  exact head/tests/Native artifacts/screenshots, P1/P2/nonblocking verdict,
  merge/delete only when clear. No second monitor.
- `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`: exact-head tests,
  automatic Native artifacts and live White/padded-footer AX proof before merge.
- `PR-387-IOS-JOURNEY-REGRESSION` — `blocked`: live proof accepted on #389;
  integration waits for #389 merge.
- `LIGHTWEIGHT-MAP-FIT-LABELS` — `queued`, nonblocking, author acknowledged:
  facts maps hug left edge / club labels overlap `洞位图`, comment 6026853016.
  Separate follow-up after #389; examples in selector review.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking: dark system status-bar text
  on dark map/review pages.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner's paired iPhone/Watch test.
  Native is simulator evidence; Watch route marker does not prove geometry
  readiness (`watch-round-seeded.png` is a waiting page).

## Live verification baseline

- **0.1.0 (80)** internal TestFlight, Apple **VALID / IN_BETA_TESTING**,
  operation=list/external=false; app/API/sync SHA
  `3614bf6f3805479f8d13de65eeec4f0ad7871f22`.
  Text provider static, Gemini vision only; no production switch/external release.
- Passed: live Native **37426762320**, TestFlight **37438559636**,
  Apple read-only **37440770465**. IPA **11400009027**, ZIP SHA256
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
  Provenance/origin/backend and both app/watch bundle versions verified.
- Synthetic pin sheet HTTP 200/18.901 s; exact date/three holes/front facts.
  HTTP/2 package 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  tunnel 2.10–2.34 s, HTTP/2/200.
- Live origin `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production `aicaddie-release-d7f69971-production-20260925`, port 39055,
  revision `d7f699712f7ac6cba41d97c420c405e090625caf`.
- Persistent evidence root `/home/jason/garmin-ai-caddie-data/operations`;
  release `release-main-3614bf6f-20261006`; #389 roots
  `pr389-56022d32-20261006` / `pr389-854f4e0f-20261007`;
  #390 `pr390-dbd23b6a-20261006`. Source/ZIPs/logs/receipts retained.

## Owned resources and blocking boundary

- No implementation worktree, active snapshot/test/render container, download
  process, observer/sampler, CI or feedback waiter at review closure.
  Native verifier **45268** and previous feedback **59022** completed.
- 6fea0239 snapshot/container closed after source backup/use checks; Native
  wait **87600**/artifact **57305** closed. Observer **23490** closed after
  GitHub TLS timeout (not a CI verdict); closure receipt confirms sampler ended.
  Same live run **37567463537** resumed in observer terminal **66412** and
  completed; sampler/waiter closure receipt retained, no feedback waiter.
  Helpers backed up in
  `operations/pr389-6fea0239-20261007`, expiry Oct 8 03:22 UTC;
  no worktree/deps/service/port/volume. Original image-copy expiry unchanged.
- Current #389 snapshot/container closed after archive/use checks. Six local
  helper/body copies removed after verified remote backups/fuser checks;
  allow-list/receipt `pr389-854f4e0f-20261007/.codex-pr389-854f4e0f-local-cleanup.json`.
  #390 and earlier #389 helpers closed; older unrelated resources protected.
- Local `.codex-pr389-56022d32-live-review` comparison copies remain,
  expiry **Oct 7 21:15 UTC**; persistent originals on homeserver.
  Next feedback wait may timeout at that expiry for exact allow-list cleanup.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089,
  image `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`;
  matching full-SHA sync image retained for owner tests.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110;
  isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13, exact release allow-list retained. Production DB/volume protected.
- Capacity **65 GiB disk / 4.5 GiB available RAM**.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`;
  SHA256 `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `blocking-waits/feedback-cursor`: never edit/delete.
- Same-turn terminal → clock.sleep(300000) → one write_stdin until its one-line
  terminal result. No idle CI/ps/state/log/liveness polling, independent waiter
  tmux, duplicate monitor or CI-only commits. Existing feedback timer unchanged.
- Every GitHub comment/review ends `_Generated by Codex_`; commits have
  `Generated-by: Codex`. Own commits/CI ignored by broad waiter.

## Next action and stopping

Post exact-head approval with the live screenshot/tree evidence, merge #389
with exact-head lock, delete its branch, then update this ledger with the
merge and closed-resource receipt. Retain all live artifacts and receipts.
No weakened assertions or CI-result-only bookkeeping commit.
Quiet interval suspended while #389 open. Once none remain establish a fresh
conservative baseline; stop after **48 quiet hours/no open PRs** or absolute
**2026-10-09 23:59 UTC**, with owned-resource handoff. Own events never reset it.
Keep ledger ≤200 lines/current-only; archive superseded detail verbatim.
After compaction read ledger, inspect Git/agent status, resume this slice.
