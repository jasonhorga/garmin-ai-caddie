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

    private enum CodingKeys: String, CodingKey {
        case hole, par, route, geometryCoverage, sourceRefs, missingData, candidateRoutes, carryTargets, steps, cautions, hazards, map
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
    }
}
