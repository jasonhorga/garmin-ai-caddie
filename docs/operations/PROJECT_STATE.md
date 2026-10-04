# Garmin AI Caddie Project State

> Short durable continuity ledger. This is the only authoritative operational
> state file; dated material in `docs/archive/` is historical and non-authoritative.

**Updated:** 2026-10-04 11:15 UTC
**Canonical branch:** `main`
**Product app tip:** `ab0d859a9a8d3887082c771327d42be578222f64`
**Product backend tip:** `a907d1b5bea056a08335fed4955eff12fbf50a9e`
**Release pipeline tip:** `3890c2e09db119b2fddea45a4c7b948caf726ed4`
**Current slice:** `FEEDBACK-TRACKING` — `in-progress`

## Current status

PR #375 is reviewed and merged at exact head `9de2c7f9`, merge `9f445745`; its
source branch is deleted. Source/Native CI `37175590533`/`37175590478` are
green; 87 iOS and 44 Watch snapshots had no P1/P2.

PR #376 is reviewed and merged at exact head `b73d98c1341fdf09584d49bb976201738a536d53`,
merge `1387e30d90b2e219a7fadd23cbcbc42a58bc13a2`; source branch is deleted.
Source CI `37191213933`, Native CI `37191213999`, and post-merge main CI
`37193169603` are green. Exact artifacts contained 88 iOS and 47 Watch images;
87 prior iOS and all 47 Watch images were byte-identical, with only the expected
`full-home-no-package.png` added. Review conclusion:
[5978632335](https://github.com/jasonhorga/garmin-ai-caddie/pull/376#issuecomment-5978632335).

PR #377 is reviewed and merged at exact head `4d23e042c0e3013685b88d8cd382cf10de23f6c7`,
merge `ab0d859a9a8d3887082c771327d42be578222f64`; its source branch is deleted.
Source CI `37195932538`, Native CI `37195932557`, and post-merge main CI
`37197802271` are green. The exact Native artifact has 89 iOS and 47 Watch
snapshots; only `full-home-active-no-package.png` was added versus the prior
head. The active-round/no-package P2 is resolved by `HubInProgressLoadingCard`
and its snapshot/contract coverage. Review conclusion:
[5979316749](https://github.com/jasonhorga/garmin-ai-caddie/pull/377#issuecomment-5979316749).

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
main-thread `gh run view`, `ps`, state reads or sleep loops. The waiter now
checks run head/provenance and ignores Codex's own docs/state-only CI events;
the owner-directed stop remains recorded below.
Each return atomically replaces `latest-result.txt`; a local timeout test and
remote SHA check passed.

Owner-requested live release gate `37185535082` at exact head `2417948a` failed
in real iOS flow (start-round path assertion and round `17711803` hole-3
shotmap timeouts); no TestFlight upload was started. Failure comment:
`5978304683`; waiter log `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37185535082-20261004T072243Z-4113818.log`.
Production is unchanged: `aicaddie-release-d7f69971-production-20260925`
on loopback `39055`. Do not switch production or distribute externally in
this slice.

## Unfinished work

1. Keep Codex's blocking waiter stopped for self-generated docs/state-only CI;
   use it only for an external or real-work PR/release conclusion. Do not make
   a commit solely to record a CI result; record it only with real work.
2. Keep the existing PR feedback monitor running and deduplicate any new
   repository feedback against this ledger; do not start a second monitor.
3. Physical iPhone/Watch evidence remains open now that build 77 is available.

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
  Native artifacts: `/home/jason/garmin-ai-caddie-data/operations/pr375-9de2c7f9-native-37175590478/`.
  Waiter logs are retained under `operations/blocking-waits/`.
- PR #376 exact-head artifacts and evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr376-native-b73d98c1-20261004/`;
  Native waiter log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37191213999-20261004T092059Z-548197.log`;
  post-merge CI log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-feedback-pr--20261004T094734Z-684277.log`.
- PR #377 exact-head artifacts and evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr377-native-4d23e042-20261004/`;
  Native waiter log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37195932557-20261004T104546Z-978246.log`;
  post-merge CI log:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait-ci-37197802271-20261004T111113Z-1096361.log`.
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
  `.codex-pr375-9de2c7f9-inspect/`, `.codex-pr376-b73d98c1-inspect/`,
  `.codex-pr377-4d23e042-inspect/`, plus dirty review manifests and
  `ops/pr_feedback_monitor.sh`, are preserved as session-owned evidence.
  Review manifests: `.codex-pr376-b73d98c1-review-manifest.md`,
  `.codex-pr377-4d23e042-review-manifest.md`.
- PR #377 Native artifact is retained under
  `/home/jason/garmin-ai-caddie-data/operations/pr377-native-4d23e042-20261004/`;
  its cleanup manifest is
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20261004T1115Z-pr377-native-4d23e042.md`.
- Persistent monitor: systemd user timer
  `gh-feedback@garmin-ai-caddie.timer` is active; its single writer is
  `/home/jason/gh-feedback/gh-feedback.sh`. State and events remain under
  `/home/jason/garmin-ai-caddie-data/operations/pr-feedback-monitor/`.
  Do not start the retired tmux loop or a second writer.
- Blocking feedback waiter `codex-pr-feedback-wait-20261004` was stopped at the
  owner's direction after the docs-only CI loop; no Codex waiter is active.
  Reuse it only for an external or real-work conclusion. Native gate
  `codex-native-2417948a-20261004` also ended after run `37185535082` failed;
  its one-line result is retained under `native-2417948a-result.txt`.

## Next action and stop conditions

Next action is to keep release stopped pending the owner/Claude fix for the
Native live-flow failures, while the existing monitor observes external PR
feedback. Keep TestFlight/external distribution disabled and do not change production.

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
reading. After compaction, follow `AGENTS.md` recovery; do not create a
competing plan or continuity file.
