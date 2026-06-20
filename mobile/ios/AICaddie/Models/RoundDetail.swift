import Foundation

/// Single-round 复盘 payload from `GET /api/v2/history/rounds/{ref}` (backend
/// `build_history_round_detail`). Scorecard-first: hole-by-hole score + the phase summary, with
/// graceful missing-data rows so the screen is never blank (the user's "复盘点进去没数据" fix).
/// Decode is tolerant — Garmin scorecards are messy, so a single odd field never fails the round.
public struct RoundDetail: Codable, Equatable {
    public let roundRef: String
    public let found: Bool
    public let title: String?
    public let round: RoundDetailSummary?
    public let scorecard: [RoundDetailHole]
    public let phaseSummary: [RoundDetailPhase]
    public let missingData: [RoundDetailMissing]

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        roundRef = (try? c.decode(String.self, forKey: .roundRef)) ?? ""
        found = (try? c.decode(Bool.self, forKey: .found)) ?? false
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        round = try? c.decodeIfPresent(RoundDetailSummary.self, forKey: .round)
        scorecard = (try? c.decodeIfPresent([RoundDetailHole].self, forKey: .scorecard)) ?? []
        phaseSummary = (try? c.decodeIfPresent([RoundDetailPhase].self, forKey: .phaseSummary)) ?? []
        missingData = (try? c.decodeIfPresent([RoundDetailMissing].self, forKey: .missingData)) ?? []
    }

    public init(roundRef: String, found: Bool, title: String? = nil, round: RoundDetailSummary? = nil,
                scorecard: [RoundDetailHole] = [], phaseSummary: [RoundDetailPhase] = [],
                missingData: [RoundDetailMissing] = []) {
        self.roundRef = roundRef
        self.found = found
        self.title = title
        self.round = round
        self.scorecard = scorecard
        self.phaseSummary = phaseSummary
        self.missingData = missingData
    }

    private enum CodingKeys: String, CodingKey {
        case roundRef, found, title, round, scorecard, phaseSummary, missingData
    }
}

public struct RoundDetailSummary: Codable, Equatable {
    public let courseName: String?
    public let date: String?
    public let score: Int?
    public let par: Int?
    public let toPar: Int?
    public let holesCompleted: Int?
    public let holesScored: Int?
    public let courseHoles: Int?
    public let confidence: String?
}

public struct RoundDetailHole: Codable, Equatable, Identifiable {
    public var id: Int { hole }
    public let hole: Int
    public let par: Int?
    public let score: Int?
    public let toPar: Int?
    /// eagle / birdie / par / bogey / double / missing — drives the score color.
    public let className: String?
    public let putts: Int?
    public let gir: Bool?
    public let fairway: String?
    public let status: String?

    public init(from decoder: Decoder) throws {
        // Tolerant: Garmin gir/fairway are sometimes null / odd types — never fail the whole round.
        let c = try decoder.container(keyedBy: CodingKeys.self)
        hole = (try? c.decode(Int.self, forKey: .hole)) ?? 0
        par = try? c.decodeIfPresent(Int.self, forKey: .par)
        score = try? c.decodeIfPresent(Int.self, forKey: .score)
        toPar = try? c.decodeIfPresent(Int.self, forKey: .toPar)
        className = try? c.decodeIfPresent(String.self, forKey: .className)
        putts = try? c.decodeIfPresent(Int.self, forKey: .putts)
        gir = try? c.decodeIfPresent(Bool.self, forKey: .gir)
        fairway = try? c.decodeIfPresent(String.self, forKey: .fairway)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
    }

    public init(hole: Int, par: Int? = nil, score: Int? = nil, toPar: Int? = nil, className: String? = nil,
                putts: Int? = nil, gir: Bool? = nil, fairway: String? = nil, status: String? = nil) {
        self.hole = hole
        self.par = par
        self.score = score
        self.toPar = toPar
        self.className = className
        self.putts = putts
        self.gir = gir
        self.fairway = fairway
        self.status = status
    }

    private enum CodingKeys: String, CodingKey {
        case hole, par, score, toPar, className, putts, gir, fairway, status
    }
}

public struct RoundDetailPhase: Codable, Equatable, Identifiable {
    public var id: String { phase }
    public let phase: String
    public let state: String?
    public let primary: String?
}

public struct RoundDetailMissing: Codable, Equatable, Identifiable {
    public var id: String { label }
    public let label: String
    public let state: String?
    public let reason: String?
}
