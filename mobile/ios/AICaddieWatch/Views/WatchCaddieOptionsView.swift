import SwiftUI

/// AI-caddie 球童打法: each route shows its complete club chain when available. The recommended
/// option is highlighted. Expected strokes and success-% stay absent until there is a calibrated model.
/// `WatchRoundState.caddieOptions`; a plain VStack so it renders in the ImageRenderer design snapshot.
public struct WatchCaddieOptionsView: View {
    public let options: [WatchCaddieOption]
    public let recommendedId: String?
    public let onBack: (() -> Void)?

    public init(
        options: [WatchCaddieOption],
        recommendedId: String? = nil,
        onBack: (() -> Void)? = nil
    ) {
        self.options = options
        self.recommendedId = recommendedId
        self.onBack = onBack
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                if let onBack {
                    Button(action: onBack) {
                        Image(systemName: "chevron.backward")
                            .font(.caption.weight(.semibold))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("返回球洞")
                }
                Text("球童打法")
                    .font(.headline)
            }
            if options.isEmpty {
                Text("暂无方案")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(options) { option in
                    optionRow(option)
                }
            }
        }
    }

    private func optionRow(_ option: WatchCaddieOption) -> some View {
        let key = strategyKey(option.optionId)
        let isRecommended = option.optionId == (recommendedId ?? "stock")
        let plan = option.plan ?? []
        return VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(option.label)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(AICaddieDesignTokens.strategyColor(key))
                Spacer()
                if plan.isEmpty, let club = option.clubName {
                    Text(club)
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                }
            }
            if !plan.isEmpty {
                Text(plan.map(\.clubName).joined(separator: " → "))
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .lineLimit(2)
                let carries = plan.compactMap(\.carryM).map { "\(Self.yards($0))" }
                if !carries.isEmpty {
                    Text(carries.joined(separator: " · ") + " 码")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            } else if let carry = option.carryM {
                Text("\(Self.yards(carry)) 码")
                    .font(.caption2.monospacedDigit())
            }
        }
        .padding(6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isRecommended ? AICaddieDesignTokens.strategyColor("stock").opacity(0.18) : Color.white.opacity(0.06))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isRecommended ? AICaddieDesignTokens.strategyColor("stock") : Color.clear, lineWidth: 1.5)
        )
    }

    /// Map the option id to the strategy colour key the design tokens understand.
    private func strategyKey(_ optionId: String) -> String {
        switch optionId.lowercased() {
        case "safe", "conservative", "protect", "protect_score":
            return "protect_score"
        case "attack", "aggressive":
            return "attack"
        default:
            return "stock"
        }
    }

    static func yards(_ metres: Double) -> Int { Int((metres * 1.09361).rounded()) }
}

/// Opening the recommendation from Hole Root goes straight to the complete play chains. The older
/// single-shot facts remain an honest fallback only for companion payloads that have no full plans.
public struct WatchCaddieScreen: View {
    public let state: WatchRoundState
    public let frontYd: Int?
    public let centerYd: Int?
    public let backYd: Int?
    public let lastShotDistanceM: Double?
    public let onBack: () -> Void

    public init(
        state: WatchRoundState,
        frontYd: Int? = nil,
        centerYd: Int? = nil,
        backYd: Int? = nil,
        lastShotDistanceM: Double? = nil,
        onBack: @escaping () -> Void = {}
    ) {
        self.state = state
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.lastShotDistanceM = lastShotDistanceM
        self.onBack = onBack
    }

    var showsPlanOptionsFirst: Bool { !state.caddieOptions.isEmpty }

    public var body: some View {
        ScrollView {
            if showsPlanOptionsFirst {
                WatchCaddieOptionsView(
                    options: state.caddieOptions,
                    recommendedId: state.offlineOptionId,
                    onBack: onBack
                )
                .padding(8)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 5) {
                        Button(action: onBack) {
                            Image(systemName: "chevron.backward")
                                .font(.caption.weight(.semibold))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("返回球洞")
                        Text("球童建议")
                            .font(.headline)
                    }
                    WatchCaddieGlanceView(
                        state: state,
                        frontYd: frontYd,
                        centerYd: centerYd,
                        backYd: backYd,
                        lastShotDistanceM: lastShotDistanceM
                    )
                }
                .padding(8)
            }
        }
        .scrollIndicators(.hidden)
    }
}
