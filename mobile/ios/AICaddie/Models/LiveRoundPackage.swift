import Foundation

public enum GeometryCoverageState: String, Codable, Equatable {
    case ready
    case partial
    case missing
}

public struct LiveRoundPackage: Codable, Equatable {
    public let schema: String
    public let roundId: String
    public let playerProfile: PlayerProfile
    public let course: Course
    public let holes: [Hole]
    public let geometryCoverage: GeometryCoverage
    public let clubProfiles: [ClubProfile]
    public let caddieDecisionEndpoint: String
    public let generatedAt: String

    public init(
        schema: String = "ai-caddie-live-round-package-v1",
        roundId: String,
        playerProfile: PlayerProfile,
        course: Course,
        holes: [Hole],
        geometryCoverage: GeometryCoverage,
        clubProfiles: [ClubProfile],
        caddieDecisionEndpoint: String,
        generatedAt: String
    ) {
        self.schema = schema
        self.roundId = roundId
        self.playerProfile = playerProfile
        self.course = course
        self.holes = holes
        self.geometryCoverage = geometryCoverage
        self.clubProfiles = clubProfiles
        self.caddieDecisionEndpoint = caddieDecisionEndpoint
        self.generatedAt = generatedAt
    }
}

public struct PlayerProfile: Codable, Equatable {
    public let playerId: String
    public let displayName: String
    public let handedness: String
}

public struct Course: Codable, Equatable {
    public let globalId: Int
    public let name: String
    public let teeBox: String
}

public struct Hole: Codable, Equatable, Identifiable {
    public var id: Int { number }

    public let number: Int
    public let par: Int
    public let yards: Int?
    public let geometryCoverage: GeometryCoverageState
}

public struct GeometryCoverage: Codable, Equatable {
    public let state: GeometryCoverageState
    public let readyHoles: Int
    public let totalHoles: Int
}

public struct ClubProfile: Codable, Equatable, Identifiable {
    public var id: String { clubName }

    public let clubName: String
    public let sampleSize: Int
    public let medianM: Double
    public let p10M: Double
    public let p90M: Double

    enum CodingKeys: String, CodingKey {
        case clubName
        case sampleSize
        case medianM = "median_m"
        case p10M = "p10_m"
        case p90M = "p90_m"
    }
}
