import CoreGraphics
import Foundation

/// watch P3: on-device geo math so the watch computes its OWN you-pixel + green distances from its GPS,
/// mirroring the phone's `WatchEventBridge.projectToTopoPx` + `GeoDistance`. Pure functions — unit-tested,
/// no CoreLocation dependency (takes plain lat/lon). This is what lets the watch update distances from its
/// own fix (less phone-dependence in companion mode; the base for standalone play once all holes are cached).
public enum WatchGeoMath {
    /// Keep the wrist rangefinder to a useful three-digit golf range. The raw geodesic result is
    /// retained for math; only presentation suppresses an off-course or stale-hole four/five-digit
    /// value that cannot fit the S70-style F/M/B instrument.
    public static let maximumUsefulGreenYards = 999

    /// Project a WGS84 point onto /topo.png pixel space via the 3 affine reference points (relative to
    /// ref[0], a 2×2 solve — well-conditioned over a hole). nil if the refs are degenerate/collinear.
    public static func projectToTopoPx(lat: Double, lon: Double, refs: [WatchProjectionRef]) -> CGPoint? {
        guard refs.count >= 3 else { return nil }
        let o = refs[0], r1 = refs[1], r2 = refs[2]
        let a = r1.lon - o.lon, b = r2.lon - o.lon
        let c = r1.lat - o.lat, d = r2.lat - o.lat
        let det = a * d - b * c
        guard abs(det) > 1e-12 else { return nil }
        let dlon = lon - o.lon, dlat = lat - o.lat
        let s = (dlon * d - b * dlat) / det
        let t = (a * dlat - dlon * c) / det
        return CGPoint(x: o.px + s * (r1.px - o.px) + t * (r2.px - o.px),
                       y: o.py + s * (r1.py - o.py) + t * (r2.py - o.py))
    }

    /// Haversine great-circle distance in metres between two WGS84 points.
    public static func metres(_ lat1: Double, _ lon1: Double, _ lat2: Double, _ lon2: Double) -> Double {
        let earthR = 6_371_000.0
        let dLat = (lat2 - lat1) * .pi / 180
        let dLon = (lon2 - lon1) * .pi / 180
        let h = sin(dLat / 2) * sin(dLat / 2)
            + cos(lat1 * .pi / 180) * cos(lat2 * .pi / 180) * sin(dLon / 2) * sin(dLon / 2)
        return 2 * earthR * atan2(sqrt(h), sqrt(max(0, 1 - h)))
    }

    public static func yards(_ metres: Double) -> Int { Int((metres * 1.09361).rounded()) }

    /// Distance in 码 from a fix to an optional green coordinate; nil if the coordinate is missing.
    public static func yards(from lat: Double, _ lon: Double, toLat: Double?, _ toLon: Double?) -> Int? {
        guard let toLat, let toLon else { return nil }
        return yards(metres(lat, lon, toLat, toLon))
    }

    public static func greenRangeText(_ yards: Int?) -> String {
        guard let yards, (0...maximumUsefulGreenYards).contains(yards) else { return "—" }
        return String(yards)
    }

    /// A useful golf distance is one the compact wrist UI can display truthfully as a three-digit
    /// measurement. Keep bad/stale GPS math available to state transitions, but never let it leak
    /// into another distance surface such as last-shot, hazards, or PinPointer.
    public static func usefulGolfYards(_ yards: Int?) -> Int? {
        guard let yards, (0...maximumUsefulGreenYards).contains(yards) else { return nil }
        return yards
    }

    public static func isBeyondUsefulGreenRange(_ yards: Int?) -> Bool {
        guard let yards else { return false }
        return yards < 0 || yards > maximumUsefulGreenYards
    }

    /// Initial great-circle bearing in degrees clockwise from true north. A same-point target has no
    /// meaningful direction and therefore returns nil instead of manufacturing a north arrow.
    public static func initialBearingDegrees(
        from latitude: Double,
        _ longitude: Double,
        to targetLatitude: Double,
        _ targetLongitude: Double
    ) -> Double? {
        guard valid(latitude: latitude, longitude: longitude),
              valid(latitude: targetLatitude, longitude: targetLongitude),
              metres(latitude, longitude, targetLatitude, targetLongitude) >= 0.5 else {
            return nil
        }
        let lat1 = latitude * .pi / 180
        let lat2 = targetLatitude * .pi / 180
        let deltaLongitude = (targetLongitude - longitude) * .pi / 180
        let y = sin(deltaLongitude) * cos(lat2)
        let x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(deltaLongitude)
        let degrees = atan2(y, x) * 180 / .pi
        guard degrees.isFinite else { return nil }
        return (degrees + 360).truncatingRemainder(dividingBy: 360)
    }

    private static func valid(latitude: Double, longitude: Double) -> Bool {
        latitude.isFinite && longitude.isFinite
            && (-90...90).contains(latitude)
            && (-180...180).contains(longitude)
    }
}

/// Presentation math for the Watch start screen. It ranks only the real course coordinates already
/// present in the mobile options payload; missing or invalid coordinates remain selectable but never
/// receive a fabricated distance.
public enum WatchCourseProximity {
    private static let nearbyRadiusM = 50_000.0

    public static func distanceM(
        to course: WatchCourseOption,
        fromLatitude latitude: Double,
        longitude: Double
    ) -> Double? {
        guard isValid(latitude: latitude, longitude: longitude),
              let courseLatitude = course.latitude,
              let courseLongitude = course.longitude,
              isValid(latitude: courseLatitude, longitude: courseLongitude) else {
            return nil
        }
        return WatchGeoMath.metres(latitude, longitude, courseLatitude, courseLongitude)
    }

    public static func ranked(
        _ courses: [WatchCourseOption],
        fromLatitude latitude: Double,
        longitude: Double
    ) -> [WatchCourseOption] {
        courses.enumerated().sorted { left, right in
            let leftDistance = distanceM(
                to: left.element,
                fromLatitude: latitude,
                longitude: longitude
            )
            let rightDistance = distanceM(
                to: right.element,
                fromLatitude: latitude,
                longitude: longitude
            )
            switch (leftDistance, rightDistance) {
            case let (lhs?, rhs?) where lhs != rhs:
                return lhs < rhs
            case (_?, nil):
                return true
            case (nil, _?):
                return false
            default:
                return left.offset < right.offset
            }
        }.map(\.element)
    }

    public static func distanceLabel(_ metres: Double) -> String? {
        guard metres.isFinite, metres >= 0 else { return nil }
        let tenthsOfAKilometre = Int((metres / 100).rounded())
        return "\(tenthsOfAKilometre / 10).\(tenthsOfAKilometre % 10) km"
    }

    public static func isNearby(distanceM: Double) -> Bool {
        distanceM.isFinite && distanceM >= 0 && distanceM <= nearbyRadiusM
    }

    private static func isValid(latitude: Double, longitude: Double) -> Bool {
        latitude.isFinite && longitude.isFinite
            && (-90...90).contains(latitude)
            && (-180...180).contains(longitude)
    }
}
