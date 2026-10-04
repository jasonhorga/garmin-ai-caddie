import Foundation

/// One hole of a photographed daily hole-location sheet (洞位图), as printed. Three tiers, best first:
/// the numbers ("40,6R" = 40 yd from the green's front-most point along the approach, 6 yd in from
/// the right edge at that depth; "22C" = on the centre line), the drawn flag dot as fractions of the
/// drawn green, or only a front / middle / back zone.
public struct PinSheetHole: Codable, Equatable, Sendable {
    /// The printed loop label of a per-loop sheet ("A" for A1…A9); nil when numbered straight through.
    public let loop: String?
    public let hole: Int
    public let fromFrontYd: Int?
    public let side: String?
    public let fromSideYd: Int?
    public let depthYd: Int?
    public let dotU: Double?
    public let dotV: Double?
    public let zone: String?

    public init(
        loop: String? = nil,
        hole: Int,
        fromFrontYd: Int? = nil,
        side: String? = nil,
        fromSideYd: Int? = nil,
        depthYd: Int? = nil,
        dotU: Double? = nil,
        dotV: Double? = nil,
        zone: String? = nil
    ) {
        self.loop = loop
        self.hole = hole
        self.fromFrontYd = fromFrontYd
        self.side = side
        self.fromSideYd = fromSideYd
        self.depthYd = depthYd
        self.dotU = dotU
        self.dotV = dotV
        self.zone = zone
    }
}

/// Places a sheet's flag on the app's own green outline, in the topo pixel frame.
///
/// It is the inverse of `GreenEdgeDistances` and uses the same play axis (reference → green area
/// centroid), so the 前/后/左/右 readout of the placed flag reproduces the sheet's numbers:
///
/// * depth is measured from the green's front-most point along the axis (the sheet's convention:
///   on a diagonal green the depth line starts beside the green);
/// * the side distance is measured straight across at that depth, to that side's edge of the green
///   part the flag stands on — on a kidney green "6L" is 6 yd from the notch, so the drawn dot
///   (when read) picks which part; without it L takes the left-most part and R the right-most;
/// * C is the middle of that part.
public enum PinSheetPlacement {
    static let yardsPerMetre = 1.0936133

    /// The sheet's "front" faces the approach, not the Tee: on a dogleg they differ. The reference
    /// is the route point `backoffMetres` before its end (the green), or the route start on a
    /// shorter route.
    public static func approachReferencePx(
        route: [[Double]],
        pixelsPerMetre: Double,
        backoffMetres: Double = 90
    ) -> [Double]? {
        let points = route.compactMap { row -> (x: Double, y: Double)? in
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            return (row[0], row[1])
        }
        guard points.count >= 2, pixelsPerMetre.isFinite, pixelsPerMetre > 0 else { return nil }
        var remaining = backoffMetres * pixelsPerMetre
        var index = points.count - 1
        while index > 0 {
            let a = points[index]
            let b = points[index - 1]
            let length = hypot(b.x - a.x, b.y - a.y)
            if length >= remaining, length > 0 {
                let t = remaining / length
                return [a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t]
            }
            remaining -= length
            index -= 1
        }
        return [points[0].x, points[0].y]
    }

    /// The flag in topo pixels, or nil when the outline or scale is unusable.
    public static func flagPx(
        for sheet: PinSheetHole,
        outlinePx: [[Double]],
        referencePx: [Double]?,
        pixelsPerMetre: Double
    ) -> [Double]? {
        guard pixelsPerMetre.isFinite, pixelsPerMetre > 0 else { return nil }
        let polygon = outlinePx.compactMap { row -> (x: Double, y: Double)? in
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            return (row[0], row[1])
        }
        guard polygon.count >= 3, let centre = GreenEdgeDistances.centroid(polygon) else { return nil }
        var axis = (x: 0.0, y: -1.0)
        if let reference = referencePx, reference.count >= 2, reference[0].isFinite, reference[1].isFinite {
            let dx = centre.x - reference[0]
            let dy = centre.y - reference[1]
            let length = hypot(dx, dy)
            if length > 1e-6 { axis = (dx / length, dy / length) }
        }
        let right = (x: -axis.y, y: axis.x)
        let along = polygon.map { ($0.x - centre.x) * axis.x + ($0.y - centre.y) * axis.y }
        guard let frontS = along.min(), let backS = along.max(), backS - frontS > 1e-6 else { return nil }
        let pixelsPerYard = pixelsPerMetre / yardsPerMetre
        let inset = min(0.5 * pixelsPerYard, (backS - frontS) / 4)

        func point(_ s: Double, _ l: Double) -> [Double] {
            [centre.x + axis.x * s + right.x * l, centre.y + axis.y * s + right.y * l]
        }
        func clampDepth(_ s: Double) -> Double { min(max(s, frontS + inset), backS - inset) }
        /// The green's parts across the axis at depth `s`, left to right, as lateral intervals.
        func intervals(at s: Double) -> [(lo: Double, hi: Double)] {
            var crossings: [Double] = []
            for index in polygon.indices {
                let a = polygon[index]
                let b = polygon[(index + 1) % polygon.count]
                let sa = (a.x - centre.x) * axis.x + (a.y - centre.y) * axis.y
                let sb = (b.x - centre.x) * axis.x + (b.y - centre.y) * axis.y
                // Half-open rule: a vertex exactly on the line is counted once.
                guard (sa <= s && s < sb) || (sb <= s && s < sa) else { continue }
                let t = (s - sa) / (sb - sa)
                let x = a.x + (b.x - a.x) * t
                let y = a.y + (b.y - a.y) * t
                crossings.append((x - centre.x) * right.x + (y - centre.y) * right.y)
            }
            crossings.sort()
            var result: [(lo: Double, hi: Double)] = []
            var index = 0
            while index + 1 < crossings.count {
                result.append((crossings[index], crossings[index + 1]))
                index += 2
            }
            return result
        }
        func dotLateral(_ parts: [(lo: Double, hi: Double)], _ fraction: Double) -> Double? {
            guard let first = parts.first, let last = parts.last else { return nil }
            return first.lo + (last.hi - first.lo) * fraction
        }
        func nearestPart(_ parts: [(lo: Double, hi: Double)], to l: Double) -> (lo: Double, hi: Double)? {
            parts.min { distance(l, $0) < distance(l, $1) }
        }
        func distance(_ l: Double, _ part: (lo: Double, hi: Double)) -> Double {
            l < part.lo ? part.lo - l : (l > part.hi ? l - part.hi : 0)
        }
        func clamp(_ l: Double, _ part: (lo: Double, hi: Double)) -> Double {
            let margin = min(0.5 * pixelsPerYard, (part.hi - part.lo) / 2)
            return min(max(l, part.lo + margin), part.hi - margin)
        }

        // 1. The printed numbers.
        if let fromFront = sheet.fromFrontYd, let side = sheet.side?.uppercased() {
            let s = clampDepth(frontS + Double(fromFront) * pixelsPerYard)
            let parts = intervals(at: s)
            guard !parts.isEmpty else { return nil }
            let hint = sheet.dotV.flatMap { dotLateral(parts, $0) }
            let sideDistance = Double(sheet.fromSideYd ?? 0) * pixelsPerYard
            let candidates: [(l: Double, part: (lo: Double, hi: Double))] = parts.map { part in
                switch side {
                case "L": return (l: part.lo + sideDistance, part: part)
                case "R": return (l: part.hi - sideDistance, part: part)
                default: return (l: (part.lo + part.hi) / 2, part: part)
                }
            }
            let fitting = candidates.filter { $0.l >= $0.part.lo - 1e-6 && $0.l <= $0.part.hi + 1e-6 }
            let pool = fitting.isEmpty ? candidates : fitting
            let chosen: (l: Double, part: (lo: Double, hi: Double))
            if let hint {
                chosen = pool.min { abs($0.l - hint) < abs($1.l - hint) }!
            } else {
                switch side {
                case "L": chosen = pool.first!
                case "R": chosen = pool.last!
                default: chosen = pool.max { ($0.part.hi - $0.part.lo) < ($1.part.hi - $1.part.lo) }!
                }
            }
            return point(s, clamp(chosen.l, chosen.part))
        }
        // 2. The drawn dot, in proportion to our green.
        if let u = sheet.dotU, let v = sheet.dotV {
            let s = clampDepth(frontS + (backS - frontS) * u)
            let parts = intervals(at: s)
            guard let l = dotLateral(parts, v), let part = nearestPart(parts, to: l) else { return nil }
            return point(s, clamp(l, part))
        }
        // 3. A zone: the middle of that third, on the widest part.
        let fraction: Double
        switch sheet.zone?.lowercased() {
        case "front": fraction = 1.0 / 6.0
        case "middle": fraction = 0.5
        case "back": fraction = 5.0 / 6.0
        default: return nil
        }
        let s = clampDepth(frontS + (backS - frontS) * fraction)
        guard let widest = intervals(at: s).max(by: { ($0.hi - $0.lo) < ($1.hi - $1.lo) }) else { return nil }
        return point(s, (widest.lo + widest.hi) / 2)
    }
}
