# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before PR397 source-review post, 2026-10-09 05:57 UTC.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 05:41 UTC
**Canonical branch:** `main` at `d02a754d`
**Latest integrated code:** `3bd1ce4dba4d5920d5e9d18bfe18b879ac612a9f` (#396)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and feedback deduplication

Claude restored and implementing. Open non-draft **#397**, branch
`claude/course-options-cache-20261009`, exact head
`ba7fc93259b277c07591ac1b8ffd49a2ef98aaf9`, base **d02a754d**.
Purpose: per-account cached `courses/options`, refreshed after instant cache restore;
failed refresh publishes only downloaded rows, disk catalogue kept intact.
Owner informed of UX boundary: while waiting, cached uninstalled rows can be
visible and an offline start may fail/retry; after confirmed failure only local
rows remain. No map pre-download proposed, no approval question pending.
- Source candidates: **two P2**, prepared in
  `.codex-pr397-ba7fc932-review.md`, **not posted yet**; await required Native
  result/artifacts before final initial review. Do not merge this head.
- P2 cancellation: successful await goes to adopt/commit without cancellation
  check; catch checks cancellation only after session side-effect handling.
  Need held success after cancel, verify disk/UI/status unchanged.
- P2 ordering: older refresh failure filters a newer successful catalogue;
  disk-write failure fallback only checks account, so older success can replace
  newer memory-only data. Need shared accepted-result order on success/failure/
  storage fallback, regressions for both paths. These are static source findings,
  not claimed runtime reproductions.
- Independent exact-head remote contracts **122 / 5.330 s / OK**.
  Initial metadata: backend/docker/frontend checks green (**37888259737**);
  required Native **37888259783** still pending then; no Native count/pass claimed.
- #397 `pr_opened`/head/source handled; terminal CI/Native events unhandled.
  Git ref `origin/pr397-review`, no implementation checkout/worktree.
- #396 accepted/merged **00:56:47 UTC**, **3bd1ce4d**, final head **f073a77d**;
  final PASS **6072047793**, branch deletion verified (404), merged source equals
  reviewed head. Detail/window/maps caches account scoped, 40-round cap; owner
  informed evicted older reviews require network.
- #396 CI **37850351795**, Native **37850351747**: **688 iOS / 448 Watch**,
  eight cache tests passed; independent **122 / 5.225 s / OK**.
  Live **37852249384 attempt 2**: **15 total / 1 skipped / 0 failures**, 2 Watch UI;
  exact f073a77d production provenance, eight relevant real PNGs inspected,
  140 Native PNGs identical to #395 reviewed baseline.
  Attempt 1 failed course-here home (one failure); original evidence retained,
  transport root cause unproven. Both attempts handled, dedup by run+attempt.
- #396 author **6069820462 / 6071084617 / 6071929325** and own
  **6069726466 / 6070307513 / 6071163486 / 6072047793** handled; final author
  request was already fulfilled by later PASS. Prior run/head IDs in
  `handled_pr396_events` and dated archives; do not replay.
- #395/#392/#393/#394 and Claude replacement request handled; no repeated release.
- Last external PR open **05:22:18 UTC** (#397); own review/merge/docs CI never
  reset quiet condition. Read last matched event JSON from returned wait log,
  ignore own-CI, never edit/delete cursor.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: accept #397 Native terminal result,
  download/review exact artifacts, post P2s, await author fix through sole waiter.
  New ready PRs actionable; exact-head tests/Native/screenshots, PASS then merge.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking unchanged fixture's
  八号铁 164 label varies; no product regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status/navigation text
  on dark maps/review.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: owner paired iPhone/Watch validation;
  simulator evidence alone does not prove paired readiness.

## Live verification and release baseline

- **0.1.0 (82)** internal TestFlight; upload **37774511661** successful.
  App **6dd96200b199ac8f5ea760719fb295bbc4eea1ef** includes #394,
  **excludes #395/#396/#397**. No newer upload/server deployment claimed.
- Apple read-only **37776197288**: **VALID / IN_BETA_TESTING**, internal group
  contains 82, no external distribution; `internalReady=false` discrepancy
  retained. IPA SHA256
  `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`;
  provenance `operations/release-main-6dd96200-20261008`.
- API `https://caddie.taile36706.ts.net`; backend/sync
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**; production
  `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
- Protected cutover `operations/production-cutover-3614bf6f-20261008`:
  DB dumps/roots/conflict report, newer 7-hole 17742546/candidate 2-hole copy
  retained; candidate ledger suffix **8,426,773 bytes** merged.
  Sync **502 rounds / 501 scorecards / 501 shots / ok / done**.
- HTTP/2 probes **3/3 200**, **1.82–2.57 s**; homeserver success alone does not
  prove Apple-runner path. Persistent root:
  `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- #397 evidence `operations/pr397-ba7fc932-20261009`: source tar, independent
  contracts/manifest/scripts/cleanup log retained. **27,598,059-byte** read-only
  /dev/shm snapshot removed after open-handle/command checks, named --rm
  container absent. Tar SHA256
  `00560a2bf85cb7b39069d9aed92890a68a03ef70bba8d13ea5d0035a9d544cf3`.
  Cleanup **62 GiB free**, production running. No PNG copies planned/created.
- #396 `operations/pr396-f073a77d-20261008`: original tar, contracts, Native and
  live attempts 1/2 ZIPs/artifacts/logs/hashes/reviews/receipts retained; runtime
  and 11 inspection copies closed, originals retained. #395 evidence/runtime
  closure likewise retained. No active review/implementation runtime, browser,
  port, tunnel, private venv or subagent.
  Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
- Stopped candidate `aicaddie-release-3614bf6f-candidate-20261006`, 39089 inactive;
  private root/DB `aicaddie_candidate_3614bf6f_20261006` protected until build82
  acceptance. Stopped rollback
  `aicaddie-release-d7f69971-production-20260925-pre-cutover` protected.
- Release source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`
  expires Oct 13; backups/allow-list retained. HTTP/2 tmux closed.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  No wait pending; next sole terminal in `active_feedback_wait`.
- Pending: **clock.sleep(300000) → one write_stdin**, same turn until one-line
  result; no CI/ps/state/log polling, independent tmux or second monitor.
  Timer unchanged, cursor retained; ignore own-CI; no CI-only commits.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

Start sole feedback waiter; handle terminal #397 Native/artifacts, post two
source P2s plus evidence, then await author's fixed head and same-head verification.
Absolute stop **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Earlier stop requires 48 hours without external PR events and no open PRs;
open #397 prevents it. Same-turn waiting method through deadline.
Ledger ≤200 lines; history verbatim in dated archives. T0541 pending next actual
review/operations commit; no CI-result-only bookkeeping commit.
After compaction read ledger, inspect Git/agent state, resume this slice.
