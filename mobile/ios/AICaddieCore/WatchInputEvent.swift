import Foundation

public enum WatchInputKind: String, Codable, Equatable {
    case score
    case putt
    case penalty
    case club
    case distance
    case location
}

/// Compact value carried by the existing Watch input adapter for a manually captured shot origin.
/// The domain/backend event remains the existing `location` live-round event; this is only the
/// WatchConnectivity/offline-queue representation and adds no second shot protocol.
public struct WatchShotLocationValue: Codable, Equatable {
    public let latitude: Double
    public let longitude: Double
    public let horizontalAccuracyM: Double

    public init?(latitude: Double, longitude: Double, horizontalAccuracyM: Double) {
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              horizontalAccuracyM.isFinite, horizontalAccuracyM >= 0 else {
            return nil
        }
        self.latitude = latitude
        self.longitude = longitude
        self.horizontalAccuracyM = horizontalAccuracyM
    }

    public init?(encodedValue: String) {
        let parts = encodedValue.split(separator: ",", omittingEmptySubsequences: false)
        guard parts.count == 3,
              let latitude = Double(parts[0]),
              let longitude = Double(parts[1]),
              let horizontalAccuracyM = Double(parts[2]) else {
            return nil
        }
        self.init(
            latitude: latitude,
            longitude: longitude,
            horizontalAccuracyM: horizontalAccuracyM
        )
    }

    public var encodedValue: String {
        "\(latitude),\(longitude),\(horizontalAccuracyM)"
    }
}

public struct WatchInputEvent: Codable, Equatable, Identifiable {
    public var id: String { eventId }

    public let schema: String = "ai-caddie-watch-input-event-v1"
    public let eventId: String
    public let roundId: String
    public let hole: Int
    public let kind: WatchInputKind
    public let value: String
    public let createdAt: String
    public let contextClub: String?
    public let shotType: String?
    public let strategyMode: String?
    public let lie: String?
    public let distanceToPinM: Double?
    public let offlineOptionId: String?
    public let decisionId: String?
    /// Optional Fairway result captured with a score on Par 4/5: HIT, LEFT, or RIGHT.
    public let fairwayResult: String?

    public init(
        eventId: String,
        roundId: String,
        hole: Int,
        kind: WatchInputKind,
        value: String,
        createdAt: String,
        contextClub: String? = nil,
        shotType: String? = nil,
        strategyMode: String? = nil,
        lie: String? = nil,
        distanceToPinM: Double? = nil,
        offlineOptionId: String? = nil,
        decisionId: String? = nil,
        fairwayResult: String? = nil
    ) {
        self.eventId = eventId
        self.roundId = roundId
        self.hole = hole
        self.kind = kind
        self.value = value
        self.createdAt = createdAt
        self.contextClub = contextClub
        self.shotType = shotType
        self.strategyMode = strategyMode
        self.lie = lie
        self.distanceToPinM = distanceToPinM
        self.offlineOptionId = offlineOptionId
        self.decisionId = decisionId
        self.fairwayResult = fairwayResult
    }
}
