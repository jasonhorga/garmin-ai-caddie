# Garmin AI Caddie Project State

> Short durable continuity ledger. This is the only authoritative operational
> state file; dated material in `docs/archive/` is historical and non-authoritative.

**Updated:** 2026-10-03 14:50 UTC
**Canonical branch:** `main` (this ledger is updated by docs-only commits)
**Product tip under release:** `a907d1b5bea056a08335fed4955eff12fbf50a9e`
**Current slice:** `RELEASE-EBE48637` — `in-progress`

## Current status

The merged B1–B7 UI queue (PRs #359–#371) is closed; PR #371 was reviewed at
exact head `cfc4c3a3f6a473562cc290bf4b3b8a76bf9de054` and squash-merged as
`a907d1b5`. Production is unchanged: `aicaddie-release-d7f69971-production-20260925`
on loopback `39055`. No production switch or external distribution is allowed
by this slice.

The exact-SHA full live Native run [37126990984](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/37126990984)
completed `failure` at `a907d1b5`. Source/app target, design snapshots, Watch
target/snapshots, Watch real screenshots, secret scans and evidence uploads
passed. The only failing step was iOS real-simulator screenshots:

- `RealFlowUITests.testBackNineThenFrontNineJourney`: after the turn it still
  observed the wrong course hole (`course hole 1` assertion failed).
- `RealFlowUITests.testCaptureRealAppFlow`: live
  `/api/v2/history/rounds/17711803/holes/3/shotmap` timed out.

Evidence is retained at
`/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/native-37126990984.log`
and `native-37126990984-artifacts/`; the 127 MB real-video artifact was not
downloaded. TestFlight upload has **not** started and remains gated on a green
exact-SHA Native run.

Candidate preflight for `a907d1b5` passed: local/public health returned the
exact revision, authenticated mobile stats and round `15043724` package passed,
geometry was `18/18 ready`, and the B7 swing-candidates probe returned 201.
Readiness is HTTP 200/degraded only for pre-existing Garmin evidence gaps.
PR #371 focused homeserver suites passed `230/230` in `13.490s`; log hash is
`8c4bba838e4990a4df16fc15940e184c6e841d6c4956e8a2897aa0cde8716f49`.

## Unfinished work

1. Diagnose the two live iOS failures above, determine whether a product fix or
   live-data/test flake is responsible, and record evidence on the relevant PR
   before dispatching one new exact-SHA Native gate.
2. Only after that gate is green, run the automatic internal-only TestFlight
   upload and Apple validity/internal-group read-only check. Keep
   `external_distribution=false`; physical iPhone/Watch evidence remains open.
3. Continue the existing PR comment monitor, deduplicating feedback against
   this ledger. No open B1–B7 PR is currently known.

## Live verification baseline

- Production: `39055`, revision `d7f69971`; do not mutate in this slice.
- Release candidate image:
  `garmin-ai-caddie-api:a907d1b5bea056a08335fed4955eff12fbf50a9e-candidate-20261003`,
  digest `sha256:1878966396b4cf757371757abda09391d8a5abf7b614192a501e148a40becd00`.
- Candidate container: `aicaddie-release-a907d1b5-candidate-20261003`,
  `127.0.0.1:39087`; its private data volume and database network are protected.
- Candidate tunnel:
  `https://refine-registration-collector-wednesday.trycloudflare.com`, tmux
  `codex-release-ebe48637-tunnel-20261003`, forwarding `39087`.
- Exact source archive:
  `/home/jason/codex-runs/garmin-ai-caddie-release-a907d1b5-20261003`.
- Focused-test log:
  `/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/pr371-cfc4c3a3-focused-tests.log`.

## Owned temporary resources and cleanup

- Review snapshot `/dev/shm/codex-pr371-cfc4c3a3-20261003`; read-only,
  expires 2026-10-04 12:33 UTC; manifest
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20261003T123300Z-pr371-cfc4c3a3-review.md`.
- Release source above: created 2026-10-03, seven-day expiry 2026-10-10 unless
  explicitly renewed. Old `ebe48637` source is retained only for audit until
  the release gate cleanup is recorded.
- Evidence root:
  `/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/`.
  Release manifest
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20261003T1318Z-release-a907d1b5.md`
  still needs its complete ownership/expiry/cleanup entries.
- Persistent PR monitor: tmux `codex-pr-monitor-20260928`; script,
  `state.json`, and log are under
  `/home/jason/garmin-ai-caddie-data/operations/pr-feedback-monitor/`.
  Do not start a second monitor.
- Local dirty review manifests, `ops/pr_feedback_monitor.sh`, and
  `.codex-release-ebe48637-inspect/` predate this slice; preserve them.

## Next action and stop conditions

Next: post/track the exact failure evidence, then make or request the smallest
in-scope correction and rerun the Native gate at the resulting exact SHA.
Complete the release only after Native is fully green, TestFlight Apple checks
are recorded, and physical-device evidence is handed off. Close resources only
through allow-listed manifests; do not broad-clean shared homeserver state.

Stop the release slice on any failed required Native/Apple gate, revision or
provenance mismatch, candidate health failure, or request for production or
external distribution. Escalate only a genuine product/release decision; do not
pause for routine CI polling or internal TestFlight execution.

## Continuity rule

Keep this file at **200 lines or fewer** and limited to current state,
unfinished work, live verification baselines, owned temporary resources, next
action, and stop conditions. At each meaningful update, preserve completed and
historical detail verbatim in a dated `docs/archive/` file marked historical
and non-authoritative; never delete information. The archive is not startup
reading. After compaction, follow this file's recovery sequence in `AGENTS.md`
and do not create a competing plan or continuity file.
