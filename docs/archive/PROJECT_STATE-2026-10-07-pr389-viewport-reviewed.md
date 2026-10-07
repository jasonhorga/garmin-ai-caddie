# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Verbatim ledger before closing head 854f4e0f source/Native review and helper copies.
Use the short live ledger for the current queue.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-07 03:01 UTC
**Canonical branch:** `main`
**Latest integrated code:** `469f0d5de2977985cc5ff1749a62bb2cf9b1fd5a` (#390)
**Internal app/API/sync source:** `3614bf6f3805479f8d13de65eeec4f0ad7871f22`
**Current slice:** `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`

## Current status and deduplication

Claude is restored. #389 open; #387/#388/#390 merged, branches deleted.
#390 reviewed at `dbd23b6a7c9b3c463cd6dc444357416b546fa405`; independent
**129 tests / 11.478 s / OK**. Source `37534418658` / Native `37534418849`
green; all three ZIPs verified, 89 iOS/47 Watch PNGs equal approved baseline.
Compiled merge `4e8d9016…` has no mobile/ios diff from head. Review comment
**6027263370** posted; merged **23:22:49 UTC**, merge `469f0d5d…`, branch
deleted. Snapshot/container/helpers closed; evidence retained. Failure branch
not executed by automatic Native; #389 viewport P2 remains open.
Queued old #389 head/runs/comments deduplicated through reply 6025783925.
Observed review/cleanup pushed as `91eebbf1`; no CI-bookkeeping commit.
Current #389 head `854f4e0f8fd375aef4f6900626bb5f216c362259`;
branch `claude/half-start-queue-whole-course-20261006`.
Author **6029824432 / 6029848118** read: viewport fix plus rebase onto
main/#390; all original assertions retained. Source **37563682442** passed;
automatic Native **37563682445** passed. Review new head's
full padded footer exclusion, target exemption, pre-tap checks and evidence;
then exact tests/artifacts and targeted live White acceptance.
Old head `56022d32…` product enrollment accepted; verify no product delta.
New P2 **6030036864** posted: geometric `frame.contains(target)` exempts
covered scroll rows as if they were footer descendants. Require actual AX
membership/identity; static covered-White counterexample is sufficient.
No current-head full/live dispatch. Independent **132 / 10.020 s / OK**;
source snapshot/test container closed after source-backup and use checks.
Four request-lifetime P2 paths resolved: shared eligibility, generation check
before cleanup, account clear and active-job explicit-intent registration.
Source **37515958115** / automatic Native **37515958145** passed.
Independent homeserver **130 tests / 8.912 s / OK**; pause/resume and account
rebind regressions passed. Snapshot/test container closed; no install.
Initial live **37519627055** failed with an empty course list before selection;
its video was verified/reviewed. Response gaps/tunnel cancellations establish
delayed requests, not the responsible network layer. Author RCA **6025352540**
read; reply **6025783925** handled. No blanket upstream/tunnel RCA claim.
Observed unchanged-head full/live **37534118109** used original assertions:
**后九→前九 / relaunch / complete prep journey passed (253.888 s)**;
main full flow passed (1,065.894 s). Only White-selection test failed.
Five evidence ZIP digests pass; all **91 iOS / 13 Watch runtime PNGs reviewed**;
all **89 iOS / 47 Watch design PNGs** byte-identical to the approved baseline.
105 origin health samples all 200 (max 4.488 s); tunnel 103/105 200.
Two tunnel connect timeouts (21:46:50 / 22:04:23) were away from the White tap.
Observer/sampler/waiter closed **22:24:57 UTC**, receipt retained.
**Blocking P2 6026685168:** White frame y=730.7–787 pt overlaps fixed Start
y=759.7–810 pt; `03-tee-row.png` cuts tee circles in half. Helper excludes
only home indicator. White tap at 22:06:33 starts Blue/前九 round; health
at the tap is HTTP/2 200 / 0.388 s. Fix full usable viewport/padding, recheck
immediately before tap, preserve White + white-T action assertions, ensure
start page remains until explicit Start and save screenshot/tree on failure.
Inspect RealFlow equivalent. No fixed sleeps, weakened assertions or unchanged
full-live rerun. Author claims fix; awaiting exact-head source/Native/live proof.
Author observation/proposal **6026596438** read from resumed cursor;
choose its second option via **6027404675**: separate viewport fix on current
main/#390, then targeted White-selection live; never unchanged-head rerun.
Visual follow-up **6026853016** posted: lightweight facts maps hug left edge
and upper club labels overlap `洞位图`. Examples/expected fit and label
avoidance recorded in `2026-10-06-pr389-live-selector-failure-review.md`.
Nonblocking and separate from #389 enrollment correctness.
Watch route marker proves page appearance, not precise map readiness:
`watch-round-seeded.png` is a waiting page. Native is simulator evidence.
Old heads, run IDs and handled comments are deduplicated in dated archives,
latest `PROJECT_STATE-2026-10-06-pr389-observed-live-reviewed.md`.
New substantive comments/heads actionable; own comments/commits/CI and
duplicates never reset quiet time. Preserve dirty `ops/pr_feedback_monitor.sh`.

## Unfinished work

- `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`: review corrected
  head/tests/Native/targeted live White before approval/merge.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: all repo PR events; required CI,
  source and screenshots before P1/P2/nonblocking verdict; merge/delete if clear.
- `PR-387-IOS-JOURNEY-REGRESSION` — `blocked`: live proof passed on #389;
  integration waits for #389 approval/merge.
- `LIGHTWEIGHT-MAP-FIT-LABELS` — `queued`, nonblocking: center facts bounds
  with margins; keep club labels clear of fixed controls (6026853016).
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking: dark system status-bar
  text on dark map/review pages.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner paired iPhone/Watch test;
  Native captures do not establish physical-device acceptance.

## Live verification baseline

- **0.1.0 (80)** internal TestFlight: Apple **VALID / IN_BETA_TESTING**,
  operation=list/external=false. App/API/sync SHA `3614bf6f…`.
  Text provider static; Gemini vision only; no production switch/external release.
- Passed: live Native **37426762320**, TestFlight **37438559636**,
  Apple read-only **37440770465**; 136 design PNGs equal approved #382;
  92 iOS/13 Watch runtime frames reviewed.
- IPA **11400009027**: provenance/backend/origin and both bundle versions
  verified; ZIP SHA256
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
- Synthetic pin sheet HTTP 200/18.901 s, exact date/three holes/front facts.
  HTTP/2 package 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s;
  four tunnel requests 2.10–2.34 s, HTTP/2/200.
- Live origin `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production `aicaddie-release-d7f69971-production-20260925`, port 39055,
  revision `d7f699712f7ac6cba41d97c420c405e090625caf`.
- Persistent evidence root `/home/jason/garmin-ai-caddie-data/operations`;
  Build80: `release-main-3614bf6f-20261006`.
  #389: `pr389-56022d32-20261006` with both `full-live-<run-id>` and
  `observed-live-37534118109`. Originals, ZIPs, logs and receipts retained.

## Owned resources and waits

- No implementation worktree, active review snapshot/test/render container,
  artifact downloader, observer, health sampler or CI waiter.
  Final observed-run terminal **94095** closed; downloads/render/copy
  **97479 / 25530 / 41033** finished. New 324 MB video not needed/downloaded.
- New #389 evidence `operations/pr389-854f4e0f-20261007`; source/tests and
  closed snapshot/container receipts retained. Helpers backed up; expiry
  Oct 8 03:08 UTC. Native 37563682445 terminal success; artifact verification next.
- #390 snapshot/container closed **23:21:30 UTC**; all five helpers removed
  after backup/hash/use checks. Evidence and cleanup manifest/receipts retained
  in `operations/pr390-dbd23b6a-20261006`; no worktree/deps/service/port/volume.
- Sixteen exact local helpers removed after byte-identical remote backup and
  fuser no-open-handle checks. Persistent allow-list/receipt:
  `pr389-56022d32-20261006/.codex-pr389-56022d32-local-cleanup.json`.
  Unrelated/older `.codex-*` files and dirty monitor script protected.
- Local `.codex-pr389-56022d32-live-review` comparison copies retained,
  expiry **Oct 7 21:15 UTC**; persistent originals on homeserver.
- Local `.codex-pr389-tee-direction-reply.md` is a backed-up PR body copy,
  expiry Oct 7 23:36 UTC; no process/container/source snapshot associated.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089;
  API image `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`.
  Matching full-SHA sync image retained for owner tests.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110.
  Isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13; exact release allow-list retained. Production DB/volume protected.
- Last capacity **65 GiB disk / 4.4 GiB available RAM**.
- Feedback terminal **59022** completed with new head's Source run
  **37563682442**; receipt `blocking-waits/wait-feedback-pr--20261006T234215Z-3787267.log`.
  No waiter active during code intake; cursor unchanged. Old events deduplicated.
- Deployed waiter
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait_for_conclusion.sh`;
  SHA256 `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `blocking-waits/feedback-cursor`; never edit/delete.
- Same-turn background terminal → sleep 300000 ms → one write_stdin until
  one-line conclusion. No idle gh run view/ps/state/log polling, new monitor,
  independent waiter tmux or CI-only commits. Existing gh-feedback timer unchanged.
- Every GitHub comment/review ends `_Generated by Codex_`; Codex commits
  have `Generated-by: Codex`. Own commits/CI ignored by broad waiter.

## Next action and stop conditions

Wait for automatic Native 37563682445 once; verify head/artifacts/PNG
correspondence. Keep P2 6030036864 open; await author membership fix, then
review its exact head and targeted live White selection before merge/delete.
No unchanged full-live rerun; no CI-only bookkeeping commits.

Quiet interval suspended while any PR is open. Once none remain establish a fresh
conservative baseline; stop after **48 quiet hours/no open PRs** or absolute
**2026-10-09 23:59 UTC**, with owned-resource handoff. Own events never reset it.
Keep ledger ≤200 lines/current-only; archive superseded text verbatim.
After compaction read ledger, inspect Git/agent status, resume this single slice.
