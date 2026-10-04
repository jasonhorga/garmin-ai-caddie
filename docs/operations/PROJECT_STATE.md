# Garmin AI Caddie Project State

> Short durable continuity ledger. This is the only authoritative operational
> state file; dated material in `docs/archive/` is historical and non-authoritative.

**Updated:** 2026-10-04 20:22 UTC
**Canonical branch:** `main`
**Product app tip:** `1e1f40a017904ab1f0df22e682c8b089489f5e56`
**Product backend tip:** `048ab6a4b02e9b8d2d81d0d1098cc7cb696f7252` (internal candidate only)
**Current slice:** `RELEASE-MAIN-1E1F40A0` — `done`

## Current status

PRs #375, #376 and #377 are merged and reviewed; their exact-head Source and
Native gates passed, and their source branches are deleted. PR #379 fixed the
live Native test controls and is merged in `main` at `1e1f40a0`; the branch
head used for the successful live Native run was `3dbff39a`.

The release sequence requested for the post-#377 `main` was completed:

- HTTP/2 tunnel throughput: 214,475-byte topology response; loopback about
  0.18 s, tunnel 1.28–2.19 s total, all eight requests HTTP/2/200.
- Live Native Mobile CI `37217499872`: success, `fixture_mode=false`, full
  iOS and Watch live flow, snapshots and secret scans passed.
- Main CI `37223130897`: success at `1e1f40a0`.
- Internal-only iOS TestFlight `37223404885`: final rerun success at
  `1e1f40a0`; the first readiness-timeout attempt was retried after warming
  the candidate service.
- Apple read-only check `37224696705`: success; build 78 is `VALID` and is
  present in the existing internal TestFlight group. No external group contains
  it and external distribution remains disabled.

The shipped internal package is **0.1.0 (78)**. IPA SHA-256:
`1b588fa1b7afd9f84f66c98ebb27258843b8b7821448f95650bdf633899e9201`.
The package points at the candidate origin below; production was not switched.

The existing PR feedback monitor remains the only feedback writer. Do not
start a second monitor or a main-thread polling loop. Do not create a commit
solely to record a CI result; record CI only with real work. The blocking
waiter ignores Codex-generated main-branch events and is active in the
allow-listed tmux session below, waiting only for future events.

## Unfinished work

1. Keep the internal candidate available while build 78 is being tested; do
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
- Release evidence:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/`.
- Native result:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/native-wait-37217499872.result`.
- TestFlight result:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/testflight-wait-37223404885-r2.result`.
- Apple result:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/apple-readonly-wait-37224696705.result`.
- Production remains `aicaddie-release-d7f69971-production-20260925` on
  loopback `39055`.
- The blocking waiter `ops/wait_for_conclusion.sh` has passed local syntax and
  remote synthetic PR-event, timeout and failed-run checks; it returns one
  summary line and stores details in its log directory.

## Owned temporary resources and cleanup

- Candidate source snapshot:
  `/home/jason/codex-runs/garmin-ai-caddie-release-048ab6a4-20261004`.
- Candidate evidence root:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/`.
- Resource manifest:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/resource-manifest.md`.
  It allow-lists only the named candidate container and HTTP/2 tmux for cleanup.
- The candidate container and HTTP/2 tmux are intentionally retained because
  build 78 uses that origin. The PR-feedback waiter is active in tmux
  `codex-pr-feedback-wait-20261004`, with log
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T202208Z-3851321.log`;
  the two older orphan waiters were stopped after this one was verified.
- Systemd user timer `gh-feedback@garmin-ai-caddie.timer` is active; its sole
  writer is `/home/jason/gh-feedback/gh-feedback.sh`. Do not stop or duplicate it.
- Existing local `.codex-*` evidence, manifests and the modified
  `ops/pr_feedback_monitor.sh` are pre-existing session artifacts and remain
  outside this state-only commit.

## Next action and stop conditions

Next action is to leave build 78 available for internal testing and observe
external PR feedback with the existing monitor. No new release, production
switch, or external TestFlight action is authorized in this slice.

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
