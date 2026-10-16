> HISTORICAL ARCHIVE — NON-AUTHORITATIVE
> Verbatim ledger before the owner-requested Build 87 release.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved verbatim in dated `docs/archive/` files.

**Updated:** 2026-10-13, PR424 merged after exact-head P2 recheck
**Canonical baseline:** main merge `6bb684fa`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress` (post-#424)

## Current state

- #404–#416 reviewed and merged; #417 remains an evidence issue with findings
  already posted. #418 remains draft/evidence-open. #420 remains
  evidence-open for the 49 mm first-tap rail. #421 awaits external review.
- #422 is draft/test-only and must not be merged. Its exact-head review is
  complete; do not treat prototype callbacks as production evidence.
- #423 was reviewed, fixed, merged as `46f9c8ff`, and its branch was deleted.
- #424 passed the P2 recheck and was merged as `6bb684fa`; implementation
  branch `claude/watch-production-ia-20261013` and the temporary audit branch
  were deleted. Pass comment:
  https://github.com/jasonhorga/garmin-ai-caddie/pull/424#issuecomment-6154831834.
- The merged #424 source covers revision acknowledgement, phone tee-landing
  fallback, inline 开球左/中/右, and the 45 mm score-row hit-target fix.
  No unresolved P1/P2 finding remains for #424.

## Unfinished queue

- `PR-418-AUDIT-477EAAB6` — `evidence-open`: hold the draft for the
  author's P1/P2 fixes and exact-head rerun.
- `PR-420-W01-49MM` — `evidence-open`: 49 mm first manual-shot rail still
  needs five successful first-try transitions.
- `WATCH-IDLE-PHYSICAL-ACCEPTANCE` — `evidence-open`: owner device
  validation remains required for #423.
- `PR-421-FEEDBACK-DELIVERY` — `evidence-open`: awaiting external review.
- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: process external events once,
  ignore Codex-owned CI/comments, and retain one same-turn feedback waiter.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` and `IOS-STATUS-CONTRAST` —
  `queued`; `OWNER-DEVICE-BUILD86` — `evidence-open`.

## Exact-head #424 evidence

- Fixed head `5ac993ef8970db809390d19e7d27ba92c8d368b0`: ordinary CI
  `38446895152` and Native CI `38446895372` passed.
- Native artifacts `11839047414` (97 design/iPhone snapshots),
  `11838888102` (47 Watch snapshots), and `11839187866` (build evidence)
  were downloaded and inspected. Only the score-row pixels changed as
  expected; no clock, safe-area, crop, or layout regression appeared.
- Test-only harness `799762d0`, runtime `38453004091`, evidence
  `/home/jason/garmin-ai-caddie-data/operations/pr424-5ac993ef-native-20261013`.
  Fresh-launch production taps: 41/42/45/46/49 mm each 390/390.
- The fixed 45 mm `fairway-open` first tap has AX frame
  `[10,174,86,37]`, interactive bottom `211`, and succeeds on attempt 1.
  First-try manual record and undo are 10/10 on every face; Watch→phone
  second-nine sync is 2/2. Native logs report the complete audit green.
- Simulator evidence still does not establish physical Crown, GPS, WCSession
  transport, OLED brightness, or wrist-motion behavior.

## Live verification baselines

- Production API/sync baseline: `cbc17f4e`; health, history, sync, precise
  prep and topo gates passed; manual sync ended `sync ok` and `done`.
- #404/#406 deployment evidence remains recorded: 237 related tests and
  nine-hole workload 35.49 s → 22.93 s.
- Internal TestFlight 0.1.0 (86) remains Apple-checked
  `VALID/IN_BETA_TESTING`; no upload is authorized by this review.

## Owned resources and cleanup

- Persistent #424 evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr424-5ac993ef-native-20261013`
  and `/home/jason/garmin-ai-caddie-data/operations/pr424-5ac993ef-native-ci-20261013`.
  Temporary harness branch is deleted; no container, service, tunnel, port,
  volume, or dependency environment was created by this recheck.
- Review worktree:
  `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011`,
  Codex-owned, back on `codex/pr424-production-harness-20261013`, expires
  2026-10-18 08:30 UTC.
- Existing untracked `.codex-*` evidence is historical and must remain.
  Archives for this closeout are
  `docs/archive/PROJECT_STATE-2026-10-13-pr424-before-close.md` and
  `docs/archive/2026-10-13-pr424-review-6eef9e13-before-close.md`.
- The feedback drain/waiter terminal ended after processing the #424 event.
  Start one required same-turn `ops/wait_for_conclusion.sh --feedback`
  after this closeout; observe only by five-minute sleep plus one
  `write_stdin`.

## Next action and stop conditions

1. Commit/push this closeout ledger and review record with the Codex trailer.
2. Start one same-turn `--feedback` waiter. Process only its one-line
   conclusion, restart it after each external event, and ignore already
   handled heads plus Codex-owned CI/comments.
3. Re-review future external PR events once their required CI is green.
4. End the goal after 48 hours with no external PR events and no open PRs, or
   earlier on an explicit owner stop instruction. Every Codex GitHub
   comment/review ends `_Generated by Codex_`; every Codex commit ends
   `Generated-by: Codex`.
