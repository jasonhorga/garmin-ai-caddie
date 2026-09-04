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
