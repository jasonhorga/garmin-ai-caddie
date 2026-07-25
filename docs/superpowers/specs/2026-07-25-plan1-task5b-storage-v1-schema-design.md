# Plan 1 Task 5B Storage-v1 Schema Design

Date: 2026-07-25 UTC

Status: owner-approved design boundary; implementation is not yet verified

## Authority and outcome

The scope and order authority remains
`../plans/2026-07-23-program-execution-index.md`. The Task 5 packet router is
`../task-cards/2026-07-24-plan1-task5-packet-map.md`. The large Plan 1 dossier
is retained as normative input, but it is not completion authority and its code
sketches are not copied without checking the live repository.

Task 5B establishes the one storage-v1 data language that Task 5 and the later
Task 11 migration will share. It must be strict against hostile JSON and
internally contradictory transport state, but that strictness is deliberately
implemented as small serial capabilities rather than one decoder-shaped
monolith.

## Approaches considered

### 1. One monolithic storage decoder

This would define every record, parse raw JSON, validate the complete ledger
graph, recompute hashes, and expose one decoder in a single packet. It has the
fewest files, but repeats the same boundary failure as the original giant Task
5: a review cannot tell whether a failure belongs to JSON parsing, schema
shape, ledger semantics, or transport algorithms. It is rejected.

### 2. Plain synthesized `Codable`

This would define the records and treat `JSONDecoder.decode` success as a valid
storage document. It is attractive because it is short, but Swift keyed
decoding ignores unknown keys, does not detect duplicate raw JSON keys, and
synthesized optional decoding accepts a missing key as `nil`. It cannot be the
storage authority and is rejected.

### 3. Capability pipeline with one final decoder

This is the selected design. Literal values, hostile raw parsing, generated
shape authority, ledger-graph validation, and transport-graph validation are
separate serial packets. Only the last packet exposes a supported storage-v1
decoder. Each earlier packet produces a bounded capability consumed by the
next; no caller can bypass the raw and graph gates by directly treating
`JSONDecoder` as authoritative.

## Frozen serial decomposition

The implementation order is exact:

1. **5B1 — literals:** value types, required-key/required-nullable encoding,
   deterministic set representation, and storage-version literal.
2. **5B2a-R — raw JSON gate:** document byte limit, duplicate-key rejection,
   depth/key limits, an absolute raw-string cap with exact scalar-length
   evidence, JSON token/container classification, and a non-public
   validated-raw capability.
3. **5B2a-S — generated V1 shape/codec:** generated exact key/type authority
   for every recursive record, required keys, nullable keys, root collection
   kinds/counts and canonical number/NFC constraints. Before any typed decode,
   it requires each request-body string to be canonical standard padded Base64
   with no whitespace, decodes it, and first-enforces the decoded byte limit.
   It also first-enforces prepared-slot count and every hard canonical-byte and
   depth bound at `events[*]` and
   `preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope`, then
   produces the typed value from the validated raw capability.
4. **5B2b-L — algorithm-free ledger graph:** origin/event/outbox/dead-letter/
   receipt relationships, logical uniqueness, storage-v1 XORs and ordered
   source semantics that require no identity or hash recomputation.
5. **5B2b-T — algorithm-free transport graph and sole supported decoder:**
   binding, prepared-batch, Watch relay and transport-root relationships that
   can be checked by exact literal comparison. It does not first-enforce the
   bounds owned by 5B2a-S. For each decoded request body it reuses the 5B2a-R
   raw scanner, rejects invalid UTF-8/JSON, duplicate keys, depth failures and
   other raw-gate failures, requires exactly `roundId` plus `events`, and
   literally compares the body round and ordered events with the enclosing
   batch and its slots. It composes all prior capabilities and owns the only
   supported storage-v1 decode entry point.

The letters describe responsibility, not parallel execution. All five packets
share Domain schema files and therefore execute serially with only one active
implementation writer at a time.

## Storage-v1 root

`DomainLedgerStateV1` has exactly these 12 JSON keys:

| Key | Wire container | Typed value | Ordering |
|---|---|---|---|
| `storageVersion` | integer | literal `1` | n/a |
| `origin` | object | `OriginSequenceState` | n/a |
| `events` | array | `[StoredEventV1]` | source order |
| `outbox` | array | `[LegacyV1OutboxRecord]` | source order |
| `deadLetters` | array | `[LegacyV1OutboxRecord]` | source order |
| `receipts` | object | `[String: LegacyV1EventReceipt]` | dictionary keys are semantic, not order-bearing |
| `legacyWireBindings` | array | `[LegacyWireBinding]` | source order |
| `preparedLegacyV1Batches` | array | `[PreparedLegacyV1Batch]` | source order |
| `watchTerminalReceiptRelayObligations` | array | `[WatchTerminalReceiptRelayObligation]` | source order |
| `watchTerminalReceiptRelayConfirmations` | array | `[WatchTerminalReceiptRelayConfirmation]` | source order |
| `migrationMarkers` | array | `CanonicalStringSet` | UTF-8-byte sorted and unique |
| `transportAnomalies` | array | `[LegacyV1TransportAnomaly]` | source order |

Bindings, prepared batches, obligations and confirmations remain arrays. Later
graph gates build checked indexes and reject duplicate logical identities; the
wire shape must not silently change to dictionaries merely to simplify that
validation. `events` contains the historical `StoredEventV1` shape, not the
later `DomainRoundEvent` shape.

## 5B1 literal roster

`DomainRoundEvent.swift` owns the historical event row only:

| Type | Exact fields |
|---|---|
| `StoredEventV1` | `eventId: String`, `originDeviceId: String`, `originEpoch: String`, `clientSequence: Int`, `roundId: String`, `kind: RoundEventKind`, `payload: [String: JSONValue]`, `occurredAt: String` |

`DomainLedgerStateV1.swift` owns the storage-root values:

| Type | Exact fields |
|---|---|
| `OriginSequenceState` | `originDeviceId: String`, `originEpoch: String`, `lastReservedClientSequence: Int` |
| `CanonicalStringSet` | a sorted-unique JSON string array |
| `DomainLedgerStateV1` | the 12 roots above, with `storageVersion` fixed to `1` |

`LegacyV1Transport.swift` owns these transport literals:

| Type | Exact fields |
|---|---|
| `LegacyDomainAlias` | `eventIdentity: String`, `eventHash: String` |
| `LegacyWireBinding` | `roundId: String`, `wireClientId: String`, `wireEventId: String`, `canonicalDomainIdentity: String`, `canonicalDomainEventHash: String`, `normalizedWireEnvelopeHash: String`, `legacyAliases: [LegacyDomainAlias]` |
| `PreparedLegacyV1Slot` | `bindingKey: String`, `exactNormalizedEnvelope: JSONValue`, `exactNormalizedEnvelopeHash: String` |
| `PreparedLegacyV1Batch` | `roundId: String`, `orderedSlots: [PreparedLegacyV1Slot]`, `exactRequestBody: Data`, `requestBodySha256: String`, `idempotencyKey: String` |
| `LegacyV1TerminalStatus` | `accepted`, `duplicate_hash_match`, `rejected_permanent` |
| `LegacyV1EventReceipt` | `eventIdentity: String`, `eventHash: String`, `status: LegacyV1TerminalStatus`, `serverSequence: Int` |
| `LegacyV1OutboxRecord` | `eventIdentity: String`, `eventHash: String`, `receipt: LegacyV1EventReceipt?`, `deadLetterReason: String?` |
| `LegacyV1TransportAnomaly` | `roundId: String`, `code: String`, `evidence: String` |
| `WatchTerminalReceiptRelayObligation` | `obligationId: String`, `eventIdentity: String`, `eventHash: String`, `status: LegacyV1TerminalStatus` |
| `WatchTerminalReceiptRelayConfirmation` | `confirmationId: String`, `obligationId: String`, `eventIdentity: String`, `eventHash: String`, `status: LegacyV1TerminalStatus` |
| `LegacyV1EventBatchBody` | `roundId: String`, `events: [JSONValue]` |

The backend-v1 request body has exactly `roundId` and `events`. The literal
body type pins that shape; creating canonical bytes, request-body SHA-256 or an
idempotency key remains 5E work. This resolves an obsolete later-dossier sketch
that inspected an `events`-only object; the live v1 `SyncClient.EventBatch`
already requires both fields.

These declarations initially remain internal to `AICaddieDomain` and conform
only where required to `Codable` and `Equatable`. Domain tests use `@testable
import`; later packets promote only the values required by an actual
cross-target API. Their stored fields are immutable `let` values in 5B1; later
store code replaces whole values rather than gaining a hidden mutation method
here. 5B1 does not add `Identifiable`, `Hashable`, `Sendable`,
`@unchecked Sendable`, or a direct public root decoder.

## 5B1 value-local behavior

5B1 implements only behavior inherent to one value:

- decoding `DomainLedgerStateV1` requires every root key and rejects a
  `storageVersion` other than `1`;
- its normal initializer always sets `storageVersion` to `1` rather than
  accepting a caller-supplied version;
- `CanonicalStringSet` encodes in ascending UTF-8 byte order (equivalent to
  Unicode-scalar order for valid Swift strings) and rejects wire arrays that
  are not in that exact order or contain duplicates;
- `LegacyV1TerminalStatus` rejects unknown raw values through enum decoding;
- both optional fields of `LegacyV1OutboxRecord` are required-nullable: absent
  keys fail, while explicit JSON `null` decodes to `nil`; encoding `nil` writes
  the key with explicit `null`;
- every other field is required, and ordered arrays preserve input order;
- the batch body encoder emits exactly `roundId` and `events`.

`CodingKeys` constrain what 5B1 emits, but do not claim to reject unknown input
keys. Unknown-key and duplicate-key rejection belongs to 5B2a-R/5B2a-S. Tests
must make this distinction visible so future code cannot advertise a direct
`JSONDecoder` call as strict storage validation.

## Frozen limits and ownership

Every bound in this table is inclusive.

| Limit | Exact value | First enforcing packet |
|---|---:|---|
| storage document bytes | ≤ 67,108,864 (64 MiB) | 5B2a-R |
| raw JSON depth | ≤ 64 | 5B2a-R |
| each root collection | ≤ 65,536 entries | 5B2a-S |
| slots per prepared batch | 1...64 | 5B2a-S |
| decoded request-body bytes | ≤ 1,048,576 | 5B2a-S |
| any raw JSON string absolute cap | ≤ 1,398,104 Unicode scalars | 5B2a-R |
| Base64 text for the request body | ≤ 1,398,104 Unicode scalars | 5B2a-S |
| canonical event or envelope bytes | ≤ 65,536 | 5B2a-S |
| event/envelope JSON depth | ≤ 16 | 5B2a-S |
| JSON object key | ≤ 128 Unicode scalars | 5B2a-R |
| ordinary JSON string | ≤ 4,096 Unicode scalars | 5B2a-S using 5B2a-R length evidence |

Existing generated `RoundTransportLimits` values are reused where they match.
Storage-only limits receive one authority in the packet that first enforces
them; 5B1 must not create a second set of unused magic constants. “Unicode
scalars” means `value.unicodeScalars.count`, not grapheme-cluster count or UTF-8
byte count.

Depth is recursive: a scalar has depth `0`; an empty object or array has depth
`1`; and a non-empty object or array has depth `1 + max(child depth)`. The
document depth is the depth of its root value. Because the raw gate does not
yet possess typed path authority, 5B2a-R rejects any string above the absolute
1,398,104-scalar cap and carries exact scalar lengths forward. 5B2a-S then
rejects values above 4,096 everywhere except the exact
`preparedLegacyV1Batches[*].exactRequestBody` path. At that path, before typed
decode, it permits at most 1,398,104 scalars, requires canonical standard
padded Base64 with no whitespace, decodes it, and first-enforces the
1,048,576-byte limit. 5B2a-S also first-enforces `1...64` prepared slots and
the 65,536-byte/depth-16 bounds at `events[*]` and
`preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope`. Inner
request-body events inherit those bounds when 5B2b-T requires exact ordered
equality with the already bounded slot envelopes; 5B2b-T does not first-enforce
them again.

The 65,536-entry limit is for each root collection. Nested arrays other than
prepared slots have no independent entry-count limit in storage-v1; document
byte/depth and key/string bounds still apply. The 65,536-byte bound applies
only to a canonical event or envelope, not automatically to every record that
contains an event, envelope or nested array.

## Canonical-authority exception

The current authority manifest forbids `serverSequence` throughout Domain
sources because it must never become canonical event identity. The legacy v1
receipt nevertheless has a required diagnostic `serverSequence` field. 5B1
therefore owns a surgical manifest exception for
`mobile/ios/AICaddieDomain/LegacyV1Transport.swift` only:

- the other forbidden symbols remain forbidden in that file;
- `serverSequence` remains forbidden in every other protected Domain source;
- the exception does not make the field a delivery acknowledgement or Domain
  identity input; and
- because the manifest is a generated-group source, all three generated
  outputs are regenerated together and must pass byte-for-byte drift checks.

The exception and generated SHA update are 5B1 mechanical ownership, not a new
canonical object or transport algorithm.

## Deferred graph and algorithm work

5B1 does not reject nonblank/format/range failures merely because a future
graph validator will. In particular it does not decide:

- whether origin fields are nonblank or a sequence is legal;
- whether event identities, outbox entries, dead letters and receipt keys match;
- whether binding, batch, obligation or confirmation logical IDs are unique;
- whether a prepared body matches ordered slots or a binding;
- whether hashes are lowercase hexadecimal or match any bytes;
- whether receipt status and outbox/dead-letter placement form a legal XOR.

Those checks belong to 5B2b-L or 5B2b-T when they require only exact literal
comparison. In particular, 5B2b-T sends each already size-bounded decoded
`exactRequestBody` through the 5B2a-R raw scanner, then requires the inner
object to contain only `roundId` and `events`. It rejects inner duplicate keys,
invalid UTF-8/JSON, depth failures and all other raw-scanner failures; requires
`body.roundId == batch.roundId`; and compares `body.events` element-for-element
in source order with `orderedSlots[*].exactNormalizedEnvelope`. It does not
re-own the 5B2a-S first bounds or derive canonical body bytes, SHA-256 or an
idempotency key. The following are outside all of 5B and remain in 5C through
5E:

- root ownership, origin rotation, sequence reservation and mutation;
- Domain identity or event-hash computation;
- versioned client/event wire IDs and historical synthetic identity;
- binding-key construction or parsing;
- media normalization and normalized-envelope hash computation;
- request-body SHA-256 and idempotency-key algorithms;
- store transactions, network calls, response application and lifecycle.

## Error and data flow

5B1 uses standard `DecodingError`/`EncodingError` for literal failures; it does
not invent store or network errors before those layers exist. 5B2 packets wrap
the composed failure at the sole decoder boundary without discarding the
reason needed by tests and diagnostics.

The successful data flow is:

```text
raw Data
  → 5B2a-R validated raw capability
  → 5B2a-S bounded exact shape + decoded bodies + typed DomainLedgerStateV1
  → 5B2b-L validated ledger capability
  → 5B2b-T inner-body raw/shape and literal transport capability
  → supported decoded storage-v1 value
```

No earlier typed value is a caller-visible authorization to mutate or migrate
state.

## Verification strategy

5B1 RED tests are compile-safe and focused on observable literal behavior:

- exact field names and representative round trips for every record;
- explicit-null encode/decode, missing nullable-key rejection and non-null
  nullable-field round trips;
- missing required root/record fields;
- storage version `1` acceptance and other-version rejection;
- sorted deterministic `CanonicalStringSet` encoding plus duplicate/unsorted
  rejection, including a non-ASCII order vector;
- exact 12-key root encoding, array-versus-dictionary containers, source-order
  retention and exact two-key backend-v1 batch-body encoding;
- all three terminal-status wire values plus unknown-status rejection;
- unknown `RoundEventKind` raw-value preservation and a known `Data` Base64
  round trip; and
- an API/source boundary assertion proving no public storage decoder, mutation,
  identity/hash or network surface was introduced.

Tests that feed duplicate raw keys, oversized input, deep JSON, unknown keys or
cross-record contradictions are intentionally assigned to their later packet.
Adding such tests to 5B1 would either require a forbidden decoder or produce a
false claim of strictness.

Native Swift behavior is verified at an exact production SHA through GitHub
Actions `macos-15`. Homeserver owns static/mechanical checks and non-native
tests. Nothing is built or tested on the shared control machine.

## Review and completion boundary

Each subpacket follows `CARD → RED → GREEN → REMOTE → SPEC → QUALITY →
VERIFIED`. SPEC must pass before QUALITY begins. Critical and Important findings
are fixed, retested and re-reviewed before the subpacket advances. Task 5B is
not complete when 5B1 is complete; only 5B2b-T may close the composed schema
decoder boundary.

There is no open Owner decision in this design.
