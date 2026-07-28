import SwiftUI

/// Hazard list: remaining hazards near→far. Bunkers show route distance + lateral gap; water shows
/// enter/clear distance. Driven by `WatchRoundState.hazards`; a plain VStack also renders in snapshots.
/// Geometry-gated upstream: holes without usable geometry push no hazards and show the empty state.
public struct WatchHazardView: View {
    public let hazards: [WatchHazard]
    public let playerProgressM: Double
    public let onSelect: ((WatchHazard) -> Void)?

    public init(
        hazards: [WatchHazard],
        playerProgressM: Double = 0,
        onSelect: ((WatchHazard) -> Void)? = nil
    ) {
        self.hazards = hazards
        self.playerProgressM = playerProgressM
        self.onSelect = onSelect
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("障碍")
                .font(.headline)
            if orderedHazards.isEmpty {
                Text(hazards.isEmpty ? "本洞无障碍数据" : "前方没有障碍")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(orderedHazards) { hazard in
                    if let onSelect {
                        Button(action: { onSelect(hazard) }) {
                            hazardRow(hazard, showsDisclosure: true)
                        }
                        .buttonStyle(.plain)
                    } else {
                        hazardRow(hazard, showsDisclosure: false)
                    }
                }
            }
        }
    }

    private var orderedHazards: [WatchHazard] {
        hazards
            .filter { (WatchHazardMapLayout.alongRouteEndMetres(for: $0)
                ?? -Double.greatestFiniteMagnitude) > playerProgressM }
            .sorted { ($0.startM ?? $0.endM ?? Double.greatestFiniteMagnitude)
                < ($1.startM ?? $1.endM ?? Double.greatestFiniteMagnitude) }
    }

    private func hazardRow(_ hazard: WatchHazard, showsDisclosure: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(hazard.kind == "water" ? "💧" : "🏖")
            VStack(alignment: .leading, spacing: 1) {
                Text(hazard.label)
                    .font(.system(size: 14, weight: .semibold))
                if let detail = carryText(hazard) {
                    Text(detail)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            }
            Spacer()
            if showsDisclosure {
                Image(systemName: "chevron.forward")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.06)))
    }

    private func carryText(_ hazard: WatchHazard) -> String? {
        if hazard.kind == "bunker" {
            let distance = hazard.startM.flatMap {
                WatchHazardMapLayout.remainingYards(to: $0, after: playerProgressM)
            }
            let side = WatchHazardMapLayout.bunkerSideMetres(for: hazard).map {
                Int(($0 * 1.09361).rounded())
            }
            if let distance, let side { return "距 \(distance) · 离球路 \(side) 码" }
            if let distance { return "距 \(distance) 码" }
            return nil
        }

        let startYards = hazard.startM.flatMap {
            WatchHazardMapLayout.remainingYards(to: $0, after: playerProgressM)
        }
        let endYards = hazard.endM.flatMap {
            WatchHazardMapLayout.remainingYards(to: $0, after: playerProgressM)
        }
        if let startYards, let endYards {
            return "前 \(startYards) · 越 \(endYards) 码"
        }
        if let endYards { return "越 \(endYards) 码" }
        if let startYards { return "前 \(startYards) 码" }
        return nil
    }
}
