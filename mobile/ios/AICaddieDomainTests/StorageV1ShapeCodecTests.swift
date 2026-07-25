import Foundation
import XCTest
@testable import AICaddieDomain

final class StorageV1ShapeCodecTests: XCTestCase {
    private typealias Decode = (String) throws -> DomainLedgerStateV1

    private enum PathComponent {
        case key(String)
        case index(Int)
    }

    private struct RecordTarget {
        let name: String
        let path: [PathComponent]
        let scalarKey: String
    }

    private enum RootCollectionPayload {
        case array(element: String)
        case object(value: String)
        case sortedStrings

        var emptyJSON: String {
            switch self {
            case .array, .sortedStrings:
                return "[]"
            case .object:
                return "{}"
            }
        }
    }

    private struct RootCollectionTarget {
        let name: String
        let key: String
        let payload: RootCollectionPayload
    }

    private let minimalStorageDocument = #"{"storageVersion":1,"origin":{"originDeviceId":"","originEpoch":"","lastReservedClientSequence":0},"events":[],"outbox":[],"deadLetters":[],"receipts":{},"legacyWireBindings":[],"preparedLegacyV1Batches":[],"watchTerminalReceiptRelayObligations":[],"watchTerminalReceiptRelayConfirmations":[],"migrationMarkers":[],"transportAnomalies":[]}"#

    private let recordTargets: [RecordTarget] = [
        .init(name: "DomainLedgerStateV1", path: [], scalarKey: "storageVersion"),
        .init(
            name: "OriginSequenceState",
            path: [.key("origin")],
            scalarKey: "originDeviceId"
        ),
        .init(
            name: "StoredEventV1",
            path: [.key("events"), .index(0)],
            scalarKey: "eventId"
        ),
        .init(
            name: "LegacyV1OutboxRecord",
            path: [.key("outbox"), .index(0)],
            scalarKey: "eventIdentity"
        ),
        .init(
            name: "LegacyV1EventReceipt",
            path: [.key("outbox"), .index(0), .key("receipt")],
            scalarKey: "eventIdentity"
        ),
        .init(
            name: "LegacyWireBinding",
            path: [.key("legacyWireBindings"), .index(0)],
            scalarKey: "roundId"
        ),
        .init(
            name: "LegacyDomainAlias",
            path: [
                .key("legacyWireBindings"), .index(0),
                .key("legacyAliases"), .index(0),
            ],
            scalarKey: "eventIdentity"
        ),
        .init(
            name: "PreparedLegacyV1Batch",
            path: [.key("preparedLegacyV1Batches"), .index(0)],
            scalarKey: "roundId"
        ),
        .init(
            name: "PreparedLegacyV1Slot",
            path: [
                .key("preparedLegacyV1Batches"), .index(0),
                .key("orderedSlots"), .index(0),
            ],
            scalarKey: "bindingKey"
        ),
        .init(
            name: "LegacyV1TransportAnomaly",
            path: [.key("transportAnomalies"), .index(0)],
            scalarKey: "roundId"
        ),
        .init(
            name: "WatchTerminalReceiptRelayObligation",
            path: [
                .key("watchTerminalReceiptRelayObligations"), .index(0),
            ],
            scalarKey: "obligationId"
        ),
        .init(
            name: "WatchTerminalReceiptRelayConfirmation",
            path: [
                .key("watchTerminalReceiptRelayConfirmations"), .index(0),
            ],
            scalarKey: "confirmationId"
        ),
    ]

    private let rootCollectionTargets: [RootCollectionTarget] = [
        .init(
            name: "events",
            key: "events",
            payload: .array(
                element: #"{"eventId":"","originDeviceId":"","originEpoch":"","clientSequence":0,"roundId":"","kind":"","payload":{},"occurredAt":""}"#
            )
        ),
        .init(
            name: "outbox",
            key: "outbox",
            payload: .array(
                element: #"{"eventIdentity":"","eventHash":"","receipt":null,"deadLetterReason":null}"#
            )
        ),
        .init(
            name: "deadLetters",
            key: "deadLetters",
            payload: .array(
                element: #"{"eventIdentity":"","eventHash":"","receipt":null,"deadLetterReason":null}"#
            )
        ),
        .init(
            name: "receipts",
            key: "receipts",
            payload: .object(
                value: #"{"eventIdentity":"","eventHash":"","status":"accepted","serverSequence":0}"#
            )
        ),
        .init(
            name: "legacyWireBindings",
            key: "legacyWireBindings",
            payload: .array(
                element: #"{"roundId":"","wireClientId":"","wireEventId":"","canonicalDomainIdentity":"","canonicalDomainEventHash":"","normalizedWireEnvelopeHash":"","legacyAliases":[]}"#
            )
        ),
        .init(
            name: "preparedLegacyV1Batches",
            key: "preparedLegacyV1Batches",
            payload: .array(
                element: #"{"roundId":"","orderedSlots":[{"bindingKey":"","exactNormalizedEnvelope":null,"exactNormalizedEnvelopeHash":""}],"exactRequestBody":"","requestBodySha256":"","idempotencyKey":""}"#
            )
        ),
        .init(
            name: "watchTerminalReceiptRelayObligations",
            key: "watchTerminalReceiptRelayObligations",
            payload: .array(
                element: #"{"obligationId":"","eventIdentity":"","eventHash":"","status":"accepted"}"#
            )
        ),
        .init(
            name: "watchTerminalReceiptRelayConfirmations",
            key: "watchTerminalReceiptRelayConfirmations",
            payload: .array(
                element: #"{"confirmationId":"","obligationId":"","eventIdentity":"","eventHash":"","status":"accepted"}"#
            )
        ),
        .init(
            name: "migrationMarkers",
            key: "migrationMarkers",
            payload: .sortedStrings
        ),
        .init(
            name: "transportAnomalies",
            key: "transportAnomalies",
            payload: .array(
                element: #"{"roundId":"","code":"","evidence":""}"#
            )
        ),
    ]

    func testMinimalStorageDocumentDecodes() throws {
        let decode: Decode = { source in
            let validatedRawJSON = try StorageV1RawJSONGate.validate(
                Data(source.utf8)
            )
            return try StorageV1ShapeCodec.decode(validatedRawJSON).state
        }

        let state = try decode(minimalStorageDocument)
        XCTAssertEqual(state.storageVersion, 1)

        try exerciseRepresentativeRoot(using: decode)
        try exerciseRoundKindAndTerminalStatuses(using: decode)
        try exerciseRecordShapeAndNullabilityMutations(using: decode)
        try exerciseNFCForDynamicKeysAndValues(using: decode)
        try exerciseOrdinaryStringScalarBounds(using: decode)
        try exerciseRootCollectionBoundsAndUnrelatedArrays(using: decode)
        try exercisePreparedSlotBounds(using: decode)
        try exerciseBase64CanonicalFormAndBounds(using: decode)
        try exerciseIntegerAndDoubleLexicalRoutes(using: decode)
        try exerciseEventEnvelopeCanonicalBoundsAndScope(using: decode)
        try exerciseUnconstrainedLegacyAndRecursiveJSON(using: decode)
        try exerciseCanonicalStringSetAtFinalDecode(using: decode)
    }

    private func activity(
        _ name: String,
        using decode: @escaping Decode,
        _ body: (Decode) throws -> Void
    ) throws {
        try XCTContext.runActivity(named: name) { _ in
            try body(decode)
        }
    }

    private func exerciseRepresentativeRoot(using decode: @escaping Decode) throws {
        try activity(
            "representative root covers every record family",
            using: decode
        ) { decode in
            let state = try decode(try representativeSource())
            XCTAssertEqual(state.storageVersion, 1)
            XCTAssertEqual(state.events.count, 1)
            XCTAssertEqual(state.outbox.count, 1)
            XCTAssertEqual(state.deadLetters.count, 1)
            XCTAssertEqual(state.receipts.count, 3)
            XCTAssertEqual(state.legacyWireBindings.count, 1)
            XCTAssertEqual(state.preparedLegacyV1Batches.count, 1)
            XCTAssertEqual(
                state.watchTerminalReceiptRelayObligations.count,
                1
            )
            XCTAssertEqual(
                state.watchTerminalReceiptRelayConfirmations.count,
                1
            )
            XCTAssertEqual(state.transportAnomalies.count, 1)
        }
    }

    private func exerciseRoundKindAndTerminalStatuses(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "open round kind and closed terminal status roster",
            using: decode
        ) { decode in
            let representative = try decode(try representativeSource())
            XCTAssertEqual(
                representative.events.first?.kind.rawValue,
                "future_round_event_kind"
            )
            XCTAssertEqual(
                Set(representative.receipts.values.map(\.status.rawValue)),
                Set([
                    "accepted",
                    "duplicate_hash_match",
                    "rejected_permanent",
                ])
            )

            let futureKind = try source(mutating: [
                .key("events"), .index(0),
            ]) { event in
                event["kind"] = "another_future_kind"
            }
            XCTAssertEqual(
                try decode(futureKind).events.first?.kind.rawValue,
                "another_future_kind"
            )

            for status in [
                "accepted", "duplicate_hash_match", "rejected_permanent",
            ] {
                let candidate = try source(mutating: [
                    .key("receipts"), .key("accepted"),
                ]) { receipt in
                    receipt["status"] = status
                }
                XCTAssertNoThrow(try decode(candidate), status)
            }
            let unknownStatus = try source(mutating: [
                .key("receipts"), .key("accepted"),
            ]) { receipt in
                receipt["status"] = "future_terminal_status"
            }
            assertRejected(
                unknownStatus,
                using: decode,
                reason: "closed terminal status accepted an unknown value"
            )
        }
    }

    private func exerciseRecordShapeAndNullabilityMutations(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "record missing extra wrong-type null and required-nullable mutations",
            using: decode
        ) { decode in
            for target in recordTargets {
                let missing = try source(mutating: target.path) { record in
                    record.removeValue(forKey: target.scalarKey)
                }
                assertRejected(
                    missing,
                    using: decode,
                    reason: "\(target.name) accepted missing \(target.scalarKey)"
                )

                let extra = try source(mutating: target.path) { record in
                    record["__unexpected"] = "extra"
                }
                assertRejected(
                    extra,
                    using: decode,
                    reason: "\(target.name) accepted an unknown key"
                )

                let wrongType = try source(mutating: target.path) { record in
                    record[target.scalarKey] = ["wrong": "type"]
                }
                assertRejected(
                    wrongType,
                    using: decode,
                    reason: "\(target.name) accepted a wrong scalar type"
                )

                let forbiddenNull = try source(mutating: target.path) { record in
                    record[target.scalarKey] = NSNull()
                }
                assertRejected(
                    forbiddenNull,
                    using: decode,
                    reason: "\(target.name) accepted forbidden null"
                )
            }

            let bothNullableFieldsNull = try source(mutating: [
                .key("outbox"), .index(0),
            ]) { outbox in
                outbox["receipt"] = NSNull()
                outbox["deadLetterReason"] = NSNull()
            }
            XCTAssertNoThrow(try decode(bothNullableFieldsNull))

            for requiredNullableKey in ["receipt", "deadLetterReason"] {
                let missing = try source(mutating: [
                    .key("outbox"), .index(0),
                ]) { outbox in
                    outbox.removeValue(forKey: requiredNullableKey)
                }
                assertRejected(
                    missing,
                    using: decode,
                    reason: "missing required-nullable \(requiredNullableKey)"
                )
            }
        }
    }

    private func exerciseNFCForDynamicKeysAndValues(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "NFC gates hostile dynamic keys and values",
            using: decode
        ) { decode in
            let precomposed = "é"
            let decomposed = "e\u{301}"

            let acceptedPayload = try source(mutating: [
                .key("events"), .index(0),
            ]) { event in
                event["payload"] = [precomposed: "café"]
            }
            XCTAssertNoThrow(try decode(acceptedPayload))

            let rejectedPayloadKey = try source(mutating: [
                .key("events"), .index(0),
            ]) { event in
                event["payload"] = [decomposed: "value"]
            }
            assertRejected(
                rejectedPayloadKey,
                using: decode,
                reason: "non-NFC payload key was accepted"
            )

            let rejectedPayloadValue = try source(mutating: [
                .key("events"), .index(0),
            ]) { event in
                event["payload"] = ["key": decomposed]
            }
            assertRejected(
                rejectedPayloadValue,
                using: decode,
                reason: "non-NFC payload string was accepted"
            )

            let acceptedReceiptKey = try source(mutating: [
                .key("receipts"),
            ]) { receipts in
                receipts[precomposed] = receipts.removeValue(forKey: "accepted")
            }
            XCTAssertNoThrow(try decode(acceptedReceiptKey))

            let rejectedReceiptKey = try source(mutating: [
                .key("receipts"),
            ]) { receipts in
                receipts[decomposed] = receipts.removeValue(forKey: "accepted")
            }
            assertRejected(
                rejectedReceiptKey,
                using: decode,
                reason: "non-NFC receipt-map key was accepted"
            )

            let equivalentKeys = try sourceWithRawPayloadMembers(
                #""é":1,"e\u0301":2"#
            )
            assertRejected(
                equivalentKeys,
                using: decode,
                reason: "canonically equivalent hostile keys collapsed before rejection"
            )
        }
    }

    private func exerciseOrdinaryStringScalarBounds(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "ordinary strings pass 4096 and reject 4097 scalars",
            using: decode
        ) { decode in
            for (count, accepted) in [(4_096, true), (4_097, false)] {
                let value = String(repeating: "😀", count: count)
                let candidate = try source(mutating: [.key("origin")]) { origin in
                    origin["originDeviceId"] = value
                }
                if accepted {
                    XCTAssertNoThrow(try decode(candidate), "count=\(count)")
                } else {
                    assertRejected(
                        candidate,
                        using: decode,
                        reason: "ordinary string accepted \(count) scalars"
                    )
                }
            }
        }
    }

    private func exerciseRootCollectionBoundsAndUnrelatedArrays(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "root collections enforce 65536 without constraining unrelated arrays",
            using: decode
        ) { decode in
            for target in rootCollectionTargets {
                let atLimit = try rootSource(target, count: 65_536)
                XCTAssertNoThrow(
                    try decode(atLimit),
                    "\(target.name) rejected its 65,536-entry boundary"
                )

                let overLimit = try rootSource(target, count: 65_537)
                assertRejected(
                    overLimit,
                    using: decode,
                    reason: "\(target.name) accepted 65,537 entries"
                )
            }
        }
    }

    private func exercisePreparedSlotBounds(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "prepared slots enforce 1 through 64",
            using: decode
        ) { decode in
            let root = try representativeJSONObject()
            let slot = try value(
                in: root,
                at: [
                    .key("preparedLegacyV1Batches"), .index(0),
                    .key("orderedSlots"), .index(0),
                ][...]
            )
            for (count, accepted) in [
                (0, false), (1, true), (64, true), (65, false),
            ] {
                let candidate = try source(mutating: [
                    .key("preparedLegacyV1Batches"), .index(0),
                ]) { batch in
                    batch["orderedSlots"] = Array(repeating: slot, count: count)
                }
                if accepted {
                    XCTAssertNoThrow(try decode(candidate), "count=\(count)")
                } else {
                    assertRejected(
                        candidate,
                        using: decode,
                        reason: "prepared slots accepted count \(count)"
                    )
                }
            }
        }
    }

    private func exerciseBase64CanonicalFormAndBounds(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "request body Base64 is standard padded canonical and bounded",
            using: decode
        ) { decode in
            for accepted in ["AAECAw==", ""] {
                XCTAssertNoThrow(
                    try decode(try sourceWithRequestBody(accepted)),
                    accepted.debugDescription
                )
            }
            for rejected in ["AB==", "AA E=", "AAE"] {
                assertRejected(
                    try sourceWithRequestBody(rejected),
                    using: decode,
                    reason: "noncanonical Base64 accepted: \(rejected.debugDescription)"
                )
            }

            let maximumBytes = RoundTransportLimits.maxHttpBodyBytes
            let maximumBody = Data(
                repeating: 0,
                count: maximumBytes
            ).base64EncodedString()
            XCTAssertEqual(
                maximumBody.unicodeScalars.count,
                StorageV1RawJSONGate.maximumStringScalars
            )
            XCTAssertNoThrow(
                try decode(try sourceWithRequestBody(maximumBody))
            )

            let overDecodedLimit = Data(
                repeating: 0,
                count: maximumBytes + 1
            ).base64EncodedString()
            XCTAssertEqual(
                overDecodedLimit.unicodeScalars.count,
                StorageV1RawJSONGate.maximumStringScalars
            )
            assertRejected(
                try sourceWithRequestBody(overDecodedLimit),
                using: decode,
                reason: "decoded request body exceeded its byte limit"
            )

            let overTextLimit = String(
                repeating: "A",
                count: StorageV1RawJSONGate.maximumStringScalars + 1
            )
            assertRejected(
                try sourceWithRequestBody(overTextLimit),
                using: decode,
                reason: "request-body text exceeded its preallocation limit"
            )
        }
    }

    private func exerciseIntegerAndDoubleLexicalRoutes(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "integer and Double lexemes take their frozen routes",
            using: decode
        ) { decode in
            for lexeme in [
                "1", "9007199254740991", "-9007199254740991",
            ] {
                XCTAssertNoThrow(
                    try decode(try sourceWithRawInteger(lexeme)),
                    "integer \(lexeme)"
                )
            }
            for lexeme in [
                "1.0", "1e0", "-0", "9007199254740992",
                "-9007199254740992", "9223372036854775807",
                "-9223372036854775808", "9223372036854775808",
                "-9223372036854775809",
            ] {
                assertRejected(
                    try sourceWithRawInteger(lexeme),
                    using: decode,
                    reason: "integer field accepted \(lexeme)"
                )
            }

            for lexeme in [
                "1", "1.5", "1e-7", "5e-324", "1e+30",
                "333333333.3333333", "9007199254740991",
                "-9007199254740991",
            ] {
                XCTAssertNoThrow(
                    try decode(try sourceWithRawRecursiveNumber(lexeme)),
                    "recursive number \(lexeme)"
                )
            }
            for lexeme in [
                "1.0", "1e0", "-0", "-0.0", "1e400",
                "9007199254740992", "-9007199254740992",
                "9223372036854775808", "-9223372036854775809",
            ] {
                assertRejected(
                    try sourceWithRawRecursiveNumber(lexeme),
                    using: decode,
                    reason: "recursive JSON number accepted \(lexeme)"
                )
            }
        }
    }

    private func exerciseEventEnvelopeCanonicalBoundsAndScope(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "event and envelope canonical bytes and depth are path scoped",
            using: decode
        ) { decode in
            let maximumBytes = RoundTransportLimits.maxEventCanonicalBytes
            XCTAssertNoThrow(
                try decode(try sourceWithEventCanonicalBytes(maximumBytes))
            )
            assertRejected(
                try sourceWithEventCanonicalBytes(maximumBytes + 1),
                using: decode,
                reason: "event exceeded its canonical-byte limit"
            )
            XCTAssertNoThrow(
                try decode(try sourceWithEnvelopeCanonicalBytes(maximumBytes))
            )
            assertRejected(
                try sourceWithEnvelopeCanonicalBytes(maximumBytes + 1),
                using: decode,
                reason: "envelope exceeded its canonical-byte limit"
            )

            let maximumDepth = RoundTransportLimits.maxEventJsonDepth
            XCTAssertNoThrow(
                try decode(
                    try sourceWithEventRelativeDepth(maximumDepth)
                )
            )
            assertRejected(
                try sourceWithEventRelativeDepth(maximumDepth + 1),
                using: decode,
                reason: "event exceeded its relative-depth limit"
            )
            XCTAssertNoThrow(
                try decode(
                    try sourceWithEnvelopeRelativeDepth(maximumDepth)
                )
            )
            assertRejected(
                try sourceWithEnvelopeRelativeDepth(maximumDepth + 1),
                using: decode,
                reason: "envelope exceeded its relative-depth limit"
            )
        }
    }

    private func exerciseUnconstrainedLegacyAndRecursiveJSON(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "legacy batch events and unrelated recursive JSON stay unconstrained",
            using: decode
        ) { _ in
            let legacyBatch = try XCTUnwrap(
                storageV1Types.first { $0.name == "LegacyV1EventBatchBody" }
            )
            guard case .record(let members) = legacyBatch.shape else {
                return XCTFail("LegacyV1EventBatchBody must be a record")
            }
            let events = try XCTUnwrap(
                members.first { $0.name == "events" }
            )
            guard case .array(let item) = events.shape,
                  case .reference(let name) = item else {
                return XCTFail("legacy events must be an unconstrained array reference")
            }
            XCTAssertEqual(name, "JSONValue")

            let recursive = try XCTUnwrap(
                storageV1Types.first { $0.name == "JSONValue" }
            )
            guard case .recursiveJSONValue(let profile) = recursive.shape else {
                return XCTFail("JSONValue must retain its recursive descriptor")
            }
            guard case .ordinaryString = profile else {
                return XCTFail("recursive JSON strings need the ordinary profile")
            }
        }
    }

    private func exerciseCanonicalStringSetAtFinalDecode(
        using decode: @escaping Decode
    ) throws {
        try activity(
            "canonical string set is sorted and unique at final typed decode",
            using: decode
        ) { decode in
            let sorted = try source(mutating: []) { root in
                root["migrationMarkers"] = ["a", "z", "é", "球"]
            }
            XCTAssertNoThrow(try decode(sorted))

            for invalid in [
                ["z", "a"],
                ["a", "a"],
            ] {
                let candidate = try source(mutating: []) { root in
                    root["migrationMarkers"] = invalid
                }
                assertRejected(
                    candidate,
                    using: decode,
                    reason: "noncanonical marker set was accepted: \(invalid)"
                )
            }
        }
    }

    private func representativeSource() throws -> String {
        try source(from: try representativeJSONObject())
    }

    private func representativeJSONObject() throws -> [String: Any] {
        try XCTUnwrap(
            JSONSerialization.jsonObject(
                with: JSONEncoder().encode(representativeState())
            ) as? [String: Any]
        )
    }

    private func representativeState() -> DomainLedgerStateV1 {
        let accepted = receipt("accepted", status: .accepted)
        let duplicate = receipt("duplicate", status: .duplicateHashMatch)
        let rejected = receipt("rejected", status: .rejectedPermanent)
        let event = StoredEventV1(
            eventId: "event-1",
            originDeviceId: "ios-1",
            originEpoch: "epoch-1",
            clientSequence: 1,
            roundId: "round-1",
            kind: RoundEventKind(rawValue: "future_round_event_kind"),
            payload: [
                "array": .array([.integer(1), .number(1.5), .null]),
                "bool": .bool(true),
                "object": .object(["text": .string("value")]),
            ],
            occurredAt: "2026-07-25T00:00:01Z"
        )
        let outbox = LegacyV1OutboxRecord(
            eventIdentity: accepted.eventIdentity,
            eventHash: accepted.eventHash,
            receipt: accepted,
            deadLetterReason: nil
        )
        let deadLetter = LegacyV1OutboxRecord(
            eventIdentity: rejected.eventIdentity,
            eventHash: rejected.eventHash,
            receipt: rejected,
            deadLetterReason: "permanent"
        )
        let binding = LegacyWireBinding(
            roundId: "round-1",
            wireClientId: "ios-1",
            wireEventId: "wire-event-1",
            canonicalDomainIdentity: "domain-identity-1",
            canonicalDomainEventHash: "domain-hash-1",
            normalizedWireEnvelopeHash: "envelope-hash-1",
            legacyAliases: [
                LegacyDomainAlias(
                    eventIdentity: "legacy-identity-1",
                    eventHash: "legacy-hash-1"
                ),
            ]
        )
        let slot = PreparedLegacyV1Slot(
            bindingKey: "binding-key-1",
            exactNormalizedEnvelope: .object([
                "eventId": .string("wire-event-1"),
            ]),
            exactNormalizedEnvelopeHash: "envelope-hash-1"
        )
        let batch = PreparedLegacyV1Batch(
            roundId: "round-1",
            orderedSlots: [slot],
            exactRequestBody: Data(
                #"{"roundId":"round-1","events":[]}"#.utf8
            ),
            requestBodySha256: "request-hash-1",
            idempotencyKey: "idempotency-key-1"
        )
        return DomainLedgerStateV1(
            origin: OriginSequenceState(
                originDeviceId: "ios-1",
                originEpoch: "epoch-1",
                lastReservedClientSequence: 1
            ),
            events: [event],
            outbox: [outbox],
            deadLetters: [deadLetter],
            receipts: [
                "accepted": accepted,
                "duplicate": duplicate,
                "rejected": rejected,
            ],
            legacyWireBindings: [binding],
            preparedLegacyV1Batches: [batch],
            watchTerminalReceiptRelayObligations: [
                WatchTerminalReceiptRelayObligation(
                    obligationId: "obligation-1",
                    eventIdentity: duplicate.eventIdentity,
                    eventHash: duplicate.eventHash,
                    status: duplicate.status
                ),
            ],
            watchTerminalReceiptRelayConfirmations: [
                WatchTerminalReceiptRelayConfirmation(
                    confirmationId: "confirmation-1",
                    obligationId: "obligation-1",
                    eventIdentity: rejected.eventIdentity,
                    eventHash: rejected.eventHash,
                    status: rejected.status
                ),
            ],
            migrationMarkers: CanonicalStringSet(Set(["a-marker", "z-marker"])),
            transportAnomalies: [
                LegacyV1TransportAnomaly(
                    roundId: "round-1",
                    code: "literal-code",
                    evidence: "literal-evidence"
                ),
            ]
        )
    }

    private func receipt(
        _ suffix: String,
        status: LegacyV1TerminalStatus
    ) -> LegacyV1EventReceipt {
        LegacyV1EventReceipt(
            eventIdentity: "identity-\(suffix)",
            eventHash: "hash-\(suffix)",
            status: status,
            serverSequence: 1
        )
    }

    private func source(
        mutating path: [PathComponent],
        _ mutation: (inout [String: Any]) throws -> Void
    ) throws -> String {
        var root: Any = try representativeJSONObject()
        try mutate(&root, at: path[...], mutation)
        return try source(from: root)
    }

    private func sourceWithRawPayloadMembers(_ members: String) throws -> String {
        let sentinel = "__PAYLOAD_SENTINEL__"
        let source = try source(mutating: [
            .key("events"), .index(0),
        ]) { event in
            event["payload"] = [sentinel: true]
        }
        let needle = #""payload":{"__PAYLOAD_SENTINEL__":true}"#
        let replacement = #""payload":{"# + members + "}"
        XCTAssertTrue(source.contains(needle))
        return source.replacingOccurrences(of: needle, with: replacement)
    }

    private func sourceWithRequestBody(_ body: String) throws -> String {
        try source(mutating: [
            .key("preparedLegacyV1Batches"), .index(0),
        ]) { batch in
            batch["exactRequestBody"] = body
        }
    }

    private func sourceWithRawInteger(_ lexeme: String) throws -> String {
        let sentinel = "__INTEGER_SENTINEL__"
        let source = try source(mutating: [.key("origin")]) { origin in
            origin["lastReservedClientSequence"] = sentinel
        }
        return try replacingExactlyOnce(
            "\"\(sentinel)\"",
            with: lexeme,
            in: source
        )
    }

    private func sourceWithRawRecursiveNumber(_ lexeme: String) throws -> String {
        let sentinel = "__NUMBER_SENTINEL__"
        let source = try source(mutating: [
            .key("events"), .index(0),
        ]) { event in
            event["payload"] = ["number": sentinel]
        }
        return try replacingExactlyOnce(
            "\"\(sentinel)\"",
            with: lexeme,
            in: source
        )
    }

    private func sourceWithEventCanonicalBytes(_ byteCount: Int) throws -> String {
        let event = try paddedEvent(canonicalByteCount: byteCount)
        let bytes = try CanonicalJSON.data(event)
        XCTAssertEqual(bytes.count, byteCount)
        let eventSource = try XCTUnwrap(String(data: bytes, encoding: .utf8))
        return try replacingExactlyOnce(
            #""events":[]"#,
            with: #""events":[\#(eventSource)]"#,
            in: minimalStorageDocument
        )
    }

    private func sourceWithEnvelopeCanonicalBytes(_ byteCount: Int) throws -> String {
        let envelope = try paddedEnvelope(canonicalByteCount: byteCount)
        let bytes = try CanonicalJSON.data(envelope)
        XCTAssertEqual(bytes.count, byteCount)
        let object = try JSONSerialization.jsonObject(with: bytes)
        return try source(mutating: [
            .key("preparedLegacyV1Batches"), .index(0),
            .key("orderedSlots"), .index(0),
        ]) { slot in
            slot["exactNormalizedEnvelope"] = object
        }
    }

    private func paddedEvent(canonicalByteCount: Int) throws -> JSONValue {
        let empty = eventValue(padding: [])
        let emptyCount = try CanonicalJSON.data(empty).count
        let padding = try paddingStrings(
            additionalCanonicalBytes: canonicalByteCount - emptyCount
        )
        let result = eventValue(padding: padding)
        XCTAssertEqual(
            try CanonicalJSON.data(result).count,
            canonicalByteCount
        )
        return result
    }

    private func eventValue(padding: [JSONValue]) -> JSONValue {
        .object([
            "eventId": .string(""),
            "originDeviceId": .string(""),
            "originEpoch": .string(""),
            "clientSequence": .integer(0),
            "roundId": .string(""),
            "kind": .string(""),
            "payload": .object(["padding": .array(padding)]),
            "occurredAt": .string(""),
        ])
    }

    private func paddedEnvelope(canonicalByteCount: Int) throws -> JSONValue {
        let empty: JSONValue = .object(["padding": .array([])])
        let emptyCount = try CanonicalJSON.data(empty).count
        let padding = try paddingStrings(
            additionalCanonicalBytes: canonicalByteCount - emptyCount
        )
        let result: JSONValue = .object(["padding": .array(padding)])
        XCTAssertEqual(
            try CanonicalJSON.data(result).count,
            canonicalByteCount
        )
        return result
    }

    private func paddingStrings(
        additionalCanonicalBytes: Int
    ) throws -> [JSONValue] {
        guard additionalCanonicalBytes > 0 else {
            XCTAssertEqual(additionalCanonicalBytes, 0)
            return []
        }
        let maximumScalars = RoundTransportLimits.maxJsonStringCharacters
        let perFullElement = maximumScalars + 3
        let elementCount = (additionalCanonicalBytes + 1 + perFullElement - 1)
            / perFullElement
        let scalarTotal = additionalCanonicalBytes - (3 * elementCount) + 1
        XCTAssertGreaterThanOrEqual(scalarTotal, 0)
        XCTAssertLessThanOrEqual(scalarTotal, maximumScalars * elementCount)

        var remaining = scalarTotal
        var result: [JSONValue] = []
        result.reserveCapacity(elementCount)
        for _ in 0..<elementCount {
            let count = min(maximumScalars, remaining)
            result.append(.string(String(repeating: "a", count: count)))
            remaining -= count
        }
        XCTAssertEqual(remaining, 0)
        return result
    }

    private func sourceWithEventRelativeDepth(_ depth: Int) throws -> String {
        let payloadDepth = depth - 2
        XCTAssertGreaterThanOrEqual(payloadDepth, 0)
        let source = try source(mutating: [
            .key("events"), .index(0),
        ]) { event in
            event["payload"] = ["nested": nestedArray(depth: payloadDepth)]
        }
        return source
    }

    private func sourceWithEnvelopeRelativeDepth(_ depth: Int) throws -> String {
        try source(mutating: [
            .key("preparedLegacyV1Batches"), .index(0),
            .key("orderedSlots"), .index(0),
        ]) { slot in
            slot["exactNormalizedEnvelope"] = nestedArray(depth: depth)
        }
    }

    private func nestedArray(depth: Int) -> Any {
        var result: Any = NSNull()
        for _ in 0..<depth {
            result = [result]
        }
        return result
    }

    private func rootSource(
        _ target: RootCollectionTarget,
        count: Int
    ) throws -> String {
        let replacement: String
        switch target.payload {
        case .array(let element):
            replacement = "[" + repeatedJSON(element, count: count) + "]"
        case .object(let value):
            let members = (0..<count).map { index in
                let key = String(format: "r%05d", index)
                return "\"\(key)\":\(value)"
            }.joined(separator: ",")
            replacement = "{" + members + "}"
        case .sortedStrings:
            let values = (0..<count).map { index in
                "\"" + String(format: "m%05d", index) + "\""
            }.joined(separator: ",")
            replacement = "[" + values + "]"
        }

        let empty = target.payload.emptyJSON
        return try replacingExactlyOnce(
            #""\#(target.key)":\#(empty)"#,
            with: #""\#(target.key)":\#(replacement)"#,
            in: minimalStorageDocument
        )
    }

    private func repeatedJSON(_ element: String, count: Int) -> String {
        guard count > 0 else { return "" }
        return Array(repeating: element, count: count).joined(separator: ",")
    }

    private func replacingExactlyOnce(
        _ needle: String,
        with replacement: String,
        in source: String
    ) throws -> String {
        let matches = source.components(separatedBy: needle).count - 1
        XCTAssertEqual(matches, 1, "replacement needle must occur exactly once")
        guard matches == 1 else { return source }
        return source.replacingOccurrences(of: needle, with: replacement)
    }

    private func mutate(
        _ value: inout Any,
        at path: ArraySlice<PathComponent>,
        _ mutation: (inout [String: Any]) throws -> Void
    ) throws {
        guard let component = path.first else {
            var object = try XCTUnwrap(value as? [String: Any])
            try mutation(&object)
            value = object
            return
        }

        switch component {
        case .key(let key):
            var object = try XCTUnwrap(value as? [String: Any])
            var child = try XCTUnwrap(object[key])
            try mutate(&child, at: path.dropFirst(), mutation)
            object[key] = child
            value = object

        case .index(let index):
            var array = try XCTUnwrap(value as? [Any])
            var child = try XCTUnwrap(
                array.indices.contains(index) ? array[index] : nil
            )
            try mutate(&child, at: path.dropFirst(), mutation)
            array[index] = child
            value = array
        }
    }

    private func value(
        in root: Any,
        at path: ArraySlice<PathComponent>
    ) throws -> Any {
        guard let component = path.first else { return root }
        switch component {
        case .key(let key):
            let object = try XCTUnwrap(root as? [String: Any])
            return try value(
                in: XCTUnwrap(object[key]),
                at: path.dropFirst()
            )
        case .index(let index):
            let array = try XCTUnwrap(root as? [Any])
            return try value(
                in: XCTUnwrap(array.indices.contains(index) ? array[index] : nil),
                at: path.dropFirst()
            )
        }
    }

    private func source(from value: Any) throws -> String {
        let data = try JSONSerialization.data(
            withJSONObject: value,
            options: [.sortedKeys]
        )
        return try XCTUnwrap(String(data: data, encoding: .utf8))
    }

    private func assertRejected(
        _ source: String,
        using decode: Decode,
        reason: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(
            try decode(source),
            reason,
            file: file,
            line: line
        )
    }
}
