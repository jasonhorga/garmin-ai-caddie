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

    /// The live hole's turn decision (`CurrentHoleView`): a plan when the round is still one
    /// nine-hole loop — a loop of a venue the catalogue knows (network or installed), or one half
    /// of an 18-hole course — else nil and the round summary follows.
    static func planAtEndOfFirstLoop(
        package: LiveRoundPackage,
        catalogue: [MobileCourseOption],
        remembered: [Int: Int],
        history: [HistoryRoundCard]
    ) -> NineLoopPlan? {
        guard package.holes.count <= 9 else { return nil }
        let active = catalogue.first(where: { $0.globalId == package.course.globalId })
        // An 18-hole course started on one half: 前九 / 后九 are its two loops.
        if let nine = package.nine?.lowercased(), nine == "front" || nine == "back",
           active.map({ $0.resolvedHoles == 18 }) ?? true {
            return halvesPlan(globalId: package.course.globalId, startedOn: nine)
        }
        guard let active, active.resolvedHoles == 9 else { return nil }
        return plan(
            front: active,
            siblings: siblings(of: active, in: catalogue),
            remembered: remembered,
            history: history
        )
    }

    /// Round hole where the second loop starts (the first hole after the first nine).
    static func firstHoleOfSecondLoop(_ holes: [Int]) -> Int? {
        holes.filter { $0 > 9 }.min()
    }

    // MARK: 18-hole course: 前九 / 后九 are its two loops (README §8)

    /// A two-loop 18-hole course uses the same flow: the round starts on one half (`nine` "front" /
    /// "back", holes 1–9 / 10–18) and the other half, the same half again or stop after nine is
    /// chosen at the turn. The halves are loops `"{globalId}:front"` / `"{globalId}:back"`.
    static func halfLoops(globalId: Int) -> [NineLoop] {
        [
            NineLoop(id: "\(globalId):front", name: "前九"),
            NineLoop(id: "\(globalId):back", name: "后九"),
        ]
    }

    /// "front" / "back" for a half-loop id, else nil.
    static func half(ofLoopId id: String) -> String? {
        let parts = id.split(separator: ":")
        guard parts.count == 2, Int(parts[0]) != nil else { return nil }
        let half = String(parts[1])
        return half == "front" || half == "back" ? half : nil
    }

    /// The turn plan for an 18-hole course round started on one half. The usual second loop is
    /// the other half.
    static func halvesPlan(globalId: Int, startedOn nine: String) -> NineLoopPlan? {
        guard nine == "front" || nine == "back" else { return nil }
        let front = "\(globalId):front"
        let back = "\(globalId):back"
        let course = NineLoopCourse(
            id: String(globalId),
            loops: halfLoops(globalId: globalId),
            usualPairs: [front: back, back: front]
        )
        guard var plan = NineLoopPlan(course: course, first: nine == "front" ? front : back) else { return nil }
        plan.beginFirstLoop()
        plan.reachTurn()
        return plan
    }

    /// The loops the turn offers. A round started on 后九 already uses round holes 10–18, so 后九
    /// cannot be added again as a second loop; every other plan offers all of its loops.
    static func turnChoices(_ plan: NineLoopPlan) -> [NineLoop] {
        guard half(ofLoopId: plan.first) == "back" else { return plan.course.loops }
        return plan.course.loops.filter { half(ofLoopId: $0.id) != "back" }
    }

    /// First round hole of the other half: 后九 starts at 10, 前九 (after a 后九 start) at 1.
    static func firstHoleOfOtherHalf(startedOn nine: String) -> Int {
        nine == "back" ? 1 : 10
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
