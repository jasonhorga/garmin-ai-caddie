# Plan 1 Task 5 Packet Map

Date: 2026-07-24 UTC

## Authority and purpose

- Scope/order authority:
  `../plans/2026-07-23-program-execution-index.md`.
- Normative dossier input: Task 5 of
  `../plans/2026-07-18-phase0-canonical-round-runtime.md`.
- Verified prerequisite: Plan 1 Task 4 at production SHA `83c91675`.

Task 5 remains one product outcome: replace lossy v1 mobile sync markers and
per-surface queues with a crash-recoverable local storage-v1 authority while
preserving the backend v1 wire. This map prevents that outcome from becoming a
single implementation/review unit. Each packet has its own RED, focused GREEN,
specification review, quality review, exact commit, and visible status.

The map is routing authority only. It does not copy the giant dossier's code
sketches and does not pre-approve a later packet's implementation.

## Packet rules

1. Packets execute serially because they share Domain storage and transport
   files. There is one implementation writer; only read-only audits may run in
   parallel.
2. Review range is exactly the active packet commit range. Reviewers classify
   Critical/Important against that packet's outcome and exclusions; adjacent
   requirements are retained for their named packet.
3. A packet is independently terminable: focused RED and GREEN commands,
   exact files, a candidate SHA, and no open Critical/Important finding.
4. Native-only behavior uses exact-SHA `macos-15` CI. Homeserver still owns
   Python/static/mechanical verification and dependency work. Native evidence
   never licenses local builds on the shared control machine.
5. Shared canonical/registry/generated files may be changed only by the active
   packet and must finish generation/authority drift checks before another
   packet starts.
6. Do not create the dossier's rejected single-receipt mutation API merely so a
   later task can delete it. `LegacyV1EventReceipt` is a literal transport
   record owned by `LegacyV1Transport.swift`; response application is whole
   batch only.

## Linear packet ledger

| Packet | Status | Independently testable outcome | Primary ownership | Depends on | Explicitly excludes |
|---|---|---|---|---|---|
| 5A Swift canonical runtime | `IN_PROGRESS` | Auditable RFC 8785 + AI-Caddie-v1 `JSONValue`, `CanonicalJSON`, and `TypedID` run in the shared Domain target and in Native CI | Domain canonical runtime, pinned SwiftJCS sources/license/provenance, number vectors, Domain test routing | Tasks 2–3 | ledger state, origin/sequence, v1 adapter, app/watch integration |
| 5B storage-v1 literal schema | `PENDING` | Final Task-5 literal record roster and required storage-v1 root encode/decode strictly without a single-receipt mutation surface | `DomainRoundEvent.swift`, `LegacyV1Transport.swift`, value-only `DomainLedgerStateV1`, authority exception/pins, codec tests | 5A | file ownership, mutation, network, lifecycle |
| 5C root ownership and sequence | `PENDING` | One composition-root owner per canonical root; distinct iOS/Watch roots; origin/epoch and reserve-before-append sequence survive crash gaps | `DomainLedgerStore.swift`, `DomainLedgerCompositionRoot.swift`, store tests | 5B | event append, wire preparation, response application |
| 5D event identity and v1 wire | `PENDING` | Domain append enforces origin/epoch/event identity; versioned client/event IDs, binding key, and historical fixed-ID synthetic golden round-trip exactly | `DomainRoundEvent.swift`, `LegacyV1Transport.swift`, store/transport tests | 5C | prepared network batches and terminal receipts |
| 5E binding and immutable prepare | `PENDING` | Media-normalized binding, alias, ordered slots, exact body/hash/key, and outbox state become durable in one transaction before first send | `LegacyV1Transport.swift`, `DomainLedgerStore.swift`, transport tests | 5D | interpreting a server response, app/watch callsites |
| 5F exact response transaction | `PENDING` | Required exact response roster is validated before one atomic terminal/dead-letter/anomaly mutation; `serverSequence` remains diagnostic only | Domain response validator/store, `SyncClient` wire decoder seam, tests | 5E | global scheduling, legacy import, Watch relay |
| 5G ledger-wide v1 batcher | `PENDING` | Pending work is selected across rounds, incompatible `round_discarded` rows do not head-of-line block, and missing configuration never clears work | Domain batcher/store tests | 5F | UI/package lifecycle and physical legacy migration |
| 5H iOS migration and lifecycle | `PENDING` | iOS `events.jsonl` imports atomically once; foreground/background flush works without an active package; finish/discard/new-round never erase pending authority | `OfflineStore.swift`, `AICaddieApp.swift`, `SyncClient.swift`, iOS tests | 5G | Watch queue migration and direct/relay race |
| 5I Watch migration and relay | `PENDING` | Watch legacy state/queues import atomically; direct and phone relay reuse exact prepared bytes; terminal obligation/confirmation survives all response races | Watch stores/clients, `WatchEventBridge.swift`, Watch/iOS bridge tests | 5G, 5H response surface | rich handoff fixture and Task-11 capture behavior |
| 5J rich restart and handoff | `PENDING` | Checked-in rich storage-v1 fixture restarts and exact-reencodes; full crash/race matrix passes; Task 11 receives exact reusable bytes and literal types | Domain fixture/tests plus cross-surface final integration tests | 5A–5I | storage-v2 operational migration, reducers, backend v2 |

## Atomicity boundaries that must not be split

- 5E keeps binding registration, aliases, prepared slots, exact body/hash/key,
  and retryable outbox mutation in one local transaction. Splitting those
  writes would permit send-before-authority or a retry with rebuilt bytes.
- 5F keeps response roster validation and all terminal/dead-letter/anomaly
  mutations in one transaction. A per-receipt API is forbidden.
- 5I keeps phone terminal application and creation of the durable Watch relay
  obligation in one phone transaction. Watch confirmation removes only the
  exact matching obligation.
- 5J's checked-in fixture is produced once from the final 5A–5I encoder. It is
  not repeatedly regenerated by tests and cannot be finalized earlier.

## Promoted dependency

Task 5's normative historical-identity and event-hash algorithms call Swift
`CanonicalJSON`/`TypedID`, but the dossier originally listed their production
files under Task 11. Packet 5A promotes that already-planned shared foundation
without changing its algorithm, pinned SwiftJCS provenance, or later consumers.
Task 11 reuses it rather than implementing a second runtime. This is an
internal dependency-order correction, not a new product or architecture
decision.

## Overall return point

- **Overall:** locked S70 unified Watch/iOS/Web/backend product.
- **Current phase:** canonical reliability foundation.
- **Current drill-down:** Task 5A Swift canonical runtime.
- **Next:** observe Task 5A Native behavioral RED, implement only 5A, then run
  spec and quality review before activating 5B.
- **Owner decision:** none.
