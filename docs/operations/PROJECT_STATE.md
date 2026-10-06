# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated files in docs/archive/ are historical and non-authoritative.

**Updated:** 2026-10-06 17:54 UTC
**Canonical branch:** `main`
**Latest integrated code:** `9f56c35b61809069537d8c3f09c28a6e3347d8d5` (#388)
**Internal app/API/sync source:** `3614bf6f3805479f8d13de65eeec4f0ad7871f22`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current status and deduplication

Claude is restored. Only #389 is open; #387/#388 merged, branches deleted.
#389 head `4e7e7eb16632db849c7b806b3096489482d3eaf1` fixes P2 6020952816
(real foreground installer and automatic worker dequeue gate bypass).
New P2 `6021873468`: retained explicit requests cannot resume through the
start gate; stale-worker cleanup precedes generation check; account rebind
retains intent; active-row early return skips registration. No merge.
Author reply `6021043095` read; do not answer it twice.

Exact-head evidence complete; evidence verdict `6022166928` handled:
- Source `37498292084` / Native `37498292248` passed.
- Independent 130 tests, 18.573 s, OK; read-only Build80 image, no network.
- All three ZIP digests verified; all 89 iOS/47 Watch design PNGs equal the
  individually reviewed #387 baseline byte-for-byte.
- Native compiled merge `83a473d2b2f164e8359821088426ce8c324979f4` has no
  mobile/ios diff from reviewed head; real foreground/per-job XTests passed.
- Exact source backup verified; snapshot/container/tmpfs closed.
- Final full live run waits for corrected head; original assertion intact.
- Review record: `docs/operations/2026-10-06-pr389-download-intent-lifetime-review.md`.

Earlier heads/comments consumed; detailed proof archived:
- #389 af7a837e: Source 37491131543 / Native 37491131642 / 130 OK /
  136 matching PNGs. P2 6020952816 / evidence 6021181763 handled.
- #389 87a00b3a: Source 37473708159 / Native 37473708114 / 129 OK /
  136 matching PNGs; P2 6019848254 / evidence 6020049168 handled.
- Author replies 6019989194/6020075979 handled. Intermediate 41857121
  runs 37490470913/37490470917 cancelled, superseded; do not reopen.
- #388 merge 9f56c35b, final 4a1108aa; original 9 + extended 15 tests OK.
  P2 6018586650 / fix 6018681148 / verdict 6019983448 handled.
- #387 merge c07114b3, final 4504b299; 130 OK/all design+Watch frames reviewed.
  Full live 37456686597 Watch passed; iOS failed missing prep-library row.
  RCA 6017108044 proved pre-existing race, product repair belongs to #389.
  Comments 6015347738/6016542546/6017410544/6019856320 handled.
  RCA supersedes 6016510080. Old review_pr376 is complete/resources closed.

Deduplicate heads, comments and run IDs. New substantive feedback/new heads
are actionable; own comments/commits/CI/duplicates never reset quiet time.

## Unfinished work

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: resume existing same-turn
  feedback cursor; review exact head/tests/Native artifacts; post P1/P2/
  non-blocking verdict and merge/delete branch only when clear.
- `PR-389-HALF-START-ENROLLMENT-REVIEW` — `blocked`: await P2 6021873468 fix.
  Re-test manual pause/real foreground resume with gate pending; automatic
  jobs still wait. Check stale-worker/account intent and active-row request.
  Then exact tests/Native artifacts and one final full live on Build80:
  fixture=false, capture_scope=full, live preflight=true; original assertion
  unchanged. Inspect queue latency trace, 后九→前九/relaunch prep journey,
  iOS/Watch runtime screenshots and Watch rendered marker before merging.
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

- Build80 candidate `aicaddie-release-3614bf6f-candidate-20261006`, port 39089;
  API image `garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006`.
  Matching full-SHA sync image retained for owner testing.
- Tunnel tmux `codex-release-http2-main-3614bf6f-20261006`, metrics 39110.
  Isolated DB `aicaddie_candidate_3614bf6f_20261006`; private config/key protected.
- Source `/home/jason/codex-runs/garmin-ai-caddie-release-3614bf6f-20261006`,
  expires Oct 13; exact allow-list in release resource-manifest.md.
- Build79 retired with verified 1,131-file backup; production volume/DB protected.
- No implementation worktree, review snapshot, test container or verification
  terminal active. #389 4e7e7eb1 snapshot removed 17:44:19 UTC after exact
  archive/use checks; cleanup receipts retained. ZIP interruption resumed;
  final digests pass. No new service/deps/ports/tunnel/volume.
- Six local helpers removed after exact remote backup verification; allow-list remains
  `.codex-pr389-4e7e7eb1-local-cleanup.json`. Earlier manifests/unknown
  `.codex-*` and dirty `ops/pr_feedback_monitor.sh` remain protected.
- Capacity baseline: 67 GiB root/3.3 GiB shm/3.9 GiB available RAM.
- Post-cleanup production and retained Build80 API health both HTTP 200.
- No feedback waiter active during review closeout. Terminals 11381/18304
  consumed obsolete cancelled runs. Resume existing cursor after commit.
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

Commit actual P2 review/evidence/resource closure and verbatim state archives
(explicit git add -f for ignored docs/archive), then resume same-turn feedback
waiter. Review author's fix; full live only when code findings clear.
Do not create CI-result-only bookkeeping commits.

Quiet interval suspended while #389 is open. Once no PRs remain, establish
a fresh conservative baseline; end after 48 quiet hours/no open PRs or
absolute **2026-10-09 23:59 UTC**, with owned-resource handoff.
Own commits/comments/CI and duplicates never reset quiet time.

Keep this file ≤200 lines/current-only; archive superseded text verbatim.
After compaction read this file, inspect Git/agent status, resume this slice.
