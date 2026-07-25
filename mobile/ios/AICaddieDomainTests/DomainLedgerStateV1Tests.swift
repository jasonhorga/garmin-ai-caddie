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
