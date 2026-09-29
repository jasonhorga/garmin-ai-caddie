import AICaddieDomain
import Foundation

/// Builds the shared ``NineLoopPlan`` for a live round from what the phone knows: the venue's
/// nine-hole loops (course options, in the course's own A / B / C order) and the player's usual
/// pairings — the last pairing chosen on this phone first, else the most recent pairing in the
/// round history.
enum NineLoopTurn {
    /// A loop named by the course's own factual loop label (A / 东 / 湖景场). A loop without one is
    /// not offered: the turn never invents a "9 洞组" name for a choice.
    static func loop(_ option: MobileCourseOption) -> NineLoop? {
        guard let label = option.resolvedSegmentLabel else { return nil }
        return NineLoop(id: String(option.globalId), name: label)
    }

    /// The loop just played is always part of the plan (it can be played again). Without a loop
    /// label it keeps the course's own name, which is factual, rather than a synthesized one.
    static func firstLoop(_ option: MobileCourseOption) -> NineLoop {
        loop(option) ?? NineLoop(id: String(option.globalId), name: option.localizedName)
    }

    /// The course options the live round resolves its loops from: the network catalogue, plus
    /// every installed template it does not list (offline, or discovery failed). Downloaded
    /// templates keep their factual venue and loop labels, so the turn works offline.
    static func loopCatalogue(network: [MobileCourseOption], downloaded: [MobileCourseOption]) -> [MobileCourseOption] {
        let listed = Set(network.map(\.globalId))
        return network + downloaded.filter { !listed.contains($0.globalId) }
    }

    /// The venue's nine-hole loops for `active` (itself included), in loop-label order.
    static func siblings(of active: MobileCourseOption, in catalogue: [MobileCourseOption]) -> [MobileCourseOption] {
        guard let venue = active.venueName else { return [] }
        var seen = Set<Int>()
        return catalogue
            .filter { ($0.venueName ?? "") == venue && $0.resolvedHoles == 9 && seen.insert($0.globalId).inserted }
            .sorted { ($0.resolvedSegmentLabel ?? "~~") < ($1.resolvedSegmentLabel ?? "~~") }
    }

    /// Round hole where the second loop starts (the first hole after the first nine).
    static func firstHoleOfSecondLoop(_ holes: [Int]) -> Int? {
        holes.filter { $0 > 9 }.min()
    }

    /// Front loop id → back loop id. `remembered` wins; history is newest first.
    static func usualPairs(remembered: [Int: Int], history: [HistoryRoundCard], loopIds: Set<Int>) -> [String: String] {
        var pairs: [String: String] = [:]
        for card in history {
            guard let front = card.globalId, let back = card.backGlobalId,
                  loopIds.contains(front), loopIds.contains(back),
                  pairs[String(front)] == nil else { continue }
            pairs[String(front)] = String(back)
        }
        for (front, back) in remembered where loopIds.contains(front) && loopIds.contains(back) {
            pairs[String(front)] = String(back)
        }
        return pairs
    }

    /// The turn plan for a round now at the end of its first loop, or nil when the round is not a
    /// single loop of a known venue.
    static func plan(
        front: MobileCourseOption,
        siblings: [MobileCourseOption],
        remembered: [Int: Int],
        history: [HistoryRoundCard]
    ) -> NineLoopPlan? {
        guard siblings.isEmpty || siblings.contains(where: { $0.globalId == front.globalId }) else { return nil }
        let options = siblings.isEmpty ? [front] : siblings
        let loops = options.compactMap { option -> NineLoop? in
            option.globalId == front.globalId ? firstLoop(option) : loop(option)
        }
        let course = NineLoopCourse(
            id: front.venueName ?? String(front.globalId),
            loops: loops,
            usualPairs: usualPairs(remembered: remembered, history: history, loopIds: Set(loops.compactMap { Int($0.id) }))
        )
        guard var plan = NineLoopPlan(course: course, first: String(front.globalId)) else { return nil }
        plan.beginFirstLoop()
        plan.reachTurn()
        return plan
    }
}
