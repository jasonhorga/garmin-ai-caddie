> HISTORICAL ARCHIVE — NON-AUTHORITATIVE
> Verbatim ledger before consuming preparation terminal 33811 and starting release preflight.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-06 06:20 UTC
**Canonical branch:** `main`
**Latest integrated code:** `3bf38b0c4ed9c7d3b6b73bf77452d25c8dbc31e4` (#386)
**Internal app source:** `3f05ca689b0ca4988bfcc404f9fe3ba446d6727c`
**Internal backend source:** `048ab6a4b02e9b8d2d81d0d1098cc7cb696f7252`
**Current slice:** `INTERNAL-RELEASE-NEXT-MAIN` — `in-progress`

## Current status and handled feedback

Jason confirms Claude is restored. Claude's latest PR #386 is reviewed and
merged; no delegation is required. Codex owns integration and release gates.

- `PR-386-VISION-REVIEW` — `done`: exact head
  `46b28275001d55c8a03e1be5cd83d1bcde52825b`; merge `3bf38b0c`.
  Source CI `37418492721` backend/frontend/docker passed; 66 independent
  provider/pin-sheet/media/config/settings/deployment tests passed.
  Final review `5424500372`; branch and read-only snapshot removed.
  Handover comment `6009994029` authorizes the queued internal sequence
  already requested by Jason. Public review contains no private relay inputs.
- `PR-384-LAYUP-REVIEW` — `done`: exact head `b8c1d5f0`, merge `95eb8224`.
  P1 `5423698557` and reply `6009204457` resolved: actual-origin water
  checks and 8 m buffers. Source `37412801028`, 51 prep tests (2 skips),
  12 goldens and original water regression passed. Review `5423787418`.
- `PR-385-PIN-SHEET-REVIEW` — `done`: head `b6b8c858`, merge `8099df3e`;
  Source `37411847028`, 42 tests passed; review `5423738591`.
- `PR-383-WAIT-POLICY` — `done`: head `1589265f`, merge `78bfbfd6`;
  Source `37396121559`, review `5422610831`; waiting method unchanged.
- `PR-382-DEVICE-FEEDBACK` — `done`: head `beb0a829`, merge `9ebc8cba`;
  Source `37279043417` / Native `37279043304`; 136 snapshots reviewed.

Deduplicate those heads and review/comment IDs. New substantive feedback or
a new head is actionable. Detailed superseded records are preserved verbatim
in dated `PROJECT_STATE-2026-10-06-*` archives.

The previous quiet interval was suspended by #386; old deadlines are invalid.
After release, establish a new quiet baseline from genuine PR events and
confirm no open PRs. Never count own bookkeeping/CI as activity.

## Unfinished work and release boundaries

- `INTERNAL-RELEASE-NEXT-MAIN` — `in-progress`: pinned latest main
  `3614bf6f3805479f8d13de65eeec4f0ad7871f22`; API, sync and app bind
  to this SHA. Includes #382/#384/#385/#386. Candidate preparation started.
- Build a new isolated candidate API plus `aicaddie-sync:<same-full-SHA>`.
  Explicitly set API_IMAGE for sync; the default targets production 39055.
- Keep text provider static; Gemini is for vision only. Read the existing
  private homeserver deployment guide; never publish relay addresses,
  actual credentials or secret paths.
- Gates: HTTP/2 tunnel/throughput → exact-SHA live Native (fixture=false,
  full capture) → internal TestFlight → Apple read-only. Also require
  synthetic pin-sheet API HTTP 200 with sensible extracted facts.
- Physical-device testing is owner evidence; live Native is simulator
  validation and must not be described as an actual paired-device test.
- Do not switch production or enable external distribution.
- After the replacement is verified, close build 79's obsolete candidate,
  tunnel/image/private copies through exact manifests. Preserve unique
  user data/evidence before deleting any copied private root.
- Resume feedback handling after release, using the durable cursor.

## Live verification baseline

- Current package: **0.1.0 (79)**, VALID / IN_BETA_TESTING; owner iPhone/
  Watch testing remains `evidence-open` until replaced/owner feedback.
- Gates: live Native `37257466397`, TestFlight `37262234670`,
  Apple read-only `37262917624`: passed. HTTP/2 214,475-byte response:
  loopback ~0.18 s, tunnel 1.28–2.19 s; eight requests HTTP/2/200.
- IPA SHA-256:
  `82d7077351a8eb079026469ef068d9f8d3929022a486371d0ecacbe61427cdb8`.
- Retained build 79 candidate:
  `aicaddie-release-048ab6a4-candidate-20261004-r2`, loopback `39088`.
  Image:
  `garmin-ai-caddie-api:048ab6a4b02e9b8d2d81d0d1098cc7cb696f7252-candidate-20261004`.
- Build 79 origin:
  `https://purple-vegetation-downtown-colon.trycloudflare.com`.
- Production remains `aicaddie-release-d7f69971-production-20260925`,
  loopback `39055`; do not modify production or moving latest aliases.
- Release evidence:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-3f05ca68-20261005/`.
- #383/#384/#385/#386 evidence roots:
  `operations/pr383-policy-1589265f-20261006/`,
  `operations/pr384-f4ad0e3b-20261006/`,
  `operations/pr384-b8c1d5f0-20261006/`,
  `operations/pr385-b6b8c858-20261006/`,
  `operations/pr386-46b28275-20261006/`, all under the project data dir.
- #386 `tests.log` records 66 passing tests; its manifest closes resources.

## Owned resources and waiting

- Build 79 source:
  `/home/jason/codex-runs/garmin-ai-caddie-release-048ab6a4-20261004`.
- Retained tunnel tmux: `codex-release-http2-main-048ab6a4-r2`.
- Allow-list:
  `/home/jason/garmin-ai-caddie-data/operations/release-main-048ab6a4-20261004-r2/resource-manifest.md`.
- No active implementation worktree or review snapshot. #383 worktree,
  both #384 snapshots, #385/#386 snapshots and test containers are closed.
- New release source/evidence registered before creation: `codex-runs/
  garmin-ai-caddie-release-3614bf6f-20261006` and `operations/
  release-main-3614bf6f-20261006`, both under the documented homeserver roots.
  Its resource-manifest.md allow-lists candidate 3614bf6f, port 39089,
  HTTP/2 tmux, private copy and isolated DB; source expiry Oct 13.
  Preparation terminal handle 33811 is pending in this same turn; read
  its one-line conclusion before starting gates. Do not start a duplicate.
- Old candidate shares production volume/DB; new candidate clones both,
  so Native tests must only target the new origin. No production writes.
- #386 local review inputs are copied/checksummed into persistent evidence
  before removal. Preserve other pre-existing `.codex-*` files and modified
  `ops/pr_feedback_monitor.sh`; never stage unrelated work.
- Existing waiter:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait_for_conclusion.sh`.
  SHA-256:
  `5b3846c9ff7b4ad6a5297f5571fa162c8e0be5a50ee63da024d6ef11be038c6d`.
- Cursor: `operations/blocking-waits/feedback-cursor`; never edit/delete.
  No pending waiter handle at slice transition.
- Use same-turn background terminal, five-minute sleep then one write_stdin
  until its one-line conclusion. No idle gh run view/process/state checks;
  no replacement while a handle is pending. Method fixed through Oct 9.
- Independent waiter tmux is closed; shared
  `gh-feedback@garmin-ai-caddie.timer` remains unchanged.
- No CI-only commits; ignore own main CI. Every GitHub comment/review ends
  `_Generated by Codex_`; every commit has `Generated-by: Codex`.

## Next action and stop conditions

Complete candidate preparation at pinned 3614bf6f, then perform release gates.
If a required gate fails, diagnose and fix only within the authorized release
scope; do not claim a passing gate or upload an unverified candidate.

End no later than **2026-10-09 23:59 UTC**, or earlier after **48 consecutive
hours with no new substantive PR event and no open PR**. Quiet timeout requires
a final condition check, resource handoff and completion of the goal.

Keep this file **≤200 lines**, current-only. Archive superseded text verbatim,
marked HISTORICAL ARCHIVE — NON-AUTHORITATIVE. After compaction read this file,
inspect Git/agent state, and resume this single slice without repeating work.
