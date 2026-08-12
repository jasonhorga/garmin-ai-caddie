import Foundation

/// Complete, filterable round archive from `GET /api/v2/history/rounds`.
/// This is intentionally independent from `LiveRoundPackage.recentHistory`, which is
/// only a small current-course convenience slice and must not power the player's archive.
public struct HistoryRoundsArchive: Codable, Equatable {
    public let total: Int
    public let groups: [HistoryMonthGroup]
    public let availableYears: [String]
    public let availableCourses: [HistoryCourseFilter]

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        total = (try? c.decode(Int.self, forKey: .total)) ?? 0
        groups = (try? c.decode([HistoryMonthGroup].self, forKey: .groups)) ?? []
        availableYears = (try? c.decode([String].self, forKey: .availableYears)) ?? []
        availableCourses = (try? c.decode([HistoryCourseFilter].self, forKey: .availableCourses)) ?? []
    }

    private enum CodingKeys: String, CodingKey { case total, groups, availableYears, availableCourses }
}

public struct HistoryMonthGroup: Codable, Equatable, Identifiable {
    public var id: String { key }
    public let key: String
    public let label: String
    public let count: Int
    public let average18: Double?
    public let bestScore: Int?
    public let rounds: [HistoryRoundCard]

    public init(key: String, label: String, count: Int, average18: Double?, bestScore: Int?, rounds: [HistoryRoundCard]) {
        self.key = key
        self.label = label
        self.count = count
        self.average18 = average18
        self.bestScore = bestScore
        self.rounds = rounds
    }
}

public struct HistoryCourseFilter: Codable, Equatable, Identifiable {
    public var id: String { key }
    public let key: String
    public let label: String
}

public struct HistoryRoundCard: Codable, Equatable, Identifiable {
    public let id: String
    public let date: String?
    public let courseName: String
    public let courseKey: String?
    public let holesCompleted: Int?
    public let score: Int?
    public let par: Int?
    public let toPar: Int?
    public let scoreStrip: [HistoryScoreCell]
    public let badges: [HistoryDataBadge]
    public let source: String?

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        date = try? c.decodeIfPresent(String.self, forKey: .date)
        courseName = (try? c.decode(String.self, forKey: .courseName)) ?? "未知球场"
        courseKey = try? c.decodeIfPresent(String.self, forKey: .courseKey)
        holesCompleted = try? c.decodeIfPresent(Int.self, forKey: .holesCompleted)
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        par = try? c.decodeIfPresent(Int.self, forKey: .par)
        toPar = try? c.decodeIfPresent(Int.self, forKey: .toPar)
        scoreStrip = (try? c.decode([HistoryScoreCell].self, forKey: .scoreStrip)) ?? []
        badges = (try? c.decode([HistoryDataBadge].self, forKey: .badges)) ?? []
        source = try? c.decodeIfPresent(String.self, forKey: .source)
    }

    private enum CodingKeys: String, CodingKey {
        case id, date, courseName, courseKey, holesCompleted, score, par, toPar, scoreStrip, badges, source
    }
}

public struct HistoryScoreCell: Codable, Equatable, Identifiable {
    public var id: Int { hole }
    public let hole: Int
    public let par: Int?
    public let score: Int?
    public let toPar: Int?
    public let className: String?
}

public struct HistoryDataBadge: Codable, Equatable, Identifiable {
    public var id: String { label }
    public let label: String
    public let state: String?
    public let value: String?
    public let reason: String?
}
