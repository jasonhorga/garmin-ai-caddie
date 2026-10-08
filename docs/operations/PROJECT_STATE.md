# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-08 05:26 UTC
**Canonical branch:** `main`
**Latest integrated code:** `fb7df3658cc02041d29e676105ee78d4e5966a63` (#393)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Claude restored. **No open PRs** at the post-merge check.
#392 reviewed exact **8f316f016a60157dd3140ba57b93fb350b911840**, PASS comment
**6046883601**, merged **0e544fa2** at **Oct 7 21:08:16 UTC**; branch deleted,
local main fast-forwarded. Merged mobile/ios/Package/workflow identical to reviewed
head. Commit has required Codex trailer. Counts/recent claims and actual
pending-time selection P2 resolved; do not re-review this head or its old events.

Latest review baseline: ordinary **37674411741**, Native **37674411722**,
independent **132 / 16.669 s / OK**. Compiled Native merge **e755122e** no relevant
diff. Three automatic artifact digests checked; **93 iOS / 47 Watch** compared
against reviewed predecessor, changed selected/zoomed frames inspected.
Live **37676853476 attempt 2**, exact head, live/production/non-fixture:
**10 / 0 failures / 1067.703 s**; TeeSelection **8 / 0 / 584.328 s**.
Two live artifact digests checked; **37 actual App PNGs**, pending-01/02/03
inspected with AX: unselected → real tap while pending → Palace/front/blue kept.
RealFlow/ReviewEdit/Core Location/all-services-offline/city-search gates pass.
This is simulator evidence; Build80 remains the owner-device baseline.

Dedupe: latest Claude **6046795815** (Oct 7 **21:02:51 UTC**) consumed; earlier
**6045536908 / 6046215308** and own progress **6046490302** consumed.
Prior #392 P2 **6043496432 / 6044451139 / 6045129506**, b186552b/69cdc9c3/ee379209
heads/CI superseded. First live attempt failure retained; never call it PASS.
#391/#389 finished evidence and corrections remain archived; no reopening.
The feedback waiter ending **03:28 UTC** was a timeout with no new external event;
the cursor remains authoritative and unchanged.
#393 reviewed exact **e912280692387fb821114107b3c240575b0fe2c8**, review comment
**6052926671**, merged **fb7df365** at **Oct 8 05:22 UTC**; source branch deleted
and local `main` fast-forwarded. Native merge **115a5261** has exact head/base
parents and an identical tree. Native production evidence passed both iOS/Watch;
93 design and 47 Watch PNGs were byte-identical to the reviewed baseline. The
new exact-head contract test passed 1/1; the bare-host full 121-test retry was
environment-limited by missing `pydantic`/`numpy`, while required CI passed.
Read last matched waiter event, not earlier ignored own lines. Preserve dirty
`ops/pr_feedback_monitor.sh` and unrelated older `.codex-*`.

Quiet baseline **Oct 7 21:08:16 UTC** (conservative: merge/no-open transition
after latest external comment); earliest quiet stop **Oct 9 21:08:16 UTC**
if no new external PR event and still no open PRs. Own merges/comments/CI/docs
never reset quiet. Hard stop remains **Oct 9 23:59 UTC**.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: existing feedback cursor,
  new actionable external feedback/PRs; exact-head checks and screenshot review,
  P1/P2 verdict, merge/delete when clear. No duplicate monitor.
- `LIVE-CATALOGUE-FALLBACK` — `queued`, nonblocking observation:
  city-search first attempt failed, same head retry passed unchanged. Cause
  unknown; AX mounted rows do not prove complete response counts. If recurrent,
  preserve actual response/search completion/scroll evidence; no weakened test.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking: zoomed snapshot's
  八号铁 164 label varies with unchanged map/fixture; no product regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status text on dark maps.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner's paired iPhone/Watch test.
  `watch-round-seeded.png` is a waiting page, not geometry-readiness proof.

## Live release baseline

- **0.1.0 (80)** internal TestFlight, Apple **VALID / IN_BETA_TESTING**,
  operation=list/external=false. App/API/sync
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**, static text / Gemini vision.
- Passed: live Native **37426762320**, TestFlight **37438559636**,
  Apple read-only **37440770465**. IPA **11400009027**, ZIP SHA256
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
  App/Watch versions, origin/backend/provenance verified; no production switch.
- Synthetic pin sheet 200/18.901 s; exact date/three holes/front facts.
  HTTP/2 package 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  tunnel 2.10–2.34 s, HTTP/2/200.
- Live origin `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production `aicaddie-release-d7f69971-production-20260925`, port 39055,
  revision **d7f699712f7ac6cba41d97c420c405e090625caf**.
- Durable root `/home/jason/garmin-ai-caddie-data/operations`;
  release `release-main-3614bf6f-20261006`; #392 `pr392-8f316f01-20261007`.
  Source, both run attempts, screenshots/digests, probes, review bodies and
  cleanup receipts retained. First failures never relabelled as successes.
- #392 merged code has not been deployed or uploaded to TestFlight.

## Owned resources and blocking boundary

- No implementation worktree, active snapshot/test/render container, download,
  observer or subagent. All #392 remote snapshots/test containers closed.
- #392 **20 local files / 3,103,800 bytes** verified against persistent
  `pr392-8f316f01-20261007/local-review-backup`, checked for users and moved to
  user trash. Only local cleanup/checksum records remain; permanent evidence kept.
- #389 56022d32 local image copy also closed: **41 files / 13,256,841 bytes**,
  remote byte-identical backup and recoverable trash. Old unrelated files protected.
- #389 6fea0239 local helpers and five screenshots reached expiry **Oct 8 03:22
  UTC**. Checksums match the persistent evidence backup; the one local
  `observed-live.py` variant was additionally preserved as
  `operations/pr389-6fea0239-20261007/.codex-pr389-6fea0239-observed-live-local-copy.py`.
  After `lsof` found no users, nine files plus the screenshot directory were
  moved to recoverable user trash. The review manifest remains locally; remote
  snapshot/container/service/volume were already closed.
- #393 read-only snapshot `/dev/shm/garmin-ai-caddie-pr393-e9122806-20261008`
  closed after merge; persistent review diff, artifacts, hashes and manifest are
  retained at `operations/pr393-e9122806-20261008`.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089;
  full-SHA API + sync images retained for owner tests.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110;
  isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13; release allow-list retained. Production DB/volume protected.
- Both 39055/39089 health/revision checked after cleanup; unchanged.
  Latest capacity **63 GiB disk / 4.2 GiB available RAM**.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`; SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `blocking-waits/feedback-cursor`: never edit/delete.
- No waiter at update; next waiter handle retained in tool store
  `active_feedback_wait` in this same turn. Recover that handle after compaction,
  do not inspect processes or start a replacement while pending.
- Same turn: terminal → clock.sleep(300000) → one write_stdin until one-line
  conclusion. No idle CI/ps/state/log polling, independent waiter tmux, duplicate
  monitor or CI-only commits. Existing feedback timer unchanged.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.
  Own commits/CI/duplicate events never reset quiet or reopen review.

## Next action and stopping

Resume the existing feedback cursor in this turn through the next external event
or stop deadline. Deduplicate already reviewed #392 heads/replies/runs without new
comments/commits. Expired #389 local copies are closed and recoverable; retain the
manifest and persistent evidence, then continue the same-turn blocking wait.
Stop after **48 quiet hours with no open PRs** or absolute **Oct 9 23:59 UTC**;
close/hand back resources at stop. No waiting-style change before owner deadline.
Ledger ≤200 lines/current-only; archive superseded detail verbatim.
After compaction read ledger, inspect Git/agent status, resume this slice.
