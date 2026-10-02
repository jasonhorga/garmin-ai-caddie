import Foundation

/// One deterministic route authority for live phone, map, and Watch surfaces.
///
/// A live response can contain a useful single-club option while a downloaded CoursePrep row
/// contains the complete opening chain.  Treating those payloads as interchangeable was the
/// source of the refresh jump (for example `1W -> 3H` becoming `3H -> 6I -> 58`).  This helper
/// keeps complete routes, gives the installed CoursePrep chain precedence for the normal route,
/// and only exposes a remote alternative when it is itself a complete, physically different line.
enum LiveCaddieRouteAuthority {
    static func resolve(
        installed: CaddiePlanSequence?,
        online: CaddieDecisionResponse?,
        offline: CaddieDecisionResponse?,
        par: Int,
        shotType: String,
        authority: ClubBagAuthority = .current
    ) -> [CaddiePlanSequence] {
        // The installed chain is the first-frame visual authority even when it is an explicit
        // CoursePrep prefix (`completion=replan_required`). Keeping that prefix prevents a refresh
        // from replacing `1W -> 3H` with an unrelated sparse planner chain. A bare Par 4/5 tee card
        // is filtered below; a measured multi-leg prefix remains useful while its next lie is
        // being re-planned.
        let installedRoute: CaddiePlanSequence? = {
            // The local evaluator rejected the installed chain (water / OB): never restore it.
            guard offline?.isLocalNoRoute != true else { return nil }
            guard let installed, !installed.steps.isEmpty else { return nil }
            // Keep a useful CoursePrep prefix, but never expose a bare Par 4/5 tee club as a
            // complete route.  A single-club route is retained only when its final step carries
            // the explicit factual GIR marker (for example a genuinely drivable Par 4).
            if !isDisplayable(installed, par: par, shotType: shotType) {
                return nil
            }
            return installed
        }()
        // A club taken out of 球包 never comes back through a decision made before the change.
        let onlineRoutes = completeDistinctRoutes(
            CaddiePlanPresentation.distinctSequences(from: online ?? emptyDecision),
            par: par,
            shotType: shotType
        ).filter { authority.rosterAllows($0.steps.map(\.clubName)) }
        let offlineRoutes = completeDistinctRoutes(
            CaddiePlanPresentation.distinctSequences(from: offline ?? emptyDecision),
            par: par,
            shotType: shotType
        ).filter { authority.rosterAllows($0.steps.map(\.clubName)) }

        var result: [CaddiePlanSequence] = []
        if let installedRoute {
            result.append(installedRoute)
        }

        // An online response with no structured route is a sparse card, not a replacement for the
        // installed route. Prefer online only for alternatives with a real chain. If there is no
        // CoursePrep route yet, the complete online route becomes the first authority.
        let candidates = onlineRoutes + offlineRoutes
        for route in candidates {
            if result.contains(where: { sameVisibleRoute($0, route) }) { continue }
            result.append(route)
        }

        // A stale remote route can be the only payload during a cold deferred-hole frame. If the
        // offline evaluator has a complete route, it is preferable to a single bare option and is
        // already deterministic from the installed bag and hole facts.
        return deduplicated(result)
    }

    /// Identity of the installed CoursePrep chain when it is presented as a route.
    static let installedRouteId = "installed-course-plan"

    /// The installed CoursePrep chain as the first-frame route, shared by live play and 备战.
    /// Only a tee shot has an installed chain. The chain stops at the first landing inside the
    /// factual green window within the Par - 2 budget (GIR), a final green-bound leg is a scoring
    /// leg, and a true pin endpoint lands on the route end. `fallbackRouteEndM` is used only when
    /// the prep row has no route length (live: the current distance to the pin).
    static func installedRoute(
        prep: CoursePrepHole?,
        par: Int,
        shotType: String,
        fallbackRouteEndM: Double?,
        authority: ClubBagAuthority = .current
    ) -> CaddiePlanSequence? {
        guard shotType.caseInsensitiveCompare("tee") == .orderedSame else { return nil }
        // A chain prepared before a 球包 change (a removed club, another typed carry) is stale: its
        // offsets, landings and leaves were planned with the old carries. Drop it; the live
        // decision re-plans from the effective profiles.
        let prepLegs = (prep?.steps ?? []).map { (club: $0.clubName ?? $0.club ?? "", carryM: $0.targetCarryM) }
        guard authority.planMatches(prepLegs) else { return nil }
        let prepSteps: [CoursePrepStep] = {
            let source = prep?.steps ?? []
            guard par >= 3,
                  let green = prep?.greenDistances,
                  green.available,
                  let front = green.frontM,
                  let back = green.backM,
                  front.isFinite,
                  back.isFinite else { return source }
            let lower = min(front, back)
            let upper = max(front, back) + 8.0
            let shotLimit = max(1, par - 2)
            var cumulative = 0.0
            var trimmed: [CoursePrepStep] = []
            for (index, step) in source.enumerated() {
                let carry = step.targetCarryM ?? 0
                cumulative += carry
                let offset = step.routeOffsetM ?? step.landingM ?? cumulative
                trimmed.append(step)
                if index + 1 <= shotLimit, offset >= lower, offset <= upper { break }
            }
            return trimmed
        }()
        let routeEnd: Double = prep?.resolvedMapOverlay?.ln ?? prep?.routeLenM ?? fallbackRouteEndM ?? 0
        let steps = prepSteps.enumerated().compactMap { index, step -> CaddiePlanSequenceStep? in
            let club = (step.clubName ?? step.club ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !club.isEmpty, club != "-" else { return nil }
            let isDirectPar3 = par == 3
            let isLast = index == max(0, prepSteps.count - 1)
            let remaining = step.expectedRemainingM
            let actualOffset = step.routeOffsetM ?? step.landingM
            let reachesPin = remaining.map { $0 <= 20 } == true
                || (routeEnd > 0 && (actualOffset ?? 0) >= routeEnd - 20)
            let suppliedRole = step.role?.trimmingCharacters(in: .whitespacesAndNewlines)
            let inferredRole: String = {
                if isDirectPar3 { return "scoring" }
                // CoursePrep producers before the shot-plan contract sometimes labelled the
                // final approach as `advance`/`position`.  A last step whose factual leave is in
                // the scoring window is the green-bound leg regardless of that stale label; keep
                // the endpoint and map arc attached to the flag.
                if isLast && reachesPin { return "scoring" }
                if let suppliedRole, !suppliedRole.isEmpty { return suppliedRole }
                return index == 0 ? shotType : "position"
            }()
            let isScoring = inferredRole.caseInsensitiveCompare("scoring") == .orderedSame
                || inferredRole.caseInsensitiveCompare("approach") == .orderedSame
            let girLanding = isGreenWindowLanding(
                offsetM: actualOffset,
                shotIndex: index,
                par: par,
                greenDistances: prep?.greenDistances
            )
            let pinEndpoint = isDirectPar3 || (
                isScoring
                    && isLast
                    && shouldTargetPin(
                        offsetM: actualOffset,
                        role: inferredRole,
                        shotIndex: index,
                        routeEndM: routeEnd,
                        par: par,
                        greenDistances: prep?.greenDistances
                    )
            )
            return CaddiePlanSequenceStep(
                id: "prep-\(step.planIndex ?? index)-\(club)",
                role: inferredRole,
                clubName: club,
                targetCarryM: step.targetCarryM,
                expectedRemainingM: pinEndpoint || girLanding ? 0 : step.expectedRemainingM,
                sampleSize: nil,
                confidence: nil,
                sourceRefs: [],
                routeOffsetM: pinEndpoint ? routeEnd : actualOffset,
                landingM: pinEndpoint ? routeEnd : actualOffset,
                planIndex: step.planIndex ?? index,
                greenInRegulation: girLanding,
                shotsToGreen: girLanding ? index + 1 : nil
            )
        }
        guard !steps.isEmpty else { return nil }
        return CaddiePlanSequence(
            id: installedRouteId,
            label: "本洞路线",
            expectedRemainingM: steps.last?.expectedRemainingM,
            riskScore: nil,
            confidence: nil,
            coverageText: nil,
            sourceRefs: [],
            steps: steps
        )
    }

    /// A factual front/back green window is a valid GIR destination. The map must not turn that
    /// landing into a flag-targeted arc merely because the route's last semantic role is scoring.
    static func isGreenWindowLanding(
        offsetM: Double?,
        shotIndex: Int,
        par: Int,
        greenDistances: CoursePrepGreenDistances?
    ) -> Bool {
        guard par >= 3,
              shotIndex + 1 <= max(1, par - 2),
              let offsetM,
              offsetM.isFinite,
              let green = greenDistances,
              green.available,
              let front = green.frontM,
              let back = green.backM,
              front.isFinite,
              back.isFinite else {
            return false
        }
        let lower = min(front, back)
        let upper = max(front, back) + 8.0
        return offsetM >= lower && offsetM <= upper
    }

    static func shouldTargetPin(
        offsetM: Double?,
        role: String,
        shotIndex: Int,
        routeEndM: Double,
        par: Int,
        greenDistances: CoursePrepGreenDistances?
    ) -> Bool {
        let normalizedRole = role.lowercased()
        guard normalizedRole == "scoring" || normalizedRole == "approach" else { return false }
        if isGreenWindowLanding(offsetM: offsetM, shotIndex: shotIndex, par: par, greenDistances: greenDistances) {
            return false
        }
        guard let offsetM, offsetM.isFinite, routeEndM > 0 else {
            // Legacy payloads without a cumulative station have no way to distinguish a pin
            // endpoint, so retain the historical scoring fallback for those payloads only.
            return true
        }
        return offsetM >= routeEndM - 20.0
    }

    /// The visible first route of a hole (`CurrentHoleView.reconcileCaddieRoutes`). An explicit
    /// player selection wins; otherwise the retained route is kept stable across refreshes, a
    /// sparse retained route is upgraded once to the installed CoursePrep chain, and a fresh hole
    /// (nothing retained, nothing chosen) leads with the first resolved route. `incoming` must not
    /// be empty.
    /// One hole's published routes after a new result. With `vetoInstalled` (the local evaluator
    /// found no safe route) the installed chain is dropped from the incoming, published and
    /// retained routes alike; if nothing else remains the hole publishes no route at all.
    static func reconciled(
        incoming: [CaddiePlanSequence],
        existing: [CaddiePlanSequence],
        installed: CaddiePlanSequence?,
        retained: CaddiePlanSequence?,
        explicitSelectionKey: String?,
        vetoInstalled: Bool,
        authority: ClubBagAuthority = .current
    ) -> (first: CaddiePlanSequence, merged: [CaddiePlanSequence])? {
        func allowed(_ route: CaddiePlanSequence) -> Bool {
            guard !vetoInstalled || route.id != installedRouteId else { return false }
            return isCurrent(route, authority: authority)
        }
        let incoming = incoming.filter(allowed)
        guard !incoming.isEmpty else { return nil }
        let existing = existing.filter(allowed)
        let first = leadingRoute(
            incoming: incoming,
            existing: existing,
            installed: vetoInstalled ? nil : installed.flatMap { allowed($0) ? $0 : nil },
            retained: retained.flatMap { allowed($0) ? $0 : nil },
            explicitSelectionKey: explicitSelectionKey
        )
        return (first, mergedRoutes(first: first, existing: existing, incoming: incoming))
    }

    /// A route still valid under the 球包 authority: none of its clubs was taken out, and an
    /// installed CoursePrep chain also still uses the typed carries (live decisions carry strategy
    /// carries, so they are re-requested on every bag change instead of compared by value).
    static func isCurrent(_ route: CaddiePlanSequence, authority: ClubBagAuthority) -> Bool {
        guard authority.rosterAllows(route.steps.map(\.clubName)) else { return false }
        guard route.id == installedRouteId else { return true }
        return authority.planMatches(route.steps.map { (club: $0.clubName, carryM: $0.targetCarryM) })
    }

    static func leadingRoute(
        incoming: [CaddiePlanSequence],
        existing: [CaddiePlanSequence],
        installed: CaddiePlanSequence?,
        retained: CaddiePlanSequence?,
        explicitSelectionKey: String?
    ) -> CaddiePlanSequence {
        func matching(_ route: CaddiePlanSequence, in routes: [CaddiePlanSequence]) -> CaddiePlanSequence? {
            routes.first(where: { routeSignature($0) == routeSignature(route) })
                ?? routes.first(where: { samePhysicalRoute($0, route) })
        }
        if let explicitSelectionKey,
           let route = incoming.first(where: { routeSignature($0) == explicitSelectionKey })
                ?? existing.first(where: { routeSignature($0) == explicitSelectionKey }) {
            return route
        }
        if let retained,
           let refreshed = matching(retained, in: incoming) {
            return refreshed
        }
        if let retained,
           let installed,
           !samePhysicalRoute(retained, installed),
           !installed.steps.isEmpty {
            // One-time sparse -> installed upgrade. Once retained is installed, the branch
            // above keeps it stable across every later response.
            return installed
        }
        if let retained { return retained }
        return incoming[0]
    }

    /// The leading route at index zero, then only physically distinct alternatives in the order
    /// the server/offline planner first revealed them, so a refresh cannot reshuffle plan tabs.
    static func mergedRoutes(
        first: CaddiePlanSequence,
        existing: [CaddiePlanSequence],
        incoming: [CaddiePlanSequence]
    ) -> [CaddiePlanSequence] {
        var merged: [CaddiePlanSequence] = [first]
        for route in existing + incoming {
            guard !merged.contains(where: { sameVisibleRoute($0, route) }) else { continue }
            merged.append(route)
        }
        return merged
    }

    static func selected(
        routes: [CaddiePlanSequence],
        preferredToken: String?,
        fallbackToken: String?
    ) -> CaddiePlanSequence? {
        guard !routes.isEmpty else { return nil }
        for token in [preferredToken, fallbackToken].compactMap({ $0 }) {
            let normalized = normalizeToken(token)
            if let match = routes.first(where: {
                normalizeToken($0.id) == normalized
                    || normalizeToken($0.label) == normalized
                    || normalizeToken(routeSignature($0)) == normalized
                    || normalizeToken(physicalSignature($0)) == normalized
                    || caddieSelectionToken(forRouteId: $0.id) == normalized
                    || caddieSelectionToken(forRouteId: $0.label) == normalized
            }) {
                return match
            }
        }
        // The first route is always the installed CoursePrep route when it exists, otherwise the
        // server's selected/stock route. This makes a refresh idempotent.
        return routes.first
    }

    static func isComplete(
        _ route: CaddiePlanSequence,
        par: Int,
        shotType: String
    ) -> Bool {
        guard !route.steps.isEmpty else { return false }
        if shotType.caseInsensitiveCompare("tee") == .orderedSame, par == 3 {
            // A Par 3 is exactly one tee-to-pin scoring leg.
            return true
        }
        guard let last = route.steps.last else { return false }
        if shotType.caseInsensitiveCompare("tee") == .orderedSame, par >= 4 {
            // A single tee club is not a complete Par 4/5 recommendation merely because an old
            // payload called it `scoring` or reported a zero leave.  It is complete only when the
            // planner explicitly proved a factual GIR landing, or when the route contains the
            // normal Par - 2 shot budget.  This prevents the live tabs from exposing a bare
            // `1W` card as if it were the whole hole while still allowing a genuine drivable
            // Par 4 (whose final step carries greenInRegulation) to remain one shot.
            let explicitGIR = route.steps.contains { $0.greenInRegulation == true }
            if !explicitGIR && route.steps.count < max(1, par - 2) {
                return false
            }
        }
        let role = last.role.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if role == "scoring" || role == "approach" { return true }
        if let remaining = last.expectedRemainingM, remaining.isFinite, remaining <= 20 {
            // A non-scoring position prefix with zero leave is deliberately not accepted. It is a
            // CoursePrep prefix and the next lie must be re-planned before claiming the green.
            return role != "position" && role != "advance" && role != "tee"
        }
        return false
    }

    /// A route may be a useful multi-leg prefix while the final lie still needs re-planning, but a
    /// lone Par 4/5 tee club is too little information to put on the player-facing route strip.
    static func isDisplayable(
        _ route: CaddiePlanSequence,
        par: Int,
        shotType: String
    ) -> Bool {
        guard !route.steps.isEmpty else { return false }
        guard shotType.caseInsensitiveCompare("tee") == .orderedSame, par >= 4 else { return true }
        // Two or more measured legs are useful as an honest prefix even on a Par 5; the stricter
        // Par - 2 budget is reserved for routes advertised as complete by `isComplete`.
        return route.steps.count >= 2
            || route.steps.contains { $0.greenInRegulation == true }
    }

    static func samePhysicalRoute(_ lhs: CaddiePlanSequence, _ rhs: CaddiePlanSequence) -> Bool {
        physicalSignature(lhs) == physicalSignature(rhs)
    }

    /// Return true when two routes would be indistinguishable to the player.
    ///
    /// The live route strip exposes the club chain and whether its final leg is a position/layup
    /// or a scoring/GIR leg. It does not expose the planner's hidden carry/route-offset values in
    /// the route tabs. Treating those hidden values as identity produced duplicate choices such as
    /// two separate `3H -> 3W` tabs after a refresh. Physical values remain available on the
    /// selected route and `samePhysicalRoute` still handles refresh retention; they must not create
    /// another player-facing strategy by themselves.
    static func sameVisibleRoute(_ lhs: CaddiePlanSequence, _ rhs: CaddiePlanSequence) -> Bool {
        guard lhs.steps.count == rhs.steps.count, !lhs.steps.isEmpty else { return false }
        for (index, pair) in zip(lhs.steps, rhs.steps).enumerated() {
            let (left, right) = pair
            guard normalizedClub(left.clubName) == normalizedClub(right.clubName) else { return false }
            if index == lhs.steps.count - 1 {
                // A role/green marker change moves the map endpoint from a layup prefix to the
                // green. Keep those routes separate even when their club labels match.
                if endpointClass(left.role) != endpointClass(right.role) { return false }
                // Missing and explicit-false GIR metadata have the same player-facing meaning.
                if (left.greenInRegulation == true) != (right.greenInRegulation == true) {
                    return false
                }
            }
        }
        return true
    }

    /// Stable UI identity for a route version. Roles are included because changing a position leg
    /// into a scoring leg changes where the map must terminate, even when the club/carry chain is
    /// unchanged.
    static func routeSignature(_ route: CaddiePlanSequence) -> String {
        route.steps.map { step in
            let club = zhClubName(step.clubName)
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            let carry = step.targetCarryM.map { String(Int($0.rounded())) } ?? "-"
            let offset = step.routeOffsetM.map { String(Int($0.rounded())) } ?? "-"
            let role = step.role.lowercased()
            return "\(club):\(carry):\(offset):\(role)"
        }.joined(separator: "|")
    }

    /// Physical identity used for deduplication and refresh retention. A server may enrich an
    /// older step with a role or replace a transport id/label without changing the actual clubs and
    /// route stations. Those payloads must update in place instead of appearing as a second route.
    static func physicalSignature(_ route: CaddiePlanSequence) -> String {
        route.steps.map { step in
            let club = zhClubName(step.clubName)
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            let carry = step.targetCarryM.map { String(Int($0.rounded())) } ?? "-"
            let offset = step.routeOffsetM.map { String(Int($0.rounded())) } ?? "-"
            return "\(club):\(carry):\(offset)"
        }.joined(separator: "|")
    }

    private static func completeDistinctRoutes(
        _ routes: [CaddiePlanSequence],
        par: Int,
        shotType: String
    ) -> [CaddiePlanSequence] {
        routes.filter { isComplete($0, par: par, shotType: shotType) }
            .reduce(into: []) { result, route in
                guard !result.contains(where: { sameVisibleRoute($0, route) }) else { return }
                result.append(route)
            }
    }

    private static func deduplicated(_ routes: [CaddiePlanSequence]) -> [CaddiePlanSequence] {
        routes.reduce(into: []) { result, route in
            guard !result.contains(where: { sameVisibleRoute($0, route) }) else { return }
            result.append(route)
        }
    }

    private static func normalizedClub(_ value: String) -> String {
        zhClubDisplayName(zhClubName(value))
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

    private static func endpointClass(_ role: String) -> String {
        switch role.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "scoring", "approach": return "scoring"
        case "tee", "advance", "position", "layup": return "position"
        default: return role.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        }
    }

    private static func normalizeToken(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private static var emptyDecision: CaddieDecisionResponse {
        CaddieDecisionResponse(
            schema: "empty",
            decisionId: nil,
            sourceRef: nil,
            evidenceRefs: nil,
            shotType: "tee",
            phase: "tee_shot",
            context: [:],
            options: [],
            selected: nil,
            selectedOptionId: nil,
            selectedOption: nil,
            sequences: [],
            selectedSequence: nil,
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [:],
            evidence: [],
            confidence: [:],
            missingData: [],
            auditCriteria: []
        )
    }
}
