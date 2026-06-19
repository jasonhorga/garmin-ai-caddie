import Foundation

/// Compact 统计 payload from `GET /api/v2/history/stats/mobile` (server `build_mobile_stats`).
/// Only the fields the 统计 screens render are modelled (Swift Codable ignores the rest). Decode is
/// section-tolerant — one odd section never blanks the whole screen. Distances are metres (the
/// client shows 码 via CoursePrepRoute.yards).
public struct MobileStats: Codable, Equatable {
    public let summary: StatsSummary?
    public let scoring: StatsScoring?
    public let time: StatsTime?
    public let trend: StatsTrend?
    public let courses: [StatsCourse]
    public let clubs: [StatsClub]
    public let diagnosis: StatsDiagnosis?

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        summary = try? c.decodeIfPresent(StatsSummary.self, forKey: .summary)
        scoring = try? c.decodeIfPresent(StatsScoring.self, forKey: .scoring)
        time = try? c.decodeIfPresent(StatsTime.self, forKey: .time)
        trend = try? c.decodeIfPresent(StatsTrend.self, forKey: .trend)
        courses = (try? c.decodeIfPresent([StatsCourse].self, forKey: .courses)) ?? []
        clubs = (try? c.decodeIfPresent([StatsClub].self, forKey: .clubs)) ?? []
        diagnosis = try? c.decodeIfPresent(StatsDiagnosis.self, forKey: .diagnosis)
    }

    public init(summary: StatsSummary? = nil, scoring: StatsScoring? = nil, time: StatsTime? = nil,
                trend: StatsTrend? = nil, courses: [StatsCourse] = [], clubs: [StatsClub] = [],
                diagnosis: StatsDiagnosis? = nil) {
        self.summary = summary
        self.scoring = scoring
        self.time = time
        self.trend = trend
        self.courses = courses
        self.clubs = clubs
        self.diagnosis = diagnosis
    }

    private enum CodingKeys: String, CodingKey { case summary, scoring, time, trend, courses, clubs, diagnosis }
}

/// Per-round trend series (近 N 场 18 洞) for the line chart — oldest→newest.
public struct StatsTrend: Codable, Equatable {
    public let points: [StatsTrendPoint]

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        points = (try? c.decodeIfPresent([StatsTrendPoint].self, forKey: .points)) ?? []
    }

    public init(points: [StatsTrendPoint]) { self.points = points }

    private enum CodingKeys: String, CodingKey { case points }
}

public struct StatsTrendPoint: Codable, Equatable, Identifiable {
    public var id: String { roundId ?? date }
    public let date: String
    public let score: Int?
    public let toPar: Int?
    public let birdies: Int?
    public let pars: Int?
    public let bogeys: Int?
    public let doublesPlus: Int?
    public let roundId: String?
}

public struct StatsSummary: Codable, Equatable {
    public let totalRounds: Int?
    public let eighteenHoleRounds: Int?
    public let nineHoleRounds: Int?
    public let courseCount: Int?
    public let average18: Double?
    public let median18: Double?
    public let recent10Average: Double?
    public let bestScore: Int?
    public let worstScore: Int?
    public let handicapEstimate: Double?
    public let handicapTrend: String?
}

public struct StatsScoring: Codable, Equatable {
    public let outcomes: StatsOutcomes?
    public let scoreBands: [StatsScoreBand]
    public let byPar: [StatsByPar]
    public let putting: StatsPutting?

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        outcomes = try? c.decodeIfPresent(StatsOutcomes.self, forKey: .outcomes)
        scoreBands = (try? c.decodeIfPresent([StatsScoreBand].self, forKey: .scoreBands)) ?? []
        byPar = (try? c.decodeIfPresent([StatsByPar].self, forKey: .byPar)) ?? []
        putting = try? c.decodeIfPresent(StatsPutting.self, forKey: .putting)
    }

    private enum CodingKeys: String, CodingKey { case outcomes, scoreBands, byPar, putting }
}

public struct StatsOutcomes: Codable, Equatable {
    public let eagleOrBetter: Int?
    public let birdie: Int?
    public let par: Int?
    public let bogey: Int?
    public let doubleOrWorse: Int?
}

public struct StatsScoreBand: Codable, Equatable, Identifiable {
    public var id: String { label }
    public let label: String
    public let count: Int?
    public let roundIds: [String]?
}

public struct StatsByPar: Codable, Equatable, Identifiable {
    public var id: String { key ?? label ?? "\(par ?? 0)" }
    public let key: String?
    public let label: String?
    public let par: Int?
    public let holeCount: Int?
    public let averageScore: Double?
    public let averageToPar: Double?
    public let parOrBetterPct: Double?
    public let birdieOrBetterPct: Double?
    public let bogeyOrWorsePct: Double?
}

public struct StatsPutting: Codable, Equatable {
    public let totalPutts: Int?
    /// Per-HOLE average (~1.9). The 统计 KPI shows per-ROUND via `averagePuttsPerRound`.
    public let averagePutts: Double?
    /// Per-ROUND putts (~33) — what 场均推杆 should display.
    public let averagePuttsPerRound: Double?
    public let roundsWithPutts: Int?
    public let threePutts: Int?
}

public struct StatsTime: Codable, Equatable {
    public let byQuarter: [StatsPeriod]
    public let byMonth: [StatsPeriod]

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        byQuarter = (try? c.decodeIfPresent([StatsPeriod].self, forKey: .byQuarter)) ?? []
        byMonth = (try? c.decodeIfPresent([StatsPeriod].self, forKey: .byMonth)) ?? []
    }

    private enum CodingKeys: String, CodingKey { case byQuarter, byMonth }
}

public struct StatsPeriod: Codable, Equatable, Identifiable {
    public var id: String { key }
    public let key: String
    public let roundCount: Int?
    public let average18: Double?
    public let bestScore: Int?
    public let worstScore: Int?
    public let outcomes: StatsOutcomes?
}

public struct StatsCourse: Codable, Equatable, Identifiable {
    public var id: String { courseKey }
    public let courseKey: String
    public let courseName: String?
    public let roundCount: Int?
    public let average18: Double?
    public let bestScore: Int?
    public let worstScore: Int?
    public let averageDifferential: Double?
    public let recentRoundId: String?
    /// Per nine-combo breakdown (黑骑士 ~ A / ~ C/A …) shown when you drill into a course.
    public let nineBreakdown: [StatsNineBreakdown]?
    /// Every round at this course (newest→oldest) for the drill-in list: 时间·成绩, tap → 单场复盘.
    public let rounds: [StatsCourseRound]?
}

/// One round in a course's drill-in list (date + score; opens 单场复盘 on tap).
public struct StatsCourseRound: Codable, Equatable, Identifiable {
    public var id: String { roundId ?? "\(date)-\(score ?? 0)" }
    public let roundId: String?
    public let date: String
    public let score: Int?
    public let holesCompleted: Int?
    public let toPar: Int?
    public let nine: String?
}

public struct StatsNineBreakdown: Codable, Equatable, Identifiable {
    public var id: String { label }
    public let label: String
    public let roundCount: Int?
    public let average: Double?
    public let bestScore: Int?
    public let recentRoundId: String?
}

public struct StatsClub: Codable, Equatable, Identifiable {
    public var id: String { club }
    public let club: String
    public let sampleCount: Int?
    /// metres — the client shows 码.
    public let median: Double?
    public let p10: Double?
    public let p90: Double?
    public let max: Double?
    public let consistency: String?
    public let distanceTrend: String?
}

public struct StatsDiagnosis: Codable, Equatable {
    public let topIssue: String?
    public let issueTrends: [StatsIssueTrend]

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        topIssue = try? c.decodeIfPresent(String.self, forKey: .topIssue)
        issueTrends = (try? c.decodeIfPresent([StatsIssueTrend].self, forKey: .issueTrends)) ?? []
    }

    private enum CodingKeys: String, CodingKey { case topIssue, issueTrends }
}

public struct StatsIssueTrend: Codable, Equatable, Identifiable {
    public var id: String { issue }
    public let issue: String
    public let phase: String?
    public let direction: String?
    public let estimatedStrokesLost: Double?
    public let recentRatePerRound: Double?
    public let baselineRatePerRound: Double?
}
