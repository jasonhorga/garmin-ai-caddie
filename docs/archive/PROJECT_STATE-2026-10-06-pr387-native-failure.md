# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before recording the full Native failure and Watch artifact review.
Live authority remains docs/operations/PROJECT_STATE.md.

+# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-06 11:18 UTC
**Canonical branch:** `main`
**Latest integrated code:** `3bf38b0c4ed9c7d3b6b73bf77452d25c8dbc31e4` (#386)
**Internal app/API/sync source:** `3614bf6f3805479f8d13de65eeec4f0ad7871f22`
**Current slice:** `PR-387-WATCH-CAPTURE-REVIEW` — `in-progress`

## Current status and deduplication

Jason confirms Claude is restored. Latest Claude PR #386 is reviewed, merged,
and included in verified internal build 80. No new subagents are required.
PR #387 is open at exact head `4504b2994331c93b16d5282afd9c205807680a23`.
Source `37442092046` and automatic Native `37442091978` passed. Full capture
is still needed to exercise the new Watch marker gate before merge.

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

- `PR-387-WATCH-CAPTURE-REVIEW` — `in-progress`: source/code review and
  targeted remote tests, then manual full live Native at exact head, artifact
  review, public verdict/merge and resource closure. Code has no blocker;
  130 independent tests passed (tests-r2.log). Full live Native **37456686597**
  dispatched once at exact head; conclusion failure/native-mobile. Diagnose
  the failing step/log before public findings or any further capture.
  Public progress comment `6015347738` is handled; do not repeat it.
- `PR-FEEDBACK-CONTINUOUS` — `queued`: consume the existing feedback
  cursor, review actionable Claude PRs on exact heads, wait for required CI,
  inspect native artifacts against approved design, comment P1/P2/non-blocking.
  With no blockers, merge and remove the source branch.
- `NATIVE-WATCH-CAPTURE` — `queued`, non-blocking: fixed sleep captured a
  launch logo in watch-score-recommendation.png. Require bounded target-ready
  capture/assertion and reject logos as target-screen evidence. Requested in
  #386 comment `6013163156`; #387 implements it, verification pending.
  Other Watch score frames/design tests passed.
- `IOS-STATUS-CONTRAST` — `queued`, non-blocking: existing dark system
  status-bar text on dark iOS map/review screens; raised with Native feedback.
- `WAIT-OWN-BRANCH-CI` — `queued`: self-CI filtering is main-only, so
  already reviewed internal Native/TestFlight runs woke feedback again.
  Reported bounded P2 on #383 as comment **6014454163**; await a fix PR.
  Existing waiting method/cursor retained; own report does not reset quiet.
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
- No implementation worktree. #387 read-only snapshot registered before creation:
  `/dev/shm/garmin-ai-caddie-pr387-4504b299-20261006`, expires Oct 7 11:18 UTC.
  Evidence: project `operations/pr387-4504b299-20261006`; API-image test
  container `codex-pr387-4504b299-tests`, --rm/network none/read-only/UID 1000,
  1 CPU/512 MiB. Capacity passed: 68 GiB root, 3.3 GiB shm, 4.2 GiB RAM.
  Preparation 45549 consumed: snapshot ready; tests hit 8 read-only data errors
  and noexec fake-xcrun (test-runner limits). Retry with isolated writable
  data tmpfs and executable /tmp; keep source read-only and original log.
  Retry 96545 succeeded/consumed: 130 tests/10.632 s. Full Native dispatcher
  helper/input registered in #387 evidence; same build 80 origin/backend.
  Dispatcher 62417 consumed: full live Native 37456686597, fixture=false,
  backend 3614bf6f explicitly pinned; no duplicate dispatch.
  Native waiter **2932** consumed: failure/native-mobile. Durable log
  `blocking-waits/wait-ci-37456686597-20261006T113705Z-1927367.log`.
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
  Feedback 34469 consumed: duplicate known TestFlight 37438559636.
  Feedback 95412 consumed: new ready PR #387; no active feedback waiter.
  Own #383 P2 comment 6014454163 is handled. Process #387 before resuming.
  All previously handled release feedback is deduplicated in dated archives.
  P2 comment input/evidence registered at project operations
  `pr383-own-branch-ci-20261006` (Codex, helper input expires Oct 7).
  Comment input remote checksum verified; local input removed.
- Same-turn background terminal: sleep 300000 ms, then one write_stdin until
  its one-line conclusion. No idle gh run view/process/state checks, duplicate
  waiter, independent waiter tmux, or CI-only commits. Method fixed through Oct 9.
  Shared `gh-feedback@garmin-ai-caddie.timer` unchanged.
- All GitHub comments/reviews end `_Generated by Codex_`; all commits have
  `Generated-by: Codex`.

## Next action and stop conditions

Release/cleanup state pushed as **4acb61f0**, #383 P2 handover as **2ec1ea1d**.
Resume only #387: diagnose failed full Native 37456686597 at head 4504b299,
then report evidence and resolve before review/merge/cleanup.
Do not upload a replacement app or switch production for this DEBUG/CI change.
For a new mobile PR, require exact-head Native CI and inspect its screenshots.

Quiet interval is suspended while #387 is open; previous Oct 8 09:23 deadline
is invalid (PR opened 09:18, after the previous queue check). After review,
confirm no open PRs and establish a new conservative quiet baseline. Finish
after 48 quiet hours and no open PRs, with a final condition/resource handoff.
Own commits/comments/CI and old duplicates never reset the clock.
Absolute end **2026-10-09 23:59 UTC**.

Keep this file ≤200 lines, current-only; archive superseded text verbatim.
After compaction read it, inspect Git/agent state and resume this single slice.
