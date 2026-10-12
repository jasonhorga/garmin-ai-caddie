# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved verbatim in dated `docs/archive/` files.

**Updated:** 2026-10-12 19:56 UTC
**Canonical baseline:** PR #418 exact head `477eaab6`; main baseline `0882c41c`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

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
  49 mm 14/18.
- #422 proto-* IA harness review is complete on head `9e03df30`; all five
  faces completed 4/4 methods, 270/270 state taps and 50/50 placeholder
  callbacks. It remains draft and unmerged; final comment is
  `6129026681`.

## Unfinished queue

- `PR-418-AUDIT-477EAAB6` — `evidence-open`: hold draft until the author
  fixes the P1/P2 findings and reruns the exact head.
- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: one blocking waiter is active;
  ignore Codex-owned docs/state CI.
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
- P2: 41 mm scorecard row 4 is unreachable in
  `phone-nine--04-scorecard-FAILURE.json` and `watch-turn--04-scorecard-
  FAILURE.json`; row frames are 26.5 pt high and row 4 starts at y=238 pt
  on a 251 pt viewport.
- P2: 46/49 mm `watch-turn--11-same-half-choice-FAILURE.json` leaves
  `watch-turn-continue` at y=268.5 pt, outside the 251 pt viewport; the
  screen also shows the offline whole-course warning.
- P2: 49 mm `phone-eighteen--09-score-missing-control-FAILURE.json` has no
  controls and test 07 fails to find `watch-score-save`. Test 12's 49 mm
  missing captures are a consequence of the same manual-shot dead end.
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
  is Codex-owned for this same-turn blocking wait; remove it when waiting ends.
- Untracked `.codex-*` files in the worktree are historical session evidence;
  do not delete or stage them.

## Next action and stop conditions

1. Launch/restart one blocking `ops/wait_for_conclusion.sh --feedback` waiter
   in the same control turn after each consumed event.
   Observe only with `sleep 300000` followed by one `write_stdin`; its
   one-line result is the only wake-up signal.
2. Process each external PR event once, ignoring Codex-owned docs/state CI.

Owner's latest explicit review requests keep this queue active; otherwise
stop when the owner stop condition is met. Every Codex commit ends with
`Generated-by: Codex`; every GitHub comment/review ends with
`_Generated by Codex_`.
Keep this file at 200 lines or fewer and archive completed detail by date
without deleting information.
