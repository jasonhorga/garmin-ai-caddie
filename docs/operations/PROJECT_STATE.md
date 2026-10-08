# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-08 21:32 UTC
**Canonical branch:** `main`
**Latest integrated code:** `8726ff7330f3f199b84758ece18e5ec3d58b62d4` (#395)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

No open PRs at **21:31 UTC**. #395 merged **21:30:51 UTC**, merge **8726ff73**,
guarded by final head **41d8299f063712d05c97e7559a41c8be5e1a988b**.
Branch `claude/results-fresh-on-open-20261008` deletion verified (Git ref 404).
Main fast-forwarded locally; unrelated dirty monitor script preserved.
Final PASS **6069435555**. Original three cache P2s, account P1 and
cancellation P2 fixed, independently verified, no remaining #395 blocker.

- #395 accepted code: scope tickets and atomic check/write/rebind, old account
  and cancelled answers neither stored nor published; background yields to
  foreground work, invalidates pre-Garmin responses, adopts pending fallback.
- Required CI **37834870412**, Native **37834870501**: **675 iOS / 448 Watch**.
  Five new account/cancellation regressions executed/passed. Checkout
  **afd5eee2**, parents **7191d9aa / 41d8299f**; app/test/backend/workflow/ops
  source matches head, only state docs differ. **93 iOS / 47 Watch** PNGs
  SHA-identical to reviewed baseline. Independent contracts **122 / 6.388 s / OK**.
- Exact-head live **37837050238**: **15 total / 1 skipped / 0 failures**.
  Production build-evidence exactly 41d8299f; iOS/Watch passed. Inspected live
  01-home / 02-results / b4b2-01 / 04 / 05: populated home/results, correct
  Back→Front order and 18-hole total; city fallback and BackNine journey pass.
- #395 heads 1547b250 / 5f3c0c3c / f4b75ad9 / ce78f2b8 / 41d8299f handled.
  Own reviews **6062275804 / 6064061351 / 6064302619 / 6065641884 /
  6067414139 / 6067792165 / 6068158813 / 6069435555** handled.
  Author **6061786172 / 6062377485 / 6064100843 / 6065414746 / 6065682452 /
  6067178741 / 6067491713 / 6067819673 / 6069372923** handled.
- #395 known runs: **37778457263 / 37778457236 / 37781120740 / 37794766703 /
  37794766696 / 37818780360 / 37818780513 / 37820662929 / 37832426991 /
  37832426883 / 37834870412 / 37834870501 / 37837050238** handled.
  **37796943981** attempts 1/2 failed, attempt 3 cancelled; retained distinct
  transport/viewport/journey evidence. Do not replay superseded CI/live.
- #392/#393/#394 integrated; **6058558621 / 6059399934 / 6061833380** handled.
  Claude **6054000859 / 6055315555 / 6058107992 / 6058245346** and Oct 8 12:05
  replacement request handled; no repeat cutover/release.
- Last external event checked: Claude **6069372923**, **21:26:54 UTC**.
  Own comments, merges and docs/CI bookkeeping do not reset the quiet interval.
  Read only the last matched event JSON from a returned wait log; ignored
  own-CI lines are not events. Never edit/delete the stream cursor.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: resume sole feedback waiter;
  review any new ready PR/feedback on its exact head; merge/delete when clear.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking: unchanged fixture's
  八号铁 164 label varied; no regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status text on dark maps.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired iPhone/Watch owner validation;
  simulator passes alone do not prove paired readiness.

## Live verification and release baseline

- **0.1.0 (82)**, internal TestFlight; upload **37774511661** succeeded.
  App **6dd96200b199ac8f5ea760719fb295bbc4eea1ef**, includes #394, **excludes #395**.
  Apple read-only/list **37776197288**: **VALID / IN_BETA_TESTING**, internal
  group contains 82; no external distribution. Apple also reports
  `internalReady=false`; retain field discrepancy. No later upload claimed.
- IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
  IPA/provenance: `operations/release-main-6dd96200-20261008`.
- #394 head **93824a8d**, merge **6dd96200** Oct 8 **12:02:45 UTC**,
  branch deleted; required Native/live passed; its 140 PNGs remain the baseline.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**.
  Production `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
- Cutover `operations/production-cutover-3614bf6f-20261008`: both DB dumps,
  pre-merge roots, conflict evidence/report retained. Newer 7-hole round 17742546
  kept; candidate 2-hole copy preserved; candidate-only ledger suffix
  **8,426,773 bytes** and cache merged. Sync **502 rounds / 501 scorecards /
  501 shots / ok / done**.
- Release HTTP/2 probes **3/3 200**, **1.82–2.57 s**; homeserver 200/HTTP2 alone
  does not prove the Apple runner path.
- Persistent evidence root: `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- #395 final evidence: `operations/pr395-41d8299f-20261008`: source tarball,
  independent contracts, Native/live artifacts/logs/hashes, manifest/reviews.
  27,402,706-byte /dev/shm snapshot removed after open-file checks; --rm contract
  container absent. Five PNG copies (1,607,810 bytes) hash-matched and moved to
  recoverable user trash; empty inspection directory removed; receipt retained.
  Earlier #395 snapshots/containers and PNG copies also closed; evidence retained.
- No active implementation/review runtime, browser, port, tunnel or subagent.
  Control files/manifests remain locally as lightweight audit copies;
  preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
- Candidate `aicaddie-release-3614bf6f-candidate-20261006` stopped; 39089 inactive.
  Keep private root/DB `aicaddie_candidate_3614bf6f_20261006` until build82 acceptance.
- Rollback `aicaddie-release-d7f69971-production-20260925-pre-cutover` stopped,
  retained. Production private volume/DB protected.
- HTTP/2 tmux closed. Release source
  `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006` expires Oct 13;
  persistent backups and cleanup allow-list retained.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Handle **55691** returned live success and closed. Next sole --feedback handle
  belongs in tool store `active_feedback_wait`; recover it after compaction.
- Pending wait: **clock.sleep(300000) → one write_stdin**, same turn, until one-line
  conclusion. No CI/ps/state/log polling, independent tmux or second monitor;
  timer unchanged. Ignore own CI/bookkeeping; no CI-only commits.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

Commit merge/review/resource closure with dated archive, then resume the sole
feedback waiter and deduplicate queued #395 events. No remaining #395 work.
No open PRs; 48-hour quiet interval is anchored to external events only.
Absolute owner stop: **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Earlier stop requires 48 hours without external PR events and no open PRs.
Keep same-turn waits through deadline. Ledger ≤200 lines; superseded text
preserved verbatim in `docs/archive/PROJECT_STATE-2026-10-08T2132-pr395-merge-close.md`.
After compaction read this ledger, inspect Git/agent state, resume this slice.
