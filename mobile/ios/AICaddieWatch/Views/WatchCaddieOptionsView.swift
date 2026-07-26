import SwiftUI

/// round-13 spec ②: the AI-caddie 球童打法 screen — 激进 / 推荐 / 保守 side by side, each with its
/// recommended club + 目标码. The recommended (stock) option is highlighted. Expected strokes and
/// success-% stay absent until there is a calibrated model. Driven by the phone-pushed
/// `WatchRoundState.caddieOptions`; a plain VStack so it renders in the ImageRenderer design snapshot.
public struct WatchCaddieOptionsView: View {
    public let options: [WatchCaddieOption]
    public let recommendedId: String?

    public init(options: [WatchCaddieOption], recommendedId: String? = nil) {
        self.options = options
        self.recommendedId = recommendedId
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("球童打法")
                .font(.headline)
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
        return VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(option.label)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(AICaddieDesignTokens.strategyColor(key))
                Spacer()
                if let club = option.clubName {
                    Text(club)
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                }
            }
            HStack(spacing: 8) {
                if let carry = option.carryM {
                    Text("\(Self.yards(carry)) 码").monospacedDigit()
                }
            }
            .font(.caption2)
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
