import CoreLocation
import Foundation

/// One hole's factual anchors for "which hole am I on": the selected Tee (package `Hole`) and the
/// green middle (CoursePrep F/M/B lat/lon). Either may be missing on a cold or lightweight package.
struct HoleLocatorGeometry {
    let hole: Int
    let tee: CLLocationCoordinate2D?
    let green: CLLocationCoordinate2D?
    /// Optional WGS84 fairway outline. It is preferred over the straight corridor when present.
    let fairway: [[CLLocationCoordinate2D]]

    init(
        hole: Int,
        tee: CLLocationCoordinate2D?,
        green: CLLocationCoordinate2D?,
        fairway: [[CLLocationCoordinate2D]] = []
    ) {
        self.hole = hole
        self.tee = tee
        self.green = green
        self.fairway = fairway
    }

    /// The package's holes in package order, with the green from the package's own course prep.
    static func rows(for package: LiveRoundPackage) -> [HoleLocatorGeometry] {
        package.holes.map { hole in
            let distances = package.coursePrep?.holes.first { $0.hole == hole.number }?.greenDistances
            let fairway = package.coursePrep?.holes.first { $0.hole == hole.number }?.fairwayOutline?.polygons
                .map { polygon in
                    polygon.outerLatLon.compactMap { row -> CLLocationCoordinate2D? in
                        guard row.count >= 2 else { return nil }
                        return coordinate(row[0], row[1])
                    }
                } ?? []
            return HoleLocatorGeometry(
                hole: hole.number,
                tee: coordinate(hole.teeLatitude, hole.teeLongitude),
                green: coordinate(distances?.middleLat, distances?.middleLon),
                fairway: fairway
            )
        }
    }

    private static func coordinate(_ latitude: Double?, _ longitude: Double?) -> CLLocationCoordinate2D? {
        guard let latitude, let longitude,
              latitude.isFinite, longitude.isFinite,
              (-90...90).contains(latitude), (-180...180).contains(longitude) else { return nil }
        return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}

/// Where the player is relative to the course, for the hole screen before the first stroke.
enum CurrentHoleLocation: Equatable {
    /// Inside this hole's area: the hole screen follows it, and a first stroke here starts the round.
    case onHole(Int)
    /// Near the course (practice range, clubhouse, car park) but in no hole's area: no round starts.
    case atCourse
    /// Far from every hole: 备战 at home.
    case awayFromCourse
    /// No usable fix, or no hole with a position.
    case unknown

    var hole: Int? {
        if case .onHole(let hole) = self { return hole }
        return nil
    }
}

/// Remembers the last hole reported by GPS while 备战 moves between hole screens. A manual hole
/// preview wins until the location actually changes to another hole.
struct PrepHoleFollowingState: Equatable {
    private(set) var lastLocatedHole: Int?
    private var pendingLocatedHole: Int?
    private var pendingSample: Sample?

    // LocationProvider's 3 m distance filter can emit two fixes from 3–6 m stationary drift.
    // Require either 5 s of persistence or 10 m of real displacement before confirming the
    // second fix. Walking to the next tee can confirm immediately; standing still can settle.
    static let minimumConfirmationInterval: TimeInterval = 5
    static let minimumConfirmationDisplacementM = 10.0

    private struct Sample: Equatable {
        let sampledAt: Date
        let latitude: Double?
        let longitude: Double?
    }

    private mutating func clearPending() {
        pendingLocatedHole = nil
        pendingSample = nil
    }

    mutating func reset() {
        lastLocatedHole = nil
        clearPending()
    }

    static let maximumConfirmationAccuracyM = 30.0
    static let maximumCachedSampleAge: TimeInterval = 30

    /// Only fresh, precise fixes well inside the candidate area may contribute time/distance.
    mutating func navigationTarget(
        currentLocatedHole: Int?, displayedHole: Int, fix: LocationFix,
        holes: [HoleLocatorGeometry], now: Date = Date()
    ) -> Int? {
        guard let sampledAt = Self.sampleDate(fix.capturedAt), let currentLocatedHole else {
            clearPending()
            return nil
        }
        guard now.timeIntervalSince(sampledAt) <= Self.maximumCachedSampleAge else {
            // CoreLocation may deliver an old cache entry first. It can replace the candidate,
            // but the next usable observation must start its own clock and displacement baseline.
            pendingLocatedHole = currentLocatedHole
            pendingSample = nil
            return nil
        }
        let accuracy = fix.horizontalAccuracyM
        guard accuracy.isFinite, (0...Self.maximumConfirmationAccuracyM).contains(accuracy),
              CurrentHoleLocator.entryDepthM(
                hole: currentLocatedHole, coordinate: fix.coordinate, holes: holes,
                preferredHole: displayedHole
              ) > max(accuracy, Self.minimumConfirmationDisplacementM) else {
            clearPending()
            return nil
        }
        return navigationTarget(currentLocatedHole: currentLocatedHole, displayedHole: displayedHole,
                                sampledAt: sampledAt, coordinate: fix.coordinate)
    }

    static func sampleDate(_ capturedAt: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: capturedAt) ?? ISO8601DateFormatter().date(from: capturedAt)
    }

    mutating func navigationTarget(
        currentLocatedHole: Int?, displayedHole: Int,
        sampledAt: Date = Date(), coordinate: CLLocationCoordinate2D? = nil
    ) -> Int? {
        guard let currentLocatedHole else {
            // A missing fix cannot confirm a consecutive sample for the pending hole, but it also
            // must not erase the last confirmed hole used by the current screen.
            clearPending()
            return nil
        }
        if currentLocatedHole == lastLocatedHole {
            clearPending()
            return nil
        }
        if lastLocatedHole == nil, currentLocatedHole == displayedHole {
            // A first fix that agrees with the screen cannot move it, so it confirms at once;
            // a later manual preview of another hole is then kept until the fix really changes.
            lastLocatedHole = currentLocatedHole
            clearPending()
            return nil
        }
        let validCoordinate = coordinate.flatMap { CLLocationCoordinate2DIsValid($0) ? $0 : nil }
        guard pendingLocatedHole == currentLocatedHole, let first = pendingSample else {
            pendingLocatedHole = currentLocatedHole
            pendingSample = Sample(sampledAt: sampledAt, latitude: validCoordinate?.latitude,
                                   longitude: validCoordinate?.longitude)
            return nil
        }
        // A replay of the same fix is not a second observation. Use the fix's capture time,
        // not delivery time, so delayed publisher callbacks cannot make old drift look stable.
        let interval = sampledAt.timeIntervalSince(first.sampledAt)
        guard interval >= 0,
              interval > 0 || first.latitude != validCoordinate?.latitude
                || first.longitude != validCoordinate?.longitude else { return nil }
        let displacement: Double = {
            guard let latitude = first.latitude, let longitude = first.longitude,
                  let validCoordinate else { return 0 }
            return GeoDistance.haversineMetres(latitude, longitude,
                                              validCoordinate.latitude, validCoordinate.longitude)
        }()
        guard interval >= Self.minimumConfirmationInterval
                || displacement >= Self.minimumConfirmationDisplacementM else { return nil }
        lastLocatedHole = currentLocatedHole
        clearPending()
        return currentLocatedHole == displayedHole ? nil : currentLocatedHole
    }
}

/// Pure "which hole am I on" from the package's hole geometry. Unlike `LiveHoleGPSResolver` (a
/// cautious proposal during play that abstains between two close tees), this always gives one answer
/// so the pre-round screen can follow the player and the first stroke has a definite hole.
///
/// Rules, in order:
/// 1. A fix worse than `maximumHorizontalAccuracyM` (or invalid) is `.unknown`.
/// 2. Within `teeRadiusM` of a tee → the nearest such tee's hole. The tee wins over every other
///    area: where a green sits beside the next tee, the player standing on that tee is about to play
///    the next hole.
///    When the displayed hole's tee is within `sharedTeeToleranceM` of that nearest tee (a shared
///    anchor), the displayed hole wins instead of package order.
/// 3. Inside a fairway outline → that hole. At an overlapping boundary, package order wins.
/// 4. Within `corridorHalfWidthM` of a hole's tee→green-middle line → that hole. At the boundary of
///    two corridors the smaller distance to the line wins; an exact tie goes to package order.
/// 5. Otherwise within `courseRadiusM` of any tee or green → `.atCourse`, else `.awayFromCourse`.
///
/// The corridor is the straight tee→green line, so on a strong dogleg the elbow can fall outside it;
/// that only delays following (the tee and green areas still match), it never picks a wrong hole.
enum CurrentHoleLocator {
    static let maximumHorizontalAccuracyM = LiveHoleGPSResolver.maximumHorizontalAccuracyM
    static let teeRadiusM = LiveHoleGPSResolver.maximumTeeDistanceM
    static let corridorHalfWidthM = 50.0
    /// Tees this close to the nearest one count as the same start area; the displayed hole wins.
    static let sharedTeeToleranceM = 5.0
    /// The design's "离所有发球台/果岭 1.5 km 外" boundary for having left the course.
    static let courseRadiusM = 1_500.0

    static func locate(
        coordinate: CLLocationCoordinate2D,
        horizontalAccuracyM: Double,
        holes: [HoleLocatorGeometry],
        preferredHole: Int? = nil
    ) -> CurrentHoleLocation {
        guard CLLocationCoordinate2DIsValid(coordinate),
              coordinate.latitude.isFinite, coordinate.longitude.isFinite,
              horizontalAccuracyM.isFinite,
              (0...maximumHorizontalAccuracyM).contains(horizontalAccuracyM) else { return .unknown }
        let anchored = holes.filter { $0.tee != nil || $0.green != nil || !$0.fairway.isEmpty }
        guard !anchored.isEmpty else { return .unknown }

        // `min(by:)` keeps the first of equal elements, so ties resolve to package order.
        let tees = anchored.compactMap { row in
            row.tee.map { (hole: row.hole, distance: metres(coordinate, $0)) }
        }
        if let nearestTee = tees.min(by: { $0.distance < $1.distance }),
           nearestTee.distance <= teeRadiusM {
            // A course package can expose one shared clubhouse/course anchor for several holes.
            // When the player is viewing one of those holes, its tee is the intended start area;
            // package order must not turn an equal-distance anchor into hole 1. A clearly nearer
            // tee still wins, so standing on hole 10's tee while viewing hole 1 follows to 10.
            if let preferredHole,
               let preferred = tees.first(where: { $0.hole == preferredHole }),
               preferred.distance <= nearestTee.distance + sharedTeeToleranceM {
                return .onHole(preferredHole)
            }
            return .onHole(nearestTee.hole)
        }

        // A valid fairway outline is stronger than the straight corridor. Package order breaks an
        // overlapping-boundary tie, while the tee rule above always wins at a shared tee/green.
        if let fairwayHole = anchored.first(where: { row in
            row.fairway.contains { pointInPolygon(coordinate, polygon: $0) }
        }) {
            return .onHole(fairwayHole.hole)
        }

        let corridors = anchored.map { row in
            (hole: row.hole, distance: distanceToHoleLine(coordinate, tee: row.tee, green: row.green))
        }
        if let nearest = corridors.min(by: { $0.distance < $1.distance }),
           nearest.distance <= corridorHalfWidthM {
            return .onHole(nearest.hole)
        }

        let nearestAnchor = anchored
            .flatMap { [$0.tee, $0.green].compactMap { $0 } }
            .map { metres(coordinate, $0) }
            .min() ?? .infinity
        return nearestAnchor <= courseRadiusM ? .atCourse : .awayFromCourse
    }

    /// Distance inside the same area that `locate` selected: tee disc, fairway outline, or
    /// rounded tee→green corridor. Competing tees/corridors also bound the winning margin, so
    /// crossing their overlap's halfway line by a metre cannot count as deep entry.
    static func entryDepthM(
        hole: Int, coordinate: CLLocationCoordinate2D, holes: [HoleLocatorGeometry],
        preferredHole: Int? = nil
    ) -> Double {
        guard locate(coordinate: coordinate, horizontalAccuracyM: 0, holes: holes,
                     preferredHole: preferredHole) == .onHole(hole),
              let row = holes.first(where: { $0.hole == hole }) else { return 0 }
        let tees = holes.compactMap { row in
            row.tee.map { (hole: row.hole, distance: metres(coordinate, $0)) }
        }
        if tees.contains(where: { $0.distance <= teeRadiusM }),
           let selected = tees.first(where: { $0.hole == hole }) {
            let margin = tees.filter { $0.hole != hole }.map {
                max(0, ($0.distance - selected.distance - sharedTeeToleranceM) / 2)
            }.min() ?? .infinity
            return min(teeRadiusM - selected.distance, margin)
        }
        // Tee areas always outrank fairways/corridors. A sample just outside a different tee
        // must also clear its boundary before it can count toward a new hole.
        let teeExclusionDepth = tees.filter { $0.hole != hole }
            .map { $0.distance - teeRadiusM }.min() ?? .infinity
        let polygonDepths = row.fairway.filter { pointInPolygon(coordinate, polygon: $0) }
            .map { distanceToPolygonBoundary(coordinate, polygon: $0) }
        if let depth = polygonDepths.max() {
            // Package order owns overlapping fairways. Clear the earlier areas' boundaries too.
            let earlier = holes.prefix { $0.hole != hole }
            let earlierBoundary = earlier.flatMap { $0.fairway }.map {
                distanceToPolygonBoundary(coordinate, polygon: $0)
            }.min() ?? .infinity
            return min(depth, min(teeExclusionDepth, earlierBoundary))
        }
        let distance = distanceToHoleLine(coordinate, tee: row.tee, green: row.green)
        let margin = holes.filter { $0.hole != hole }.map {
            max(0, (distanceToHoleLine(coordinate, tee: $0.tee, green: $0.green) - distance) / 2)
        }.min() ?? .infinity
        let fairwayBoundary = holes.filter { $0.hole != hole }.flatMap { $0.fairway }.map {
            distanceToPolygonBoundary(coordinate, polygon: $0)
        }.min() ?? .infinity
        return min(corridorHalfWidthM - distance, min(margin, min(teeExclusionDepth, fairwayBoundary)))
    }

    private static func distanceToPolygonBoundary(
        _ point: CLLocationCoordinate2D, polygon: [CLLocationCoordinate2D]
    ) -> Double {
        guard polygon.count >= 3 else { return .infinity }
        return polygon.indices.map { index in
            distanceToHoleLine(point, tee: polygon[index], green: polygon[(index + 1) % polygon.count])
        }.min() ?? .infinity
    }

    static func locate(fix: LocationFix?, package: LiveRoundPackage) -> CurrentHoleLocation {
        locate(fix: fix, package: package, preferredHole: nil)
    }

    static func locate(
        fix: LocationFix?,
        package: LiveRoundPackage,
        preferredHole: Int?
    ) -> CurrentHoleLocation {
        guard let fix else { return .unknown }
        return locate(
            coordinate: fix.coordinate,
            horizontalAccuracyM: fix.horizontalAccuracyM,
            holes: HoleLocatorGeometry.rows(for: package),
            preferredHole: preferredHole
        )
    }

    private static func metres(_ a: CLLocationCoordinate2D, _ b: CLLocationCoordinate2D) -> Double {
        GeoDistance.haversineMetres(a.latitude, a.longitude, b.latitude, b.longitude)
    }

    /// Distance to the tee→green segment in a local flat frame centred on the fix (exact enough over
    /// a hole's few hundred metres). A hole with one anchor is the distance to that point.
    private static func distanceToHoleLine(
        _ point: CLLocationCoordinate2D,
        tee: CLLocationCoordinate2D?,
        green: CLLocationCoordinate2D?
    ) -> Double {
        guard let tee, let green else {
            return (tee ?? green).map { metres(point, $0) } ?? .infinity
        }
        let metresPerDegreeLatitude = 111_320.0
        let metresPerDegreeLongitude = metresPerDegreeLatitude * cos(point.latitude * .pi / 180)
        func local(_ c: CLLocationCoordinate2D) -> (x: Double, y: Double) {
            ((c.longitude - point.longitude) * metresPerDegreeLongitude,
             (c.latitude - point.latitude) * metresPerDegreeLatitude)
        }
        let a = local(tee)
        let b = local(green)
        let dx = b.x - a.x
        let dy = b.y - a.y
        let lengthSquared = dx * dx + dy * dy
        guard lengthSquared > 0 else { return (a.x * a.x + a.y * a.y).squareRoot() }
        // The point is the origin of the local frame.
        let t = max(0, min(1, -(a.x * dx + a.y * dy) / lengthSquared))
        let cx = a.x + t * dx
        let cy = a.y + t * dy
        return (cx * cx + cy * cy).squareRoot()
    }

    private static func pointInPolygon(
        _ point: CLLocationCoordinate2D,
        polygon: [CLLocationCoordinate2D]
    ) -> Bool {
        guard polygon.count >= 3 else { return false }
        var inside = false
        var previous = polygon[polygon.count - 1]
        for current in polygon {
            let crosses = (current.latitude > point.latitude) != (previous.latitude > point.latitude)
            if crosses {
                let denominator = previous.latitude - current.latitude
                if abs(denominator) > .ulpOfOne {
                    let longitude = (previous.longitude - current.longitude)
                        * (point.latitude - current.latitude) / denominator + current.longitude
                    if point.longitude < longitude { inside.toggle() }
                }
            }
            previous = current
        }
        return inside
    }
}
