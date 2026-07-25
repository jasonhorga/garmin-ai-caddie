# Plan 1 Task 5B1 Storage-v1 Literals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this card. The one
> implementation writer uses `superpowers:test-driven-development`; fresh
> read-only reviewers run SPEC before QUALITY. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Define the exact storage-v1 literal/value types and their local
required-key, required-nullable, deterministic-set and version behavior without
creating a storage decoder, graph validator, mutation API or transport
algorithm.

**Architecture:** Three focused internal Swift files in `AICaddieDomain` own
the historical event row, storage-root values and legacy-v1 transport values.
Ordinary `Codable` remains a value codec, not an authority decoder. A surgical
authority-manifest exception permits the diagnostic legacy `serverSequence`
field in one file while all generated outputs remain in sync.

**Tech Stack:** Swift 5.9, Foundation `Codable`, XCTest, Python 3.12 mechanical
audits, canonical contract generator, GitHub Actions `macos-15`.

---

## Authority, baseline and exclusions

- Scope/order authority:
  `../plans/2026-07-23-program-execution-index.md`.
- Design authority:
  `../specs/2026-07-25-plan1-task5b-storage-v1-schema-design.md`.
- Packet router: `2026-07-24-plan1-task5-packet-map.md`.
- Initial approved design commit:
  `0b1df575e6f90af4cb8e263a9428906363bf9038`; the bounded schema-audit
  refinements to that design are committed atomically with this card.
- Implementation baseline: the commit that first adds this card. Before RED,
  record it exactly with:

  ```bash
  CARD_SHA=$(git log --diff-filter=A -1 --format=%H -- \
    docs/superpowers/task-cards/2026-07-25-plan1-task5b1-storage-v1-literals.md)
  test -n "$CARD_SHA"
  ```
- Verified dependency: Task 5A production candidate `343e9a2`, reviewed audit
  boundary `f14fb9f`, final verification commit `51f9bd6`.

5B1 includes only value-local behavior. It explicitly excludes:

- raw JSON byte/depth/duplicate-key/Unicode-scalar gates;
- generated recursive unknown-key/type/count validation;
- ledger or transport cross-record graph validation;
- any supported/public storage-v1 decoder;
- ownership, persistence, sequence reservation, mutation or lifecycle;
- Domain identity/hash, versioned wire identity, historical synthetic identity,
  binding-key, normalization, request SHA or idempotency algorithms;
- network requests or response application; and
- the rich final storage fixture, which belongs to 5J.

Execution remains serial under one active implementation writer and follows
`CARD → RED → GREEN → REMOTE → SPEC → QUALITY → VERIFIED`.

The later 5B gates retain inclusive limits of 64 MiB document bytes, raw depth
64, 65,536 entries per root collection, `1...64` prepared slots, 1,048,576
decoded request-body bytes, an absolute 1,398,104-scalar raw-string cap and the
same request-body Base64 cap, 65,536 canonical event/envelope bytes,
event/envelope depth 16, 128 Unicode scalars per key and 4,096 per ordinary
string. Depth is recursive: a scalar has depth `0`; an empty object or array
has depth `1`; and a non-empty object or array has depth
`1 + max(child depth)`.

5B2a-R carries exact scalar counts under the absolute cap. Before typed decode,
5B2a-S applies 4,096 everywhere except the exact request-body path, requires
that field to be canonical standard padded Base64 with no whitespace, decodes
it, and first-enforces the 1,048,576-byte bound. 5B2a-S also first-enforces the
root counts, `1...64` prepared slots and the 65,536-byte/depth-16 bounds at
`events[*]` and
`preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope`. Inner
request-body events inherit those bounds when 5B2b-T requires exact ordered
equality with the slot envelopes; 5B2b-T does not re-own those first bounds. It
passes each decoded request body through the 5B2a-R raw scanner, rejects inner
duplicate keys, invalid UTF-8/JSON, depth and other raw-gate failures, requires
exactly `roundId` plus `events`, and literally compares the body round and
ordered events with the enclosing batch and `orderedSlots` envelopes.
Canonical body, SHA-256 and idempotency-key derivation remain 5E.

The root-count limit intentionally does not invent independent counts for
nested arrays other than prepared slots; document byte/depth and key/string
bounds still apply. The 65,536-byte limit applies only to a canonical event or
envelope, not to every containing record. 5B1 pins these future decisions in
the design but does not enforce them.

## Owned files

Create:

- `mobile/ios/AICaddieDomain/DomainRoundEvent.swift`
- `mobile/ios/AICaddieDomain/DomainLedgerStateV1.swift`
- `mobile/ios/AICaddieDomain/LegacyV1Transport.swift`
- `mobile/ios/AICaddieDomainTests/DomainLedgerStateV1Tests.swift`
- `mobile/ios/AICaddieDomainTests/LegacyV1TransportTests.swift`
- `tests/test_storage_v1_literal_schema_assets.py`

Modify:

- `contracts/canonical/authority.json`
- `ai_caddie/contracts/generated.py` — generated SHA only
- `mobile/ios/AICaddieDomain/GeneratedContracts.swift` — generated SHA only
- `web_v2/src/contracts/generated.ts` — generated SHA only

The Swift Package and XcodeGen targets already include these source/test
directories. `Package.swift`, `mobile/ios/project.yml`, the Native workflow,
registries and schemas are not modified.

## Exact literal contract

The production roster is exactly:

```text
DomainRoundEvent.swift
  StoredEventV1

DomainLedgerStateV1.swift
  OriginSequenceState
  CanonicalStringSet
  DomainLedgerStateV1

LegacyV1Transport.swift
  LegacyDomainAlias
  LegacyWireBinding
  PreparedLegacyV1Slot
  PreparedLegacyV1Batch
  LegacyV1TerminalStatus
  LegacyV1EventReceipt
  LegacyV1OutboxRecord
  LegacyV1TransportAnomaly
  WatchTerminalReceiptRelayObligation
  WatchTerminalReceiptRelayConfirmation
  LegacyV1EventBatchBody
```

All types are internal and have only the required `Codable` and `Equatable`
conformances. Schema contract fields are immutable `let` values;
`CanonicalStringSet` keeps its immutable backing array private because the
array is an encoding detail rather than a record field. `DomainLedgerStateV1`
encodes the exact 12-root shape from the design and always owns literal version
`1`. `LegacyV1OutboxRecord.receipt` and `deadLetterReason` are required-nullable:
missing is invalid, explicit null is `nil`, and nil re-encodes as explicit null.
`CanonicalStringSet` is a single UTF-8-byte-sorted unique array on the wire.

### Final production declarations

`DomainRoundEvent.swift` is exactly the following historical event-row layer:

```swift
import Foundation

struct StoredEventV1: Codable, Equatable {
    let eventId: String
    let originDeviceId: String
    let originEpoch: String
    let clientSequence: Int
    let roundId: String
    let kind: RoundEventKind
    let payload: [String: JSONValue]
    let occurredAt: String
}
```

`DomainLedgerStateV1.swift` is exactly the following storage-root value layer:

```swift
import Foundation

struct OriginSequenceState: Codable, Equatable {
    let originDeviceId: String
    let originEpoch: String
    let lastReservedClientSequence: Int
}

struct CanonicalStringSet: Codable, Equatable {
    private let values: [String]

    init(_ values: Set<String> = []) {
        self.values = values.sorted(by: Self.precedesInUTF8)
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let ordered = try container.decode([String].self)
        guard ordered == ordered.sorted(by: Self.precedesInUTF8),
              Set(ordered).count == ordered.count else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription:
                    "CanonicalStringSet must be sorted and unique"
            )
        }
        values = ordered
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(values)
    }

    private static func precedesInUTF8(_ lhs: String, _ rhs: String) -> Bool {
        lhs.utf8.lexicographicallyPrecedes(rhs.utf8)
    }
}

struct DomainLedgerStateV1: Codable, Equatable {
    let storageVersion: Int
    let origin: OriginSequenceState
    let events: [StoredEventV1]
    let outbox: [LegacyV1OutboxRecord]
    let deadLetters: [LegacyV1OutboxRecord]
    let receipts: [String: LegacyV1EventReceipt]
    let legacyWireBindings: [LegacyWireBinding]
    let preparedLegacyV1Batches: [PreparedLegacyV1Batch]
    let watchTerminalReceiptRelayObligations:
        [WatchTerminalReceiptRelayObligation]
    let watchTerminalReceiptRelayConfirmations:
        [WatchTerminalReceiptRelayConfirmation]
    let migrationMarkers: CanonicalStringSet
    let transportAnomalies: [LegacyV1TransportAnomaly]

    private enum CodingKeys: String, CodingKey {
        case storageVersion, origin, events, outbox, deadLetters, receipts
        case legacyWireBindings, preparedLegacyV1Batches
        case watchTerminalReceiptRelayObligations
        case watchTerminalReceiptRelayConfirmations
        case migrationMarkers, transportAnomalies
    }

    init(
        origin: OriginSequenceState,
        events: [StoredEventV1],
        outbox: [LegacyV1OutboxRecord],
        deadLetters: [LegacyV1OutboxRecord],
        receipts: [String: LegacyV1EventReceipt],
        legacyWireBindings: [LegacyWireBinding],
        preparedLegacyV1Batches: [PreparedLegacyV1Batch],
        watchTerminalReceiptRelayObligations:
            [WatchTerminalReceiptRelayObligation],
        watchTerminalReceiptRelayConfirmations:
            [WatchTerminalReceiptRelayConfirmation],
        migrationMarkers: CanonicalStringSet,
        transportAnomalies: [LegacyV1TransportAnomaly]
    ) {
        storageVersion = 1
        self.origin = origin
        self.events = events
        self.outbox = outbox
        self.deadLetters = deadLetters
        self.receipts = receipts
        self.legacyWireBindings = legacyWireBindings
        self.preparedLegacyV1Batches = preparedLegacyV1Batches
        self.watchTerminalReceiptRelayObligations =
            watchTerminalReceiptRelayObligations
        self.watchTerminalReceiptRelayConfirmations =
            watchTerminalReceiptRelayConfirmations
        self.migrationMarkers = migrationMarkers
        self.transportAnomalies = transportAnomalies
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        let decodedVersion = try values.decode(
            Int.self,
            forKey: .storageVersion
        )
        guard decodedVersion == 1 else {
            throw DecodingError.dataCorruptedError(
                forKey: .storageVersion,
                in: values,
                debugDescription: "storageVersion must equal 1"
            )
        }
        storageVersion = decodedVersion
        origin = try values.decode(OriginSequenceState.self, forKey: .origin)
        events = try values.decode([StoredEventV1].self, forKey: .events)
        outbox = try values.decode(
            [LegacyV1OutboxRecord].self,
            forKey: .outbox
        )
        deadLetters = try values.decode(
            [LegacyV1OutboxRecord].self,
            forKey: .deadLetters
        )
        receipts = try values.decode(
            [String: LegacyV1EventReceipt].self,
            forKey: .receipts
        )
        legacyWireBindings = try values.decode(
            [LegacyWireBinding].self,
            forKey: .legacyWireBindings
        )
        preparedLegacyV1Batches = try values.decode(
            [PreparedLegacyV1Batch].self,
            forKey: .preparedLegacyV1Batches
        )
        watchTerminalReceiptRelayObligations = try values.decode(
            [WatchTerminalReceiptRelayObligation].self,
            forKey: .watchTerminalReceiptRelayObligations
        )
        watchTerminalReceiptRelayConfirmations = try values.decode(
            [WatchTerminalReceiptRelayConfirmation].self,
            forKey: .watchTerminalReceiptRelayConfirmations
        )
        migrationMarkers = try values.decode(
            CanonicalStringSet.self,
            forKey: .migrationMarkers
        )
        transportAnomalies = try values.decode(
            [LegacyV1TransportAnomaly].self,
            forKey: .transportAnomalies
        )
    }
}
```

`LegacyV1Transport.swift` is exactly the following literal transport layer:

```swift
import Foundation

struct LegacyDomainAlias: Codable, Equatable {
    let eventIdentity: String
    let eventHash: String
}

struct LegacyWireBinding: Codable, Equatable {
    let roundId: String
    let wireClientId: String
    let wireEventId: String
    let canonicalDomainIdentity: String
    let canonicalDomainEventHash: String
    let normalizedWireEnvelopeHash: String
    let legacyAliases: [LegacyDomainAlias]
}

struct PreparedLegacyV1Slot: Codable, Equatable {
    let bindingKey: String
    let exactNormalizedEnvelope: JSONValue
    let exactNormalizedEnvelopeHash: String
}

struct PreparedLegacyV1Batch: Codable, Equatable {
    let roundId: String
    let orderedSlots: [PreparedLegacyV1Slot]
    let exactRequestBody: Data
    let requestBodySha256: String
    let idempotencyKey: String
}

enum LegacyV1TerminalStatus: String, Codable, Equatable {
    case accepted
    case duplicateHashMatch = "duplicate_hash_match"
    case rejectedPermanent = "rejected_permanent"
}

struct LegacyV1EventReceipt: Codable, Equatable {
    let eventIdentity: String
    let eventHash: String
    let status: LegacyV1TerminalStatus
    let serverSequence: Int
}

struct LegacyV1OutboxRecord: Codable, Equatable {
    let eventIdentity: String
    let eventHash: String
    let receipt: LegacyV1EventReceipt?
    let deadLetterReason: String?

    private enum CodingKeys: String, CodingKey {
        case eventIdentity, eventHash, receipt, deadLetterReason
    }

    init(
        eventIdentity: String,
        eventHash: String,
        receipt: LegacyV1EventReceipt?,
        deadLetterReason: String?
    ) {
        self.eventIdentity = eventIdentity
        self.eventHash = eventHash
        self.receipt = receipt
        self.deadLetterReason = deadLetterReason
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        eventIdentity = try values.decode(String.self, forKey: .eventIdentity)
        eventHash = try values.decode(String.self, forKey: .eventHash)
        guard values.contains(.receipt) else {
            throw DecodingError.keyNotFound(
                CodingKeys.receipt,
                .init(
                    codingPath: values.codingPath,
                    debugDescription: "receipt is required-nullable"
                )
            )
        }
        receipt = try values.decodeIfPresent(
            LegacyV1EventReceipt.self,
            forKey: .receipt
        )
        guard values.contains(.deadLetterReason) else {
            throw DecodingError.keyNotFound(
                CodingKeys.deadLetterReason,
                .init(
                    codingPath: values.codingPath,
                    debugDescription:
                        "deadLetterReason is required-nullable"
                )
            )
        }
        deadLetterReason = try values.decodeIfPresent(
            String.self,
            forKey: .deadLetterReason
        )
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(eventIdentity, forKey: .eventIdentity)
        try values.encode(eventHash, forKey: .eventHash)
        if let receipt {
            try values.encode(receipt, forKey: .receipt)
        } else {
            try values.encodeNil(forKey: .receipt)
        }
        if let deadLetterReason {
            try values.encode(deadLetterReason, forKey: .deadLetterReason)
        } else {
            try values.encodeNil(forKey: .deadLetterReason)
        }
    }
}

struct LegacyV1TransportAnomaly: Codable, Equatable {
    let roundId: String
    let code: String
    let evidence: String
}

struct WatchTerminalReceiptRelayObligation: Codable, Equatable {
    let obligationId: String
    let eventIdentity: String
    let eventHash: String
    let status: LegacyV1TerminalStatus
}

struct WatchTerminalReceiptRelayConfirmation: Codable, Equatable {
    let confirmationId: String
    let obligationId: String
    let eventIdentity: String
    let eventHash: String
    let status: LegacyV1TerminalStatus
}

struct LegacyV1EventBatchBody: Codable, Equatable {
    let roundId: String
    let events: [JSONValue]
}
```

## Task 1: Establish behavioral RED

### Files

- Create: `mobile/ios/AICaddieDomainTests/DomainLedgerStateV1Tests.swift`
- Create: `mobile/ios/AICaddieDomainTests/LegacyV1TransportTests.swift`
- Create: `tests/test_storage_v1_literal_schema_assets.py`

- [ ] **Step 1: Add the Swift tests before production declarations exist**

`DomainLedgerStateV1Tests.swift` must contain these tests against the wished-for
internal API:

```swift
import Foundation
import XCTest
@testable import AICaddieDomain

func assertEveryEncodedRecordKeyIsRequired<T: Codable>(
    _ value: T,
    file: StaticString = #filePath,
    line: UInt = #line
) throws {
    let encoded = try JSONEncoder().encode(value)
    let object = try XCTUnwrap(
        JSONSerialization.jsonObject(with: encoded) as? [String: Any],
        "\(T.self) must encode as a keyed record",
        file: file,
        line: line
    )
    XCTAssertFalse(
        object.isEmpty,
        "\(T.self) must encode at least one key",
        file: file,
        line: line
    )
    for key in object.keys.sorted() {
        var missing = object
        missing.removeValue(forKey: key)
        let missingData = try JSONSerialization.data(withJSONObject: missing)
        XCTAssertThrowsError(
            try JSONDecoder().decode(T.self, from: missingData),
            "missing required record key was accepted: \(T.self).\(key)",
            file: file,
            line: line
        )
    }
}

final class DomainLedgerStateV1Tests: XCTestCase {
    private let rootKeys: Set<String> = [
        "storageVersion", "origin", "events", "outbox", "deadLetters",
        "receipts", "legacyWireBindings", "preparedLegacyV1Batches",
        "watchTerminalReceiptRelayObligations",
        "watchTerminalReceiptRelayConfirmations", "migrationMarkers",
        "transportAnomalies",
    ]

    private func jsonObject<T: Encodable>(_ value: T) throws -> [String: Any] {
        try XCTUnwrap(
            JSONSerialization.jsonObject(
                with: JSONEncoder().encode(value)
            ) as? [String: Any]
        )
    }

    private func sampleReceipt(
        identity: String,
        status: LegacyV1TerminalStatus = .accepted
    ) -> LegacyV1EventReceipt {
        LegacyV1EventReceipt(
            eventIdentity: identity,
            eventHash: "hash-\(identity)",
            status: status,
            serverSequence: 7
        )
    }

    private func sampleState() -> DomainLedgerStateV1 {
        let first = StoredEventV1(
            eventId: "event-b",
            originDeviceId: "ios-1",
            originEpoch: "epoch-1",
            clientSequence: 2,
            roundId: "round-1",
            kind: RoundEventKind(rawValue: "score"),
            payload: ["strokes": .integer(4)],
            occurredAt: "2026-07-25T00:00:02Z"
        )
        let second = StoredEventV1(
            eventId: "event-a",
            originDeviceId: "ios-1",
            originEpoch: "epoch-1",
            clientSequence: 1,
            roundId: "round-1",
            kind: RoundEventKind(rawValue: "note"),
            payload: ["text": .string("second in source order")],
            occurredAt: "2026-07-25T00:00:01Z"
        )
        let receipt = sampleReceipt(identity: "identity-delivered")
        let rejectedB = sampleReceipt(
            identity: "identity-dead-b",
            status: .rejectedPermanent
        )
        let rejectedA = sampleReceipt(
            identity: "identity-dead-a",
            status: .rejectedPermanent
        )
        let bindingB = LegacyWireBinding(
            roundId: "round-b",
            wireClientId: "ios-phone",
            wireEventId: "wire-event-b",
            canonicalDomainIdentity: "identity-event-b",
            canonicalDomainEventHash: "domain-hash-b",
            normalizedWireEnvelopeHash: "wire-hash-b",
            legacyAliases: [
                LegacyDomainAlias(
                    eventIdentity: "identity-alias-b2",
                    eventHash: "domain-hash-b2"
                ),
                LegacyDomainAlias(
                    eventIdentity: "identity-alias-b1",
                    eventHash: "domain-hash-b1"
                ),
            ]
        )
        let bindingA = LegacyWireBinding(
            roundId: "round-a",
            wireClientId: "ios-phone",
            wireEventId: "wire-event-a",
            canonicalDomainIdentity: "identity-event-a",
            canonicalDomainEventHash: "domain-hash-a",
            normalizedWireEnvelopeHash: "wire-hash-a",
            legacyAliases: [
                LegacyDomainAlias(
                    eventIdentity: "identity-alias-a",
                    eventHash: "domain-hash-a"
                ),
            ]
        )
        let envelopeB2: JSONValue = .object([
            "eventId": .string("wire-b2"),
        ])
        let envelopeB1: JSONValue = .object([
            "eventId": .string("wire-b1"),
        ])
        let envelopeA: JSONValue = .object([
            "eventId": .string("wire-a"),
        ])
        let batchBodyB = Data(
            #"{"roundId":"round-b","events":[{"eventId":"wire-b2"},{"eventId":"wire-b1"}]}"#.utf8
        )
        let batchBodyA = Data(
            #"{"roundId":"round-a","events":[{"eventId":"wire-a"}]}"#.utf8
        )
        let obligationB = WatchTerminalReceiptRelayObligation(
            obligationId: "obligation-b",
            eventIdentity: receipt.eventIdentity,
            eventHash: receipt.eventHash,
            status: receipt.status
        )
        let obligationA = WatchTerminalReceiptRelayObligation(
            obligationId: "obligation-a",
            eventIdentity: rejectedA.eventIdentity,
            eventHash: rejectedA.eventHash,
            status: rejectedA.status
        )
        return DomainLedgerStateV1(
            origin: OriginSequenceState(
                originDeviceId: "ios-1",
                originEpoch: "epoch-1",
                lastReservedClientSequence: 2
            ),
            events: [first, second],
            outbox: [
                LegacyV1OutboxRecord(
                    eventIdentity: "identity-event-b",
                    eventHash: "domain-hash-b",
                    receipt: nil,
                    deadLetterReason: nil
                ),
                LegacyV1OutboxRecord(
                    eventIdentity: "identity-event-a",
                    eventHash: "domain-hash-a",
                    receipt: nil,
                    deadLetterReason: nil
                ),
            ],
            deadLetters: [
                LegacyV1OutboxRecord(
                    eventIdentity: rejectedB.eventIdentity,
                    eventHash: rejectedB.eventHash,
                    receipt: rejectedB,
                    deadLetterReason: "permanent-b"
                ),
                LegacyV1OutboxRecord(
                    eventIdentity: rejectedA.eventIdentity,
                    eventHash: rejectedA.eventHash,
                    receipt: rejectedA,
                    deadLetterReason: "permanent-a"
                ),
            ],
            receipts: [receipt.eventIdentity: receipt],
            legacyWireBindings: [bindingB, bindingA],
            preparedLegacyV1Batches: [
                PreparedLegacyV1Batch(
                    roundId: "round-b",
                    orderedSlots: [
                        PreparedLegacyV1Slot(
                            bindingKey: "binding-key-b2",
                            exactNormalizedEnvelope: envelopeB2,
                            exactNormalizedEnvelopeHash: "wire-hash-b2"
                        ),
                        PreparedLegacyV1Slot(
                            bindingKey: "binding-key-b1",
                            exactNormalizedEnvelope: envelopeB1,
                            exactNormalizedEnvelopeHash: "wire-hash-b1"
                        ),
                    ],
                    exactRequestBody: batchBodyB,
                    requestBodySha256: "request-hash-b",
                    idempotencyKey: "idempotency-b"
                ),
                PreparedLegacyV1Batch(
                    roundId: "round-a",
                    orderedSlots: [
                        PreparedLegacyV1Slot(
                            bindingKey: "binding-key-a",
                            exactNormalizedEnvelope: envelopeA,
                            exactNormalizedEnvelopeHash: "wire-hash-a"
                        ),
                    ],
                    exactRequestBody: batchBodyA,
                    requestBodySha256: "request-hash-a",
                    idempotencyKey: "idempotency-a"
                ),
            ],
            watchTerminalReceiptRelayObligations: [obligationB, obligationA],
            watchTerminalReceiptRelayConfirmations: [
                WatchTerminalReceiptRelayConfirmation(
                    confirmationId: "confirmation-b",
                    obligationId: obligationB.obligationId,
                    eventIdentity: obligationB.eventIdentity,
                    eventHash: obligationB.eventHash,
                    status: obligationB.status
                ),
                WatchTerminalReceiptRelayConfirmation(
                    confirmationId: "confirmation-a",
                    obligationId: obligationA.obligationId,
                    eventIdentity: obligationA.eventIdentity,
                    eventHash: obligationA.eventHash,
                    status: obligationA.status
                ),
            ],
            migrationMarkers: CanonicalStringSet(
                Set(["z-marker", "a-marker"])
            ),
            transportAnomalies: [
                LegacyV1TransportAnomaly(
                    roundId: "round-1",
                    code: "literal-code-b",
                    evidence: "literal-evidence-b"
                ),
                LegacyV1TransportAnomaly(
                    roundId: "round-1",
                    code: "literal-code-a",
                    evidence: "literal-evidence-a"
                ),
            ]
        )
    }

    func testStorageRootRoundTripsWithExactTwelveKeysAndContainers() throws {
        let state = sampleState()
        let data = try JSONEncoder().encode(state)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )

        XCTAssertEqual(Set(object.keys), rootKeys)
        XCTAssertEqual(object["storageVersion"] as? Int, 1)
        let origin = try XCTUnwrap(object["origin"] as? [String: Any])
        XCTAssertEqual(Set(origin.keys), [
            "originDeviceId", "originEpoch", "lastReservedClientSequence",
        ])
        XCTAssertNotNil(object["receipts"] as? [String: Any])
        for key in rootKeys.subtracting([
            "storageVersion", "origin", "receipts",
        ]) {
            XCTAssertNotNil(object[key] as? [Any], key)
        }
        XCTAssertEqual(object["migrationMarkers"] as? [String], [
            "a-marker", "z-marker",
        ])

        let decoded = try JSONDecoder().decode(
            DomainLedgerStateV1.self,
            from: data
        )
        XCTAssertEqual(decoded, state)
        XCTAssertEqual(decoded.events.map(\.eventId), ["event-b", "event-a"])
        XCTAssertEqual(decoded.outbox.map(\.eventIdentity), [
            "identity-event-b", "identity-event-a",
        ])
        XCTAssertEqual(decoded.deadLetters.map(\.eventIdentity), [
            "identity-dead-b", "identity-dead-a",
        ])
        XCTAssertEqual(decoded.legacyWireBindings.map(\.wireEventId), [
            "wire-event-b", "wire-event-a",
        ])
        XCTAssertEqual(
            decoded.legacyWireBindings[0].legacyAliases.map(\.eventIdentity),
            ["identity-alias-b2", "identity-alias-b1"]
        )
        XCTAssertEqual(
            decoded.preparedLegacyV1Batches.map(\.idempotencyKey),
            ["idempotency-b", "idempotency-a"]
        )
        XCTAssertEqual(
            decoded.preparedLegacyV1Batches[0].orderedSlots.map(\.bindingKey),
            ["binding-key-b2", "binding-key-b1"]
        )
        XCTAssertEqual(
            decoded.watchTerminalReceiptRelayObligations.map(\.obligationId),
            ["obligation-b", "obligation-a"]
        )
        XCTAssertEqual(
            decoded.watchTerminalReceiptRelayConfirmations.map(\.confirmationId),
            ["confirmation-b", "confirmation-a"]
        )
        XCTAssertEqual(decoded.transportAnomalies.map(\.code), [
            "literal-code-b", "literal-code-a",
        ])
    }

    func testEveryStoredEventOriginAndStorageRootKeyIsRequired() throws {
        let state = sampleState()
        try assertEveryEncodedRecordKeyIsRequired(state.events[0])
        try assertEveryEncodedRecordKeyIsRequired(state.origin)
        try assertEveryEncodedRecordKeyIsRequired(state)
    }

    func testStorageVersionMustBeLiteralOne() throws {
        var object = try jsonObject(sampleState())
        object["storageVersion"] = 2
        let data = try JSONSerialization.data(withJSONObject: object)
        XCTAssertThrowsError(
            try JSONDecoder().decode(DomainLedgerStateV1.self, from: data)
        )
    }

    func testCanonicalStringSetEncodesSortedAndRejectsNoncanonicalArrays() throws {
        let value = CanonicalStringSet(Set(["球", "z", "é", "a"]))
        let data = try JSONEncoder().encode(value)
        XCTAssertEqual(
            try JSONDecoder().decode([String].self, from: data),
            ["a", "z", "é", "球"]
        )
        XCTAssertEqual(
            try JSONDecoder().decode(CanonicalStringSet.self, from: data),
            value
        )
        for invalid in [#"["z","a"]"#, #"["a","a"]"#] {
            XCTAssertThrowsError(
                try JSONDecoder().decode(
                    CanonicalStringSet.self,
                    from: Data(invalid.utf8)
                )
            )
        }
    }

    func testStoredEventHasExactFieldsAndPreservesUnknownKind() throws {
        let event = StoredEventV1(
            eventId: "future-event",
            originDeviceId: "watch-1",
            originEpoch: "epoch-future",
            clientSequence: 41,
            roundId: "round-1",
            kind: RoundEventKind(rawValue: "future_literal_kind"),
            payload: ["future": .bool(true)],
            occurredAt: "2026-07-25T00:00:41Z"
        )
        XCTAssertEqual(Set(try jsonObject(event).keys), [
            "eventId", "originDeviceId", "originEpoch", "clientSequence",
            "roundId", "kind", "payload", "occurredAt",
        ])
        let decoded = try JSONDecoder().decode(
            StoredEventV1.self,
            from: JSONEncoder().encode(event)
        )
        XCTAssertEqual(decoded, event)
        XCTAssertEqual(decoded.kind.rawValue, "future_literal_kind")
    }
}
```

`LegacyV1TransportTests.swift` must pin all record keys, the terminal enum,
required-nullable behavior and the backend body:

```swift
import Foundation
import XCTest
@testable import AICaddieDomain

final class LegacyV1TransportTests: XCTestCase {
    private func keys<T: Encodable>(_ value: T) throws -> Set<String> {
        let data = try JSONEncoder().encode(value)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        return Set(object.keys)
    }

    func testLiteralRecordsEncodeExactFieldRosters() throws {
        let status = LegacyV1TerminalStatus.duplicateHashMatch
        let receipt = LegacyV1EventReceipt(
            eventIdentity: "identity-1",
            eventHash: "hash-1",
            status: status,
            serverSequence: 9
        )
        let alias = LegacyDomainAlias(
            eventIdentity: "identity-1",
            eventHash: "hash-1"
        )
        let binding = LegacyWireBinding(
            roundId: "round-1",
            wireClientId: "ios-phone",
            wireEventId: "wire-1",
            canonicalDomainIdentity: "identity-1",
            canonicalDomainEventHash: "hash-1",
            normalizedWireEnvelopeHash: "wire-hash-1",
            legacyAliases: [alias]
        )
        let slot = PreparedLegacyV1Slot(
            bindingKey: "binding-key-1",
            exactNormalizedEnvelope: .object(["eventId": .string("wire-1")]),
            exactNormalizedEnvelopeHash: "wire-hash-1"
        )
        let batch = PreparedLegacyV1Batch(
            roundId: "round-1",
            orderedSlots: [slot],
            exactRequestBody: Data(#"{"roundId":"round-1","events":[]}"#.utf8),
            requestBodySha256: "request-hash-1",
            idempotencyKey: "idempotency-1"
        )
        let outbox = LegacyV1OutboxRecord(
            eventIdentity: "identity-1",
            eventHash: "hash-1",
            receipt: nil,
            deadLetterReason: nil
        )
        let anomaly = LegacyV1TransportAnomaly(
            roundId: "round-1",
            code: "code-1",
            evidence: "evidence-1"
        )
        let obligation = WatchTerminalReceiptRelayObligation(
            obligationId: "obligation-1",
            eventIdentity: "identity-1",
            eventHash: "hash-1",
            status: status
        )
        let confirmation = WatchTerminalReceiptRelayConfirmation(
            confirmationId: "confirmation-1",
            obligationId: "obligation-1",
            eventIdentity: "identity-1",
            eventHash: "hash-1",
            status: status
        )
        let body = LegacyV1EventBatchBody(
            roundId: "round-1",
            events: [.object(["eventId": .string("wire-1")])]
        )

        XCTAssertEqual(try keys(alias), ["eventIdentity", "eventHash"])
        XCTAssertEqual(try keys(binding), [
            "roundId", "wireClientId", "wireEventId",
            "canonicalDomainIdentity", "canonicalDomainEventHash",
            "normalizedWireEnvelopeHash", "legacyAliases",
        ])
        XCTAssertEqual(try keys(slot), [
            "bindingKey", "exactNormalizedEnvelope",
            "exactNormalizedEnvelopeHash",
        ])
        XCTAssertEqual(try keys(batch), [
            "roundId", "orderedSlots", "exactRequestBody",
            "requestBodySha256", "idempotencyKey",
        ])
        XCTAssertEqual(try keys(receipt), [
            "eventIdentity", "eventHash", "status", "serverSequence",
        ])
        XCTAssertEqual(try keys(outbox), [
            "eventIdentity", "eventHash", "receipt", "deadLetterReason",
        ])
        XCTAssertEqual(try keys(anomaly), ["roundId", "code", "evidence"])
        XCTAssertEqual(try keys(obligation), [
            "obligationId", "eventIdentity", "eventHash", "status",
        ])
        XCTAssertEqual(try keys(confirmation), [
            "confirmationId", "obligationId", "eventIdentity", "eventHash",
            "status",
        ])
        XCTAssertEqual(try keys(body), ["roundId", "events"])

        try assertEveryEncodedRecordKeyIsRequired(alias)
        try assertEveryEncodedRecordKeyIsRequired(binding)
        try assertEveryEncodedRecordKeyIsRequired(slot)
        try assertEveryEncodedRecordKeyIsRequired(batch)
        try assertEveryEncodedRecordKeyIsRequired(receipt)
        try assertEveryEncodedRecordKeyIsRequired(outbox)
        try assertEveryEncodedRecordKeyIsRequired(anomaly)
        try assertEveryEncodedRecordKeyIsRequired(obligation)
        try assertEveryEncodedRecordKeyIsRequired(confirmation)
        try assertEveryEncodedRecordKeyIsRequired(body)
    }

    func testRetryableOutboxWritesExplicitNullAndRequiresBothNullableKeys() throws {
        let record = LegacyV1OutboxRecord(
            eventIdentity: "identity-1",
            eventHash: "hash-1",
            receipt: nil,
            deadLetterReason: nil
        )
        let data = try JSONEncoder().encode(record)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertTrue(object["receipt"] is NSNull)
        XCTAssertTrue(object["deadLetterReason"] is NSNull)
        XCTAssertEqual(
            try JSONDecoder().decode(LegacyV1OutboxRecord.self, from: data),
            record
        )

        for missingKey in ["receipt", "deadLetterReason"] {
            var missing = object
            missing.removeValue(forKey: missingKey)
            let missingData = try JSONSerialization.data(withJSONObject: missing)
            XCTAssertThrowsError(
                try JSONDecoder().decode(
                    LegacyV1OutboxRecord.self,
                    from: missingData
                ),
                "missing required-nullable key was accepted: \(missingKey)"
            )
        }
    }

    func testNonNullOutboxFieldsRoundTripExactly() throws {
        let receipt = LegacyV1EventReceipt(
            eventIdentity: "identity-1",
            eventHash: "hash-1",
            status: .rejectedPermanent,
            serverSequence: 12
        )
        let record = LegacyV1OutboxRecord(
            eventIdentity: receipt.eventIdentity,
            eventHash: receipt.eventHash,
            receipt: receipt,
            deadLetterReason: "permanent"
        )
        XCTAssertEqual(
            try JSONDecoder().decode(
                LegacyV1OutboxRecord.self,
                from: JSONEncoder().encode(record)
            ),
            record
        )
    }

    func testTerminalStatusesUseExactWireValuesAndRejectUnknown() throws {
        let cases: [(LegacyV1TerminalStatus, String)] = [
            (.accepted, "accepted"),
            (.duplicateHashMatch, "duplicate_hash_match"),
            (.rejectedPermanent, "rejected_permanent"),
        ]
        for (status, rawValue) in cases {
            let data = try JSONEncoder().encode(status)
            XCTAssertEqual(
                try JSONDecoder().decode(String.self, from: data),
                rawValue
            )
            XCTAssertEqual(
                try JSONDecoder().decode(
                    LegacyV1TerminalStatus.self,
                    from: data
                ),
                status
            )
        }
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                LegacyV1TerminalStatus.self,
                from: Data(#""future_status""#.utf8)
            )
        )
    }

    func testPreparedBatchDataUsesStandardPaddedBase64AndRoundTrips() throws {
        let batch = PreparedLegacyV1Batch(
            roundId: "round-1",
            orderedSlots: [
                PreparedLegacyV1Slot(
                    bindingKey: "binding-key-1",
                    exactNormalizedEnvelope: .object([:]),
                    exactNormalizedEnvelopeHash: "literal-envelope-hash"
                ),
            ],
            exactRequestBody: Data([0, 1, 2, 3]),
            requestBodySha256: "literal-request-hash",
            idempotencyKey: "literal-idempotency-key"
        )
        let data = try JSONEncoder().encode(batch)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertEqual(object["exactRequestBody"] as? String, "AAECAw==")
        XCTAssertEqual(
            try JSONDecoder().decode(PreparedLegacyV1Batch.self, from: data),
            batch
        )
    }

    func testBackendV1BodyHasExactlyRoundIdAndOrderedEvents() throws {
        let body = LegacyV1EventBatchBody(
            roundId: "round-1",
            events: [
                .object(["eventId": .string("wire-b")]),
                .object(["eventId": .string("wire-a")]),
            ]
        )
        let data = try JSONEncoder().encode(body)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertEqual(Set(object.keys), ["roundId", "events"])
        let events = try XCTUnwrap(object["events"] as? [[String: Any]])
        XCTAssertEqual(events.compactMap { $0["eventId"] as? String }, [
            "wire-b", "wire-a",
        ])
        let decoded = try JSONDecoder().decode(
            LegacyV1EventBatchBody.self,
            from: data
        )
        XCTAssertEqual(decoded.events, body.events)
        XCTAssertEqual(decoded, body)
    }
}
```

- [ ] **Step 2: Add the homeserver mechanical RED**

`tests/test_storage_v1_literal_schema_assets.py` must inspect only source and
authority boundaries:

```python
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools.contracts.check_authority import AuthorityViolation, check_authority


ROOT = Path(__file__).resolve().parents[1]
EVENT = Path("mobile/ios/AICaddieDomain/DomainRoundEvent.swift")
LEDGER = Path("mobile/ios/AICaddieDomain/DomainLedgerStateV1.swift")
TRANSPORT = Path("mobile/ios/AICaddieDomain/LegacyV1Transport.swift")
PROTECTED_PATHS = [
    "contracts/canonical/**/*.json",
    "ai_caddie/rounds/**/*.py",
    "server_v2/round_ledger_api.py",
    "mobile/ios/AICaddieDomain/**/*.swift",
    "web_v2/src/contracts/**/*.ts",
]


class StorageV1LiteralSchemaAssetTests(unittest.TestCase):
    def test_top_level_type_roster_is_exact(self) -> None:
        expected = {
            EVENT: {"StoredEventV1"},
            LEDGER: {
                "OriginSequenceState", "CanonicalStringSet",
                "DomainLedgerStateV1",
            },
            TRANSPORT: {
                "LegacyDomainAlias", "LegacyWireBinding",
                "PreparedLegacyV1Slot", "PreparedLegacyV1Batch",
                "LegacyV1TerminalStatus", "LegacyV1EventReceipt",
                "LegacyV1OutboxRecord", "LegacyV1TransportAnomaly",
                "WatchTerminalReceiptRelayObligation",
                "WatchTerminalReceiptRelayConfirmation",
                "LegacyV1EventBatchBody",
            },
        }
        for relative, names in expected.items():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(
                    path.is_file(),
                    f"missing literal source: {relative.as_posix()}",
                )
                source = path.read_text(encoding="utf-8")
                actual = set(
                    re.findall(
                        r"^(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
                        source,
                        flags=re.MULTILINE,
                    )
                )
                self.assertEqual(actual, names)

    def test_literal_sources_are_internal_and_algorithm_free(self) -> None:
        forbidden = (
            "public", "Identifiable", "Hashable", "Sendable", "@unchecked",
            "CryptoKit", "SHA256", "CanonicalJSON", "TypedID",
            "URLSession", "FileManager", "binding.v1", "event.v1",
            "decodeStorageV1", "reserveClientSequence", "appendEvent",
            "prepareLegacyV1Batch", "applyLegacyV1BatchResponse",
        )
        for relative in (EVENT, LEDGER, TRANSPORT):
            path = ROOT / relative
            self.assertTrue(
                path.is_file(),
                f"missing literal source: {relative.as_posix()}",
            )
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=relative, token=token):
                    self.assertNotIn(token, source)

    def test_server_sequence_exception_is_exactly_one_file(self) -> None:
        transport_path = ROOT / TRANSPORT
        self.assertTrue(
            transport_path.is_file(),
            f"missing literal source: {TRANSPORT.as_posix()}",
        )
        transport_source = transport_path.read_text(encoding="utf-8")
        self.assertEqual(transport_source.count("serverSequence"), 1)
        self.assertIn("let serverSequence: Int", transport_source)
        manifest = json.loads(
            (ROOT / "contracts/canonical/authority.json").read_text(
                encoding="utf-8"
            )
        )
        rules = manifest["forbiddenSymbols"]
        server_rules = [rule for rule in rules if rule["values"] == ["serverSequence"]]
        self.assertEqual(len(server_rules), 1)
        self.assertEqual(
            server_rules[0]["paths"],
            [*PROTECTED_PATHS, f"!{TRANSPORT.as_posix()}"],
        )
        common = [
            rule for rule in rules
            if set(rule["values"]) == {
                "weatherSnapshot", "weatherByHole", "WatchInputEvent",
                "autoshot_candidate",
            }
        ]
        self.assertEqual(len(common), 1)
        self.assertEqual(common[0]["paths"], PROTECTED_PATHS)

    def test_new_sources_pass_the_repository_authority_gate(self) -> None:
        for relative in (EVENT, LEDGER, TRANSPORT):
            path = ROOT / relative
            self.assertTrue(
                path.is_file(),
                f"missing literal source: {relative.as_posix()}",
            )
        try:
            violations = check_authority(
                ROOT,
                changed_paths=[
                    EVENT.as_posix(), LEDGER.as_posix(),
                    TRANSPORT.as_posix(),
                ],
            )
        except AuthorityViolation as exc:
            self.fail(f"authority gate rejected storage sources: {exc}")
        self.assertEqual(
            violations,
            [],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Commit and observe the initial RED at exact SHA**

```bash
git add \
  mobile/ios/AICaddieDomainTests/DomainLedgerStateV1Tests.swift \
  mobile/ios/AICaddieDomainTests/LegacyV1TransportTests.swift \
  tests/test_storage_v1_literal_schema_assets.py
git commit -m "test: define Task 5B1 literal schema"
git push origin HEAD:refs/heads/evidence/plan1-task5b1-literals-red-tests
```

On homeserver, create a new unique clone under `/home/jason/codex-runs`, check
out the exact pushed SHA, and run:

```bash
/home/jason/.local/bin/uv run python -m unittest \
  tests.test_storage_v1_literal_schema_assets \
  tests.test_contract_codegen \
  tests.test_contract_authority -v
```

Expected: controlled assertion failures, not `FileNotFoundError`/test errors,
because the three production files and authority exception do not exist.
Trigger Native Mobile CI at the exact evidence ref. Expected: Domain tests fail
to compile because the wished-for literal types do not exist. Record the exact
SHA, GitHub run/job IDs, exit codes and intended diagnostics.

## Task 2: Establish compile-safe behavioral RED

### Files

- Create: `mobile/ios/AICaddieDomain/DomainRoundEvent.swift`
- Create: `mobile/ios/AICaddieDomain/DomainLedgerStateV1.swift`
- Create: `mobile/ios/AICaddieDomain/LegacyV1Transport.swift`

- [ ] **Step 1: Add the minimum compile seam after the test-only RED**

Declare the exact immutable fields and memberwise initializers, but deliberately
leave these three behaviors synthesized/noncanonical:

```swift
// RED-only seam; replaced by Task 3 GREEN.
struct CanonicalStringSet: Codable, Equatable {
    let values: [String]

    init(_ values: Set<String> = []) {
        self.values = Array(values)
    }
}

// RED-only seam uses synthesized optional Codable, which omits nil keys and
// accepts missing keys.
struct LegacyV1OutboxRecord: Codable, Equatable {
    let eventIdentity: String
    let eventHash: String
    let receipt: LegacyV1EventReceipt?
    let deadLetterReason: String?
}
```

All other records use the exact fields in the design. The root has the exact
12 fields and normal initializer setting version `1`, but its synthesized
decoder still accepts encoded version `2`. Do not add an algorithm, validator,
public API or authority exception in this RED seam.

- [ ] **Step 2: Commit and observe behavioral RED**

```bash
git add \
  mobile/ios/AICaddieDomain/DomainRoundEvent.swift \
  mobile/ios/AICaddieDomain/DomainLedgerStateV1.swift \
  mobile/ios/AICaddieDomain/LegacyV1Transport.swift
git commit -m "test: expose Task 5B1 behavioral RED seam"
git push origin HEAD:refs/heads/evidence/plan1-task5b1-literals-red-behavior
```

Run the same homeserver suite. Expected: the mechanical authority test remains
a controlled assertion RED rather than an uncaught `AuthorityViolation`.
Trigger Native CI at the exact evidence ref. Expected behavioral failures:

- `CanonicalStringSet` is an object/nondeterministic instead of a canonical
  sorted array;
- storage version `2` decodes successfully; and
- nil outbox fields are omitted and missing optional keys are accepted.

Compilation alone is not sufficient RED evidence.

## Task 3: Implement the minimal GREEN values

### Files

- Modify: `mobile/ios/AICaddieDomain/DomainRoundEvent.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainLedgerStateV1.swift`
- Modify: `mobile/ios/AICaddieDomain/LegacyV1Transport.swift`
- Modify: `contracts/canonical/authority.json`
- Modify generated outputs listed under ownership

- [ ] **Step 1: Replace only the three RED seams**

Replace the RED-only `CanonicalStringSet`, synthesized root decoder and
synthesized optional outbox codec with the three exact GREEN implementations in
the **Final production declarations** section of this card. Leave every other
declaration byte-for-byte unchanged. Do not add string, hash, sequence,
cross-record or unknown-key validation.

- [ ] **Step 2: Narrow the canonical-authority exception**

Split the existing single forbidden-symbol rule into two. The common rule keeps
the original five protected path patterns and these four symbols:

```json
["weatherSnapshot", "weatherByHole", "WatchInputEvent", "autoshot_candidate"]
```

The second rule uses the same five positive paths followed by:

```json
"!mobile/ios/AICaddieDomain/LegacyV1Transport.swift"
```

and its only value is `serverSequence`. Do not exempt the whole file from the
other four forbidden symbols.

- [ ] **Step 3: Commit and push the provisional generator inputs**

The three GREEN source files and authority manifest must exist in a commit
before a fresh homeserver clone can obtain them. On the control worktree run:

```bash
set -euo pipefail
git add \
  mobile/ios/AICaddieDomain/DomainRoundEvent.swift \
  mobile/ios/AICaddieDomain/DomainLedgerStateV1.swift \
  mobile/ios/AICaddieDomain/LegacyV1Transport.swift \
  contracts/canonical/authority.json
git commit -m "feat: add Task 5B1 storage literals"
GENERATOR_INPUT_SHA=$(git rev-parse HEAD)
GENERATOR_INPUT_REF="refs/heads/evidence/plan1-task5b1-generator-input-$GENERATOR_INPUT_SHA"
git push origin "$GENERATOR_INPUT_SHA:$GENERATOR_INPUT_REF"
GENERATED_ATTEMPT_NONCE=$(
  printf '%s\0' "$GENERATOR_INPUT_SHA" "$(date -u +%s%N)" "$$" "$RANDOM" |
    git hash-object --stdin |
    cut -c1-16
)
test -n "$GENERATED_ATTEMPT_NONCE"
GENERATED_REF="refs/heads/evidence/plan1-task5b1-generated-${GENERATOR_INPUT_SHA}-${GENERATED_ATTEMPT_NONCE}"
EXISTING_GENERATED_REF=$(git ls-remote --heads origin "$GENERATED_REF")
test -z "$EXISTING_GENERATED_REF"
```

Record the input SHA/ref, attempt nonce and generated ref. The provisional
commit contains the source and authority inputs, while the earlier RED tests
remain in its ancestry. Every remote generator retry creates and records a new
attempt nonce/ref; never force or overwrite an existing audit ref. Never claim
that an uncommitted control-worktree edit was pushed.

- [ ] **Step 4: Generate, commit and push only on homeserver**

Pass the exact recorded SHA and refs to homeserver. The remote script creates a
fresh clone, verifies its detached input SHA, runs the generator, verifies the
three-file output roster, commits those outputs as a distinct commit and pushes
that commit to the precomputed evidence ref:

```bash
ssh homeserver bash -s -- \
  "$GENERATOR_INPUT_SHA" "$GENERATOR_INPUT_REF" "$GENERATED_REF" <<'REMOTE'
set -euo pipefail
GENERATOR_INPUT_SHA=$1
GENERATOR_INPUT_REF=$2
GENERATED_REF=$3
RUN_DIR=$(mktemp -d \
  "/home/jason/codex-runs/task5b1-generator-${GENERATOR_INPUT_SHA}-XXXXXX")
printf 'RUN_DIR=%s\n' "$RUN_DIR"
git clone --quiet --no-checkout \
  https://github.com/jasonhorga/garmin-ai-caddie.git "$RUN_DIR"
cd "$RUN_DIR"
git fetch --quiet origin "$GENERATOR_INPUT_REF"
git checkout --quiet --detach "$GENERATOR_INPUT_SHA"
test "$(git rev-parse HEAD)" = "$GENERATOR_INPUT_SHA"
test -z "$(git status --porcelain=v1)"

/home/jason/.local/bin/uv run python tools/contracts/generate_contracts.py
EXPECTED_GENERATED=$(printf '%s\n' \
  ai_caddie/contracts/generated.py \
  mobile/ios/AICaddieDomain/GeneratedContracts.swift \
  web_v2/src/contracts/generated.ts)
test "$(git diff --name-only | LC_ALL=C sort)" = "$EXPECTED_GENERATED"
git diff --check
git add \
  ai_caddie/contracts/generated.py \
  mobile/ios/AICaddieDomain/GeneratedContracts.swift \
  web_v2/src/contracts/generated.ts
test "$(git diff --cached --name-only | LC_ALL=C sort)" = \
  "$EXPECTED_GENERATED"
git commit -m "build: regenerate Task 5B1 contracts"
test "$(git rev-parse HEAD^)" = "$GENERATOR_INPUT_SHA"
test -z "$(git status --porcelain=v1)"
git push origin "HEAD:$GENERATED_REF"
REMOTE
```

The generator itself writes the exact digest into all three headers. Do not run
it on the control machine, copy a digest by hand or hand-edit any generated
declaration.

- [ ] **Step 5: Fetch and fast-forward the control worktree**

Integrate only the homeserver-generated commit and prove its parent/output
roster before treating its SHA as the GREEN candidate:

```bash
git fetch origin "$GENERATED_REF"
GENERATED_SHA=$(git rev-parse FETCH_HEAD)
test "$(git rev-parse "$GENERATED_SHA^")" = "$GENERATOR_INPUT_SHA"
EXPECTED_GENERATED=$(printf '%s\n' \
  ai_caddie/contracts/generated.py \
  mobile/ios/AICaddieDomain/GeneratedContracts.swift \
  web_v2/src/contracts/generated.ts)
test "$(git diff-tree --no-commit-id --name-only -r "$GENERATED_SHA" | \
  LC_ALL=C sort)" = \
  "$EXPECTED_GENERATED"
git merge --ff-only FETCH_HEAD
test "$(git rev-parse HEAD)" = "$GENERATED_SHA"
test -z "$(git status --porcelain=v1)"
```

## Task 4: Verify REMOTE and mechanical boundaries

- [ ] **Step 1: Run focused and regression checks in a clean homeserver clone**

Push the exact candidate SHA to a unique evidence ref, then run the complete
remote block. `CARD_SHA` is recomputed and tested inside the fresh homeserver
clone; it is never inherited from the control shell:

```bash
set -euo pipefail
CANDIDATE_SHA=$(git rev-parse HEAD)
CANDIDATE_REF="refs/heads/evidence/plan1-task5b1-green-$CANDIDATE_SHA"
git push origin "$CANDIDATE_SHA:$CANDIDATE_REF"
ssh homeserver bash -s -- "$CANDIDATE_SHA" "$CANDIDATE_REF" <<'REMOTE'
set -euo pipefail
CANDIDATE_SHA=$1
CANDIDATE_REF=$2
RUN_DIR=$(mktemp -d \
  "/home/jason/codex-runs/task5b1-remote-${CANDIDATE_SHA}-XXXXXX")
CARD_PATH="docs/superpowers/task-cards/2026-07-25-plan1-task5b1-storage-v1-literals.md"
printf 'RUN_DIR=%s\n' "$RUN_DIR"
git clone --quiet --no-checkout \
  https://github.com/jasonhorga/garmin-ai-caddie.git "$RUN_DIR"
cd "$RUN_DIR"
git fetch --quiet origin "$CANDIDATE_REF"
git checkout --quiet --detach "$CANDIDATE_SHA"
test "$(git rev-parse HEAD)" = "$CANDIDATE_SHA"
CARD_SHA=$(git log --diff-filter=A -1 --format=%H -- "$CARD_PATH")
test -n "$CARD_SHA"
test "$(git cat-file -t "$CARD_SHA")" = commit
git cat-file -e "$CARD_SHA:$CARD_PATH"
git merge-base --is-ancestor "$CARD_SHA" HEAD

/home/jason/.local/bin/uv run python -m unittest \
  tests.test_storage_v1_literal_schema_assets \
  tests.test_swift_canonical_runtime_assets \
  tests.test_contract_codegen \
  tests.test_contract_authority -v

/home/jason/.local/bin/uv run python tools/contracts/generate_contracts.py
test -z "$(git status --porcelain=v1)"

git diff --no-renames --name-only -z "$CARD_SHA"..HEAD | \
  /home/jason/.local/bin/uv run python tools/contracts/check_authority.py

git diff --check "$CARD_SHA"..HEAD
test -z "$(git status --porcelain=v1)"
REMOTE
```

Expected: all tests pass; regeneration changes no bytes; authority and diff
checks exit `0`; clone status remains empty. Preserve the complete log and its
SHA-256.

- [ ] **Step 2: Run Native Mobile CI at the same exact SHA**

`gh workflow run --ref` receives the branch name, not the full Git ref. Derive
that name, dispatch, locate only the newly created exact-SHA run and verify its
head before waiting for completion:

```bash
set -euo pipefail
CANDIDATE_SHA=$(git rev-parse HEAD)
CANDIDATE_REF="refs/heads/evidence/plan1-task5b1-green-$CANDIDATE_SHA"
REMOTE_CANDIDATE_SHA=$(git ls-remote --heads origin "$CANDIDATE_REF" |
  awk 'NR == 1 {print $1}')
test "$REMOTE_CANDIDATE_SHA" = "$CANDIDATE_SHA"
CANDIDATE_REF_NAME=${CANDIDATE_REF#refs/heads/}
test "$CANDIDATE_REF_NAME" != "$CANDIDATE_REF"
DISPATCHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
gh workflow run native-mobile.yml --ref "$CANDIDATE_REF_NAME"
RUN_ID=
for _ in $(seq 1 30); do
  RUN_ID=$(gh run list \
    --workflow native-mobile.yml \
    --branch "$CANDIDATE_REF_NAME" \
    --event workflow_dispatch \
    --limit 100 \
    --json databaseId,headSha,createdAt \
    --jq "map(select(.headSha == \"$CANDIDATE_SHA\" and .createdAt >= \"$DISPATCHED_AT\")) | sort_by(.createdAt) | .[-1].databaseId // empty")
  if test -n "$RUN_ID"; then
    break
  fi
  sleep 2
done
test -n "$RUN_ID"
RUN_HEAD_SHA=$(gh run view "$RUN_ID" --json headSha --jq .headSha)
test "$RUN_HEAD_SHA" = "$CANDIDATE_SHA"
gh run watch "$RUN_ID" --exit-status
```

The completed job must show:

- `DomainLedgerStateV1Tests` executed with zero failures;
- `LegacyV1TransportTests` executed with zero failures;
- complete Domain, iOS and Watch suites green; and
- existing SwiftJCS artifact-boundary gates still green.

Record exact candidate SHA, run ID, job ID, suite/test counts and downloaded log
SHA-256. A run at a moving branch head or another SHA is not evidence.

- [ ] **Step 3: Check the exact diff and source boundary**

The production candidate range from exact `CARD_SHA` may contain only the three test files,
three production value files, the one authority manifest change and three
mechanically regenerated outputs. It must not contain a public decoder,
`DomainLedgerStore`, `DomainLedgerCompositionRoot`, app/Watch callsite or
fixture.

## Task 5: SPEC, QUALITY and verification record

- [ ] **Step 1: Independent SPEC review**

Give a fresh read-only reviewer this card, the design, baseline SHA, candidate
SHA, complete diff and remote evidence. The reviewer reports Critical and
Important findings against 5B1 only. Adjacent raw/graph/algorithm requirements
remain in their named packets. Any real finding returns to the same writer,
then repeats REMOTE and SPEC until PASS.

- [ ] **Step 2: Independent QUALITY review after SPEC PASS**

Give a different fresh read-only reviewer the exact same frozen candidate range
plus the SPEC result. Inspect Codable correctness, null handling, error paths,
API surface, manifest exception scope, generated drift and test quality. Fix,
retest and re-review every Critical or Important issue.

- [ ] **Step 3: Record evidence and mark only 5B1 VERIFIED**

Create
`docs/superpowers/reviews/2026-07-25-plan1-task5b1-storage-v1-literals-verification.md`
with exact RED/GREEN SHAs, trees, commands, run/job IDs, logs/hashes, review
verdicts and exclusions. Update the Execution Index and packet map so 5B1 is
`VERIFIED` and the next POP is 5B2a-R. This documentation commit is an audit
head; it does not change the verified production candidate bytes.

Do not mark Task 5B or Plan 1 frozen at 5B1. The final Plan 1 strict serializer
decision, complete mechanical freeze and final SHA-256 remain later gates.
