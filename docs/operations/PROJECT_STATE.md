# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-07 03:11 UTC
**Canonical branch:** `main`
**Latest integrated code:** `469f0d5de2977985cc5ff1749a62bb2cf9b1fd5a` (#390)
**Latest review:** exact-head 854f4e0f source/Native review and resource closure.
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Claude restored. #389 is open; #387/#388/#390 merged and branches deleted.
#389 current head **854f4e0f8fd375aef4f6900626bb5f216c362259**, branch
`claude/half-start-queue-whole-course-20261006`, rebased on main/#390.
Author **6029824432 / 6029848118** read; superseded `666495f0` needs no review.
Four acquisition-lifetime fixes and their behavior tests equal accepted
`56022d32`; only new App delta is padded footer accessibility grouping.
Original full-live **37534118109** passed back-nine→front-nine / relaunch /
complete prep journey (**253.888 s**), main flow **1,065.894 s**.
All **91 iOS / 13 Watch runtime PNGs** reviewed; transport samples/closure
retained. That original enrollment proof remains accepted.
Current exact-head independent **132 tests / 10.020 s / OK**.
Source **37563682442** / automatic Native **37563682445** passed.
All three Native ZIP digests pass; every **89 iOS / 47 Watch** design PNG
equals individually reviewed #387 baseline. Compiled merge
`d95bf0f69afdbc62d40fc89a38441b0a5ad4f615` has no mobile/ios diff from head.
**P2 6030036864, open:** `UITestViewport.swift:37` uses
`frame.contains(target)` to exempt supposed footer children. A scroll row
fully behind the footer gets the same exemption and is marked fullyVisible.
Static counterexample: viewport bottom 818, padded footer y749.7–818,
covered White y755.7–812. This is source logic proof, not a new simulator tap.
Require actual AX membership/identity, partial/full occlusion behavior checks;
preserve White-selected / white-T action / no implicit Start assertions.
No current-head full/live dispatched; await corrected head before targeted live.
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

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: resume existing feedback cursor;
  exact head/tests/Native artifacts/screenshots, P1/P2/nonblocking verdict,
  merge/delete only when clear. No second monitor.
- `PR-389-HALF-START-ENROLLMENT-REVIEW` — `blocked`: author P2 6030036864
  membership fix; review its head and targeted live White before merging.
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

Resume existing same-turn feedback cursor for author P2 correction / new PRs.
Viewport review/cleanup is recorded with archives in this commit. No current-head
full-live rerun and no CI-result-only bookkeeping commit.
Quiet interval suspended while #389 open. Once none remain establish a fresh
conservative baseline; stop after **48 quiet hours/no open PRs** or absolute
**2026-10-09 23:59 UTC**, with owned-resource handoff. Own events never reset it.
Keep ledger ≤200 lines/current-only; archive superseded detail verbatim.
After compaction read ledger, inspect Git/agent status, resume this slice.
