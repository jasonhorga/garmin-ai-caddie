import Foundation

/// One policy owns the three quick club chips shown during a live shot. The backend recommendation
/// is authoritative; distance-ranked bag clubs are only fallbacks when a decision has not arrived.
enum LiveClubStripPolicy {
    /// The backend's answer is a display fact even when the player's downloaded bag does not yet
    /// contain a matching distance profile. Keeping the carry beside the normalized name lets the
    /// map and the quick strip consume exactly the same recommendation instead of silently falling
    /// back to whichever bag row happened to sort first.
    struct Recommendation: Equatable {
        let name: String
        let carryMetres: Double?
    }

    /// Resolve the club and carry for the selected route. Long-hole responses put the authoritative
    /// first shot in `selectedSequence.clubs`; short-hole responses only have the selected option.
    /// A sequence's first step wins because it is the value used to draw the landing marker.
    /// `strategyMode` is optional for older callers, but when supplied it is the source of truth
    /// while the player is switching between 保守/推荐/进攻 cards and before the server round-trip.
    static func recommendation(
        from decision: CaddieDecisionResponse,
        strategyMode requestedStrategyMode: String? = nil
    ) -> Recommendation? {
        let sequences = CaddiePlanSequence.sequences(from: decision)
        let options = CaddiePlanOption.options(from: decision)
        let requestedMode = normalizedStrategyMode(requestedStrategyMode)
        let selectedID = CaddiePlanSequence.selectedSequenceId(from: decision) ?? decision.selectedOptionId
        let selectedSequence = sequences.first(where: { $0.id == selectedID })
        let sequence = requestedMode.flatMap { mode in
            sequences.first(where: { strategyMode(for: $0) == mode })
        } ?? selectedSequence ?? sequences.first
        let selectedOption = options.first { $0.id == decision.selectedOptionId }
        let option = requestedMode.flatMap { mode in
            options.first(where: { strategyMode(for: $0) == mode })
        } ?? selectedOption ?? options.first
        if let step = sequence?.steps.first,
           let name = normalizedClubName(step.clubName) {
            let carry = validCarry(step.targetCarryM) ?? validCarry(option?.carryM)
            return Recommendation(name: name, carryMetres: carry)
        }

        guard let option, let name = normalizedClubName(option.clubName) else {
            return nil
        }
        return Recommendation(name: name, carryMetres: validCarry(option.carryM))
    }

    private static func strategyMode(for sequence: CaddiePlanSequence) -> String? {
        caddieStrategyMode(forRouteId: sequence.id)
            ?? caddieStrategyMode(forRouteId: sequence.label)
    }

    private static func strategyMode(for option: CaddiePlanOption) -> String? {
        caddieStrategyMode(forRouteId: option.id)
            ?? caddieStrategyMode(forRouteId: option.label)
    }

    private static func normalizedStrategyMode(_ value: String?) -> String? {
        guard let value else { return nil }
        return caddieStrategyMode(forRouteId: value) ?? value.lowercased()
    }

    static func orderedNames(
        profiles: [String: ClubProfile],
        recommended: String?,
        selected: String,
        targetMetres: Double?
    ) -> [String] {
        let ordered = profiles.sorted { lhs, rhs in
            if let targetMetres {
                let lhsDelta = abs(lhs.value.medianM - targetMetres)
                let rhsDelta = abs(rhs.value.medianM - targetMetres)
                if lhsDelta != rhsDelta { return lhsDelta < rhsDelta }
            }
            if lhs.value.medianM != rhs.value.medianM {
                return lhs.value.medianM > rhs.value.medianM
            }
            return lhs.key < rhs.key
        }.map(\.key)

        var result: [String] = []
        if let recommended,
           !recommended.isEmpty {
            result.append(recommended)
        }
        if !selected.isEmpty,
           !result.contains(selected) {
            result.append(selected)
        }
        for name in ordered where !result.contains(name) {
            result.append(name)
            if result.count == 3 { break }
        }
        return Array(result.prefix(3))
    }

    static func distanceMetres(
        for name: String,
        profiles: [String: ClubProfile],
        recommendation: Recommendation?
    ) -> Double? {
        if let recommendation,
           recommendation.name == name,
           let carry = validCarry(recommendation.carryMetres) {
            return carry
        }
        return profiles[name]?.medianM
    }

    private static func normalizedClubName(_ raw: String) -> String? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed != "-", trimmed.lowercased() != "unknown" else {
            return nil
        }
        return zhClubName(trimmed)
    }

    private static func validCarry(_ value: Double?) -> Double? {
        guard let value,
              value.isFinite,
              value > 0,
              value <= GeoDistance.maximumUsefulGreenMetres else {
            return nil
        }
        return value
    }
}
