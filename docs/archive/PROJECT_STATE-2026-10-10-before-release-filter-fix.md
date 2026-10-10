> HISTORICAL ARCHIVE — NON-AUTHORITATIVE
>
> Verbatim ledger before the manual-release provenance fix and build verification.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 19:14 UTC
**Canonical branch:** main; latest product merge a08634a86a43f576cf1288eb393d581195d3f9f8
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

#414 corrected head c13a717e7c1724f59fb8301dcdb7a16238989ef1 independently
approved6100961909; merged de2cedcf; exact-head branch deleted.
Capture-order P2 closed: phone sends the latest shot's own capture time and
Watch selects the newest same-hole origin by time. Real record/receive/relaunch/
other-hole regressions executed successfully; snapshot revision guard retained.
Contracts126/8.492s, CI38072029710 and Native38072029726 green:
iOS786/0, Watch454/0 plus2 UI tests. Native79edbfd1 parent2 is exact c13a717e,
parent1 cbb45f5d. All144 PNGs match reviewed336c12a3;8 Watch frames reinspected.
Clean merge-tree with current main preserves #413 root/layout fixes.
Source/snapshot/containers/seven local controls closed. Report
2026-10-10-pr414-review-c13a717e.md; evidence published2678fd23 with shared
normal index unchanged.

#416 head a38a97bc4e520dd30fa5f7bc36ec11580674fcdb approved6101180215,
merged a08634a8; exact-head branch deleted. Horizontal-leader follow-up closed.
Contracts126/6.491s; CI38075749402 and Native38075749433 green:
iOS785/0, Watch452/0 plus2 UI tests; crowded-layout leader assertions executed.
Native58314394 parents a0ade550/exact a38a97bc.144 PNGs downloaded;143 unchanged,
all Watch images match reviewed #413. The one changed iOS zoomed image gains
八号铁164; before/after inspected, iOS source unchanged, existing fixture-stability
follow-up remains nonblocking. Clean current-main integration preserves #414.
Report2026-10-10-pr416-review-a38a97bc.md; resources closed; evidence published
b662572e with shared normal index unchanged. Feedback terminal20278 ended SSH255
without a summary (remote host closed channel); transport recovery is current operation.
Do not assume a PR event was consumed; preserve cursor. No local terminal pending.
At20:02UTC SSH banner exchange timed out, while local127.0.0.1:2223 listeners
remain. Public health probe also failed TLS connection (curl35); production
status cannot be inferred. No proxy/key/route/service changes were made.
Wait300000ms between bounded SSH reconnect attempts; after reconnect recover
single-wait ownership before rearming. Last known service health is19:10UTC/cbc17f4e.
SSH recovered20:10:16UTC. Exact old orphan PID73178 closed under the
feedback-recovery-20261010T2010 manifest; cwd/start/UID/command/fds checked,
its own tail child closed, cursor/shared monitor preserved. Health200/cbc17f4e.
Recovery log shows TestFlight run38079005590 failed19:20:08 but was filtered
as self-generated; verify through explicit --release conclusion before handling.
Explicit release verdict returned failure/testflight, log
blocking-waits/wait-release-38079005590-20261010T201619Z-122809.log.
Build86 archive/export succeeded; Fastfile backend preflight TLS unexpected EOF
failed before upload_to_testflight. Public health now200/cbc17f4e; SSH returned
again20:22:23 after one transient local connection refusal, no config changes.
Claude already dispatched retry38083089271 at20:16:20 on b662572e, in progress;
follow that existing release, avoid duplicate dispatch. Fix the self-head filter
to deliver manual TestFlight/Apple conclusions while keeping own push-CI ignored.

#413 approved6100717513 at eeb99712, merged a0ade550, branch/resources closed;
evidence published3f0238d8. Report2026-10-10-pr413-review-eeb99712.md.
Its horizontal-leader suggestion is nonblocking, not an open P2.
#415 approved6100310265 at d9a05556, merged cbc17f4e; API/sync deployed.
Reports/review/deployment/resource evidence published d4f17933.
#404–#412 already reviewed/merged/deployed as applicable. Do not repeat
their handled reviews, comments or CI results; dated archives preserve detail.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: one same-turn durable feedback
  waiter; deduplicate old/self events, review author corrections and new PRs.
- `PR416-REVIEW` — `done`: a38a97bc approved/merged a08634a8; branch/resources closed.
- `PR414-REVIEW` — `done`: capture-order P2 fixed; c13a717e approved/merged
  de2cedcf, exact-head branch and temporary resources closed.
- `PR413-REVIEW` — `done`: eeb99712 approved/merged a0ade550; resources closed.
- `PR415-BACKEND-DEPLOY` — `done`: cbc17f4e API/sync live and manually synced.
- `WATCH-PLAN-HORIZONTAL-LEADERS` — `done`: #416 handles #413's suggestion.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 variation; nonblocking,
  reproduced/reported in #4166101180215; fixed-route snapshots should be consistent.
- `IOS-STATUS-CONTRAST` — `queued`: dark navigation/status text; nonblocking.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired-device validation owner work.
- `NEXT-INTERNAL-IOS-RELEASE` — `evidence-open`: Claude reports build85;
  independently inspect release/Apple evidence when delivered. No upload this slice.
- `WAIT-RELEASE-EVENT-FILTER` — `queued`: current operations fix; manual CD
  conclusions are incorrectly discarded when their head is a Codex commit.
- `RELEASE-38083089271` — `queued`: bounded delegated explicit-release wait;
  read-only, no dispatch/PR messages/source edits; return terminal conclusion only.

## Live verification baseline

- Production API aicaddie-release-cbc17f4e-production-20261010, loopback39055;
  public https://caddie.taile36706.ts.net; health exact cbc17f4e revision.
  API garmin-ai-caddie-api:cbc17f4e76f085229c3bdb3c74a5067951b217a6-candidate-20261010,
  ID sha256:337d893f73039d863ada4967012dddbe9d91acda637645fe15ea7779a56b35c5.
  Sync aicaddie-sync:cbc17f4e76f085229c3bdb3c74a5067951b217a6,
  ID sha256:b3e870d74407f0df355087a67ff3dd6718abc62e9f027e503166d20afe77ca64.
  Prebuilt binding/post-switch and installed sync revision gates passed.
- Startup/switch/gates23.617s under shared sync lock. Protected DB/private volume,
  network and ingress retained. Public/loopback health/history/sync status200.
  Three-hole precise prep200/all-ready6.4467s; cached PNG200/0.1024s/678x1060;
  history200/0.0631s. Server probes, not phone loading timings.
  Manual sync17:51:52→17:52:25UTC/33s, exact revision/sync ok/done.
  New-image43 related/deployment tests/0.969s passed.
- Last independently verified TestFlight0.1.0(82): upload37774511661;
  Apple37776197288 VALID/IN_BETA_TESTING; IPA
  f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721.
  Claude-reported83/85 remain unverified here; no new package claim.
- #413 Native38068696361 iOS785/0, Watch452/0 plus2 UI tests;144 PNGs match a6ff.
  #414 Native38072029726 iOS786/0, Watch454/0 plus2 UI tests;144 PNGs match336c.
  Neither is a physical Watch GPS/battery/WCSession timing claim.
  Last merged-source live capture37990736669 iOS772/0, Watch448/0.
- Prior #404/#406 workload35.4904→22.9303s,237 tests passed/5 skips;
  scope/conditions in2026-10-10-pr404-406-backend-deploy.md; no new phone-speed claim.

## Owned resources and cleanup

- No active snapshot/worktree/dependency env/container/volume/service/tunnel/agent.
  Terminal20278 ended SSH255; its exact old orphan73178 is now closed with
  manifest/receipts under operations/feedback-recovery-20261010T2010.
  No feedback terminal pending. Explicit release38079005590 conclusion is next.
  #416 evidence operations/pr416-a38a97bc-20261010:
  source/contracts/Native/144 PNGs/comparison/integration/review/merge/cleanup retained.
  Snapshot28,366,673bytes removed after source/file-hash/open-file/process checks;
  --rm contracts/visual containers absent; health200/cbc17f4e. Eight local review
  scripts/input/images1,349,809bytes hash-matched to persistent backups and removed.
  Exact branch head checked before deletion; allow-list/cleanup receipts retained.
  Alternate publication index removed after guarded push; shared normal index preserved.
  Capacity49GiB disk/5.0GiB available RAM/4GiB shm before work.
- #414 evidence /home/jason/garmin-ai-caddie-data/operations/pr414-c13a717e-20261010:
  source/provenance/diffs/contracts/Native/all144 PNGs/hash/sheets/integration/
  review/comment/merge/branch cleanup retained. Read-only snapshot28,268,570bytes
  removed after archive/file-hash/open-file/process checks; --rm containers absent.
  Seven local scripts/input/sheets206,523bytes hash-matched to persistent backups
  and removed under exact allow-list; manifest/receipt retained. Health200/cbc17f4e.
  Alternate Git-index publication only, removed after guarded push.
- #413 evidence operations/pr413-eeb99712-20261010 retained; snapshot28,263,275bytes,
  containers/branch/seven local files202,949bytes closed. Publication3f0238d8 used
  alternate index; normal shared index unchanged. Local allow-list is audit evidence.
- #415 review/deploy evidence operations/pr415-d9a05556-20261010 and
  operations/pr415-deploy-cbc17f4e-20261010 retained; snapshot28,319,648bytes/
  candidate/disposable volume/local scripts closed. f9586f6c stopped/retained rollback;
  b0f64b65/3614bf6f remain protected. User volume/DB/ingress unchanged;
  deploy-tools pinned cbc17f4e. Historical #414/#404–#412 details are dated archives.
- Preserve unrelated dirty ops/pr_feedback_monitor.sh and older .codex-* files.
  Local main's older docs commits remain intact. Shared canonical remote checkout
  /home/jason/codex-runs/garmin-ai-caddie-claude-takeover-20261005 belongs to Claude
  too: never switch/reset/stash, alter its files or use its normal index.
  Publish scoped evidence via alternate index on fresh origin/main.
- gh-feedback timer and blocking-waits/feedback-cursor unchanged.

## Next action and stopping

Completed #416 evidence publishedb662572e. Transport restored and orphan73178
closed. Get --release38079005590 one-line conclusion and diagnose real failure;
keep the release evidence separate from own push-CI filtering. Then resume
ops/wait_for_conclusion.sh --feedback in one same-turn background terminal.
Wait300000ms, read its handle once; repeat until one-line terminal result.
Do not inspect waiter liveness or start a second monitor. Read only returned
event/log; handle new heads/PRs with exact tests/Native and visual review.
Approve/merge/delete only when clear. No CI-only commits; ignore Codex
comments/commits/CI as actionable events or quiet resets.
Deduplicate38063457169/38063457127/38065042464/38065042410/38065207338/
38072318888/38068696174/38068696361/38072029710/38072029726/
38075749402/38075749433; ignore own #413 merge CI38075353239/a0ade550.
#413 reply6099812003 and #414 correction6100271007 are already handled.

Owner resumed after historical October9 cutoff. Stop after48h without external
PR events and with no open PRs, or an owner stop. Latest independently handled
external check-set event: #4162026-10-10 18:40:59UTC (same verified Native result);
earliest conditional quiet stop2026-10-12 18:40:59UTC. Verify no newer external events and no open PRs
before completing the goal. Keep this ledger≤200 lines.
