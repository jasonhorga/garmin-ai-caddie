# Plan 1 Task 4 execution card — mobile event durability

Date: 2026-07-23 UTC

## Authority and bounded outcome

- Scope/order authority: `../plans/2026-07-23-program-execution-index.md`.
- Normative dossier input: Task 4 of
  `../plans/2026-07-18-phase0-canonical-round-runtime.md`.
- Existing candidate history: `964fef2` through `8ef2996`.
- Remediation baseline: `311c6285e86adfff54dbe8e25abfef160ba4c220`.

Finish the existing v1 mobile event store and iOS replay slice so exact retries,
committed-prefix recovery, ACK bounds, effective-envelope comparison, and
privacy normalization remain correct across process failure. Preserve the v1
wire response. This task is complete only after focused homeserver tests and
native macOS tests pass and independent specification and quality reviews have
no open Critical or Important issue.

## Confirmed current RED evidence

These are production-path observations at the remediation baseline, not
proposed behavior:

- `[globally committed duplicate, new event]` initially returns
  `[duplicate_hash_match, accepted]`; the exact retry raises
  `idempotency_key_body_mismatch`.
- A 5,000-event append against a non-empty committed log opens
  `events.jsonl` five times, although it fsyncs that log once. The current
  one-open test starts from an empty log and misses this path.
- A valid pending target followed by extra physical bytes remains readable;
  recovery validates only `targetByteLength <= EOF`.
- A complete untracked JSONL row with no pending marker is silently truncated
  by the next append, which then succeeds. The same recovery branch is also
  used for a genuinely torn EOF fragment.
- Base-state pending validation checks the tail in isolation, so its sequence
  comparison restarts at zero and does not prove monotonicity across the
  committed-base/target boundary.
- `_append_row` remains as a forbidden per-row compatibility helper.
- Python sanitizes structural `schema` and `timestamp` while preserving the
  identity triplet. Swift sanitizes payload values only.
- Python currently leaves `/opt/...`, `/etc/...`, lowercase
  `C:\users\...`, and UNC paths visible. Python redacts `Bearer İ` and
  `Bearer ı`; those cases have no macOS/Foundation golden proof.
- Native Mobile CI run `30036446529` compiled the candidate but failed the
  byte comparison in
  `testLaterMediaUploadSuccessKeepsResponseLostRetryBodyAndKeyExact` twice.
  The two values came from independent default `JSONEncoder` instances over
  dictionary-backed values. That byte order is not a Task 4 invariant.

## Owned files

Production and direct tests may change only as required within these groups:

- Backend store: `ai_caddie/caddie/mobile_event_store.py` and
  `tests/test_mobile_event_store_phase0.py`.
- Shared privacy authority: the canonical sanitizer golden, its generated
  Swift resource, `tools/contracts/generate_contracts.py`,
  `tests/test_contract_codegen.py`, and the three generated declaration files
  whose common source pin changes when the canonical fixture changes.
- iOS durability/replay: `mobile/ios/AICaddie/Services/OfflineStore.swift`,
  `mobile/ios/AICaddie/AICaddieApp.swift`,
  `mobile/ios/AICaddieTests/OfflineStoreTests.swift`, and
  `mobile/ios/AICaddieTests/LiveRoundAppModelTests.swift`.

Any additional production file requires a demonstrated Task 4 dependency and
must be reported before it is edited. There is only one implementation writer
for all canonical, generated, backend, and Swift changes.

## Frozen invariants to close

1. Reconstruct the original append-candidate sequence after filtering exact
   identities already committed under other request keys. Rows committed under
   the current request key must be an ordered prefix of that candidate
   sequence. Full normalized request hash and identity-envelope mismatch checks
   remain fail closed.
2. A normal non-empty append uses one event-log handle across committed-prefix
   validation, recovery/read, and batch append, with one event-log flush/fsync.
   Remove `_append_row`; 5,000 rows remain one batch operation.
3. A pending target permits only the frozen base/partial-target/exact-target
   recovery states. Physical bytes beyond `targetByteLength` are corruption.
   The complete target, including the base/tail sequence boundary, must satisfy
   marker-owned row ordering and storage semantics.
   With no pending marker, only a non-decodable, newline-free torn EOF fragment
   may be truncated. Any complete untracked row or complete JSON value fails
   closed and is never blessed by another request. Recovery and corruption
   validation happen before a new request reservation mutates durable state.
4. Every newly created authority/lock directory entry receives the required
   file/directory durability barrier in creation order, including event and ACK
   lock files. Faults never expose uncommitted rows or advance ACK.
5. iOS compares the full normalized identity and effective transport envelope,
   repairs only torn EOF, reloads and proves every page event durable, and only
   then advances/ACKs that page. A real `LiveRoundAppModel` test must exercise
   torn EOF through HTTP replay and HTTP ACK. A syntactically complete JSON
   value that is not a valid `LiveRoundEvent` is corruption, not a torn
   fragment; it must be preserved and fail closed.
6. Media upload success removes pending media without rewriting the event log
   or changing the ordered effective `EventBatch` or idempotency key. Compare
   semantics and physical log bytes, not arbitrary JSON object member order.
   Capture the real production event POST body and `Idempotency-Key` across the
   response-lost retry rather than rebuilding either oracle in the test.
7. Python and Swift apply one golden effective-envelope policy: recursively
   redact secrets and filesystem paths, sanitize structural `schema` and
   `timestamp`, preserve exact `roundId/clientId/eventId`, and retain the
   existing local-media placeholder behavior. Golden coverage includes
   `/opt`, `/etc`, `/srv`, UNC, lowercase Windows user paths, `Bearer İ`, and
   `Bearer ı` on Foundation.

## Required RED matrix and implementation order

1. Add backend tests for mixed-roster exact retry, non-empty 5,000-event
   one-open/one-fsync behavior, pending-target extra bytes, torn versus complete
   untracked tails, cross-boundary pending sequence regression, and lock-entry
   durability. Run them at the current baseline on homeserver and record the
   expected failures before production edits.
2. Make the smallest backend state-machine change that closes those REDs. Run
   the complete existing Task 4 Python matrix after each behavior group.
3. Extend the root sanitizer golden first. Prove the new Python cases fail for
   the path leaks. Generate the byte-identical Swift fixture and common source
   pins on homeserver, then align Python/Swift production behavior.
4. Replace the flaky raw-body oracle with effective `EventBatch` equality,
   stable key equality, and unchanged physical `events.jsonl` bytes. Add a real
   response-lost-then-successful media/event sync test that captures both
   production POSTs; preserve a behavioral RED against `45bd2ec^`, where
   upload success still rewrote the event envelope.
5. Add the `LiveRoundAppModel` torn-EOF replay test that captures the actual
   replay and ACK requests, reopens `OfflineStore`, and proves durable contents
   before ACK. Add a Swift EOF case for syntactically complete invalid event
   JSON. Run the native suite on macOS/Foundation.

Tests use production public boundaries and explicit fault hooks. A passing test
that never failed for the intended reason, an import/compile error, private
rejected APIs, or a mock-only assertion is not RED evidence.

## Verification gates

Run from a fresh exact candidate clone on homeserver unless the command requires
macOS/Foundation:

```text
uv run python -m unittest \
  tests.test_mobile_event_store_phase0 \
  tests.test_server_v2_mobile \
  tests.test_mobile_contracts \
  tests.test_mobile_reconciliation \
  tests.test_member_event_partition \
  tests.test_evidence_player_scope -v

uv run python -m unittest \
  tests.test_contract_codegen tests.test_contract_authority -v

web_v2/node_modules/.bin/vitest run src/contracts/generated.test.ts

git diff --no-renames --name-only -z <base>..<head> |
  uv run python tools/contracts/check_authority.py
git diff --check <base>..<head>
```

Then run Native Mobile CI on `macos-15` at the exact candidate SHA. The iOS app
tests must include the Foundation sanitizer golden, `OfflineStoreTests`, the
real media-sync regression, and `LiveRoundAppModelTests`; the Watch target must
still compile and test. Recompute the canonical source digest and verify all
three generated pins plus the byte-identical Swift fixture before review.

## Explicit exclusions

- Do not add Task 5 exact prepared request-body persistence, response-roster
  authority, DomainLedger/outbox/receipts, global multi-round flush, sync-marker
  removal, or finish/discard lifecycle changes.
- Do not add round-event v2 schemas, reducers, scoring behavior, AutoShot, map,
  installer, or course-acquisition work.
- Do not weaken the frozen privacy promise or reinterpret it as only the paths
  already listed in the implementation.
- Do not modify the frozen Plan 1 dossier. This card and the Execution Index
  route live implementation evidence.
- Do not run tests, builds, generators, or dependency installation on the local
  machine.
