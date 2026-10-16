<!-- HISTORICAL ARCHIVE — NON-AUTHORITATIVE -->
# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Completed/history is preserved verbatim in dated `docs/archive/` files.

**Updated:** 2026-10-13, PR424 exact-head production audit concluded with P2
**Canonical baseline:** main `af918d60`; PR424 review head `cc84f909`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress` (#424 review)

## Current state

- #404–#416 reviewed and merged; #417 remains an evidence issue with findings
  already posted. #418 remains draft/evidence-open. #420 remains
  evidence-open for the 49 mm first-tap rail. #421 awaits external review.
- #422 is draft/test-only and must not be merged. Its exact-head review is
  complete; do not treat prototype callbacks as production evidence.
- #423 was reviewed, fixed, merged as `46f9c8ff`, and its branch was deleted.
- #424 is open and not approved. Requested head `27c9ad36` is the first
  parent of current head `cc84f909`; the second parent is main
  `af918d60`. The production score/root/turn source review and five-face
  runtime audit are complete. One P2 remains: 45 mm fresh-launch
  `fairway-open` failed its first centre tap. Claude must fix and rerun the
  exact-head audit before merge.
  P2 conclusion is posted at
  https://github.com/jasonhorga/garmin-ai-caddie/pull/424#issuecomment-6152319702.
- The revision acknowledgement, phone tee-landing fallback, and inline
  开球左/中/右 row are covered by source review and Native tests. No new
  source-level blocker was found in those changes.

## Unfinished queue

- `PR-424-45MM-FIRST-TAP` — `evidence-open`: fix the 45 mm
  `watch-score-fairway` first-tap failure, then rerun the full fresh-launch
  five-face production harness and post receipts.
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

- Requested-head CI: ordinary `38403888026`, Native
  `38403887972`; both passed. Current merge-head CI: ordinary
  `38435188634`, Native `38435188599`; both passed.
- Native artifacts were downloaded and inspected for both heads. Current head
  artifacts are design `11832603751` and Watch `11834067000`; 47 Watch and
  97 phone snapshots showed no layout, clock, safe-area, or crop regression.
- Test-only harness `60cc7ebc`, runtime `38422216695`, evidence
  `/home/jason/garmin-ai-caddie-data/operations/pr424-27c9ad36-rerun-20261013`.
  Production taps: 41 mm 390/390, 42 mm 390/390, 45 mm 389/390,
  46 mm 390/390, 49 mm 390/390.
- The sole failure is
  `watch-audit-45mm/0003-production-tap--fairway-open-x0-2.json`:
  fresh launch, centre point `[53,196]`, AX frame `[10,177,86,38]`,
  interactive bottom 215, no state change after 4.5 s. The same control
  succeeds on retry. Its 38 pt exposed frame sits at the bottom hit boundary;
  require a stable first tap and rerun fresh-launch trials.
- Additional receipts passed: first-shot record 50/50, undo 50/50,
  Watch→phone second-nine sync 2/2, and B→C→B revision acknowledgement in
  Native unit coverage. Native log: 470 Watch unit tests and 2 UI tests.
- Simulator evidence does not establish physical Crown, GPS, WCSession
  delivery, OLED brightness, or wrist interaction.

## Live verification baselines

- Production API/sync baseline: `cbc17f4e`; health, history, sync, precise
  prep and topo gates passed; manual sync ended `sync ok` and `done`.
- #404/#406 deployment evidence remains recorded: 237 related tests and
  nine-hole workload 35.49 s → 22.93 s.
- Internal TestFlight 0.1.0 (86) remains Apple-checked
  `VALID/IN_BETA_TESTING`; no upload is authorized by this review.

## Owned resources and cleanup

- Review snapshot manifest `.codex-pr424-6eef9e13-review-manifest.md`;
  persistent evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr424-27c9ad36-rerun-20261013`
  and `/home/jason/garmin-ai-caddie-data/operations/pr424-cc84f909-native-20261013`.
  The contract container is removed; no new service, tunnel, port, volume, or
  dependency environment was created.
- Review worktree:
  `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011`,
  Codex-owned, expires 2026-10-18 08:30 UTC.
- Existing untracked `.codex-*` evidence is historical and must remain.
  Archives created for this update:
  `docs/archive/PROJECT_STATE-2026-10-13-pr424-before-final.md` and
  `docs/archive/2026-10-13-pr424-review-6eef9e13-before-final.md`.
- Feedback waiter terminal `3642` is retained only until this review is
  posted; restart the required same-turn `ops/wait_for_conclusion.sh
  --feedback` afterwards and observe only via five-minute sleep plus one
  `write_stdin`.

## Next action and stop conditions

1. Commit/push this state and review record with the Codex trailer; the P2
   blocking #424 review comment is posted at issuecomment-6152319702.
2. Start one same-turn `--feedback` waiter. Process only its one-line
   conclusion, then restart it after each external event. Do not poll CI,
   processes, monitor state, or logs from the main thread.
3. Re-review #424 only after Claude supplies a fix and green exact-head
   Native/runtime evidence. Do not merge while the P2 is open.
4. End the goal after 48 hours with no external PR events and no open PRs, or
   earlier on an explicit owner stop instruction. Every Codex GitHub comment
   ends `_Generated by Codex_`; every Codex commit ends
   `Generated-by: Codex`.
