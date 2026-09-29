import AICaddieDomain
import Foundation

/// Builds the shared ``NineLoopPlan`` for a live round from what the phone knows: the venue's
/// nine-hole loops (course options, in the course's own A / B / C order) or the two halves of an
/// 18-hole course (前九 / 后九), and the player's usual pairings — the last pairing chosen on this
/// phone first, else the most recent pairing in the round history.
///
/// A loop's id is its request entry `"{globalId}:{half}"` (B4b-2): `"31795:all"` for a nine-hole
/// loop, `"41825:front"` / `"41825:back"` for a half. ``entry(_:)`` turns it back into the
/// `loops=` unit.
enum NineLoopTurn {
    static func loopId(_ entry: RoundLoopEntry) -> String {
        RoundLoopEntry.loopKey([entry])
    }

    static func entry(_ loopId: String) -> RoundLoopEntry? {
        guard let entries = RoundLoopEntry.entries(loopKey: loopId), entries.count == 1 else { return nil }
        return entries[0]
    }

    /// A loop named by the course's own factual loop label (A / 东 / 湖景场). A loop without one is
    /// not offered: the turn never invents a "9 洞组" name for a choice.
    static func loop(_ option: MobileCourseOption) -> NineLoop? {
        guard let label = option.resolvedSegmentLabel else { return nil }
        return NineLoop(id: loopId(RoundLoopEntry(globalId: option.globalId, half: "all")), name: label)
    }

    /// The loop just played is always part of the plan (it can be played again). Without a loop
    /// label it keeps the course's own name, which is factual, rather than a synthesized one.
    static func firstLoop(_ option: MobileCourseOption) -> NineLoop {
        loop(option)
            ?? NineLoop(id: loopId(RoundLoopEntry(globalId: option.globalId, half: "all")), name: option.localizedName)
    }

    /// The two halves of an 18-hole course, in course order.
    static func halves(globalId: Int) -> [NineLoop] {
        [
            NineLoop(id: loopId(RoundLoopEntry(globalId: globalId, half: "front")), name: "前九"),
            NineLoop(id: loopId(RoundLoopEntry(globalId: globalId, half: "back")), name: "后九"),
        ]
    }

    /// "前九" / "后九" for a half, the loop's own name for a nine-hole loop (scorecard, turn).
    static func loopName(_ loop: RoundLoop, catalogue: [MobileCourseOption]) -> String {
        switch loop.half {
        case "front": return "前九"
        case "back": return "后九"
        default:
            guard let option = catalogue.first(where: { $0.globalId == loop.globalId }) else { return "9 洞" }
            return firstLoop(option).displayName
        }
    }

    /// The course options the live round resolves its loops from: the network catalogue, plus
    /// every installed template it does not list (offline, or discovery failed). Downloaded
    /// templates keep their factual venue and loop labels, so the turn works offline.
    ///
    /// The network row stays authoritative for the same id, except when it is coarser than the
    /// installed template: a whole-course / unlabeled row (the CourseView-unavailable shape) never
    /// masks an installed nine-hole loop with a factual label.
    static func loopCatalogue(network: [MobileCourseOption], downloaded: [MobileCourseOption]) -> [MobileCourseOption] {
        let installed = Dictionary(downloaded.map { ($0.globalId, $0) }, uniquingKeysWith: { first, _ in first })
        let merged = network.map { row -> MobileCourseOption in
            guard let local = installed[row.globalId], isFactualLoop(local), !isFactualLoop(row) else { return row }
            return local
        }
        let listed = Set(network.map(\.globalId))
        return merged + downloaded.filter { !listed.contains($0.globalId) }
    }

    /// A nine-hole loop with the course's own loop label.
    static func isFactualLoop(_ option: MobileCourseOption) -> Bool {
        option.resolvedHoles == 9 && option.resolvedSegmentLabel != nil
    }

    /// The venue's nine-hole loops for `active` (itself included), in loop-label order.
    static func siblings(of active: MobileCourseOption, in catalogue: [MobileCourseOption]) -> [MobileCourseOption] {
        guard let venue = active.venueName else { return [] }
        var seen = Set<Int>()
        return catalogue
            .filter { ($0.venueName ?? "") == venue && $0.resolvedHoles == 9 && seen.insert($0.globalId).inserted }
            .sorted { ($0.resolvedSegmentLabel ?? "~~") < ($1.resolvedSegmentLabel ?? "~~") }
    }

    /// The live hole's turn decision (`CurrentHoleView`): a plan when the round is still one loop —
    /// a half of an 18-hole course, or a nine-hole loop of a venue the catalogue knows (network
    /// or installed) — else nil and the round summary follows.
    static func planAtEndOfFirstLoop(
        package: LiveRoundPackage,
        catalogue: [MobileCourseOption],
        remembered: [String: String],
        history: [HistoryRoundCard]
    ) -> NineLoopPlan? {
        guard package.roundLoops.count == 1, let first = package.roundLoops.first else { return nil }
        if first.isCourseHalf {
            let loops = halves(globalId: first.globalId)
            let ids = Set(loops.map(\.id))
            let course = NineLoopCourse(
                id: String(first.globalId),
                loops: loops,
                usualPairs: remembered.filter { ids.contains($0.key) && ids.contains($0.value) }
            )
            guard var plan = NineLoopPlan(course: course, first: loopId(first.entry)) else { return nil }
            plan.beginFirstLoop()
            plan.reachTurn()
            return plan
        }
        guard let active = catalogue.first(where: { $0.globalId == first.globalId }),
              active.resolvedHoles == 9 else { return nil }
        return plan(
            front: active,
            siblings: siblings(of: active, in: catalogue),
            remembered: remembered,
            history: history
        )
    }

    /// First loop id → second loop id. `remembered` wins; history is newest first.
    static func usualPairs(remembered: [String: String], history: [HistoryRoundCard], loopIds: Set<String>) -> [String: String] {
        var pairs: [String: String] = [:]
        for card in history {
            guard let front = card.globalId, let back = card.backGlobalId else { continue }
            let frontId = loopId(RoundLoopEntry(globalId: front, half: "all"))
            let backId = loopId(RoundLoopEntry(globalId: back, half: "all"))
            guard loopIds.contains(frontId), loopIds.contains(backId),
                  pairs[frontId] == nil else { continue }
            pairs[frontId] = backId
        }
        for (front, back) in remembered where loopIds.contains(front) && loopIds.contains(back) {
            pairs[front] = back
        }
        return pairs
    }

    /// The turn plan for a round now at the end of its first loop, or nil when the round is not a
    /// single loop of a known venue.
    static func plan(
        front: MobileCourseOption,
        siblings: [MobileCourseOption],
        remembered: [String: String],
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
            usualPairs: usualPairs(remembered: remembered, history: history, loopIds: Set(loops.map(\.id)))
        )
        guard var plan = NineLoopPlan(course: course, first: firstLoop(front).id) else { return nil }
        plan.beginFirstLoop()
        plan.reachTurn()
        return plan
    }
}
