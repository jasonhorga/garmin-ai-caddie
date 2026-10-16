<!-- HISTORICAL ARCHIVE — NON-AUTHORITATIVE -->
# PR424 production IA review — in progress

Current production head: `9995abfc8de68a1aceaa99c81dd387956e91c682`.
Original finding head: `6eef9e13cfe191e2668dfd41cd80c5c94a6e9e97`.
Harness branch: `codex/pr424-production-harness-20261013`, commit `54a3153e`.
Runtime `38393954768` was dispatched for the prior source head; a new five-face
runtime will be dispatched after Native CI for `9995abfc` is green. The harness
remains test-only.
No product fixes, release, or merge approved in this slice.

## P2: same-round phone reseeding drops second-nine editability

`WatchRoundModel.applyRoundSeed` retains the extended Watch loop key and holes
but constructs a fresh `PersistedRound` without `secondNineAddedAtTurn`. The
normal one-nine phone seed therefore clears the new provenance flag, making
`canChangeSecondNine` false while the second nine remains unplayed. Phone
active-hole selection and activation both send these seeds. The regression
expects editability to survive; execution is pending in the runtime run.
PR comment: https://github.com/jasonhorga/garmin-ai-caddie/pull/424#issuecomment-6144359659
Claude fixed the identity-preserving prefix case at `f3766024`, retaining the
persisted provenance flag. Source review confirms the fix; both the retained
editability and dropped-nine stale-seed regressions still await native execution.

## Verification and evidence boundaries

Remote preflight: 149 targeted Python tests passed (11 collector, 126 mobile
contracts, 12 native visual parity), using the existing release image, no install.
Ordinary CI `38382863189` and Native `38382863562` passed on this PR revision.
Native Watch log records 470 unit tests and 2 UI tests, zero failures.

The Native artifact checkout is GitHub's merge candidate `0c757522`, parents
`ee1870b1` and `6eef9e13`. It includes the already merged PR423 idle-pause
changes as well as the PR424 head; it is not byte-identical to the standalone
PR head. The test-only runtime branch is based directly on `6eef9e13` and adds
only explicit DEBUG fixture routing and audit tests/collection.

Downloaded and inspected all 47 Watch snapshots against the approved design
and #422 B layout: 31 match the prior reviewed PR423 image bytes, 16 changed.
The 97 phone snapshots all match the prior reviewed PR423 image bytes. The new
score rows/sheet fit in their design canvases; ImageRenderer evidence does not
prove Watch clock overlays, first-tap hit delivery, Crown, or scrolling.
Those remain the pending five-face runtime acceptance checks.

Prior-head ordinary CI `38389567724` and Native `38389567637` passed. New-head
ordinary CI `38396582897` passed; Native `38396582952` was queued while this
review was updated.
All 47 Watch and 97 phone images in those freshly downloaded artifacts match the
already inspected `6eef9e13` set byte-for-byte. Native build evidence identifies
merge candidate `90ee8d53`; it is distinct from standalone `f3766024`. Comparison
receipt: `native-comparison-f3766024.json` in the persistent evidence directory.
The corrected harness carries the exact `f3766024` product head, with only DEBUG
fixture/test/collection changes (the file inventory is recorded in Git).

Initial runtime `38388376104` executed zero control trials: the added DEBUG
trace escaped a quote inside Swift interpolation incorrectly. The log and 46 mm
failure artifact are retained in operations; the correction is `f7073470`.
That failed harness build supplies no product interaction verdict.

Second attempt `38390603419` compiled all five faces but stopped before tests at
an unbound `AUDIT_FACE` variable. The corrected workflow puts it in job-level
environment and preserves failure status during video cleanup. Zero controls
were executed in that attempt. Its 46 mm artifact is retained at
`failed-attempt-2/watch-audit-46mm`; it supplies no product interaction verdict.
The corrected-base remote preflight again passed all 149 targeted Python checks.
Stale feedback run `38366800596` belongs to old PR head `3570e9c`, so it does not
supersede the current-head green Native result or justify another author request.

## P2: Watch turn-table changes do not reach the already active phone — addressed, pending exact-head verification

On `f3766024`, `applySecondLoop` and `dropSecondNine` persist only on Watch.
`AICaddieWatchApp` emits its round-start identity only at initial course start.
The iPhone's `handleWatchRoundStart` also returns for an existing same-round
package before examining the new loop key/hole table. Thus an offline Watch
A→A+B turn, B→C replacement, or drop leaves the phone's current table unchanged.
The existing input-event payload cannot communicate that topology change.
An old full-pair phone seed can also overwrite the new Watch pair. This needs
durable, ordered same-round table reconciliation, not another creation message.
Source-path finding only; physical WCSession delivery is not measured here.

Claude added `tableRevision`/`tableAwaitingPhone`, the persisted Watch relay,
same-round phone reconciliation, and regressions in `9995abfc`. Source review
confirms the normal add/replace/drop and stale-table echo path. The phone's
retry-on-failed-reconciliation path remains a separate P2: it records a revision
before the async `setSecondLoop` succeeds, so a failed offline fetch can suppress
later delivery of the same revision until relaunch (comment `6145599208`).
This does not clear the finding until a retry regression or equivalent success
acknowledgement exists.

The reverse echo is also not revision-qualified: Watch add B(r1), replace
C(r2), replace B(r3), then delayed phone seeds B(r1) followed by C(r2) can
clear the awaiting flag at the old matching B key and restore stale C. The
phone seed schema carries no acknowledged table revision. Key equality alone
cannot prove that the phone applied the current choice. Source-order finding;
the requested regression includes relaunch and the final B(r3) acknowledgement.

Persistent evidence:
`/home/jason/garmin-ai-caddie-data/operations/pr424-6eef9e13-20261013`.
The evidence manifest records temporary snapshot, containers, and local image
copy lifetime. Contract/graphics containers use `--rm`; no service, tunnel,
port, volume, or dependency environment was created.
