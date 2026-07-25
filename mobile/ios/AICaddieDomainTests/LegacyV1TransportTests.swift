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
