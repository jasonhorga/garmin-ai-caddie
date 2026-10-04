# Garmin AI Caddie Project State

> Short durable continuity ledger. This is the only authoritative operational
> state file; dated material in `docs/archive/` is historical and non-authoritative.

**Updated:** 2026-10-04 02:54 UTC
**Canonical branch:** `main`
**Product app tip:** `1d3bca3d94fc60b17440bd5110bb6c35be04cd14`
**Product backend tip:** `a907d1b5bea056a08335fed4955eff12fbf50a9e`
**Release pipeline tip:** `3890c2e09db119b2fddea45a4c7b948caf726ed4`
**Current slice:** `FEEDBACK-TRACKING` — `in-progress`

## Current status

PR #373 is reviewed and merged at exact head `eb63590c58ee687b1b298403fc34b66e899547aa`;
its source branch is deleted. The exact-SHA live Native gate
[37153025859](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/37153025859)
is green, including iOS, Watch, real-simulator flows, design snapshots,
Watch snapshots, secret scan, and build evidence. The accepted app/backend
provenance is `1d3bca3d` / `a907d1b5`.

The build-number safeguard from PR #370 feedback is merged as PR #374 at
`3890c2e0`; Source CI `37159235915` and post-merge main CI `37159674238` are
green. It now fails closed when App Store Connect build lookup fails, so the
Apple agreement blocker cannot silently select build 1.

The internal-only TestFlight workflow `37170793965` succeeded at exact head
`e0e884af`; App Store Connect resolved build **77 before build**, uploaded
`0.1.0 (77)`, and wrote provenance. The read-only Apple check `37171317368`
also succeeded: its log reports build 77 `state=VALID`, and the existing
internal TestFlight group (`internal=true`) lists build 77. External
distribution remains disabled.

Production is unchanged: `aicaddie-release-d7f69971-production-20260925`
on loopback `39055`. Do not switch production or distribute externally in
this slice.

## Unfinished work

1. Use `ops/wait_for_conclusion.sh` for the next CI/release or PR-feedback
   wait; do not resume main-thread polling loops.
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
  `.codex-release-ebe48637-inspect/`, plus dirty review manifests and
  `ops/pr_feedback_monitor.sh`, are preserved as session-owned evidence.
- Persistent monitor: tmux `codex-pr-monitor-20260928`; state and logs are
  under `/home/jason/garmin-ai-caddie-data/operations/pr-feedback-monitor/`.
  No second monitor may be started.

## Next action and stop conditions

Next action is to use the pushed blocking waiter for the next CI/release or
PR-feedback conclusion, then handle only the returned actionable event. Keep
external distribution disabled and do not change production.

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
