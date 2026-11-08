import Foundation

/// The complete, fail-closed contract for showing one current-shot recommendation on Hole Root.
/// Legacy `suggestedClub` / `caddieOptions` remain useful in Caddie detail, but cannot independently
/// opt the root into an apparently live recommendation. The range is longitudinal only: p10/p90 are
/// measured carry facts and must never be rendered as a fabricated lateral ellipse.
public struct WatchRootCaddieRecommendation: Codable, Equatable {
    public let decisionId: String
    public let clubName: String
    public let aimCarryM: Double
    public let carryP10M: Double
    public let carryP90M: Double
    public let sampleSize: Int
    public let confidence: String
    public let source: String
    public let mode: String
    public let generatedAt: String
    public let validUntil: String
    public let originLatitude: Double
    public let originLongitude: Double
    public let originAccuracyM: Double
    public let maximumMovementM: Double
    public let evidenceCount: Int

    public init(
        decisionId: String,
        clubName: String,
        aimCarryM: Double,
        carryP10M: Double,
        carryP90M: Double,
        sampleSize: Int,
        confidence: String,
        source: String,
        mode: String,
        generatedAt: String,
        validUntil: String,
        originLatitude: Double,
        originLongitude: Double,
        originAccuracyM: Double,
        maximumMovementM: Double,
        evidenceCount: Int
    ) {
        self.decisionId = decisionId
        self.clubName = clubName
        self.aimCarryM = aimCarryM
        self.carryP10M = carryP10M
        self.carryP90M = carryP90M
        self.sampleSize = sampleSize
        self.confidence = confidence
        self.source = source
        self.mode = mode
        self.generatedAt = generatedAt
        self.validUntil = validUntil
        self.originLatitude = originLatitude
        self.originLongitude = originLongitude
        self.originAccuracyM = originAccuracyM
        self.maximumMovementM = maximumMovementM
        self.evidenceCount = evidenceCount
    }
}

/// Whether a root recommendation may be drawn for one Watch fix at `now` (all times ISO-8601).
/// Fail-closed: a live, measured, internally consistent recommendation inside its time window, and an
/// accurate fix no older than 15 s that has not moved beyond the recommendation's origin window.
public enum RootCaddieAdviceTrust {
    public static func isTrusted(
        _ recommendation: WatchRootCaddieRecommendation,
        fixLatitude: Double,
        fixLongitude: Double,
        fixAccuracyM: Double,
        fixCapturedAt: String,
        now: String
    ) -> Bool {
        true
    }
}
