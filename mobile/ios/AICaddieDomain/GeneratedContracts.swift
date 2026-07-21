// generated; do not edit
public let canonicalContractSourceSHA256 = "f49c911225cac30cfdddfe5c485d217c6c199a432831f66855a509a96d6aec5c"

public struct CanonicalObjectDescriptor: Sendable, Equatable {
    public let objectName: String
    public let domainTag: String
    public let schemaRef: String
    public let includedFields: [String]
    public let excludedFields: [String]
}

public enum GeneratedCanonicalObjects {
    public static let byDomain: [String: CanonicalObjectDescriptor] = [
        "CanonicalFixtureAlpha/v1": CanonicalObjectDescriptor(objectName: "CanonicalFixtureAlpha", domainTag: "CanonicalFixtureAlpha/v1", schemaRef: "contracts/canonical/canonical_fixture_v1.schema.json", includedFields: ["*"], excludedFields: ["transportNote"]),
        "CanonicalFixtureBeta/v1": CanonicalObjectDescriptor(objectName: "CanonicalFixtureBeta", domainTag: "CanonicalFixtureBeta/v1", schemaRef: "contracts/canonical/canonical_fixture_v1.schema.json", includedFields: ["*"], excludedFields: ["transportNote"]),
    ]
}

public enum RoundEventSubmissionClass: String, Codable, Sendable {
    case ordinaryEvent = "ordinary_event"
    case resolutionPrerequisite = "resolution_prerequisite"
    case ordinaryOrResolutionCommit = "ordinary_or_resolution_commit"
    case resolutionCommitOnly = "resolution_commit_only"
}

public struct RoundEventKind: RawRepresentable, Codable, Hashable, Sendable {
    public let rawValue: String
    public init(rawValue: String) { self.rawValue = rawValue }
    public init(from decoder: Decoder) throws {
        self.rawValue = try decoder.singleValueContainer().decode(String.self)
    }
    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
    public static let knownValues: Set<String> = []
    public static let submissionClasses: [String: RoundEventSubmissionClass] = [:]
}

public struct ReasonCode: RawRepresentable, Codable, Hashable, Sendable {
    public let rawValue: String
    public init(rawValue: String) { self.rawValue = rawValue }
    public init(from decoder: Decoder) throws {
        self.rawValue = try decoder.singleValueContainer().decode(String.self)
    }
    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
    public static let accountPrincipalConflict = ReasonCode(rawValue: "account_principal_conflict")
    public static let actorNotAuthorized = ReasonCode(rawValue: "actor_not_authorized")
    public static let bindingNotEstablished = ReasonCode(rawValue: "binding_not_established")
    public static let bootstrapRequired = ReasonCode(rawValue: "bootstrap_required")
    public static let consumerAckAheadOfStream = ReasonCode(rawValue: "consumer_ack_ahead_of_stream")
    public static let deadLetterQuotaExceeded = ReasonCode(rawValue: "dead_letter_quota_exceeded")
    public static let entityBaseRevisionConflict = ReasonCode(rawValue: "entity_base_revision_conflict")
    public static let eventBatchTooLarge = ReasonCode(rawValue: "event_batch_too_large")
    public static let eventEnvelopeLimitExceeded = ReasonCode(rawValue: "event_envelope_limit_exceeded")
    public static let flagPositionNotPlayerSet = ReasonCode(rawValue: "flag_position_not_player_set")
    public static let greenSurfaceQuarantined = ReasonCode(rawValue: "green_surface_quarantined")
    public static let idempotencyKeyBodyMismatch = ReasonCode(rawValue: "idempotency_key_body_mismatch")
    public static let identityEnvelopeMismatch = ReasonCode(rawValue: "identity_envelope_mismatch")
    public static let illegalLifecycleTransition = ReasonCode(rawValue: "illegal_lifecycle_transition")
    public static let invalidDeviceProof = ReasonCode(rawValue: "invalid_device_proof")
    public static let legacyMigrationInvalidPayload = ReasonCode(rawValue: "legacy_migration_invalid_payload")
    public static let legacyMigrationMalformed = ReasonCode(rawValue: "legacy_migration_malformed")
    public static let legacyMigrationUnmappable = ReasonCode(rawValue: "legacy_migration_unmappable")
    public static let mergeControlNotReady = ReasonCode(rawValue: "merge_control_not_ready")
    public static let mergeSemanticBindingMismatch = ReasonCode(rawValue: "merge_semantic_binding_mismatch")
    public static let missingEventReceipt = ReasonCode(rawValue: "missing_event_receipt")
    public static let payloadSchemaInvalid = ReasonCode(rawValue: "payload_schema_invalid")
    public static let peerLedgerBundleInvalid = ReasonCode(rawValue: "peer_ledger_bundle_invalid")
    public static let playerCancelledTarget = ReasonCode(rawValue: "player_cancelled_target")
    public static let projectionDependencyCycle = ReasonCode(rawValue: "projection_dependency_cycle")
    public static let replayGapDetected = ReasonCode(rawValue: "replay_gap_detected")
    public static let requestBodyTooLarge = ReasonCode(rawValue: "request_body_too_large")
    public static let resolutionCommitConflict = ReasonCode(rawValue: "resolution_commit_conflict")
    public static let resolutionCommitInvalidBundle = ReasonCode(rawValue: "resolution_commit_invalid_bundle")
    public static let resolutionCommitRequired = ReasonCode(rawValue: "resolution_commit_required")
    public static let resolutionEpisodeConflict = ReasonCode(rawValue: "resolution_episode_conflict")
    public static let resolutionEpisodeTerminal = ReasonCode(rawValue: "resolution_episode_terminal")
    public static let resolutionRequiredCauseMissing = ReasonCode(rawValue: "resolution_required_cause_missing")
    public static let roundBindingMismatch = ReasonCode(rawValue: "round_binding_mismatch")
    public static let roundStartAuthorityUnavailable = ReasonCode(rawValue: "round_start_authority_unavailable")
    public static let roundStartBindingRejected = ReasonCode(rawValue: "round_start_binding_rejected")
    public static let roundStartIntentConflict = ReasonCode(rawValue: "round_start_intent_conflict")
    public static let shotIdentityConflict = ReasonCode(rawValue: "shot_identity_conflict")
    public static let shotLocationUnavailable = ReasonCode(rawValue: "shot_location_unavailable")
    public static let shotTargetNotPlayerConfirmed = ReasonCode(rawValue: "shot_target_not_player_confirmed")
    public static let shotTargetOrphaned = ReasonCode(rawValue: "shot_target_orphaned")
    public static let transportReceiptHashMismatch = ReasonCode(rawValue: "transport_receipt_hash_mismatch")
    public static let unknownEventKind = ReasonCode(rawValue: "unknown_event_kind")
    public static let unsupportedClientVersion = ReasonCode(rawValue: "unsupported_client_version")
}

public enum RoundTransportLimits {
    public static let maxHttpBodyBytes = 1048576
    public static let maxEventsPerBatch = 64
    public static let maxEventCanonicalBytes = 65536
    public static let maxEventJsonDepth = 16
    public static let maxRawJsonDepth = 64
    public static let maxJsonKeyCharacters = 128
    public static let maxJsonStringCharacters = 4096
    public static let maxDeadLetterRetainedBytes = 16384
    public static let maxDeadLettersPerRound = 2048
    public static let maxDeadLetterPageSize = 100
    public static let maxConsumerEpochCharacters = 128
    public static let maxMergeSourceIncarnations = 8
    public static let maxSyncPathIdCharacters = 128
    public static let maxReplayPageSize = 500
}
