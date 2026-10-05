# Garmin AI Caddie Project State

> Short durable continuity ledger. This is the only authoritative operational
> state file; dated material in `docs/archive/` is historical and non-authoritative.

**Updated:** 2026-10-05 06:59 UTC
**Canonical branch:** `main`
**Latest main tip:** `7f2d3764` (PR #381 review evidence recorded)
**Product app tip:** `3f05ca689b0ca4988bfcc404f9fe3ba446d6727c` (requested release source)
**Product backend tip:** `048ab6a4b02e9b8d2d81d0d1098cc7cb696f7252` (internal candidate only)
**Current slice:** `PR-382-REVIEW` — `evidence-open`

## Current status

The owner requested an internal-only release from latest `main` including
#375/#376/#377, in order: HTTP/2 speed, live Native, TestFlight, Apple read-only.
The release source was app tip `3f05ca689b0ca4988bfcc404f9fe3ba446d6727c`;
the healthy `048ab6a4`
candidate and tunnel were reused. All required gates passed and build 79 was
uploaded to the existing internal TestFlight group. Production and external
distribution were unchanged.

PRs #375, #376 and #377 are merged and reviewed; their exact-head Source and
Native gates passed, and their source branches are deleted. PR #379 fixed the
live Native test controls and is merged in `main` at `1e1f40a0`; the branch
head used for the successful live Native run was `3dbff39a`.
PR #380 was reviewed at exact head `677a76bd40611b5046b3ab2f1695e640d73f5bb8`.
Native Mobile CI `37267563159` and Source CI `37267563158` passed; the 89 iOS
and 47 Watch snapshot artifacts were downloaded and checked against the UI
redesign README/plan. The review comment is
`https://github.com/jasonhorga/garmin-ai-caddie/pull/380#issuecomment-5988944913`.
It merged at `bb7c8565ce7877023a23bd7a4ff5985ba11dc021` and its remote branch
was deleted.
PR #381 fixed two real feedback-wait gaps: `--feedback` now resumes from an
atomic line cursor, and provenance filtering distinguishes Codex trailers from
Claude's shared GitHub identity. Exact head `ddf5406bf4d76c0c24da60ce590292042a65af1`
passed Source CI; real-stream cursor and commit-provenance tests passed on the
homeserver. The review comment is
`https://github.com/jasonhorga/garmin-ai-caddie/pull/381#issuecomment-5989088276`.
It merged at `1b709a815b7a79d9bb8e9763f914c88d0ed26629` and its remote branch
was deleted.

PR #382 is open at exact head `df69ca9ebd1fd74f99c89aa71669193e79861f3c`.
Source CI `37271834177` and Native Mobile CI `37271834164` passed. The Native
artifact contains 89 iOS and 47 Watch snapshots; all 136 PNG hashes match the
corresponding #380 snapshots (the two prior contact sheets are the only extra
files). Review evidence is retained at
`/home/jason/garmin-ai-caddie-data/operations/pr382-native-37271834164-20261005/`.
The review found one P2 blocker: `recentRows` deduplicates by localized display
strings instead of stable `course.globalId`, so distinct courses can collapse
or localization changes can duplicate a course. Review and clarification are
posted at
`https://github.com/jasonhorga/garmin-ai-caddie/pull/382#issuecomment-5989666689`;
do not merge until the fix and regression test are reviewed.

PR #383 remains open and blocked by the owner decision not to change the
same-turn feedback-wait method before 2026-10-09; its P1 comment is
`https://github.com/jasonhorga/garmin-ai-caddie/pull/383#issuecomment-5989315293`.

The release sequence for this exact main was completed:

- HTTP/2 tunnel throughput: 214,475-byte topology response; loopback about
  0.18 s, tunnel 1.28–2.19 s total, all eight requests HTTP/2/200.
- Live Native Mobile CI `37257466397`: success, `fixture_mode=false`, full
  iOS and Watch live flow, snapshots and secret scans passed.
- Internal-only iOS TestFlight `37262234670`: success at this exact main;
  upload used `test_environment_upload=true`, `external_distribution=false`.
- Apple read-only check `37262917624`: success; build 79 is `VALID`,
  `IN_BETA_TESTING`, unexpired, and present in the existing internal group.
  No external distribution was requested.

The shipped internal package is **0.1.0 (79)**. IPA SHA-256:
`82d7077351a8eb079026469ef068d9f8d3929022a486371d0ecacbe61427cdb8`.
The package points at the candidate origin below; production was not switched.

The existing PR feedback monitor remains the only feedback writer. Do not
start a second monitor or a main-thread polling loop. Do not create a commit
solely to record a CI result; record CI only with real work. Feedback waits
must run in the same control turn through one background-terminal handle and
be observed in five-minute cycles until the waiter prints its one-line result;
the old independent tmux waiter is no longer used. The waiter ignores
Codex-generated main-branch events.

## Unfinished work

1. Keep the internal candidate available while build 79 is being tested; do
   not switch production or enable external distribution.
2. Physical iPhone/Watch evidence is still open for the internal build.
3. When the owner ends this slice, clean the candidate container and tunnel
   through their allow-listed manifests; keep evidence and the image until the
   release decision is closed.

## Live verification baseline

- Candidate health: HTTP 200, revision `048ab6a4…`.
- Candidate image/container: `garmin-ai-caddie-api:048ab6a4b02e9b8d2d81d0d1098cc7cb696f7252-candidate-20261004`,
  `aicaddie-release-048ab6a4-candidate-20261004-r2`, loopback `39088`.
- Candidate origin: `https://purple-vegetation-downtown-colon.trycloudflare.com`.
- HTTP/2 tmux: `codex-release-http2-main-048ab6a4-r2`.
- Release evidence root:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-3f05ca68-20261005/`.
- Native wait log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37257466397-20261005T030439Z-1636881.log`.
- TestFlight wait log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-release-37262234670-20261005T040901Z-1967339.log`.
- Apple read-only wait log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37262917624-20261005T041828Z-2026802.log`.
- PR #380 Native review artifacts and visual-audit evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr380-native-37267563159-20261005/`;
  review snapshot expiry is 2026-10-06 05:48 UTC.
- PR #382 Native review artifacts and visual-audit evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr382-native-37271834164-20261005/`;
  review snapshot expiry is 2026-10-06 06:59 UTC.
- Production remains `aicaddie-release-d7f69971-production-20260925` on
  loopback `39055`.
- The blocking waiter `ops/wait_for_conclusion.sh` has passed local syntax and
  remote synthetic PR-event, timeout and failed-run checks; it returns one
  summary line and stores details in its log directory.
- The homeserver waiter copy is synced to the merged main script, SHA-256
  `5b3846c9ff7b4ad6a5297f5571fa162c8e0be5a50ee63da024d6ef11be038c6d`;
  feedback cursor: `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/feedback-cursor`.

## Owned temporary resources and cleanup

- Candidate source snapshot:
  `/home/jason/codex-runs/garmin-ai-caddie-release-048ab6a4-20261004`.
- Candidate evidence root:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/`.
- Resource manifest:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/resource-manifest.md`.
  It allow-lists only the named candidate container and HTTP/2 tmux for cleanup.
- The candidate container and HTTP/2 tmux are intentionally retained because
  build 79 uses that origin. The independent PR-feedback tmux waiter
  `codex-pr-feedback-wait-20261004` was stopped; its log remains at
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T202208Z-3851321.log`
  for audit history. Future feedback waits are same-turn resources and must
  be closed when their result is consumed.
- Systemd user timer `gh-feedback@garmin-ai-caddie.timer` is active; its sole
  writer is `/home/jason/gh-feedback/gh-feedback.sh`. Do not stop or duplicate it.
- Existing local `.codex-*` evidence, manifests and the modified
  `ops/pr_feedback_monitor.sh` are pre-existing session artifacts and remain
  outside this state-only commit.

## Next action and stop conditions

Next action: owner performs physical iPhone/Watch validation of internal build
79; when PR feedback arrives, launch the same-turn blocking waiter described
in `AGENTS.md`. Keep the candidate origin available until that handoff closes;
no production switch, external distribution, or tester mutation is authorized.

Owner end condition: end this goal no later than **2026-10-09 23:59 UTC**;
it may end earlier after **48 consecutive hours with no new PR event and no
open PR**. Record the final state here before ending the goal.

Stop on any failed required Native/Apple gate, provenance or revision mismatch,
candidate health failure, or request for production/external distribution.
Close temporary resources only through their allow-listed manifests; never
broad-clean shared homeserver state.

## Continuity rule

Keep this file at **200 lines or fewer** and limited to current state,
unfinished work, live verification baselines, owned temporary resources, next
action, and stop conditions. Preserve completed or historical detail verbatim
in a dated file under `docs/archive/` marked
`HISTORICAL ARCHIVE — NON-AUTHORITATIVE`; the archive is not startup reading.
After compaction, follow `AGENTS.md` recovery; do not create a competing plan
or continuity file.
