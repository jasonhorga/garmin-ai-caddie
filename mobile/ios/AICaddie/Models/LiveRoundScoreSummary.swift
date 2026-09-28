import Foundation

/// One recorded hole as the scorecard and the round summary read it.
struct LiveHoleScore: Equatable {
    let hole: Int
    let par: Int
    let score: Int
    let putts: Int
    let penalties: Int
    let fairway: String?
    /// B0c source (`watch_detected` / `phone_shots` / `default` / `manual_edit` / legacy).
    let source: String?

    /// An untouched default preselection says nothing about putting or reaching the green.
    var isUntouchedDefault: Bool { source == LiveScoreSource.default.rawValue }

    /// GIR is never recorded; it is estimated from the total and the putts (README §2): the green
    /// was reached in regulation when the strokes before the first putt are at most Par − 2.
    var estimatedGIR: Bool { score - putts <= par - 2 }
}

/// Totals shared by the scorecard (计分卡) and the round summary (本场汇总). Holes are in play order;
/// the first nine are OUT and the next nine IN.
struct LiveRoundScoreSummary: Equatable {
    let holes: [LiveHoleScore]

    var strokes: Int { holes.reduce(0) { $0 + $1.score } }
    var par: Int { holes.reduce(0) { $0 + $1.par } }
    var toPar: Int? { holes.isEmpty ? nil : strokes - par }

    /// Cumulative to-par after each recorded hole, in play order (the scorecard trend line).
    var cumulativeToPar: [Int] {
        var running = 0
        return holes.map { hole in
            running += hole.score - hole.par
            return running
        }
    }

    var fairwaysHit: Int { holes.filter { $0.par != 3 && $0.fairway == LiveFairwayResult.hit.rawValue }.count }
    var fairwaysRecorded: Int { holes.filter { $0.par != 3 && $0.fairway != nil }.count }

    /// Putting and GIR skip untouched default holes (B0c), so a par saved without a look cannot
    /// inflate either.
    private var measuredHoles: [LiveHoleScore] { holes.filter { !$0.isUntouchedDefault } }
    var putts: Int? {
        let measured = measuredHoles
        return measured.isEmpty ? nil : measured.reduce(0) { $0 + $1.putts }
    }
    var puttHoles: Int { measuredHoles.count }
    var girHit: Int { measuredHoles.filter(\.estimatedGIR).count }
    var girRecorded: Int { measuredHoles.count }

    var penalties: Int { holes.reduce(0) { $0 + $1.penalties } }

    static func percent(_ part: Int, of whole: Int) -> Int? {
        guard whole > 0 else { return nil }
        return Int((Double(part) / Double(whole) * 100).rounded())
    }

    /// "+4", "E", "-2".
    static func toParText(_ value: Int) -> String {
        if value == 0 { return "E" }
        return value > 0 ? "+\(value)" : "\(value)"
    }
}
