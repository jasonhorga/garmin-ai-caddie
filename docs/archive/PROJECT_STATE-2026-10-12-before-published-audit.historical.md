HISTORICAL ARCHIVE — NON-AUTHORITATIVE

# Garmin AI Caddie Project State

> Short authoritative live ledger. History is preserved in dated archives.

**Updated:** 2026-10-12 02:58 UTC
**Canonical baseline:** main 3e785b14 / product merge 95b5694e (#419)
**Current slice:** WATCH417-ELEMENT-AUDIT — in-progress

## Current state

- Owner widened #417 (6111380071 / 6111790655): wrist-scale element review,
  repeated gestures, 20/60 pt drags, value reachability, real-round tempo,
  adversarial navigation and S70/Golfshot/Apple Workout comparison.
- Both comments read completely; issue-only wake-up miss acknowledged in
  6114726773. Scaffolding only; Claude implements product fixes after triage.
- #419 merged; #418 draft on codex/watch417-simulator-audit. Reuse existing
  editing worktree; no second implementation checkout.
- Full run 38182935895 / 1ef62984: 16 methods per face, no skips;
  41/46/49 mm 11/5, 14/2, 12/4 pass/fail, 252/343/334 PNGs.
- Control supplement 38188153210 / 8e6feee6: four methods per face, no skips;
  41/46/49 mm 3/1, 2/2, 4/0 pass/fail, 51/39/63 PNGs.
- P1 49 mm manual shot 0/5 posted in 6115815445; 41/46 mm 5/5 with undo.
  No injected candidate in these first-pointer trials.
- Also document root menu 49 mm 0/5 (41/46 mm 5/5), page swipe 0/5,
  hazard pan switches page, clipped numbers and many element-level frictions.
- Picker supplement 38191363704 / c1d5c876: two methods per face, no skips,
  all pass; 58/60/58 PNGs. Range pairs: 41/46 mm 61/61 valid; 49 mm 60/60
  plus one invalid preparation. Continuous trials still hit collection races;
  do not label these raw rates as confirmed product failures.
- Required CI 38191204820 / Native CI 38191204685 pass at c1d5c876.
- New scaffold samples state before a fresh chip-open plus immediate input;
  no query between open and pointer gesture, no production timer change.
  Remote nine audit regressions pass (1.120 s). New exact native/runtime
  evidence still required. Partial runs cannot masquerade as full coverage.
- Immediate-picker 38194936812 / 7155607d plus required/Native
  38194820494 / 38194820350 succeeded; artifacts downloaded to a separate
  immutable root. Adjudicate fresh-open rates and all start/target pairs.
- Review correction: plan-pan raw 0/5 conflicts with visible movement;
  withhold a plan-pan defect. Earlier hazard-pan trials 2–5 ran on 果岭,
  so only the first is valid. Scoped map-recheck resets before every pan,
  reads fresh snapshots and captures settled images; no product edits.
- Nine map collector regressions pass (2.060 s). Thirty-four distinct
  states inspected in nine calibrated normal/glare pages; physical wrist,
  display ruler calibration and sunlight remain unproved.
- Raw evidence immutable; earlier compile failures are harness diagnostics.
  #404–#416 deployment and internal TestFlight Build 86 already complete.

## Unfinished queue

- WATCH417-ELEMENT-AUDIT — in-progress: complete calibrated image review,
  fresh-open picker supplement, per-screen tables, task counts and distinct
  evidence-backed P1–P3 findings on #417.
- PR-418-AUDIT-SCAFFOLD — evidence-open: draft; collection is not a UX pass.
- PR-FEEDBACK-CONTINUOUS — queued: resume deduplicated feedback after #417.
- NATIVE-FIXTURE-LAYOUT-STABILITY — queued: nonblocking #416 variation.
- IOS-STATUS-CONTRAST — queued: nonblocking dark status/navigation text.
- OWNER-DEVICE-BUILD86 — evidence-open: paired physical-device validation.

## Verification boundaries

- Adjudicate final state separately from raw predicate flags. XCTest time is
  synchronization overhead, not 300 ms visible feedback latency.
- AX content bounds can differ from padded hit bounds; boundary taps needed.
  Source font tokens are not measurements of scaled glyph size.
- Crown, gloves, wet fingers, wrist/AOD sensing, sunlight/OLED, GPS, battery,
  notifications and actual WCSession timing remain hardware gaps.
- Physical exports retain pixels, mm/DPI and rulers; reduced pages are
  calibrated proxies, not a claim of wearing a watch.
- Fixture repeats one factual mapped hole, no all-course/caddie quality claim.
  No new TestFlight requested. No product fixes in this audit.

## Live verification baselines

- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6;
  health/history, incremental sync and prep/topo gates passed; sync ok/done.
- #404/#406: 237 related tests, five existing skips; nine-hole workload
  35.49 s -> 22.93 s, two render workers; deployment evidence retained.
- Internal TestFlight 0.1.0 (86): Apple VALID / IN_BETA_TESTING verified.
- #419 required/Native 38159377877 / 38159377871, PASS 6112715912.

## Owned resources and cleanup

- Editing worktree /home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011;
  Codex, created Oct 11 08:30 UTC, expires Oct 18 08:30 UTC.
- Persistent roots under /home/jason/garmin-ai-caddie-data/operations:
  watch417-simulator-audit-20261011, pr419-4cfb1588-20261011,
  watch417-wide-audit-20261012, watch417-control-recheck-20261012,
  watch417-picker-recheck-20261012. Raw/artifacts, physical aids, fetched
  reference receipts, diagnostics and waiter logs retained.
- New persistent operations root: watch417-immediate-picker-20261012;
  exact 7155607d artifacts, no old evidence overwritten.
- Local /tmp/garmin-watch417-images-20261012-GCqa8Y expires Oct 13 08:30 UTC
  or after review; preserve remote originals.
- No live audit service, dependency environment, volume, port, tunnel or timer.
  Terminal 18014 closed SSH 255 without output. Delegated replacement 67985
  returned three success conclusions and closed 0; download 72960 closed 0.
  Latest agent's original three-waiter shell/attachment and handles closed 0;
  summaries recovered from owned logs. No pending waiter; cursor unchanged.
- Snapshot /dev/shm/garmin-ai-caddie-watch417-immediate-picker-20261012:
  31 MiB, read-only, expires Oct 13 02:02 UTC or after verification.
  Named --rm container exited 0 and removed; snapshot removed after open-file check.
  Manifest/log retained in picker evidence. Older snapshots already removed.
- Map collector snapshot /dev/shm/garmin-ai-caddie-watch417-map-recheck-20261012;
  only two input files, expires Oct 13 02:50 UTC or after verification;
  24 KiB, nine tests passed; no open files, named --rm container removed;
  exact snapshot removed after persistent manifest/log retention.
- Shared canonical checkout unchanged. Force-add only individually named
  owned history ledgers because docs/archive is Git-ignored.

## Next action and stop conditions

1. Push scoped map-recheck scaffold and dispatch after picker run closure;
   adjudicate exact-head picker evidence, keep all raw results immutable.
2. Finish physical/normal/glare evidence, publish tables and distinct
   findings on #417 with Actions links and no internal hosts/paths.
3. Keep #418 draft until sufficient coverage/triage; return to feedback.
   Never commit CI bookkeeping alone or loop on own CI events.

Continuous cutoff: 2026-10-13 08:22:16 UTC, or earlier after 48 hours without
external PR events and no open PRs. Explicit #417 audit remains authorized;
owner stop overrides work. GitHub comments end _Generated by Codex_;
Codex commits end Generated-by: Codex. Keep ledger <=200 lines; archive
historical detail verbatim by date.
