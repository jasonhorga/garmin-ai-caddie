import Foundation

public enum LiveRoundEventKind: String, Codable, CaseIterable, Equatable {
    case score
    case club
    case putt
    case penalty
    case note
    case location
    case photo
    case video
    case syncMarker = "sync_marker"
}

public enum JSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

public struct LiveRoundEvent: Codable, Equatable, Identifiable {
    public var id: String { eventId }

    public let schema: String
    public let eventId: String
    public let roundId: String
    public let timestamp: String
    public let hole: Int
    public let kind: LiveRoundEventKind
    public let payload: [String: JSONValue]

    public init(
        schema: String = "ai-caddie-live-round-event-v1",
        eventId: String,
        roundId: String,
        timestamp: String,
        hole: Int,
        kind: LiveRoundEventKind,
        payload: [String: JSONValue]
    ) {
        self.schema = schema
        self.eventId = eventId
        self.roundId = roundId
        self.timestamp = timestamp
        self.hole = hole
        self.kind = kind
        self.payload = payload
    }
}
