import Foundation
import CoreGraphics

/// A geographic point returned by the per-hole history endpoint.
public struct HoleHistoryCoordinate: Codable, Equatable {
    public let lat: Double
    public let lon: Double

    public init(lat: Double, lon: Double) {
        self.lat = lat
        self.lon = lon
    }
}

/// One corrected shot from the player's own rounds in the last two years.
public struct HoleHistoryShot: Codable, Equatable, Identifiable {
    public let id: String
    public let roundRef: String
    public let date: String
    public let roundHole: Int
    public let order: Int
    public let isTee: Bool
    public let start: HoleHistoryCoordinate?
    public let end: HoleHistoryCoordinate?
    public let distanceM: Double?
    public let startLie: String?
    public let endLie: String?
    public let result: String
    public let teeFairway: String?
    public let shotType: String?
}

public struct HoleHistoryGreen: Codable, Equatable {
    public let available: Bool
    public let lat: Double?
    public let lon: Double?
    public let source: String?

    public init(available: Bool, lat: Double?, lon: Double?, source: String?) {
        self.available = available
        self.lat = lat
        self.lon = lon
        self.source = source
    }
}

public struct HoleHistoryShotsResponse: Codable, Equatable {
    public let schema: String
    public let globalId: Int
    public let localHole: Int
    public let days: Int
    public let since: String
    public let roundCount: Int
    public let shots: [HoleHistoryShot]
    public let green: HoleHistoryGreen
    public let missingData: [[String: String]]

    public init(
        schema: String = "ai-caddie-hole-history-shots-v1",
        globalId: Int,
        localHole: Int,
        days: Int = 730,
        since: String = "",
        roundCount: Int = 0,
        shots: [HoleHistoryShot] = [],
        green: HoleHistoryGreen = HoleHistoryGreen(available: false, lat: nil, lon: nil, source: nil),
        missingData: [[String: String]] = []
    ) {
        self.schema = schema
        self.globalId = globalId
        self.localHole = localHole
        self.days = days
        self.since = since
        self.roundCount = roundCount
        self.shots = shots
        self.green = green
        self.missingData = missingData
    }
}

/// Pure geometry used by the phone history layer. The map supplies pixels-per-metre from its
/// authoritative overlay, so a dragged player marker works even when the GPS projection is absent.
public enum HoleHistoryOverlayRenderer {
    public struct ProjectedShot: Equatable, Identifiable {
        public let id: String
        public let start: CGPoint?
        public let end: CGPoint?
        public let distanceM: Double?
        public let isTee: Bool
        public let result: String

        public init(id: String, start: CGPoint?, end: CGPoint?, distanceM: Double?, isTee: Bool, result: String) {
            self.id = id
            self.start = start
            self.end = end
            self.distanceM = distanceM
            self.isTee = isTee
            self.result = result
        }
    }

    /// Select shots whose starting point is within the requested radius of the player's marker.
    /// Tee shots are always retained so the tee landing colour remains visible in the history view.
    public static func nearby(
        _ shots: [ProjectedShot],
        player: CGPoint?,
        radiusMetres: Double = 25,
        pixelsPerMetre: Double
    ) -> [ProjectedShot] {
        guard let player, pixelsPerMetre.isFinite, pixelsPerMetre > 0 else {
            return shots.filter(\.isTee)
        }
        let radius = max(radiusMetres, 0) * pixelsPerMetre
        return shots.filter { shot in
            shot.isTee
                || shot.start.map { hypot($0.x - player.x, $0.y - player.y) <= radius } == true
                || (shot.start == nil && shot.end == nil && shot.distanceM != nil)
        }
    }

    public static func summary(_ shots: [ProjectedShot], pixelsPerMetre: Double) -> (count: Int, averageYards: Int?) {
        let distances = shots.compactMap { shot -> Double? in
            if let distanceM = shot.distanceM, distanceM.isFinite, distanceM >= 0 { return distanceM }
            guard let start = shot.start, let end = shot.end,
                  pixelsPerMetre.isFinite, pixelsPerMetre > 0 else { return nil }
            return Double(hypot(end.x - start.x, end.y - start.y)) / pixelsPerMetre
        }
        let average = distances.isEmpty ? nil : Int((distances.reduce(0, +) / Double(distances.count) * 1.0936133).rounded())
        return (shots.count, average)
    }

    static func summaryText(_ shots: [ProjectedShot], pixelsPerMetre: Double) -> String? {
        nil
    }

    /// Retain geographic placement when the source pixel frame changes; pixel-only maps use
    /// the same route-station transfer as the target and flag.
    static func carryPlayer(_ pixel: CGPoint, from previous: CoursePrepHole, to next: CoursePrepHole) -> CGPoint? {
        if let source = previous.holeImageProjection, let destination = next.holeImageProjection,
           let mapped = GarminRasterProjectionMath.remap(pixel: pixel, from: source, to: destination) {
            return mapped
        }
        guard let oldOverlay = previous.resolvedMapOverlay,
              let newOverlay = next.resolvedMapOverlay else { return nil }
        return LiveMapCarryOver.transfer(pixel, from: oldOverlay, to: newOverlay)
    }

    static func distanceOnlyText(_ shots: [ProjectedShot]) -> String? {
        let values = shots.compactMap { shot -> Int? in
            guard shot.end == nil, let distance = shot.distanceM,
                  distance.isFinite, distance >= 0 else { return nil }
            return Int((distance * 1.0936133).rounded())
        }
        guard !values.isEmpty else { return nil }
        return "历史距离 " + values.prefix(5).map { "\($0)码" }.joined(separator: " · ")
    }

    static func unmappedDistanceText(_ shots: [HoleHistoryShot]) -> String? {
        distanceOnlyText(shots.map {
            ProjectedShot(id: $0.id, start: nil, end: nil, distanceM: $0.distanceM, isTee: $0.isTee, result: $0.result)
        })
    }

}
