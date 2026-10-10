HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 UTC
**Canonical branch:** `main`, `b0f64b65fe51af6665e531010d272fc101d203ac`
**Current slice:** `BACKEND-404-406-DEPLOY` — `in-progress`

## Current state

Owner resumed review after the previous 2026-10-09 23:59 UTC cutoff.
#404/#405/#406 were reviewed at their exact heads, PASS comments posted,
merged and source branches deleted. Approval reviews cannot be submitted
because both agents use the PR author's GitHub account; PASS is in comments.

- #404 head `1fd0ad4c11669f62b5629912c92e54b5f6ff17c6`;
  P2 submit-time broken-pool fix closed, 102 tests /2.287 s /OK /3 skips.
  CI `38006952014` green; PASS comment `6094057484`;
  merge `398c4cc1a91213fcf2b9915a81e628fdb849fec7`.
- #406 head `0e17d9ae05ebed1d02983361fc7f489a3a0ccbc1`;
  profile cache/membership/prep suites 132 tests /0.776 s /OK /2 skips.
  CI `38007960730` green; PASS comment `6094058361`;
  merge `6969e87fd687ca5326681d74ea6f61eaca0daa1a`.
- #405 head `3a093c1c1e6d157ab52ae31b866fba643b25e3ed`;
  3 release-tooling contracts /0.133 s /OK. Full workflow suite:
  38 passed, 3 existing environment errors (runtime image has no git).
  CI `38005987086` green; PASS comment `6094057971`;
  merge `b0f64b65fe51af6665e531010d272fc101d203ac`.
- Delay explanations `6093885051/6093885466/6093885977` posted as requested.
  Those events/heads are handled; do not duplicate reviews.
- Candidate startup/health and authenticated readiness responded on 39088
  using a disposable private volume; readiness degraded as expected for
  empty fixture data. Candidate container/volume removed.
- Production switched to b0f64b65 on 39055; health exact revision confirmed.
  Prior 3614bf6f container stopped and retained for rollback.
  Sync image build/deployment gate terminal **30505** remains pending.
  Consume its final result; do not start a duplicate build.
- Deployment inspection accidentally printed credential fields; future
  diagnostics must filter/consume credentials remotely without output.

## Unfinished queue

- `BACKEND-404-406-DEPLOY`: finish same-revision sync gate, verify live
  history/prep/topo, two-worker memory and timing, close temporary resources.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume same-turn blocking feedback
  waits after deployment closeout. Do not create CI-only bookkeeping commits.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: dark navigation/status text; nonblocking.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired device validation owner work.

## Live verification baseline

- Last independently verified internal TestFlight **0.1.0 (82)**,
  upload `37774511661`; Apple read-only `37776197288` VALID/IN_BETA_TESTING.
  IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
  #405 author reports build83 upload `38004360047`; not independently checked.
  This review/deploy batch has not uploaded a new iOS build.
- API `https://caddie.taile36706.ts.net`, loopback39055:
  `aicaddie-release-b0f64b65-production-20261010`, exact b0f64b65 revision.
  API image `garmin-ai-caddie-api:b0f64b65fe51af6665e531010d272fc101d203ac-candidate-20261010`,
  ID `sha256:0d1f306ae1316120764205b74963b65118934cc0291cd3a158d03d2f42154d20`.
  Sync matching image pending; no post-deploy performance claim yet.
- Latest merged-source Native `37990736669`: iOS772/0, Watch448/0,
  142 PNGs match reviewed baseline; no mobile source change in this batch.
- Protected production private volume, PostgreSQL and ingress unchanged.

## Owned resources

- Deployment evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr404-406-deploy-20261010`.
  Resource manifest recorded; temporary source expires Oct11 05:17 UTC:
  `/home/jason/codex-runs/garmin-ai-caddie-b0f64b65fe51af6665e531010d272fc101d203ac-20261010`.
- Review copies awaiting exact allow-list cleanup:
  `/dev/shm/codex-garmin-review-20261010`,
  `/dev/shm/codex-garmin-review-20261010-rw`; no active test container.
  Dependencies reused from API image; no private venv installed.
- Candidate `aicaddie-release-b0f64b65-candidate-20261010` and volume
  `codex-pr404-406-private-20261010` removed after checks; production retained.
- Stopped rollback `aicaddie-release-3614bf6f-production-20261008` retained.
  No subagent, browser, preview, tunnel or feedback wait pending.
- Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`.
  gh-feedback timer/cursor unchanged. Comment/commit attribution applies.

## Next action and stopping

Read terminal30505's sync/deployment gate conclusion, then verify deployed
render/profile paths with bounded isolated cache tests and live read-only probes.
Retain detailed evidence remotely, clean only session-owned allow-list targets,
update this ledger together with real review/deploy work and push.

Prior absolute cutoff is historical; owner has explicitly resumed work.
Continuous tracking stops after48h without external PR events and no open PRs,
or a new owner stop instruction. Ignore our own commits/comments/CI as quiet resets.
Keep ledger ≤200 lines. Archives are historical and non-authoritative.
