# Internal TestFlight 0.1.0 (87)

The owner requested an internal iPhone + Watch build from main after #423/#424.
Release source is `bfe850b7dd32fc64dc5a5d5b3c7adc46c8c73eaf`, whose native
product tree matches the reviewed #424 head `5ac993ef` (including #423).
Main ordinary CI `38465815672`, exact-head Native CI `38446895372`, and
five-face production interaction runtime `38453004091` passed before release.

## Release and diagnosis

First release `38525467740` archived Build 87, then failed before upload on
the readiness HTTP request with `Net::ReadTimeout` (`Fastfile:163/170`).
The full terminal log proves a read timeout, not a received non-200 response
as initially inferred in the relay. Retry `38527231865` also archived Build 87 and
received HTTP 200, but failed the full-readiness evidence requirement. Neither
run uploaded a binary; the App Store Connect latest-build query still selected
87 on the successful third attempt.

Authenticated diagnosis used the running API's environment token without
printing it or copying it to local files. Correct loopback origin is
`http://127.0.0.1:9000` inside the API container; the initial 8000-port probe
was refused and provides no service evidence. Correct loopback and public
`https://caddie.taile36706.ts.net` health/readiness both returned HTTP 200 and
the expected backend `cbc17f4e76f085229c3bdb3c74a5067951b217a6`.
Readiness was authenticated, with valid checks, but runtime/service degraded:

- `private_snapshot_acceptance`: explicit acceptance evidence missing.
- `mobile_package`: source, 18/18 geometry, 11 club profiles and 18/18 caddie
  seeds ready; cached weather was missing for the selected historical round.
- `mobile_events`: the container lacks the legacy
  `mobile/contracts/live_round_event.schema.json` file checked by readiness.
  The empty event-kind list is a missing-file check, not a measured endpoint
  execution failure. The image copies `contracts/canonical`, not `mobile`.
- Native, external release, roadmap and operations evidence is incomplete.

Correct loopback/public readiness took 8.352/8.137 seconds. Sync status was
ready initially, transiently degraded during a check, then ready on both
origins after the scheduled sync completed at 07:38:18 UTC with no error.
The deployment-token probe alone did not prove the GitHub secret matched;
the successful release's mandatory authenticated preflight now proves that.

The first two dispatches incorrectly selected full-readiness mode for this
internal validation environment. Third release `38529901074` used the existing
standing internal hardware-validation path documented in
`docs/ios-testflight-setup.md`: `upload_to_testflight=true`,
`test_environment_upload=true`, the public origin above, and the exact
deployed backend revision. This permits degraded operational evidence while
still enforcing authentication, valid check shape, health, origin and revision.
No application, backend, ingress, secret or gate implementation was changed.

## Package and Apple evidence

Release: https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38529901074.
App Store Connect accepted the binary at 07:50:25 UTC; processing finished at
07:52:58 UTC; workflow succeeded at 07:53:07 UTC on 2026-10-14.
Downloaded artifact `11878037725` contains the signed IPA and provenance.
The independent verifier matched source, workflow run, API host, backend,
all upload flags and IPA SHA-256:

`b847f3fdc2c461f176494c732f92a32322b0bdf3da3a3fc313b2bbc782596b0a`

Both actual plists contain version/build `0.1.0 (87)`:

| App | Bundle ID | Evidence |
| --- | --- | --- |
| iPhone | `com.ai-caddie.mobile` | Public API origin configured; no admin-token plist key |
| Embedded Watch | `com.ai-caddie.mobile.watchkitapp` | Companion ID matches iPhone; no admin-token plist key |

Read-only Apple workflow `38532148335` used `operation=list`, version/build
`0.1.0/87`, `external_distribution=false`, and bundle diagnostics. It succeeded.
Apple reports build ID `788b70fe-cc3d-4b81-93cd-60bdd394c30e`, `VALID`,
`expired=false`, `missingExportCompliance=false`, and
`internalState=IN_BETA_TESTING`. The existing internal all-builds group
explicitly includes 87; the external group does not. The helper reports
`internalReady=false`; the actual beta state and group/build relationship are
the evidence of current internal availability. Apple bundle diagnostics
reported the processed phone bundle; the embedded Watch is independently
verified in the actual IPA. No tester/group mutation or external distribution
was performed.

Apple run: https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/38532148335.

## Device handoff and resources

On this exact build the owner must still verify Crown score-row selection;
45-minute stationary idle pause and workout/GPS shutdown; accidental quit
and relaunch within 30 minutes; Watch second-nine selection/replacement
following on the phone; and tee-result preselection after a second shot on
either device. Simulator, archive and Apple checks do not prove those physical
behaviors or successful installation on a particular device.

Persistent evidence and control backups:
`/home/jason/garmin-ai-caddie-data/operations/release87-20261014`.
Full terminal logs remain under `operations/blocking-waits/`:
`wait-release-38529901074-20261014T074526Z-418229.log` and
`wait-ci-38532148335-20261014T080622Z-456173.log`, with the two earlier
failure logs also preserved. Diagnostic/package scripts use existing Python;
no dependency environment, container, volume, service, tunnel, port or worktree
was created. Temporary local release controls are backed up with checksums
and closed; only persistent release evidence remains. Feedback waiter terminal
17035 is retained for the original continuous-review goal.
