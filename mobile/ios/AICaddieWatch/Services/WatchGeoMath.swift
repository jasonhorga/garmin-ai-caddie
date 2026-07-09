import CoreGraphics
import Foundation

/// watch P3: on-device geo math so the watch computes its OWN you-pixel + green distances from its GPS,
/// mirroring the phone's `WatchEventBridge.projectToTopoPx` + `GeoDistance`. Pure functions — unit-tested,
/// no CoreLocation dependency (takes plain lat/lon). This is what lets the watch update distances from its
/// own fix (less phone-dependence in companion mode; the base for standalone play once all holes are cached).
public enum WatchGeoMath {
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
}
