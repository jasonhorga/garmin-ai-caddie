import Foundation

public enum JSONValue: Codable, Equatable {
    case integer(Int64)
    case number(Double)
    case null
    case bool(Bool)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public init(from decoder: Decoder) throws {
        self = .null
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encodeNil()
    }
}
