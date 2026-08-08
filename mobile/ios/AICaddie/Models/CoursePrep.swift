import Foundation

/// Pre-round course-prep DTO from `GET /api/v2/courses/{globalId}/prep`.
/// Mirrors the engine's `course_prep` output (par + route + hazards + strategy + styled map).
public struct CoursePrepResponse: Codable, Equatable {
    public let schema: String
    public let globalId: Int
    public let holeCount: Int
    public let clubs: [CoursePrepClub]
    public let holes: [CoursePrepHole]
}

public struct CoursePrepPackage: Codable, Equatable {
    public let schema: String
    public let globalId: Int
    public let holes: [CoursePrepHole]
    public let missingData: [CoursePrepMissingData]?
}

public struct CoursePrepClub: Codable, Equatable {
    public let name: String
    public let m: Double
    public let yd: Int
}

public struct CoursePrepStep: Codable, Equatable {
    public let club: String?
    public let note: String
}

public struct CoursePrepMissingData: Codable, Equatable {
    public let label: String?
    public let reason: String?
}

public struct CoursePrepCandidateRoute: Codable, Equatable {
    public let id: String
    public let club: String?
    public let carryM: Double?
    public let riskScore: Double?
}

public struct CoursePrepCarryTarget: Codable, Equatable {
    public let kind: String
    public let distanceM: Double?
    public let enterM: Double?
    public let clearM: Double?
    public let sideM: Double?
}

public struct CoursePrepOverlay: Codable, Equatable {
    public let w: Int
    public let h: Int
    public let ppm: Double
    public let ln: Double
    public let route: [[Double]] // [px, py, cumMetres]
}

public struct CoursePrepMap: Codable, Equatable {
    public let image: String // data:image/jpeg;base64,...
    public let overlay: CoursePrepOverlay
}

public struct CoursePrepHazardIntervalReadout: Equatable {
    public let toStartYards: Int
    public let toClearYards: Int
    public let isBehind: Bool
    public let isInside: Bool
    public let isCleared: Bool

    public init(toStartYards: Int, toClearYards: Int, isBehind: Bool, isInside: Bool, isCleared: Bool) {
        self.toStartYards = toStartYards
        self.toClearYards = toClearYards
        self.isBehind = isBehind
        self.isInside = isInside
        self.isCleared = isCleared
    }
}

struct CoursePrepLiveHazardReadout: Equatable {
    let id: String
    let kind: String
    let label: String
    let toYards: Int
    let overYards: Int

    var detail: String { "到 \(toYards) · 过 \(overYards) 码" }

    static func upcoming(
        hazards: CoursePrepHazards,
        route: [[Double]],
        projectionRefs: [CoursePrepProjectionRef],
        playerLatitude: Double,
        playerLongitude: Double
    ) -> [Self]? {
        guard playerLatitude.isFinite, (-90...90).contains(playerLatitude),
              playerLongitude.isFinite, (-180...180).contains(playerLongitude) else {
            return nil
        }
        let refs = projectionRefs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
        guard let playerPx = WatchEventBridge.projectToTopoPx(
            lat: playerLatitude,
            lon: playerLongitude,
            refs: refs
        ), let progressM = playerProgressMetres(on: route, playerPx: playerPx) else {
            return nil
        }

        let supported = hazards.details
            .filter { $0.kind == "bunker" || $0.kind == "water" }
            .sorted {
                if $0.frontRouteM == $1.frontRouteM { return $0.kind < $1.kind }
                return $0.frontRouteM < $1.frontRouteM
            }
        guard !supported.isEmpty else { return nil }

        let totals = Dictionary(grouping: supported, by: \.kind).mapValues(\.count)
        var ordinals: [String: Int] = [:]
        var upcoming: [(readout: Self, frontRouteM: Double)] = []
        var hasUnpassedGeometry = false

        for detail in supported {
            let ordinal = ordinals[detail.kind, default: 0]
            ordinals[detail.kind] = ordinal + 1
            guard max(detail.frontRouteM, detail.backRouteM) > progressM else { continue }
            hasUnpassedGeometry = true
            guard let front = coordinate(for: detail.frontPx, refs: refs),
                  let back = coordinate(for: detail.backPx, refs: refs),
                  let toYards = GeoDistance.yards(
                      from: playerLatitude,
                      playerLongitude,
                      to: front.latitude,
                      front.longitude
                  ),
                  let overYards = GeoDistance.yards(
                      from: playerLatitude,
                      playerLongitude,
                      to: back.latitude,
                      back.longitude
                  ) else {
                continue
            }
            let baseLabel = detail.kind == "water" ? "水域" : "沙坑"
            let label = totals[detail.kind, default: 0] > 1 ? "\(baseLabel) \(ordinal + 1)" : baseLabel
            upcoming.append((
                readout: Self(
                    id: "\(detail.kind)-\(ordinal)",
                    kind: detail.kind,
                    label: label,
                    toYards: toYards,
                    overYards: overYards
                ),
                frontRouteM: detail.frontRouteM
            ))
        }

        if !hasUnpassedGeometry { return [] }
        guard !upcoming.isEmpty else { return nil }
        return upcoming.sorted {
            if $0.readout.toYards == $1.readout.toYards {
                if $0.frontRouteM == $1.frontRouteM { return $0.readout.id < $1.readout.id }
                return $0.frontRouteM < $1.frontRouteM
            }
            return $0.readout.toYards < $1.readout.toYards
        }.map(\.readout)
    }

    private static func coordinate(
        for pixels: [Double],
        refs: [(lat: Double, lon: Double, px: Double, py: Double)]
    ) -> (latitude: Double, longitude: Double)? {
        guard pixels.count >= 2 else { return nil }
        return WatchEventBridge.projectFromTopoPx(px: pixels[0], py: pixels[1], refs: refs)
    }

    private static func playerProgressMetres(on route: [[Double]], playerPx: [Double]) -> Double? {
        guard playerPx.count >= 2, playerPx[0].isFinite, playerPx[1].isFinite, route.count >= 2 else {
            return nil
        }
        var bestDistanceSquared = Double.greatestFiniteMagnitude
        var bestProgressM: Double?
        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            guard validRoutePoint(start), validRoutePoint(end), end[2] >= start[2] else { continue }
            let dx = end[0] - start[0]
            let dy = end[1] - start[1]
            let lengthSquared = dx * dx + dy * dy
            guard lengthSquared > 0 else { continue }
            let rawFraction = ((playerPx[0] - start[0]) * dx + (playerPx[1] - start[1]) * dy)
                / lengthSquared
            let fraction = min(max(rawFraction, 0), 1)
            let projectedX = start[0] + dx * fraction
            let projectedY = start[1] + dy * fraction
            let playerDX = playerPx[0] - projectedX
            let playerDY = playerPx[1] - projectedY
            let distanceSquared = playerDX * playerDX + playerDY * playerDY
            if distanceSquared < bestDistanceSquared {
                bestDistanceSquared = distanceSquared
                bestProgressM = start[2] + (end[2] - start[2]) * fraction
            }
        }
        return bestProgressM
    }

    private static func validRoutePoint(_ point: [Double]) -> Bool {
        point.count >= 3 && point[0].isFinite && point[1].isFinite && point[2].isFinite
    }
}

public enum CoursePrepRoute {
    private static let yard = 1.09361

    public static func yards(fromMetres metres: Double) -> Int {
        Int((metres * yard).rounded())
    }

    /// 码 → 米(用户在前端以「码」输入距离时,转回后端用的米)。
    public static func metres(fromYards yards: Double) -> Double {
        yards / Self.yard
    }

    public static func intervalReadout(currentMetres: Double, startMetres: Double, endMetres: Double) -> CoursePrepHazardIntervalReadout {
        let start = min(startMetres, endMetres)
        let end = max(startMetres, endMetres)
        return CoursePrepHazardIntervalReadout(
            toStartYards: yards(fromMetres: max(0, start - currentMetres)),
            toClearYards: yards(fromMetres: max(0, end - currentMetres)),
            isBehind: currentMetres < start,
            isInside: currentMetres >= start && currentMetres <= end,
            isCleared: currentMetres > end
        )
    }
}

public struct CoursePrepHazards: Codable, Equatable {
    public let waterCarry: [[Double]]
    public let bunkers: [[Double]]
    public let details: [CoursePrepHazardDetail]

    public init(
        waterCarry: [[Double]] = [],
        bunkers: [[Double]] = [],
        details: [CoursePrepHazardDetail] = []
    ) {
        self.waterCarry = waterCarry
        self.bunkers = bunkers
        self.details = details
    }

    private enum CodingKeys: String, CodingKey {
        case waterCarry = "water_carry"
        case bunkers, details
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        waterCarry = try container.decodeIfPresent([[Double]].self, forKey: .waterCarry) ?? []
        bunkers = try container.decodeIfPresent([[Double]].self, forKey: .bunkers) ?? []
        details = try container.decodeIfPresent([CoursePrepHazardDetail].self, forKey: .details) ?? []
    }
}

/// Player-facing front/back facts for one mapped hazard. Route metres are used only for ordering and
/// passed/remaining state; front/back metres are straight-line distances from the selected tee, and
/// the pixel pairs are the real geometry boundary points on the shared topo image.
public struct CoursePrepHazardDetail: Codable, Equatable {
    public let kind: String
    public let frontM: Double
    public let backM: Double
    public let frontRouteM: Double
    public let backRouteM: Double
    public let frontPx: [Double]
    public let backPx: [Double]
    public let sideM: Double?

    public init(
        kind: String,
        frontM: Double,
        backM: Double,
        frontRouteM: Double,
        backRouteM: Double,
        frontPx: [Double],
        backPx: [Double],
        sideM: Double?
    ) {
        self.kind = kind
        self.frontM = frontM
        self.backM = backM
        self.frontRouteM = frontRouteM
        self.backRouteM = backRouteM
        self.frontPx = frontPx
        self.backPx = backPx
        self.sideM = sideM
    }
}

/// Garmin CourseView's lightweight 30-direction green shape. `pointsPx` is drawing-only in the
/// same affine frame as `resolvedMapOverlay`; the source values are intentionally not exposed as
/// measured front/middle/back distances.
public struct CoursePrepGreenOutline: Codable, Equatable {
    public let available: Bool
    public let source: String?
    public let distanceUnit: String?
    public let pointsPx: [[Double]]

    public init(
        available: Bool,
        source: String? = nil,
        distanceUnit: String? = nil,
        pointsPx: [[Double]] = []
    ) {
        self.available = available
        self.source = source
        self.distanceUnit = distanceUnit
        self.pointsPx = pointsPx
    }
}

public struct CoursePrepHole: Codable, Equatable {
    public let hole: Int
    public let par: Int
    public let parSource: String
    public let blueYards: Int
    public let routeLenM: Double
    public let route: [[Double]]
    public let geometryCoverage: String
    public let geometryRevision: String?
    public let sourceRefs: [String]
    public let missingData: [CoursePrepMissingData]
    public let candidateRoutes: [CoursePrepCandidateRoute]
    public let carryTargets: [CoursePrepCarryTarget]
    public let steps: [CoursePrepStep]
    public let cautions: [String]
    public let landingM: Double?
    public let teeClub: String?
    public let hazards: CoursePrepHazards
    public let map: CoursePrepMap?
    // round-13 LIVE: per-hole 前/中/后果岭 (F/M/B) + plays-like slope, served on /prep (no DEM).
    public let greenDistances: CoursePrepGreenDistances?
    public let playsLike: CoursePrepPlaysLike?
    // watch P0.1: geo→px anchors so a client can place its GPS/pin/landings on the topo map.
    public let holeImageProjection: CoursePrepHoleImageProjection?
    /// Drawing-only outline available while precise prodgeometry is still downloading.
    public let greenOutline: CoursePrepGreenOutline?

    private enum CodingKeys: String, CodingKey {
        case hole, par, route, geometryCoverage, geometryRevision, sourceRefs, missingData, candidateRoutes, carryTargets, steps, cautions, hazards, map, greenDistances, playsLike, holeImageProjection, greenOutline
        case parSource = "par_source"
        case blueYards = "blue_yards"
        case routeLenM = "route_len_m"
        case landingM = "landing_m"
        case teeClub = "tee_club"
    }

    public init(
        hole: Int,
        par: Int,
        parSource: String,
        blueYards: Int,
        routeLenM: Double,
        route: [[Double]] = [],
        geometryCoverage: String = "missing",
        geometryRevision: String? = nil,
        sourceRefs: [String] = [],
        missingData: [CoursePrepMissingData] = [],
        candidateRoutes: [CoursePrepCandidateRoute] = [],
        carryTargets: [CoursePrepCarryTarget] = [],
        steps: [CoursePrepStep] = [],
        cautions: [String] = [],
        landingM: Double? = nil,
        teeClub: String? = nil,
        hazards: CoursePrepHazards = CoursePrepHazards(),
        map: CoursePrepMap? = nil,
        greenDistances: CoursePrepGreenDistances? = nil,
        playsLike: CoursePrepPlaysLike? = nil,
        holeImageProjection: CoursePrepHoleImageProjection? = nil,
        greenOutline: CoursePrepGreenOutline? = nil
    ) {
        self.hole = hole
        self.par = par
        self.parSource = parSource
        self.blueYards = blueYards
        self.routeLenM = routeLenM
        self.route = route
        self.geometryCoverage = geometryCoverage
        self.geometryRevision = geometryRevision
        self.sourceRefs = sourceRefs
        self.missingData = missingData
        self.candidateRoutes = candidateRoutes
        self.carryTargets = carryTargets
        self.steps = steps
        self.cautions = cautions
        self.landingM = landingM
        self.teeClub = teeClub
        self.hazards = hazards
        self.map = map
        self.greenDistances = greenDistances
        self.playsLike = playsLike
        self.holeImageProjection = holeImageProjection
        self.greenOutline = greenOutline
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.hole = try container.decode(Int.self, forKey: .hole)
        self.par = try container.decode(Int.self, forKey: .par)
        self.parSource = try container.decode(String.self, forKey: .parSource)
        self.blueYards = try container.decode(Int.self, forKey: .blueYards)
        self.routeLenM = try container.decode(Double.self, forKey: .routeLenM)
        self.route = try container.decodeIfPresent([[Double]].self, forKey: .route) ?? []
        self.geometryCoverage = try container.decodeIfPresent(String.self, forKey: .geometryCoverage) ?? "missing"
        self.geometryRevision = try container.decodeIfPresent(String.self, forKey: .geometryRevision)
        self.sourceRefs = try container.decodeIfPresent([String].self, forKey: .sourceRefs) ?? []
        self.missingData = try container.decodeIfPresent([CoursePrepMissingData].self, forKey: .missingData) ?? []
        self.candidateRoutes = try container.decodeIfPresent([CoursePrepCandidateRoute].self, forKey: .candidateRoutes) ?? []
        self.carryTargets = try container.decodeIfPresent([CoursePrepCarryTarget].self, forKey: .carryTargets) ?? []
        self.steps = try container.decode([CoursePrepStep].self, forKey: .steps)
        self.cautions = try container.decode([String].self, forKey: .cautions)
        self.landingM = try container.decodeIfPresent(Double.self, forKey: .landingM)
        self.teeClub = try container.decodeIfPresent(String.self, forKey: .teeClub)
        self.hazards = try container.decode(CoursePrepHazards.self, forKey: .hazards)
        self.map = try container.decodeIfPresent(CoursePrepMap.self, forKey: .map)
        self.greenDistances = try container.decodeIfPresent(CoursePrepGreenDistances.self, forKey: .greenDistances)
        self.playsLike = try container.decodeIfPresent(CoursePrepPlaysLike.self, forKey: .playsLike)
        self.holeImageProjection = try container.decodeIfPresent(CoursePrepHoleImageProjection.self, forKey: .holeImageProjection)
        self.greenOutline = try container.decodeIfPresent(CoursePrepGreenOutline.self, forKey: .greenOutline)
    }

    /// Overlay in the shared `/topo.png` pixel frame. Rendered prep already embeds this value; the
    /// lightweight `render=false` response instead carries the route in local metres plus three affine
    /// anchors. The backend fixes those anchors at local (0,0), (120,0), and (0,120), in that order.
    public var resolvedMapOverlay: CoursePrepOverlay? {
        if let overlay = map?.overlay,
           overlay.w > 0, overlay.h > 0, overlay.route.count >= 2 {
            return overlay
        }
        guard route.count >= 2,
              let projection = holeImageProjection,
              projection.available,
              let width = projection.widthPx, width > 0,
              let height = projection.heightPx, height > 0,
              let refs = projection.refs, refs.count >= 3 else {
            return nil
        }

        let origin = refs[0]
        let xReference = refs[1]
        let yReference = refs[2]
        let pixelValues = [
            origin.px, origin.py,
            xReference.px, xReference.py,
            yReference.px, yReference.py,
        ]
        guard pixelValues.allSatisfy(\.isFinite) else { return nil }

        let xBasis = (
            x: (xReference.px - origin.px) / 120,
            y: (xReference.py - origin.py) / 120
        )
        let yBasis = (
            x: (yReference.px - origin.px) / 120,
            y: (yReference.py - origin.py) / 120
        )
        let ppm = (hypot(xBasis.x, xBasis.y) + hypot(yBasis.x, yBasis.y)) / 2
        guard ppm.isFinite, ppm > 0 else { return nil }

        var previousLocal: (x: Double, y: Double)?
        var cumulativeM = 0.0
        var projectedRoute: [[Double]] = []
        for row in route {
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            let local = (x: row[0], y: row[1])
            if let previousLocal {
                cumulativeM += hypot(local.x - previousLocal.x, local.y - previousLocal.y)
            }
            let routeM = row.count >= 3 && row[2].isFinite ? row[2] : cumulativeM
            projectedRoute.append([
                origin.px + local.x * xBasis.x + local.y * yBasis.x,
                origin.py + local.x * xBasis.y + local.y * yBasis.y,
                routeM,
            ])
            previousLocal = local
        }

        let length = routeLenM.isFinite && routeLenM > 0
            ? routeLenM
            : (projectedRoute.last?[2] ?? 0)
        return CoursePrepOverlay(
            w: width,
            h: height,
            ppm: ppm,
            ln: length,
            route: projectedRoute
        )
    }

    /// Composite rounds renumber the second CourseView loop from local holes 1...9 to round holes
    /// 10...18. Retain every factual prep field while moving only that display/event identity.
    public func renumbered(to roundHole: Int) -> CoursePrepHole {
        CoursePrepHole(
            hole: roundHole,
            par: par,
            parSource: parSource,
            blueYards: blueYards,
            routeLenM: routeLenM,
            route: route,
            geometryCoverage: geometryCoverage,
            geometryRevision: geometryRevision,
            sourceRefs: sourceRefs,
            missingData: missingData,
            candidateRoutes: candidateRoutes,
            carryTargets: carryTargets,
            steps: steps,
            cautions: cautions,
            landingM: landingM,
            teeClub: teeClub,
            hazards: hazards,
            map: map,
            greenDistances: greenDistances,
            playsLike: playsLike,
            holeImageProjection: holeImageProjection,
            greenOutline: greenOutline
        )
    }
}

public struct CoursePrepGreenDistances: Codable, Equatable {
    public let available: Bool
    public let frontM: Double?
    public let middleM: Double?
    public let backM: Double?
    // round-13 B1 (LIVE rangefinder): the green Front/Middle/Back as WGS84 lat/lon, so the phone can
    // recompute live distance to the green from its own GPS fix (offline). Present only when the
    // hole's RefLat/RefLon anchor is known; nil otherwise → the UI falls back to the tee distances.
    // Property names match the backend JSON keys (frontLat/frontLon/…), so the synthesized Codable
    // decodes them with no explicit CodingKeys; absent keys decode as nil.
    public let frontLat: Double?
    public let frontLon: Double?
    public let middleLat: Double?
    public let middleLon: Double?
    public let backLat: Double?
    public let backLon: Double?
}

public struct CoursePrepPlaysLike: Codable, Equatable {
    public let available: Bool
    public let deltaM: Double?
    public let deltaYd: Int?
}

// watch P0.1: the topo image's geo→pixel mapping. 3 non-collinear reference points (each WGS84 +
// its pixel on /topo.png); a client fits an affine from them to project any lat/lon → pixel.
public struct CoursePrepHoleImageProjection: Codable, Equatable {
    public let available: Bool
    public let widthPx: Int?
    public let heightPx: Int?
    public let refs: [CoursePrepProjectionRef]?
}

public struct CoursePrepProjectionRef: Codable, Equatable {
    public let lat: Double
    public let lon: Double
    public let px: Double
    public let py: Double
}
