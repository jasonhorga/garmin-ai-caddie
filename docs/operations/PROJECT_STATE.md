# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 08:23 UTC
**Canonical branch:** `main`
**Latest integrated code:** `91859eb8d938af6fca6948d4ae3f93bf2f35c1bb` (#397)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and feedback deduplication

Claude restored and implementing. #397 accepted/merged **08:19:46 UTC**,
**91859eb8**; final reviewed head **58928fac5d241cb52fdf5f8cf995d80878b8db18**.
Final PASS **6077199917**, source branch deletion verified 404; all non-doc
merged source equals reviewed head. Local main fast-forwarded, dirty monitor
preserved. Post-merge open PR inventory **08:22 UTC: empty**.
- Account-scoped `courses/options` restores immediately, then refreshes.
  Confirmed failure publishes downloaded rows only, full disk catalogue kept.
  Owner informed pending refresh may show uninstalled cached rows and offline
  start may fail/retry. No map pre-download or approval pending.
- Cancellation/ordering/old-401 P2s addressed; unique locked sequence also fixes
  old Native Date-ticket tie. CI **37894021084**, Native **37894020995**:
  **697 iOS / 448 Watch**, eight catalogue regressions and filtering passed.
  Independent **122 / 5.502 s / OK**. Native checkout **3871171c**, parents
  **b82c1b66 / 58928fac**; non-doc source identical. 140 design/Watch PNGs
  matched previously reviewed originals; known zoomed 164-label toggle only.
- Same-head live **37894476953**: **15 total / 1 fixture-only skip / 0 failures**,
  two Watch UI passed, exact app58928fac/backend3614bf6f production provenance.
  Checked 12 iOS + 3 Watch originals: Chinese catalogue, pending-nearby
  downloaded selection retained, offline new first hole, turn and restored home.
- #397 heads **ba7fc932 / cfb65b53 / 7c192a1d / 58928fac**, author
  **6075000869 / 6075229235 / 6075596162 / 6075760765**, own
  **6075192701 / 6075652720 / 6077199917** handled. Initial/cfb/7c/final
  CI/Native and old-live cancellations handled; final live handled.
  Run/head details in `handled_pr397_events` and dated archives; do not replay.
- #396/#395/#392/#393/#394 and Claude replacement request handled.
  #396 final **f073a77d**, merge **3bd1ce4d**; CI/Native **688 / 448**,
  independent **122 / 5.225 s**; live **37852249384 attempt 2** passed.
  Attempt-1 home-nearby failure retained, transport root cause still unproven.
- Last known external terminal PR event **07:51:18 UTC** (#397 live).
  Own reviews/merges/docs CI never reset quiet condition. Returned waiter log:
  read last matched event JSON only; never edit/delete cursor.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: await external ready PR/feedback
  through sole waiter; test exact heads, required Native/screenshots for mobile,
  post P1/P2 or PASS and merge/delete branch when clear. No open PR at inventory.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: nonblocking unchanged fixture
  八号铁 164 label variation; no product regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark status/navigation text
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
  prove Apple-runner path. Persistent operations root:
  `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- #397 final evidence `operations/pr397-58928fac-20261009`: source tar,
  independent contracts, Native artifacts/log/hashes/source proof, live ZIPs/
  artifacts/log, three labelled sheets, final review/merge/cleanup receipts.
  **27,606,396-byte** /dev/shm snapshot removed, named --rm container absent.
  Tar SHA256 `98f646c6a4810af46657e8579b6471222b529c9716b6284c9330dfaf89895aec`.
  All terminals **93796 / 96332 / 78673 / 5129 / 30084** completed/cleared.
  Three SHA-matched local inspection copies **1,137,294 bytes** moved to
  recoverable trash; empty directory removed. Original/derived remote evidence
  retained; 62 GiB free, production running. Lightweight .codex-pr397 controls
  retained as receipts, not active runtime.
- Initial/cfb/7c #397 roots retained: original contract/Native evidence, Date-tie
  Native failure log, P2 reviews. Initial snapshot **27,598,059 bytes** removed.
  #396/#395 original source/test/artifact/review/cleanup evidence retained;
  all owned runtime and inspection copies closed.
- No review/coding worktree, runtime container, browser, port, tunnel, private
  venv, inspection PNG directory, artifact terminal or subagent active.
  Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
- Protected stopped candidate `aicaddie-release-3614bf6f-candidate-20261006`,
  39089 inactive, private DB `aicaddie_candidate_3614bf6f_20261006`; stopped
  rollback `aicaddie-release-d7f69971-production-20260925-pre-cutover` retained.
  Release source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`
  expires Oct13; backups/data preserved pending owner build82 validation.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  No feedback wait pending; next sole terminal in `active_feedback_wait`.
  Pending: **clock.sleep(300000) → one write_stdin**, same turn until one-line
  result. No CI/ps/state/log liveness checks, independent tmux or second monitor.
  Timer unchanged, cursor retained; ignore own-CI; no CI-only commits.
- GitHub comments end `_Generated by Codex_`; commits end
  `Generated-by: Codex`.

## Next action and stopping

Commit/push real #397 review/merge/resource closure with dated archives, then
start sole feedback waiter. Dedup all listed completed heads/comments/runs;
new ready PR is actionable without a request. Native/red PR goes to author.
Absolute stop **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Earlier stop requires 48 hours without external PR events and no open PRs;
quiet condition not met. Same-turn waiting method through owner deadline.
Ledger ≤200 lines; history verbatim in dated archives, no CI-result-only commits.
After compaction read ledger, inspect Git/agent state, resume this slice.
