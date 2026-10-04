# Garmin AI Caddie Project State

> Short durable continuity ledger. This is the only authoritative operational
> state file; dated material in `docs/archive/` is historical and non-authoritative.

**Updated:** 2026-10-04 06:26 UTC
**Canonical branch:** `main`
**Product app tip:** `9f44574556084ee9a57f43a44424c770e0a76338`
**Product backend tip:** `a907d1b5bea056a08335fed4955eff12fbf50a9e`
**Release pipeline tip:** `3890c2e09db119b2fddea45a4c7b948caf726ed4`
**Current slice:** `FEEDBACK-TRACKING` — `in-progress`

## Current status

PR #375 is reviewed and merged at exact head
`9de2c7f9300dbef85223eaaaafe9cd928f46ff03`, merge `9f445745`; its source
branch is deleted. Source CI `37175590533` and Native Mobile CI `37175590478`
are green. All 87 design snapshots and 44 Watch snapshots were inspected
against the design README and implementation plan with no P1/P2. Review
[5976613647](https://github.com/jasonhorga/garmin-ai-caddie/pull/375#issuecomment-5976613647)
is the authoritative approval.

Feedback deduplication: PR #375 P1 comment `5976330290` (stale labels at
`999770ae`) is resolved by `a8c6d627` / `9de2c7f9`, Claude reply
`5976556856`, and the successful exact-head Native gate. Do not reopen that
failure or treat the superseded `a8c6d627` CI failure as current feedback.
The accepted deployed/release app/backend provenance remains
`1d3bca3d` / `a907d1b5`; the new app tip has not been released.

The internal-only TestFlight workflow `37170793965` succeeded at exact head
`e0e884af`; App Store Connect resolved build **77 before build**, uploaded
`0.1.0 (77)`, and wrote provenance. The read-only Apple check `37171317368`
also succeeded: its log reports build 77 `state=VALID`, and the existing
internal TestFlight group (`internal=true`) lists build 77. External
distribution remains disabled.

The blocking waiter and rule are pushed (`a7657f76`, follow-ups through
`b11b2dba`, rule clarification `51c7d608`, result persistence `ea0cee78`). It owns the wait, ignores
non-terminal CI events, and returns one summary line; do not interleave
main-thread `gh run view`, `ps`, state reads or sleep loops. Next terminal
feedback wait is the only in-progress slice.
Each return atomically replaces `latest-result.txt`; a local timeout test and
remote SHA check passed.

Post-merge main CI `37177482710` is terminal-success for merge `9f445745`;
the deduplicating monitor recorded it before the new feedback waiter started.
State-record commit `e6d01cec` CI `37177808382` also completed successfully
with no failed jobs; its waiter log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T044505Z-3228056.log`.
The following state commit `ee5cadbc` CI `37177962031` completed successfully
with no failed jobs; its exact-run waiter log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37177962031-20261004T045226Z-3266067.log`.
State-record commit `b72f5bad` CI `37178222591` also completed successfully
with no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T045453Z-3285054.log`.
State-record commit `020863d7` CI `37178921114` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T051329Z-3392078.log`.
Documentation commit `f609809a` CI `37179532145` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T052303Z-3450495.log`.
Waiter-state commit `93b07304` CI `37179793477` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T053203Z-3496637.log`.
Attribution-rule commit `b0327a3a` CI `37180150501` completed successfully
with no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T053603Z-3523956.log`.
Waiter-record commit `3be1c2f2` CI `37180351545` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T054150Z-3556377.log`.
Documentation commit `8ea02dd6` CI `37180614551` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T054649Z-3587215.log`.
Documentation commit `2a0350a5` CI `37180851379` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T055218Z-3619718.log`.
Documentation commit `03bc6f43` CI `37181109291` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T055817Z-3652767.log`.
Documentation commit `c05e06bf` CI `37181389348` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T060411Z-3684919.log`.
Documentation commit `ae581d9a` CI `37181697647` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T061038Z-3719441.log`.
Documentation commit `be81223b` CI `37182016314` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T061531Z-3748956.log`.
Documentation commit `dca35bee` CI `37182257018` completed successfully with
no failed jobs; its feedback-wait log is
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T062153Z-3781834.log`.
Waiter implementation commit `ea0cee78` CI `37178724632` completed
successfully with no failed jobs. The new script atomically updated
`latest-result.txt`; log:
`/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T050332Z-3333013.log`.

Production is unchanged: `aicaddie-release-d7f69971-production-20260925`
on loopback `39055`. Do not switch production or distribute externally in
this slice.

## Unfinished work

1. Use `ops/wait_for_conclusion.sh` for the next CI/release or PR-feedback
   wait; do not resume main-thread polling loops.
2. Keep the existing PR feedback monitor running and deduplicate any new
   repository feedback against this ledger; do not start a second monitor.
3. Review new actionable feedback or the next PR on its exact head; require
   relevant tests and successful Native CI with design/Watch artifact review
   for iOS/Watch changes. No pending PR #375 blocker remains.
4. Physical iPhone/Watch evidence remains open now that build 77 is available.

## Live verification baseline

- Native gate: run `37153025859`, all required jobs green.
- Native artifacts:
  `/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/native-37153025859-artifacts/`.
- TestFlight artifact:
  `/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/testflight-37170793965/artifact/`.
  IPA SHA-256:
  `9c960c6d57b9d44b337d0ecac02722507cc580c2d833d6e07c68ca09cba35633`.
- TestFlight CD: `37170793965`; Apple validity/group check: `37171317368`.
- Blocking waiter `ops/wait_for_conclusion.sh` was syntax-checked locally and
  exercised on homeserver with synthetic PR-event, timeout, and failed-run
  cases; each returned one summary line and kept details in its log directory.
- PR #375 exact-head Native `37175590478` and Source CI `37175590533` passed.
  Logs:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37175590478-20261004T040813Z-3003026.log`,
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37175590533-20261004T042825Z-3128761.log`.
  Native artifacts and remote contact sheets:
  `/home/jason/garmin-ai-caddie-data/operations/pr375-9de2c7f9-native-37175590478/`.
  Build evidence records the synthetic PR merge `a351364a` for that run;
  GitHub run head is the reviewed `9de2c7f9`.
- Candidate image/container for the accepted backend:
  `garmin-ai-caddie-api:a907d1b5bea056a08335fed4955eff12fbf50a9e-candidate-20261003`,
  `aicaddie-release-a907d1b5-candidate-20261003`, loopback `39087`.
- Measured candidate ingress:
  `https://bee-famous-payments-household.trycloudflare.com`,
  tmux `codex-release-http2-20261003`; the HTTP/2 tunnel is retained for
  the next gate and is not production traffic.

## Owned temporary resources and cleanup

- Exact release source:
  `/home/jason/codex-runs/garmin-ai-caddie-release-a907d1b5-20261003`;
  created 2026-10-03, seven-day expiry 2026-10-10 unless renewed.
- Release evidence root:
  `/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/`;
  cleanup is pending the Apple unblock and final release decision.
- HTTP/2 ingress manifests:
  local `.codex-release-http2-20261003-manifest.md` and remote
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20261003T2023Z-release-http2.md`.
- Local inspection directories
  `.codex-release-37153025859-inspect/` and
  `.codex-release-ebe48637-inspect/`, `.codex-pr375-999770ae-inspect/`,
  `.codex-pr375-9de2c7f9-inspect/`, plus dirty review manifests and
  `ops/pr_feedback_monitor.sh`, are preserved as session-owned evidence.
- Persistent monitor: systemd user timer
  `gh-feedback@garmin-ai-caddie.timer` is active; its single writer is
  `/home/jason/gh-feedback/gh-feedback.sh`. State and events remain under
  `/home/jason/garmin-ai-caddie-data/operations/pr-feedback-monitor/`.
  Do not start the retired tmux loop or a second writer.
- Blocking feedback waiter: reuse tmux `codex-pr-feedback-wait-20261004`, using
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait_for_conclusion.sh`
  and the existing event stream; it is active and owns the next wait. It
  was restarted at 2026-10-04 05:23 UTC after the prior session exited. It
  expires 2026-10-11 or after its next conclusion is consumed. Its one-line result is written to
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/latest-result.txt`.

## Next action and stop conditions

Next action is to block on the existing monitor's next PR feedback or CI
conclusion, then handle only the returned actionable event. Keep
external distribution disabled and do not change production.

Owner end condition: end this goal no later than **2026-10-09 23:59 UTC**;
it may end earlier after **48 consecutive hours with no new PR event and no
open PR**. Record the final state here before ending the goal.

Stop this slice on any failed required Native/Apple gate, provenance or
revision mismatch, candidate health failure, or request for production or
external distribution. Close temporary resources only through their
allow-listed manifests; never broad-clean shared homeserver state.

## Continuity rule

Keep this file at **200 lines or fewer** and limited to current state,
unfinished work, live verification baselines, owned temporary resources, next
action, and stop conditions. Preserve completed or historical detail
verbatim in a dated file under `docs/archive/` marked
`HISTORICAL ARCHIVE — NON-AUTHORITATIVE`; the archive is not startup
reading. After compaction, follow the recovery sequence in `AGENTS.md` and
do not create a competing plan or continuity file.
