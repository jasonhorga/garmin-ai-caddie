import Foundation

/// Why a round left open was set aside.
public enum WatchRoundPauseReason: Equatable {
    case leftCourse
    case stationary
    case finished
}

/// Owner report 2026-10-12: a round left open after play kept the golf workout session and GPS
/// running in the background and drained the watch. A round is set aside (workout and GPS stop;
/// nothing is lost; the next open asks to resume) when the player has clearly stopped playing:
/// - well away from every tee and green of the round, with no input, for a while (drove off);
/// - in one place (or with no wrist fix at all) with no recorded input for a long time;
/// - every hole scored and no input since.
/// Input is a recorded event or a change in the number of scored holes (a score entered on the
/// phone counts too).
/// Fed once a minute with the newest wrist fix while the workout keeps the app alive; once the
/// workout stops the system suspends the app in the background, which stops GPS too.
public struct WatchRoundIdleTracker {
    public static let offCourseMetres: Double = 1_500
    public static let offCourseSeconds: TimeInterval = 10 * 60
    public static let stationaryMetres: Double = 50
    public static let stationarySeconds: TimeInterval = 45 * 60
    public static let finishedIdleSeconds: TimeInterval = 20 * 60
    /// Indoor or cold fixes wander by tens of metres; they must not count as "moved".
    public static let maximumAnchorAccuracyMetres: Double = 25

    private var offCourseSince: Date?
    private var anchorLatitude: Double?
    private var anchorLongitude: Double?
    private var anchorAt: Date?
    /// When tracking (re)started: a resumed round gets the full grace period again, even though
    /// tapping Resume records no input.
    private var trackingSince: Date?
    private var scoredHoles: Int?
    private var scoredHolesChangedAt: Date?

    public init() {}

    public mutating func reset() {
        offCourseSince = nil
        anchorLatitude = nil
        anchorLongitude = nil
        anchorAt = nil
        trackingSince = nil
        scoredHoles = nil
        scoredHolesChangedAt = nil
    }

    public mutating func evaluate(
        latitude: Double?,
        longitude: Double?,
        horizontalAccuracyM: Double = 5,
        at now: Date,
        holePoints: [(latitude: Double, longitude: Double)],
        lastActivityAt: Date?,
        scoredHoles holes: Int = 0,
        allHolesScored: Bool
    ) -> WatchRoundPauseReason? {
        let since = trackingSince ?? now
        trackingSince = since
        if let scoredHoles, scoredHoles != holes { scoredHolesChangedAt = now }
        scoredHoles = holes
        let lastInput = max(lastActivityAt ?? .distantPast, scoredHolesChangedAt ?? .distantPast, since)
        let idle = now.timeIntervalSince(lastInput)

        if let latitude, let longitude {
            if !holePoints.isEmpty {
                let nearest = holePoints
                    .map { WatchGeoMath.metres($0.latitude, $0.longitude, latitude, longitude) }
                    .min() ?? 0
                if nearest > Self.offCourseMetres {
                    let away = offCourseSince ?? now
                    offCourseSince = away
                    // Input means the player is still playing, whatever the course geometry says.
                    if now.timeIntervalSince(away) >= Self.offCourseSeconds, idle >= Self.offCourseSeconds {
                        return .leftCourse
                    }
                } else {
                    offCourseSince = nil
                }
            }

            if let anchorLatitude, let anchorLongitude,
               horizontalAccuracyM > Self.maximumAnchorAccuracyMetres
                || WatchGeoMath.metres(anchorLatitude, anchorLongitude, latitude, longitude) <= Self.stationaryMetres {
                // Still in the same place, or too coarse a fix to say otherwise.
            } else {
                anchorLatitude = latitude
                anchorLongitude = longitude
                anchorAt = now
            }
        }

        if allHolesScored, idle >= Self.finishedIdleSeconds { return .finished }
        // With no fix at all there is no sign of movement: only input keeps the round in play.
        let lastSign = max(anchorAt ?? .distantPast, lastInput)
        if now.timeIntervalSince(lastSign) >= Self.stationarySeconds { return .stationary }
        return nil
    }
}
