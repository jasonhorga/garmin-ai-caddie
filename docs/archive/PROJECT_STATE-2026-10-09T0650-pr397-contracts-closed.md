HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Superseded after exact-head contracts and owned snapshot cleanup.
The following ledger is preserved verbatim.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 06:46 UTC
**Canonical branch:** `main` at `b82c1b66`
**Latest integrated code:** `3bd1ce4dba4d5920d5e9d18bfe18b879ac612a9f` (#396)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and feedback deduplication

Claude restored and implementing. Open non-draft **#397**, branch
`claude/course-options-cache-20261009`, exact head
`58928fac5d241cb52fdf5f8cf995d80878b8db18`, base **d02a754d**.
Purpose: per-account cached `courses/options`, refreshed after instant cache restore;
failed refresh publishes only downloaded rows, disk catalogue kept intact.
Owner informed of UX boundary: while waiting, cached uninstalled rows can be
visible and an offline start may fail/retry; after confirmed failure only local
rows remain. No map pre-download proposed, no approval question pending.
- Initial review **6075192701**: cancellation/accepted-result ordering P2s.
  Author **6075229235** fixed cancellation and catalogue/disk-fallback ordering
  in **cfb65b53**, adding three held-response regressions.
- Required Native **37890979905** failed `native-mobile / Test iOS app target`:
  catalogue consecutive-ticket regression three assertions failed, exit 65.
  Author **6075596162** fixed equal Date tickets in **7c192a1d**: lock-protected
  UInt64 sequence now orders results disk commits and catalogue memory commits.
  CI **37890979986** passed; old Native failure is not new-head evidence.
- Follow-up **6075652720** on exact **7c192a1d** raised remaining ordering P2.
  Catch checks account/cancellation, but invalidates session and logs before
  sequence acceptance. R1 late 401 after R2 success still signs out the current
  session before rejecting the stale failure. Need acceptance before all failure
  side effects and held late-401 regression without UITEST_MODE bypass; preserve
  genuine current 401 sign-out. Static source finding, no runtime claim.
- Author **6075760765** fixed it in **58928fac**: accepts failure sequence before
  any side effect; separate accepted-failure publisher. Two held/current-401
  regressions exercise real sign-out with no UITEST_MODE. Static review clear;
  exact-head verification underway, no final pass yet.
- Current CI **37894021084** green; required Native **37894020995** and live
  **37894476953** pending. Prior 7c CI **37892892060** handled; Native
  **37892892061** not yet consumed. Old live **37889373222 / 37890981619**
  terminal cancellation handled; 7c live **37893343715** author-cancelled.
- Initial **ba7fc932** independent remote contracts **122 / 5.330 s / OK**.
  CI **37888259737** and required Native **37888259783** success confirmed by
  terminal events; Native concluded **05:33:44 UTC**, **692 iOS / 448 Watch**,
  all four new catalogue tests actually passed. Checkout **9db0a9bb**, parents
  **d02a754d / ba7fc932**; complete tree/source diff empty against reviewed head.
  140 PNGs checked: 139 identical to #396 live baseline, changed zoomed map
  matches previously visually reviewed #396 required image (八号铁 164 toggle).
  No new screenshot blocker; updated exact comment **6075192701** with evidence.
- #397 initial/cfb/7c heads and comments **6075000869 / 6075192701 / 6075229235 /
  6075596162 / 6075652720 / 6075760765** handled; initial/cfb and latest CI
  handled. Latest required Native/live still pending. Dedup in
  `handled_pr397_events`; Git ref `origin/pr397-review`, no coding worktree.
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
- Last external reply **06:37:33 UTC** (#397); own review/merge/docs CI never
  reset quiet condition. Read last matched event JSON from returned wait log,
  ignore own-CI, never edit/delete cursor.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: verify #397 exact **58928fac**:
  independent contracts, required Native/images/provenance, same-head live;
  merge only if clear. Do not use initial-head evidence to approve new source.
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
  Native artifacts/log/hashes and updated review retained in same evidence root.
  Artifact terminal **42959** completed and cleared. No pending download/runtime
  or local PNG inspection copy; old-head Native review complete.
- #397 cfb failure diagnostics terminal **73938** completed; retained log
  `operations/pr397-cfb65b53-20261009/native-failure.log`. Latest review body
  `operations/pr397-7c192a1d-20261009/review.md`, comment **6075652720**.
  No source snapshot/container/tar/inspection copies created for cfb/7c.
- #397 latest ownership recorded before verification in
  `.codex-pr397-58928fac-review-manifest.md`, remote evidence
  `operations/pr397-58928fac-20261009`. Planned read-only snapshot
  `/dev/shm/garmin-ai-caddie-pr397-58928fac-20261009`, --rm container
  `codex-pr397-58928fac-contracts-20261009`, expires at owner deadline.
  Capacity: 62 GiB free / 4.7 GiB available RAM; no dependencies/runtime service.
- #396 `operations/pr396-f073a77d-20261008`: original tar, contracts, Native and
  live attempts 1/2 ZIPs/artifacts/logs/hashes/reviews/receipts retained; runtime
  and 11 inspection copies closed, originals retained. #395 evidence/runtime
  closure likewise retained. No coding worktree, browser, port, tunnel, private
  venv or subagent; sole planned read-only snapshot above.
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

Run independent contracts on exact 58928fac; close its snapshot/container.
Then sole waiter for terminal Native/live; inspect artifacts and same-head
provenance, post PASS/merge only if clear. Older heads are not acceptance evidence.
Absolute stop **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Earlier stop requires 48 hours without external PR events and no open PRs;
open #397 prevents it. Same-turn waiting method through deadline.
Ledger ≤200 lines; history verbatim in dated archives accompanies real review
and resource work, not CI-result-only bookkeeping. T0646 pending next commit.
After compaction read ledger, inspect Git/agent state, resume this slice.
