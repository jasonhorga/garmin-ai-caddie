import Foundation

/// The action taken when an open phone round has been quiet for long enough.
public enum PhoneRoundIdleAction: Equatable {
    case none
    case resumed
    case finishLeftCourse
    case finishAfterCompletedRound
    case pauseStationary
    case wrongCourse
}

/// Foreground-only idle policy for an iPhone round. The tracker contains no Core Location or UI
/// dependency so the thresholds can be checked with deterministic fixture times.
public struct PhoneRoundIdleTracker {
    public static let offCourseMetres: Double = 1_500
    public static let offCourseSeconds: TimeInterval = 10 * 60
    public static let stationaryMetres: Double = 50
    public static let stationarySeconds: TimeInterval = 45 * 60
    public static let completedRoundSeconds: TimeInterval = 20 * 60
    public static let maximumAnchorAccuracyMetres: Double = 25

    private var trackingSince: Date?
    private var offCourseSince: Date?
    private var anchorLatitude: Double?
    private var anchorLongitude: Double?
    private var anchorAt: Date?
    private var hasBeenOnCourse = false
    private var hasSeenOffCourse = false

    public init() {}

    public mutating func reset() {
        trackingSince = nil
        offCourseSince = nil
        anchorLatitude = nil
        anchorLongitude = nil
        anchorAt = nil
        hasBeenOnCourse = false
        hasSeenOffCourse = false
    }

    /// Reset the quiet and movement clocks after a score edit while retaining the evidence that
    /// this round has already matched (or mismatched) the selected course.
    public mutating func resetIdleClockPreservingCourse() {
        trackingSince = nil
        offCourseSince = nil
        anchorLatitude = nil
        anchorLongitude = nil
        anchorAt = nil
    }

    public mutating func evaluate(
        latitude: Double?,
        longitude: Double?,
        horizontalAccuracyM: Double = 5,
        at now: Date,
        coursePoints: [(latitude: Double, longitude: Double)],
        lastActivityAt: Date?,
        hasRecordedStroke: Bool,
        allHolesScored: Bool
    ) -> PhoneRoundIdleAction {
        let since = trackingSince ?? now
        trackingSince = since
        let lastInput = max(lastActivityAt ?? .distantPast, since)
        let idle = now.timeIntervalSince(lastInput)

        var nearest: Double?
        if let latitude, let longitude, !coursePoints.isEmpty {
            nearest = coursePoints.map {
                haversineMetres($0.latitude, $0.longitude, latitude, longitude)
            }.min()
            if let nearest, nearest <= Self.offCourseMetres {
                hasBeenOnCourse = true
                hasSeenOffCourse = false
                offCourseSince = nil
            } else if nearest != nil {
                hasSeenOffCourse = true
                offCourseSince = offCourseSince ?? now
            }
        } else {
            // A cached/off-course sample cannot keep the departure clock alive through a GPS gap.
            // Time-only rules below still run, but a fresh fix must establish a new ten-minute
            // departure interval before an automatic finish or wrong-course prompt.
            offCourseSince = nil
        }

        if let latitude, let longitude {
            if let anchorLatitude, let anchorLongitude,
               (horizontalAccuracyM > Self.maximumAnchorAccuracyMetres
                || haversineMetres(anchorLatitude, anchorLongitude, latitude, longitude) <= Self.stationaryMetres) {
                // The fix is stationary or too coarse to establish movement.
            } else {
                self.anchorLatitude = latitude
                self.anchorLongitude = longitude
                anchorAt = now
            }
        }

        // A manually selected wrong course is a prompt only. It must never silently create a
        // saved round from a location that has not once matched the selected course.
        if let offCourseSince,
           now.timeIntervalSince(offCourseSince) >= Self.offCourseSeconds,
           idle >= Self.offCourseSeconds {
            // A round without a stroke is never saved, pushed or prompted (design §4).
            guard hasRecordedStroke else { return .none }
            if hasBeenOnCourse { return hasRecordedStroke ? .finishLeftCourse : .none }
            // A wrong-course selection is only a prompt, but a player who then remains
            // stationary still gets the same 45-minute local pause safeguard. This never
            // seals or uploads the round.
            let lastSign = max(anchorAt ?? .distantPast, lastInput)
            if now.timeIntervalSince(lastSign) >= Self.stationarySeconds {
                return .pauseStationary
            }
            return .wrongCourse
        }

        // Once a live round has observed a location away from the selected course without ever
        // matching it, a later GPS gap must not turn the completed-round timer into an automatic
        // save. The only valid outcome for that round is the visible mismatch prompt.
        if allHolesScored, hasRecordedStroke, !hasSeenOffCourse, idle >= Self.completedRoundSeconds {
            return .finishAfterCompletedRound
        }

        let lastSign = max(anchorAt ?? .distantPast, lastInput)
        if hasRecordedStroke, now.timeIntervalSince(lastSign) >= Self.stationarySeconds {
            return .pauseStationary
        }
        return .none
    }

    private func haversineMetres(_ lat1: Double, _ lon1: Double, _ lat2: Double, _ lon2: Double) -> Double {
        let radius = 6_371_000.0
        let dLat = (lat2 - lat1) * .pi / 180
        let dLon = (lon2 - lon1) * .pi / 180
        let a = sin(dLat / 2) * sin(dLat / 2)
            + cos(lat1 * .pi / 180) * cos(lat2 * .pi / 180) * sin(dLon / 2) * sin(dLon / 2)
        return radius * 2 * atan2(sqrt(a), sqrt(1 - a))
    }
}
