# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived 2026-10-07 after PR392 ee379209 source, Native artifact and live
review. Intake state preserved verbatim. Latest verdicts: 6044451139 and
6045129506; the live run failed. Current state is PROJECT_STATE.md.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-07 18:20 UTC
**Canonical branch:** `main`
**Latest integrated code:** `704812fe9c6e953f71bcc255a41bd794524fbb38` (#391)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Claude is restored. PR #392 is open, branch
`claude/start-round-nearby-pending-20261007`, head
**ee3792096401d154f72619f3d5879d5e38b096c3**. Claude addressed the two P2
items in 69cdc9c3, then corrected fixture phase seeding in ee379209. Ordinary
CI **37664261141** green; automatic Native **37664261261** pending. Independent
exact-head checks **132 / 6.087 s / OK**, --rm test container ended. Live review
**37666850323** dispatched after origin/tunnel revision checks, fixture=false,
capture_scope=review, retained Build80 backend. Current action: Native frames
and the real delayed-nearby/downloaded-course selection journey.
The initial b186552b review completed:
ordinary CI **37658217088**, Native **37658217297**, independent **132 / 16.963 s**
passed. Native compiled merge **f2201251753dfdda3ab86dabd8e996a913128b82**
has no `mobile/ios` diff from the reviewed head. All three artifact SHA256s
verified; all **89 iOS / 47 Watch** frames match the reviewed #391 baseline.
Inspected `full-start.png` and `full-start-selected.png`; neither depicts
the new pending/downloaded state.

Verdict comment **6043496432**: **two P2, no merge**.
- Count scope: a recent A/9-hole row dedupes the downloaded A/B row, so the
  new `.downloaded`-only subtitle leaves a bare 9→27 change when nearby arrives.
  Express the count's actual scope separately from ordering/source priority;
  retain venue deduplication and single-source loop authority.
- New UI evidence: deterministic pending-before-fix, pending-request-with-rows,
  and completed screenshots; existing rows must remain selectable, late results
  retain selection, failure/manual search must end the wait. Current new test
  checks strings only. A bounded fixture journey is enough.
Nonblocking: document this limited status-copy exception in README §8/B4.

Wait for Claude's substantive reply/new head. Initial `pr_opened` is consumed;
old b186552b CI/head events and own review comment are deduplicated evidence.
PR #392 opened **2026-10-07 17:19:48 UTC**: quiet stop suspended while it is open.
A new external PR event resets quiet; own events never do.
#391 exact head **d895eb3c** merged **704812fe** after full live **37625844812**;
PASS **6040488818**, label correction **6041199587** (八号铁 131), branch deleted.
#389 merged **d679ca90**, verdict **6030960009**, live **37567463537**.
Older runs/comments/heads, superseded preflight failure and deleted corrections
are archived. Own main CI **37648112679** ignored. Read the **last matched event**
in waiter receipts; earlier log entries may be ignored.
Preserve dirty `ops/pr_feedback_monitor.sh` and unrelated older `.codex-*`.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: existing cursor, no second monitor.
  Await #392 fixes, review each new ready head after green CI and Native
  artifacts/screenshots, post P1/P2/nonblocking verdict, merge/delete when clear.
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
  download, observer, subagent, or feedback waiter before starting corrected head.
- Read-only snapshot `/dev/shm/garmin-ai-caddie-pr392-ee379209-20261007`,
  evidence `operations/pr392-ee379209-20261007`, local `.codex-pr392-ee379209-*`;
  expiry **Oct 8 18:20 UTC**. One --rm test container; no worktree/deps/port/volume.
- #392 snapshot `/dev/shm/garmin-ai-caddie-pr392-b186552b-20261007` removed after
  source archive, process-reference and mount checks; temp test container ended.
  Durable `operations/pr392-b186552b-20261007` retains source, artifacts, logs,
  review body, manifest, `snapshot-cleanup-receipt.json` (17:45 UTC),
  `local-cleanup-manifest.json` / `local-cleanup-receipt.json`.
  Seven local helper/image files verified against retained copies, six exact
  resources moved to user trash. Both services healthy; no port/volume created.
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
- Last capacity **64 GiB disk / 3.9 GiB available RAM**.
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
