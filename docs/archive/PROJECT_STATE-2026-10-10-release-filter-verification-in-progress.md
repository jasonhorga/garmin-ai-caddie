> HISTORICAL ARCHIVE — NON-AUTHORITATIVE
>
> Verbatim ledger while release filtering was prepared, before remote test/Apple closure.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-10 20:33 UTC
**Canonical branch:** main; origin/main b662572e; product merge a08634a8
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

#404–#416 reviewed/merged; applicable backend deployments complete. Do not repeat
handled reviews/comments/tests. Reports and verbatim archives preserve evidence.
#413/#414/#416 branches/resources closed; evidence published b662572e.
Shared canonical checkout remains a38a97bc; preserve its HEAD/files/normal index.

Current operation: correct suppression of manual TestFlight/Apple outcomes on
Codex heads, then validate successful release38083089271. Code prepared in
ops/wait_for_conclusion.sh, provenance tests and AGENTS. Only actual
workflow_dispatch runs for the three TestFlight workflows bypass self-CI
filtering; manual Native CI remains suppressed. Remote tests not executed yet.

Release38079005590 failed19:20:08UTC at backend-preflight TLS EOF before upload.
Build86 archive/export succeeded; no uploaded86 claim. Explicit verdict preserved
in blocking-waits/wait-release-38079005590-20261010T201619Z-122809.log.
Claude's retry38083089271 on b662572e returned success/none through delegated
explicit waiter; handle17379 closed0, no resources. No duplicate upload.
Log blocking-waits/wait-release-38083089271-20261010T202711Z-130634.log.
Verify its package/provenance, then Apple via ios-testflight-testers.yml,
operation=list and external_distribution=false.

SSH loss20:02UTC recovered20:10:16. Exact owned orphan73178 closed with receipts
in operations/feedback-recovery-20261010T2010; cursor/shared monitor preserved.
Loopback/public health200/cbc17f4e. No routes/proxies/keys changed.
No pending main feedback terminal or delegated wait; rearm after this operation.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: exact-head reviews and same-turn waits.
- `WAIT-RELEASE-EVENT-FILTER` — `queued`: code prepared; remote regressions,
  resource closure and scoped publication required before corrected waiter use.
- `RELEASE-38083089271` — `evidence-open`: terminal success; independently
  verify package and Apple processing/internal availability.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: nonblocking 八号铁164 variation
  reported in #4166101180215; fixed-route snapshots should remain consistent.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired-device validation owner work.

## Live verification baseline

- Production API/sync cbc17f4e76f085229c3bdb3c74a5067951b217a6.
  API aicaddie-release-cbc17f4e-production-20261010, loopback39055;
  public https://caddie.taile36706.ts.net; user data/ingress retained.
  API garmin-ai-caddie-api:cbc17f4e76f085229c3bdb3c74a5067951b217a6-candidate-20261010;
  sync aicaddie-sync:cbc17f4e76f085229c3bdb3c74a5067951b217a6.
  Both prebuilt before cutover; revision/deployment gates passed.
  Manual sync17:51:52–17:52:25UTC/33s, exact revision/sync ok/done.
  New-image43 tests/0.969s. Health/history/sync/precise prep/PNG200.
- #404/#406 nine-hole mixed workload35.4904→22.9303s;237 tests/5 existing skips.
  Report2026-10-10-pr404-406-backend-deploy.md; server time, not phone UX.
- #414 exact c13a717e approved6100961909/merged de2cedcf;126 contracts/8.492s.
  Native38072029726 iOS786/0, Watch454/0,2 UI tests;144 PNGs matched.
- #416 exact a38a97bc approved6101180215/merged a08634a8;126 contracts/6.491s.
  Native38075749433 iOS785/0, Watch452/0,2 UI tests;143/144 PNGs identical,
  all Watch unchanged; zoomed iOS image variation reported as nonblocking.
- Last independently verified TestFlight0.1.0(82): upload37774511661,
  Apple37776197288 VALID/IN_BETA_TESTING; IPA
  f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721.
  No newer Apple-verified package yet. Simulator/source evidence does not prove
  physical-device GPS, battery, WCSession timing or installation.

## Owned resources and cleanup

- No pending feedback terminal, delegated agent, service, container, volume,
  dependency environment, tunnel or implementation worktree.
- Reserved snapshot /dev/shm/garmin-ai-caddie-wait-release-filter-20261010;
  expires2026-10-11 20:33UTC, manifest recorded before creation.
  Evidence operations/wait-release-filter-20261010: manifest/source hashes/
  tests/publication/cleanup. Alternate publication index removed after push.
  Tests use mocked GitHub data; no production cursor/event modifications.
- Earlier #413/#414/#416 snapshots/controls closed, evidence retained.
  #415 disposable resources closed; old f9586f6c stopped/rollback retained.
- Preserve unrelated dirty ops/pr_feedback_monitor.sh and older .codex-* files.
  Local main e930ca65/older docs commits retained. Shared remote repository
  /home/jason/codex-runs/garmin-ai-caddie-claude-takeover-20261005 is Claude's too:
  never switch/reset/stash, alter its files or use its normal index.
  Publish scoped code/evidence via alternate index on fresh origin/main.
- gh-feedback timer and blocking-waits/feedback-cursor unchanged.
  Last capacity49GiB disk/5.0GiB available RAM/3.3GiB shm.
- Displaced ledger retained verbatim in
  docs/archive/PROJECT_STATE-2026-10-10-before-release-filter-fix.md.

## Next action and stopping

Run provenance regressions on homeserver and inspect38083089271 upload metadata.
Confirm Apple through the real read-only tester workflow; comment verified
outcome on #416. Publish tested waiter/policy/evidence, close exact resources,
preserve shared working state. Then one same-turn --feedback terminal:
wait300000ms, read its handle once, repeat until one-line conclusion.
No liveness checks/second monitor, CI-only commits or quiet resets for own CI.
Handle returned new events; exact-head CI/Native/screenshots before merge.

Owner resumed after historical October9 cutoff. Stop after48h without external
PR events and no open PRs, or an owner stop. Last recorded external PR check-set
#4162026-10-10 18:40:59UTC; conditional quiet stop2026-10-12 18:40:59UTC.
Update after genuine external release/event provenance verification; own commits/
CI/comments never reset it. Confirm no newer events/open PRs before completion.
Keep this ledger≤200 lines.
