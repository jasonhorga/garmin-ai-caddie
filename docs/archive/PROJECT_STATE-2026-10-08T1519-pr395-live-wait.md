# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived verbatim after fixed-head source review and resource closure.
Only docs/operations/PROJECT_STATE.md is authoritative.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-08 15:06 UTC
**Canonical branch:** `main`
**Latest integrated code:** `6dd96200b199ac8f5ea760719fb295bbc4eea1ef` (#394)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state and deduplication

Claude restored. #394 is merged and its release result has been returned.
Open PR #395, non-draft, new head `5f3c0c3c8e4101e1c78b5110caaeccbb79311e96`:
author fixes in comment **6062377485**, exact-head re-review underway.
CI **37794766703** and Native **37794766696** already green; verify provenance,
tests and artifacts. Prior head `1547b250` review had **3 P2 blockers**
in comment **6062275804**: cancel/resume an already-running background refresh
for foreground work; invalidate older cache writers after Garmin sync; retain
new fallback cache when a pending page request fails. Recheck those fixes on
`5f3c0c3c`; do not repeat review of `1547b250`. Prior findings were static
time-order analysis, not injected Swift race reproductions.

- #395 CI **37778457263**, Native **37778457236**, live **37781120740** passed.
  Native merge **31924176**, parents base **6dd96200** and head **1547b250**;
  merge/head trees identical. **93 iOS / 47 Watch** PNGs match #394 hashes;
  live home/results visually checked. Independent contracts: **122 / 5.176 s
  / OK**. Initial sandbox fixture-write errors retained separately.
- #395 evidence: `operations/pr395-1547b250-20261008` (review, manifests,
  Native/live artifacts and contract logs). Original live evidence and current
  reviewed head are handled; own review comment must not retrigger work.

- #392/#393 finished; old heads, comments, CI and cleanup are archived.
- #394 exact head `93824a8d59e08a781246ede04678e85a1a0bd5fb` reviewed;
  PASS comment **6059399934**; merged **6dd96200** at **Oct 8 12:02:45 UTC**;
  source branch deleted. App/test/workflow tree matches the reviewed head.
- Required CI **37736864574**, Native **37736864564**, live **37738509778**
  passed on that head. Live: **13 UI / 448 unit tests**; includes the #393
  failing journey and observed intent yielding/resuming.
- Native **93 iOS / 47 Watch** PNGs are byte-identical to the reviewed #393
  baseline. Artifacts/hashes retained at `operations/pr394-93824a8d-20261008/native-artifacts`.
- #394 release response **6061833380** includes build 82 and corrects the
  earlier disk-capacity misreading. Required CI was sufficient; no disk gate
  prevented extra tests (about 63 GiB free).
- Do not repeat #393 cutover requests or #394 known replies/CI when cursor
  replays them. #393 result **6058558621**, #394 review/release above are own
  comments. Claude's **6054000859 / 6055315555 / 6058107992 / 6058245346**
  and Oct 8 12:05 replacement request are already handled.
- Read the last matched event from the returned wait log, not preceding ignored
  CI lines. Cursor is authoritative; never edit/delete it.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: re-review #395 fixes delivered by
  the feedback stream; inspect changed code on the new exact head, relevant tests,
  Native/screenshots, resolve P1/P2 before merge/delete; handle subsequent PRs.
- `LIVE-CATALOGUE-FALLBACK` — `queued`, nonblocking: city-search first attempt
  failed; unchanged-head retry passed. If recurrent, preserve actual response,
  completion and scroll evidence; AX mounted rows alone are insufficient.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`, nonblocking: 八号铁 164 label
  varies on unchanged fixture; no product regression claimed.
- `IOS-STATUS-CONTRAST` — `queued`, nonblocking dark status text on dark maps.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: owner's paired iPhone/Watch test.
  Supersedes build 80/81 validation. Live CI is simulator evidence;
  `watch-round-seeded.png` waiting page alone does not prove geometry readiness.

## Live verification and release baseline

- **0.1.0 (82)**, internal TestFlight: workflow **37774511661** succeeded.
  App commit **6dd96200b199ac8f5ea760719fb295bbc4eea1ef** includes #394.
  Apple read-only/list **37776197288**: **VALID / IN_BETA_TESTING**;
  existing internal group includes 82; no external distribution.
- Apple exposes `internalReady=false` alongside `IN_BETA_TESTING`; retain this
  field discrepancy. Build 81 lacks #394 and must not be the acceptance build.
- IPA SHA256 `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
  IPA, provenance and PR response: `operations/release-main-6dd96200-20261008`.
- Stable API `https://caddie.taile36706.ts.net`, backend and immutable sync
  revision **3614bf6f3805479f8d13de65eeec4f0ad7871f22**.
  Production `aicaddie-release-3614bf6f-production-20261008`, loopback **39055**.
  Build82 upload preflight verified this revision; no new backend promotion.
- Cutover evidence `operations/production-cutover-3614bf6f-20261008` includes
  both database dumps, pre-merge roots, conflict evidence and merge report.
  Production's newer 7-hole round 17742546 retained; candidate's 2-hole copy
  preserved. Candidate-only ledger suffix **8,426,773 bytes** and cache changes
  merged. Completed sync: **502 rounds / 501 scorecards / 501 shots / ok / done**.
- Stable-origin HTTP/2 probes: **3/3 200 / HTTP2**, **1.82–2.57 s**.
- Durable remote evidence root: `/home/jason/garmin-ai-caddie-data/operations`.
  Historical build80/81 runs, screenshots and failed attempts remain archived.

## Owned resources and wait boundary

- New #395 read-only snapshot planned:
  `/dev/shm/garmin-ai-caddie-pr395-5f3c0c3c-20261008`, expires Oct 9 15:06 UTC.
  Manifest/evidence: `operations/pr395-5f3c0c3c-20261008`; one `--rm` network-none
  contract container, no dependency installation, ports or services.
- #395 snapshot `/dev/shm/garmin-ai-caddie-pr395-1547b250-20261008` closed
  after open-file check; `--rm` contract container gone. Two local PNG copies
  match persistent evidence hashes and were moved to recoverable user trash.
  Manifest/evidence at `operations/pr395-1547b250-20261008` retained. No active
  implementation worktree, port, tunnel, browser service or subagent.
  Local review ref `origin/pr395-review` now points to the author's fixed head.
- Candidate `aicaddie-release-3614bf6f-candidate-20261006` is **stopped**;
  port 39089 no longer serves it. Keep its private root and isolated DB
  `aicaddie_candidate_3614bf6f_20261006` until owner build82 validation.
- Rollback `aicaddie-release-d7f69971-production-20260925-pre-cutover` is
  **stopped and retained**. Production private volume/database protected.
- HTTP/2 tmux `codex-release-http2-main-3614bf6f-20261006` closed.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`
  expires **Oct 13**; release allow-list and persistent backups retained.
- Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and older `.codex-*`;
  do not stage them. Prior local review copies are recoverable in user trash.
- Deployed waiter `operations/blocking-waits/wait_for_conclusion.sh`; SHA256
  `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
- Last feedback waiter delivered **6062377485** and is closed; no wait pending.
  After review, start the next sole `--feedback` waiter in this same turn. Store terminal
  handle in `active_feedback_wait`; recover it after compaction if pending.
- While pending: **clock.sleep(300000) → one write_stdin** with a short
  observation interval, repeat in the same turn. No CI/ps/state/log polling,
  replacement waiter, independent tmux or second monitor. Timer unchanged.
- Ignore own CI/bookkeeping and duplicate comments; no CI-only state commits.
  GitHub comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.

## Next action and stopping

Release reply is complete; re-review #395 fixed head, then reply and resume the
existing cursor. Deduplicate old #393/#394/#395 events, including original
author evidence **6061786172**, own review **6062275804** and release **6061833380**.
Preserve all new evidence on homeserver.
48-hour quiet stopping is **not eligible while #395 is open**; count only new
external PR events, never own comments/merges/CI/docs. Absolute owner stop:
**2026-10-09 23:59 UTC**. At stop close/hand back owned runtime resources.
Keep this same-turn waiting method through the deadline. Ledger ≤200 lines.
Latest superseded ledger is archived verbatim in
`docs/archive/PROJECT_STATE-2026-10-08T1506-pr395-fixed-head.md`.
After compaction: read this ledger, inspect Git/agent state, resume this slice.
