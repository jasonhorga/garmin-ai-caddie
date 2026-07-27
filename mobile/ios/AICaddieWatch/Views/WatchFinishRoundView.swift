import SwiftUI

/// round-12 P3.3 (Watch standalone): the round-finish summary reached from `WatchRoundHomeView`'s
/// "结束". Shows the score relative to par (large, color-coded), total strokes / holes played / putts,
/// any still-pending uploads, then confirm-finish (upload remaining events + finalize) or keep playing.
/// Presentational (driven by the standalone round model); kept as a VStack so it renders in
/// ImageRenderer snapshots for CI visual review.
public struct WatchFinishRoundView: View {
    public let courseName: String
    public let holesPlayed: Int
    public let holeCount: Int
    public let totalStrokes: Int
    public let toPar: Int?
    public let totalPutts: Int?
    public let fairwaySummary: WatchOutcomeSummary?
    public let girSummary: WatchOutcomeSummary?
    public let pendingUploads: Int
    public let onConfirmFinish: () -> Void
    public let onKeepPlaying: () -> Void

    public init(
        courseName: String,
        holesPlayed: Int,
        holeCount: Int,
        totalStrokes: Int,
        toPar: Int?,
        totalPutts: Int? = nil,
        fairwaySummary: WatchOutcomeSummary? = nil,
        girSummary: WatchOutcomeSummary? = nil,
        pendingUploads: Int = 0,
        onConfirmFinish: @escaping () -> Void = {},
        onKeepPlaying: @escaping () -> Void = {}
    ) {
        self.courseName = courseName
        self.holesPlayed = holesPlayed
        self.holeCount = holeCount
        self.totalStrokes = totalStrokes
        self.toPar = toPar
        self.totalPutts = totalPutts
        self.fairwaySummary = fairwaySummary
        self.girSummary = girSummary
        self.pendingUploads = pendingUploads
        self.onConfirmFinish = onConfirmFinish
        self.onKeepPlaying = onKeepPlaying
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text("结束本场").font(.headline.weight(.bold))
                Text(courseName).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }

            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(toParText)
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                VStack(alignment: .leading, spacing: 0) {
                    Text("\(totalStrokes) 杆").font(.body.weight(.semibold))
                    Text("\(holesPlayed)/\(holeCount) 洞").font(.caption2).foregroundStyle(.secondary)
                }
            }

            if totalPutts != nil || fairwaySummary != nil || girSummary != nil {
                HStack(spacing: 6) {
                    if let totalPutts {
                        finishMetric(label: "推杆", value: "\(totalPutts)")
                    }
                    if let fairwaySummary {
                        finishMetric(
                            label: "球道",
                            value: "\(fairwaySummary.hits)/\(fairwaySummary.recorded)"
                        )
                    }
                    if let girSummary {
                        finishMetric(
                            label: "GIR",
                            value: "\(girSummary.hits)/\(girSummary.recorded)"
                        )
                    }
                }
                .frame(maxWidth: .infinity)
            }
            if pendingUploads > 0 {
                Label("稍后同步 \(pendingUploads)", systemImage: "arrow.up.circle")
                    .font(.caption)
                    .foregroundStyle(AICaddieDesignTokens.offline)
            }

            Button(action: onConfirmFinish) {
                Text("保存并结束").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)
            Button(action: onKeepPlaying) {
                Text("继续打球").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
        .padding(8)
    }

    private var toParText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }

    private func finishMetric(label: String, value: String) -> some View {
        VStack(spacing: 0) {
            Text(value).font(.caption.weight(.semibold))
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
