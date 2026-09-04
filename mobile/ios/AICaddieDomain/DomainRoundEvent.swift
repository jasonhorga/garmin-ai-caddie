import Foundation

struct StoredEventV1: Codable, Equatable {
    let eventId: String
    let originDeviceId: String
    let originEpoch: String
    let clientSequence: Int
    let roundId: String
    let kind: RoundEventKind
    let payload: [String: JSONValue]
    let occurredAt: String
}
