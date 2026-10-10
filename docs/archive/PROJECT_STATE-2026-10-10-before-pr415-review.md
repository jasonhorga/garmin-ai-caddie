HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 17:26 UTC
**Canonical branch:** main; product merge d3f05e13b884773041e4ad22c3f0343e9bcd3201
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

#414 head336c12a352189494c575d961de02f84c49e5f250 blocked in6100191973:
one P2: an older undelivered Watch mark overrides a newer phone mark because
absence from phoneShotIds is treated as chronology. Require capture identity/
time and same-hole newest-origin selection; real receive/record/relaunch tests.
Contracts126/10.294s/OK; CI38065042464 green, Native38065042410 iOS786/0,
Watch453/0 plus2 UI tests; merge21e26c76 parent2 is exact head.144 PNGs,
139 unchanged from #412, all5 changed Watch PNGs visually inspected/readable.
The initial acknowledgement-lifetime claim was corrected in the same comment
after call-site tracing; first version retained, not an outstanding finding.
Snapshot/containers/local copies closed. Report2026-10-10-pr414-review-336c12a3.md.
Old/self #406/#413 events deduplicated; resume one feedback terminal next.

#413 head a6ff242d2086096303e62906104e1d8c2a4bc56b reviewed in6099765021:
one P2, not merged. Bottom-fit pass can move left-side multi-leg labels back
inside the newly excluded rootFactsFrame; concrete41mm rectangle case is in
the comment/evidence. Require final exclusion/bounds/nonoverlap properties and
crowded four-leg tests on41/45/49mm, then review the new exact head.
Contracts126/5.402s/OK; CI38063457169 green. Native38063457127 iOS785/0,
Watch451/0 plus2 UI tests; checkout12a05637 parent2 is exact head.
All144 PNGs downloaded:136 match #412,8 intended root changes inspected against
owner request/README/B6/prototype. Normal full-bleed/player/chip/plays-like
layout looks correct. Snapshot/containers closed; source/artifacts/review retained.

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

- `PR414-REVIEW` — `blocked`: capture-order P2 comment6100191973 at336c12a3;
  wait for author fix, then exact-head tests/Native/snapshots. Do not merge.
- `PR413-REVIEW` — `blocked`: P2 comment6099765021 at a6ff242d; author fix
  and new exact-head Native/contract/visual verification required. Do not merge.
- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: resume one same-turn feedback
  terminal after review; deduplicate old/self events.
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

- #414 evidence: /home/jason/garmin-ai-caddie-data/operations/pr414-336c12a3-20261010.
  Snapshot28,265,982bytes removed after1,275 hashes/open-file/process checks;
  --rm contracts/visual containers absent. All144 Native PNGs/provenance,
  review versions/comment/correction and cleanup retained. Seven local controls/
  sheet/manifest backed up/hash-matched/removed. Production health200/f9586f6c.
  No active snapshot, implementation worktree, service, tunnel or subagent.
  No feedback terminal pending; resume it after publishing this real review.
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
- #408 local controls were backed up/hash-matched and removed (seven files).
  Preserve unrelated dirty ops/pr_feedback_monitor.sh and older .codex-* files.
  Local main's older two docs commits remain intact. Remote canonical checkout
  is now Claude's #414 branch336c12a3 with in-flight Swift edits: preserve its
  HEAD/files/index. Publish review docs through a separate temporary Git index
  based on origin/main; do not switch/reset/stash either working checkout.
- No pending feedback wait at deployment closeout. Resume it in the same control
  turn after pushing this real operations change. gh-feedback timer/cursor unchanged.
- #413 evidence: /home/jason/garmin-ai-caddie-data/operations/pr413-a6ff242d-20261010.
  Snapshot removed28,259,017 bytes after1,275 archive-file hashes/open-file checks;
  --rm contracts/visual containers absent. Native artifacts/144 PNGs/comparison/
  contact sheets/provenance/P2 review/cleanup retained. Local helpers/two sheets
  are hash-matched to remote copies and closed after review publication.
  No active snapshot, implementation worktree, preview/tunnel or subagent.

## Next action and stopping

Consume feedback from the durable cursor; prioritize the #413/#414 P2 fixes and
the #406 atomic-writer fixture follow-up when they arrive. Review each new exact
head/Native artifacts, then approve/merge/delete only when clear. Resume
ops/wait_for_conclusion.sh --feedback in one same-turn background terminal.
Wait300000ms, read its handle once, repeat until its one-line terminal result.
Do not inspect waiter liveness or run a second monitor. Only then read the
returned event, deduplicate and handle genuine PR feedback. No CI-only commits;
ignore Codex comments/commits/CI as feedback or quiet resets.

The historical October9 cutoff was superseded by the owner's explicit resume.
Stop after48h with no external PR events and no open PRs, or an owner stop.
Latest handled external event: #414 Native completion2026-10-10 16:04:49 UTC;
earliest quiet stop2026-10-12 16:04:49 UTC, conditional on no newer external
events and no open PRs. Verify both conditions before completing the goal.
Keep this ledger≤200 lines.
