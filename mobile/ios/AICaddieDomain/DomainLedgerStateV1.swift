import Foundation

struct OriginSequenceState: Codable, Equatable {
    let originDeviceId: String
    let originEpoch: String
    let lastReservedClientSequence: Int
}

// RED-only seam; replaced by Task 3 GREEN.
struct CanonicalStringSet: Codable, Equatable {
    let values: [String]

    init(_ values: Set<String> = []) {
        self.values = Array(values)
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
}
