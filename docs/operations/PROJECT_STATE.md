# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 06:15 UTC
**Canonical branch:** `main`, product merge `45ab789d3e2ebd6dd77afff0873c0e19ccc761ac`
**Current slice:** `PR408-REVIEW` — `in-progress`

## Current state

Owner resumed review after the historical 2026-10-09 23:59 UTC cutoff.
#404/#405/#406 reviews/merges/deployment and #407 review/merge are complete.
Do not repeat their heads or handled PASS/deployment comments.
#407 head936987631dd6498e758d2ba68ce47b4f34873080: PASS6094541989,
merge45ab789d, source branch deleted. Contracts126/126; Native38028436609
iOS776/0, Watch448/0; all four new regressions passed. Native merge4e6134e5
contains the exact head. All142 PNGs match #403's reviewed baseline; relevant
phone/Watch plan/zoom/hazard/flag/off-course images inspected. No new release.

Two new ready PRs:
- #408 head `90f8e7f29aecec3afadf0a11b3e724518b96e291`,
  branch `claude/plays-like-approach-20261010`: green-approach club selection
  using plays-like distance. Unreviewed; inspect CI/files before verification.
- #409 head `a435a5c9ac691f00f67b3a83759df548a5840edd`,
  branch `claude/mixed-venue-loops-20261010`: offer an 18-hole course alongside
  a venue's nines. Unreviewed; Native and screenshot gate required if mobile changes.

## Unfinished queue

- `PR408-REVIEW` — `in-progress`: exact-head code/tests/required CI; comment
  P1/P2/nonblocking or PASS, merge/delete only when clear; deploy backend if needed.
- `PR409-REVIEW` — `queued`: exact-head gates, Native artifacts/design inspection.
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
- Latest PR-head Native38028436609: iOS776/0, Watch448/0,142 baseline PNG matches.
  Last merged-source live capture37990736669: iOS772/0, Watch448/0.

## Owned resources

- Evidence: /home/jason/garmin-ai-caddie-data/operations/pr404-406-deploy-20261010
  and /home/jason/garmin-ai-caddie-data/operations/pr407-93698763-20261010.
  Original source archives/tests/Native PNGs/reviews/cleanup receipts retained.
- #407 snapshot removed (28,089,999 bytes); --rm contract/inspection containers
  absent. Local controls/contact sheets backed up/hash-matched and removed.
  No active snapshot, implementation worktree, test service, tunnel or subagent.
- Stopped rollback `aicaddie-release-3614bf6f-production-20261008` retained.
  No feedback/CI wait pending; gh-feedback timer and cursor unchanged.
- Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
  Filter/consume credentials on homeserver; never print them during inspection.

## Next action and stopping

Commit/push #407's completed review/cleanup and dated archive together, then
inspect #408 at its exact head. #409 follows. Use the existing blocking waiter
for any pending CI; inspect required iOS/Watch screenshots before approval.
After closure retain one feedback terminal and wait in the same control turn.

Prior absolute cutoff is historical; owner explicitly resumed work.
Continuous tracking stops after48h without external PR events and no open PRs,
or a new owner stop instruction. Latest external PR update06:11:00 UTC (#409);
quiet condition is not satisfied while #408/#409 are open. Ignore our own
commits/comments/CI as quiet resets. Keep ledger ≤200 lines.
