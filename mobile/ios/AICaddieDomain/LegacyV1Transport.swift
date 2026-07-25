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

// RED-only seam uses synthesized optional Codable, which omits nil keys and
// accepts missing keys.
struct LegacyV1OutboxRecord: Codable, Equatable {
    let eventIdentity: String
    let eventHash: String
    let receipt: LegacyV1EventReceipt?
    let deadLetterReason: String?
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
