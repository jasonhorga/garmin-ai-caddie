import SwiftUI

public struct WatchCaddieGlanceView: View {
    public let state: WatchRoundState

    public init(state: WatchRoundState) {
        self.state = state
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: "scope")
                Text(state.suggestedClub ?? state.selectedClub ?? "--")
                    .font(.headline)
            }
            if let targetNote = state.targetNote {
                Text(targetNote)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if let nextShotPrompt = state.nextShotPrompt {
                HStack(spacing: 4) {
                    Image(systemName: "figure.golf")
                    Text(nextShotPrompt)
                        .lineLimit(2)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(AICaddieDesignTokens.strategyColor("stock"))
            }
            Text(state.caddieConfidence)
                .font(.caption)
                .foregroundStyle(AICaddieDesignTokens.confidenceColor(state.caddieConfidence))
        }
    }
}
