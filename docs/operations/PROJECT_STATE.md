# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 23:59 UTC
**Canonical branch:** `main`; product merge `d2b3536b` (#403),
bookkeeping `1ee54a1e`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `done` (owner 23:59 UTC cutoff)

## Current state

# Closing inventory at23:58:55 UTC
Two ready PRs remain open; no new reviews started during closeout:
- #404 now head `1fd0ad4c11669f62b5629912c92e54b5f6ff17c6` (author update),
  not reviewed/tested by Codex. Below evidence/P2 applies to prior e8093d90 only.
- #405 head `3a093c1c1e6d157ab52ae31b866fba643b25e3ed`, branch
  `claude/testflight-preflight-timeout-20261009`; unreviewed, CI not checked.

#404 OPEN/ready, reviewed head `e8093d902b2d60ba805a0aeb1afdc0806166ee76`,
branch `claude/topo-render-processes-20261009`, merge-base `1ee54a1e`.
P2 review **6091300546** posted; do not merge or deploy yet.

P2: _render_cold catches submit-time BrokenProcessPool as generic RuntimeError;
fallback returns but does not discard the singleton pool, so later cold renders
keep falling back to the API process. Handle BrokenProcessPool before RuntimeError,
discard the broken pool, and regress both fallback and fresh-pool acquisition
on the next call. Existing tests cover future.result failure, not submit failure.
Independent probe reproduced discard **0 calls instead of1**.

Verified exact-head backend evidence:
- Related suite **101 tests /2.502 s /OK /3 pre-existing geometry skips**,
  including all7 added pool cases and a real forkserver geometry-unavailable path.
- Independent submit-broken probe **1 test /FAIL**, intentionally exposing P2.
- CI `38005936408` backend/frontend/docker all green; no mobile/ios changes.
- First suite attempt omitted the tracked .env.example in the read-only snapshot.
  Restored the placeholder template and reran successfully; first log retained.
- Author's cold-course 35→15 s measurement was not independently rerun.
  Two render processes require deployment and memory validation; no deploy done.
- Evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr404-e8093d90-20261009`
  (source/tests/probe/attempt1/cleanup/manifest/review originals).

#399–#403 merged; reviewed heads/requests/CI/comments handled and branches deleted.
#403 final PASS6090217699; CI attempt3 and author green reply6090005691 at22:03:20
handled. #404 opened23:44:59, head e8093d90 and P2 comment6091300546 handled.
No duplicate re-review of those heads/events. Historical detail is archived verbatim.

## Unfinished queue

- `PR404-SUBMIT-BROKEN-POOL` — `queued`: author fix, exact-head recovery
  regression/relevant suites and CI on new1fd0ad4c; PASS/merge after P2 is closed.
  Backend deployment is a separate follow-up, with same-revision API/sync builds.
- `PR405-REVIEW` — `queued`: inspect 3a093c1c and required CI; apply the normal
  exact-head review/verification/comment/merge gates. No release claim yet.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 label variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired iPhone/Watch validation remains owner work.

## Live verification baseline

- Latest claimed internal TestFlight **0.1.0 (82)**, upload `37774511661`;
  excludes #395 onward. Apple read-only `37776197288`: VALID /IN_BETA_TESTING.
  IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  `3614bf6f3805479f8d13de65eeec4f0ad7871f22`; production container
  `aicaddie-release-3614bf6f-production-20261008`, loopback39055.
  Protected cutover retained; sync last recorded 502 rounds /501 scorecards /
  501 shots /ok /done. HTTP/2 homeserver 3/3 HTTP200, 1.82–2.57 s;
  not Apple-runner path evidence.
- Latest merged-source Native `37990736669`: iOS772/0, Watch448/0, live production;
  all142 PNGs match the manually reviewed baseline.
  `operations/pr403-fd73dca5-20261009/native-artifacts` retained.
- #403 anchor saves when speculative rows are queued; a failed guess does not
  retry merely by returning home then back. Boundary disclosed. No new release.

## Owned resources

- No active snapshot, worktree, test container, preview/service/tunnel or subagent.
  PR404 snapshot removed (28,063,810 bytes), --rm container absent, production
  running. Source/test/Native originals and cleanup receipts remain.
- A 1,730-byte placeholder /home/jason/.env.example was accidentally extracted
  while restoring the snapshot template. Confirmed new creation/hash; removed
  after open-file check. Repository template/source archive retained. No runtime
  environment file was changed or removed.
- Local controls/manifests/reviews retained as receipts; preserve unrelated dirty
  `ops/pr_feedback_monitor.sh` and historical `.codex-*`.
- Feedback waiter43125 returned PR404 event and ended; no feedback wait pending.
  gh-feedback timer unchanged. No liveness polling, replacement or independent tmux.
  No CI-result-only commits. Comment/commit attribution rules remain in force.

## Next action and stopping

Continuous tracking ended at owner cutoff; closeout committed/pushed separately
from any CI-only bookkeeping. Do not start a replacement waiter or new review.
Future work
requires a new owner instruction; resume PR404 exact current head before merging.

Absolute stop: **2026-10-09 23:59 UTC**; earlier stop requires48h quiet and no
open PRs (not satisfied). Latest handled external event: PR404 opened23:44:59.
Keep ledger ≤200 lines; dated archives are historical, non-authoritative.
