# Plan 1 Task 4 Mobile Event Durability Verification

Date: 2026-07-24 UTC
Verified production HEAD: `83c91675c629d938bc7f653b125093e1564a66d8`
Verified tree: `650f90507a4728809b12d485b969da9b635367a9`

## Bounded requirement and exclusions

The bounded execution card is
`../task-cards/2026-07-23-plan1-task4-mobile-event-durability.md`. Task 4
finishes the existing v1 mobile event durability and iOS replay slice. Its
approved behavior is:

- exact retry after filtering identities already committed by another request;
- one batch append authority with committed-prefix and pending-marker crash
  recovery, one event-log open and fsync for a non-empty append, and strict
  corruption handling;
- durable monotonic ACKs bounded by the committed partition high-water;
- iOS torn-EOF repair, full effective-envelope comparison, durable reload
  before cursor advance, and ACK only after a complete replay page succeeds;
- media-upload success that does not rewrite the event log or alter the
  effective event batch or idempotency key; and
- one Python/Swift privacy policy and byte-identical sanitizer fixture that
  redacts structural fields, secrets, local media, and cross-platform paths
  while preserving the event identity triplet.

Task 4 does not add Task 5 prepared request-body or receipt-roster authority,
DomainLedger/outbox/receipt state, sync-marker removal, finish/discard lifecycle
changes, v2 round schemas, reducers, scoring, AutoShot, maps, course acquisition,
or installation. The final diff does not introduce any of those later-task
authorities.

The storage threat model frozen for this task is process failure among
cooperative workers using the application-owned player partition. It is not a
hostile same-UID local-filesystem security boundary. That distinction is
recorded under deferred findings below and was not silently added to the
completion contract during review.

## Production and remediation evidence

The final linear history after the verified Task 3 HEAD is:

- `0664ec0391b84421b36fc1017953d1bd445ad6bb` — record the bounded Task 4
  execution card and confirmed RED evidence;
- `1d94f4eeda9551b977e7746a11878bdf361a454f` — implement committed-prefix
  fencing, retry/replay repair, shared sanitizer behavior, and production-path
  regression coverage;
- `83c91675c629d938bc7f653b125093e1564a66d8` — close final backend, Swift,
  Foundation, HTTP replay/ACK, and review-remediation cases at the exact
  candidate used by all final gates.

The earlier candidate chain `964fef2` through `8ef2996` remains historical
implementation evidence. It is not the completion authority. The live
remediation baseline is
`311c6285e86adfff54dbe8e25abfef160ba4c220`, and the final candidate has that
verified baseline in its ancestry.

The final candidate changes 17 files relative to the baseline, with 5,089
insertions and 297 deletions. Most of that volume is crash/fault and native
regression evidence: 1,193 added/modified lines in the Python store tests,
1,078 in `OfflineStoreTests`, and 751 in `LiveRoundAppModelTests`. The shared
`ai_caddie/llm/llm_providers.py` change is a demonstrated privacy dependency:
it aligns the already-shared secret/path redactor with the Task 4 canonical
sanitizer cases and has direct regression coverage in `tests/test_llm_providers.py`.

Before branch integration, the candidate commit had sole parent `1d94f4e`, its
tree was `650f9050`, the worktree diff against the candidate was empty, and the
staged index independently wrote the same tree. The feature branch was advanced
with compare-and-swap rather than by rebuilding the candidate commit, then
pushed publicly.

## RED to GREEN evidence

The bounded card records the observed production REDs at the remediation
baseline, including:

- mixed globally committed/new exact retry ending in
  `idempotency_key_body_mismatch`;
- a non-empty 5,000-row append opening the event log five times;
- pending-target extra bytes being accepted;
- complete untracked JSON being truncated as though it were a torn EOF;
- cross-boundary sequence validation restarting at zero;
- Python/Swift sanitizer drift and uncovered `/opt`, `/etc`, `/srv`, UNC,
  lowercase Windows-user, and Unicode bearer cases; and
- Native Mobile CI run `30036446529`, where a raw dictionary JSON-order oracle
  failed despite unchanged effective events.

The final regression matrix replaces that raw-order oracle with effective
`EventBatch`, idempotency-key, physical-log, actual HTTP replay, and ACK
assertions. It exercises the final public production boundaries and explicit
fault hooks. Fresh final GREEN evidence is listed below.

## Independent reviews

The final independent specification verdict for `83c91675` was `SPEC PASS`:
zero Critical and zero Important findings. A proposed pathname/symlink issue
was adjudicated as a separate hostile-local-writer threat model rather than a
missing invariant in the frozen cooperative-worker/process-crash task.

The final independent code-quality review reported:

- Critical: 0;
- Important: 0;
- Minor: 1; and
- ready to integrate: yes.

The Minor finding is that a crash after Swift creates a named
`.events.jsonl.*.tmp` file but before `renameat` can leave an orphan; normal
open does not currently reclaim those names. This can accumulate storage after
repeated crashes but does not expose uncommitted events, advance ACK, change
retry identity, or violate privacy. It is retained as an explicit follow-up,
not used to mutate the exact already-verified candidate.

## Homeserver final verification

Final verification used a fresh clone of the publicly pushed feature branch:

`/home/jason/codex-runs/garmin-ai-caddie-task4-final-83c9167-20260724-a1`

It resolved to exact `83c91675` and remained clean after every command. Logs
with exact command, HEAD, timestamps, exit code, test count where applicable,
and clean-status footer are in:

`/home/jason/codex-runs/garmin-ai-caddie-task4-final-logs-83c9167-20260724-a1`

Fresh commands and results were:

```text
/home/jason/.local/bin/uv run python -m unittest \
  tests.test_mobile_event_store_phase0 \
  tests.test_server_v2_mobile \
  tests.test_mobile_contracts \
  tests.test_mobile_reconciliation \
  tests.test_member_event_partition \
  tests.test_evidence_player_scope -v
  -> Ran 271 tests in 12.513s; OK; exit 0

/home/jason/.local/bin/uv run python -m unittest \
  tests.test_contract_codegen tests.test_contract_authority -v
  -> Ran 89 tests in 1.936s; OK; exit 0

npm ci
  -> installed/audited 240 packages; exit 0

web_v2/node_modules/.bin/vitest run src/contracts/generated.test.ts
  -> 1 file passed; 1 test passed; exit 0

/home/jason/.local/bin/uv run python tools/contracts/generate_contracts.py
  -> exit 0; no generated drift; clean worktree

git diff --no-renames --name-only -z 311c628..HEAD |
  /home/jason/.local/bin/uv run python tools/contracts/check_authority.py
git diff --no-renames --name-only -z 1d94f4e..HEAD |
  /home/jason/.local/bin/uv run python tools/contracts/check_authority.py
  -> both exit 0

git diff --check 311c628..HEAD
git diff --check 1d94f4e..HEAD
cmp contracts/canonical/fixtures/mobile_event_sanitizer_golden.json \
  mobile/ios/AICaddieTests/Fixtures/mobile_event_sanitizer_golden.json
git status --porcelain=v1
  -> all exit 0; status empty
```

The initial fresh-clone Python attempt used bare `uv` in a non-login shell and
ended before test discovery with exit 127 because that PATH omits
`$HOME/.local/bin`. The exact same test command was immediately rerun with the
verified absolute executable path and passed 271/271. The failed environment
attempt is preserved as `python-consumer.log`; it is not counted as a test
failure or hidden from the evidence.

`npm ci` reported four dependency advisories (one low, three high) without
changing the lockfile or worktree. Task 4 changes no web dependency. Dependency
remediation remains a repository maintenance concern and is not silently
mixed into this durability candidate.

Final log SHA-256 values are:

| Log | SHA-256 |
|---|---|
| `python-consumer-rerun1.log` | `e38e135c1a252b940db35f2f67a3ab1a7e3446ea91b25ab3070a59207ef80440` |
| `python-contracts.log` | `3115845e5e5d85e7682d506c0c489221794822fd708f6dc3cd4b826807ae2ba3` |
| `npm-ci.log` | `ad2342ef7b030922ea4a918b3ecde0a395777169fc90fe00730c4563e6f8bfbd` |
| `vitest.log` | `eba52649d9af9396b923ac54b2907c28c29f13265928d11f2d305d74460ec360` |
| `generator.log` | `8dd0956fa22c0541b132527af7d98f933dc91e8b2e881c4b4630351760efe5ad` |
| `authority-ranges.log` | `f64f706f738aa3a190d20b669cc8009b83111b8b7c0182f93adc4bd8902662eb` |
| `mechanical-gates.log` | `96fd945167aaea27a773db3ad8a66e9a11b9d126c7f7d5e164b4d18d897925de` |

## Native exact-SHA evidence

Native Mobile CI run
[`30060357954`](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30060357954),
job `89380592683`, checked out exact SHA `83c91675` on `macos-15` and completed
successfully:

- iOS app target: 108 tests, 0 failures;
- real iOS UI flows: 3 tests, 0 failures; and
- Watch target: 66 tests, 0 failures.

The complete public run log independently hashes to
`ad105b40cea4f72375154d6c8d700ec44e03c3ba145082db8be3b8686f41d919`.
Because the branch integration preserved the exact candidate SHA, this native
evidence remains exact and was not replaced by a redundant rerun.

## Verified artifact digests

| Artifact | SHA-256 |
|---|---|
| `ai_caddie/caddie/mobile_event_store.py` | `0fd544969843f0f871014fd224a87681eef88f9b71bcda02aff3771d9e5a30e9` |
| `mobile/ios/AICaddie/Services/OfflineStore.swift` | `de8a6437138797c5c6d8d14cf727596381a6989cc035127e83dbae175f67b842` |
| canonical sanitizer fixture | `123cba00d8ead0ab2388f508bc9119eba4ba888755b087924839f57947e8aa37` |
| generated Swift sanitizer fixture | `123cba00d8ead0ab2388f508bc9119eba4ba888755b087924839f57947e8aa37` |
| `ai_caddie/contracts/generated.py` | `5bd150ca72dc852f774a9e3c1a10f37b432fac8eb415b80490fe6bf6c10e9b3c` |
| `mobile/ios/AICaddieDomain/GeneratedContracts.swift` | `8d767752fe623a656705e2788dba146d40ebf34d89f171dce43126deddbb7d1b` |
| `web_v2/src/contracts/generated.ts` | `aca4517f8618a628139f223b8ac4bb8d29e5370af9c102b4d51b92c664d65c25` |

All three generated declarations carry the same source pin:
`75acf5110fec370fb7fb42340552429eda55377fc417729ad77c4e0869f5bc21`.

## Deferred findings

These findings are real but outside the frozen Task 4 completion boundary:

1. define a hostile local-filesystem writer threat model and, if adopted,
   harden trusted-parent/ownership/ACL, symlink/FIFO, and lock-inode behavior as
   one coherent security boundary rather than adding a partial pathname check;
2. coordinate `players.delete_player` with in-flight partition operations by a
   tombstone/partition-lock protocol; and
3. reclaim store-owned orphan `.events.jsonl.*.tmp` files on authority open (or
   use an unnamed temporary mechanism), with the required directory barrier.

None is permitted to disappear from the backlog, and none is allowed to
silently widen Task 4 after its approved process-crash/cooperative-worker
contract passed.

## Gate result and POP

Plan 1 Task 4 satisfies the Execution Index definition of `VERIFIED` at exact
production HEAD `83c91675`: bounded requirements and exclusions are recorded,
production and RED-to-GREEN evidence exist, fresh homeserver gates pass,
native evidence is exact-SHA green, specification review is green, and code
quality has zero open Critical or Important findings.

POP returns to the S70 Unified Golf Program Execution Index. The next work is
to extract Plan 1 Task 5 into small, independently terminable packets before
implementation; this record does not pre-approve any Task 5 behavior or allow
Task 4 review to continue expanding.
