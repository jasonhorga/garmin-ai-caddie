# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-07 20:44 UTC
**Canonical branch:** `main`
**Latest integrated code:** `704812fe9c6e953f71bcc255a41bd794524fbb38` (#391)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Claude restored. PR **#392** open; branch
`claude/start-round-nearby-pending-20261007`, reviewed head
**8f316f016a60157dd3140ba57b93fb350b911840**. Original P2 findings resolved:
- Installed coverage now counts raw downloaded templates, not catalogue holes.
  Actual subtitle-chain test installed=9/catalogue=18 passes.
- Carried/default A/B/C with no played record now says `27 洞`.
- Live pending-01 is genuinely unselected; pending-02 has a real tap, while
  waiting; pending-03 keeps Palace/front/blue and the same start action.

Ordinary **37674411741**, automatic Native **37674411722**, independent
**132 / 16.669 s / OK** pass. Native merge **e755122e** has no mobile/ios,
Package.swift or workflow diff. Three artifact digests checked; **93 iOS /
47 Watch** compared with reviewed ee379209. 91 iOS/all Watch unchanged.
Selected subtitle inspected and correct. Zoomed image inspected: extra
八号铁 164 label varies despite unchanged map/fixture; no control overlap;
snapshot timing stability is nonblocking, separate from start-page behavior.

**Do not merge yet**: live **37676853476 attempt 1** failed **10 / 1 failure**,
sole failure city-search catalogue fallback could not find Palace 31793.
RealFlow **302.452 s**, ReviewEdit **180.930 s**, downloaded/offline journey
**157.690 s** passed; TeeSelection **8 / 702.684 s / 1 failure**.
Two live artifacts SHA256 checked; **38 actual PNGs**, all three pending
screens and failing search screen inspected plus AX. History timeout did not
recur; no causal diagnosis claimed. Native simulator evidence is not a device test.
Failure AX has 16 mounted List rows at the bottom; it does not prove the
complete response omitted Palace. One current warm identical city search:
**200 / 0.852 s / 51 matches**, 31793 present (index 31); not first-response proof.
Claude reran failed job as **attempt 2 at 20:27 UTC**; reuse that run, no duplicate
dispatch. Preserve original offline/GPS/city assertions; await terminal result.

Progress verdict **6046490302** closes old P2, leaves live validation open and
asks for actual response/search-complete/scroll evidence if failure recurs.
Claude replies **6045536908 / 6046215308** consumed. Prior P2
**6043496432 / 6044451139 / 6045129506**, b186552b/69cdc9c3/ee379209 heads and
their CI are superseded/deduplicated. Own comments/CI never reopen the review.
#391 merged **704812fe**, live **37625844812**, verdict **6040488818**,
label correction **6041199587** (八号铁 131); branch deleted.
#392 opened Oct 7 17:19:48 UTC; latest known external event **20:27:01 UTC**;
quiet stop suspended while PR open. Read last matched waiter event, not earlier
ignored own lines. Preserve dirty `ops/pr_feedback_monitor.sh`/unrelated files.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: await #392 live attempt 2,
  verify final artifacts; P1/P2 verdict, merge/delete after blockers clear.
  Then existing feedback cursor, no second monitor; review new actionable heads.
- `LIVE-CATALOGUE-FALLBACK` — `evidence-open`: first live attempt failed
  above; rerun and evidence needed, no assertion relaxation.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status text on dark maps.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner's paired iPhone/Watch test.
  `watch-round-seeded.png` is a waiting page, not geometry-readiness proof.

## Live verification baseline

- **0.1.0 (80)** internal TestFlight, Apple **VALID / IN_BETA_TESTING**,
  operation=list/external=false. App/API/sync
  **3614bf6f3805479f8d13de65eeec4f0ad7871f22**, static text / Gemini vision.
- Passed: live Native **37426762320**, TestFlight **37438559636**,
  Apple read-only **37440770465**. IPA **11400009027**, ZIP SHA256
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
  App/Watch versions, origin/backend/provenance checked; no production switch.
- Synthetic pin sheet 200/18.901 s; exact date/three holes/front facts.
  HTTP/2 package 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  tunnel 2.10–2.34 s, HTTP/2/200.
- Live origin `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production `aicaddie-release-d7f69971-production-20260925`, port 39055,
  revision **d7f699712f7ac6cba41d97c420c405e090625caf**.
- Durable root `/home/jason/garmin-ai-caddie-data/operations`;
  release `release-main-3614bf6f-20261006`; #391 `pr391-353e7288-20261007`;
  #392 `pr392-8f316f01-20261007`: source, tests, Native/live artifacts,
  probes, review body and cleanup receipts. Prior #392 evidence also retained.
- Current snapshot/API/sync baseline is for Build80; reviewing #392 does not
  claim it is deployed or uploaded to TestFlight.

## Owned resources and blocking boundary

- No implementation worktree, active read-only snapshot, test/render container,
  download, observer or subagent. #392 8f316f01 snapshot closed after source
  archive/file/process verification; receipt in its persistent evidence.
- Local `.codex-pr392-8f316f01-*` review helpers and seven screenshot copies
  owned; expiry **Oct 8 19:43 UTC**, manifest retained in its evidence directory.
  Close/recoverably remove after final review, preserve permanent originals.
- #389 56022d32 local image directory closed **Oct 7 20:44 UTC**:
  **41 files / 13,256,841 bytes**, remote SHA256 backup verified, moved to user
  trash. Exact allow-list/receipt retained in `pr389-56022d32-20261006`;
  remote snapshot/container had already closed. Older unrelated files protected.
- #389 6fea0239 local helpers/screenshots backed up in
  `operations/pr389-6fea0239-20261007`; expiry **Oct 8 03:22 UTC**.
  Remote snapshot/container/service/volume already closed.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089;
  full-SHA candidate API + sync images retained for owner tests.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110;
  isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13; release allow-list retained. Production DB/volume protected.
- Latest capacity **63 GiB disk / 4.2 GiB available RAM**.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`; SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `blocking-waits/feedback-cursor`: never edit/delete.
- SSH/run-watch EOF interrupted attempt-1 waiting once; recovered without
  redispatch. Error and final logs retained. No active waiter at this update.
- Same turn: terminal → clock.sleep(300000) → one write_stdin until one-line
  conclusion. No idle CI/ps/state/log polling, independent waiter tmux, duplicate
  monitor or CI-only commits. Existing feedback timer unchanged.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.
  Own commits/CI/duplicate events never reset quiet or reopen review.

## Next action and stopping

Block on **37676853476 attempt 2** in this same turn. Resolve failed validation
or inspect final evidence and merge #392; then existing feedback cursor bounded
by next owned-resource expiry/stop deadline. Do not dispatch another duplicate run.
Stop after **48 quiet hours with no open PRs** or absolute **Oct 9 23:59 UTC**;
own events never reset quiet. Close/hand back resources at stop.
Ledger ≤200 lines/current-only; archive superseded detail verbatim.
After compaction read ledger, inspect Git/agent status, resume this slice.
