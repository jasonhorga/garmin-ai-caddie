import Foundation

public struct WatchSyncAcknowledgement: Equatable {
    public let acceptedEventIds: [String]
    public let duplicateEventIds: [String]
    public let rejectedEventIds: [String]
    public let phoneSequence: Int

    public var acknowledgedEventIds: [String] {
        acceptedEventIds + duplicateEventIds
    }

    public var resolvedEventIds: [String] {
        acceptedEventIds + duplicateEventIds + rejectedEventIds
    }

    public static func decode(_ reply: [String: Any], fallbackEventId: String) -> WatchSyncAcknowledgement {
        let accepted = reply["accepted"] as? Bool ?? false
        let eventId = reply["eventId"] as? String ?? fallbackEventId
        let explicitAcceptedEventIds = stringArray(reply["acceptedEventIds"])
        let acceptedEventIds = explicitAcceptedEventIds ?? (accepted ? [eventId] : [])
        let duplicateEventIds = stringArray(reply["duplicateEventIds"]) ?? []
        let rejectedEventIds = stringArray(reply["rejectedEventIds"]) ?? []
        let phoneSequence = intValue(reply["phoneSequence"]) ?? intValue(reply["watchAckSequence"]) ?? 0

        return WatchSyncAcknowledgement(
            acceptedEventIds: acceptedEventIds,
            duplicateEventIds: duplicateEventIds,
            rejectedEventIds: rejectedEventIds,
            phoneSequence: phoneSequence
        )
    }

    private static func stringArray(_ value: Any?) -> [String]? {
        value as? [String]
    }

    private static func intValue(_ value: Any?) -> Int? {
        if let raw = value as? Int {
            return raw
        }
        if let raw = value as? Double, raw.isFinite {
            return Int(raw)
        }
        return nil
    }
}
