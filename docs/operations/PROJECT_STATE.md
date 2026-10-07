# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-07 08:29 UTC
**Canonical branch:** `main`
**Latest integrated code:** `d679ca9029f543256b333b36cf1f998368ad04bc` (#389)
**Latest review:** PR #391 exact-head 64905987 review; live acceptance blocked.
**Current slice:** `PR391-LIVE-LIGHTWEIGHT-MAP` — `evidence-open`

## Current state and deduplication

Claude restored. PR #391 is open; #387/#388/#389/#390 are merged and their
branches deleted. PR #391 exact head is **649059876e690a80fd90b9f3c896e4d0f511580b**
on `claude/live-lightweight-map-fit-20261007`. Ordinary CI **37583640893** and
automatic Native CI **37583640781** passed; design (89 iOS) and Watch (47)
artifacts were checked, with only the four expected iOS lightweight-map frames
different from the #387 baseline. Required live run **37587781499** is red:
9/10 selected iOS tests passed, but `RealFlowUITests.testCaptureRealAppFlow`
failed on three attempts with `NSURLError -1001` for
`GET /api/v2/history/rounds?hasShots=true&limit=120`; preflight/course discovery
were HTTP 200 and the origin log has no matching request. No live 09d,
b4b2-02, or b4b2-04 map frame was captured. P1 evidence-block comment
**6033977600** posted; do not merge until a successful live capture exists.
Evidence: `operations/pr391-64905987-20261007/observed-live-37587781499/`.

#389 exact head **6fea02399ab4136455cf333ebf1660388c372211**
merged as **d679ca9029f543256b333b36cf1f998368ad04bc** after the exact-head
live review and conclusion comment **6030960009**. Formal approval was refused
by GitHub because the PR author and Codex share the same account; the review
conclusion comment is the recorded verdict.
Author **6030082845** read: exemption now queries AX subtree, pure bottom
rule and partial/full White/real Start behavior test added. Code confirms
geometric containment removed, original acceptance assertions intact.
Source **37565345697** passed; independent **132 / 6.398 s / OK**.
Snapshot/container closed. Automatic Native **37565345670** passed,
terminal **87600** closed; all three ZIP digests/136 PNG comparison pass.
Compiled merge `d756a6ec97e9a80b253c3b710599f66756199b56` has no mobile/ios diff.
Live **37567463537** dispatched 03:35:35 UTC, exact head 6fea0239,
`capture_scope=review`, fixture=false/preflight=true against retained Build80.
White + white-T + start-page assertions intact; no full nine-loop rerun.
Origin/tunnel preflight 200: 0.007 s / HTTP/2 1.179 s. Observer manifest backed up.
Progress comment **6030396620** posted; posting terminal **5195** closed.
Live Native terminal **66412** ended `status=completed conclusion=success
failed_jobs=none` after the first observer hit a transient GitHub TLS timeout.
Review scope executed 10 tests / 0 failures (TeeSelection 8 tests / 521.913 s),
including the pure viewport ownership test. Live artifacts `real-screenshots`
ZIP digest `sha256:be78c68896c31d1cf9e53c7c0b86f4a8cd8d7b0d7872dbc7063e590ee0e27d77`
verified: 34 PNGs plus trees. White selected tree and screenshot show
`start-round-primary-action` = `从 前九 开始 · 白 T`; the app remains on
`开始一场` until explicit Start. No P1/P2 remains for this head.
Old heads/runs/comments deduplicated in dated archives; new substantive
feedback/head actionable. Own events/duplicates never reset quiet time.
When reading a waiter receipt, use its **last matched event**: it can ignore
an earlier own CI event before accepting a different PR event.
Preserve dirty `ops/pr_feedback_monitor.sh` and unrelated older `.codex-*`.

## Unfinished queue

- `PR391-LIVE-LIGHTWEIGHT-MAP` — `evidence-open`: await Claude's transport fix
  or a new exact head; re-run required live evidence, then issue P1/P2 verdict.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume existing feedback cursor;
  exact head/tests/Native artifacts/screenshots, P1/P2/nonblocking verdict,
  merge/delete only when clear. No second monitor.
- `LIGHTWEIGHT-MAP-FIT-LABELS` — `queued`, nonblocking, author acknowledged:
  facts maps hug left edge / club labels overlap `洞位图`, comment 6026853016.
  Separate follow-up after #389; examples in selector review.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking: dark system status-bar text
  on dark map/review pages.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner's paired iPhone/Watch test.
  Native is simulator evidence; Watch route marker does not prove geometry
  readiness (`watch-round-seeded.png` is a waiting page).

## Live verification baseline

- **0.1.0 (80)** internal TestFlight, Apple **VALID / IN_BETA_TESTING**,
  operation=list/external=false; app/API/sync SHA
  `3614bf6f3805479f8d13de65eeec4f0ad7871f22`.
  Text provider static, Gemini vision only; no production switch/external release.
- Passed: live Native **37426762320**, TestFlight **37438559636**,
  Apple read-only **37440770465**. IPA **11400009027**, ZIP SHA256
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
  Provenance/origin/backend and both app/watch bundle versions verified.
- Synthetic pin sheet HTTP 200/18.901 s; exact date/three holes/front facts.
  HTTP/2 package 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  tunnel 2.10–2.34 s, HTTP/2/200.
- Live origin `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production `aicaddie-release-d7f69971-production-20260925`, port 39055,
  revision `d7f699712f7ac6cba41d97c420c405e090625caf`.
- Persistent evidence root `/home/jason/garmin-ai-caddie-data/operations`;
  release `release-main-3614bf6f-20261006`; #389 roots
  `pr389-56022d32-20261006` / `pr389-854f4e0f-20261007`;
  #390 `pr390-dbd23b6a-20261006`. Source/ZIPs/logs/receipts retained.

## Owned resources and blocking boundary

- No implementation worktree, active snapshot/test/render container, download
  process, observer/sampler, CI or feedback waiter at review closure.
  Native verifier **45268** and previous feedback **59022** completed.
- PR391 exact-head snapshot `/dev/shm/garmin-ai-caddie-pr391-64905987-20261007`
  was checked for references and removed at 08:29 UTC; cleanup receipt is
  `operations/pr391-64905987-20261007/snapshot-cleanup-20261007.json`.
  Live run artifacts (including `real-screenshots`, `real-video`, and native
  evidence) remain under `operations/pr391-64905987-20261007/`; local visual
  copies were moved to the user trash after inspection.
- 6fea0239 snapshot/container closed after source backup/use checks; Native
  wait **87600**/artifact **57305** closed. Observer **23490** closed after
  GitHub TLS timeout (not a CI verdict); closure receipt confirms sampler ended.
  Same live run **37567463537** resumed in observer terminal **66412** and
  completed; sampler/waiter closure receipt retained, no feedback waiter.
  Helpers backed up in
  `operations/pr389-6fea0239-20261007`, expiry Oct 8 03:22 UTC;
  no worktree/deps/service/port/volume. Original image-copy expiry unchanged.
- Current #389 snapshot/container closed after archive/use checks. Six local
  helper/body copies removed after verified remote backups/fuser checks;
  allow-list/receipt `pr389-854f4e0f-20261007/.codex-pr389-854f4e0f-local-cleanup.json`.
  #390 and earlier #389 helpers closed; older unrelated resources protected.
- Local `.codex-pr389-56022d32-live-review` comparison copies remain,
  expiry **Oct 7 21:15 UTC**; persistent originals on homeserver.
  Next feedback wait may timeout at that expiry for exact allow-list cleanup.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089,
  image `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`;
  matching full-SHA sync image retained for owner tests.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110;
  isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13, exact release allow-list retained. Production DB/volume protected.
- Capacity **65 GiB disk / 4.5 GiB available RAM**.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`;
  SHA256 `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `blocking-waits/feedback-cursor`: never edit/delete.
- Same-turn terminal → clock.sleep(300000) → one write_stdin until its one-line
  terminal result. No idle CI/ps/state/log/liveness polling, independent waiter
  tmux, duplicate monitor or CI-only commits. Existing feedback timer unchanged.
- Every GitHub comment/review ends `_Generated by Codex_`; commits have
  `Generated-by: Codex`. Own commits/CI ignored by broad waiter.

## Next action and stopping

Await Claude's response to PR391 comment **6033977600** or a new exact head;
when actionable, re-run the required live Native capture and inspect 09d /
b4b2-02 / b4b2-04 before deciding. Until then, retain the PR391 evidence and
do not merge. After the open PR is resolved, start the existing feedback cursor
waiter in the same control turn and process only its one-line conclusion.
No weakened assertions or CI-result-only bookkeeping commit.
The 48-hour quiet interval is not active while PR391 is open. After all PRs
are closed, stop after **48 quiet hours/no open PRs** or absolute
**2026-10-09 23:59 UTC**, with owned-resource handoff. Own events never reset it.
Keep ledger ≤200 lines/current-only; archive superseded detail verbatim.
After compaction read ledger, inspect Git/agent status, resume this slice.
