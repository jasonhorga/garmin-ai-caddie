> HISTORICAL ARCHIVE — NON-AUTHORITATIVE
> Verbatim state before final-head #389 evidence closeout, 2026-10-06 17:54 UTC.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-06 17:30 UTC
**Canonical branch:** `main`
**Latest integrated code:** `9f56c35b61809069537d8c3f09c28a6e3347d8d5` (#388)
**Internal app/API/sync source:** `3614bf6f3805479f8d13de65eeec4f0ad7871f22`
**Current slice:** `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`

## Current status and deduplication

Claude is restored. #387 and #388 are merged; their source branches deleted.
#389 new head `4e7e7eb16632db849c7b806b3096489482d3eaf1` claims fixes for
P2 6020952816 is resolved: real foreground preserves the fresh-entry gate;
each worker dequeue gates automatic work. New P2 `6021873468`: retained
explicit IDs cannot restart on foreground; stale worker cleanup mutates
intent before generation check; intent is not cleared on account rebind.
Source `37498292084` and Native `37498292248` passed. Independent tests
and Native artifacts are being collected; full live waits for corrected head.
Author reply `6021043095` read substantively; do not answer it twice.
No new subagents; old review_pr376 is complete and its resources closed.

- #389 previous reviewed head `af7a837e1a5c739dcaaa3faaef4e0a7f05b0c57c`; Source
  `37491131543`/Native `37491131642` green. Fix/rebase replies 6019989194 /
  6020075979 handled. Independent 130 tests and three ZIP digests pass;
  all 89 iOS/47 Watch PNGs match reviewed baseline; compiled 75bbf446 has
  no mobile/ios diff from this head. P2 6020952816 / evidence 6021181763
  handled. No full live run on known-blocked head. Intermediate head
  `41857121bdc917bb82cba0af870bd707e26df225` and cancelled runs
  37490470913/37490470917 are superseded by the rebase. Previous reviewed head
  `87a00b3a6a0a99eeb661c30e0fd9c31b70fc70ab`:
  Source `37473708159`, automatic Native `37473708114`, independent
  129 tests passed. Three artifact ZIP digests verified; all 89 iOS/47 Watch
  design PNGs match the individually reviewed #387 baseline byte-for-byte.
  Native compiled merge `359fd969…` has no mobile/ios diff from PR head.
  New XCTest durable enrollment regression passed (0.292 s).
  Superseded head fc8a6028 CI 37470175422/37470175346 consumed; later
  87a00b3a already passed Native. Do not reopen the obsolete test failure.
  P2 `6019848254` and screenshot completion `6020049168` handled.
- #388 final head `4a1108aaa6a87b78a9032149a1fecdeff65b7827`,
  merge `9f56c35b`; Source `37480859996` passed. Original 9 and extended
  15 tests (including those 9) passed; bash syntax passed. Prior P2
  `6018586650` resolved: run + summary + genuine comment returns cursor=3.
  Claude fix reply `6018681148`, final verdict `6019983448` handled.
  Preserve Claude/unknown provenance and explicit --run/--release outcomes.
- #387 head `4504b2994331c93b16d5282afd9c205807680a23`,
  merge `c07114b3`; Source `37442092046`, automatic Native
  `37442091978`, independent 130 tests passed. Full live `37456686597`
  Watch passes; its separate iOS journey failed missing prep-library row.
  Progress `6015347738`, P2 `6016542546`, screenshot verdict
  `6017410544`, integration decision `6019856320` handled.
- RCA `6017108044` confirmed pre-existing product race; it supersedes
  retry/options comment `6016510080`. #387 Watch has no regression.
  Final combined live iOS/Watch verification belongs to #389.

Deduplicate these heads/comments and the release/Native run IDs below.
Earlier completed reviews are archived. New substantive feedback/new heads
are actionable; own comments/commits/CI/duplicates never reset quiet time.

## Unfinished work

- `PR-FEEDBACK-CONTINUOUS` — `queued`: resume existing cursor and
  same-turn feedback waiter. Review exact head/related tests/required Native
  artifacts, comment P1/P2/non-blocking, merge/delete branch when clear.
- `PR-389-HALF-START-ENROLLMENT-REVIEW` — `in-progress`: re-review 4e7e7eb1.
  P2 6021873468 posted; collect independent/Native evidence and close named
  review resources, then await author fix. Require behavior regression for
  manual pause/foreground resume with gate pending and stale/account intent.
  Full live only on corrected head; original assertion stays intact.
- `PR-387-IOS-JOURNEY-REGRESSION` — `blocked`: product RCA/P2 carried by
  #389; final head must pass Native and full live on existing build80 backend,
  including queue trace, 后九→前九/relaunch prep and Watch rendered-marker.
- `IOS-STATUS-CONTRAST` — `queued`, non-blocking: existing dark system
  status-bar text on dark iOS map/review screens; no new rendering change.
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
- Synthetic pin sheet: HTTP 200, 18.901 s, exact date/three holes/front facts.
  HTTP/2 package: 203,928 raw/~17,855 wire bytes; loopback 1.72–2.78 s,
  four tunnel requests 2.10–2.34 s, all HTTP/2/200.
- Origin: `https://developments-deputy-joined-logged.trycloudflare.com`.
- Production `aicaddie-release-d7f69971-production-20260925`, port `39055`,
  revision `d7f699712f7ac6cba41d97c420c405e090625caf`.
- Evidence root: `/home/jason/garmin-ai-caddie-data/operations`.
  Release: `release-main-3614bf6f-20261006`.
  #387: `pr387-4504b299-20261006`; full live iOS remains failed, Watch passed.
  #388: `pr388-4a1108aa-20261006`; replay/provenance/install/closure evidence.
  #389: `pr389-87a00b3a-20261006`; exact source, 129 tests, three ZIPs,
  per-frame hashes/native log/source provenance and cleanup receipts retained.

## Owned resources and waits

- #389 final-head review: read-only snapshot planned at
  `/dev/shm/garmin-ai-caddie-pr389-4e7e7eb1-20261006`, expires Oct 7 17:35 UTC;
  --rm test container `codex-pr389-4e7e7eb1-tests-20261006`. Evidence/manifest
  `operations/pr389-4e7e7eb1-20261006`; no service/deps/new worktree.
- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`,
  loopback `39089`; API image
  `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`.
  Matching full-SHA sync image remains.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics `39110`.
  Isolated DB `aicaddie_candidate_3614bf6f_20261006`; private-root/config
  in release evidence remain for owner testing; existing key protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13. Exact allow-list: release evidence resource-manifest.md.
- Build79 old candidate/image tag/source retired with 1,131 files verified
  in backup. Original production volume/database protected; old tunnel absent.
- No implementation worktree/feedback waiter active. Terminal 18304 ended
  on superseded cancelled run 37490470913; stop waiting and review new head.
  #389 af7a837e snapshot/test container/tmpfs closed with source backup/use
  checks. API timeout/partial curl logs retained; fresh signed IPv4 resumes
  completed all ZIPs. Terminal 63920 consumed; no verification terminal live.
  Evidence/receipts: `operations/pr389-af7a837e-20261006`.
  Six local helpers removed after exact remote checksum verification; small
  `.codex-pr389-af7a837e-local-cleanup.json` retained with earlier allow-list.
  No new service/deps/port/worktree; production/build80 health proof retained.
  #389 snapshot/test tmpfs/container and #388 snapshot/isolated test temp
  removed after exact source backup/use checks. Receipts retained.
  Capacity/health closeout: 67 GiB root, 3.3 GiB shm; production/build80 HTTP 200.
- Fourteen local review/merge helpers removed after byte/checksum validation
  of remote backups; allow-list retained in #388 evidence and small local
  `.codex-pr387-388-389-local-cleanup.json`. Preserve unrelated old
  `.codex-*` and dirty `ops/pr_feedback_monitor.sh`.
- #389 original mount/CWD verifier errors retained; isolated tmpfs run 129 OK.
  Initial gh artifact timeout retained; fresh signed IPv4 curl resumed it;
  all three final ZIP digests verified. Never log credentials/signed URLs.
- Existing deployed waiter updated from verified #388 source, old copy backed
  up under #388 evidence. Cursor SHA unchanged; waiting method not changed.
  Path: `/home/jason/garmin-ai-caddie-data/operations/blocking-waits/wait_for_conclusion.sh`.
  SHA-256: `37dd8727b1f47c09d56512b52765dc2984dafe6cf90381803d302338a6048179`.
  Cursor: `operations/blocking-waits/feedback-cursor`; never edit/delete.
- Last feedback completion:
  `wait-feedback-pr--20261006T151251Z-2468825.log`; current RCA/new heads
  processed. Buffered events may repeat reviewed #387/#388/#389 items.
  Terminal **11381** ended on obsolete cancelled CI and is consumed.
  No feedback or verification terminal active at final-head review intake.
  Buffered events can repeat handled fix/rebase replies and green CI.
- Same-turn background terminal: sleep 300000 ms, then one write_stdin until
  one-line conclusion. No idle gh run view/process/state checks, duplicate
  waiter, independent waiter tmux, or CI-only commits. Fixed through Oct 9.
  Shared `gh-feedback@garmin-ai-caddie.timer` unchanged.
- Every GitHub comment/review ends `_Generated by Codex_`; commits carry
  `Generated-by: Codex`. Own commits/CI do not wake broad waits.

## Next action and stop conditions

Review/integration/resource closure pushed as **6b2418e4**, with verbatim
archives explicitly added despite docs/archive ignore rule (3a896d10).
P2 re-review/resource closure and verbatim archives pushed as **d226518b**.
Review new #389 head 4e7e7eb1, verify CI/native artifacts, then full live
(fixture=false/full/live preflight) on retained build80 backend.
Commit actual review/resource work, then resume same-turn feedback wait.
No CI-only result commits; no merge before blocking findings resolve.

Quiet interval suspended while #389 is open. Once reviews close and no PRs
remain, establish a fresh conservative baseline. End after 48 quiet hours/no
open PRs, or absolute end **2026-10-09 23:59 UTC**, with resource handoff.
Own commits/comments/CI and duplicates never reset the clock.

Keep this file ≤200 lines/current-only. Read it after compaction, inspect
Git/agent state and resume this slice. Archive superseded text verbatim.
