import SwiftUI

public struct WatchCaddieGlanceView: View {
    public let state: WatchRoundState

    public init(state: WatchRoundState) {
        self.state = state
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            // round-13 LIVE: 前/中/后果岭(F/M/B)+ 坡度补偿 + 距上一杆 (码). Each guarded so a
            // hole without geometry (fields nil) shows nothing rather than "0" noise.
            if state.centerGreenM != nil || state.frontGreenM != nil || state.backGreenM != nil {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    if let front = state.frontGreenM { greenPip("前", front) }
                    if let center = state.centerGreenM {
                        VStack(spacing: 0) {
                            Text("\(Self.yards(center))")
                                .font(.system(size: 34, weight: .bold, design: .rounded)).monospacedDigit()
                                .foregroundStyle(AICaddieDesignTokens.bogey)
                            Text("中").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    if let back = state.backGreenM { greenPip("后", back) }
                }
            }
            if let delta = state.elevationDeltaM, abs(delta) >= 0.5 {
                let dy = Self.yards(delta)
                HStack(spacing: 3) {
                    Image(systemName: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                    Text("坡度 \(dy > 0 ? "+" : "")\(dy) 码")
                }
                .font(.caption2)
                .foregroundStyle(delta > 0 ? AICaddieDesignTokens.bogey : AICaddieDesignTokens.par)
            }
            if let fromLast = state.distanceFromLastShotM {
                HStack(spacing: 3) {
                    Image(systemName: "arrow.left.and.right")
                    Text("距上一杆 \(Self.yards(fromLast)) 码")
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
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

    private func greenPip(_ label: String, _ metres: Double) -> some View {
        VStack(spacing: 0) {
            Text("\(Self.yards(metres))").font(.headline.weight(.semibold)).monospacedDigit()
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }

    // Fields are metres; the R13 design shows distances in 码 (yards).
    static func yards(_ metres: Double) -> Int { Int((metres * 1.09361).rounded()) }
}
