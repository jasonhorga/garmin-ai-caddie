# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-06 09:27 UTC
**Canonical branch:** `main`
**Latest integrated code:** `3bf38b0c4ed9c7d3b6b73bf77452d25c8dbc31e4` (#386)
**Internal app/API/sync source:** `3614bf6f3805479f8d13de65eeec4f0ad7871f22`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current status and deduplication

Jason confirms Claude is restored. Latest Claude PR #386 is reviewed, merged,
and included in verified internal build 80. No new subagents are required.
No open PRs at 2026-10-06 09:13 UTC; the durable waiter delivers later events.

- `PR-386-VISION-REVIEW` — `done`: head
  `46b28275001d55c8a03e1be5cd83d1bcde52825b`; merge `3bf38b0c`.
  Source `37418492721` and 66 independent tests passed; review `5424500372`.
  Handover `6009994029`, release progress `6011111141`, Native review
  `6012727261`, release completion `6013163156` are handled.
- `PR-384-LAYUP-REVIEW` — `done`: head `b8c1d5f0`, merge `95eb8224`.
  P1 `5423698557` / reply `6009204457` resolved; Source `37412801028`,
  51 prep tests (2 skips), 12 goldens and water regression passed.
  Final review `5423787418`.
- `PR-385-PIN-SHEET-REVIEW` — `done`: head `b6b8c858`, merge `8099df3e`;
  Source `37411847028`, 42 tests passed; review `5423738591`.
- `PR-383-WAIT-POLICY` — `done`: head `1589265f`, merge `78bfbfd6`;
  Source `37396121559`, review `5422610831`; method unchanged.
- `PR-382-DEVICE-FEEDBACK` — `done`: head `beb0a829`, merge `9ebc8cba`;
  Source `37279043417` / Native `37279043304`; 136 snapshots reviewed.
- `INTERNAL-RELEASE-NEXT-MAIN` — `done`: all release gates and exact
  obsolete-resource retirement complete. Do not re-upload build 80.

Deduplicate these heads, comments/reviews and release run IDs. New substantive
feedback/new heads are actionable. Superseded details are verbatim in dated
PROJECT_STATE archives, including build80-verified and native-reviewed.
Own release events/comments and bookkeeping CI do not reset quiet time.

## Unfinished work

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: consume the existing feedback
  cursor, review actionable Claude PRs on exact heads, wait for required CI,
  inspect native artifacts against approved design, comment P1/P2/non-blocking.
  With no blockers, merge and remove the source branch.
- `NATIVE-WATCH-CAPTURE` — `queued`, non-blocking: fixed sleep captured a
  launch logo in watch-score-recommendation.png. Require bounded target-ready
  capture/assertion and reject logos as target-screen evidence. Requested in
  #386 comment `6013163156`; other Watch score frames/design tests passed.
- `IOS-STATUS-CONTRAST` — `queued`, non-blocking: existing dark system
  status-bar text on dark iOS map/review screens; raised with Native feedback.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: Jason's paired iPhone/Watch
  testing. Live Native evidence is simulator testing, not physical devices.

## Live verification baseline

- Package **0.1.0 (80)**: uploaded and Apple **VALID / IN_BETA_TESTING**;
  existing internal group contains 80. Apple operation=list/external=false.
- Exact release SHA `3614bf6f3805479f8d13de65eeec4f0ad7871f22` for app,
  API and sync. Text provider static; Gemini vision only. Private deployment
  inputs remain in homeserver evidence; do not publish secrets/relay addresses.
- Gates passed: Live Native `37426762320` (fixture=false/full/live preflight),
  TestFlight `37438559636`, Apple read-only `37440770465`.
  136 design PNGs equal approved #382; 92 iOS + 13 Watch runtime frames reviewed.
- All four screenshot ZIP digests verified. IPA artifact `11400009027` digest,
  provenance, backend/origin and both embedded bundle versions verified.
- IPA SHA-256:
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
- Synthetic pin sheet: HTTP 200, 18.901 s, exact date/three holes/front-side facts.
  HTTP/2 package: 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  four tunnel requests 2.10–2.34 s, all HTTP/2/200.
- Origin: `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production remains `aicaddie-release-d7f69971-production-20260925`,
  port `39055`, revision `d7f699712f7ac6cba41d97c420c405e090625caf`.
  No production switch/external distribution.
- Release evidence:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-3614bf6f-20261006`.
  It retains native review, artifact/Apple attestations and retirement manifests.
  #386 review evidence: project `operations/pr386-46b28275-20261006`.

## Owned resources and waits

- Retain build 80 candidate `aicaddie-release-3614bf6f-candidate-20261006`,
  loopback `39089`; image
  `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`.
  Sync image `aicaddie-sync:3614bf6f3805479f8d13de65eeec4f0ad7871f22`.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics `39110`.
  Isolated DB `aicaddie_candidate_3614bf6f_20261006` and private-root/config
  beneath release evidence remain for owner testing; existing key is protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13. Exact allow-list: release evidence `resource-manifest.md`.
- Build 79's old candidate/image tag/source removed. All 1,131 source files
  are backed up and checksum-verified in `retired-build79-source.tar.gz`.
  Original shared production volume/database retained. Old tunnel absent.
  Service health passed after cleanup; `release-79-retirement.json` has capacity.
- No active implementation worktree or review snapshot/test container.
  Local 13 review JPEGs + manifest matched remote copies and were removed.
  Release helper/input copies are preserved/checksummed in remote evidence.
  Preserve unrelated older `.codex-*` and dirty `ops/pr_feedback_monitor.sh`.
- All release/dispatch/download/cleanup terminals consumed: 1655, 89153,
  77191, 7679, 58930, 23813, 46012 (failed before deletion), 56391 (passed).
  All 21 owned local helpers/inputs removed after remote checksum verification;
  receipt/log retained in release evidence. Immutable workflow branch removed.
- Existing waiter:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait_for_conclusion.sh`.
  SHA-256 `5b3846c9ff7b4ad6a5297f5571fa162c8e0be5a50ee63da024d6ef11be038c6d`.
  Cursor `operations/blocking-waits/feedback-cursor`; never edit/delete it.
  No pending feedback handle yet; register the handle immediately after launch.
- Same-turn background terminal: sleep 300000 ms, then one write_stdin until
  its one-line conclusion. No idle gh run view/process/state checks, duplicate
  waiter, independent waiter tmux, or CI-only commits. Method fixed through Oct 9.
  Shared `gh-feedback@garmin-ai-caddie.timer` unchanged.
- All GitHub comments/reviews end `_Generated by Codex_`; all commits have
  `Generated-by: Codex`.

## Next action and stop conditions

Commit this real release/cleanup state once, then launch --feedback with a
timeout to the quiet deadline and retain its handle. Only its conclusion permits
event processing. Skip already handled release events; do not repeat gates.
For a new mobile PR, require exact-head Native CI and inspect its screenshots.

Fresh conservative quiet baseline: **2026-10-06 09:23 UTC**, after release;
conditional 48-hour deadline **2026-10-08 09:23 UTC**. A new substantive PR
event resets it; own commits/comments/CI and duplicate old events do not.
Finish earlier only after 48 quiet hours **and no open PRs**, with a final
condition check and resource handoff. Absolute end **2026-10-09 23:59 UTC**.

Keep this file ≤200 lines, current-only; archive superseded text verbatim.
After compaction read it, inspect Git/agent state and resume this single slice.
