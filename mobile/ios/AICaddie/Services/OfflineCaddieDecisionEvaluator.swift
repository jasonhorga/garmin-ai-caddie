import Foundation

public final class OfflineCaddieDecisionEvaluator {
    public init() {}

    public func selectedOption(
        in seed: CaddieContextSeed,
        strategyMode: String?,
        requestedOptionId: String? = nil
    ) -> OfflineCaddieOption? {
        let requested = requestedOptionId?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
        let preferredId = requested.flatMap { id in
            seed.offlineOptions.first(where: {
                $0.optionId.trimmingCharacters(in: .whitespacesAndNewlines)
                    .lowercased()
                    .replacingOccurrences(of: "-", with: "_") == id
            })?.optionId
        } ?? preferredOptionId(for: strategyMode) ?? seed.selectedOfflineOptionId
        if let preferredId,
           let option = seed.offlineOptions.first(where: { $0.optionId == preferredId }) {
            return option
        }
        return seed.offlineOptions.first
    }

    public func makeDecision(
        seed: CaddieContextSeed,
        request: CaddieDecisionRequest,
        strategyMode: String?
    ) -> CaddieDecisionResponse? {
        let requestedOptionId: String? = {
            guard case .string(let raw) = request.context["requestedOptionId"] else { return nil }
            return raw
        }()
        guard let selected = selectedOption(
            in: seed,
            strategyMode: strategyMode,
            requestedOptionId: requestedOptionId
        ) else {
            return nil
        }
        let rawCanonicalSteps = canonicalPlanSteps(from: request.context) ?? canonicalPlanSteps(from: seed.context)
        let greenWindow = greenWindow(
            from: request.context["greenDistances"] ?? seed.context["greenDistances"]
        )
        let par = integer(request.context["par"] ?? seed.context["par"]) ?? 4
        let canonicalSteps = rawCanonicalSteps.map {
            boundedCanonicalSteps(
                $0,
                targetM: targetDistanceMetres(from: request.context),
                par: par
            )
        }
        let plans = routePlans(
            seed: seed,
            request: request,
            canonicalSteps: canonicalSteps,
            par: par,
            greenWindow: greenWindow
        )
        let optionRows = seed.offlineOptions.map { option in
            optionPayload(
                option,
                canonicalFirstStep: plans[option.optionId]?.first
            )
        }
        let sequenceRows = seed.offlineOptions.compactMap { option -> [String: JSONValue]? in
            guard let steps = plans[option.optionId], !steps.isEmpty else { return nil }
            if option.optionId == "stock", canonicalSteps != nil {
                return canonicalSequencePayload(steps: steps, selected: true)
            }
            return routeSequencePayload(steps: steps, option: option)
        }
        let selectedRow = optionPayload(
            selected,
            canonicalFirstStep: plans[selected.optionId]?.first
        )
        let selectedSequence: [String: JSONValue]? = {
            guard let steps = plans[selected.optionId], !steps.isEmpty else { return nil }
            if selected.optionId == "stock", canonicalSteps != nil {
                return canonicalSequencePayload(steps: steps, selected: true)
            }
            return routeSequencePayload(steps: steps, option: selected)
        }()
        let evidenceRefs = uniqueRefs([seed.sourceRef] + selected.sourceRefs + (selected.sampleRefs ?? []))
        let missingData = seed.missingData + (selected.missingData ?? [])
        let decisionId = offlineDecisionId(seed: seed, request: request, selected: selected)

        return CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2",
            decisionId: decisionId,
            sourceRef: seed.sourceRef,
            evidenceRefs: evidenceRefs,
            shotType: request.shotType,
            phase: phase(for: request.shotType),
            context: request.context,
            options: optionRows,
            selected: selectedRow,
            selectedOptionId: selected.optionId,
            selectedOption: selectedRow,
            sequences: sequenceRows,
            selectedSequence: selectedSequence,
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [
                "target": .string("offline_seed"),
                "note": .string("Use the cached plan and avoid escalating risk without fresh geometry, wind, or lie evidence."),
            ],
            evidence: offlineEvidence(seed: seed, selected: selected),
            confidence: confidencePayload(selected),
            missingData: missingData,
            auditCriteria: auditCriteria(seed: seed, selected: selected)
        )
    }

    private func preferredOptionId(for strategyMode: String?) -> String? {
        switch strategyMode {
        case "protect_score":
            return "safe"
        case "attack":
            return "attack"
        case "stock":
            return "stock"
        default:
            return nil
        }
    }

    private func optionPayload(
        _ option: OfflineCaddieOption,
        canonicalFirstStep: [String: JSONValue]? = nil
    ) -> [String: JSONValue] {
        let canonicalName = canonicalFirstStep.flatMap { string($0["clubName"] ?? $0["club"]) }
        let clubName = canonicalName ?? option.clubName
        let carry = canonicalFirstStep.flatMap { number($0["targetCarry_m"] ?? $0["targetCarryM"]) }
            ?? option.carryM
        var clubRow: [String: JSONValue] = [
            "clubName": .string(clubName),
            "median_m": .number(carry),
            "p10_m": jsonNumberOrNull(option.p10M),
            "p90_m": jsonNumberOrNull(option.p90M),
            "sampleSize": .number(Double(option.sampleSize ?? 0)),
            "confidence": .string(option.confidence ?? "low"),
            "sourceRefs": .array(option.sourceRefs.map { .string($0) }),
        ]
        if let canonicalFirstStep {
            clubRow["planIndex"] = canonicalFirstStep["planIndex"] ?? .number(0)
        }
        var row: [String: JSONValue] = [
            "id": .string(option.optionId),
            "label": .string(option.label),
            "clubName": .string(clubName),
            "carryM": .number(carry),
            "carry_m": .number(carry),
            "riskScore": .number(option.riskScore),
            "source": .string(option.source),
            "sourceRefs": .array(option.sourceRefs.map { .string($0) }),
            "clubRecommendation": .object([
                "source": canonicalFirstStep == nil ? .string(option.source) : .string("course_prep"),
                "clubs": .array([.object(clubRow)])
            ]),
        ]
        if let p10M = option.p10M {
            row["p10M"] = .number(p10M)
        }
        if let p90M = option.p90M {
            row["p90M"] = .number(p90M)
        }
        if let sampleSize = option.sampleSize {
            row["sampleSize"] = .number(Double(sampleSize))
        }
        if let confidence = option.confidence {
            row["confidence"] = .string(confidence)
        }
        if let coverage = option.coverage {
            row["coverage"] = coveragePayload(coverage)
        }
        if let sampleRefs = option.sampleRefs {
            row["sampleRefs"] = .array(sampleRefs.map { .string($0) })
        }
        if let missingData = option.missingData {
            row["missingData"] = .array(missingData.map { .object($0) })
        }
        return row
    }

    private func canonicalPlanSteps(
        from context: [String: JSONValue]
    ) -> [[String: JSONValue]]? {
        guard case .array(let values) = context["canonicalShotPlan"] else { return nil }
        let rows = values.compactMap { value -> [String: JSONValue]? in
            guard case .object(let row) = value,
                  let rawName = string(row["clubName"] ?? row["club"]),
                  !rawName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return row
        }
        return rows.isEmpty ? nil : rows
    }

    // MARK: - Deterministic package route fallback

    private struct LocalClubProfile {
        let name: String
        let carryM: Double
        let p10M: Double?
        let p90M: Double?
        let sampleSize: Int

        var key: String { Self.clubKey(name) }

        static func clubKey(_ value: String) -> String {
            let compact = value.lowercased().filter { $0.isLetter || $0.isNumber }
            switch compact {
            case "driver", "1d", "1w": return "1w"
            case "3wood", "3w": return "3w"
            case "5wood", "5w": return "5w"
            case "7wood", "7w": return "7w"
            default: return compact
            }
        }

        var isDriver: Bool { key == "1w" }
    }

    private func routePlans(
        seed: CaddieContextSeed,
        request: CaddieDecisionRequest,
        canonicalSteps: [[String: JSONValue]]?,
        par: Int,
        greenWindow: (front: Double, back: Double, routeBased: Bool)?
    ) -> [String: [[String: JSONValue]]] {
        var plans: [String: [[String: JSONValue]]] = [:]
        // Planned landings are clamped to this route end for display; GIR must not use the clamp.
        let routeEndM = targetDistanceMetres(from: request.context)
        if let canonicalSteps, !canonicalSteps.isEmpty {
            plans["stock"] = canonicalSteps
        }

        guard request.shotType == "tee",
              let targetM = targetDistanceMetres(from: request.context),
              targetM > 0 else {
            for (key, steps) in plans {
                plans[key] = trimAtGreenWindow(steps, par: par, greenWindow: greenWindow, routeEndM: routeEndM).steps
            }
            return plans
        }
        let profiles = localProfiles(from: request.context["clubProfiles"] ?? seed.context["clubProfiles"])
        guard !profiles.isEmpty else {
            for (key, steps) in plans {
                plans[key] = trimAtGreenWindow(steps, par: par, greenWindow: greenWindow, routeEndM: routeEndM).steps
            }
            return plans
        }

        let water = waterIntervals(from: request.context)
        for option in seed.offlineOptions {
            if option.optionId == "stock", plans["stock"] != nil { continue }
            guard let steps = fallbackSteps(
                for: option,
                profiles: profiles,
                targetM: targetM,
                par: par,
                water: water
            ), !steps.isEmpty else { continue }
            plans[option.optionId] = trimAtGreenWindow(
                steps,
                par: par,
                greenWindow: greenWindow,
                routeEndM: routeEndM
            ).steps
        }
        // A malformed/old seed can have no explicit stock option but still carry a usable bag.
        if plans["stock"] == nil,
           let stock = seed.offlineOptions.first(where: { $0.optionId == "stock" }),
           let steps = fallbackSteps(for: stock, profiles: profiles, targetM: targetM, par: par, water: water) {
            plans["stock"] = trimAtGreenWindow(steps, par: par, greenWindow: greenWindow, routeEndM: routeEndM).steps
        }
        if !plans.isEmpty {
            for (key, steps) in plans {
                plans[key] = trimAtGreenWindow(steps, par: par, greenWindow: greenWindow, routeEndM: routeEndM).steps
            }
        }
        return materialAlternatives(plans, profiles: profiles, targetM: targetM, par: par, water: water)
    }

    private func targetDistanceMetres(from context: [String: JSONValue]) -> Double? {
        for key in ["distanceToPin_m", "remainingToPin_m", "holeRemaining_m", "canonicalPlanRouteLength_m"] {
            if let value = number(context[key]), value.isFinite, value > 0, value <= 1000 {
                return value
            }
        }
        if let yards = number(context["yards"]), yards.isFinite, yards > 0, yards <= 1100 {
            return yards / 1.09361
        }
        return nil
    }

    private func greenWindow(from value: JSONValue?) -> (front: Double, back: Double, routeBased: Bool)? {
        guard case .object(let row) = value else { return nil }
        let straightFront = number(row["frontM"] ?? row["front_m"] ?? row["greenFrontM"])
        let straightBack = number(row["backM"] ?? row["back_m"] ?? row["greenBackM"])
        let routeFront = number(
            row["frontRouteM"] ?? row["front_route_m"] ?? row["greenFrontRouteM"]
        )
        let routeBack = number(
            row["backRouteM"] ?? row["back_route_m"] ?? row["greenBackRouteM"]
        )
        let routeBased = routeFront != nil && routeBack != nil
        let front = routeBased ? routeFront : straightFront
        let back = routeBased ? routeBack : straightBack
        guard let front, let back,
              front.isFinite,
              back.isFinite,
              front > 0,
              back > 0 else {
            return nil
        }
        return (
            min(front, back),
            max(front, back),
            routeBased
        )
    }

    private func trimAtGreenWindow(
        _ source: [[String: JSONValue]],
        par: Int,
        greenWindow: (front: Double, back: Double, routeBased: Bool)?,
        routeEndM: Double? = nil
    ) -> (steps: [[String: JSONValue]], gir: Bool) {
        guard par >= 3,
              let greenWindow,
              !source.isEmpty else {
            return (source, false)
        }
        let shotLimit = max(1, par - 2)
        var cumulative = 0.0
        var previousOffset = 0.0
        for (index, raw) in source.enumerated() {
            let carry = number(raw["targetCarry_m"] ?? raw["targetCarryM"] ?? raw["median_m"]) ?? 0
            guard carry > 0 else { continue }
            cumulative += carry
            let displayOffset = number(raw["routeOffset_m"] ?? raw["routeOffsetM"] ?? raw["landing_m"] ?? raw["landingM"])
                ?? cumulative
            // The planners clamp the landing to the route end so the map line stops at the flag.
            // A median landing past the back edge must not be pulled onto the green and called GIR.
            var offset = displayOffset
            let projected = previousOffset + carry
            if let routeEndM, displayOffset >= routeEndM - 0.05, projected > displayOffset + 0.05 {
                offset = projected
            }
            previousOffset = offset
            guard index + 1 <= shotLimit else { break }
            guard offset >= greenWindow.front, offset <= greenWindow.back + 8 else { continue }
            var trimmed = Array(source.prefix(index + 1))
            guard !trimmed.isEmpty else { return (source, false) }
            var final = trimmed[trimmed.count - 1]
            final["role"] = .string("scoring")
            final["expectedRemaining_m"] = .number(0)
            final["expectedRemainingM"] = .number(0)
            final["routeOffset_m"] = .number(displayOffset)
            final["landing_m"] = .number(displayOffset)
            final["greenInRegulation"] = .bool(true)
            final["shotsToGreen"] = .number(Double(index + 1))
            var window: [String: JSONValue] = [
                "frontM": .number(greenWindow.front),
                "backM": .number(greenWindow.back),
            ]
            if greenWindow.routeBased {
                window["frontRouteM"] = .number(greenWindow.front)
                window["backRouteM"] = .number(greenWindow.back)
            }
            final["girWindow"] = .object(window)
            trimmed[trimmed.count - 1] = final
            return (trimmed, true)
        }
        return (source, false)
    }

    private func boundedCanonicalSteps(
        _ source: [[String: JSONValue]],
        targetM: Double?,
        par: Int
    ) -> [[String: JSONValue]] {
        guard let targetM, targetM > 0 else { return source }
        var travelled = 0.0
        var result: [[String: JSONValue]] = []
        for (index, raw) in source.enumerated() {
            if !result.isEmpty, travelled >= targetM - 20 { break }
            let carry = number(raw["targetCarry_m"] ?? raw["targetCarryM"]) ?? 0
            guard carry > 0 else { continue }
            let next = travelled + carry
            if next > targetM + 20 { break }
            var row = raw
            let endpoint = par == 3 ? targetM : min(targetM, next)
            row["routeOffset_m"] = .number(endpoint)
            row["landing_m"] = .number(endpoint)
            row["expectedRemaining_m"] = .number(par == 3 ? 0 : max(0, targetM - endpoint))
            if par == 3 || index == source.count - 1 || endpoint >= targetM - 20 {
                row["role"] = .string("scoring")
            }
            row["planIndex"] = row["planIndex"] ?? .number(Double(result.count))
            result.append(row)
            travelled = next
            if par == 3 || endpoint >= targetM - 20 { break }
        }
        return result.isEmpty ? source : result
    }

    private func localProfiles(from value: JSONValue?) -> [LocalClubProfile] {
        let rows: [[String: JSONValue]]
        switch value {
        case .array(let values):
            rows = values.compactMap { value in
                guard case .object(let row) = value else { return nil }
                return row
            }
        case .object(let values):
            rows = values.values.compactMap { value in
                guard case .object(let row) = value else { return nil }
                return row
            }
        default:
            rows = []
        }
        var byKey: [String: LocalClubProfile] = [:]
        for row in rows {
            guard let name = string(row["clubName"] ?? row["name"]),
                  let carry = number(row["median_m"] ?? row["median"] ?? row["carryM"]),
                  carry.isFinite, carry > 0 else { continue }
            let profile = LocalClubProfile(
                name: name,
                carryM: carry,
                p10M: number(row["p10_m"] ?? row["p10M"] ?? row["p10"]),
                p90M: number(row["p90_m"] ?? row["p90M"] ?? row["p90"]),
                sampleSize: integer(row["sampleSize"]) ?? 0
            )
            let key = profile.key
            if let existing = byKey[key], existing.sampleSize >= profile.sampleSize { continue }
            byKey[key] = profile
        }
        return byKey.values.sorted { $0.carryM > $1.carryM }
    }

    private func fallbackSteps(
        for option: OfflineCaddieOption,
        profiles: [LocalClubProfile],
        targetM: Double,
        par: Int,
        water: [(front: Double, back: Double)] = []
    ) -> [[String: JSONValue]]? {
        guard let first = profiles.first(where: { $0.key == LocalClubProfile.clubKey(option.clubName) })
            ?? profiles.min(by: { abs($0.carryM - option.carryM) < abs($1.carryM - option.carryM) }) else {
            return nil
        }

        if par == 3 {
            return [makeRouteStep(
                first,
                index: 0,
                role: "scoring",
                routeOffsetM: targetM,
                // A Par 3 fallback is one scoring shot to the pin.  The measured carry remains
                // the club fact, but the route endpoint is the green even when carry and nominal
                // pin distance differ by a few metres.
                expectedRemainingM: 0,
                planSource: "offline_bag_fallback"
            )]
        }

        guard let chain = plannedChain(first: first, profiles: profiles, targetM: targetM, water: water) else {
            return nil
        }
        var steps: [[String: JSONValue]] = []
        var travelled = 0.0
        for (index, club) in chain.clubs.enumerated() {
            let remaining = max(0, targetM - travelled)
            let isLastWindow = remaining <= Self.scoringWindowM
            travelled += club.carryM
            let reachesTarget = travelled >= targetM - Self.scoringWindowM
            let offset = min(targetM, travelled)
            let role = index == 0 ? "tee" : (reachesTarget || isLastWindow ? "scoring" : "position")
            steps.append(makeRouteStep(
                club,
                index: index,
                role: role,
                routeOffsetM: offset,
                expectedRemainingM: max(0, targetM - offset),
                planSource: "offline_bag_fallback"
            ))
        }
        return steps.isEmpty ? nil : steps
    }

    // MARK: - Whole-hole sequence planning
    //
    // The same contract as the server planner (`decision.py` `_sequence_tail` /
    // `_whole_hole_sequence_key`): a seed option fixes only the tee club; the rest of the hole is
    // chosen as one complete chain scored by its leave, each club's own carry distribution
    // (p10-p90 spread; the green-bound stroke weighs most), extra strokes and repeats. A chain never
    // plays a club more than `maxCarryIncreaseM` longer than its tee club after it (no short iron,
    // then wood), its longer clubs come first, and no landing is inside a factual water carry.

    private static let scoringWindowM = 20.0
    private static let maxOvershootM = 10.0
    private static let extraStepCostM = 25.0
    private static let repeatedClubPenaltyM = 12.0
    private static let maxCarryIncreaseM = 15.0
    private static let waterBufferM = 8.0
    private static let maxTailSteps = 4
    /// An alternative must lower the whole chain's modelled risk by at least this much to be 稳妥,
    /// or shorten the green-bound stroke by `materialApproachGainM` to be 进攻.
    private static let materialRiskMarginM = 2.0
    private static let materialApproachGainM = 10.0
    /// A Par 3 alternative is a club that actually plays to the green.
    private static let par3CarryWindowM = 15.0

    private struct PlannedChain {
        let clubs: [LocalClubProfile]
        let leaveM: Double
    }

    private func stabilityCost(_ profile: LocalClubProfile, scoringShot: Bool) -> Double {
        let spread: Double = {
            if let p10 = profile.p10M, let p90 = profile.p90M, p90 > p10 { return p90 - p10 }
            return max(12, profile.carryM * 0.15)
        }()
        let evidence = min(1, Double(max(0, profile.sampleSize)) / 20)
        return spread * (scoringShot ? 0.55 : 0.10) + (1 - evidence) * (scoringShot ? 8 : 3)
    }

    private func chainRisk(_ clubs: [LocalClubProfile], leaveM: Double) -> Double {
        clubs.enumerated().reduce(abs(leaveM)) { total, item in
            total + stabilityCost(item.element, scoringShot: item.offset == clubs.count - 1)
        }
    }

    private func landsInWater(_ offsetM: Double, water: [(front: Double, back: Double)]) -> Bool {
        water.contains { offsetM > $0.front - Self.waterBufferM && offsetM < $0.back + Self.waterBufferM }
    }

    private func waterIntervals(from context: [String: JSONValue]) -> [(front: Double, back: Double)] {
        guard case .array(let rows)? = context["hazardWaterCarry_m"] else { return [] }
        return rows.compactMap { row in
            guard case .array(let pair) = row, pair.count >= 2,
                  let a = number(pair[0]), let b = number(pair[1]), a >= 0, b >= 0 else { return nil }
            return (min(a, b), max(a, b))
        }
    }

    private func plannedChain(
        first: LocalClubProfile,
        profiles: [LocalClubProfile],
        targetM: Double,
        water: [(front: Double, back: Double)]
    ) -> PlannedChain? {
        guard !landsInWater(min(first.carryM, targetM), water: water) else { return nil }
        let tail = bestTail(after: first, profiles: profiles, remainingM: targetM - first.carryM, water: water)
        let clubs = [first] + tail
        return PlannedChain(clubs: clubs, leaveM: targetM - clubs.reduce(0) { $0 + $1.carryM })
    }

    private func bestTail(
        after first: LocalClubProfile,
        profiles: [LocalClubProfile],
        remainingM: Double,
        water: [(front: Double, back: Double)]
    ) -> [LocalClubProfile] {
        guard remainingM > Self.scoringWindowM else { return [] }
        let playable = profiles
            .filter { !$0.isDriver && $0.carryM <= first.carryM + Self.maxCarryIncreaseM }
            .sorted { $0.carryM > $1.carryM }
        guard let longest = playable.first?.carryM, longest > 0 else { return [] }
        let minimumSteps = max(1, Int(((remainingM - Self.scoringWindowM) / longest).rounded(.up)))
        let maximumSteps = min(Self.maxTailSteps, minimumSteps + 1)
        guard minimumSteps <= maximumSteps else { return [] }
        var best: (key: [Double], clubs: [LocalClubProfile])?
        for count in minimumSteps...maximumSteps {
            forEachCombination(count: count, of: playable.count) { indexes in
                // Ascending indexes are descending carries: longer clubs first.
                let clubs = indexes.map { playable[$0] }
                var position = first.carryM
                for club in clubs {
                    position += club.carryM
                    if landsInWater(position, water: water) { return }
                }
                let leave = remainingM - clubs.reduce(0) { $0 + $1.carryM }
                let overshoot = max(0, -leave)
                let repeats = zip(clubs, clubs.dropFirst()).filter { $0.0.key == $0.1.key }.count
                var cost = abs(leave)
                    + Double(repeats) * Self.repeatedClubPenaltyM
                    + Double(count - minimumSteps) * Self.extraStepCostM
                for (index, club) in clubs.enumerated() {
                    cost += stabilityCost(club, scoringShot: index == clubs.count - 1)
                }
                let samples = clubs.reduce(0) { $0 + $1.sampleSize }
                let key: [Double] = [
                    overshoot > Self.maxOvershootM ? 1 : 0,
                    leave > Self.scoringWindowM ? 1 : 0,
                    cost,
                    overshoot,
                    -Double(samples),
                ]
                if best.map({ key.lexicographicallyPrecedes($0.key) }) ?? true {
                    best = (key, clubs)
                }
            }
        }
        return best?.clubs ?? []
    }

    /// Every multiset of `count` indexes below `n`, as non-decreasing index arrays.
    private func forEachCombination(count: Int, of n: Int, _ body: ([Int]) -> Void) {
        guard count > 0, n > 0 else { return }
        var indexes = Array(repeating: 0, count: count)
        while true {
            body(indexes)
            var position = count - 1
            while position >= 0 && indexes[position] == n - 1 { position -= 1 }
            if position < 0 { return }
            indexes[position] += 1
            for next in (position + 1)..<count { indexes[next] = indexes[position] }
        }
    }

    /// One plan's whole-hole facts: strokes, whether it reaches the scoring window, the green-bound
    /// stroke's length and the chain's modelled risk from the player's own club distributions.
    private func chainSummary(
        _ steps: [[String: JSONValue]],
        profiles: [LocalClubProfile],
        targetM: Double
    ) -> (strokes: Int, complete: Bool, approachM: Double, risk: Double) {
        var clubs: [LocalClubProfile] = []
        var offsets: [Double] = []
        var travelled = 0.0
        for row in steps {
            let carry = number(row["targetCarry_m"] ?? row["targetCarryM"]) ?? 0
            travelled += carry
            offsets.append(number(row["routeOffset_m"] ?? row["routeOffsetM"] ?? row["landing_m"] ?? row["landingM"]) ?? travelled)
            let name = string(row["clubName"] ?? row["club"]) ?? "-"
            let key = LocalClubProfile.clubKey(name)
            clubs.append(profiles.first { $0.key == key }
                ?? LocalClubProfile(name: name, carryM: carry, p10M: nil, p90M: nil, sampleSize: 0))
        }
        let last = steps.last
        let leave = last.flatMap { number($0["expectedRemaining_m"] ?? $0["expectedRemainingM"]) }
            ?? max(0, targetM - travelled)
        let gir: Bool = {
            if case .bool(true)? = last?["greenInRegulation"] { return true }
            return false
        }()
        let previous = offsets.count >= 2 ? offsets[offsets.count - 2] : 0
        return (
            steps.count,
            gir || leave <= Self.scoringWindowM,
            max(0, targetM - previous),
            chainRisk(clubs, leaveM: leave)
        )
    }

    /// Keep only alternatives that are whole-hole strategies: complete; on a Par 4/5 reaching the
    /// green in regulation whenever any plan can (a lay-up is offered only when no plan can, with
    /// an auditable reason); 稳妥 lowering the whole chain's modelled risk without adding strokes;
    /// 进攻 shortening the green-bound stroke without adding strokes; a Par 3 alternative playing
    /// to the green.
    private func materialAlternatives(
        _ plans: [String: [[String: JSONValue]]],
        profiles: [LocalClubProfile],
        targetM: Double,
        par: Int,
        water: [(front: Double, back: Double)]
    ) -> [String: [[String: JSONValue]]] {
        var result = plans
        if par == 3 {
            for (id, steps) in plans where id != "stock" {
                guard let carry = steps.first.flatMap({ number($0["targetCarry_m"] ?? $0["targetCarryM"]) }),
                      abs(carry - targetM) <= Self.par3CarryWindowM else {
                    result[id] = nil
                    continue
                }
            }
            return result
        }
        let girLimit = max(1, par - 2)
        let summaries = plans.mapValues { chainSummary($0, profiles: profiles, targetM: targetM) }
        let girReachable = summaries.values.contains { $0.complete && $0.strokes <= girLimit }
        let layupReason: String = {
            if let longest = profiles.first, landsInWater(min(longest.carryM, targetM), water: water) {
                return "water_carry"
            }
            return "beyond_reach"
        }()
        let stock = summaries["stock"]
        for (id, steps) in plans {
            guard let summary = summaries[id] else { continue }
            if summary.strokes > girLimit {
                if girReachable, id != "stock" {
                    result[id] = nil
                    continue
                }
                if !girReachable {
                    result[id] = steps.map { row in
                        var row = row
                        row["layupReason"] = .string(layupReason)
                        return row
                    }
                }
            }
            guard id != "stock" else { continue }
            guard summary.complete else {
                result[id] = nil
                continue
            }
            guard let stock, stock.complete else { continue }
            let addsStrokes = summary.strokes > stock.strokes
            switch id {
            case "safe":
                if addsStrokes || summary.risk > stock.risk - Self.materialRiskMarginM { result[id] = nil }
            case "attack":
                if addsStrokes || summary.approachM > stock.approachM - Self.materialApproachGainM { result[id] = nil }
            default:
                if addsStrokes { result[id] = nil }
            }
        }
        return result
    }

    private func makeRouteStep(
        _ profile: LocalClubProfile,
        index: Int,
        role: String,
        routeOffsetM: Double,
        expectedRemainingM: Double,
        planSource: String
    ) -> [String: JSONValue] {
        var row: [String: JSONValue] = [
            "clubName": .string(profile.name),
            "role": .string(role),
            "targetCarry_m": .number(profile.carryM),
            "routeOffset_m": .number(routeOffsetM),
            "landing_m": .number(routeOffsetM),
            "expectedRemaining_m": .number(expectedRemainingM),
            "planIndex": .number(Double(index)),
            "planVersion": .string("ai-caddie-shot-plan-v1"),
            "planSource": .string(planSource),
            "sampleSize": .number(Double(profile.sampleSize)),
        ]
        if let p10M = profile.p10M { row["p10_m"] = .number(p10M) }
        if let p90M = profile.p90M { row["p90_m"] = .number(p90M) }
        return row
    }

    private func routeSequencePayload(
        steps: [[String: JSONValue]],
        option: OfflineCaddieOption
    ) -> [String: JSONValue] {
        let label = steps.compactMap { string($0["clubName"] ?? $0["club"]) }.joined(separator: "-")
        let expected = steps.last.flatMap { number($0["expectedRemaining_m"] ?? $0["expectedRemainingM"]) } ?? 0
        let total = steps.reduce(0) {
            $0 + (number($1["targetCarry_m"] ?? $1["targetCarryM"]) ?? 0)
        }
        var payload: [String: JSONValue] = [
            "id": .string(option.optionId),
            "label": .string(label),
            "strategyLabel": .string(option.label),
            "clubs": .array(steps.map { .object($0) }),
            "totalPlannedCarry_m": .number(total),
            "expectedRemaining_m": .number(expected),
            "riskScore": .number(option.riskScore),
            "planSource": .string("offline_bag_fallback"),
            "completion": .string(expected > 20 ? "replan_required" : "scoring_window"),
        ]
        if let reason = steps.first?["layupReason"] {
            payload["layupReason"] = reason
        }
        if let final = steps.last,
           case .bool(true) = final["greenInRegulation"] {
            payload["greenInRegulation"] = .bool(true)
            payload["girWindow"] = final["girWindow"] ?? .null
            payload["shotsToGreen"] = final["shotsToGreen"] ?? .number(Double(steps.count))
            payload["completion"] = .string("scoring_window")
        }
        return payload
    }

    private func canonicalSequencePayload(
        steps: [[String: JSONValue]],
        selected: Bool
    ) -> [String: JSONValue]? {
        guard selected, !steps.isEmpty else { return nil }
        let clubs: [JSONValue] = steps.enumerated().compactMap { index, raw in
            guard let name = string(raw["clubName"] ?? raw["club"]) else { return nil }
            var row: [String: JSONValue] = [
                "clubName": .string(name),
                "role": raw["role"] ?? .string(index == 0 ? "advance" : "position"),
                "planIndex": raw["planIndex"] ?? .number(Double(index)),
            ]
            for key in [
                "targetCarry_m", "targetCarryM", "routeOffset_m", "routeOffsetM",
                "landing_m", "landingM", "expectedRemaining_m", "expectedRemainingM",
                "planVersion", "planSource", "greenInRegulation", "girWindow", "shotsToGreen",
            ] {
                if let value = raw[key] { row[key] = value }
            }
            if steps.count == 1, row["role"] == .string("advance") {
                row["role"] = .string("scoring")
            }
            return .object(row)
        }
        guard !clubs.isEmpty else { return nil }
        let label = steps.compactMap { string($0["clubName"] ?? $0["club"]) }.joined(separator: "-")
        var payload: [String: JSONValue] = [
            "id": .string("stock"),
            "label": .string(label),
            "strategyLabel": .string("推荐"),
            "clubs": .array(clubs),
            "planSource": .string("course_prep"),
            "planVersion": .string("ai-caddie-shot-plan-v1"),
            "completion": .string("scoring_window"),
        ]
        if let final = steps.last,
           case .bool(true) = final["greenInRegulation"] {
            payload["greenInRegulation"] = .bool(true)
            payload["girWindow"] = final["girWindow"] ?? .null
            payload["shotsToGreen"] = final["shotsToGreen"] ?? .number(Double(steps.count))
            payload["completion"] = .string("scoring_window")
        }
        return payload
    }

    private func string(_ value: JSONValue?) -> String? {
        guard case .string(let raw) = value else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func number(_ value: JSONValue?) -> Double? {
        guard case .number(let raw) = value, raw.isFinite else { return nil }
        return raw
    }

    private func integer(_ value: JSONValue?) -> Int? {
        guard let raw = number(value) else { return nil }
        return Int(raw.rounded())
    }

    private func offlineEvidence(seed: CaddieContextSeed, selected: OfflineCaddieOption) -> [[String: JSONValue]] {
        seed.evidence + [
            [
                "label": .string("offline_caddie"),
                "value": .string("cached_decision"),
                "sourceRef": .string(seed.sourceRef),
            ],
            [
                "label": .string("offline_option"),
                "value": .string(selected.optionId),
                "clubName": .string(selected.clubName),
                "confidence": .string(selected.confidence ?? "low"),
            ],
        ]
    }

    private func confidencePayload(_ option: OfflineCaddieOption) -> [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "level": .string(option.confidence ?? "low"),
            "source": .string("offline_package_seed"),
            "sampleSize": .number(Double(option.sampleSize ?? 0)),
        ]
        if let coverage = option.coverage {
            payload["coverage"] = coveragePayload(coverage)
        }
        return payload
    }

    private func auditCriteria(seed: CaddieContextSeed, selected: OfflineCaddieOption) -> [[String: JSONValue]] {
        [
            [
                "label": .string("offline_selected_option"),
                "targetOptionId": .string(selected.optionId),
                "sourceRef": .string(seed.sourceRef),
            ],
            [
                "label": .string("club_profile_confidence"),
                "clubName": .string(selected.clubName),
                "confidence": .string(selected.confidence ?? "low"),
                "sampleSize": .number(Double(selected.sampleSize ?? 0)),
            ],
        ]
    }

    private func coveragePayload(_ coverage: OfflineOptionCoverage) -> JSONValue {
        .object([
            "ready": .number(Double(coverage.ready)),
            "total": .number(Double(coverage.total)),
            "pct": .number(coverage.pct),
        ])
    }

    private func jsonNumberOrNull(_ value: Double?) -> JSONValue {
        guard let value else {
            return .null
        }
        return .number(value)
    }

    private func uniqueRefs(_ refs: [String]) -> [String] {
        var seen: Set<String> = []
        var output: [String] = []
        for ref in refs {
            let trimmed = ref.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, !seen.contains(trimmed) else {
                continue
            }
            seen.insert(trimmed)
            output.append(trimmed)
        }
        return output
    }

    private func phase(for shotType: String) -> String {
        switch shotType {
        case "tee":
            return "Tee"
        case "recovery":
            return "Recovery"
        default:
            return "Approach"
        }
    }

    private func offlineDecisionId(
        seed: CaddieContextSeed,
        request: CaddieDecisionRequest,
        selected: OfflineCaddieOption
    ) -> String {
        let raw = "offline-\(seed.sourceRef)-\(request.shotType)-\(selected.optionId)"
        return raw
            .replacingOccurrences(of: ":", with: "-")
            .replacingOccurrences(of: " ", with: "-")
    }
}
