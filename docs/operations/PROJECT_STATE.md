# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-06 21:28 UTC
**Canonical branch:** `main`
**Latest integrated code:** `9f56c35b61809069537d8c3f09c28a6e3347d8d5` (#388)
**Internal app/API/sync source:** `3614bf6f3805479f8d13de65eeec4f0ad7871f22`
**Current slice:** `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`

## Current status and deduplication

Claude is restored. Only #389 is open; #387/#388 merged, branches deleted.
#389 new head `56022d326edf7b4cc789f9ecea818ceb6da50805` claims all four
P2 6021873468 paths fixed; code diff confirms shared eligibility, generation
check before cleanup, account clear and active-job intent registration.
Author reply `6023411098` read; Source `37515958115` passed,
Native `37515958145` passed. Independent 130 tests/8.912 s passed; snapshot/container
closed after source backup checks. Native artifacts verified: all 89 iOS/47
Watch design frames byte-identical to reviewed baseline; all ZIP digests pass.
New pause/resume (0.214 s) and account-rebind (0.049 s) behavior tests passed;
compiled feafce442 has no mobile/ios diff. P2 resolved; full live **37519627055**
dispatched 19:31:35 UTC on exact head 56022d32, fixture=false/full/live preflight.
P2 closure/live-dispatch comment **6023959200** posted and handled.
Full live 37519627055 failed before starting the round: RealFlowUITests:70
could not find `start-round-course-half-31793-back`. Repaired enrollment path
not exercised. Inspect actual screenshots/selection/catalogue before RCA;
prior code P2 stays resolved. No blind rerun, weakened assertion or merge.
Live failure intake comment **6025340897** posted and handled.
Live artifact downloader terminal **10844** completed; five ZIP digests pass,
86 iOS/13 Watch runtime PNGs plus 136 design frames. Watch capture succeeded.
Review-sheet terminal **32028** completed; --rm image container closed.
Local copies `.codex-pr389-56022d32-live-review`: all 86 iOS/13 Watch frames
reviewed; full-live designComparison confirms all 89 iOS/47 Watch equal baseline.
Remote sheets/index are canonical; copies expire Oct 7 21:15.
Video downloader **59206** completed success; artifact **11443055917**
ZIP SHA256 `f4ef44ec8a2b8591c9a185f794fa19974dda40ac82ea3f5d108f65d4eb5dcbbc`.
Verified/extracted under full-live `video-evidence`; failed selector has no PNG.
Video shows empty Hub → empty course list/spinner → retry icon; no selection.
Origin response gap/tunnel cancellations verified; responsible layer unproven.
Author RCA **6025352540** read; reply **6025783925** handled, evidence boundary
preserved. Review `2026-10-06-pr389-live-selector-failure-review.md`.
One unchanged-head observed full live **37534118109** dispatched 21:28:19 UTC;
original assertions/live preflight/full/fixture=false, retained Build80 backend.
Health preflight origin HTTP 200/0.035 s; tunnel HTTP/2 200/1.165 s.
Next start its origin/tunnel trace + existing blocking CI waiter in same turn.
Evidence subdirectory
`operations/pr389-56022d32-20261006/full-live-37519627055`.
Earlier reviewed heads/comments deduplicated in dated archive
`PROJECT_STATE-2026-10-06-pr389-live-video-intake.md`; old review_pr376 closed.

Deduplicate heads, comments and run IDs. New substantive feedback/new heads
are actionable; own comments/commits/CI/duplicates never reset quiet time.

## Unfinished work

- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume existing same-turn
  feedback cursor; review exact head/tests/Native artifacts; post P1/P2/
  non-blocking verdict and merge/delete branch only when clear.
- `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`: await observed full
  live 37534118109. Code P2/tests/design proof complete. Check unchanged
  后九→前九/relaunch prep journey and queue trace before approval/merge.
  Repeated selection failure requires origin/tunnel trace diagnosis.
- `PR-387-IOS-JOURNEY-REGRESSION` — `blocked`: carried by #389 final live proof.
- `IOS-STATUS-CONTRAST` — `queued`, non-blocking: existing dark iOS system
  status-bar text on dark map/review screens.
- `OWNER-DEVICE-BUILD80` — `evidence-open`: owner's paired iPhone/Watch test;
  Native evidence is simulator evidence, not paired physical-device testing.

## Live verification baseline

- **0.1.0 (80)** available in existing internal TestFlight group; Apple
  **VALID / IN_BETA_TESTING**, operation=list/external=false.
- App/API/sync SHA `3614bf6f3805479f8d13de65eeec4f0ad7871f22`.
  Text provider static; Gemini vision only. No production switch/external release.
- Passed: Live Native `37426762320`, TestFlight `37438559636`,
  Apple read-only `37440770465`; 136 design PNGs equal approved #382,
  92 iOS/13 Watch runtime frames reviewed.
- IPA artifact `11400009027`, ZIP/provenance/backend/origin and both bundle
  versions verified. SHA256:
  `84ceedfbafc1ff23095e35f7a4218970377a1083e7659ae65679b25f24f07d55`.
- Synthetic pin sheet: HTTP 200/18.901 s, exact date/3 holes/front facts.
  HTTP/2 package: 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  four tunnel requests 2.10–2.34 s, HTTP/2/200.
- Live origin: `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production: `aicaddie-release-d7f69971-production-20260925`, port 39055,
  revision `d7f699712f7ac6cba41d97c420c405e090625caf`.
- Evidence root `/home/jason/garmin-ai-caddie-data/operations`:
  release-main-3614bf6f-20261006; pr387-4504b299-20261006;
  pr388-4a1108aa-20261006; pr389-87a00b3a-20261006;
  pr389-af7a837e-20261006; pr389-4e7e7eb1-20261006.

## Owned resources and waits

- #389 read-only snapshot completed and closed at
  `/dev/shm/garmin-ai-caddie-pr389-56022d32-20261006`, expires Oct 7 19:10;
  --rm test container `codex-pr389-56022d32-tests-20261006`, no network/deps.
  Evidence/resource manifest `operations/pr389-56022d32-20261006`.
- Video renderer `codex-pr389-video-selection-20261006` closed automatically;
  11 frames/two sheets/index retained, downloader 59206/extractor 80386 finished.
- `.codex-pr389-56022d32-observed-live.py`: read-only origin/tunnel sampler
  plus existing blocking waiter, expiry 7,200 s after start; no new service,
  worktree/container/port/volume. Evidence `observed-live-37534118109`.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089;
  API image `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`.
  Matching full-SHA sync image retained for owner testing.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110.
  Isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config/key protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13; exact allow-list in release resource-manifest.md.
- Build79 retired with verified 1,131-file backup; production volume/DB protected.
- Verifier terminal **82946** completed (130 OK); snapshot/container closed.
  Native wait terminal **21614** completed success, run 37515958145; task-scoped final
  summary `operations/pr389-56022d32-20261006/native-wait-result.txt`.
  Artifact verifier terminal **41986** completed success, all ZIPs/136 frames.
  Full live run **37519627055** failed; observer 94141 completed, waiter
  3111915 ended. SSH closed 72721 and original result was reattached;
  no duplicate waiter/run/cursor changes. No active CI waiter.
  task-scoped final summary `operations/pr389-56022d32-20261006/full-live-wait-result.txt`.
  No implementation worktree. Previous #389 4e7e7eb1 snapshot removed
  17:44:19 UTC after exact
  archive/use checks; cleanup receipts retained. ZIP interruption resumed;
  final digests pass. No new service/deps/ports/tunnel/volume.
- Six local helpers removed after exact remote backup verification; allow-list remains
  `.codex-pr389-4e7e7eb1-local-cleanup.json`. Earlier manifests/unknown
  `.codex-*` and dirty `ops/pr_feedback_monitor.sh` remain protected.
- Capacity baseline: 66 GiB disk/4.3 GiB available RAM.
- Post-cleanup production and retained Build80 API health both HTTP 200.
- Feedback waiter PID 2953236 / observer terminal 41738 completed with
  author reply 6023411098. Lost handle 88742 was reattached, never duplicated.
  No feedback waiter active while reviewing new head; cursor unchanged.
  Reviewed heads/runs and own review comments all deduplicated; unchanged
  cursor retained. Previous handles consumed; no liveness checks.
- Deployed waiter:
  `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait_for_conclusion.sh`.
  SHA256 `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor `operations/blocking-waits/feedback-cursor`; never edit/delete.
- Same-turn background terminal → sleep 300000 ms → one write_stdin, until
  one-line conclusion. No idle gh run view/ps/state/liveness/log polling,
  duplicate monitor, independent waiter tmux or CI-only commits.
  gh-feedback timer unchanged; wait method fixed through Oct 9.
- Every GitHub comment/review ends `_Generated by Codex_`; every Codex
  commit has `Generated-by: Codex`. Own commits/CI ignored by broad waiter.

## Next action and stop conditions

Commit selector review/visual evidence and verbatim archives, then start one
observed-live 37534118109 waiter. Retain terminal in this turn; no CI/liveness
checks while it waits. On terminal result inspect actual journey/trace/artifacts.
Do not create CI-result-only bookkeeping commits.

Quiet interval suspended while #389 is open. Once no PRs remain, establish
a fresh conservative baseline; end after 48 quiet hours/no open PRs or
absolute **2026-10-09 23:59 UTC**, with owned-resource handoff.
Own commits/comments/CI and duplicates never reset quiet time.

Keep this file ≤200 lines/current-only; archive superseded text verbatim.
After compaction read this file, inspect Git/agent status, resume this slice.
