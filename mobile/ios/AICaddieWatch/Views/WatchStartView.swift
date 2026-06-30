import SwiftUI

/// round-12 P3.3 (Watch standalone): the watch's home-before-a-round screen. The primary action is
/// 「开始记分」— a clean scorecard right on the wrist (works without the phone / Garmin). Whether the
/// iPhone is reachable is a light note underneath, not a headline (a phone-coordinated round still
/// seeds automatically). Presentational — the start action is wired to
/// `WatchRoundModel.startPracticeRound()` by the app.
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

            // 主动作:直接开一张干净的记分卡。无需手机 / Garmin 也能在手表上独立记分。
            Button(action: onStartPractice) {
                Text("开始记分").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)

            // 连接状态只作轻量提示,不喧宾夺主:无论是否连手机都能记分,联网后自动同步。
            Label(
                phoneReachable ? "已连接 iPhone · 自动同步" : "手表可独立记分,联网后自动同步",
                systemImage: phoneReachable ? "iphone.radiowaves.left.and.right" : "applewatch"
            )
            .font(.caption2)
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
        }
        .padding()
    }
}
