# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved in dated `docs/archive/` files.

**Updated:** 2026-10-16 06:13 UTC; #430 reviewed, three P2 findings posted
**Canonical baseline:** main `19691617`; #430 review head `36449d4048dfa6385b8fc8db42809dd4dd06ab1d`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and unfinished work

- `PR430-REVIEW` — `evidence-open`: draft reviewed at exact head `36449d40`.
  Comment: https://github.com/jasonhorga/garmin-ai-caddie/pull/430#issuecomment-6209326656.
  Three P2s: preserve exact-head Native CI/artifact acceptance; require trusted
  owner-channel TestFlight authority; describe player/Apple/owner credential
  boundaries correctly. Required CI `38859007391` is green; diff check passed.
  All four files read and compared read-only with current agenthub code and
  cutover playbook. Release-failure wake wording remains provisional.
  **Review only; do not merge.** Merge belongs to cutover step 5 after freeze
  and explicit handoff of unresolved evidence. Current main policy remains active.
- `BACKEND-READINESS-428` — `done`: revision `e1243ba9` deployed as
  `aicaddie-release-e1243ba9-production-20261015`; authenticated readiness
  reports `runtimeStatus=ready`, `mobile_events=ready`, and
  `mobile_package=ready`. Matching sync image ran; log ended `sync ok`,
  `done`. Issue comment:
  https://github.com/jasonhorga/garmin-ai-caddie/issues/428#issuecomment-6194494187
- `TESTFLIGHT-89` — `done`: CD run
  https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38745733734
  completed without degraded-readiness opt-in. Uploaded `0.1.0 (89)`;
  provenance/backend revision match; IPA SHA-256
  `5027d1e0c8063ef69a4e84be92300b9a6b64491edd4e2570c6f0417de8b1fb59`.
  IPA contains iOS and WatchKit targets, both build 89.
- `APPLE-READONLY-89` — `done`: check
  https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38750039805
  reports build `VALID`, `internalState=IN_BETA_TESTING`,
  `usesNonExemptEncryption=false`; build 89 is in the existing internal
  group. Apple processed `com.ai-caddie.mobile` and
  `com.ai-caddie.mobile.watchkitapp`.
- #425 and #427 are merged/deployed. #417 remains an evidence issue;
  #418 is draft/evidence-open; #420 awaits the requested 49 mm transitions;
  #421 is done: exact head `62201d90` passed 19/19 provenance tests,
  `bash -n`, and `git diff --check`; PASS comment
  https://github.com/jasonhorga/garmin-ai-caddie/pull/421#issuecomment-6200552328;
  merge commit is `d9de84ad` and its branch is deleted. #422 is draft/test-only
  and must not merge.
- `MAIN-PROVENANCE-FIX` — `done`: `cf535491` changed the legacy feedback
  filter to require a final standalone attribution line and restored detailed
  self-receipt logs. The exact main snapshot passed 20/20 provenance tests;
  CI run https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38813163550
  passed backend, frontend and docker.
- `PR429-REVIEW` — `done`: rebased exact head `2b39d63a` passed 33/33
  deployment harness tests on homeserver and required CI `38813956158`.
  PASS comment (no P1/P2):
  https://github.com/jasonhorga/garmin-ai-caddie/pull/429#issuecomment-6203460746.
  Merged as `ec8cddfe`; remote branch deleted. Real sandbox deployment and
  agenthub cutover remain future operations; production is unchanged.
  Continue processing new PR heads/comments once their required CI is terminal.
- The owner target remains seconds for nearby maps and under 30 s for an unseen
  course. Keep Watch cold-start and caddie correctness evidence explicit.

## Live verification baselines

- Production: revision
  `e1243ba9c516f2983a56aab1cdbd032d4595ab9c`, container
  `aicaddie-release-e1243ba9-production-20261015`, public
  `https://caddie.taile36706.ts.net`; matching sync image exists.
- Release evidence: `/home/jason/garmin-ai-caddie-data/operations/release-readiness-428-20261015`.
  Apple waiter log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-38750039805-20261015T142108Z-3379555.log`.
- Existing cold-start baseline: nearby 28242 public drawable vector package
  `3.241 s`; cold 28214 first drawable package `6.453 s` through the
  homeserver Funnel. These are server/Funnel timings, not wrist/Tokyo/Austria
  timings.
- Build 87 remains in the internal group as historical baseline; Build 89 is
  the current release candidate verified above.
- #421 exact-head test snapshot was `/dev/shm/codex-garmin-ai-caddie-pr421-62201d90`;
  it was removed immediately after the 19-test pass. No review snapshot remains.
- Main-fix verification snapshot `/dev/shm/codex-main-waitfix-20261015` was
  removed after the 20-test pass.
- #429 test command: `python3 -m unittest -v tests.test_agenthub_deploy`
  in author's clean exact-head checkout
  `/home/jason/codex-runs/garmin-ai-caddie-claude-deploy-20261015`;
  33 tests in 87.490 s, exit 0. No dependency installation or real Docker
  deployment; test temporary directories cleaned by unittest.

## Owned resources and cleanup

- The first isolated build process and image
  `garmin-ai-caddie-readiness-428:20261015` were absent at cleanup time.
  Exact context `/home/jason/codex-runs/codex-readiness-428-20261015`
  (35 MB before cleanup) was removed using an exact allow-list:
  `/home/jason/garmin-ai-caddie-data/operations/cleanup-codex-readiness-428-20261015.txt`.
  The temporary cleanup container was removed; shared BuildKit cache and
  production rollback container were left untouched.
- Release and Apple waiters are terminal; no temporary build or review
  container remains. Persistent release evidence above is retained.
- #430 review created no worktree, service or container. Public review text:
  `/home/jason/garmin-ai-caddie-data/operations/pr430-review-20261016/review-36449d40.md`.
  Remote `/tmp/codex-pr429-review.LzZ8jB` (601 bytes, failed formal approval's
  public body) awaits exact allow-list cleanup; no credentials in that file.
- Feedback terminal 4865 ended normally on #430's `pr_opened` event. That
  event and review request are handled once; own signed review needs no reply.
  Resume the existing cursor; do not reset it or start a second monitor.
- Existing review worktree
  `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011`
  expires 2026-10-18 08:30 UTC. Historical `.codex-*` evidence is retained.
  Do not delete it without an explicit allow-list.

## Next action and stop conditions

1. Await #430 revisions through the same-turn feedback waiter; re-review a
   changed head once. Do not merge #430 before the agreed cutover step 5.
   Continue other external events; do not poll CI, processes or monitor state,
   and ignore Codex-only docs/state CI and signed self-receipts.
2. For a new code PR: review the exact head, run required remote tests, inspect
   Native artifacts when applicable, and comment with P1/P2/non-blocking evidence.
3. Owner stop condition: stop at the explicit owner stop, or after 48 hours with
   no new external PR event and no open PR. The previously recorded 2026-10-09
   wall-clock cutoff is historical/elapsed; newer owner requests keep this
   active slice authorized.
4. Every Codex GitHub comment/review ends `_Generated by Codex_`; every Codex
   commit ends `Generated-by: Codex`.
