# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived 2026-10-09 19:55 UTC before PR402 review. Prior ledger preserved verbatim.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 19:06 UTC
**Canonical branch:** `main`; latest integrated product code
`2502a0c99dc76aa1b8eb70aade01b891124508f5` (#401 merge)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state

#401 is MERGED (19:04:19 UTC), branch `claude/speculative-prefetch-20261009`
deleted by successful GitHub ref DELETE. PASS comment **6087423825**.
Exact reviewed head `bd8575ea65665b659dc21f165d641a283835f365`;
merge `2502a0c99dc76aa1b8eb70aade01b891124508f5`.

All prior P2/evidence gaps closed:
- Actual dequeue requires fresh measured space for one course; pending-row
  reservations are deducted only when adding rows. Unknown/stale/cap-edge/exact
  one-course selector regression passes.
- New measurement wakes existing queued guesses; worker requests a remeasurement
  after another download makes its old capacity measurement invalid.
- Preparing a round gates actual automatic dequeue/preemption.
- New settings toggle screenshot manually passed at `1ce1dd09`; latest image
  identical, default off, full label/two-line footer/system List.

Final evidence:
- Independent homeserver contracts: **126/126, 12.273 s, OK**.
- CI `37973756337`: all green. Native `37973756093`: live production
  evidence; iOS **759/0**, Watch **448/0**. New actual selector regression
  explicitly passed in Native log.
- Native evidence `daa634ebfdf2dcc4d2725eedd976e9cfa1b55f90` parents
  are main `b3574459` and the exact reviewed head.
- **142/142** design/Watch PNGs byte-identical to latest reviewed baseline.
- Evidence at
  `/home/jason/garmin-ai-caddie-data/operations/pr401-bd8575ea-20261009`:
  source tar, contracts, Native logs/artifacts/provenance/hash comparison, PASS,
  merge request, manifest and cleanup log. Prior-head evidence retained.

Nonblocking follow-up in PASS: if another write ends during a storage scan, its
stale publication can request remeasure while the in-flight flag is still true;
flag clear does not retry, so guesses may await the next foreground/path/settings
event. Add an interleaving regression/retry. Capacity gate remains effective;
source-path review only, no independent Swift reproduction claimed.

#399/#400/#401 final heads/comments/CI/reviews/merges and retrospective events handled.
#401 prior reviews `6086245677` / `6086839589` and author fix/review requests
at18:30:22 /18:47:55 UTC handled; do not replay. Own docs CI ignored.
Completed detail is preserved verbatim in dated archives.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: await new actionable PR feedback;
  review ready PRs at exact head/green CI, then merge/delete if clear.
- `PREFETCH-MEASUREMENT-RETRY` — `queued`: nonblocking scan/write interleaving
  follow-up described in #401 PASS; await author follow-up PR.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 label variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired iPhone/Watch validation remains owner work.

## Live verification baseline

- Internal TestFlight 0.1.0 (82), upload `37774511661`, latest claimed release;
  excludes #395 onward. Apple read-only `37776197288`: VALID /IN_BETA_TESTING.
  IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  `3614bf6f3805479f8d13de65eeec4f0ad7871f22`; production container
  `aicaddie-release-3614bf6f-production-20261008`, loopback39055.
- Protected cutover evidence retained; sync last recorded
  502 rounds /501 scorecards /501 shots /ok /done.
- HTTP/2 homeserver: 3/3 HTTP200, 1.82–2.57 s; not Apple-runner path evidence.
- Latest 142-PNG reviewed baseline:
  `operations/pr401-bd8575ea-20261009/native-artifacts`.
  Earlier main baseline retained at `operations/pr399-f9aa623e-20261009/native-artifacts`.

## Owned resources and wait boundary

- PR401 final snapshot removed (27,927,837 bytes); named --rm contract container
  absent; production running. Source/log/Native originals retained.
- Prior PR401 snapshots/local settings inspection PNG already removed; receipts
  retained. No active worktree, snapshot, container, private venv, service, port,
  tunnel, subagent, verification terminal or local image inspection copy.
- Local PR401 controls/manifests/reviews/merge request retained as receipts.
  Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and historical `.codex-*`.
- Deployed waiter: `operations/blocking-waits/wait_for_conclusion.sh`.
  No wait pending at ledger write; after push start one `--feedback` terminal,
  retain handle in same turn; `clock.sleep(300000)` → one `write_stdin`
  until one-line conclusion. No liveness checks/replacement waiter.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.
  No CI-result-only commits.

## Next action and stopping

Resume sole feedback waiter. Ignore handled events/own docs CI. New ready PRs
are actionable after required CI; independently test exact head, verify Native/
screenshots where applicable, post findings or PASS, and merge/delete if clear.

Absolute stop: **2026-10-09 23:59 UTC**. Earlier stop requires 48 hours without
external PR events and no open PRs. Last handled author event:18:47:55 UTC.
Keep ledger ≤200 lines; archive historical detail verbatim before replacement.
