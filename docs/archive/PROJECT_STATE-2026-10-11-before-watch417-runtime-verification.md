HISTORICAL ARCHIVE — NON-AUTHORITATIVE


# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-11 08:30 UTC
**Canonical branch:** main; product merge a08634a8; released source b662572e
**Current slice:** `WATCH-417-SIMULATOR-AUDIT` — `in-progress`

## Current state and deduplication

#404–#416 reviewed/merged; applicable backend deployments complete. Do not repeat
handled reviews/comments/tests. Reports and verbatim archives preserve evidence.
#413/#414/#416 branches/resources closed; evidence published b662572e.
Shared canonical checkout remains a38a97bc; preserve its HEAD/files/normal index.

Waiter/tests/AGENTS and release86 evidence published0882c41c8f872f4f71ead309d19ac3fae9e2add3.
Actual Actions workflow/event metadata grants the exception only to the three
manual TestFlight workflows. Own ordinary/manual Native CI remains suppressed.
Homeserver15 provenance regressions/12.740s passed, no skips; bash -n passed.
Snapshot closed. Published waiter runtime path is this operation's persistent
publication/ops/wait_for_conclusion.sh; do not overwrite shared source files.

Release38079005590 failed19:20:08UTC at backend-preflight TLS EOF before upload.
Build86 archive/export succeeded; no uploaded86 claim. Explicit verdict preserved
in blocking-waits/wait-release-38079005590-20261010T201619Z-122809.log.
Claude's retry38083089271 on b662572e returned success/none through delegated
explicit waiter; handle17379 closed0, no resources. No duplicate upload.
Log blocking-waits/wait-release-38083089271-20261010T202711Z-130634.log.
Downloaded IPA/provenance independently match source/run/backend/hash; actual
iPhone and embedded Watch plists both0.1.0(86). Apple read-only38084409144
success20:37:04UTC: VALID/unexpired/IN_BETA_TESTING; existing internal all-builds
group contains86, external group does not. No particular device-install claim.
Apple log blocking-waits/wait-ci-38084409144-20261010T203723Z-143537.log.
Report2026-10-10-release86-and-waiter-filter.md; #416 reply6102006509 handled.

SSH loss20:02UTC recovered20:10:16. Exact owned orphan73178 closed with receipts
in operations/feedback-recovery-20261010T2010; cursor/shared monitor preserved.
Loopback/public health200/cbc17f4e. No routes/proxies/keys changed.
Second transport incident recovered21:48:35UTC. Terminal57229 ended SSH255,
no summary; reconnect had banner timeout and public TLS failure. Existing local
listener/keepalive retained. Exact orphan174535/start21:07:27/UID1000/cwd/fds
verified; TERM via pidfd closed it and own tail174548. Cursor hash unchanged.
Receipts operations/feedback-recovery-20261010T2148; no shared service changes.
Loopback/public health200/ok/cbc17f4e. Single-consumer ownership recovered;
Third handle81339 also endedSSH255; exact orphan220407/start21:53:37 and own
220420 closed via verified pidfds; cursor unchanged, health200/cbc17f4e.
Receipts operations/feedback-recovery-20261010T2229. Pending PTY handle11516.
Effective server channel/unused timeout none; causal limit not established.
Next same-turn wait uses an owned local PTY with echo disabled and remote -T;
on each5-minute write_stdin observation send one newline as terminal keepalive.
Only a status/conclusion summary begins event processing; no config/timer changes.

## Unfinished queue

- `WATCH-417-SIMULATOR-AUDIT` — `in-progress`: Jason/Claude #417 findings-only
  whole-round Watch audit on newest Actions watchOS, 41/45-or46/49mm faces.
  Test/workflow scaffolding allowed on its own branch/PR; no product fixes.
  Capture per-step screenshots and motion recordings, face contact sheets,
  ranked P1/P2/P3 findings with design references and explicit simulator gaps.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume after the current audit slice.
- `WAIT-RELEASE-EVENT-FILTER` — `done`:15 regressions passed; this commit
  publishes code/policy/evidence; explicit CI38085319748 also passed.
- `RELEASE-38083089271` — `done`:0.1.0(86), uploaded/source/Apple/internal group
  independently verified; exact artifacts retained, both wait terminals closed.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: nonblocking 八号铁164 variation
  reported in #4166101180215; fixed-route snapshots should remain consistent.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD86` — `evidence-open`: current paired-device validation owner work;
  supersedes the old build82 baseline without claiming device validation.

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
- Independently verified TestFlight0.1.0(86): upload38083089271,
  Apple38084409144 VALID/IN_BETA_TESTING, existing internal group includes86;
  source b662572e, backend cbc17f4e, IPA
  c59ca85eb527443306d1f49462c8b2c09ac2ecaa2fbebf08ed66dbec0affb4e9.
  Both package plists86/companion IDs match. This does not prove physical-device
  GPS, battery, WCSession timing or installation. Prior82 details archived.

## Owned resources and cleanup

- Terminal57229 closed255; its exact orphan174535 and own tail174548 are closed.
  Third terminal81339 closed255; old220407/220420 closed, local1818-byte control
  removed after persistent hash/fuser checks. Manifest/receipts retained under
  feedback-recovery-20261010T2229. Next handle is an owned same-turn PTY using the
  same published waiter; input heartbeat is a scoped experiment, not proven fix.
  PTY11516 returned issue_comment6107086037/#416 and closed0 on October11.
  #417 new-task comment consumed; issue scope read. No pending feedback waiter.
  Manifest/ownership/pidfd closure/cursor hashes/health/capacity retained in
  operations/feedback-recovery-20261010T2148. Local1818-byte recovery control
  removed after persistent hash/fuser checks; manifest remains recoverable audit.
  No delegated agent, service, container, volume, dependency environment,
  tunnel or implementation worktree; no proxy/key/route/service changes.
  Terminal83480 closed0 and two immediate replay waits closed0: actual stream
  delivery of38083089271/38084409144/#4166102006509 confirmed and deduplicated.
  No new external event or quiet reset; no replay-induced commits/comments.
- Snapshot /dev/shm/garmin-ai-caddie-wait-release-filter-20261010 closed:
 34520bytes, source comparisons/process cwd/fds clear; exact2-file deletion.
  Evidence operations/wait-release-filter-20261010: manifest/source hashes/tests/
  scripts/release IPA/provenance/Apple/cleanup/publication; persistent retained.
  Guarded publication0882c41c complete; active alternate index removed and shared
  normal index/head/files unchanged. Aborted whitespace index retained as audit.
  Local controls have exact backup/allow-list receipts; no production cursor/
  event changes. Both release/Apple delegated handles closed; no cleanup pending.
- Earlier #413/#414/#416 snapshots/controls closed, evidence retained.
  #415 disposable resources closed; old f9586f6c stopped/rollback retained.
- One planned editing worktree: garmin-ai-caddie-watch417-20261011, branch
  codex/watch417-simulator-audit, owner Codex, expiry October18 08:30UTC.
  Manifest .codex-watch417-20261011-manifest.md; no new remote snapshot yet.
- Preserve unrelated dirty ops/pr_feedback_monitor.sh and older .codex-* files.
  Local main e930ca65/older docs commits retained. Shared remote repository
  /home/jason/codex-runs/garmin-ai-caddie-claude-takeover-20261005 is Claude's too:
  never switch/reset/stash, alter its files or use its normal index.
  Publish scoped code/evidence via alternate index on fresh origin/main.
- gh-feedback timer and blocking-waits/feedback-cursor unchanged.
  Last capacity49GiB disk/5.0GiB available RAM/3.3GiB shm.
- Displaced ledger retained verbatim in
  docs/archive/PROJECT_STATE-2026-10-10-before-release-filter-fix.md and
  PROJECT_STATE-2026-10-10-release-filter-verification-in-progress.md; post-publication
  transition preserved in PROJECT_STATE-2026-10-10-before-resuming-feedback.md;
  second-recovery states retained in before-second-transport-recovery and
  second-transport-recovery-in-progress dated archives; third prior state in
  PROJECT_STATE-2026-10-10-before-third-transport-recovery.md.

## Next action and stopping

Publication/local controls closure complete. Explicit CI38085319748 returned
success/none, log blocking-waits/wait-ci-38085319748-20261010T205245Z-160139.log;
no standalone CI-result commit. Resume the tested published waiter from
operations/wait-release-filter-20261010/publication/ops after #417 audit.
Current action: inspect exact-main workflows/test roots and design references,
post the audit plan to #417, add bounded test-only scaffolding on its branch,
then perform one documented Actions dispatch and review real simulator output.
No product fixes; findings go to #417 for Jason/Claude triage.
The transport recovery does not reset the external PR quiet interval.
Publication ID/guards are in persistent publication-commit.txt.
Deduplicate already handled manual runs38079005590/38083089271/38084409144 and
#404–#416 comments/checks; do not re-review or reset quiet time for own events.
For a pending handle:
wait300000ms, write_stdin once with chars="\\n" (echo disabled), repeat until
one-line conclusion. Do not mistake blank input echo for an event.
No liveness checks/second monitor, CI-only commits or quiet resets for own CI.
Handle returned new events; exact-head CI/Native/screenshots before merge.

Owner resumed after historical October9 cutoff. Stop after48h without external
PR events and no open PRs, or an owner stop. Last external PR event:
Claude #416 comment6107086037, 2026-10-11 08:22:16UTC; conditional quiet stop
2026-10-13 08:22:16UTC. Complete #417 first. Own Apple dispatch38084409144 and own CI/comment
do not reset it. Confirm no newer external events/open PRs before completion.
Keep this ledger≤200 lines.
