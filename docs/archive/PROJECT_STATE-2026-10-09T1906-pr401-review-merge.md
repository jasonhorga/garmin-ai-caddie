# HISTORICAL ARCHIVE — NON-AUTHORITATIVE

Archived 2026-10-09 19:06 UTC on PR401 review/merge/resource closure. Prior ledger preserved verbatim.

# Garmin AI Caddie Project State

> Short durable continuity ledger. Only this file is authoritative.
> Dated docs/archive/ files are historical and non-authoritative.

**Updated:** 2026-10-09 19:00 UTC
**Canonical branch:** `main`; latest integrated product code
`d340c5ba2fafbae3a88b84caa2a2edd211610431` (#400 merge)
**Current slice:** `PR-FEEDBACK-CONTINUOUS` — `in-progress`

## Current state

Final re-review at #401 `bd8575ea65665b659dc21f165d641a283835f365`.
CI37973756337 and Native37973756093 are green. Source confirms capacity/freshness
now guards actual dequeue, fresh publication restarts existing queued jobs, and
new selector regression covers unknown/stale/insufficient/exact-one-course room.
Independent contracts and latest Native provenance/142-PNG comparison pending.
Prior findings/evidence below remain references until final review closure.

#401 is OPEN, branch `claude/speculative-prefetch-20261009`,
head `1ce1dd09af985fc03ce71defc07ab6cee18ba8ed`, merge-base `d340c5ba`;
main at review `0aeb82f4`. Review comment **6086839589**:
- Remaining P2: freshness/capacity only gates NEW speculative rows. Actual
  next-job/worker selection still accepts existing rows with unknown, stale or
  exhausted capacity. Require fresh capacity before dequeue, a wake-up of
  existing reserved rows after measurement, and actual selector/worker regressions.
- Prior preparation P2 closed: dequeue/preemption use the preparation token;
  callbacks during preparation, recovery afterward and explicit prep behavior pass.
- Visual gap closed: new actual simulator `settings-prefetch-cellular.png`
  manually inspected: default-off switch, full label, two-line footer/system List.
  SHA256 `927b35003a7195a3c27c1d6342f055c838c0a247dec2257d48b4ad5ba58f0232`.

Latest exact-head evidence:
- Independent homeserver contracts: **126/126, 5.412 s, OK**.
- CI `37969493839`: all green. Native `37969493841`: live production
  evidence, iOS **758/0**, Watch **448/0**. Two new model tests and screenshot
  capture explicitly passed in the Native log.
- Native evidence `d2edaf95a7fe555da962cfe38d5e221b83f0fb33` parents
  are main `0aeb82f4` and the exact reviewed head.
- PNG comparison: **142** current, **141** baseline-identical, one added settings
  image inspected as above; no changed/removed images.
- Remaining P2 is source-path review; no independent Swift reproduction claimed.
- Evidence at
  `/home/jason/garmin-ai-caddie-data/operations/pr401-1ce1dd09-20261009`:
  source tar, contracts, Native provenance/logs/artifacts/hash comparison,
  review, closed manifest and cleanup log. Prior `7d67a40d` evidence retained.

#399/#400 final heads/comments/CI/reviews/merges and retrospective events handled.
#400 PASS `6085501723`, merged/deleted. #401 `7d67a40d` review `6086245677`
and author fix/review requests at17:54:01 /18:13:49 UTC handled; do not repost.
Own docs CI ignored. Completed detail remains verbatim in dated archives.

## Unfinished queue

- `PR-FEEDBACK-CONTINUOUS` — `in-progress`: await #401 final capacity fix;
  verify new head/tests/Native artifacts, then PASS/merge if clear.
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
- For #401 follow-up compare to the reviewed 142-PNG artifact baseline at
  `operations/pr401-1ce1dd09-20261009/native-artifacts`.
  Earlier main baseline remains `operations/pr399-f9aa623e-20261009/native-artifacts`.

## Owned resources and wait boundary

- PR401 `1ce1dd09` snapshot removed (27,924,375 bytes); named --rm container
  absent; production running. Source/log/Native originals retained.
- Local settings PNG (122,548 bytes) SHA-checked then removed, empty owned
  inspection directory removed. Closed remote manifest records both cleanups.
- Active final review snapshot `/dev/shm/garmin-ai-caddie-pr401-bd8575ea-20261009`,
  --rm container `codex-pr401-bd8575ea-contracts-20261009`; expires23:59 or review end.
  Manifest `.codex-pr401-bd8575ea-review-manifest.md`; evidence under
  `operations/pr401-bd8575ea-20261009`. No worktree/env/service/subagent/local image.
- Local PR401 controls/manifests/review retained as receipts.
  Preserve unrelated dirty `ops/pr_feedback_monitor.sh` and historical `.codex-*`.
- Deployed waiter: `operations/blocking-waits/wait_for_conclusion.sh`.
  No wait pending at ledger write; after push start one `--feedback` terminal,
  retain handle in same turn; `clock.sleep(300000)` → one `write_stdin`
  until one-line conclusion. No liveness checks/replacement waiter.
- Comments end `_Generated by Codex_`; commits end `Generated-by: Codex`.
  No CI-result-only commits.

## Next action and stopping

Resume sole feedback waiter. Ignore handled events/own docs CI. On #401 fixes,
check queued-job capacity enforcement and wake-up, actual flow regressions,
exact-head contracts and Native/artifact provenance; compare all 142 images to
latest reviewed baseline. PASS/merge/delete only when remaining P2 closes.

Absolute stop: **2026-10-09 23:59 UTC**. Earlier stop requires 48 hours without
external PR events and no open PRs. Last handled author event:18:13:49 UTC.
Keep ledger ≤200 lines; archive historical detail verbatim before replacement.
