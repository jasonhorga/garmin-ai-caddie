import Foundation

/// `HolePrep.fairwayOutline` version 1 (IMPLEMENTATION_PLAN B0).
///
/// `*Px` rings are in the same display frame as `greenOutline.pointsPx`; `*LatLon` rings are
/// `[lat, lon]` WGS84 degrees. Rings are not closed and have at least three points. Winding is
/// normalised by the server (RFC 7946) but consumers must not rely on it. A missing key, `null`,
/// or a malformed value all decode to "no outline" at the call site (`try?`), never a failed hole.
public struct FairwayOutline: Codable, Equatable {
    public let version: Int
    public let source: String?
    public let polygons: [FairwayPolygon]

    public init(version: Int, source: String? = nil, polygons: [FairwayPolygon]) {
        self.version = version
        self.source = source
        self.polygons = polygons
    }
}

public struct FairwayPolygon: Codable, Equatable {
    public let outerPx: [[Double]]
    public let holesPx: [[[Double]]]
    public let outerLatLon: [[Double]]
    public let holesLatLon: [[[Double]]]

    public init(
        outerPx: [[Double]] = [],
        holesPx: [[[Double]]] = [],
        outerLatLon: [[Double]],
        holesLatLon: [[[Double]]] = []
    ) {
        self.outerPx = outerPx
        self.holesPx = holesPx
        self.outerLatLon = outerLatLon
        self.holesLatLon = holesLatLon
    }

    private enum CodingKeys: String, CodingKey {
        case outerPx, holesPx, outerLatLon, holesLatLon
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        outerPx = try container.decodeIfPresent([[Double]].self, forKey: .outerPx) ?? []
        holesPx = try container.decodeIfPresent([[[Double]]].self, forKey: .holesPx) ?? []
        outerLatLon = try container.decodeIfPresent([[Double]].self, forKey: .outerLatLon) ?? []
        holesLatLon = try container.decodeIfPresent([[[Double]]].self, forKey: .holesLatLon) ?? []
    }
}

public enum TeeResult: String, Codable, Equatable {
    case hit
    case left
    case right
}

/// Swift port of `ai_caddie/courses/tee_result.py`. Both implementations read the shared vectors
/// in `tests/fixtures/tee_result_vectors.json` (copied into this target's test fixtures), so any
/// behaviour change must update the vectors and both ports together.
///
/// Returns `nil` ("do not preselect") for par 3, no outline, an unknown outline version, no
/// position, or a point outside the fairway that cannot be sided (no usable route, or exactly on
/// the route line). A point inside the fairway is `.hit` even without a route.
public enum TeeResultClassifier {
    public static let supportedVersion = 1
    /// Same WGS84 equatorial radius as the server's `shot_projection` (Garmin's mesh frame).
    public static let earthRadiusM = 6_378_137.0
    /// A ball this close to the fairway edge counts as in the fairway.
    public static let edgeToleranceM = 0.5

    private struct Point {
        let x: Double
        let y: Double
    }

    public static func classify(
        point: [Double]?,
        outline: FairwayOutline?,
        route: [[Double]],
        par: Int
    ) -> TeeResult? {
        if par == 3 { return nil }
        guard let position = latLon(point),
              let outline, outline.version == supportedVersion else { return nil }

        let polygons: [(outer: [(Double, Double)], holes: [[(Double, Double)]])] = outline.polygons.compactMap { polygon in
            let outer = ring(polygon.outerLatLon)
            guard !outer.isEmpty else { return nil }
            let holes = polygon.holesLatLon.map(ring).filter { !$0.isEmpty }
            return (outer, holes)
        }
        guard !polygons.isEmpty else { return nil }

        // Origin = mean of every outer-ring vertex, so the flat projection error stays tiny.
        let outerVertices = polygons.flatMap { $0.outer }
        let count = Double(outerVertices.count)
        let lat0 = outerVertices.reduce(0.0) { $0 + $1.0 } / count
        let lon0 = outerVertices.reduce(0.0) { $0 + $1.1 } / count
        let cosLat0 = cos(lat0 * .pi / 180)
        func project(_ value: (Double, Double)) -> Point {
            Point(
                x: (value.1 - lon0) * .pi / 180 * earthRadiusM * cosLat0,
                y: (value.0 - lat0) * .pi / 180 * earthRadiusM
            )
        }

        let p = project(position)
        for polygon in polygons {
            let outer = polygon.outer.map(project)
            let holes = polygon.holes.map { $0.map(project) }
            let inPolygon = inside(p, outer) && !holes.contains { inside(p, $0) }
            let nearEdge = ([outer] + holes).map { ringDistance(p, $0) }.min() ?? .infinity
            if inPolygon || nearEdge <= edgeToleranceM {
                return .hit
            }
        }

        // The route is only needed to tell left from right; "hit" above never depends on it.
        let routeM = route.compactMap { latLon($0) }.map(project)
        guard routeM.count >= 2 else { return nil }
        var bestIndex = 0
        var bestDistance = Double.infinity
        for index in 0..<(routeM.count - 1) {
            let distance = segmentDistance(p, routeM[index], routeM[index + 1])
            if distance < bestDistance {
                bestDistance = distance
                bestIndex = index
            }
        }
        let start = routeM[bestIndex]
        let end = routeM[bestIndex + 1]
        // x east / y north: a positive cross product is to the left of the direction of play.
        let cross = (end.x - start.x) * (p.y - start.y) - (end.y - start.y) * (p.x - start.x)
        if cross > 0 { return .left }
        if cross < 0 { return .right }
        return nil
    }

    private static func latLon(_ value: [Double]?) -> (Double, Double)? {
        guard let value, value.count >= 2, value[0].isFinite, value[1].isFinite else { return nil }
        return (value[0], value[1])
    }

    private static func ring(_ values: [[Double]]) -> [(Double, Double)] {
        let points = values.compactMap { latLon($0) }
        return points.count >= 3 ? points : []
    }

    /// Even/odd ray cast; winding direction does not matter.
    private static func inside(_ point: Point, _ ring: [Point]) -> Bool {
        var result = false
        var previous = ring.count - 1
        for index in 0..<ring.count {
            let a = ring[index]
            let b = ring[previous]
            if (a.y > point.y) != (b.y > point.y),
               point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x {
                result.toggle()
            }
            previous = index
        }
        return result
    }

    private static func segmentDistance(_ point: Point, _ start: Point, _ end: Point) -> Double {
        let dx = end.x - start.x
        let dy = end.y - start.y
        let lengthSquared = dx * dx + dy * dy
        if lengthSquared <= 0 {
            return hypot(point.x - start.x, point.y - start.y)
        }
        let t = max(0, min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared))
        return hypot(point.x - (start.x + t * dx), point.y - (start.y + t * dy))
    }

    private static func ringDistance(_ point: Point, _ ring: [Point]) -> Double {
        var best = Double.infinity
        for index in 0..<ring.count {
            best = min(best, segmentDistance(point, ring[index], ring[(index + 1) % ring.count]))
        }
        return best
    }
}
