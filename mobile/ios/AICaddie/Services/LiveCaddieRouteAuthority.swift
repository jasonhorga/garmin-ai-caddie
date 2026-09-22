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
        shotType: String
    ) -> [CaddiePlanSequence] {
        // The installed chain is the first-frame visual authority even when it is an explicit
        // CoursePrep prefix (`completion=replan_required`). Keeping that prefix prevents a refresh
        // from replacing `1W -> 3H` with an unrelated sparse planner chain. Completeness is only a
        // gate for *additional* remote alternatives.
        let installedRoute = installed?.steps.isEmpty == false ? installed : nil
        let onlineRoutes = completeDistinctRoutes(
            CaddiePlanPresentation.distinctSequences(from: online ?? emptyDecision),
            par: par,
            shotType: shotType
        )
        let offlineRoutes = completeDistinctRoutes(
            CaddiePlanPresentation.distinctSequences(from: offline ?? emptyDecision),
            par: par,
            shotType: shotType
        )

        var result: [CaddiePlanSequence] = []
        if let installedRoute {
            result.append(installedRoute)
        }

        // An online response with no structured route is a sparse card, not a replacement for the
        // installed route. Prefer online only for alternatives with a real chain. If there is no
        // CoursePrep route yet, the complete online route becomes the first authority.
        let candidates = onlineRoutes + offlineRoutes
        for route in candidates {
            if result.contains(where: { samePhysicalRoute($0, route) }) { continue }
            result.append(route)
        }

        // A stale remote route can be the only payload during a cold deferred-hole frame. If the
        // offline evaluator has a complete route, it is preferable to a single bare option and is
        // already deterministic from the installed bag and hole facts.
        return deduplicated(result)
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
        let role = last.role.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if role == "scoring" || role == "approach" { return true }
        if let remaining = last.expectedRemainingM, remaining.isFinite, remaining <= 20 {
            // A non-scoring position prefix with zero leave is deliberately not accepted. It is a
            // CoursePrep prefix and the next lie must be re-planned before claiming the green.
            return role != "position" && role != "advance" && role != "tee"
        }
        return false
    }

    static func samePhysicalRoute(_ lhs: CaddiePlanSequence, _ rhs: CaddiePlanSequence) -> Bool {
        physicalSignature(lhs) == physicalSignature(rhs)
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
                guard !result.contains(where: { samePhysicalRoute($0, route) }) else { return }
                result.append(route)
            }
    }

    private static func deduplicated(_ routes: [CaddiePlanSequence]) -> [CaddiePlanSequence] {
        routes.reduce(into: []) { result, route in
            guard !result.contains(where: { samePhysicalRoute($0, route) }) else { return }
            result.append(route)
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
