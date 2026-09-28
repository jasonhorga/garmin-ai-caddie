import Foundation

/// Distances from the flag to the four edges of the green (IMPLEMENTATION_PLAN B1 旗位界面).
///
/// Everything is computed in the full-hole topo pixel frame shared by `greenOutline.pointsPx`, the
/// route overlay and the flag, then converted with the overlay's pixels-per-metre:
///
/// * the play axis `u` points from the player (current position, or the tee before a GPS fix) to the
///   green's area centroid; the front edge is the first boundary hit going back along `-u`, the back
///   edge the first hit along `u`;
/// * left / right are the perpendiculars as seen by a player facing the green (image y grows down,
///   so facing `u`, the right-hand direction is `(-u.y, u.x)`);
/// * each distance is the first crossing of the ray from the flag with the outline, so a concave
///   green reports the nearest edge in that direction, not the far lobe.
///
/// A flag on the boundary reports 0 toward that edge. Degenerate input (fewer than three distinct
/// vertices, a non-finite point, a non-positive scale) resolves to `nil`, never a fabricated number.
public struct GreenEdgeDistances: Equatable {
    public struct Edge: Equatable {
        /// Rounded yards from the flag to this edge.
        public let yards: Int
        /// The edge point in topo pixels (the end of the drawn guide line).
        public let pointPx: [Double]
    }

    public let front: Edge
    public let back: Edge
    public let left: Edge
    public let right: Edge
    /// Flag offset from the green centre along the play axis, rounded yards; positive = behind.
    public let behindCentreYards: Int
    /// Flag offset from the green centre across the play axis, rounded yards; positive = right.
    public let rightOfCentreYards: Int
    /// Unit direction vectors (topo pixels) for front / back / left / right, for label placement.
    public let frontDirection: [Double]
    public let rightDirection: [Double]

    static let yardsPerMetre = 1.0936133

    public static func resolve(
        flagPx: [Double],
        outlinePx: [[Double]],
        referencePx: [Double]?,
        pixelsPerMetre: Double
    ) -> GreenEdgeDistances? {
        guard pixelsPerMetre.isFinite, pixelsPerMetre > 0,
              let flag = point(flagPx) else { return nil }
        let polygon = normalized(outlinePx.compactMap(point))
        guard polygon.count >= 3, let centre = centroid(polygon) else { return nil }

        // Play axis: player -> green centre. Without a usable player point (or when the player is
        // standing on the centre) fall back to "up the image", the direction every hole map is drawn.
        var axis = (x: 0.0, y: -1.0)
        if let reference = referencePx.flatMap(point) {
            let dx = centre.x - reference.x
            let dy = centre.y - reference.y
            let length = hypot(dx, dy)
            if length > 1e-6 { axis = (dx / length, dy / length) }
        }
        let right = (x: -axis.y, y: axis.x)
        let directions = [
            (x: -axis.x, y: -axis.y),  // front: back toward the player
            axis,                       // back
            (x: -right.x, y: -right.y), // left
            right,                      // right
        ]
        let edges = directions.map { direction -> Edge in
            let t = rayHit(from: flag, direction: direction, polygon: polygon) ?? 0
            return Edge(
                yards: yards(pixels: t, pixelsPerMetre: pixelsPerMetre),
                pointPx: [flag.x + direction.x * t, flag.y + direction.y * t]
            )
        }
        let dx = flag.x - centre.x
        let dy = flag.y - centre.y
        return GreenEdgeDistances(
            front: edges[0],
            back: edges[1],
            left: edges[2],
            right: edges[3],
            behindCentreYards: signedYards(pixels: dx * axis.x + dy * axis.y, pixelsPerMetre: pixelsPerMetre),
            rightOfCentreYards: signedYards(pixels: dx * right.x + dy * right.y, pixelsPerMetre: pixelsPerMetre),
            frontDirection: [directions[0].x, directions[0].y],
            rightDirection: [right.x, right.y]
        )
    }

    /// Distance (pixels) from `origin` along `direction` to the green edge: the first crossing with
    /// `t > 0` whose leading half lies on the green. A flag on the boundary heading outward (no such
    /// crossing, or the first segment runs outside the green) is 0 from that edge.
    static func rayHit(
        from origin: (x: Double, y: Double),
        direction: (x: Double, y: Double),
        polygon: [(x: Double, y: Double)]
    ) -> Double? {
        var hits: [Double] = []
        for index in polygon.indices {
            let a = polygon[index]
            let b = polygon[(index + 1) % polygon.count]
            let ex = b.x - a.x
            let ey = b.y - a.y
            let denominator = direction.x * ey - direction.y * ex
            guard abs(denominator) > 1e-12 else { continue }
            let wx = a.x - origin.x
            let wy = a.y - origin.y
            let t = (wx * ey - wy * ex) / denominator
            let s = (wx * direction.y - wy * direction.x) / denominator
            guard t >= -1e-9, s >= -1e-9, s <= 1 + 1e-9 else { continue }
            hits.append(max(t, 0))
        }
        guard !hits.isEmpty else { return nil }
        guard let first = hits.filter({ $0 > 1e-6 }).min() else { return 0 }
        let mid = (x: origin.x + direction.x * first / 2, y: origin.y + direction.y * first / 2)
        return contains(mid, polygon: polygon) ? first : 0
    }

    /// Even-odd point in polygon.
    static func contains(_ point: (x: Double, y: Double), polygon: [(x: Double, y: Double)]) -> Bool {
        var inside = false
        var previous = polygon.count - 1
        for current in polygon.indices {
            let a = polygon[current]
            let b = polygon[previous]
            if (a.y > point.y) != (b.y > point.y) {
                let x = (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x
                if point.x < x { inside.toggle() }
            }
            previous = current
        }
        return inside
    }

    /// Area centroid (falls back to the vertex mean for a zero-area outline).
    static func centroid(_ polygon: [(x: Double, y: Double)]) -> (x: Double, y: Double)? {
        var area = 0.0
        var cx = 0.0
        var cy = 0.0
        for index in polygon.indices {
            let a = polygon[index]
            let b = polygon[(index + 1) % polygon.count]
            let cross = a.x * b.y - b.x * a.y
            area += cross
            cx += (a.x + b.x) * cross
            cy += (a.y + b.y) * cross
        }
        if abs(area) > 1e-9 {
            return (cx / (3 * area), cy / (3 * area))
        }
        guard !polygon.isEmpty else { return nil }
        let count = Double(polygon.count)
        return (polygon.map(\.x).reduce(0, +) / count, polygon.map(\.y).reduce(0, +) / count)
    }

    private static func point(_ row: [Double]) -> (x: Double, y: Double)? {
        guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
        return (row[0], row[1])
    }

    private static func normalized(_ points: [(x: Double, y: Double)]) -> [(x: Double, y: Double)] {
        var result: [(x: Double, y: Double)] = []
        for point in points {
            if let last = result.last, hypot(last.x - point.x, last.y - point.y) <= 1e-4 { continue }
            result.append(point)
        }
        if result.count > 1, let first = result.first, let last = result.last,
           hypot(first.x - last.x, first.y - last.y) <= 1e-4 {
            result.removeLast()
        }
        return result
    }

    private static func yards(pixels: Double, pixelsPerMetre: Double) -> Int {
        max(0, Int((pixels / pixelsPerMetre * yardsPerMetre).rounded()))
    }

    private static func signedYards(pixels: Double, pixelsPerMetre: Double) -> Int {
        Int((pixels / pixelsPerMetre * yardsPerMetre).rounded())
    }
}
