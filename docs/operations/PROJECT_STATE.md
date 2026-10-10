# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 15:47 UTC
**Canonical branch:** main; product merge d3f05e13b884773041e4ad22c3f0343e9bcd3201
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Owner resumed review after the historical October9 cutoff. #404–#412 were
reviewed at exact heads, approved by comment, merged and their branches deleted.
Do not repeat handled review/merge/CI events. Exact-head tests, Native snapshots,
comments and cleanup details are retained verbatim in the dated archives:
- PROJECT_STATE-2026-10-10-before-pr408-deployment.md
- PROJECT_STATE-2026-10-10-pr408-deployment-in-progress.md

#412 head95801f4111f0ae3fa12fd619e91e3d8a60978e5e approved6096711733;
merge d3f05e13. Native38039403230 passed iOS/Watch, all144 snapshot hashes
match #411. Research request6096018681 answered6097100629 with the report
docs/operations/2026-10-10-watch-battery-research.md. Do not repeat that research.

#408 deployment request6098706732 on #412 cleared the live-round hold.
Main f9586f6c4e2ca20e02a7a72f4543a71a57419e49 was independently deployed;
main CI38049391237 passed at that SHA. API/sync were built before cutover.
Only production backend code difference from b0f64b65 was course_prep.py (#408).
Deployment succeeded; health/protected reads/precise prep/topo and manual sync
passed. Result report: docs/operations/2026-10-10-pr408-backend-deploy.md.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: resume one same-turn feedback
  terminal after this real deployment closeout; deduplicate old/self events.
- `PR408-BACKEND-DEPLOY` — `done`: f9586f6c API and matching sync are live;
  manual incremental sync ended15:41:15 UTC with sync ok/done.
- `CLUB-CACHE-REGRESSION-FIXTURE` — `queued`, nonblocking: comment6099157088
  on #406 asks Claude to use the real atomic writer and assert unchanged size/
  mtime plus changed inode. Initial deployment suite241/3.737s had one flaky
  in-place-fixture failure and5 existing skips; preserved, not discarded.
  Exact-source probe: production atomic writer200/200 passed with same size/
  restored mtime; fixture stale3/100 overlay,13/100 ext4 with identical metadata.
  Unmodified related suite then passed241/4.599s/5 existing skips.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: dark navigation/status text; nonblocking.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired-device validation owner work.
- `NEXT-INTERNAL-IOS-RELEASE` — `evidence-open`: Claude reports build85;
  independently check its release/Apple evidence when the event is delivered.
  This deployment did not upload a new iOS package.
- `WATCH-BATTERY-RESEARCH` — `done`: report and #412 reply delivered; Claude
 6098706732 acknowledged it and plans splitting static map/live overlays.

## Live verification baseline

- Production API: aicaddie-release-f9586f6c-production-20261010 on loopback39055;
  public https://caddie.taile36706.ts.net. Health reports exact f9586f6c revision.
  API image garmin-ai-caddie-api:f9586f6c4e2ca20e02a7a72f4543a71a57419e49-candidate-20261010,
  ID sha256:e2122d7980a016d31f968ec73901ed2d49b8a5c8f7047fff9035ad197ba26420.
  Sync aicaddie-sync:f9586f6c4e2ca20e02a7a72f4543a71a57419e49,
  ID sha256:65a7ddef96d1c5219960200fa85020a5602e30e355db1ee80a4b0c3c746b499e.
  Prebuilt binding/post-switch deployment gate/installed sync revision gate passed.
- API switch/startup/gates32.079s after the existing sync released its lock.
  Protected private volume, DB/network and ingress retained. Public/loopback
  health200, history200, sync status200; three-hole prep200/all geometry ready
  (5.9045s), cached topo PNG200 (0.058s;678x1060). These are server probes.
  Manual sync15:40:40→15:41:15 UTC/35s, exact revision confirmed/sync ok/done.
- Isolated startup health exact revision, anonymous history401, empty-data
  readiness200/degraded as expected. Related241 tests passed; first fixture
  failure and independent writer diagnosis remain part of deployment evidence.
- Last independently verified TestFlight0.1.0(82): upload37774511661;
  Apple37776197288 VALID/IN_BETA_TESTING; IPA
  f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721.
  Claude-reported83/85 are not yet independently verified in this ledger.
- Native #412 exact-head38039403230 passed;144 PNGs unchanged from #411.
  Last merged-source live capture37990736669: iOS772/0, Watch448/0.
  Physical Watch battery/WCSession timing remains next-device evidence.
- Prior #404/#406 server workload35.4904→22.9303s;237 tests passed/5 skips.
  Scope/conditions are in2026-10-10-pr404-406-backend-deploy.md; no new
  end-to-end phone speed claim from this deployment.

## Owned resources and cleanup

- Persistent new evidence:
  /home/jason/garmin-ai-caddie-data/operations/pr408-deploy-f9586f6c-20261010.
  Source tar/provenance, image IDs, original failure, writer probe, tests,
  startup/cutover/live checks, sync result, comments and cleanup receipts retained.
- Temporary snapshot /dev/shm/codex-pr408-deploy-f9586f6c-20261010 removed
  (28,257,897 bytes), source archive SHA verified and open files checked.
  Candidate codex-pr408-f9586f6c-candidate-20261010 and its labelled disposable
  private volume removed; --rm test/probe containers ended. No active snapshot,
  implementation worktree, preview service, tunnel or subagent.
- b0f64b65 prior production stopped/retained for rollback; older3614bf6f rollback
  remains protected. Existing deploy-tools refreshed and pinned to f9586f6c;
  prior tool copies retained in evidence. Shared sync lock belongs to the host.
- Local helper files for this slice are backed up and hash-checked before removal.
  Preserve unrelated dirty ops/pr_feedback_monitor.sh and older .codex-* files.
  Local main's older two docs commits remain intact; publish this slice via the
  clean remote Git checkout, without rewriting the local branch or dirty work.
- No pending feedback wait at deployment closeout. Resume it in the same control
  turn after pushing this real operations change. gh-feedback timer/cursor unchanged.

## Next action and stopping

Finish the result comments/docs commit for the verified deployment; resume
ops/wait_for_conclusion.sh --feedback in one same-turn background terminal.
Wait300000ms, read its handle once, repeat until its one-line terminal result.
Do not inspect waiter liveness or run a second monitor. Only then read the
returned event, deduplicate and handle genuine PR feedback. No CI-only commits;
ignore Codex comments/commits/CI as feedback or quiet resets.

The historical October9 cutoff was superseded by the owner's explicit resume.
Stop after48h with no external PR events and no open PRs, or an owner stop.
Latest handled external event: #412 comment6098706732 at2026-10-10 14:46:41 UTC;
earliest quiet stop2026-10-12 14:46:41 UTC, conditional on no newer external
events and no open PRs. Verify both conditions before completing the goal.
Keep this ledger≤200 lines.
