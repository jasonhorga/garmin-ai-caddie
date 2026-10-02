import Foundation

/// B5b 球场 (README §9, `stats.html` 6): the course page's facts from one course row plus the
/// history-wide `scoring.loops` / `nineCombos`, matched by the course's own `loopKeys`.
enum ResultsCoursePresentation {
    /// A hole's topo image identity, parsed from a `gid:<globalId>:<span>` loop key (a loop without
    /// a Garmin id — `course:` keys — has no topo).
    struct HoleRef: Equatable {
        let globalId: Int
        let localHole: Int
    }

    static func globalId(fromLoopKey key: String) -> Int? {
        let parts = key.split(separator: ":")
        guard parts.count == 3, parts[0] == "gid" else { return nil }
        return Int(parts[1])
    }

    /// The backdrop: hole 1 of the first loop with a Garmin id (10 for a 10–18 loop).
    static func backdrop(_ course: StatsCourse) -> HoleRef? {
        for key in course.loopKeys ?? [] {
            guard let gid = globalId(fromLoopKey: key) else { continue }
            return HoleRef(globalId: gid, localHole: key.hasSuffix(":10-18") ? 10 : 1)
        }
        return nil
    }

    struct Dot: Equatable, Identifiable {
        var id: String { roundId ?? "\(index)" }
        /// 0 = oldest.
        let index: Int
        let roundId: String?
        let score: Int
        let isBest: Bool
    }

    /// One dot per complete 18-hole round, oldest first; the best one marked (ties: the newest).
    static func dots(_ course: StatsCourse) -> [Dot] {
        let rounds = (course.rounds ?? []).filter { ($0.holesCompleted ?? 18) == 18 && $0.score != nil }.reversed()
        let scores = rounds.compactMap(\.score)
        let best = scores.min()
        let bestIndex = best.flatMap { value in scores.lastIndex(of: value) }
        return rounds.enumerated().map { index, round in
            Dot(index: index, roundId: round.roundId, score: round.score ?? 0, isBest: index == bestIndex)
        }
    }

    struct HardHole: Equatable, Identifiable {
        var id: String { "\(loopKey):\(hole)" }
        let loopKey: String
        let loopLabel: String
        let hole: Int
        let par: Int?
        let averageToPar: Double
        let samples: Int
        let topo: HoleRef?
        /// "+0.92".
        var overPar: String { String(format: "%+.2f", averageToPar) }
    }

    /// The course's three hardest holes: its own loops' holes with at least 2 samples, by average
    /// over par (ties: more samples, then loop and hole order).
    static func hardestHoles(_ course: StatsCourse, loops: [StatsLoop], limit: Int = 3) -> [HardHole] {
        let keys = Set(course.loopKeys ?? [])
        let candidates = loops.filter { keys.contains($0.loopKey) }.flatMap { loop in
            loop.holes.compactMap { hole -> HardHole? in
                guard let average = hole.averageToPar, let samples = hole.samples, samples >= 2 else { return nil }
                return HardHole(
                    loopKey: loop.loopKey,
                    loopLabel: loopName(loop.label, venue: course.courseName),
                    hole: hole.hole,
                    par: hole.par,
                    averageToPar: average,
                    samples: samples,
                    topo: globalId(fromLoopKey: loop.loopKey).map { HoleRef(globalId: $0, localHole: hole.hole) }
                )
            }
        }
        return Array(candidates.sorted {
            if $0.averageToPar != $1.averageToPar { return $0.averageToPar > $1.averageToPar }
            if $0.samples != $1.samples { return $0.samples > $1.samples }
            return ($0.loopKey, $0.hole) < ($1.loopKey, $1.hole)
        }.prefix(limit))
    }

    /// A loop label without the venue prefix ("Black Knight B" -> "B") when it repeats the course.
    static func loopName(_ label: String?, venue: String?) -> String {
        let label = (label ?? "").trimmingCharacters(in: .whitespaces)
        if let venue, !venue.isEmpty, label.hasPrefix(venue) {
            let rest = label.dropFirst(venue.count).trimmingCharacters(in: .whitespaces)
            if !rest.isEmpty { return rest }
        }
        return label.isEmpty ? "—" : label
    }

    struct Combo: Equatable, Identifiable {
        var id: String { "\(frontKey)>\(backKey)" }
        let frontKey: String
        let backKey: String
        /// "B → C · 6 次 · 85.8".
        let text: String
        let rounds: Int
    }

    /// The course's front -> back combinations, most played first (ties: lower average, then keys).
    static func combos(_ course: StatsCourse, combos: [StatsNineCombo]) -> [Combo] {
        let keys = Set(course.loopKeys ?? [])
        return combos.compactMap { combo -> Combo? in
            guard let front = combo.frontKey, let back = combo.backKey, keys.contains(front), keys.contains(back) else {
                return nil
            }
            let rounds = combo.rounds ?? 0
            let average = combo.average.map { String(format: "%.1f", $0) } ?? "—"
            return Combo(
                frontKey: front,
                backKey: back,
                text: "\(loopName(combo.front, venue: course.courseName)) → \(loopName(combo.back, venue: course.courseName)) · \(rounds) 次 · \(average)",
                rounds: rounds
            )
        }
        .sorted { ($1.rounds, $0.frontKey, $0.backKey) < ($0.rounds, $1.frontKey, $1.backKey) }
    }

    /// "全部 6 种组合 · 只打 9 洞 3 次" (the 9-hole part only when the course has any).
    static func allCombosLabel(_ course: StatsCourse, count: Int) -> String {
        let nine = course.nineOnlyRounds ?? 0
        return nine > 0 ? "全部 \(count) 种组合 · 只打 9 洞 \(nine) 次" : "全部 \(count) 种组合"
    }

    /// "打过 12 次 · 最近 9 月 21 日" (rounds newest first; the date part only when it parses).
    static func subtitle(_ course: StatsCourse) -> String {
        var parts = ["打过 \(course.roundCount ?? course.rounds?.count ?? 0) 次"]
        if let date = course.rounds?.first?.date, let day = monthDay(date) { parts.append("最近 \(day)") }
        return parts.joined(separator: " · ")
    }

    /// "2026-09-21…" -> "9 月 21 日".
    static func monthDay(_ raw: String) -> String? {
        let parts = raw.prefix(10).split(separator: "-")
        guard parts.count == 3, let month = Int(parts[1]), let day = Int(parts[2]) else { return nil }
        return "\(month) 月 \(day) 日"
    }

    struct HoleVisit: Equatable, Identifiable {
        var id: String { "\(round.id)#\(displayHole)" }
        let round: StatsCourseRound
        /// The hole's number on that round's scorecard (front 1–9, back 10–18).
        let displayHole: Int
    }

    /// Every round here that played `hole` (newest first), with the hole's number in that round:
    /// a loop hole keeps its place within the nine, on whichever side the round played the loop.
    static func visits(_ course: StatsCourse, hole: HardHole) -> [HoleVisit] {
        let withinNine = (hole.hole - 1) % 9
        return (course.rounds ?? []).compactMap { round in
            guard let ref = round.roundId, !ref.isEmpty else { return nil }
            if round.frontLoopKey == hole.loopKey { return HoleVisit(round: round, displayHole: withinNine + 1) }
            if round.backLoopKey == hole.loopKey { return HoleVisit(round: round, displayHole: withinNine + 10) }
            return nil
        }
    }
}
