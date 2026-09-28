import AICaddieDomain
import Foundation

/// Builds the shared ``NineLoopPlan`` for a live round from what the phone knows: the venue's
/// nine-hole loops (course options, in the course's own A / B / C order) and the player's usual
/// pairings — the last pairing chosen on this phone first, else the most recent pairing in the
/// round history.
enum NineLoopTurn {
    static func loop(_ option: MobileCourseOption) -> NineLoop {
        NineLoop(
            id: String(option.globalId),
            name: option.resolvedSegmentLabel ?? option.segmentDisplayTitle
        )
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
        let loops = siblings.isEmpty ? [front] : siblings
        guard loops.contains(where: { $0.globalId == front.globalId }) else { return nil }
        let course = NineLoopCourse(
            id: front.venueName ?? String(front.globalId),
            loops: loops.map(loop),
            usualPairs: usualPairs(remembered: remembered, history: history, loopIds: Set(loops.map(\.globalId)))
        )
        guard var plan = NineLoopPlan(course: course, first: String(front.globalId)) else { return nil }
        plan.beginFirstLoop()
        plan.reachTurn()
        return plan
    }
}
