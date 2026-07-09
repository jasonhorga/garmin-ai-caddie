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

    public init(waterCarry: [[Double]] = [], bunkers: [[Double]] = []) {
        self.waterCarry = waterCarry
        self.bunkers = bunkers
    }

    private enum CodingKeys: String, CodingKey {
        case waterCarry = "water_carry"
        case bunkers
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

    private enum CodingKeys: String, CodingKey {
        case hole, par, route, geometryCoverage, sourceRefs, missingData, candidateRoutes, carryTargets, steps, cautions, hazards, map, greenDistances, playsLike, holeImageProjection
        case parSource = "par_source"
        case blueYards = "blue_yards"
        case routeLenM = "route_len_m"
        case landingM = "landing_m"
        case teeClub = "tee_club"
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
