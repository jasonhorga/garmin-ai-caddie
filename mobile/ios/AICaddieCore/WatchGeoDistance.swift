import Foundation

public enum WatchGeoDistance {
    /// Great-circle (haversine) distance in metres between two WGS84 points.
    public static func metres(_ lat1: Double, _ lon1: Double, _ lat2: Double, _ lon2: Double) -> Double {
        let earthR = 6_371_000.0
        let dLat = (lat2 - lat1) * .pi / 180
        let dLon = (lon2 - lon1) * .pi / 180
        let h = sin(dLat / 2) * sin(dLat / 2)
            + cos(lat1 * .pi / 180) * cos(lat2 * .pi / 180) * sin(dLon / 2) * sin(dLon / 2)
        return 2 * earthR * atan2(sqrt(h), sqrt(max(0, 1 - h)))
    }
}
