# Backend deployment: #404, #405, #406 (2026-10-10)

Reviewed and merged #404 at `1fd0ad4c`, #405 at `3a093c1c`, and #406 at
`0e17d9ae`. All required backend/frontend/docker CI jobs were green on those
exact heads. PASS comments are `6094057484`, `6094057971`, and `6094058361`.
The shared GitHub identity cannot approve its own PRs, so conclusions were
posted as comments. All three source branches were deleted after merge.

The review queue had paused at the owner's October 9 23:59 UTC cutoff.
The October 10 instruction explicitly resumed it. Delay explanations were
posted on all three PRs before review. The previous terminal state is retained
verbatim in `docs/archive/PROJECT_STATE-2026-10-10-before-resumed-reviews.md`.

## Verification

On homeserver, related tests passed on each PR head: #404 102 tests/3 skips;
#406 132 tests/2 skips; #405 three release-tooling contract tests. The full
#405 workflow suite had three environment errors because the API runtime image
does not contain Git; those tests passed in the required GitHub CI. No new
Native CI was required: this batch changed backend and release tooling only.

After merging, the relevant suites also ran against the combined main source
`b0f64b65fe51af6665e531010d272fc101d203ac` and its newly built image:
**237 tests, 4.107 seconds, OK, five existing geometry-data skips**.

With production data mounted read-only, fresh disposable PNG caches and the
same four-CPU limit, course 43184's first nine holes were measured sequentially
on the prior and new API images. The workloads ran topo rendering and three
three-hole prep batches concurrently. Club profiles were loaded twice before
the mixed workload, so the new profile cache was warm; process workers and
per-hole prep/PNG caches were cold.

| Measurement | Prior 3614bf6f | New b0f64b65 |
| --- | ---: | ---: |
| Nine topo maps + three prep batches, wall | 35.4904 s | 22.9303 s |
| Prep batches | 8.9972 / 7.8312 / 10.5078 s | 4.0731 / 4.9639 / 7.1676 s |
| First club-profile call | 0.6344 s | 0.6892 s |
| Repeated club-profile call | 0.5567 s | 0.0086 s |
| Nine warm PNG reads | 0.0172 s | 0.0456 s |
| Sampled peak container memory | 292.7 MiB | 357.4 MiB |

All nine PNG SHA-256 values match. Two actual render worker PIDs were
observed. This independent measurement is about 35% faster; it does not
reproduce the author's 15-second result. It excludes Garmin acquisition and
phone transfer, and is not a complete cold-course loading-time promise.

## Deployment

- New production API: `aicaddie-release-b0f64b65-production-20261010` on
  `127.0.0.1:39055`, using the existing protected private volume and database.
- API image:
  `garmin-ai-caddie-api:b0f64b65fe51af6665e531010d272fc101d203ac-candidate-20261010`.
  ID `sha256:0d1f306ae1316120764205b74963b65118934cc0291cd3a158d03d2f42154d20`.
- Matching sync image:
  `aicaddie-sync:b0f64b65fe51af6665e531010d272fc101d203ac`.
  ID `sha256:19760d29e05f5bf2305907993f169e3895adeee4b0d9e133f977185ab8d9bf72`.
- `ops/complete_homeserver_api_deploy.sh` built the matching sync image and
  passed. Its check-only rerun and the installed sync wrapper's check-only
  revision gate passed as well.
- The 05:37 scheduled sync skipped while that image was still building.
  Manual incremental sync completed at 05:48:19 UTC with `sync ok` and `done`,
  502 summaries/501 scorecards and no new rounds. The runbook now requires
  prebuilding the matching sync image before API cutover, followed by the
  post-switch gate, to avoid this gap on later deployments.
- Prior API `aicaddie-release-3614bf6f-production-20261008` is stopped and
  retained for rollback. Ingress, database and persistent volumes are retained.
- Startup candidate on 39088 and its disposable private volume were removed
  after health/authenticated-readiness checks. Empty-data readiness was degraded
  as expected. No iOS build was uploaded by this batch.

Detailed source/probe/test evidence and the resource manifest are retained at
`/home/jason/garmin-ai-caddie-data/operations/pr404-406-deploy-20261010`.

Production checks returned HTTP 200 for loopback/public health (both bound to
the deployed revision), sync status, history overview, three-hole precise prep
and topo PNG. History overview took 0.0394 s; precise prep 4.7422 s; the first
requested PNG 6.4232 s. These are server probes after startup, not phone UX
measurements. The first probe supplied a comma-separated hole list and correctly
received 422; the corrected request used repeated `holes` query parameters.

Temporary review/deploy sources were archived and removed under
`source-cleanup.json` (three exact directories, 126,382,305 bytes). Docker-created
test files required an elevated retry for cleanup; the same validated allow-list
and archive checksums were used. No test container/candidate volume remains.
Production health was reconfirmed after cleanup; 55 GiB disk space remains.

A deployment inspection mistakenly printed container credential fields.
Later verification consumes credentials on homeserver and reports only
allow-listed endpoint timing/status data. No credential values are included
in this report or repository evidence.
