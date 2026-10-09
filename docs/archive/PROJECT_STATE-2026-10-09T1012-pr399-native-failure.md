HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 09:49 UTC
**Canonical branch:** `main` (pushed **c06fb903e5d52e8e1e03855147b947c92438cd27**)
**Latest integrated code:** `c06fb903e5d52e8e1e03855147b947c92438cd27` (#398 merge; #397 product `91859eb8`)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and feedback deduplication

Claude restored and implementing. **#398 merged 09:44:44 UTC** after exact-head
review. Final head `ffe1f90c9792a2008e6997a9019484d63b1eedb4`, merge
`c06fb903e5d52e8e1e03855147b947c92438cd27`, branch deleted (404). Purpose was
whole-course download progress only in settings, consistent with approved design.
Author **6077872405** fixed both P2s from own **6077762890**. Final review comment
**6078427324** PASS:
- Retained progress identity now round/loopKey/tee; package identity change
  immediately recomputes from disk or clears. Settings rejects stale identity.
- Live progress counts successfully persisted same-identity facts plus matching
  PNG; all three successful round writes retain returned persisted facts, final
  publication follows persistence. Cancellation/current-identity guards retained.
- Held-network add/drop-nine, denied-package-write with all PNGs present, and
  row rejection on loop/tee changes read fully. Independent exact-ffe contracts
  **123 / 5.674 s / OK**, owned snapshot/container closed.
CI **37909110114** and Native **37909110130** succeeded. Exact-ffe contracts
**123 / 5.674 s / OK**. Native merge evidence `4bff8cd7` parents were latest
main `c7b66ad8` plus exact head; **706 iOS / 448 Watch** passed. Artifact had
141 PNGs: 140 baseline hashes identical plus expected settings-only image,
visually checked. Heads/comments/runs and final PASS are deduplicated in
`handled_pr398_events`; initial/a9 runtime and current fixed-head resources are closed.

#397 merged **08:19:46 UTC**, **91859eb8**; reviewed exact **58928fac**,
PASS **6077199917**, branch deletion verified; merged non-doc source matches.
Independent **122 / 5.502 s / OK**, Native **37894020995**:
**697 iOS / 448 Watch**, 140 design/Watch PNGs matched reviewed originals.
Live **37894476953** passed: **15 total / 1 fixture-only skip / 0 failures**,
2 Watch UI tests; app589/backend361 production provenance and 15 screenshots
checked. All #397 heads/comments/CI/Native/live/cancellations handled in
`handled_pr397_events`; final request6076847715 already fulfilled, do not replay.
#396/#395/#392/#393/#394 and Claude replacement request handled; details archived.
Last external event **09:06:07 UTC** author fix (new-head CI also external).
Own comments/merges/docs CI never reset the owner's 48-hour quiet condition.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: monitor new actionable PR events and
  comments through the owner deadline. #398 is merged and closed; do not replay.
  New ready PRs remain actionable.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: unchanged fixture 八号铁164
  label variation; nonblocking, no product regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: owner paired iPhone/Watch validation;
  simulator evidence alone does not prove paired readiness.

## Live verification and release baseline

- **0.1.0 (82)** internal TestFlight; upload **37774511661** successful.
  App **6dd96200b199ac8f5ea760719fb295bbc4eea1ef** includes #394,
  **excludes #395/#396/#397/#398**. No newer upload/server deployment claimed.
- Apple read-only **37776197288**: **VALID / IN_BETA_TESTING**, internal group82,
  no external distribution; `internalReady=false` discrepancy retained.
  IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`;
  provenance `operations/release-main-6dd96200-20261008`.
- API `https://caddie.taile36706.ts.net`; backend/sync
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**; production
  `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
- Protected `operations/production-cutover-3614bf6f-20261008`: DB dumps/roots/
  conflict report, newer 7-hole17742546/candidate2-hole copy, ledger suffix
  **8,426,773 bytes** retained. Sync **502 rounds/501 scorecards/501 shots/ok/done**.
- HTTP/2 **3/3 200**, **1.82–2.57 s**; homeserver does not prove Apple-runner path.
  Persistent root `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- #398 fixed-head manifest `.codex-pr398-ffe1f90c-review-manifest.md`:
  snapshot `/dev/shm/garmin-ai-caddie-pr398-ffe1f90c-20261009`, named --rm
  container `codex-pr398-ffe1f90c-contracts-20261009`, evidence
  `operations/pr398-ffe1f90c-20261009`. Created09:21, expires23:59 or review end.
  Capacity62 GiB disk/3.3 GiB shm/4.5 GiB available RAM. Runtime now closed;
  read-only existing image/env, no dependency install, network or private venv.
  Snapshot **27,677,011 bytes** removed after scoped checks; container absent.
  Contracts terminal44789/cleanup48382 complete; tar SHA256
  `fd40979d5efeb11d68e219e9428d2f634cc5f664377be9950d25c1d759f120cc`.
  Original tar/contracts/cleanup receipts retained; production running/62 GiB free.
- Initial #398 tar/log/cleanup/manifest retained at
  `operations/pr398-aa18d0d2-20261009`; snapshot27,660,535 bytes removed,
  container absent. SHA256
  `a879e509949fd31e34f3def215fb532fc5342f730f942ddd45d8f030c0155a05`.
  Own P2 review at `operations/pr398-a9fd08d0-20261009/review.md`.
- #397 final original tar/contracts/Native/live/images/review/cleanup retained at
  `operations/pr397-58928fac-20261009`; all runtimes, artifact terminals and
  inspection copies closed. Earlier #397/#396/#395 evidence and failures retained.
- No active review/coding worktree, browser, port, tunnel, private venv,
  inspection PNG directory, artifact terminal or subagent. Preserve unrelated
  dirty `ops/pr_feedback_monitor.sh` and older `.codex-*` controls.
- Protected stopped candidate `aicaddie-release-3614bf6f-candidate-20261006`,
  39089 inactive, DB `aicaddie_candidate_3614bf6f_20261006`; stopped rollback
  `aicaddie-release-d7f69971-production-20260925-pre-cutover` retained.
  Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`
  expiresOct13; backups/data protected pending owner build82 validation.
- Deployed sole waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  No feedback wait pending; next sole terminal in `active_feedback_wait`.
  Feedback pending: **clock.sleep(300000) → one write_stdin**, same turn to result.
  No CI/ps/state/log liveness checks, independent tmux or second monitor.
  Timer/cursor retained; ignore own-CI; no CI-result-only commits.
- GitHub comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

Independent exact-ffe contracts/runtime closure complete; use sole blocking
waiter for Native37909110130, then download/prove/inspect
final-head artifacts before acceptance. Post findings or PASS, SHA-guard merge
and branch deletion only if clear. Persist this real review with dated history.
Absolute stop **2026-10-09 23:59 UTC**; no owned runtime remains to close.
Earlier stop requires 48 hours without external PR events and no open PRs;
quiet condition not met. Same-turn waiting method through owner deadline.
Ledger≤200 lines, archives preserve history, no CI-result-only commits.
After compaction read ledger, inspect Git/agent state, resume this slice.
