# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Preserved verbatim before reviewing Claude's #388 all-branch self-CI fix.
Live authority remains docs/operations/PROJECT_STATE.md.

+# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-06 13:38 UTC
**Canonical branch:** `main`
**Latest integrated code:** `3bf38b0c4ed9c7d3b6b73bf77452d25c8dbc31e4` (#386)
**Internal app/API/sync source:** `3614bf6f3805479f8d13de65eeec4f0ad7871f22`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current status and deduplication

Claude is restored. #386 is merged and included in internal build 80.
#387 Watch screenshot fix has completed exact-head code/runtime review, but
merge is blocked on a separate iOS journey failure handed to Claude. No new
subagents are required; old review_pr376 is complete and resources closed.

- #387 exact head `4504b2994331c93b16d5282afd9c205807680a23`.
  Source `37442092046`, automatic Native `37442091978`, independent
  130 tests passed. Full live Native `37456686597` failed one iOS journey.
  Watch target-ready capture passed; all 13 runtime frames reviewed.
  Progress `6015347738`, P2 `6016542546`, screenshot verdict
  `6017410544` are handled. Do not repeat these comments/runs.
- #386 head `46b28275001d55c8a03e1be5cd83d1bcde52825b`,
  merge `3bf38b0c`; Source `37418492721`, 66 tests/review `5424500372`.
  Handover `6009994029`, release progress `6011111141`, Native review
  `6012727261`, release completion `6013163156` are handled.
- #384 head `b8c1d5f0`, merge `95eb8224`; P1 `5423698557` /
  reply `6009204457` resolved; final review `5423787418`.
- #385 head `b6b8c858`, merge `8099df3e`; review `5423738591`.
- #383 head `1589265f`, merge `78bfbfd6`; review `5422610831`.
  Own-branch CI P2 `6014454163` remains awaiting a fix PR.
- #382 head `beb0a829`, merge `9ebc8cba`; 136 snapshots reviewed.

Deduplicate these heads/comments and the release/Native run IDs below.
New substantive feedback/new heads are actionable. Superseded details are
verbatim in dated archives; own comments/commits/CI never reset quiet time.

## Unfinished work

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: resume the existing cursor
  and same-turn feedback waiter; process Claude's root cause/fix for #387.
  Review each actionable PR on exact head, required CI and native artifacts;
  comment P1/P2/non-blocking; with no blockers merge/delete source branch.
- `PR-387-WATCH-CAPTURE-REVIEW` — `blocked`: code/Watch capture passes;
  full Native failed `RealFlowUITests.testBackNineThenFrontNineJourney`
  at RealFlowUITests.swift:141: after 后九→前九, summary and relaunch into
  prep, `prep-download-row-31793:` is missing. P2 handed to Claude.
  Five journey frames/72-stroke summary exist; b4b2-06 is absent due to
  prerequisite failure. Await root cause and targeted verification; do not
  blindly re-run full Native or remove the assertion. Separate fix PR is OK.
- `NATIVE-WATCH-CAPTURE` — `evidence-open`: #387 readiness helper passed
  full runtime proof. watch-score-recommendation is now the actual score
  page (H7/P4, 5 strokes, putts 2/penalties 0, three tee results, save button),
  not a logo. Close after the fix is integrated.
- `IOS-STATUS-CONTRAST` — `queued`, non-blocking: existing dark system
  status-bar text on dark iOS map/review screens; no new rendering change.
- `WAIT-OWN-BRANCH-CI` — `queued`: skip Codex-provenance feedback CI
  across branches, preserve Claude under shared identity, keep explicit
  --run/--release results. #383 P2 `6014454163`; await fix PR.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: Jason's paired iPhone/Watch
  testing; Native proof is simulator testing, not physical-device testing.

## Live verification baseline

- **0.1.0 (80)** uploaded; Apple **VALID / IN_BETA_TESTING**, existing
  internal group contains 80. Apple operation=list/external=false.
- App/API/sync SHA `3614bf6f3805479f8d13de65eeec4f0ad7871f22`.
  Text provider static; Gemini vision only. Private deployment inputs remain
  in remote evidence; no production switch or external distribution.
- Passed gates: Live Native `37426762320` (fixture=false/full/live preflight),
  TestFlight `37438559636`, Apple read-only `37440770465`.
  136 design PNGs equal approved #382; 92 iOS/13 Watch runtime frames reviewed.
- IPA artifact `11400009027`: ZIP/provenance/backend/origin and both embedded
  bundle versions verified. IPA SHA-256:
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
- Synthetic pin sheet: HTTP 200, 18.901 s, exact date/three holes/front-side
  facts. HTTP/2 package: 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  four tunnel requests 2.10–2.34 s, all HTTP/2/200.
- Origin: `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production `aicaddie-release-d7f69971-production-20260925`, port `39055`,
  revision `d7f699712f7ac6cba41d97c420c405e090625caf`.
- Release evidence:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-3614bf6f-20261006`.
- #387 evidence: project `operations/pr387-4504b299-20261006`: five ZIP
  digests/native proof verified; 89 iOS/47 Watch design frames match build80
  byte-for-byte; 91 iOS/13 Watch runtime frames inspected against README,
  Watch prototype/plan. Full log, source tar, tests, digests, per-frame index
  and review sheets retained. iOS proof remains failed; Watch passed.
  Partial artifact transfer resumed successfully; preserve timeout logs.

## Owned resources and waits

- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`,
  loopback `39089`; API image
  `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`.
  Matching full-SHA sync image remains.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics `39110`.
  Isolated DB `aicaddie_candidate_3614bf6f_20261006`; private-root/config
  under release evidence remain for owner testing; existing key protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13. Exact allow-list: release evidence resource-manifest.md.
- Build79 old candidate/image tag/source retired; all 1,131 source files
  backed up/checksum-verified. Original production volume/database protected;
  old tunnel absent; retirement manifest/capacity/health retained.
- No implementation worktree or active review snapshot. #387 snapshot
  `/dev/shm/garmin-ai-caddie-pr387-4504b299-20261006` removed after source
  tar checksum and /proc/container use checks. Test/renderer --rm containers
  closed. Production/build80 health both 200 on /api/v2/health.
- #387 local 18 JPEGs/12 helper-inputs plus two metadata copies removed
  after remote checksum verification (32 files); exact manifests/source
  backups/evidence retained remotely. Cleanup receipts in #387 evidence.
  Preserve unrelated old `.codex-*` and dirty `ops/pr_feedback_monitor.sh`.
- #387 terminals all consumed: 45549 (runner constraints), 96545 (130 passed),
  62417 (dispatch), 2932 (Native failure), 10645 (artifact timeout),
  49939 (resume/all ZIPs verified), 89541 (review render), 76700 (copy).
- Existing waiter:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait_for_conclusion.sh`.
  SHA-256 `5b3846c9ff7b4ad6a5297f5571fa162c8e0be5a50ee63da024d6ef11be038c6d`.
  Cursor `operations/blocking-waits/feedback-cursor`; never edit/delete.
  Feedback 34469 (duplicate TestFlight) and 95412 (#387 opening) consumed.
  Buffered duplicates consumed through 66427 (#387 green CI, own #383 P2);
  41681 hit transient TLS on reviewed 37442091978; no retry/quiet reset.
  Feedback waiter **99006** active; same-turn observation only.
- Same-turn background terminal: sleep 300000 ms, then one write_stdin until
  one-line conclusion. No idle gh run view/process/state checks, duplicate
  waiter, independent waiter tmux, or CI-only commits. Fixed through Oct 9.
  Shared `gh-feedback@garmin-ai-caddie.timer` unchanged.
- Every GitHub comment/review ends `_Generated by Codex_`; commits carry
  `Generated-by: Codex`.

## Next action and stop conditions

Review/resource closure and archives pushed as **4d74f20f**. Wait on feedback
terminal **99006** in this same turn for Claude's reply/fix or a new actionable
PR. #387 stays open; no replacement TestFlight/production switch for DEBUG/CI.

Quiet interval suspended while #387 is open; previous Oct 8 09:23 deadline
is invalid. Once reviews close and there are no open PRs, establish a fresh
conservative baseline. End after 48 quiet hours/no open PRs, or at absolute
end **2026-10-09 23:59 UTC**, with final resource/condition handoff.
Own commits/comments/CI and duplicates never reset the clock.

Keep this file ≤200 lines/current-only. Read it after compaction, inspect
Git/agent state and resume this slice. Archive superseded text verbatim.
