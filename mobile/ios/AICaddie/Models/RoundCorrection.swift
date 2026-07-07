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

/// One review-edit operation, POSTed to `/api/v2/history/rounds/{ref}/corrections`
/// (mirrors server `RoundCorrectionRequest`). Only non-nil fields go on the wire, and every op
/// carries a fresh `clientMutationId` so retries are idempotent.
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
    public var clientMutationId: String?

    public init(op: String, shotId: String? = nil, hole: Int? = nil, field: String? = nil,
                value: AnyCodableValue? = nil, reason: String? = nil, px: [Double]? = nil,
                club: String? = nil, lie: String? = nil, insertAfterShotId: String? = nil,
                order: [String]? = nil, clientMutationId: String? = UUID().uuidString) {
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
        self.clientMutationId = clientMutationId
    }

    private enum CodingKeys: String, CodingKey {
        case op, shotId, hole, field, value, reason, px, club, lie, insertAfterShotId, order, clientMutationId
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
}
