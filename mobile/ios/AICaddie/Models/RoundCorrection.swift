import Foundation

/// A JSON value the backend correction endpoint accepts in `value` (string for club/lie, int for
/// penalty, `[Double]` pixel pair for a dragged position).
public enum AnyCodableValue: Encodable, Equatable {
    case string(String)
    case int(Int)
    case doubles([Double])

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .int(let i): try c.encode(i)
        case .doubles(let d): try c.encode(d)
        }
    }
}

/// One geometry-independent shot fact in an atomic whole-hole save. It deliberately cannot encode
/// start/end pixels or WGS84, so a mapless edit can never move or fabricate the original GPS.
public struct RoundShotFact: Encodable, Equatable {
    public let id: String
    public let club: String?
    public let lie: String?
    public let clubSource: String?
    public let lieSource: String?

    public init?(shot: RoundShot) {
        guard let stableId = shot.shotId?.trimmingCharacters(in: .whitespacesAndNewlines),
              !stableId.isEmpty,
              !shot.synthetic else { return nil }
        id = stableId
        club = shot.club
        lie = shot.lie
        clubSource = shot.clubSource == "manual" ? "manual" : nil
        lieSource = shot.lieSource == "manual" ? "manual" : nil
    }

    private enum CodingKeys: String, CodingKey { case id, club, lie, clubSource, lieSource }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        // A nil value is an intentional user-approved clearing, not an omitted field.
        try c.encode(club, forKey: .club)
        try c.encode(lie, forKey: .lie)
        try c.encodeIfPresent(clubSource, forKey: .clubSource)
        try c.encodeIfPresent(lieSource, forKey: .lieSource)
    }
}

/// One review-edit operation, POSTed to `/api/v2/history/rounds/{ref}/corrections`
/// (mirrors server `RoundCorrectionRequest`). Precise maps commit `replaceHoleShots`; a mapless
/// list commits `replaceHoleFacts`. Both remain one atomic/idempotent whole-hole save.
public struct RoundCorrectionOp: Encodable, Equatable {
    public let op: String
    public var shotId: String?
    public var hole: Int?
    public var field: String?
    public var value: AnyCodableValue?
    public var reason: String?
    public var px: [Double]?
    public var club: String?
    public var lie: String?
    public var insertAfterShotId: String?
    public var order: [String]?
    public var shots: [RoundShot]?
    public var factShots: [RoundShotFact]?
    public var manualPenalty: Int?
    public var geometryRevision: String?
    public var clientMutationId: String?

    public init(op: String, shotId: String? = nil, hole: Int? = nil, field: String? = nil,
                value: AnyCodableValue? = nil, reason: String? = nil, px: [Double]? = nil,
                club: String? = nil, lie: String? = nil, insertAfterShotId: String? = nil,
                order: [String]? = nil, shots: [RoundShot]? = nil,
                factShots: [RoundShotFact]? = nil, manualPenalty: Int? = nil,
                geometryRevision: String? = nil, clientMutationId: String? = UUID().uuidString) {
        self.op = op
        self.shotId = shotId
        self.hole = hole
        self.field = field
        self.value = value
        self.reason = reason
        self.px = px
        self.club = club
        self.lie = lie
        self.insertAfterShotId = insertAfterShotId
        self.order = order
        self.shots = shots
        self.factShots = factShots
        self.manualPenalty = manualPenalty
        self.geometryRevision = geometryRevision
        self.clientMutationId = clientMutationId
    }

    private enum CodingKeys: String, CodingKey {
        case op, shotId, hole, field, value, reason, px, club, lie, insertAfterShotId, order
        case shots, manualPenalty, geometryRevision, clientMutationId
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(op, forKey: .op)
        try c.encodeIfPresent(shotId, forKey: .shotId)
        try c.encodeIfPresent(hole, forKey: .hole)
        try c.encodeIfPresent(field, forKey: .field)
        try c.encodeIfPresent(value, forKey: .value)
        try c.encodeIfPresent(reason, forKey: .reason)
        try c.encodeIfPresent(px, forKey: .px)
        try c.encodeIfPresent(club, forKey: .club)
        try c.encodeIfPresent(lie, forKey: .lie)
        try c.encodeIfPresent(insertAfterShotId, forKey: .insertAfterShotId)
        try c.encodeIfPresent(order, forKey: .order)
        if let factShots {
            try c.encode(factShots, forKey: .shots)
        } else {
            try c.encodeIfPresent(shots, forKey: .shots)
        }
        try c.encodeIfPresent(manualPenalty, forKey: .manualPenalty)
        try c.encodeIfPresent(geometryRevision, forKey: .geometryRevision)
        try c.encodeIfPresent(clientMutationId, forKey: .clientMutationId)
    }

    // MARK: Constructors (one per edit action; delete carries no reason — the design's direct-delete)

    public static func delete(_ id: String) -> Self { .init(op: "deleteShot", shotId: id) }
    public static func editClub(_ id: String, _ v: String) -> Self {
        .init(op: "editField", shotId: id, field: "club", value: .string(v))
    }
    public static func editLie(_ id: String, _ v: String) -> Self {
        .init(op: "editField", shotId: id, field: "lie", value: .string(v))
    }
    public static func move(_ id: String, px: [Double]) -> Self {
        .init(op: "editField", shotId: id, field: "position", value: .doubles(px))
    }
    public static func add(px: [Double], club: String?, lie: String?, after: String?) -> Self {
        .init(op: "addShot", px: px, club: club, lie: lie, insertAfterShotId: after)
    }
    public static func reorder(_ ids: [String]) -> Self { .init(op: "reorderShot", order: ids) }
    public static func setPenalty(hole: Int, _ v: Int) -> Self {
        .init(op: "setHolePenalty", hole: hole, value: .int(v))
    }
    public static func replaceHoleShots(
        hole: Int,
        shots: [RoundShot],
        manualPenalty: Int,
        geometryRevision: String?,
        clientMutationId: String = UUID().uuidString
    ) -> Self {
        .init(
            op: "replaceHoleShots",
            hole: hole,
            shots: shots,
            manualPenalty: max(0, manualPenalty),
            geometryRevision: geometryRevision,
            clientMutationId: clientMutationId
        )
    }

    public static func replaceHoleFacts(
        hole: Int,
        shots: [RoundShot],
        manualPenalty: Int,
        clientMutationId: String = UUID().uuidString
    ) -> Self {
        .init(
            op: "replaceHoleFacts",
            hole: hole,
            factShots: shots.compactMap { RoundShotFact(shot: $0) },
            manualPenalty: max(0, manualPenalty),
            clientMutationId: clientMutationId
        )
    }
}
