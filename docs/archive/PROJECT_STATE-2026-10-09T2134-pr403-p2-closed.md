# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived at 2026-10-09 21:34 UTC after fd73dca5 code/Native review and resource closure.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 21:31 UTC
**Canonical branch:** `main`; product merge `188399c9` (#402);
review bookkeeping `fe44a8a9`
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state

#403 author fix head `fd73dca520b148a4afd934acb77f643a0346a2fa` fetched.
Source reviewed: generation/intent fence closes obsolete completion paths;
A→home and deterministic A→B regressions added. Independent exact contracts,
Native37990736669 evidence/regressions/142-PNG comparison pending.
CI37990736702: backend/frontend green, docker FAILURE (author reports Docker
Hub429, rerun planned). Required CI must be green before PASS/merge.
Author reply at21:19:02 (IC_kwDOSeO0vs8AAAABavVhQQ) received.

#403 OPEN/ready, exact reviewed head
`e5788c79e369e7bad050b92c19655827ae49627e`,
branch `claude/new-area-prefetch-20261009`, merge-base `188399c9`.
P2 review comment **6089071054**; do not merge yet.

P2: a newer nearby result clears/replaces pendingNewArea, but an older Tee pass
may still park its request again, queue old courses or publish its anchor.
Need a verifiable current intent/pass identity (including no-area invalidation),
with completion validation before park/enqueue/anchor. Preserve same-area
yield/resume; drop superseded areas. Requested model regressions: A→home/covered
and A→B with old completion released after accepting the new result.
Source-path finding only; no independent Swift interleaving reproduction claimed.

One nonblocking description correction: leaving for home and returning does not
change the persistent anchor; another newly anchored area is needed. Keep the
bounded retry behavior if desired and describe it accurately.

Verification of current head is complete:
- Independent homeserver contracts **126/126, 9.496 s, OK**.
- CI `37986519475` green; Native `37986519318` live production,
  iOS **770/0**, Watch **448/0**. New nearby/blue-Tee and Wi-Fi cancellation
  regressions explicitly passed.
- Native evidence `20021cdfbff02b401b016587a530d054f2c23a41` parents
  are main `fe44a8a9` and the exact reviewed head.
- All 142 PNGs downloaded; **141 identical /1 expected change** against #402.
  `settings-prefetch-cellular.png` manually passed: full label/default off,
  two-line footer without clipping. Other design/Watch images unchanged.
- Evidence:
  `/home/jason/garmin-ai-caddie-data/operations/pr403-e5788c79-20261009`
  (source/contracts/Native/provenance/hash comparison/review/cleanup originals).

#399–#402 are merged, branches deleted, all final heads/author requests/CI/PASS/
merge events handled. #402 PASS 6088323923; prior request at19:42:30 handled.
#403 author ready request at20:41:09 (IC_kwDOSeO0vs8AAAABau03lA) handled in
this review. Deduplicate retrospective events and own comments/docs CI.
Completed details preserved verbatim in dated archives.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: verify #403 fd73dca5 fix/Native;
  close resources, then await Docker recovery before merge.
- `NATIVE-FIXTURE-LAYOUT-STABILITY` — `queued`: 八号铁164 label variation; nonblocking.
- `IOS-STATUS-CONTRAST` — `queued`: nonblocking dark navigation/status text.
- `OWNER-DEVICE-BUILD82` — `evidence-open`: paired iPhone/Watch validation remains owner work.

## Live verification baseline

- Internal TestFlight **0.1.0 (82)**, upload `37774511661`, latest claimed
  release; excludes #395 onward. Apple read-only `37776197288`: VALID /
  IN_BETA_TESTING. IPA SHA256
  `f8e112b8bf75e4a33fad838bff39e69ec783679ba8a040091b957ec5cc896721`.
- API `https://caddie.taile36706.ts.net`; backend/sync revision
  `3614bf6f3805479f8d13de65eeec4f0ad7871f22`; production container
  `aicaddie-release-3614bf6f-production-20261008`, loopback39055.
  Protected cutover retained; sync last recorded 502 rounds /501 scorecards /
  501 shots /ok /done. HTTP/2 homeserver 3/3 HTTP200, 1.82–2.57 s;
  not Apple-runner path evidence.
- Latest reviewed UI baseline: `operations/pr403-e5788c79-20261009/native-artifacts`.
  Source still has P2; #402 merged baseline remains retained.

## Owned resources and wait boundary

- Reserved snapshot `/dev/shm/garmin-ai-caddie-pr403-fd73dca5-20261009`,
  --rm container `codex-pr403-fd73dca5-contracts-20261009`, expires23:59/review end.
  Manifest `.codex-pr403-fd73dca5-review-manifest.md`; evidence under
  `operations/pr403-fd73dca5-20261009`. No worktree/service/subagent.
  Prior PR403 snapshot removed (28,008,871 bytes); --rm container absent; production
  running. Local settings inspection PNG/directory removed after hash/open-file
  checks. Remote originals and cleanup receipts retained.
- Local controls/manifests/reviews retained as receipts; preserve unrelated dirty
  `ops/pr_feedback_monitor.sh` and historical `.codex-*`.
- Deployed waiter: `operations/blocking-waits/wait_for_conclusion.sh`.
  No wait pending at ledger write; after push start one `--feedback` terminal,
  retain handle in same turn; `clock.sleep(300000)` → one `write_stdin`.
  Only its one-line conclusion signals work; no liveness/replacement checks.
  Existing timeout option bounds the wait before the absolute cutoff.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.
  No CI-result-only commits.

## Next action and stopping

Finish fd73dca5 verification/close resources, then resume sole feedback waiter.
For #403 fix, fetch exact head and verify requested
intent interleavings plus Native evidence/artifacts; comment PASS and merge/delete
only when P2 is closed. Review new ready PRs after required CI. Ignore handled
events/own docs CI; do not change the waiting method.

Absolute stop: **2026-10-09 23:59 UTC**. Earlier stop requires 48 hours without
external PR events and no open PRs. Latest author reply:21:19:02 UTC.
Keep ledger ≤200 lines; archive historical detail verbatim before replacement.
