# Garmin AI Caddie Project State

> Short durable continuity ledger. This is the only authoritative operational
> state file; dated material in `docs/archive/` is historical and non-authoritative.

**Updated:** 2026-10-03 22:22 UTC
**Canonical branch:** `main`
**Product app tip:** `1d3bca3d94fc60b17440bd5110bb6c35be04cd14`
**Product backend tip:** `a907d1b5bea056a08335fed4955eff12fbf50a9e`
**Current slice:** `RELEASE-EBE48637` — `blocked`

## Current status

PR #373 is reviewed and merged at exact head `eb63590c58ee687b1b298403fc34b66e899547aa`;
its source branch is deleted. The exact-SHA live Native gate
[37153025859](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/37153025859)
is green, including iOS, Watch, real-simulator flows, design snapshots,
Watch snapshots, secret scan, and build evidence. The accepted app/backend
provenance is `1d3bca3d` / `a907d1b5`.

The internal-only TestFlight workflow
`37157174440` built, signed, produced the IPA and provenance, then failed
at Apple upload with `ProgramLicenseAgreementUpdated`: the Apple Developer
program agreement is missing or expired. Read-only build/group query
`37157774570` failed for the same account condition. The IPA and provenance
are retained; no upload completed, no tester was changed, and
`external_distribution=false` remains enforced.

Production is unchanged: `aicaddie-release-d7f69971-production-20260925`
on loopback `39055`. Do not switch production or distribute externally in
this slice.

## Unfinished work

1. Owner/account action: accept or update the missing Apple program agreement.
2. After that external blocker is cleared, rerun the internal-only TestFlight
   workflow at the already green app/backend revisions, then run the
   read-only Apple validity and existing internal-group check.
3. Keep the existing PR feedback monitor running and deduplicate any new
   repository feedback against this ledger; do not start a second monitor.
4. Physical iPhone/Watch evidence remains open after TestFlight becomes
   available.

## Live verification baseline

- Native gate: run `37153025859`, all required jobs green.
- Native artifacts:
  `/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/native-37153025859-artifacts/`.
- TestFlight artifact:
  `/home/jason/garmin-ai-caddie-data/operations/release-ebe48637-20261003/testflight-37157174440/artifact/`.
  IPA SHA-256:
  `c303371db58e090cb7a3e8628adee449845cc4426f561a9f4d08adac019272dd`.
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

Next action is external: clear the Apple agreement blocker. Do not retry
TestFlight or mutate product code while that condition remains. Once cleared,
run the internal-only upload and read-only Apple checks automatically; keep
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
