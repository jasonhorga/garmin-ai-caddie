HISTORICAL ARCHIVE — NON-AUTHORITATIVE
Preserved verbatim before recording the remaining multi-hole retry-bound blocker.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 08:22:10 UTC
**Canonical branch:** `main`, product merge `869b73eea1330f31e37cb4944f13204d6e9dd4e3`
**Current slice:** `PR411-FIX-REVIEW` — `in-progress`

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

## Unfinished queue

- `PR411-FIX-REVIEW` — `in-progress`: new head1166c6d9576fa7b92aecbd17ddd86f74dacf1d49,
  author reply6095535098 at08:08:55 UTC. New WatchTopoSender queues cached maps
  after package activation, loads off-main, retries failed transfers; six behavior
  tests include real cached bootstrap against503 and recording enqueue.
  CI38036897627 green; Native38036897631 pending when read. P26095373116
  original triggers are corrected; reviewing multi-hole retry budget/cancellation
  before closing. A depleted hole can be resent by another hole's retry because
  sync checks only sent membership. Run exact-head contracts/Native before
  final disposition; old34c86257 tests/comments already handled.
- `PR408-BACKEND-DEPLOY` — `queued`: only after fix/review/merge. No production
  API restart before10:00 UTC unless decision/prep traffic is quiet30 minutes
  (author's owner-live-round constraint6094461766). Prebuild matching sync image.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: same-turn blocking waits after reviews;
  no CI-only bookkeeping commits, self-event loops or waiter liveness checks.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: dark navigation/status text; nonblocking.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired device validation owner work.
- `NEXT-INTERNAL-IOS-RELEASE` — `evidence-open`: #407 is merged, not in a
  Codex-uploaded TestFlight package; include it in the next requested internal release.

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
  No active snapshot, implementation worktree, test service, tunnel or subagent.
- Stopped rollback `aicaddie-release-3614bf6f-production-20261008` retained.
  No pending Native/feedback wait. gh-feedback timer/cursor unchanged.
  Consumed/deduplicated #404–409 backlog without new comments/tests/CI commits.
  One historical waiter GitHub transport timeout was not a CI failure.
  Last feedback terminal63903 ended with author fix6095535098; no pending wait.
- Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
  Filter/consume credentials on homeserver; never print them during inspection.

## Next action and stopping

Finish #4111166c6d9 review/tests and multi-hole retry budget analysis. Verify
exact-head Native source/artifacts for approval; report reproducible remaining
blocker if confirmed. Close review resources before disposition/next wait.
#408 deployment remains queued for10:00 UTC; a bounded feedback timeout may
wake that scheduled slice. Build matching sync before API cutover. Do not
check waiter liveness, repeatedly query traffic or create CI-only commits.

Prior absolute cutoff is historical; owner explicitly resumed work.
Continuous tracking stops after48h without external PR events and no open PRs,
or a new owner stop instruction. Latest external PR event08:08:55 UTC (#411);
quiet requires48h with no new external events and no open PRs;#411 is open.
Ignore our own
commits/comments/CI as quiet resets. Keep ledger ≤200 lines.
