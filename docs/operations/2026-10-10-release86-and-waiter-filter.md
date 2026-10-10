# TestFlight86 verification and release-event filtering

The feedback waiter discarded the failed TestFlight run38079005590 because
its head carried Codex's commit trailer. This provenance describes who changed
the source; it does not make a manually dispatched release outcome ordinary CI.
The explicit release waiter recovered the failure. Build86 had archived and
exported successfully, but backend preflight failed with TLS unexpected EOF
before upload. Claude had already dispatched retry38083089271; no second
upload was started by Codex.

## Corrected event handling

The waiter now reads workflowName and event from the actual Actions run before
filtering. Terminal workflow_dispatch outcomes for iOS TestFlight (CD),
iOS TestFlight Testers and iOS TestFlight Artifact Diagnostics remain actionable
on Codex or unmarked bookkeeping heads. The exception also applies to a terminal
PR check summary containing one of those real runs. An event's claimed workflow
does not grant the exception. Ordinary CI and manually dispatched Native Mobile
CI on Codex heads remain suppressed. Explicit --run/--release behavior, the
production event stream, cursor and shared monitor are retained.

Homeserver verification used the actual Bash waiter with isolated mocked GitHub
fixtures: **15 tests /12.740s, OK, no skips**, plus bash -n. The tests cover failed
TestFlight outcomes including the failed job/log path, Apple on a bookkeeping
head, terminal-only delivery, untrusted stream metadata, persistent cursor
advancement, and continued self-run/check-summary suppression.

Command: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
-p test_wait_for_conclusion_provenance.py -v. Exit0. No dependencies installed.
The34520-byte read-only snapshot was removed after source backup comparisons and
cwd/open-descriptor checks. No containers, volumes, services, ports or tunnels.

## Uploaded package

Retry38083089271 completed successfully at2026-10-10 20:27:19UTC, exact
main b662572e55b5262f285fc19c284ca30358915d8d. The upload log confirms successful
App Store Connect upload at20:24:35UTC and processing completion at20:27:08UTC.
The downloaded AICaddie-ipa artifact11680579635 contains provenance matching
the source/run, backend cbc17f4e76f085229c3bdb3c74a5067951b217a6 and
uploadCompleted=true. Its IPA SHA-256 independently matches:

`c59ca85eb527443306d1f49462c8b2c09ac2ecaa2fbebf08ed66dbec0affb4e9`

Both actual package plists show0.1.0(86). Phone bundle com.ai-caddie.mobile;
embedded Watch bundle com.ai-caddie.mobile.watchkitapp; companion ID matches.
The release lane specifies distribute_external=false. This inspection does not
establish a successful installation or physical Watch GPS/battery behavior.

Apple read-only run38084409144 was dispatched on the same head with operation=list,
app_version=0.1.0, build_number=86, external_distribution=false and bundle
diagnostics enabled. It completed successfully at20:37:04UTC. Apple reports
build86 VALID, expired=false, missingExportCompliance=false and
internalState=IN_BETA_TESTING. The existing internal all-builds group explicitly
contains86; the external group does not. Apple-processed bundle metadata includes
the actual iPhone and embedded Watch executable entitlements. The diagnostic
internalReady=false value is preserved in the full log; the decisive distribution
evidence is IN_BETA_TESTING and the existing internal group's build relationship.
The exact CI dependency fastlane2.240.1 implements that helper as
internal_build_state == READY_FOR_BETA_TESTING, so an already testing build
returns false. Its source is retained with the evidence.
This does not establish a particular device's successful installation.

Loopback/public health remained200/ok on exact backend cbc17f4e after cleanup.
Neither the backend nor ingress was redeployed by this operation.

Persistent evidence, scripts, release artifact and cleanup receipts:
/home/jason/garmin-ai-caddie-data/operations/wait-release-filter-20261010.
Explicit retry log:
blocking-waits/wait-release-38083089271-20261010T202711Z-130634.log.
Apple read-only log:
blocking-waits/wait-ci-38084409144-20261010T203723Z-143537.log.
SSH orphan recovery receipts remain in feedback-recovery-20261010T2010.

Publication uses a fresh-main alternate Git index and commit provenance guards;
the shared checkout's source, HEAD and normal index are preserved. Run the tested
published waiter from this operation's persistent publication/ops path until
the shared canonical checkout is normally updated by its owner. Do not record
subsequent own CI conclusions in standalone bookkeeping commits.

Five local editing/control scripts and comment files10405bytes are closed under
the exact allow-list after matching persistent backup hashes and a clear fuser
check. Their manifest and backups remain audit evidence; unrelated older local
controls are retained. #416 release reply6102006509 is already handled.
