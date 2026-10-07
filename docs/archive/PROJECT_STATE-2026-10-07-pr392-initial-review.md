# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived 2026-10-07 after the first PR392 exact-head review and cleanup.
This intake ledger is preserved verbatim; current state is
`docs/operations/PROJECT_STATE.md`. Verdict: comment 6043496432, two P2 items.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-07 17:25 UTC
**Canonical branch:** `main`
**Latest integrated code:** `704812fe9c6e953f71bcc255a41bd794524fbb38` (#391)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Claude is restored. PR #391 exact head
`d895eb3ca40beede520196409cba026d0fde0cd4` passed ordinary CI
**37617712657**, automatic Native **37617712656**, and full live Native
**37625844812** against backend **3614bf6f3805479f8d13de65eeec4f0ad7871f22**.
All 89 iOS design / 47 Watch snapshots were compared; three expected partial-map
frames changed, Watch unchanged. Full-live `09d`, `b4b2-02`, `b4b2-04` reviewed:
the **八号铁 131** label is below `洞位图`. PASS **6040488818**; correct label
correction **6041199587** (own event; deduplicate). Incorrect correction
**6041162042** and formatting-error comment **6040447618** were deleted.
#391 merged **2026-10-07 14:49 UTC** as **704812fe**; branch deleted.
PR #392 opened **2026-10-07 17:19 UTC**, exact head
`b186552b064b77f16745667927bfc2d6b9986bfa`, branch
`claude/start-round-nearby-pending-20261007`; ordinary CI **37658217088** green,
Native **37658217297** running. Current action: independent contract checks,
exact-head source review and Native screenshot evidence. Quiet stop suspended
while #392 is open; new external PR event resets the quiet interval.

#389 merged as **d679ca9029f543256b333b36cf1f998368ad04bc**; exact-head verdict
**6030960009**, live **37567463537**. Older feedback/head/run details are archived.
Consumed: #391 author's **6040089085**, own PASS, cancelled **37623923166**,
successful **37625844812**, deleted **6041162042**. Preflight-only failed
**37619843120** is superseded. Own main CI **37639893199 / 37641795035**
ignored. Own events/duplicates never reopen review or reset quiet time.
Read the **last matched event** in a waiter receipt; earlier entries may be ignored.
Preserve dirty `ops/pr_feedback_monitor.sh` and unrelated older `.codex-*`.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: existing cursor, no second monitor.
  Review new ready PRs at exact head after green CI; inspect Native artifacts and
  screenshots, post P1/P2/nonblocking verdict, merge/delete only when clear.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking: dark status-bar text on dark
  map/review pages; await a bounded implementation PR.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner's paired iPhone/Watch test.
  Native is simulator evidence; `watch-round-seeded.png` is a waiting page and
  its route marker does not establish geometry readiness.
The lightweight map fit/label follow-up is complete in #391.

## Live verification baseline

- **0.1.0 (80)** internal TestFlight; Apple **VALID / IN_BETA_TESTING**,
  operation=list/external=false. App/API/sync
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**; static text, Gemini vision.
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
- Durable evidence root `/home/jason/garmin-ai-caddie-data/operations`;
  release `release-main-3614bf6f-20261006`; #391 `pr391-353e7288-20261007`,
  full live under `live-dispatch/full-37625844812/`. Source/ZIPs/logs retained.

## Owned resources and blocking boundary

- No implementation worktree, active review snapshot/test/render container,
  download, observer, subagent, or feedback waiter before starting #392.
- #392 owned read-only snapshot `/dev/shm/garmin-ai-caddie-pr392-b186552b-20261007`,
  evidence `operations/pr392-b186552b-20261007`, helper/manifest `.codex-pr392-*`,
  expiry **Oct 8 17:25 UTC**. Planned temporary test container
  `codex-pr392-b186552b-tests-20261007`; no worktree/deps/port/volume/service.
- #391 snapshot `/dev/shm/garmin-ai-caddie-pr391-353e7288-20261007` closed after
  retained-source, process-reference and Docker-mount verification.
  Receipts in `operations/pr391-353e7288-20261007`: `snapshot-cleanup-receipt.json`
  (15:48 UTC), `local-cleanup-manifest.json`, `local-cleanup-receipt.json`.
  All 34 local image/helper files verified against `local-review-backup/`,
  then ten exact local resources moved to user trash; recoverable there or
  from durable backup. Production 39055 / candidate 39089 health unchanged.
- Older #391 64905987 snapshot/local copies closed; receipt retained.
- Local `.codex-pr389-56022d32-live-review/` comparison copies remain;
  expiry **Oct 7 21:15 UTC**, persistent originals on homeserver. Next feedback
  waiter may timeout then for exact allow-list cleanup.
- #389 6fea0239 local helper/screenshot copies: persistent backup
  `operations/pr389-6fea0239-20261007`, expiry **Oct 8 03:22 UTC**.
  No remaining remote snapshot/container/service/volume for that review.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089,
  full-SHA candidate API and matching sync image retained for owner tests.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110;
  isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13; exact release allow-list retained. Production DB/volume protected.
- Last capacity **63 GiB disk / 4.6 GiB available RAM**.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`; SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `blocking-waits/feedback-cursor`: never edit/delete.
- Same-turn terminal → clock.sleep(300000) → one write_stdin until its one-line
  conclusion. No idle CI/ps/state/log/liveness polling, independent waiter tmux,
  duplicate monitor or CI-only commits; existing feedback timer unchanged.
- Every GitHub comment/review ends `_Generated by Codex_`; commits end with
  `Generated-by: Codex`. Own commits/CI ignored by broad waiter.

## Next action and stopping

Resume the feedback cursor waiter in the same turn, bounded by the next owned
resource expiry or stop deadline. Process only its one-line conclusion; no
weakened assertions or CI-only bookkeeping commits.
Stop after **48 quiet hours/no open PRs** or absolute **2026-10-09 23:59 UTC**;
own events never reset quiet time. Close or hand back owned resources at stop.
Keep ledger ≤200 lines/current-only; archive superseded detail verbatim.
After compaction read ledger, inspect Git/agent status, resume this slice.
