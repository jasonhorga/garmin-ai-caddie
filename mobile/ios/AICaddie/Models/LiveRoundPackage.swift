import Foundation

public enum GeometryCoverageState: String, Codable, Equatable {
    case ready
    case partial
    case missing
}

public enum OfflinePackageCacheState: String, Equatable {
    case ready
    case stale
    case expired
    case degraded
}

public struct LiveRoundPackage: Codable, Equatable {
    public let schema: String
    public let roundId: String
    public let dataMode: String
    public let sourceCoverage: SourceCoverage
    public let missingData: [[String: JSONValue]]
    public let playerProfile: PlayerProfile
    public let course: Course
    public let holes: [Hole]
    public let geometryCoverage: GeometryCoverage
    public let caddieContextSeeds: [CaddieContextSeed]
    public let weatherSnapshot: WeatherSnapshot
    public let clubProfiles: [ClubProfile]
    public let caddieDecisionEndpoint: String
    public let offlinePackageStatus: OfflinePackageStatus
    public let eventCursor: EventCursor
    public let recentHistory: RecentHistory
    public let cachedCaddieRules: CachedCaddieRules
    public let generatedAt: String

    public init(
        schema: String = "ai-caddie-live-round-package-v1",
        roundId: String,
        dataMode: String,
        sourceCoverage: SourceCoverage,
        missingData: [[String: JSONValue]],
        playerProfile: PlayerProfile,
        course: Course,
        holes: [Hole],
        geometryCoverage: GeometryCoverage,
        caddieContextSeeds: [CaddieContextSeed],
        weatherSnapshot: WeatherSnapshot,
        clubProfiles: [ClubProfile],
        caddieDecisionEndpoint: String,
        offlinePackageStatus: OfflinePackageStatus,
        eventCursor: EventCursor,
        recentHistory: RecentHistory,
        cachedCaddieRules: CachedCaddieRules,
        generatedAt: String
    ) {
        self.schema = schema
        self.roundId = roundId
        self.dataMode = dataMode
        self.sourceCoverage = sourceCoverage
        self.missingData = missingData
        self.playerProfile = playerProfile
        self.course = course
        self.holes = holes
        self.geometryCoverage = geometryCoverage
        self.caddieContextSeeds = caddieContextSeeds
        self.weatherSnapshot = weatherSnapshot
        self.clubProfiles = clubProfiles
        self.caddieDecisionEndpoint = caddieDecisionEndpoint
        self.offlinePackageStatus = offlinePackageStatus
        self.eventCursor = eventCursor
        self.recentHistory = recentHistory
        self.cachedCaddieRules = cachedCaddieRules
        self.generatedAt = generatedAt
    }

    public func cacheState(now: Date = Date()) -> OfflinePackageCacheState {
        offlinePackageStatus.cacheState(now: now)
    }
}

public struct SourceCoverage: Codable, Equatable {
    public let state: String
    public let dataMode: String
    public let requestedRoundId: String
    public let selectedRoundId: String?
    public let roundFound: Bool
    public let availableRoundCount: Int
    public let holeCount: Int
    public let clubProfileCount: Int
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

public struct CaddieContextSeed: Codable, Equatable, Identifiable {
    public var id: String { sourceRef }

    public let hole: Int
    public let sourceRef: String
    public let shotTypes: [String]
    public let requiredLiveInputs: [String]
    public let context: [String: JSONValue]
    public let evidence: [[String: JSONValue]]
    public let missingData: [[String: JSONValue]]
}

public struct WeatherSnapshot: Codable, Equatable {
    public let schema: String
    public let state: String
    public let source: String
    public let confidence: String
    public let missingData: [WeatherMissingData]
}

public struct WeatherMissingData: Codable, Equatable {
    public let label: String
    public let reason: String
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

public struct OfflinePackageStatus: Codable, Equatable {
    public let state: String
    public let preparedAt: String
    public let expiresAt: String
    public let cachePolicy: CachePolicy

    public var preparedAtDate: Date? {
        ISO8601DateFormatter().date(from: preparedAt)
    }

    public var expiresAtDate: Date? {
        ISO8601DateFormatter().date(from: expiresAt)
    }

    public func cacheState(now: Date) -> OfflinePackageCacheState {
        if state == "expired" {
            return .expired
        }
        if state == "degraded" {
            return .degraded
        }
        guard let expiresAtDate else {
            return .expired
        }
        if now >= expiresAtDate {
            return .expired
        }
        if let preparedAtDate,
           let staleAt = Calendar(identifier: .gregorian).date(
            byAdding: .hour,
            value: cachePolicy.staleAfterHours,
            to: preparedAtDate
           ),
           now >= staleAt
        {
            return .stale
        }
        return .ready
    }
}

public struct CachePolicy: Codable, Equatable {
    public let staleAfterHours: Int
    public let expiresAfterHours: Int
}

public struct EventCursor: Codable, Equatable {
    public let serverSequence: Int
    public let pendingEventCount: Int
}

public struct RecentHistory: Codable, Equatable {
    public let course: CourseRecentHistory
    public let rounds: [RecentRoundSummary]
    public let holes: [HoleRecentHistory]

    enum CodingKeys: String, CodingKey {
        case course
        case rounds
        case holes
    }

    public init(course: CourseRecentHistory, rounds: [RecentRoundSummary] = [], holes: [HoleRecentHistory]) {
        self.course = course
        self.rounds = rounds
        self.holes = holes
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.course = try container.decode(CourseRecentHistory.self, forKey: .course)
        let rounds = try container.decodeIfPresent([RecentRoundSummary].self, forKey: .rounds)
        self.rounds = rounds ?? []
        self.holes = try container.decode([HoleRecentHistory].self, forKey: .holes)
    }
}

public struct RecentRoundSummary: Codable, Equatable, Identifiable {
    public var id: String { roundId }

    public let roundId: String
    public let date: String
    public let courseName: String
    public let score: Int
    public let par: Int?
    public let toPar: Int?
    public let holesCompleted: Int
    public let sourceRefs: [String]
}

public struct CourseRecentHistory: Codable, Equatable {
    public let courseKey: String
    public let roundCount: Int
    public let averageScore: Double?
    public let bestScore: Int?
    public let worstScore: Int?
    public let recentScores: [Int]
    public let roundIds: [String]
}

public struct HoleRecentHistory: Codable, Equatable, Identifiable {
    public var id: Int { number }

    public let number: Int
    public let sampleCount: Int
    public let averageToPar: Double?
    public let repeatedIssues: [RepeatedIssue]
}

public struct RepeatedIssue: Codable, Equatable {
    public let label: String
    public let count: Int
}

public struct CachedCaddieRules: Codable, Equatable {
    public let decisionContract: String
    public let offlineCapable: Bool
    public let requiredInputs: [String]
    public let degradeWhenMissing: [String]
}
