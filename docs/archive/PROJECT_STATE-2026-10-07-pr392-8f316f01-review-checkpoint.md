HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before the PR392 8f316f01 review checkpoint, 2026-10-07.
Use docs/operations/PROJECT_STATE.md for current state.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-07 19:43 UTC
**Canonical branch:** `main`
**Latest integrated code:** `704812fe9c6e953f71bcc255a41bd794524fbb38` (#391)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Claude is restored. PR #392 open, branch
`claude/start-round-nearby-pending-20261007`. Last reviewed head
**ee3792096401d154f72619f3d5879d5e38b096c3**; await newer Claude feedback/head.
New actionable head **8f316f016a60157dd3140ba57b93fb350b911840** under review:
ordinary **37674411741**, Native **37674411722**, independent **132 / 16.669 s**
passed. Claimed coverage/recent fixes still require screenshot review;
live review **37676853476** in flight for the real pending tap and history timeout.
Native merge **e755122e** has no mobile/ios/workflow diff from this head.
Artifacts digests checked: 93 iOS/47 Watch; 91 iOS and all Watch frames unchanged.
Selected subtitle correctly reads `27 洞` without a played claim. Zoomed map
loses the extra 八号铁 164 label seen in ee379209 despite unchanged map code;
no control overlap, note snapshot stability separately from this start-page PR.
Ordinary **37664261141**, automatic Native **37664261261**, independent
**132 / 6.087 s / OK** passed. Compiled merge **e97a75d7** has no mobile/ios diff.
All three artifact SHA256s checked; **93 iOS / 47 Watch** frames compared to
reviewed #391. Four added nearby-phase frames inspected, plus changed selected
caption and zoomed map (extra 八号铁 164 label, clear of controls); Watch unchanged.

**Two P2 remain; no merge**:
- Count provenance, comment **6044451139**: raw downloaded=9 can be reconciled
  to catalogue=18 before subtitle, falsely saying 已下载 18 洞. Also synthetic
  carried/default rows use source=recent without a played record: selected
  fixture falsely says 最近打过 27 洞. Preserve actual download coverage and
  distinguish genuine recent evidence from carried/catalogue authority.
- Actual waiting-time selection, comment **6045129506**: live pending-01 already
  has Palace/front/blue selected (PNG and AX tree); conditional tap is skipped,
  pending-02 unchanged. Require a real unselected→selected/action-changing
  journey and retained course/loop/tee after nearby arrives.

Live review **37666850323** failed: RealFlow's review evidence resolver timed
out on history/shotmap HTTP reads (~20 s each), before app flow. TeeSelection
**8 / 564.751 s / 0 failures**, ReviewEdit passed; whole run **10 / 1 failure**.
Do not label the run PASS or weaken assertions. ZIP digest checked, **27 PNGs**,
including three nearby-pending captures inspected. Runtime proves existing
preselection retained, not a new user pick. Later authorized warm shotmap GET:
origin **200 / 2.319 s**, HTTP/2 tunnel **200 / 3.255 s**, 165,136 bytes; this
does not prove the cause of earlier runner timeouts. First 401 probe is invalid
latency evidence and retained separately. Stronger live revalidation still needed.

Initial b186552b review / ordinary **37658217088** / Native **37658217297**
consumed; verdict **6043496432**. Intermediate **69cdc9c3** superseded by ee379209.
Own comments and old CI/head events are deduplicated, not fresh review work.
#391 merged **704812fe**, full live **37625844812**, PASS **6040488818**,
label correction **6041199587** (八号铁 131), branch deleted. #389 merged d679ca90.
PR392 opened **Oct 7 17:19:48 UTC**; quiet stop suspended while open.
Read the **last matched event** in waiter logs; earlier own events may be ignored.
Preserve dirty `ops/pr_feedback_monitor.sh` and unrelated older `.codex-*`.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: existing cursor, no second monitor.
  Await #392 fixes; exact-head checks/Native artifacts/screenshots, P1/P2 verdict,
  merge/delete only after blocking findings and required evidence are clear.
- `LIVE-HISTORY-REQUEST-TIMEOUT` — `evidence-open`: failed live review above;
  inspect/revalidate without dropping assertions or claiming full-run success.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking: dark status-bar text on dark
  map/review pages; await bounded implementation PR.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner's paired iPhone/Watch test.
  Native is simulator evidence; `watch-round-seeded.png` is a waiting page,
  its marker does not establish geometry readiness.
Lightweight map fit/label follow-up completed in #391.

## Live verification baseline

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
  release `release-main-3614bf6f-20261006`; #391 `pr391-353e7288-20261007`;
  #392 `pr392-b186552b-20261007` / `pr392-ee379209-20261007`.
  Source/ZIPs/logs/review bodies/verification and cleanup receipts retained.

## Owned resources and blocking boundary

- New read-only snapshot `/dev/shm/garmin-ai-caddie-pr392-8f316f01-20261007`,
  remote `codex-pr392-8f316f01-tests-20261007` (--rm) registered for exact-head
  review; expiry **Oct 8 19:43 UTC**. Evidence `operations/pr392-8f316f01-20261007`;
  local `.codex-pr392-8f316f01-*` helpers and three Native image copies owned,
  see resource manifest; close after review.
  No implementation worktree, observer, subagent, or feedback waiter active.
- #392 ee379209 snapshot closed **19:23 UTC** after retained-source/process/mount
  checks; **21 local helper/image files** verified, **12 exact resources** moved
  to user trash. `pr392-ee379209-20261007` retains snapshot/local cleanup
  manifests/receipts, all Native and live originals, visual sheets and probes.
  Both 39055/39089 healthy; no service/port/volume created. Earlier b186552b,
  #391 and remote #389 review resources closed; older unrelated files protected.
- Local `.codex-pr389-56022d32-live-review/` remains; expiry **Oct 7 21:15 UTC**,
  persistent originals retained. Bound feedback wait to expiry for exact cleanup.
- #389 6fea0239 local helper/screenshot copies backed up in
  `operations/pr389-6fea0239-20261007`, expiry **Oct 8 03:22 UTC**;
  remote snapshot/container/service/volume already closed.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089;
  full-SHA candidate API + sync images retained for owner tests.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110;
  isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13; release allow-list retained. Production DB/volume protected.
- Last capacity **63 GiB disk**; previous available RAM **4.6 GiB**.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`; SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `blocking-waits/feedback-cursor`: never edit/delete.
- Same turn: terminal → clock.sleep(300000) → one write_stdin until one-line
  conclusion. No idle CI/ps/state/log polling, independent waiter tmux, duplicate
  monitor or CI-only commits; existing feedback timer unchanged.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.
  Own commits/CI/duplicate events never reset quiet or reopen review.

## Next action and stopping

Resume existing feedback cursor in this turn, bounded by owned-resource expiry
or stop deadline. Read only returned event evidence; review latest actionable
Claude head and resolve P2/live evidence before merge.
Stop after **48 quiet hours with no open PRs** or absolute **Oct 9 23:59 UTC**;
own events never reset quiet. Close or hand back resources at stop.
Ledger ≤200 lines/current-only; archive superseded detail verbatim.
After compaction read ledger, inspect Git/agent status, resume this slice.
