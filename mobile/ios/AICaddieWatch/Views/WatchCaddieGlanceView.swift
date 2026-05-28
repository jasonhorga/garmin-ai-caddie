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
            HStack(spacing: 4) {
                Image(systemName: state.targetLatitude == nil || state.targetLongitude == nil ? "mappin.slash" : "mappin.and.ellipse")
                Text(state.targetLatitude == nil || state.targetLongitude == nil ? "Pin needed" : "\(state.targetKind ?? "target") ready")
                    .lineLimit(1)
            }
            .font(.caption2)
            .foregroundStyle(state.targetLatitude == nil || state.targetLongitude == nil ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
            if let nextShotPrompt = state.nextShotPrompt {
                HStack(spacing: 4) {
                    Image(systemName: "figure.golf")
                    Text(nextShotPrompt)
                        .lineLimit(2)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(AICaddieDesignTokens.strategyColor("stock"))
            }
            if let holePlanSummary = state.holePlanSummary {
                HStack(spacing: 4) {
                    Image(systemName: "point.topleft.down.curvedto.point.bottomright.up")
                    Text(holePlanSummary)
                        .lineLimit(2)
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AICaddieDesignTokens.strategyColor(state.strategyMode ?? "stock"))
            }
            if let evidenceSummary = state.evidenceSummary {
                HStack(spacing: 4) {
                    Image(systemName: "checklist")
                    Text(evidenceSummary)
                        .lineLimit(2)
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            if let missingDataSummary = state.missingDataSummary {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle")
                    Text(missingDataSummary)
                        .lineLimit(2)
                }
                .font(.caption2)
                .foregroundStyle(AICaddieDesignTokens.confidenceColor("low"))
            }
            Text(state.caddieConfidence)
                .font(.caption)
                .foregroundStyle(AICaddieDesignTokens.confidenceColor(state.caddieConfidence))
        }
    }
}
