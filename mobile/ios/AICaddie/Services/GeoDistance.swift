import CoreLocation
import Foundation

/// Great-circle distance helpers shared across the app.
///
/// Extracted (round-13 B1) so the LIVE GPS rangefinder on the hole screen (CurrentHoleView) and any
/// other caller can compute distance to a known coordinate from the current CoreLocation fix WITHOUT
/// a backend round-trip — it works offline on the course. The phone gets the green Front/Middle/Back
/// as WGS84 lat/lon on the per-hole prep (CoursePrepGreenDistances) and ranges to them locally as the
/// fix updates.
///
/// NOTE: `StartRoundView` still carries its own identical private `haversineMetres` to avoid churning
/// a file with a parallel in-flight change; collapsing that onto this helper is a trivial follow-up.
enum GeoDistance {
    /// Metres between two WGS84 coordinates (haversine, mean Earth radius 6 371 000 m).
    static func haversineMetres(_ lat1: Double, _ lon1: Double, _ lat2: Double, _ lon2: Double) -> Double {
        let r = 6_371_000.0
        let dLat = (lat2 - lat1) * .pi / 180
        let dLon = (lon2 - lon1) * .pi / 180
        let a = sin(dLat / 2) * sin(dLat / 2)
            + cos(lat1 * .pi / 180) * cos(lat2 * .pi / 180) * sin(dLon / 2) * sin(dLon / 2)
        return r * 2 * atan2(sqrt(a), sqrt(1 - a))
    }

    /// Whole yards between two WGS84 coordinates, or nil when either coordinate is missing.
    /// Reuses the project's 1 m = 1.09361 yd converter so display stays consistent with the backend.
    static func yards(from lat1: Double, _ lon1: Double, to lat2: Double?, _ lon2: Double?) -> Int? {
        guard let lat2, let lon2 else { return nil }
        let metres = haversineMetres(lat1, lon1, lat2, lon2)
        return Int((metres * 1.09361).rounded())
    }
}
