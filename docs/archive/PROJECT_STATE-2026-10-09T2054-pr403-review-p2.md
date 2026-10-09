# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived at 2026-10-09 20:54 UTC after PR403 exact-head review and resource closure.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 20:42 UTC
**Canonical branch:** `main`; latest integrated product code
`188399c9f63ba35aedffcc0a4720bfe594bc914a` (#402 merge)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state

#403 OPEN/ready, head `e5788c79e369e7bad050b92c19655827ae49627e`,
branch `claude/new-area-prefetch-20261009`, merge-base `188399c9`.
CI37986519475 green; Native37986519318 pending at discovery. Exact source and
new-area lifecycle/cancellation review in progress; independent contracts and
Native provenance/screenshots pending. Source-path concern: an in-flight area's
completion can re-park/queue it after a newer nearby answer clears/replaces it.

#402 is MERGED; branch `claude/remeasure-retry-20261009` deleted after exact
ref validation. PASS comment **6088323923**.
Exact reviewed head `13bcb2856e3408de81f490b895e2323d2c887704`;
merge `188399c9f63ba35aedffcc0a4720bfe594bc914a`.
The #401 nonblocking measurement retry is implemented: clear the in-flight flag
before deciding whether a stale walk needs one additional scan. Fresh measured
capacity and foreground/network/round gates still control speculative dequeue.

Verified evidence:
- Independent homeserver contracts: **126/126, 12.229 s, OK**.
- CI `37978205150` all green. Native `37978205170`: live production
  evidence; iOS **760/0**, Watch **448/0**. New bounded-retry regression
  explicitly passed (0.008 s).
- Native evidence `e3687b95078b67d5545b710445245825627bbe70` parents
  are main `2502a0c9` and the exact reviewed head.
- **142/142** design/Watch PNGs downloaded and byte-identical to the
  already manually reviewed #401 baseline.
- Evidence at
  `/home/jason/garmin-ai-caddie-data/operations/pr402-13bcb285-20261009`:
  source tar, contracts, Native logs/artifacts/provenance/hash comparison, PASS,
  exact-head merge/branch receipt, manifest and cleanup log.

Bounded limitation disclosed in PASS: if the retry is also overtaken by writes,
queued guesses wait for the next normal trigger. Capacity safety remains gated.
The regression simulates stale timestamps; no exhaustive real disk-interleaving
reproduction is claimed. This remains nonblocking.

#399/#400/#401/#402 heads, author requests, review replies, CI and merges handled;
deduplicate retrospective events. #401 prior comments 6086245677 /6086839589 /
6087423825 handled. Own docs CI ignored. Completed details preserved verbatim
in dated archives.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: review #403 exact head/Native,
  post findings or PASS and close resources before returning to feedback wait.
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
- Latest 142-PNG verified baseline:
  `operations/pr402-13bcb285-20261009/native-artifacts`.
  Prior #399/#401 evidence retained.

## Owned resources and wait boundary

- PR403 reserved snapshot `/dev/shm/garmin-ai-caddie-pr403-e5788c79-20261009`,
  --rm contracts container `codex-pr403-e5788c79-contracts-20261009`;
  expiry23:59 or review end. Manifest `.codex-pr403-e5788c79-review-manifest.md`;
  evidence `operations/pr403-e5788c79-20261009`. No worktree/service/subagent.
  Prior PR402 snapshot removed (27,968,951 bytes); named --rm container absent;
  production running. Cleanup receipt in the evidence directory.
- Original source/log/Native evidence and local controls/manifests/reviews/merge
  requests retained as receipts. Preserve unrelated dirty
  `ops/pr_feedback_monitor.sh` and historical `.codex-*`.
- Deployed waiter: `operations/blocking-waits/wait_for_conclusion.sh`.
  No wait pending at ledger write; after push start one `--feedback` terminal,
  retain handle in same turn; `clock.sleep(300000)` → one `write_stdin`
  until one-line conclusion. No liveness checks/replacement waiter.
  Use existing timeout option to return before the absolute owner cutoff.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.
  No CI-result-only commits.

## Next action and stopping

Finish PR403 verification/review; then resume sole feedback waiter. Ignore
handled events/own docs CI. New ready PRs
are actionable after required CI; independently test exact head, verify Native/
screenshots where applicable, post findings or PASS, and merge/delete if clear.

Absolute stop: **2026-10-09 23:59 UTC**. Earlier stop requires 48 hours without
external PR events and no open PRs. New PR403 discovery at20:38 UTC resets quiet;
prior author request at19:42:30 UTC handled.
Keep ledger ≤200 lines; archive historical detail verbatim before replacement.
