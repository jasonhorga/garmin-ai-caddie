import SwiftUI

/// round-13 spec ⑤: the 障碍 (Hazard) screen — bunkers then water, near→far, each with its carry
/// interval (前沿 = near edge / 越过 = far edge, in 码). Driven by the phone-pushed
/// `WatchRoundState.hazards`; a plain VStack so it renders in the ImageRenderer design snapshot.
/// Geometry-gated upstream: holes without usable geometry push no hazards and show the empty state.
public struct WatchHazardView: View {
    public let hazards: [WatchHazard]

    public init(hazards: [WatchHazard]) {
        self.hazards = hazards
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("障碍")
                .font(.headline)
            if hazards.isEmpty {
                Text("本洞无障碍数据")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(hazards) { hazard in
                    hazardRow(hazard)
                }
            }
        }
    }

    private func hazardRow(_ hazard: WatchHazard) -> some View {
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
        }
        .padding(6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.06)))
    }

    private func carryText(_ hazard: WatchHazard) -> String? {
        guard let start = hazard.startM else {
            return nil
        }
        if let end = hazard.endM {
            return "前沿 \(Self.yards(start)) · 越过 \(Self.yards(end)) 码"
        }
        return "前沿 \(Self.yards(start)) 码"
    }

    static func yards(_ metres: Double) -> Int { Int((metres * 1.09361).rounded()) }
}
