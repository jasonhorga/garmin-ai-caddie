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
    static func recommendation(from decision: CaddieDecisionResponse) -> Recommendation? {
        let sequences = CaddiePlanSequence.sequences(from: decision)
        let selectedID = CaddiePlanSequence.selectedSequenceId(from: decision) ?? decision.selectedOptionId
        let sequence = sequences.first(where: { $0.id == selectedID }) ?? sequences.first
        let options = CaddiePlanOption.options(from: decision)
        let option = options.first { $0.id == decision.selectedOptionId } ?? options.first
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
