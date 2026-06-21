import SwiftUI

/// round-12 P3.3 (Watch standalone): the watch's home-before-a-round screen. Lets the user start a
/// self-contained practice round right on the wrist (no phone / Garmin needed) and shows whether the
/// iPhone is connected (a phone-coordinated round seeds the round automatically instead). Presentational
/// — the start action is wired to `WatchRoundModel.startPracticeRound()` by the app.
public struct WatchStartView: View {
    public let phoneReachable: Bool
    public let onStartPractice: () -> Void

    public init(phoneReachable: Bool, onStartPractice: @escaping () -> Void = {}) {
        self.phoneReachable = phoneReachable
        self.onStartPractice = onStartPractice
    }

    public var body: some View {
        VStack(spacing: 10) {
            Text("AI Caddie")
                .font(.headline.weight(.bold))
            Label(
                phoneReachable ? "已连接 iPhone" : "未连接 iPhone",
                systemImage: phoneReachable ? "iphone.radiowaves.left.and.right" : "iphone.slash"
            )
            .font(.caption2)
            .foregroundStyle(phoneReachable ? AICaddieDesignTokens.par : .secondary)

            Button(action: onStartPractice) {
                Text("开始练习记分").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)

            Text("在手表上独立记分,联网后自动同步")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}
