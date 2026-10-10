# PR415 backend deployment (2026-10-10)

Exact target main: cbc17f4e76f085229c3bdb3c74a5067951b217a6.
Main CI38072318888 passed; reviewed PR415 head d9a05556, approval6100310265,
26 related tests/0.555s and100 focused cache regressions/0.295s passed.
Only production backend code change from f9586f6c is Garmin shot-file atomic
writes for200 data and400 placeholders. This improves reliable cache refresh;
no new end-to-end phone speed claim.

## Resource manifest (before build)

- Owner/session: Codex / codex-pr415-deploy-cbc17f4e-20261010.
- Created2026-10-10 17:39UTC; temporary expiry2026-10-11 17:39UTC.
- Evidence: /home/jason/garmin-ai-caddie-data/operations/pr415-deploy-cbc17f4e-20261010.
- Read-only source: /dev/shm/codex-pr415-deploy-cbc17f4e-20261010.
- API image: garmin-ai-caddie-api:cbc17f4e76f085229c3bdb3c74a5067951b217a6-candidate-20261010.
- Sync image: aicaddie-sync:cbc17f4e76f085229c3bdb3c74a5067951b217a6.
- --rm tests: codex-pr415-cbc17f4e-tests-20261010, no network or named volume.
- Candidate: codex-pr415-cbc17f4e-candidate-20261010, loopback39088, isolated
  SQLite/private volume codex-pr415-cbc17f4e-private-20261010.
- Production: aicaddie-release-cbc17f4e-production-20261010, loopback39055,
  protected existing garmin-ai-caddie_ai-caddie-private volume and DB/network.
- Rollback: aicaddie-release-f9586f6c-production-20261010 retained/stopped only
  after success. Older rollbacks and shared user volumes are protected.
- Credential envfiles: mode0600, /dev/shm/codex-pr415-deploy-cbc17f4e-20261010-*.env,
  removed in finally, never printed or copied into evidence.
- Existing operations/deploy-tools refresh with prior versions retained in
  evidence and source revision pinned to target; cron and ingress unchanged.
- Local .codex-pr415-cbc17f4e-deploy.py control backed up/hash-matched before cleanup.
- No worktree, dependency environment, service exposure, tunnel or agent.

Build both revision-bound images before cutover, verify isolated startup, hold
the existing sync lock across switch/gate, then release it before the manual
incremental sync. Cleanup only exact manifest resources; retain source and
all verification/cutover/sync receipts. Results will be appended on completion.

## Result

Production now runs aicaddie-release-cbc17f4e-production-20261010. API image ID
sha256:337d893f73039d863ada4967012dddbe9d91acda637645fe15ea7779a56b35c5;
sync image ID
sha256:b3e870d74407f0df355087a67ff3dd6718abc62e9f027e503166d20afe77ca64.
Both were built before switch; post-switch and installed sync gates passed.
Startup/switch/gates23.617s. Old f9586f6c stopped and retained for rollback.
Protected private volume/DB/network/ingress remained. Existing deploy-tools
were pinned to cbc17f4e, with prior copies retained in evidence.

The new image's43 related/deployment tests passed/0.969s. Isolated health
reported the exact revision, anonymous history401, authenticated readiness200/
degraded with empty fixture data as expected. Live loopback/public health,
history overview, sync status, three-hole precise prep and topo PNG returned200.
All three holes have ready geometry; server prep6.4467s, cached PNG0.1024s
(678x1060), history0.0631s. These are server probes, not phone loading timings.

One manual incremental sync ran17:51:52→17:52:25UTC/33s. It verified the exact
API/sync revision and finished with sync ok/done. No iOS upload in this slice.

Source archive/provenance verified before cleanup. Snapshot28,319,648bytes,
candidate and labelled disposable volume removed; --rm test container ended.
Production health remains good; protected rollback/user data retained. All
build/test/candidate/cutover/live/sync/tool-backup/cleanup receipts persist.
