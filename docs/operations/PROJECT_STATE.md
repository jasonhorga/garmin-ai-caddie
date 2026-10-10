# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 11:40 UTC
**Canonical branch:** `main`, product merge `d3f05e13b884773041e4ad22c3f0343e9bcd3201`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state

Owner resumed review after the historical 2026-10-09 23:59 UTC cutoff.
#404/#405/#406 reviews/merges/deployment and #407 review/merge are complete.
Do not repeat their heads or handled PASS/deployment comments.
#407 head936987631dd6498e758d2ba68ce47b4f34873080: PASS6094541989,
merge45ab789d, source branch deleted. Contracts126/126; Native38028436609
iOS776/0, Watch448/0; all four new regressions passed. Native merge4e6134e5
contains the exact head. All142 PNGs match #403's reviewed baseline; relevant
phone/Watch plan/zoom/hazard/flag/off-course images inspected. No new release.

#408 corrected head e188dfffe5c9d1d23b6fc402a8a8e6420cad2076 approved in
6094808089, merged80973ed9 at06:48:32 UTC; source branch deleted. P26094615864
closed: raw<3m elevation noise is filtered before club selection. Independent
related prep170/OK/2 existing skips, elevation10/OK, original362m probe1/OK
(both flat/noisy Driver→3W). CI38030779827 green. No production change yet.

#409 head b040b2eeb2774cb22e07cd7a7c07768af8f6e620 approved6094888102,
merged ebd09a0e at06:58:38 UTC; source branch deleted. P26094741902 closed.
Independent contracts126/OK; CI38031964101 green; Native38031964045 passed
iOS778/0, Watch448/0, exact head is parent2 of checked-out331bdb4c. All144
PNGs downloaded:142 unchanged,2 added. Inspected both mixed-venue selected9/
selected18 captures and ABC baseline: names/halves/tees/actions fit;18-hole
yardage is not shown as nine-hole total. Ready for author's planned internal
release including#407/#409; no Codex TestFlight upload in this review batch.

#410 head795dd9595343ea4853296ee9d2dcd99c8881fa8f approved6095236472,
merged869b73ee at07:43:54 UTC; source branch deleted. Contracts126/OK;
CI38034191333 green, Native38034191294 iOS778/0, Watch449/0. New GPS callback
filter regression and fresh/accurate-fix rejection both passed. Native merge
2fe27955 parent2 is exact head; all144 PNGs match #409 baseline. Acquiring,
distance-hero and always-on captures inspected. Hardware stationary fix cadence/
battery remains device evidence. Separate topo delivery/layout follow-ups pending.

#412 head95801f4111f0ae3fa12fd619e91e3d8a60978e5e reviewed in comment
6096711733 and merged d3f05e13 at10:49:06 UTC; source branch deleted. Native
38039403230 exact head passed iOS and Watch. Downloaded 144 design/watch PNGs;
all hashes match #411 baseline. No P1/P2; physical battery-round measurement
remains evidence-open. The branch was two commits behind main but current-main
comparison contained only its three intended Watch files.

## Unfinished queue

- #411 head24444e020d32b791cc5182dd88b0f5fa233da541 approved6095892808,
  merged7439b592 at08:59:59 UTC; source branch deleted. P26095373116 closed.
  Explicit exhausted set and two-hole regression prevent a different retry timer
  reviving an exhausted hole. Contracts126/OK; CI38037976758 green; Native
  38037976761 exact head parent2 of8a0aab2e, Watch449/0 and cached-resume/retry
  tests passed; all144 PNGs identical to PR409 baseline. No visual regression;
  physical WCSession timing remains next-device evidence.
- `PR408-BACKEND-DEPLOY` — `done`: combined #404/#406 backend deployment and
  matching sync image are verified in the live baseline and report below.
- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: same-turn blocking waits after reviews;
  no CI-only bookkeeping commits, self-event loops or waiter liveness checks.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: dark navigation/status text; nonblocking.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired device validation owner work.
- `NEXT-INTERNAL-IOS-RELEASE` — `evidence-open`: #407 is merged, not in a
  Codex-uploaded TestFlight package; include it in the next requested internal release.
- `WATCH-BATTERY-RESEARCH` — `done`: public-source report and short #412
  comment6097100629 posted. Report is retained at
  `/home/jason/garmin-ai-caddie-data/operations/watch-battery-research-20261010/report.md`.

## Live verification baseline

- Last independently verified internal TestFlight **0.1.0 (82)**,
  upload37774511661; Apple read-only37776197288 VALID/IN_BETA_TESTING.
  IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
  #405 author reports build83 upload38004360047; not independently checked.
  This review/deploy batch has not uploaded iOS.
- API `https://caddie.taile36706.ts.net`, loopback39055:
  `aicaddie-release-b0f64b65-production-20261010`, exact b0f64b65 revision.
  Matching API/sync images and deployment/installed sync revision gates passed.
  Manual sync ended05:48:19 UTC with sync ok/done, 502 summaries/501 scorecards.
  Health/public health/history/sync/prep/topo200; protected volume/DB/ingress retained.
- Isolated four-CPU benchmark: nine topo +three prep batches35.4904→22.9303 s;
  nine PNG hashes match, two actual workers. Server-only, not phone load time.
  Combined deployed-source suites237 tests /4.107 s /OK /5 existing skips.
  Full evidence: [backend deployment report](2026-10-10-pr404-406-backend-deploy.md).
- Latest PR-head Native38034191294: iOS778/0, Watch449/0,144 baseline PNG matches.
  Last merged-source live capture37990736669: iOS772/0, Watch448/0.

## Owned resources

- Evidence: /home/jason/garmin-ai-caddie-data/operations/pr404-406-deploy-20261010
  and /home/jason/garmin-ai-caddie-data/operations/pr407-93698763-20261010.
  Original source archives/tests/Native PNGs/reviews/cleanup receipts retained.
- #407 snapshot removed (28,089,999 bytes); --rm contract/inspection containers
  absent. Local controls/contact sheets backed up/hash-matched and removed.
- #408 evidence: /home/jason/garmin-ai-caddie-data/operations/pr408-90f8e7f2-20261010.
  Snapshot removed (28,088,036 bytes), three --rm containers absent; local helpers
  backed up/hash-matched and removed. Source/tests/failing probe/review retained.
  Correction evidence: /home/jason/garmin-ai-caddie-data/operations/pr408-e188dfff-20261010.
  Snapshot/three containers closed; source/probe/test/review/cleanup retained.
  Six local correction controls hash-matched remote originals and were removed.
  #409 snapshot removed (28,084,003 bytes); --rm contracts container absent,
  local controls/screenshot backed up/hash-matched and removed. Evidence:
  /home/jason/garmin-ai-caddie-data/operations/pr409-a435a5c9-20261010.
  #409 correction evidence: /home/jason/garmin-ai-caddie-data/operations/pr409-b040b2ee-20261010.
  Snapshot removed (28,086,784 bytes), --rm contracts container absent. Native
  waiter6350/artifact terminal1456 ended; all evidence retained. Six local
  helpers+three screenshots hash-matched persistent originals and removed.
  #410 evidence: /home/jason/garmin-ai-caddie-data/operations/pr410-795dd959-20261010.
  Exact source, Native provenance/144 PNGs/logs/review/cleanup retained. Snapshot
  removed and --rm contracts container absent. Native52143/artifact30546 closed;
  six local helpers+three PNGs (62,200 bytes) hash-matched originals and removed.
  #411 evidence: /home/jason/garmin-ai-caddie-data/operations/pr411-34c86257-20261010.
  Source/contracts/P2 comment/cleanup retained; snapshot and --rm contract
  container closed. Four local controls (6,806 bytes) hash-matched originals
  and removed; no Native wait/artifact/local image copy was started for this head.
  #411 final evidence: /home/jason/garmin-ai-caddie-data/operations/pr411-24444e02-20261010.
  Source/contracts/retry P2/cleanup retained; snapshot/--rm container closed.
  Six local controls(8713 bytes) hash-matched originals and removed; Native
  waiter/artifact terminals completed; no local images/service remained.
  #412 evidence: /home/jason/garmin-ai-caddie-data/operations/pr412-95801f41-20261010.
  Native artifacts downloaded; 144 PNG hashes compared to #411 and retained.
  Battery research report: /home/jason/garmin-ai-caddie-data/operations/watch-battery-research-20261010/report.md;
  repository copy is docs/operations/2026-10-10-watch-battery-research.md.
  No active snapshot, implementation worktree, test service, tunnel or subagent.
- Stopped rollback `aicaddie-release-3614bf6f-production-20261008` retained.
  No pending Native/feedback wait. gh-feedback timer/cursor unchanged.
  Consumed/deduplicated #404–412 backlog without CI-only bookkeeping commits.
  One historical waiter GitHub transport timeout was not a CI failure.
  Last feedback at08:43:23 UTC delivered#411 fix; final approval/merge handled.
- Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
  Filter/consume credentials on homeserver; never print them during inspection.

## Next action and stopping

Retain one same-turn --feedback terminal (sleep300000ms→read once). Deduplicate
handled#404–412; process genuine new PR/comment or an explicitly requested
internal release.
Physical Watch transfer timing is release evidence, not a merge blocker. No
CI-only bookkeeping commits.

Prior absolute cutoff is historical; owner explicitly resumed work.
Continuous tracking stops after48h without external PR events and no open PRs,
or a new owner stop instruction. Latest external PR event09:14:21 UTC (the
#412 research request); quiet requires48h with no new external events and no
open PRs (target 2026-10-12 09:14:21 UTC). Codex comments/commits/CI do not
reset quiet.
Ignore our own
commits/comments/CI as quiet resets. Keep ledger ≤200 lines.
