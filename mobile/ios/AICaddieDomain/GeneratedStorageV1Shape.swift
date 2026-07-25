// generated; do not edit
internal enum StorageV1ProfileName {
    case ordinaryString
    case rootCollection
    case preparedSlots
    case requestBody
    case eventOrEnvelope
}

internal enum StorageV1PolicyName {
    case rootCollection
    case preparedSlots
    case requestBody
    case eventOrEnvelope
}

internal enum StorageV1CollectionRepresentation {
    case sortedUniqueArray
}

internal enum StorageV1Base64Alphabet {
    case standard
}

internal enum StorageV1Base64Padding {
    case required
}

internal enum StorageV1LimitReference {
    case literal(Int)
    case authority(name: String, value: Int)
}

internal enum StorageV1LimitProfileDescriptor {
    case stringScalars(maximum: StorageV1LimitReference)
    case count(minimum: StorageV1LimitReference?, maximum: StorageV1LimitReference)
    case base64(
        alphabet: StorageV1Base64Alphabet,
        padding: StorageV1Base64Padding,
        maximumTextScalars: StorageV1LimitReference,
        maximumDecodedBytes: StorageV1LimitReference
    )
    case canonicalJSON(
        maximumBytes: StorageV1LimitReference,
        maximumDepth: StorageV1LimitReference
    )
}

internal enum StorageV1ScalarDescriptor {
    case string(profile: StorageV1ProfileName)
    case int
    case base64Data
}

internal indirect enum StorageV1ShapeDescriptor {
    case scalar(StorageV1ScalarDescriptor)
    case reference(String)
    case array(StorageV1ShapeDescriptor)
    case dynamicMap(StorageV1ShapeDescriptor)
    case nullable(StorageV1ShapeDescriptor)
    case constrained(policy: StorageV1PolicyName, value: StorageV1ShapeDescriptor)
    case literalInt(Int)
    case record([StorageV1MemberDescriptor])
    case collection(
        representation: StorageV1CollectionRepresentation,
        items: StorageV1ShapeDescriptor
    )
    case openString(profile: StorageV1ProfileName)
    case closedEnum([String])
    case recursiveJSONValue(stringProfile: StorageV1ProfileName)
}

internal struct StorageV1MemberDescriptor {
    internal let name: String
    internal let shape: StorageV1ShapeDescriptor
}

internal struct StorageV1RootDescriptor {
    internal let name: String
    internal let shape: StorageV1ShapeDescriptor
}

internal struct StorageV1TypeDescriptor {
    internal let name: String
    internal let shape: StorageV1ShapeDescriptor
}

internal struct StorageV1PolicyDescriptor {
    internal let name: StorageV1PolicyName
    internal let profile: StorageV1ProfileName
}

internal struct StorageV1NamedLimitProfile {
    internal let name: StorageV1ProfileName
    internal let descriptor: StorageV1LimitProfileDescriptor
}

internal let storageV1ShapeSourceSHA256 = "20449e09109502907bb9f483544cca5e4d63613d2ad8e28da7bb85110bd093bf"

internal let storageV1ReferencedDomainTypes: [Any.Type] = [
    StoredEventV1.self,
    OriginSequenceState.self,
    CanonicalStringSet.self,
    DomainLedgerStateV1.self,
    LegacyDomainAlias.self,
    LegacyWireBinding.self,
    PreparedLegacyV1Slot.self,
    PreparedLegacyV1Batch.self,
    LegacyV1TerminalStatus.self,
    LegacyV1EventReceipt.self,
    LegacyV1OutboxRecord.self,
    LegacyV1TransportAnomaly.self,
    WatchTerminalReceiptRelayObligation.self,
    WatchTerminalReceiptRelayConfirmation.self,
    LegacyV1EventBatchBody.self,
    RoundEventKind.self,
    JSONValue.self,
]

internal let storageV1LimitProfiles: [StorageV1NamedLimitProfile] = [
    .init(name: .ordinaryString, descriptor: .stringScalars(maximum: .authority(name: "RoundTransportLimits.maxJsonStringCharacters", value: RoundTransportLimits.maxJsonStringCharacters))),
    .init(name: .rootCollection, descriptor: .count(minimum: nil, maximum: .literal(65536))),
    .init(name: .preparedSlots, descriptor: .count(minimum: .literal(1), maximum: .authority(name: "RoundTransportLimits.maxEventsPerBatch", value: RoundTransportLimits.maxEventsPerBatch))),
    .init(name: .requestBody, descriptor: .base64(alphabet: .standard, padding: .required, maximumTextScalars: .authority(name: "StorageV1RawJSONGate.maximumStringScalars", value: StorageV1RawJSONGate.maximumStringScalars), maximumDecodedBytes: .authority(name: "RoundTransportLimits.maxHttpBodyBytes", value: RoundTransportLimits.maxHttpBodyBytes))),
    .init(name: .eventOrEnvelope, descriptor: .canonicalJSON(maximumBytes: .authority(name: "RoundTransportLimits.maxEventCanonicalBytes", value: RoundTransportLimits.maxEventCanonicalBytes), maximumDepth: .authority(name: "RoundTransportLimits.maxEventJsonDepth", value: RoundTransportLimits.maxEventJsonDepth))),
]

internal let storageV1Policies: [StorageV1PolicyDescriptor] = [
    .init(name: .rootCollection, profile: .rootCollection),
    .init(name: .preparedSlots, profile: .preparedSlots),
    .init(name: .requestBody, profile: .requestBody),
    .init(name: .eventOrEnvelope, profile: .eventOrEnvelope),
]

internal let storageV1Roots: [StorageV1RootDescriptor] = [
    .init(name: "storageDocument", shape: .reference("DomainLedgerStateV1")),
    .init(name: "legacyV1EventBatchBody", shape: .reference("LegacyV1EventBatchBody")),
]

internal let storageV1Types: [StorageV1TypeDescriptor] = [
    .init(name: "StoredEventV1", shape: .record([.init(name: "eventId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "originDeviceId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "originEpoch", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "clientSequence", shape: .scalar(.int)), .init(name: "roundId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "kind", shape: .reference("RoundEventKind")), .init(name: "payload", shape: .dynamicMap(.reference("JSONValue"))), .init(name: "occurredAt", shape: .scalar(.string(profile: .ordinaryString)))])),
    .init(name: "OriginSequenceState", shape: .record([.init(name: "originDeviceId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "originEpoch", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "lastReservedClientSequence", shape: .scalar(.int))])),
    .init(name: "CanonicalStringSet", shape: .collection(representation: .sortedUniqueArray, items: .scalar(.string(profile: .ordinaryString)))),
    .init(name: "DomainLedgerStateV1", shape: .record([.init(name: "storageVersion", shape: .literalInt(1)), .init(name: "origin", shape: .reference("OriginSequenceState")), .init(name: "events", shape: .constrained(policy: .rootCollection, value: .array(.constrained(policy: .eventOrEnvelope, value: .reference("StoredEventV1"))))), .init(name: "outbox", shape: .constrained(policy: .rootCollection, value: .array(.reference("LegacyV1OutboxRecord")))), .init(name: "deadLetters", shape: .constrained(policy: .rootCollection, value: .array(.reference("LegacyV1OutboxRecord")))), .init(name: "receipts", shape: .constrained(policy: .rootCollection, value: .dynamicMap(.reference("LegacyV1EventReceipt")))), .init(name: "legacyWireBindings", shape: .constrained(policy: .rootCollection, value: .array(.reference("LegacyWireBinding")))), .init(name: "preparedLegacyV1Batches", shape: .constrained(policy: .rootCollection, value: .array(.reference("PreparedLegacyV1Batch")))), .init(name: "watchTerminalReceiptRelayObligations", shape: .constrained(policy: .rootCollection, value: .array(.reference("WatchTerminalReceiptRelayObligation")))), .init(name: "watchTerminalReceiptRelayConfirmations", shape: .constrained(policy: .rootCollection, value: .array(.reference("WatchTerminalReceiptRelayConfirmation")))), .init(name: "migrationMarkers", shape: .constrained(policy: .rootCollection, value: .reference("CanonicalStringSet"))), .init(name: "transportAnomalies", shape: .constrained(policy: .rootCollection, value: .array(.reference("LegacyV1TransportAnomaly"))))])),
    .init(name: "LegacyDomainAlias", shape: .record([.init(name: "eventIdentity", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "eventHash", shape: .scalar(.string(profile: .ordinaryString)))])),
    .init(name: "LegacyWireBinding", shape: .record([.init(name: "roundId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "wireClientId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "wireEventId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "canonicalDomainIdentity", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "canonicalDomainEventHash", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "normalizedWireEnvelopeHash", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "legacyAliases", shape: .array(.reference("LegacyDomainAlias")))])),
    .init(name: "PreparedLegacyV1Slot", shape: .record([.init(name: "bindingKey", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "exactNormalizedEnvelope", shape: .constrained(policy: .eventOrEnvelope, value: .reference("JSONValue"))), .init(name: "exactNormalizedEnvelopeHash", shape: .scalar(.string(profile: .ordinaryString)))])),
    .init(name: "PreparedLegacyV1Batch", shape: .record([.init(name: "roundId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "orderedSlots", shape: .constrained(policy: .preparedSlots, value: .array(.reference("PreparedLegacyV1Slot")))), .init(name: "exactRequestBody", shape: .constrained(policy: .requestBody, value: .scalar(.base64Data))), .init(name: "requestBodySha256", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "idempotencyKey", shape: .scalar(.string(profile: .ordinaryString)))])),
    .init(name: "LegacyV1TerminalStatus", shape: .closedEnum(["accepted", "duplicate_hash_match", "rejected_permanent"])),
    .init(name: "LegacyV1EventReceipt", shape: .record([.init(name: "eventIdentity", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "eventHash", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "status", shape: .reference("LegacyV1TerminalStatus")), .init(name: "serverSequence", shape: .scalar(.int))])),
    .init(name: "LegacyV1OutboxRecord", shape: .record([.init(name: "eventIdentity", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "eventHash", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "receipt", shape: .nullable(.reference("LegacyV1EventReceipt"))), .init(name: "deadLetterReason", shape: .nullable(.scalar(.string(profile: .ordinaryString))))])),
    .init(name: "LegacyV1TransportAnomaly", shape: .record([.init(name: "roundId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "code", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "evidence", shape: .scalar(.string(profile: .ordinaryString)))])),
    .init(name: "WatchTerminalReceiptRelayObligation", shape: .record([.init(name: "obligationId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "eventIdentity", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "eventHash", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "status", shape: .reference("LegacyV1TerminalStatus"))])),
    .init(name: "WatchTerminalReceiptRelayConfirmation", shape: .record([.init(name: "confirmationId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "obligationId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "eventIdentity", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "eventHash", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "status", shape: .reference("LegacyV1TerminalStatus"))])),
    .init(name: "LegacyV1EventBatchBody", shape: .record([.init(name: "roundId", shape: .scalar(.string(profile: .ordinaryString))), .init(name: "events", shape: .array(.reference("JSONValue")))])),
    .init(name: "RoundEventKind", shape: .openString(profile: .ordinaryString)),
    .init(name: "JSONValue", shape: .recursiveJSONValue(stringProfile: .ordinaryString)),
]
