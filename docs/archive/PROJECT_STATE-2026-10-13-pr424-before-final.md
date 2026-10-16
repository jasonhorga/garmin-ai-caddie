<!-- HISTORICAL ARCHIVE — NON-AUTHORITATIVE -->
# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved verbatim in dated `docs/archive/` files.

**Updated:** 2026-10-13, PR424 table-sync fix audit running
**Canonical baseline:** main `46f9c8ff`; audit #418 head `477eaab6`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress` (#424 exact-head audit)

## Current state

- #404–#416 were reviewed, merged, and (where required) deployed. Do not
  repeat those reviews, tests, comments, or Build 86 upload.
- #417 whole-round Watch audit remains an evidence pass; findings are posted on
  issue #417 and product fixes are Claude/Jason work.
- #418 is still draft/test-only and must not be merged. Exact-head review
  comment [#6131193783](https://github.com/jasonhorga/garmin-ai-caddie/pull/418#issuecomment-6131193783)
  is posted with P1/P2 findings. Required CI
  `38204478707` and Native CI `38204478793` are green. Exact-head Watch
  Runtime Visual Check `38285619153` failed: 41 mm 15/18, 46 mm 16/18,
  49 mm 14/18. Evidence qualifications/viewport corrections are posted in
  [#6133656813](https://github.com/jasonhorga/garmin-ai-caddie/pull/418#issuecomment-6133656813).
- #420 is open and not mergeable: production head `bd2ec304` passes ordinary
  CI `38190513760` and Native CI `38190513917`, but the exact five-tap check
  still records 49 mm `0/5` first manual-shot transitions. Latest evidence
  comment is [#6118215955](https://github.com/jasonhorga/garmin-ai-caddie/issues/417#issuecomment-6118215955).
- #422 proto-* IA harness review is complete on head `9e03df30`; all five
  faces completed 4/4 methods, 270/270 state taps and 50/50 placeholder
  callbacks. Native CI `38251072892` and runtime `38267523735` are green;
  its final comment is `6129026681`. It remains draft and unmerged.
- #423 P2 fixed on `45c08f1f`, reviewed and merged as `46f9c8ff`; branch
  deleted. PASS comment [#6142128127](https://github.com/jasonhorga/garmin-ai-caddie/pull/423#issuecomment-6142128127).
  CI `38365095710` / Native `38365095654` passed (469 Watch unit, 2 UI
  tests). Save failure keeps play/services active; automatic retry each
  minute. Report: `2026-10-13-pr423-review-45c08f1f.md`.
- #421 `62201d90` is our feedback-delivery PR, awaiting Claude review.
- #424 is ready on `9995abfc`; ordinary `38396582897` is green and Native
  `38396582952` is queued. Review production score/root/turn across
  41/42/45/46/49 mm, including Watch/phone second-nine replacement.
  Harness `54a3153e` is pushed on `codex/pr424-production-harness-20261013`;
  runtime `38393954768` covered the prior head; re-dispatch after Native green.
  149 remote Python checks passed again. Claude added table revision relay and
  phone reconciliation in `9995abfc`; retry P2 comment `6145599208` remains
  open pending a success-ack regression.
  Acknowledgement comment `6144032817`; phone-reseed regressions await Native.
  P2 phone-reseed finding `6144359659` is fixed in source at `f3766024`
  (reply `6144399135`); both positive-expectation regressions await execution.
  All 47 Watch/97 phone Native snapshots match the already inspected `6eef9e13`
  set byte-for-byte; current Native checkout is merge candidate `90ee8d53`. Report:
  `2026-10-13-pr424-review-6eef9e13.md`. Final review/runtime still pending.
  The table-sync P2 is addressed in source (comment `6145204555` and Claude
  reply `614?`), but failed phone reconciliation can be suppressed by the
  in-memory applied-revision guard (comment `6145599208`). No paired-device
  claim; exact-head Native/runtime evidence is pending.

## Unfinished queue

- `PR-418-AUDIT-477EAAB6` — `evidence-open`: hold draft until the author
  fixes the P1/P2 findings and reruns the exact head.
- `PR-420-W01-49MM` — `evidence-open`: stale-fix wiring is covered, but the
  49 mm production rail still fails the required five real first taps.
- `WATCH-IDLE-PHYSICAL-ACCEPTANCE` — `evidence-open`: owner verifies #423
  background minute loop/workout/GPS shutdown and accidental relaunch.
- `PR-421-FEEDBACK-DELIVERY` — `evidence-open`: awaiting external review.
- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: process external events and
  retain one same-turn waiter handle; ignore own CI/comments and reviewed heads.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: nonblocking #416 variation.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark status/navigation text.
- `OWNER-DEVICE-BUILD86` — `evidence-open`: paired-device validation remains
  owner work; package evidence is not a physical-install claim.

## Exact-head audit evidence

- Run: [38285619153](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38285619153);
  artifacts:
  `/home/jason/garmin-ai-caddie-data/operations/pr418-477eaab6-20261012/artifacts`.
- P1 candidate: on 49 mm, `0001–0005-first-try--manual--*.json` all report
  `recordSucceeded=false`, with `afterRecord shots=0;pending=false` for
  centre and 8 pt off-centre taps. The direct `shots--01-manual-button-
  no-transition.json` capture agrees. The injected recovery candidate is
  explicitly not success evidence.
- P2: 41 mm scorecard row 4 is not reached by the bounded harness in
  `phone-nine--04-scorecard-FAILURE.json` and `watch-turn--04-scorecard-
  FAILURE.json`; row frames are 26.5 pt high and row 4 starts at y=238 pt
  on the 176×215 pt window. This is row-reachability evidence, not a claim
  that every user's scroll is permanently blocked.
- P2: 46/49 mm `watch-turn--11-same-half-choice-FAILURE.json` leaves
  `watch-turn-continue` at y=268.5 pt, below the 248/251 pt windows. The
  bounded scroll does not make it hittable; `WatchTurnView` does contain a
  ScrollView, so this is not evidence of a permanent dead end.
- P2: 49 mm `phone-eighteen--09-score-missing-control-FAILURE.json` stops at
  `hole=9; scored=8; screen=scorecard` before `audit-restore`; the evidence
  is ninth-hole scorecard/editor reachability, not a proven resume regression.
- 41/46 mm first-try shot evidence is 5/5 record+undo. Simulator data does
  not prove a physical Crown, real GPS, WCSession delivery, OLED luminance,
  or wrist motion. Physical-scale sheets are retained for inspection.

## Live verification baselines

- Production API/sync: `cbc17f4e76f085229c3bdb3c74a5067951b217a6`; health,
  history, sync, precise prep and topo PNG gates passed; manual sync reported
  `sync ok` and `done`.
- #404/#406 deployment evidence: 237 related tests; nine-hole workload
  35.49 s → 22.93 s; two render workers observed.
- Internal TestFlight 0.1.0 (86) remains Apple-checked
  `VALID/IN_BETA_TESTING`; no new upload is authorized by this audit.

## Owned resources and cleanup

- #424 manifest: `.codex-pr424-6eef9e13-review-manifest.md`.
  Sole snapshot moved to `/dev/shm/garmin-ai-caddie-pr424-f3766024-20261013`,
  expires 2026-10-14 10:54 UTC; persistent operations evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr424-6eef9e13-20261013`.
  Native artifacts are retained there; contract container is removed.
  Local visual copy: `/tmp/codex-pr424-native-20261013.2B2y04` (same expiry).
  Agent `/root/wait_release_38083089271` owns the same-turn wait for
  `38393954768` and then `38396582952`. Feedback waiter terminal `3642` is retained in this turn;
  observe only after five-minute sleeps. No additional service.

- Review worktree:
  `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011`,
  Codex-owned, expires 2026-10-18 08:30 UTC.
- Remote artifact evidence is persistent at
  `/home/jason/garmin-ai-caddie-data/operations/pr418-477eaab6-20261012`;
  no new container, service, tunnel, dependency environment, or simulator
  was created in this slice. Existing audit artifacts remain under their
  retention policy.
- Local visual samples in `/tmp/codex-pr418-visual` were removed 2026-10-12
  after the review comment; do not delete the remote artifact set.
- Temporary waiter source `/home/jason/codex-runs/garmin-ai-caddie-wait-20261012`
  is Codex-owned for this same-turn blocking wait; its `ops/wait_for_conclusion.sh`
  includes the Codex issue/review feedback-attribution filter, including
  `plain_issue_comment` for #417. Remote targeted tests: 20/20 passed, zero skips.
  Temporary correction body `/tmp/codex-pr418-correction-body-20261012.md` was
  removed after posting.
  Remove the waiter source directory when waiting ends.
- #423 artifacts/logs are retained in operations `pr423-85ae2914-20261013`
  and `pr423-45c08f1f-20261013`; all 47 revised Watch snapshots match the
  prior review. Both /dev/shm PR423 snapshots and local scratch are removed;
  the new evidence directory retains the manifest and cleanup result.
- Untracked `.codex-*` files in the worktree are historical session evidence;
  do not delete or stage them.

## Next action and stop conditions

1. After Native CI `38396582952` is green, re-dispatch the five-face runtime
   against exact `9995abfc` using harness `54a3153e`; collect receipts. Earlier
   `38388376104` failed harness compilation and `38390603419` built but stopped
   at missing `AUDIT_FACE`; neither executed product control trials.
   Finish #424 exact-head code review and five-face runtime acceptance;
   post P1/P2/evidence limits on #424 and #417. Merge only if unblocked.
2. Launch/restart one blocking `ops/wait_for_conclusion.sh --feedback` waiter
   in the same control turn after each consumed event.
   Observe only with `sleep 300000` followed by one `write_stdin`; its
   one-line result is the only wake-up signal.
3. Process each external PR event once, ignoring Codex-owned CI and feedback
   events; Claude/unknown/unmarked events remain actionable.

Stop only after 48 hours with no external PR events and no open PRs, or an
owner stop instruction (latest continuous-goal instruction supersedes the
earlier dated cutoff). Drafts count as open. Last handled external request:
#424 fix comment `6144399135`, 2026-10-13 11:20:38 UTC. #423 new head/CI events
are reviewed receipts and must not trigger another review. Own comments/CI
do not restart the quiet interval. Every Codex commit ends with
`Generated-by: Codex`; every GitHub comment/review ends with
`_Generated by Codex_`.
Keep this file at 200 lines or fewer and archive completed detail by date
without deleting information.
