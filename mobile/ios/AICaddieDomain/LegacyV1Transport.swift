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
