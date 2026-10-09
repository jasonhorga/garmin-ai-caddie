# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before PR397 initial source/contract review, 2026-10-09 05:41 UTC.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 01:01 UTC
**Canonical branch:** `main`
**Latest integrated code:** `3bd1ce4dba4d5920d5e9d18bfe18b879ac612a9f` (#396)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and feedback deduplication

Claude restored and implementing; Codex retains independent review/integration.
**No open PRs** at the post-#396 merge listing. Continue the sole feedback waiter.
#396 merged **00:56:47 UTC**, final head **f073a77dc7bbfd7db280ed913645c6607e8def9f**,
merge **3bd1ce4d**. Branch `claude/results-subpages-cache-20261008` deleted (404).
Local main fast-forwarded; merged app/tests/backend/workflow/ops source matches
reviewed head. Unrelated dirty monitor script preserved.
- Final PASS **6072047793**: account-origin/cancellation P1 and 40-round retention
  P2 fixed, independently verified. Window statistics/review detail/maps reused
  before refresh; all async writers ticket-scoped; deterministic per-account cap.
  Owner informed: older evicted reviews need network; no approval pending.
- CI **37850351795**, required Native **37850351747**:
  **688 iOS / 448 Watch**, eight cache regressions executed/passed.
  Independent remote contracts **122 / 5.225 s / OK**. Native checkout
  **e1af8e1**, parents **ca542dc4 / f073a77d**, product/test/workflow source matches.
- Same-head live **37852249384 attempt 2**, success **00:43:31 UTC**:
  **15 iOS total / 1 skipped / 0 failures**, **2 Watch UI passed**;
  production build-evidence exactly f073a77d, iOS/Watch passed.
  Its **140 design/Watch PNGs SHA-identical** to reviewed #395 baseline.
  Eight real PNGs inspected: home/results/time/performance/review/shot-map/
  after-edit/Watch home; correct Beijing Palace home/weather, data populated,
  OUT45 + IN47 = 92, routes retained. Existing dark-top-text contrast nonblocking.
- Live attempt **1** failed only `TeeSelectionUITests/testCaptureTeeSelector:131`
  (15 total / 1 skipped / 1 failure): home lacked course-here/nearby and weather.
  Original log/PNG/AX/provenance retained; transport root cause not independently
  established. Same source passed attempt 2; original failure is not erased.
- #396 handled heads **0380a39f / f073a77d**; author **6069820462 / 6071084617**;
  own reviews **6069726466 / 6070307513 / 6071163486 / 6072047793**;
  runs **37847732954 / 37847732960 / 37850351795 / 37850351747** and live
  **37852249384 attempts 1/2**. Dedup by run+attempt, not ID alone.
- #395 accepted at **8726ff73**, final head **41d8299f**; all prior feedback,
  reviews/runs/branches/resources handled. Detailed IDs retained in dated
  archives and `handled_pr395_events`; do not replay superseded feedback.
  #392/#393/#394 and Claude replacement request handled; no repeated release.
- Last reviewed external event: #396 same-head live attempt 2 **00:43:31 UTC**.
  Own review/merge/docs/CI never reset the 48-hour quiet interval. Future author
  events are handled from the stream, not inferred from self-generated CI.
- Read only last matched event JSON from returned wait log; own-CI lines are not
  events. Never edit/delete cursor. Final dedup in `handled_pr396_events`.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: same-turn waiter, inspect actionable
  new PR/reply/head/terminal CI; exact-head review, required Native/artifacts,
  comment PASS or P1/P2, merge and delete branch when clear.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking unchanged fixture's
  八号铁 164 label varies; no product regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status/navigation text
  on dark maps/review.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: owner paired iPhone/Watch validation;
  simulator evidence alone does not prove paired readiness.

## Live verification and release baseline

- **0.1.0 (82)** internal TestFlight, upload **37774511661** successful.
  App **6dd96200b199ac8f5ea760719fb295bbc4eea1ef** includes #394,
  **excludes #395/#396**. No newer upload or server deployment claimed.
- Apple read-only **37776197288**: **VALID / IN_BETA_TESTING**, internal
  group contains 82, no external distribution. Apple `internalReady=false`
  discrepancy retained; owner device verification remains open.
- IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`;
  provenance `operations/release-main-6dd96200-20261008`.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**.
  Production `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
- Protected cutover `operations/production-cutover-3614bf6f-20261008`:
  DB dumps/roots/conflict report, newer 7-hole 17742546 and candidate 2-hole
  copy retained; candidate-only ledger suffix **8,426,773 bytes** merged.
  Sync **502 rounds / 501 scorecards / 501 shots / ok / done**.
- HTTP/2 probes **3/3 200**, **1.82–2.57 s**; homeserver success alone does not
  prove Apple-runner path. Persistent root:
  `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- #396 evidence `operations/pr396-f073a77d-20261008`: source tarball,
  independent contracts, required Native and live attempts 1/2 ZIPs/artifacts/
  logs/hashes, manifest, reviews and cleanup receipts. Originals retained.
  Read-only 27,546,510-byte /dev/shm snapshot removed after open-handle/command
  checks; named --rm contract container absent. Tar SHA256
  `c41c22acdbdf3c654d28e7d136a9c56feceeb27c8dfa8c20368c8069b12426f3`.
  PNG inspection copies closed: 2 required (1,293,964 bytes), 1 failed
  (232,060), 8 passing (2,729,276); SHA-matched, recoverable trash, empty dirs
  removed. Capacity **61 GiB free**, production running.
- #395 evidence `operations/pr395-41d8299f-20261008` retained; runtime/copies
  closed. No active review/implementation runtime, browser, port, tunnel or
  subagent. Local control manifests are audit copies; preserve unrelated
  dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
- Stopped candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089
  inactive; private root/DB `aicaddie_candidate_3614bf6f_20261006` protected
  until build82 acceptance. Stopped rollback
  `aicaddie-release-d7f69971-production-20260925-pre-cutover` protected.
- Release source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`
  expires Oct 13; backups/cleanup allow-list retained. HTTP/2 tmux closed.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  No wait currently pending; next sole terminal in `active_feedback_wait`.
- Pending wait: **clock.sleep(300000) → one write_stdin**, same turn until its
  one-line result. No CI/ps/state/log polling, independent tmux or second monitor.
  Timer unchanged, cursor retained; ignore own-CI; no CI-only bookkeeping commits.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

Start sole feedback waiter and dedup queued #396/#395 merge/review/run events.
Process new external events; do not repeat release/cutover or start CI-only commits.
Absolute owner stop: **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Earlier stop requires 48 hours without external PR events and no open PRs.
Keep same-turn method through deadline. Ledger ≤200 lines; preserve superseded
text verbatim in dated archives (T2336/T0101 with this real merge/resource work).
After compaction read ledger, inspect Git/agent state, resume this slice.
