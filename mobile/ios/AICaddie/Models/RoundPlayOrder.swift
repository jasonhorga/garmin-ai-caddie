import Foundation

/// The order a round is played in when it starts at the first stroke's hole (design 2026-10-23 §2):
/// the start hole to the last hole of the package's table, then its first hole up to the one before
/// the start — 5 → 5…18, 1…4. A two-tee or shotgun start is the same rule, and a 27-hole
/// combination follows its own package table (round holes in loop order), never physical numbers.
enum RoundPlayOrder {
    /// `roundHoles` in package order; a start hole that is nil or not in the table keeps it as is.
    static func holes(_ roundHoles: [Int], startingAt startHole: Int?) -> [Int] {
        guard let startHole, let index = roundHoles.firstIndex(of: startHole) else { return roundHoles }
        return Array(roundHoles[index...]) + Array(roundHoles[..<index])
    }

    /// Rotate the complete round table. Physical front/back loops are one 18-hole round, and a
    /// second nine-hole loop is represented by round holes 10–18, so neither case should revisit
    /// the first nine before the round is complete.
    static func holes(_ roundHoles: [Int], startingAt startHole: Int?, loops: [RoundLoop]) -> [Int] {
        // Two `all` entries are two sequential nine-hole loops. When play starts part-way through
        // the first loop, the holes before that start have already been played; continue into the
        // second loop instead of rotating those completed holes back onto the end.
        if loops.count == 2, loops.allSatisfy({ $0.half == "all" }),
           let startHole,
           let startIndex = loops.firstIndex(where: { $0.contains(roundHole: startHole) }) {
            let grouped = loops.map { loop in roundHoles.filter { loop.contains(roundHole: $0) } }
            guard grouped.flatMap({ $0 }).count == roundHoles.count,
                  let withinLoop = grouped[startIndex].firstIndex(of: startHole) else {
                return holes(roundHoles, startingAt: startHole)
            }
            return Array(grouped[startIndex][withinLoop...]) + grouped.dropFirst(startIndex + 1).flatMap { $0 }
        }
        return holes(roundHoles, startingAt: startHole)
    }

    /// The hole after `hole` in play order; nil after the last one (the round is complete).
    static func next(after hole: Int, in roundHoles: [Int], startingAt startHole: Int?) -> Int? {
        let ordered = holes(roundHoles, startingAt: startHole)
        guard let index = ordered.firstIndex(of: hole), ordered.indices.contains(index + 1) else { return nil }
        return ordered[index + 1]
    }

    static func next(after hole: Int, in roundHoles: [Int], startingAt startHole: Int?, loops: [RoundLoop]) -> Int? {
        let ordered = holes(roundHoles, startingAt: startHole, loops: loops)
        guard let index = ordered.firstIndex(of: hole), ordered.indices.contains(index + 1) else { return nil }
        return ordered[index + 1]
    }
}

/// The hole screen's top bar (design §1–§2): before the first stroke it says where the player is
/// and that nothing is recorded; once that stroke started the round it says the round is recording.
enum HoleScreenRoundBanner: Equatable {
    case prep
    case atCourse
    case readyToStart(courseHole: Int)
    case recording(courseHole: Int)

    static func resolve(
        roundStarted: Bool,
        location: CurrentHoleLocation,
        courseHoleNumber: (Int) -> Int,
        currentCourseHole: Int
    ) -> Self {
        if roundStarted { return .recording(courseHole: currentCourseHole) }
        switch location {
        case .onHole(let hole): return .readyToStart(courseHole: courseHoleNumber(hole))
        case .atCourse: return .atCourse
        case .awayFromCourse, .unknown: return .prep
        }
    }

    var text: String {
        switch self {
        case .prep: return "没到场，先备战·不记录"
        case .atCourse: return "不在球洞范围·不记录"
        case .readyToStart(let hole): return "第 \(hole) 洞 · 记第一杆即开打"
        case .recording(let hole): return "第 \(hole) 洞 · 正在记录"
        }
    }

    var isRecording: Bool {
        if case .recording = self { return true }
        return false
    }

    /// The one-line notice for a stroke recorded before the round started in no hole's area.
    static func notStartedNotice(_ location: CurrentHoleLocation) -> String {
        switch location {
        case .atCourse: return "练习场、会所里记杆不算开打，这一杆没有记录"
        case .awayFromCourse, .unknown, .onHole: return "没到场，备战不记录"
        }
    }
}
