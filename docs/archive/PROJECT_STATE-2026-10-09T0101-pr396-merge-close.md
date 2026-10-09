# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before PR396 merge/resource-close state, 2026-10-09 01:01 UTC.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-08 23:36 UTC
**Canonical branch:** `main`
**Latest integrated code:** `8726ff7330f3f199b84758ece18e5ec3d58b62d4` (#395)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and feedback deduplication

Claude restored and implementing; Codex retains independent review/integration.
Open non-draft **#396**, `claude/results-subpages-cache-20261008`, exact head
`f073a77dc7bbfd7db280ed913645c6607e8def9f`. Original account P1 and retention P2
fixed and verified; interim review **6070307513** posted, no remaining source blocker.
Same-head live **37852249384 attempt 1** failed; author started attempt 2.
Do not merge until complete live result/provenance/screenshots are accepted.
- Failure review **6071163486**: **15 total / 1 skipped / 1 failure**, only
  `TeeSelectionUITests/testCaptureTeeSelector:131`; injected Beijing Palace
  location but home shows 今天去哪打？/暂无天气, no course-here/change-course card.
  Independently checked attempt-1 log, exact f073a77d production build-evidence,
  home PNG and AX; Watch 448 tests and two UI tests passed. Transport root cause
  not independently established. Author **6071084617** reports TLS errors and
  absent nearby/weather backend arrivals; asked for client terminal causes if
  repeated. Keep original failure evidence; no new cache-source issue claimed.
- Origin tickets protect foreground detail/map, async edit-save and prefetch;
  stale-account/cancelled answers are neither written nor published.
- Every successful detail/map write and migration shares deterministic pruning:
  current round plus newest 39 others, maximum 40 per account.
  Owner informed: evicted older reviews require network; no approval pending.
- CI **37850351795**, required Native **37850351747** passed:
  **688 iOS / 448 Watch**, eight cache regression tests executed/passed.
  Independent remote contracts **122 / 5.225 s / OK**.
- Native checkout **e1af8e1978438edea69e7be23578475bf12c0081**, parents
  **ca542dc4 / f073a77d**: app/tests/backend/workflow/ops match reviewed head;
  only state docs differ. Artifacts reviewed against design and #395 baseline.
  **139/140** PNGs SHA-identical; visually inspected `full-hole-map-zoomed.png`
  only adds pre-existing variable 八号铁 164 label. No new layout regression.
- Handled #396 heads **0380a39f / f073a77d**, author **6069820462**,
  own reviews **6069726466 / 6070307513** and runs
  **37847732954 / 37847732960 / 37850351795 / 37850351747**.
  Initial review's erroneous UI-route example was transparently corrected;
  original retained in `operations/pr396-0380a39f-20261008/initial-review-original.md`.
- #395 fully integrated at **8726ff73**, final head **41d8299f**, final PASS
  **6069435555**, branch deletion verified (404). Source/CI/Native/live and
  cleanup accepted; detailed heads/comments/runs retained verbatim in archives
  and tool store `handled_pr395_events`. Do not replay superseded events.
- #392/#393/#394 and Claude replacement request handled; no repeated release.
- Handled author **6071084617**, own **6071163486**, live attempt **1**; attempt
  **2 remains unhandled** even though run ID is unchanged. Dedup by run+attempt.
- Last external author reply **23:29:28 UTC** (#396 **6071084617**);
  its f073a77d head/terminal CI/Native reviewed. Own review/merge/docs CI never
  reset the owner's quiet interval. Open #396 prevents early quiet stop.
- Read only last matched event JSON from a returned wait log; ignored own-CI
  lines are not events. Never edit/delete stream cursor.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: await #396 live/author events via
  sole waiter; require attempt-2 outcome, inspect evidence, merge if no blockers.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking:
  unchanged fixture's 八号铁 164 label varies; no product regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status text on dark maps.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: owner paired iPhone/Watch validation;
  simulator evidence alone does not prove paired readiness.

## Live verification and release baseline

- **0.1.0 (82)**, internal TestFlight, upload **37774511661** successful.
  App **6dd96200b199ac8f5ea760719fb295bbc4eea1ef** includes #394,
  **excludes #395/#396**. No newer upload claimed.
- Apple read-only **37776197288**: **VALID / IN_BETA_TESTING**, internal
  group contains 82, no external distribution. Apple `internalReady=false`
  discrepancy retained; owner device verification remains open.
- IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`;
  provenance `operations/release-main-6dd96200-20261008`.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**.
  Production `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
- Protected cutover evidence `operations/production-cutover-3614bf6f-20261008`:
  DB dumps, roots, conflict report, newer 7-hole 17742546 and candidate 2-hole
  copy retained; candidate-only ledger suffix **8,426,773 bytes** merged.
  Incremental sync **502 rounds / 501 scorecards / 501 shots / ok / done**.
- HTTP/2 probes **3/3 200**, **1.82–2.57 s**; homeserver success alone does not
  prove Apple-runner path. Persistent root:
  `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- #396 evidence `operations/pr396-f073a77d-20261008`: source tarball,
  contracts, Native artifacts/logs/hashes, manifests, review and cleanup log.
  Read-only snapshot `/dev/shm/garmin-ai-caddie-pr396-f073a77d-20261008`
  (**27,546,510 bytes**) removed after open-handle/command checks;
  named --rm contract container absent. Tar SHA256
  `c41c22acdbdf3c654d28e7d136a9c56feceeb27c8dfa8c20368c8069b12426f3`.
  Two inspected PNG copies (**1,293,964 bytes**) SHA-matched and moved to
  recoverable user trash; empty directory removed. Originals retained.
  Cleanup capacity **61 GiB free**, production running.
  Live attempt-1 ZIPs/artifacts/log preserved in same evidence directory; no
  runtime created. Failed home PNG copy (232,060 bytes) hash-matched and moved
  to recoverable trash; empty inspection directory removed; original retained.
- #395 evidence `operations/pr395-41d8299f-20261008` retained; all snapshots,
  containers and inspection copies closed. No active review/implementation
  runtime, browser, port, tunnel or subagent. Control manifests are audit copies.
  Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
- Stopped candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089
  inactive; private root/DB `aicaddie_candidate_3614bf6f_20261006` protected
  until build82 acceptance. Stopped rollback
  `aicaddie-release-d7f69971-production-20260925-pre-cutover` protected.
- Release source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`
  expires Oct 13; persistent backups/cleanup allow-list retained. HTTP/2 tmux closed.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  No wait currently pending; next sole terminal recorded in `active_feedback_wait`.
- Pending wait: **clock.sleep(300000) → one write_stdin**, same turn, until its
  one-line result. No CI/ps/state/log polling, independent tmux or second monitor.
  Timer unchanged, cursor retained; ignore own-CI; no CI-only bookkeeping commits.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

Start sole feedback waiter, dedup known #396/#395 events by attempt, then await
#396 same-head live attempt 2. On success inspect provenance/screenshots, post
PASS, SHA-guard merge and delete branch. No new TestFlight upload implied.
Absolute owner stop: **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Earlier stop requires 48 hours without external PR events and no open PRs.
Keep same-turn waiting method through deadline. Ledger ≤200 lines; history
preserved verbatim in dated archives; T2336/resource receipt pending next real
integration/operations commit, no CI-result-only bookkeeping commit.
After compaction read ledger, inspect Git/agent state, resume this slice.
