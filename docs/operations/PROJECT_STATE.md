# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-11 12:34 UTC
**Canonical branch:** main 0882c41c; released source b662572e
**Current slice:** `WATCH-417-SIMULATOR-AUDIT` — `in-progress`

## Current state and deduplication

#404–#416 reviewed/merged; applicable backend deployments complete. Do not repeat
handled reviews/comments/tests, or upload another Build86.
Claude's #416 comment6107086037 (October11 08:22:16UTC) requests #417:
whole-round Watch simulator UI/UX findings only; no product fixes this pass.
Plan posted #4176107176093. Scaffolding draft PR #418 is open.
Review required CI and dedicated actual simulator artifacts before any merge.

## Unfinished queue

- `WATCH-417-SIMULATOR-AUDIT` — `in-progress`: newest installed stable
  Xcode/watchOS, 41/46/49mm, ten production-control flows; per-step screenshots,
  motion recordings/contact sheets, ranked P1/P2/P3 findings in #417.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume after the current audit.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: nonblocking 八号铁164
  variation reported #4166101180215; fixed-route snapshots should be consistent.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD86` — `evidence-open`: owner paired-device validation;
  build86 package evidence supersedes82, physical-device behavior is unproven.

## Audit source and verification

Owned implementation branch codex/watch417-simulator-audit, base0882c41c.
Published exact #418 head678eca1b05b34bdc541200e0e1388074a9f7c509;
34082897 initial source and8bfb7fd3 unpublished draft superseded.
Guarded bundle push preserved shared HEAD/index and removed temporary ref.
Latest follow-up: exact measurement clearing/flag edge drag/zoomed hazard switching,
mixed A/B venues and consistent220-yard shot movement.
Latest source preparation:6 audit-tool +12 native visual +126 mobile
contracts=144 tests passed; mobile7.297s; two workflow YAML files parsed.
First #418 source34082897: CI38127947554/Native38127947531 succeeded;
latest exact-head Native CI/screenshot evidence still pending. First mobile attempt
hit read-only fixture data; isolated128MiB tmpfs resolved it, container removed.
First audit38136927473 finished failure; CI38136912931/Native38136912932
succeeded. PTY61473 closed1 after delivering all three explicit conclusions.
Artifacts retained privately: audit73MiB/Native23MiB. All ten audit methods
actually executed on each face:41/46mm6 failures,49mm7; no skipped-audit claim.
Actual observed runner: Xcode26.3/watchOS26.2 (not mocked26.0).
Initial screenshots inspected:41mm center575 clips to5…; unzoomed swipe after
measurement stayed on plan; zoomed hazard drag switched to green. Provisional
UI findings need viewport telemetry/reproduction. Harness also queried a switch
as a button and scroll up/down could undo its own progress. Ultra bottom-control
taps did not transition; explicit visual-centre taps/real long-press alternative
will separate pointer/harness behavior from a dead-end product flow.
Test-only corrections/observations implemented;7 audit-tool+12 visual+126
mobile contracts=145 passed (mobile7.181s). Named recovery preserves broken
interactions while collecting later pages; no product fixes. First-pass gallery
101/107/57 screenshots, face comparisons artifact11702260861.
Exact new-head Native/runtime verification still required.
Mock selector watchOS26.0 is test data, not an observed runner runtime.

Fixtures repeat an existing hole across synthetic all-par5 rounds. This does
not establish real course geometry/caddie quality, GPS, battery, WCSession
timing or physical Crown/wrist behavior. Selected hardware/events are injected;
heading telemetry establishes requested service state only.
README§3 and watch.html layout/interaction reference read. October10 full-bleed map/floating
F/M/B direction overrides older prototype column.
Detailed scope: docs/operations/2026-10-11-watch417-simulator-audit.md.

## Live verification baselines

- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6.
  API aicaddie-release-cbc17f4e-production-20261010/loopback39055;
  public https://caddie.taile36706.ts.net; user data/ingress retained.
  API/sync images prebuilt before cutover; deployment gates passed.
  Manual sync17:51:52–17:52:25UTC/33s, exact revision/sync ok/done.
 43 new-image tests passed; health/history/sync/precise prep/PNG200.
- #404/#406 mixed nine-hole workload35.4904→22.9303s;237 tests/5 existing
  skips. Report2026-10-10-pr404-406-backend-deploy.md; server time, not phone UX.
- #414 c13a717e approved/merged;126 contracts; Native38072029726
  iOS786/Watch454 unit tests,2 UI tests;144 PNGs matched.
- #416 a38a97bc approved/merged;126 contracts; Native38075749433
  iOS785/Watch452 unit tests,2 UI tests;143/144 PNGs identical, Watch unchanged.
- Independently verified internal TestFlight0.1.0(86): upload38083089271,
  Apple38084409144 VALID/IN_BETA_TESTING, existing internal group includes86;
  source b662572e/backend cbc17f4e; IPA
  c59ca85eb527443306d1f49462c8b2c09ac2ecaa2fbebf08ed66dbec0affb4e9.
  iPhone/embedded Watch plists86/companion IDs match. No physical install claim.
- Waiter filter0882c41c:15 provenance regressions/12.740s, bash -n,
  explicit CI38085319748 passed. No CI-result-only bookkeeping commit.

## Owned resources and cleanup

- Local editing implementation worktree:
  /home/ubuntu/claude-web-data/repo/garmin-ai-caddie-watch417-20261011;
  owner Codex, created October11 08:30UTC, expiry October18 08:30UTC.
- Remote verification snapshot (30MiB, no Git worktree/dependencies):
  /dev/shm/garmin-ai-caddie-watch417-verify-20261011;
  expiry tightened to October12 08:30UTC; three latest Swift files refreshed.
- Persistent private evidence:
  /home/jason/garmin-ai-caddie-data/operations/watch417-simulator-audit-20261011.
  Manifest .codex-watch417-20261011-manifest.md; scoped contract container
  removed; no active new service/tunnel/timer/delegated agent.
- Existing transport bundle/publisher preserved; old publisher hardcodes34082897
  and creates a PR: do not rerun unchanged. Use a new exact-SHA bundle updater.
  Prior temporary publication ref removed; shared HEAD/index guards passed.
- Parent local checkout e930ca65 has unrelated dirty/older .codex-* files;
  preserve them. Shared remote source
  /home/jason/codex-runs/garmin-ai-caddie-claude-takeover-20261005 belongs to
  Claude too: never checkout/reset/stash, overwrite files or use normal index.
- All prior feedback/release/Apple terminals closed.11516 delivered the #417
  task and closed0. Explicit wait PTY61473 closed1; artifact-download terminal9348 closed0.
  No active waiter; do not recover old handles.
  Prior transport recoveries/closure receipts retained in dated operations.
- gh-feedback timer/cursor unchanged. Published waiter:
  /home/jason/garmin-ai-caddie-data/operations/wait-release-filter-20261010/publication/ops/wait_for_conclusion.sh
- Local first-pass contact-sheet copy .codex-watch417-first-contact-sheets/
  is owned, backed by private persistent artifacts; expiry October12 08:30UTC.
- Last verified capacity57GiB disk/4.9GiB RAM. Recheck before heavy work.
- Displaced ledger preserved verbatim in
  docs/archive/PROJECT_STATE-2026-10-11-before-watch417-runtime-verification.md; subsequent transition in
  PROJECT_STATE-2026-10-11-before-watch417-dispatch.md.

## Next action and stopping

Publish the corrected test harness (directional container scroll, Switch query,
explicit tap coordinates, viewport/page telemetry, non-silent recovery after
recorded UI findings; collector rejects zero/skipped methods). Remote preparation verified145 tests; publish
#418 follow-up, then one documented dispatch on that corrected exact source.
Retain first failure as evidence; do not rerun unchanged source. Required final
exact-head Native CI/screenshots before merge. Complete9/18-hole/turn flows,
review all faces/artifacts and report ranked findings/gaps to #417.
Separate harness failures, product findings and simulator gaps; report #417.
Do not claim ten flows ran if skipped or artifacts are empty.
Close owned resources when review ends, then resume feedback waiter same turn.

For feedback: retain one owned PTY, echo disabled/remote -T, wait300000ms then
write_stdin once with newline; repeat until one-line conclusion. No ad-hoc
liveness polling, independent tmux waiter, second monitor, CI-only commits or
quiet resets for own events. Explicit CI/release waits follow the same boundary.

Owner resumed after historical October9 cutoff. Stop after48h without external
PR events and no open PRs, or owner stop. Last recorded external event:
Claude #4166107086037, October11 08:22:16UTC; conditional quiet stop
October13 08:22:16UTC. Complete #417 first and confirm newer external events/open
PRs before completion. Own commits/comments/CI/bookkeeping do not reset it.
Keep this ledger≤200 lines.
