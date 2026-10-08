HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before the 2026-10-08 19:26 UTC review/state update.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-08 18:06 UTC
**Canonical branch:** `main`
**Latest integrated code:** `6dd96200b199ac8f5ea760719fb295bbc4eea1ef` (#394)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current review and deduplication

Claude restored. Open non-draft **#395**, branch
`claude/results-fresh-on-open-20261008`, head
`f4b75ad9b4193aed7440e3ac713c39d464f5df80`, author **6065682452**.
Three UI-test files changed; product/contract source unchanged from 5f3c0c3c.
Original three cache P2s resolved. **Do not merge yet**: await new-head Native
**37818780513** passed; CI **37818780360** passed. Native source/artifacts
reviewed: **670 iOS / 448 Watch**, all **140 PNGs** match the prior baseline.
Checkout **43d5d24b**, parents **78bf1d8f / f4b75ad9**; app/test/workflow/backend/
ops source matches the head. Same-head live **37820662929**, started Oct 8
**17:58:14 UTC**, is pending. Do not claim a live pass from Native snapshots.

- P2 / test: `catalogue-course-catalog-city-field-result-missing.png` in
  artifact **11566465719** visibly contains 北京丽宫 31793. Its AX frame
  y **722.3–766.3** is falsely excluded by the hidden underlying Start band
  at y **747.6**. f4b75ad9 now ignores a band that is not hittable, retains
  active-band protection and adds the observed geometry's sheet regression.
  Static fix reviewed; its runtime validation awaits **37820662929**.
- P2 / validation: `RealFlowUITests.swift:76` is 后九 tap → value not becoming
  已选择 (16:21:07–16:21:16 UTC), before the first journey screenshot.
  f4b75ad9 adds screenshot/AX and before/after frame/value when this fails;
  logged center is derived from the frame, not proof of the actual hit point.
  Full 后→前 assertions retained; outcome still needs same-head live evidence.
- Required CI **37794766703**, Native **37794766696** passed: **670 iOS /
  448 Watch**, including four cache regressions. Checkout **b824a61b**,
  parents **ff567de4 / 5f3c0c3c**; all app/test/workflow/backend/ops source
  matches the head (only state docs differ). **93 iOS / 47 Watch** PNG hashes
  match the previously reviewed baseline. Independent contracts:
  **122 / 5.144 s / OK**. These are the 5f3c0c3c baseline, not f4b75ad9 CI;
  do not repeat contracts for unchanged source. Obtain new Native/artifacts.
- Live **37796943981 attempt 2** failed: **14 total / 1 skipped / 2 failures**
  (BackNine journey + NoCourse city fallback). Pinned log/artifact retained in
  `operations/pr395-5f3c0c3c-20261008`. Do not classify this city failure as TLS.
- Attempt 1: **14 total / 1 skipped / 4 failures** (RealFlow prep search,
  ReviewEdit, no-GPS fallback, Tee home). Catalogue screenshot explicitly
  shows network error; review/Tee log SSL **-1200 / -9816**. Pinned
  `live-run-attempt1.log`, artifact **11561028078** retained even after retry.
- Independently corroborated author transport **6064100843**, reply **6064302619**:
  production access-log gap **15:28:26.616–15:33:10.854 UTC**, no restart;
  TLS handshake errors 15:28 / 15:29 / 15:32: **14 / 7 / 12**.
  Bounded raw logs retained. Access logs record responses; EOF is not a root cause.
- Prior #395 head **1547b250** reviewed in **6062275804**; tests, original
  live evidence and closure archived. Author **6061786172 / 6062377485 /
  6064100843** handled. Own **6062275804 / 6064061351 / 6064302619 /
  6065641884**, old-head CI, fixed-head required CI, and both failed live
  attempts above are handled; next fixed head/reply/new attempt is actionable.
- Author **6065414746** (old-head attempt 3 underway) is answered by the later
  **6065641884** review. Author fix **6065682452** now being reviewed.
  Old-head attempt 3 was cancelled **17:47:25 UTC**, already handled;
  it cannot attest to the new helper.
- #392/#393/#394 integrated and closed; #393 result **6058558621**,
  #394 PASS **6059399934**, release **6061833380** handled. Claude's
  **6054000859 / 6055315555 / 6058107992 / 6058245346** and Oct 8 12:05
  replacement request handled. Do not replay known cutover/release requests.
- Read only the last matched event JSON from a returned wait log; preceding
  ignored own-CI lines are not events. Never edit/delete the stream cursor.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: await #395 f4b75ad9 live
  **37820662929**; inspect its terminal evidence, final P1/P2
  conclusion; merge/delete only when clear. Handle subsequent new PR feedback.
- `LIVE-CATALOGUE-FALLBACK` — `evidence-open`: first-attempt TLS/network
  failure and second-attempt viewport false negative are distinct; retain both.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking: 八号铁 164
  label varied on unchanged fixture; no regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status text on dark maps.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired iPhone/Watch validation.
  Build 80/81 superseded; simulator evidence alone does not prove paired readiness.

## Live verification and release baseline

- **0.1.0 (82)**, internal TestFlight, upload **37774511661** succeeded.
  App **6dd96200b199ac8f5ea760719fb295bbc4eea1ef** includes #394.
  Apple read-only/list **37776197288**: **VALID / IN_BETA_TESTING**, internal
  group contains 82; no external distribution. Apple also reports
  `internalReady=false`; retain the field discrepancy.
- IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
  IPA/provenance: `operations/release-main-6dd96200-20261008`.
- #394 exact head **93824a8d**, merged **6dd96200** Oct 8 12:02:45 UTC,
  branch deleted; required Native/live passed. Its 140 PNGs are the review baseline.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**.
  Production `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
- Cutover `operations/production-cutover-3614bf6f-20261008`: both DB dumps,
  pre-merge roots, conflict evidence and merge report retained. Production's
  newer 7-hole round 17742546 kept; candidate's 2-hole copy preserved;
  candidate-only ledger suffix **8,426,773 bytes** and cache merged.
  Completed sync: **502 rounds / 501 scorecards / 501 shots / ok / done**.
- Release HTTP/2 probes **3/3 200**, **1.82–2.57 s**; Oct 8 homeserver
  health check 200/HTTP2 does not validate the hosted Apple runner path.
- Persistent evidence root: `/home/jason/garmin-ai-caddie-data/operations`.

## Owned resources and wait boundary

- f4b75ad9 review uses only read-only Git refs; no standalone test snapshot.
  Manifest/evidence root: `operations/pr395-f4b75ad9-20261008`; no runtime.
- Both #395 snapshots `/dev/shm/garmin-ai-caddie-pr395-{1547b250,5f3c0c3c}-20261008`
  closed after open-file checks; named `--rm` contract containers absent.
  Manifests, source tarball, Native/live artifacts/logs retained in their
  operations roots. All local PNG copies hash-matched remote and moved to
  recoverable user trash, including the attempt-2 **498,081-byte** copy.
  No active implementation/review runtime, browser, port, tunnel or subagent.
- Candidate `aicaddie-release-3614bf6f-candidate-20261006` **stopped**;
  port 39089 inactive. Keep private root/DB
  `aicaddie_candidate_3614bf6f_20261006` until owner build82 acceptance.
- Rollback `aicaddie-release-d7f69971-production-20260925-pre-cutover`
  **stopped and retained**. Production private volume/DB protected.
- HTTP/2 tmux `codex-release-http2-main-3614bf6f-20261006` closed.
  Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`
  expires **Oct 13**; persistent backups and release allow-list retained.
- Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`, SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Feedback handle **44525** returned attempt-2 failure and is closed.
  Start next sole `--feedback`; store handle in `active_feedback_wait`.
  Recover any stored pending handle after compaction; never start replacements.
- Pending: **clock.sleep(300000) → one write_stdin**, same turn, repeat until
  one-line conclusion. No CI/ps/state/log polling, independent tmux or second
  monitor; timer unchanged. Ignore own CI/bookkeeping; no CI-only commits.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

#395 f4b75ad9 Native/source/artifact review complete; await its live via the same
cursor, inspect terminal artifacts and return final review. Do not reuse old live
as proof of the corrected UI-test helper.
48-hour quiet stop is ineligible while #395 is open; only external events count.
Absolute owner stop: **2026-10-09 23:59 UTC**; close/hand back owned runtime then.
Keep current same-turn waits through the deadline. Ledger ≤200 lines.
Superseded ledger preserved verbatim in
`docs/archive/PROJECT_STATE-2026-10-08T1806-pr395-native-artifacts.md`
(pending inclusion with the next real review/merge commit).
After compaction read this ledger, inspect Git/agent state, resume this slice.
