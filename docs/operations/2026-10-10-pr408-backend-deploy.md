# Backend deployment: #408 (2026-10-10)

Deployment requested by Claude in #412 comment6098706732 at14:46:41 UTC,
after confirming Jason's live round ended and the 10:00 UTC hold passed.
Exact target main: `f9586f6c4e2ca20e02a7a72f4543a71a57419e49`.
Main CI38049391237 completed successfully. The only production backend code
change since `b0f64b65` is #408's elevation-aware approach club selection;
the remaining product changes are previously reviewed iOS/Watch code.

## Resource manifest (created before verification/build)

- Owner/session: Codex / codex-pr408-deploy-f9586f6c-20261010.
- Created: 2026-10-10 15:05 UTC; temporary resources expire2026-10-11 15:05 UTC.
- Read-only source snapshot: `/dev/shm/codex-pr408-deploy-f9586f6c-20261010`.
- Persistent evidence: `/home/jason/garmin-ai-caddie-data/operations/pr408-deploy-f9586f6c-20261010`.
- Local orchestration helper: `.codex-pr408-f9586f6c-deploy.py`; persistent copy
  `deployer.py` in the evidence directory. Remove local copy after hash verification.
- A credential envfile is created with mode0600 under `/dev/shm` only while
  creating each API container, then removed in a `finally` block.
- API image: `garmin-ai-caddie-api:f9586f6c4e2ca20e02a7a72f4543a71a57419e49-candidate-20261010`.
- Sync image: `aicaddie-sync:f9586f6c4e2ca20e02a7a72f4543a71a57419e49`.
- Tests container: `codex-pr408-f9586f6c-tests-20261010` (`--rm`, network-none,
  read-only source, disposable tmpfs, shared image environment).
- Startup candidate: `codex-pr408-f9586f6c-candidate-20261010`, loopback39088,
  disposable private volume `codex-pr408-f9586f6c-private-20261010`, isolated SQLite.
- Production target: `aicaddie-release-f9586f6c-production-20261010`, loopback39055,
  existing protected `garmin-ai-caddie_ai-caddie-private` volume and DB/network.
- Rollback: retain `aicaddie-release-b0f64b65-production-20261010` stopped after
  success; restore it automatically if cutover checks fail.
- Existing older rollback, ingress, DB, credential stores and user volumes are
  protected. No new tunnel, service port exposure, dependency environment or agent.
- New API/sync images become deployed resources on successful cutover. Candidate,
  disposable volume, snapshot and local helper are removed only after evidence
  is saved and allow-list targets checked. Never print container env/secrets.

Verification, deployment and cleanup results will be appended here.

Initial verification: 241 related tests ran in3.737s; one failure and five
existing geometry-data skips. `test_a_same_size_rewrite_that_keeps_the_mtime_is_read_again`
observed150.0 rather than151.0. Original log retained as `tests-first-failure.log`.
Cutover has not started. Investigate fixture in-place writes versus the production
atomic writer and real filesystem metadata; do not discard this failure on retry.
Temporary diagnostic container `codex-pr408-cache-writer-probe-20261010` is
`--rm`, network-none, exact image/source, evidence mounted for generated results.
Local helper `.codex-pr408-club-cache-probe.py` will be backed up and removed.

The exact-source diagnostic held file size and restored mtime equal for every
attempt. The fixture's in-place writer returned stale150.0 in3/100 overlay and
13/100 ext4 cases where all metadata stayed identical. The real production
`data.write_json` atomic writer passed100/100 cases on each filesystem, with
identical initial/replacement serialization. This is a nonblocking fixture
defect under the documented atomic-writer contract, not a proven production
sync defect. Feedback to #406 asks for the real writer plus size/mtime/inode
assertions, without sleeps. Keep original failure and diagnostic evidence.
Local feedback body `.codex-pr406-cache-test-followup.md` is also backed up before cleanup.

After this diagnosis, the unmodified241-test suite passed in4.599s (five existing
skips). Candidate health reports the exact revision; anonymous protected history
returns401; authenticated empty-data readiness is degraded as expected. Before
cutover the existing scheduled sync was active: acquire its shared lock once and
block on that lock, then hold it through the API switch/revision gate. Run the
installed sync check after releasing the lock so it cannot silently skip itself.
Refresh the existing pinned deploy-tools copies and SOURCE_REVISION in this
deployment; preserve prior copies in evidence. Local scalar source-revision
file `.codex-pr408-tools-SOURCE_REVISION` is retained remotely before cleanup.

## Deployment and live verification results

Production is now `aicaddie-release-f9586f6c-production-20261010`, loopback39055,
with the exact target revision. API image ID
`sha256:e2122d7980a016d31f968ec73901ed2d49b8a5c8f7047fff9035ad197ba26420`;
matching sync image ID
`sha256:65a7ddef96d1c5219960200fa85020a5602e30e355db1ee80a4b0c3c746b499e`.
Both images were available before switching. Startup and mandatory post-switch
revision gates took32.079s. Installed sync check-only gate verified the new SHA.
The protected private volume, Postgres/network, credentials and ingress remain.

Loopback/public health, protected history overview, sync status, three-hole
precise prep and topo PNG returned200. All three prep holes have geometry ready;
prep5.9045s, cached PNG0.058s (678x1060). These are server probes, not a phone
end-to-end loading benchmark. The previously deployed process-pool/cache speedups
remain; this slice adds #408's slope-aware club choice without a new speed claim.

Manual sync started15:40:40 UTC, verified API/sync revision at15:40:41 and ended
15:41:15 with `sync ok` and `done` (35s). The first verification helper looked
only at the last16 log lines and missed the earlier revision line. A read-only
check of the complete last sync segment confirmed the successful same-revision
run; the helper was corrected. The sync itself was not repeated.

The cached-input fixture follow-up is posted on #406 as comment6099157088.
No iOS/Watch package was uploaded by this deployment; Claude separately reports85.

## Cleanup

Allow-list and receipt: `cleanup-allowlist.json`/`cleanup-result.json` in evidence.
The source archive checksum and lack of open snapshot files were checked first.
Temporary snapshot28,257,897 bytes, isolated candidate and labelled disposable
private volume were removed. --rm test/probe containers ended. Source archive,
tests, initial failure, probe and all verification/cleanup evidence are retained.
Prior b0f64b65 production is stopped/retained for rollback. Older rollback, DB,
user volumes and ingress are protected. No new worktree, preview, tunnel or agent.
Local controls are hash-matched to persistent copies and removed after publication.
