import Foundation

/// Shared player-facing naming for measured and legacy course hazards.
///
/// Decoder order is not meaningful to a golfer. When geometry is available, name a hazard by its
/// side of the intended route and whether it protects the fairway or green. Older cached intervals
/// can still distinguish fairway/green from route distance, but must not invent left/right.
public enum HazardDisplayNaming {
    public static func label(
        kind: String,
        frontRouteM: Double,
        frontPx: [Double],
        sideM: Double?,
        route: [[Double]]?
    ) -> String {
        let side = lateralLabel(
            frontRouteM: frontRouteM,
            frontPx: frontPx,
            sideM: sideM,
            route: route
        )
        if kind == "water" {
            return side == "前方" ? "前方水障碍" : "\(side)水障碍"
        }
        let totalM: Double?
        if let last = route?.last, last.count >= 3 {
            totalM = last[2]
        } else {
            totalM = nil
        }
        let area = totalM.map { $0 - frontRouteM <= 55 ? "果岭" : "球道" } ?? ""
        return side == "前方" ? "\(area)沙坑" : "\(side)\(area)沙坑"
    }

    public static func legacyLabel(
        kind: String,
        interval: [Double],
        route: [[Double]]?
    ) -> String {
        guard let front = interval.first else {
            return kind == "water" ? "水障碍" : "沙坑"
        }
        return label(
            kind: kind,
            frontRouteM: front,
            frontPx: [],
            sideM: nil,
            route: route
        )
    }

    private static func lateralLabel(
        frontRouteM: Double,
        frontPx: [Double],
        sideM: Double?,
        route: [[Double]]?
    ) -> String {
        guard let route, route.count >= 2, frontPx.count >= 2 else { return "前方" }
        let segments = zip(route, route.dropFirst()).filter { segment in
            segment.0.count >= 2 && segment.1.count >= 2
        }
        guard !segments.isEmpty else { return "前方" }
        let selected: ([Double], [Double])?
        if let stationSegment = segments.first(where: { segment in
            guard segment.0.count >= 3, segment.1.count >= 3 else { return false }
            let low = min(segment.0[2], segment.1[2]) - 1
            let high = max(segment.0[2], segment.1[2]) + 1
            return low...high ~= frontRouteM
        }) {
            selected = stationSegment
        } else {
            selected = segments.min { lhs, rhs in
                routeSegmentDistanceSquared(point: frontPx, segment: lhs)
                    < routeSegmentDistanceSquared(point: frontPx, segment: rhs)
            }
        }
        guard let selected else { return "前方" }
        let first = selected.0
        let second = selected.1
        let dx = second[0] - first[0]
        let dy = second[1] - first[1]
        let length = hypot(dx, dy)
        guard length > 0 else { return "前方" }
        let cross = dx * (frontPx[1] - first[1]) - dy * (frontPx[0] - first[0])
        let lateralPixels = cross / length
        if abs(lateralPixels) < 7 || (sideM ?? .greatestFiniteMagnitude) < 4 {
            return "前方"
        }
        // UIKit/watchOS image coordinates point down, reversing the Cartesian cross-product sign.
        return lateralPixels < 0 ? "左侧" : "右侧"
    }

    private static func routeSegmentDistanceSquared(
        point: [Double],
        segment: ([Double], [Double])
    ) -> Double {
        let first = segment.0
        let second = segment.1
        let dx = second[0] - first[0]
        let dy = second[1] - first[1]
        let lengthSquared = dx * dx + dy * dy
        guard lengthSquared > 0 else {
            let px = point[0] - first[0]
            let py = point[1] - first[1]
            return px * px + py * py
        }
        let rawT = ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / lengthSquared
        let t = min(1, max(0, rawT))
        let px = point[0] - (first[0] + t * dx)
        let py = point[1] - (first[1] + t * dy)
        return px * px + py * py
    }
}
