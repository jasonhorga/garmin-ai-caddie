HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before PR395 final review/merge/resource closure.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-08 20:10 UTC
**Canonical branch:** `main`
**Latest integrated code:** `6dd96200b199ac8f5ea760719fb295bbc4eea1ef` (#394)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current review and deduplication

Claude restored. Open non-draft **#395**, branch
`claude/results-fresh-on-open-20261008`, checked head
`41d8299f063712d05c97e7559a41c8be5e1a988b` (author **6067819673**).
Account P1 / cancellation P2 accepted in **6068158813**. Captured scope and
atomic check/write/rebind lock; stale/cancelled foreground outcomes not committed
or published; notification lifecycle cancellation and background guards retained.
**Do not merge yet:** same-head live **37837050238**, started **20:07:13 UTC**,
pending. Inspect its terminal evidence/screenshots before final approval/merge.
- CI **37834870412**, Native **37834870501** passed: **675 iOS / 448 Watch**.
  All five new foreground account/A→B→A/background/cancelled-success regressions
  actually passed. Checkout **afd5eee2**, parents **7191d9aa / 41d8299f**;
  app/test/backend/workflow/ops source matches head, only state docs differ.
  All **93 iOS / 47 Watch** PNGs SHA-identical to reviewed f4b75ad9 baseline.
  Independent contracts **122 / 6.388 s / OK**. Do not repeat passed checks.

- CI **37818780360** and Native **37818780513** passed: **670 iOS / 448 Watch**.
  Checkout **43d5d24b**, parents **78bf1d8f / f4b75ad9**; product/test/workflow/
  backend/ops source matches head. All **93 iOS / 47 Watch** PNGs byte-identical
  to reviewed baseline. Independent **122 contracts / 5.144 s / OK** at
  5f3c0c3c apply to unchanged product/contract source; no redundant repeat.
- Exact-head live **37820662929** passed: **15 total / 1 skipped / 0 failures**.
  Full BackNine→FrontNine, city catalogue fallback, Tee selector and covered-band
  regression passed. Visually reviewed b4b2-01 / 04 / 05: start, turn, summary;
  correct loop order and 18-hole total. Live/source build-evidence exact head.
  Prior viewport/journey validation blockers closed; this is not account-race proof.
- Original three cache P2s resolved in 5f3c0c3c. Original review **6062275804**,
  fixed-head **6064061351**, transport **6064302619**, test findings **6065641884**,
  account **6067414139**, cancellation **6067792165**, fixes **6068158813** handled.
- Author **6061786172 / 6062377485 / 6064100843 / 6065414746 / 6065682452 /
  6067178741 / 6067491713 / 6067819673** handled. Heads 1547b250 / 5f3c0c3c /
  f4b75ad9 / ce78f2b8 source inspected; 41d8299f source/Native review completed.
  Runs **37778457263 / 37778457236 / 37781120740 / 37794766703 /
  37794766696 / 37818780360 / 37818780513 / 37820662929 / 37832426991 /
  37832426883 / 37834870412 / 37834870501** handled. ce78f2b8 CI superseded;
  its Native artifacts need no separate replay after final-head Native above.
- **37796943981**: attempt 1 TLS/network failure (4 failures), attempt 2
  viewport false negative + BackNine unselected (2 failures), attempt 3 cancelled
  **17:47:25 UTC**. All handled; distinct logs/artifacts retained. TLS EOF
  alone is not root-cause evidence. Do not replay them.
- #392/#393/#394 integrated; **6058558621 / 6059399934 / 6061833380** handled.
  Claude **6054000859 / 6055315555 / 6058107992 / 6058245346** and Oct 8 12:05
  replacement request handled; no repeat cutover/release.
- Read only the last matched event JSON from a returned wait log; ignored own-CI
  lines are not events. Never edit/delete the stream cursor.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: await #395 final-head live result;
  review terminal evidence/screenshots; merge/delete when no P1/P2 remains.
- `LIVE-CATALOGUE-FALLBACK` — `evidence-open`: retained TLS/network and viewport
  failures are distinct; new-head fallback now passed. Keep historical evidence.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking: unchanged fixture's
  八号铁 164 label varied; no regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status text on dark maps.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired iPhone/Watch owner validation;
  simulator passes alone do not prove paired readiness.

## Live verification and release baseline

- **0.1.0 (82)**, internal TestFlight, upload **37774511661** succeeded.
  App **6dd96200b199ac8f5ea760719fb295bbc4eea1ef**, includes #394, excludes #395.
  Apple read-only/list **37776197288**: **VALID / IN_BETA_TESTING**, internal
  group contains 82; no external distribution. Apple also reports
  `internalReady=false`; retain the field discrepancy.
- IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
  IPA/provenance: `operations/release-main-6dd96200-20261008`.
- #394 head **93824a8d**, merged **6dd96200** Oct 8 **12:02:45 UTC**;
  branch deleted, required Native/live passed; its 140 PNGs are the baseline.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**.
  Production `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
- Cutover `operations/production-cutover-3614bf6f-20261008`: both DB dumps,
  pre-merge roots, conflict evidence/report retained. Newer 7-hole round 17742546
  kept; candidate's 2-hole copy preserved; candidate-only ledger suffix
  **8,426,773 bytes** and cache merged. Sync **502 rounds / 501 scorecards /
  501 shots / ok / done**.
- Release HTTP/2 probes **3/3 200**, **1.82–2.57 s**; homeserver's health 200/HTTP2
  does not prove the Apple runner path.
- Persistent evidence root: `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- #395 final-head evidence: `operations/pr395-41d8299f-20261008`: source tarball,
  independent contracts, Native artifacts/log/hashes, manifest and **6068158813**.
  Snapshot /dev/shm/garmin-ai-caddie-pr395-41d8299f-20261008 (27,402,706 bytes)
  removed after no-open-handle checks; named --rm contract container absent.
  No local PNG copy created. Earlier-head evidence and failed-attempt logs retained.
- Earlier #395 /dev/shm snapshots and named --rm contract containers closed.
  All prior local PNG copies hash-matched and moved to recoverable user trash.
  Three f4b75ad9 PNG copies (944,266 bytes) hash-matched, no open handles;
  moved to recoverable user trash, empty inspection directory removed.
  Exact cleanup manifest/receipt retained under the persistent review root.
  No active implementation/review runtime, browser, port, tunnel or subagent.
- Candidate `aicaddie-release-3614bf6f-candidate-20261006` stopped; 39089 inactive.
  Keep private root/DB `aicaddie_candidate_3614bf6f_20261006` until build82 acceptance.
- Rollback `aicaddie-release-d7f69971-production-20260925-pre-cutover` stopped,
  retained. Production private volume/DB protected.
- HTTP/2 tmux closed. Release source
  `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006` expires Oct 13.
  Persistent backups and cleanup allow-list retained.
- Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Feedback handle **41875** returned live success and closed. No pending waiter.
  Next sole --feedback handle goes in tool store `active_feedback_wait`.
- Pending wait: **clock.sleep(300000) → one write_stdin**, same turn, until one-line
  conclusion. No CI/ps/state/log polling, independent tmux or second monitor;
  timer unchanged. Ignore own CI/bookkeeping; no CI-only commits.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

Await #395 live **37837050238** through the sole waiter; inspect terminal artifacts,
then final exact-head review and guarded merge/delete. No remaining source P1/P2.
48-hour quiet stop is ineligible while #395 is open; only external events count.
Absolute owner stop: **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Keep same-turn waits through the deadline. Ledger ≤200 lines.
Superseded ledgers preserved verbatim in dated archives:
2026-10-08T1750, T1806 and T1926 committed in **7191d9aa**;
T1950 and T2010 included with this independent review/test/resource closure.
After compaction read this ledger, inspect Git/agent state, resume this slice.
