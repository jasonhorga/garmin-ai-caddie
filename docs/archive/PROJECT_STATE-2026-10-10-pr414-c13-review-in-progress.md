HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived2026-10-10 at corrected #414 c13a717e review closeout.
Previous ledger follows verbatim; current authority is ../operations/PROJECT_STATE.md.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 18:27 UTC
**Canonical branch:** main; latest product merge a0ade5505758b92026eab09cb450c06a4d0da726
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

#413 corrected head eeb9971263d01ec4274033180e4c68a83634b20c independently
approved6100717513; merged a0ade550 at18:20:03UTC; exact-head branch deleted.
The original P2 is fixed: final label stacks are validated and invalid results
search horizontal/vertical slots. Actual-measured41/45/49mm four-leg Native
regressions and the176x215/54x15 case passed. Contracts126/8.026s; CI38068696174
and Native38068696361 green: iOS785/0, Watch452/0 plus2 UI tests.
All144 PNGs hash-identical to the previously reviewed a6ff head;8 root/plan/
plays-like images reinspected. No physical-GPS or new crowded-screenshot claim.
Nonblocking: leader-line condition checks Y only and should also detect X moves.
Report2026-10-10-pr413-review-eeb99712.md; source/snapshot/containers/local
control cleanup closed. Review/merge/cleanup evidence published3f0238d8;
normal shared Git index unchanged. No waiter pending during corrected #414 review.

#414 head336c12a352189494c575d961de02f84c49e5f250 blocked in6100191973:
an older undelivered Watch mark overrides a newer phone mark because absence
from phoneShotIds is treated as chronology. Require capture identity/time and
same-hole newest-origin selection; real receive/record/relaunch regressions.
Contracts126/10.294s; CI38065042464 green; Native38065042410 iOS786/0,
Watch453/0 plus2 UI tests.144 PNGs downloaded,5 changed Watch images inspected.
The initial acknowledgement-lifetime claim was corrected after call-site
tracing; the first review is historical evidence, not an outstanding finding.
Snapshot/containers/local controls closed. Report2026-10-10-pr414-review-336c12a3.md.
Author correction6100271007 at17:30:32UTC supplies new head
c13a717e7c1724f59fb8301dcdb7a16238989ef1 and lastShotCapturedAt/newest-time selection.
CI38072029710/Native38072029726 green. Independently review real receive/record/
relaunch/hole-isolation paths, Native provenance and all artifacts before merge.

#415 approved6100310265 at d9a05556, merged cbc17f4e; branch deleted.
Real Garmin200/400 writes and cache fixture use the same atomic writer.
Related26 tests and100 focused regressions passed independently on ext4.
Exact cbc17f4e API/sync deployed,43 image/deployment tests passed; protected
reads/precise prep/topo200 and manual incremental sync33s/sync ok/done.
Result comments#4156100488599/#4066100488830; report and cleanup published d4f17933.
Do not repeat #404–#412 reviews/merges/deployment or their handled feedback.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: same-turn durable feedback waiter;
  deduplicate old/self events; handle new PRs and author corrections.
- `PR414-REVIEW` — `queued`: current corrected-head operation c13a717e;
  prior capture-order P2 remains open until independent verification passes.
- `PR413-REVIEW` — `done`: eeb99712 approved/merged a0ade550; branch/resources closed.
- `PR415-REVIEW` — `done`: d9a05556 approved/merged cbc17f4e; branch/resources closed.
- `PR415-BACKEND-DEPLOY` — `done`: cbc17f4e API/sync live and manually synced.
- `WATCH-PLAN-HORIZONTAL-LEADERS` — `queued`: nonblocking #413 follow-up.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: dark navigation/status text; nonblocking.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired-device validation owner work.
- `NEXT-INTERNAL-IOS-RELEASE` — `evidence-open`: Claude reports build85;
  independently check release/Apple evidence when delivered. No upload this slice.

## Live verification baseline

- Production API aicaddie-release-cbc17f4e-production-20261010, loopback39055;
  public https://caddie.taile36706.ts.net; health exact cbc17f4e revision.
  API garmin-ai-caddie-api:cbc17f4e76f085229c3bdb3c74a5067951b217a6-candidate-20261010,
  ID sha256:337d893f73039d863ada4967012dddbe9d91acda637645fe15ea7779a56b35c5.
  Sync aicaddie-sync:cbc17f4e76f085229c3bdb3c74a5067951b217a6,
  ID sha256:b3e870d74407f0df355087a67ff3dd6718abc62e9f027e503166d20afe77ca64.
  Prebuilt binding/post-switch and installed sync revision gates passed.
- Startup/switch/gates23.617s under shared sync lock. Protected DB/private volume,
  network and ingress retained. Public/loopback health, history and sync status200.
  Three-hole precise prep200/all-ready6.4467s; cached PNG200/0.1024s/678x1060;
  history200/0.0631s. Server probes, not phone loading timings.
  Manual sync17:51:52→17:52:25UTC/33s, exact revision/sync ok/done.
- New-image43 related/deployment tests/0.969s passed. Isolated health exact
  revision, anonymous history401 and empty-data readiness200/degraded as expected.
- Last independently verified TestFlight0.1.0(82): upload37774511661;
  Apple37776197288 VALID/IN_BETA_TESTING; IPA
  f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721.
  Claude-reported83/85 remain unverified here; no new package claim.
- #413 Native38068696361 checkout69cdb102b106f901c7a27abefedc7f6b469495bf
  has exact eeb99712 parent2 and7959d078 parent1; all144 PNGs retained.
  Last live merged-source capture37990736669 iOS772/0, Watch448/0.
  Physical Watch GPS/battery/WCSession timing remains device evidence.
- Prior #404/#406 workload35.4904→22.9303s,237 tests passed/5 skips;
  conditions/scope in2026-10-10-pr404-406-backend-deploy.md. No new phone-speed claim.

## Owned resources and cleanup

- Reserved review snapshot /dev/shm/codex-pr414-c13a717e-20261010, read-only;
  expiry2026-10-11 18:39UTC; evidence operations/pr414-c13a717e-20261010.
  Labelled --rm contracts/visual containers only; no worktree/env/service/tunnel/agent.
  Capacity49GiB disk/5.1GiB available RAM/4GiB shm. No waiter pending.
- #413 evidence /home/jason/garmin-ai-caddie-data/operations/pr413-eeb99712-20261010:
  source/provenance/contracts/Native/all144 PNGs/compare/sheets/review/merge retained.
  Snapshot28,263,275bytes removed after source and file-hash/open-file checks;
  --rm contracts/visual containers absent; production health200/cbc17f4e.
  Exact remote branch head checked before deletion. Seven local controls/sheets
  (202,949bytes) hash-matched to persistent backups and removed; manifest/receipt retained.
  Publication uses a temporary alternate Git index, removed after guarded push.
- #415 review evidence operations/pr415-d9a05556-20261010: source/test/100-run
  regression/review/cleanup retained; snapshot/ext4 dir/containers/local files closed.
- #415 deploy evidence operations/pr415-deploy-cbc17f4e-20261010: source/build/
  image/test/candidate/cutover/live/sync/tool backups/cleanup retained.
  Snapshot28,319,648bytes/candidate/disposable volume/local controls closed.
  f9586f6c stopped/retained rollback; protected user volume/DB/ingress unchanged.
  Earlier b0f64b65/3614bf6f rollbacks retained; deploy-tools pinned cbc17f4e.
- #414 evidence operations/pr414-336c12a3-20261010: source/contracts/Native/
  144 PNGs/review versions/correction/cleanup retained; snapshot28,265,982bytes,
  containers and seven local files closed.
- Historical #404–#412 review/deployment/resource details are dated archives.
  Preserve unrelated dirty ops/pr_feedback_monitor.sh and older .codex-* files.
  Local main's older docs commits remain intact. Remote canonical checkout
  /home/jason/codex-runs/garmin-ai-caddie-claude-takeover-20261005 is shared with
  Claude and may contain in-flight Swift edits. Do not switch/reset/stash or use
  its normal index. Publish scoped evidence via separate index on fresh origin/main.
- gh-feedback timer and blocking-waits/feedback-cursor remain unchanged.

## Next action and stopping

Complete #414 c13a717e source/contracts/Native/provenance/screenshot review;
comment/merge only if clear, close resources and publish real review evidence.
Then resume
ops/wait_for_conclusion.sh --feedback in one same-turn background terminal.
Wait300000ms, read its handle once; repeat until one-line terminal result.
Do not inspect waiter liveness or start a second monitor. Read only the returned
event/log; prioritize #414 corrections and new PRs. Review exact heads/Native
artifacts; approve/merge/delete branches only when clear. No CI-only commits.
Deduplicate38063457169/38063457127/38065042464/38065042410/38065207338/
38072318888/38068696174/38068696361 and already handled #413 reply6099812003.
Ignore Codex comments/commits/CI as actionable events or quiet resets.

Owner resumed after the historical October9 cutoff. Stop after48h without
external PR events and with no open PRs, or an owner stop. Latest independently
handled external event: #414 author correction2026-10-10 17:30:32UTC; earliest
conditional quiet stop2026-10-12 17:30:32UTC. #414 remains open, so do not stop.
Verify both conditions before completing the goal. Keep this ledger≤200 lines.
