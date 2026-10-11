# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-11 14:31 UTC
**Canonical audit baseline:** main0882c41c / released source b662572e
**Current slice:** `WATCH-417-SIMULATOR-AUDIT` — `in-progress`

## Current state and deduplication

#404–#416 reviewed/merged; applicable backend deployments complete.
Do not repeat handled reviews/comments/tests or upload another Build86.
Claude #4166107086037 (October11 08:22:16UTC) requests #417:
whole-round Watch simulator findings only; no product fixes this pass.
Plan #4176107176093; first findings #4176109098136; draft scaffold PR #418.
Required final exact-head Native CI/screenshots before any scaffold merge.

## Unfinished queue

- `WATCH-417-SIMULATOR-AUDIT` — `in-progress`: three-face actual simulator
  audit, complete9/18-hole/turn flows, per-step screenshots/motion/contact
  sheets; ranked P1/P2/P3 findings in #417. Product fixes await Jason/Claude.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume after the audit.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 nonblocking
  variation reported #4166101180215; fixed-route snapshots should be consistent.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD86` — `evidence-open`: owner paired-device validation;
  package evidence does not prove physical installation/behavior.

## Audit source and evidence

#418 published headab1732e59b096c24b68ef0de575afb218a724afa, base0882c41c.
Guarded bundle pushes preserve shared HEAD/index; temporary refs removed.
Local follow-up prepared for publication; fixes only the driver: normal slow scroll flicks,
stop when a control is already hittable, correct 继续本场 label, quick wheel
captures/stored pointer coordinates, unique failure names and named manual
candidate recovery after a recorded unresponsive +. No product behavior fixes.
Preparation repeated145 tests (mobile10.293s); scoped container removed.
Native/runtime verification of that follow-up is still required.

- First source678eca1b: audit38136927473 failed; CI38136912931 and
  Native38136912932 succeeded. Ten methods/face actually ran;41/46mm6 failed,
 49mm7 failed.101/107/57 PNGs; artifacts73MiB+Native23MiB retained.
- Corrected sourceab1732e5: audit38140105793 failed; CI38140032223 and
  Native38140032219 succeeded. Ten methods/face, zero skips;41mm6 passed/
 4 failed/101 PNGs;46mm7/3/171 PNGs;49mm5/5/122 PNGs.12/12/13 observations.
  Artifact281MiB+Native23MiB retained.46mm complete nine-hole score/save passed;
 18-hole flow reached9/offline restoration. Other full-round coverage incomplete.
- Actual runtime receipts: Xcode26.3 / watchOS26.2,41/46/49mm. Mock26.0
  selector output in unit tests is not runner evidence.
- Preparation ab1732e5:7 audit-tool+12 native visual+126 mobile contracts
  =145 passed (mobile7.181s). First mobile read-only-data error preserved;
  fixture-only128MiB tmpfs resolved it; scoped container removed.
- UI evidence:41mm center575 shows5…;46/49mm two-digit score11 shows…;
  unzoomed swipe after measurement stays on plan; hazard drag at actual zoom2
  changes to green. Flag edge dragging/zoom/AOD/late map/stale snapshot/heading
  and shot undo/commit/candidate paths now have screenshots. Ultra + remains
  unresponsive in two passes; preserve finding, inspect later controls via a
  named injected candidate without claiming manual admission.
- Remaining harness issues: wrong restore button label, wheel idle closure
  racing slow metadata, scroll targeting/back/header retries. Follow-up above
  addresses those; do not report harness retries as user navigation cost.

Fixtures repeat one existing hole across synthetic all-par5 rounds; they do
not prove real-course geometry/caddie quality, GPS, battery, WCSession timing or
physical Crown/wrist behavior. Heading telemetry proves requested service state.
README§3/watch.html read; October10 full-bleed/floating F/M/B overrides older
prototype column. Audit detail:2026-10-11-watch417-simulator-audit.md.
Collection success differs from UX success: observation JSON preserves failed
expectations; named injected recovery boundaries must remain visible in reports.
Do not claim complete flow coverage for skipped/empty or partial galleries.

## Live verification baselines

- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6.
  API aicaddie-release-cbc17f4e-production-20261010/loopback39055;
  public https://caddie.taile36706.ts.net; user data/ingress retained.
  API/sync images prebuilt, deployment gates passed; manual sync33s/sync ok/done;
 43 new-image tests; health/history/sync/precise prep/PNG200.
- #404/#406 nine-hole workload35.4904→22.9303s;237 tests/5 existing skips.
  Report2026-10-10-pr404-406-backend-deploy.md; server time, not phone UX.
- #414 c13a717e approved/merged;126 contracts; Native38072029726
  iOS786/Watch454 unit tests,2 UI tests;144 PNGs matched.
- #416 a38a97bc approved/merged;126 contracts; Native38075749433
  iOS785/Watch452 unit tests,2 UI tests;143/144 PNGs identical, Watch unchanged.
- Independently verified internal TestFlight0.1.0(86): upload38083089271,
  Apple38084409144 VALID/IN_BETA_TESTING, existing internal group includes86;
  source b662572e/backend cbc17f4e; IPA
  c59ca85eb527443306d1f49462c8b2c09ac2ecaa2fbebf08ed66dbec0affb4e9.
  iPhone/embedded Watch plists86/companion IDs match; no physical install claim.
- Waiter0882c41c:15 provenance regressions, bash -n and explicit CI passed.
  No CI-result-only bookkeeping commits.

## Owned resources and cleanup

- One local editing implementation worktree:
  /home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011;
  Codex, created October11 08:30UTC, expiry October18 08:30UTC.
- One remote verification snapshot (30MiB, no worktree/dependencies):
  /dev/shm/garmin-ai-caddie-watch417-verify-20261011;
  expiry October12 08:30UTC; latest follow-up Swift sources refreshed.
- Private persistent evidence:
  /home/jason/garmin-ai-caddie-data/operations/watch417-simulator-audit-20261011.
  Test containers auto-removed; no new service/tunnel/timer/delegated agent.
  Manifest .codex-watch417-20261011-manifest.md; transport bundles/publish receipts
  retained. Use exact source hashes above, not the old hardcoded publisher.
- PTYs11516/61473/91314 closed;11516 delivered task,61473/91314 delivered
  all three explicit terminal conclusions (exit1 for audit failures).
  Download terminals9348/56753 closed0. No active waiting terminal.
- Owned local first/second contact-sheet copies .codex-watch417-first-contact-sheets/
  and .codex-watch417-second-contact-sheets/; backed by private persistent
  artifacts, expiry October12 08:30UTC. No local image processing.
- Preserve unrelated dirty parent checkout e930ca65 and older .codex-* files.
  Shared source /home/jason/codex-runs/garmin-ai-caddie-claude-takeover-20261005:
  never checkout/reset/stash, overwrite files or use normal index.
- gh-feedback timer/cursor unchanged. Published waiter:
  /home/jason/garmin-ai-caddie-data/operations/wait-release-filter-20261010/publication/ops/wait_for_conclusion.sh
- Last capacity57GiB disk/4.7GiB available RAM; recheck before heavy work.
- Prior ledgers preserved verbatim in dated docs/archive/PROJECT_STATE-2026-10-11-*
  files, including before-watch417-second-runtime-triage.

## Next action and stopping

Remote-verify/publish the remaining test-driver corrections on #418; one explicit
corrected-source dispatch and exact Native wait. Retain both prior attempts.
Finish all feasible9/18/turn UI paths; preserve genuine dead ends as findings,
not passing assertions. Inspect every flow/face and relevant motion; rank findings
with screenshot/design links in #417. Review/merge scaffold when justified,
close owned resources and resume feedback waiting in this same turn.
No product fixes or new release upload in this audit.

For feedback: retain one PTY, echo disabled/SSH -T; wait300000ms then write_stdin
once with newline; repeat until one-line conclusion. No interleaved liveness/
CI/state polling, independent tmux waiter, second monitor, CI-only commits or
quiet resets for own events. Explicit waits follow the same boundary.

Owner resumed after historical October9 cutoff. Stop after48h without external
PR events and no open PRs, or owner stop. Last recorded external event:
Claude #4166107086037, October11 08:22:16UTC; conditional quiet stop
October13 08:22:16UTC. Complete #417 first; confirm newer external events/open
PRs before completion. Own commits/comments/CI/bookkeeping do not reset it.
Keep this ledger≤200 lines.
