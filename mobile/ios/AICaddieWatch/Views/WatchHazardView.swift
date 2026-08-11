import SwiftUI

/// Hazard list: remaining hazards near→far. New geometry shows the same 到/过 front/back readout for
/// sand and water; old bunker caches keep their one reliable distance and never expose lateral gap.
/// Geometry-gated upstream: holes without usable geometry push no hazards and show the empty state.
public struct WatchHazardView: View {
    public let hazards: [WatchHazard]
    public let playerProgressM: Double
    public let playerImagePoint: CGPoint?
    public let route: [[Double]]
    public let onSelect: ((WatchHazard) -> Void)?

    public init(
        hazards: [WatchHazard],
        playerProgressM: Double = 0,
        playerImagePoint: CGPoint? = nil,
        route: [[Double]] = [],
        onSelect: ((WatchHazard) -> Void)? = nil
    ) {
        self.hazards = hazards
        self.playerProgressM = playerProgressM
        self.playerImagePoint = playerImagePoint
        self.route = route
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
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
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
        let hasFrontBack = hazard.kind == "water" || WatchHazardMapLayout.hasMeasuredFrontBack(hazard)
        if !hasFrontBack {
            let distance = edgeYards(
                pixel: hazard.frontPx,
                teeDistanceM: hazard.frontDistanceM,
                routeM: hazard.startM
            )
            if let distance { return "距 \(distance) 码" }
            return nil
        }

        let startYards = edgeYards(
            pixel: hazard.frontPx,
            teeDistanceM: hazard.frontDistanceM,
            routeM: hazard.startM
        )
        let endYards = edgeYards(
            pixel: hazard.backPx,
            teeDistanceM: hazard.backDistanceM,
            routeM: hazard.endM
        )
        if let startYards, let endYards {
            return "到 \(startYards) · 过 \(endYards) 码"
        }
        if let endYards { return "过 \(endYards) 码" }
        if let startYards { return "到 \(startYards) 码" }
        return nil
    }

    private func edgeYards(pixel: [Double]?, teeDistanceM: Double?, routeM: Double?) -> Int? {
        if let playerImagePoint,
           let edge = WatchHazardMapLayout.point(pixel),
           let live = WatchHazardMapLayout.distanceYards(from: playerImagePoint, to: edge, on: route) {
            return WatchGeoMath.usefulGolfYards(live)
        }
        if playerProgressM <= 0, let teeDistanceM {
            return WatchGeoMath.usefulGolfYards(Int((teeDistanceM * 1.09361).rounded()))
        }
        return WatchGeoMath.usefulGolfYards(routeM.flatMap {
            WatchHazardMapLayout.remainingYards(to: $0, after: playerProgressM)
        })
    }
}
