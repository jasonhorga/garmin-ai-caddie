import SwiftUI

enum WatchFinishMetricTone: Equatable {
    case score
    case neutral
    case gir
    case fairway
}

struct WatchFinishMetric: Equatable {
    let value: String
    let label: String
    let detail: String?
    let tone: WatchFinishMetricTone

    init(
        value: String,
        label: String,
        detail: String? = nil,
        tone: WatchFinishMetricTone
    ) {
        self.value = value
        self.label = label
        self.detail = detail
        self.tone = tone
    }
}

/// round-12 P3.3 (Watch standalone): the round-finish summary reached from `WatchRoundHomeView`'s
/// "结束". It restores the approved compact result grid while retaining honest outcome denominators
/// and the safe finish transaction: pending events are saved before the round is finalized, and keep
/// playing remains non-destructive. Kept as plain stacks so CI's ImageRenderer captures the real view.
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
        VStack(alignment: .leading, spacing: 5) {
            VStack(alignment: .leading, spacing: 2) {
                Text("结束球局")
                    .font(.system(size: 15, weight: .bold))
                HStack(spacing: 4) {
                    Text(courseName)
                        .lineLimit(1)
                    Spacer(minLength: 2)
                    Text("\(holesPlayed)/\(holeCount) 洞")
                        .fixedSize()
                }
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.secondary)
            }

            HStack(spacing: 4) {
                ForEach(Array(headlineMetrics.enumerated()), id: \.offset) { _, metric in
                    finishMetric(metric, valueSize: 20)
                }
            }
            .frame(maxWidth: .infinity)

            if !outcomeMetrics.isEmpty {
                HStack(spacing: 14) {
                    ForEach(Array(outcomeMetrics.enumerated()), id: \.offset) { _, metric in
                        finishMetric(metric, valueSize: 20)
                    }
                }
                .padding(.horizontal, 13)
                .frame(maxWidth: .infinity)
            }

            if let pendingUploadText {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.up.circle")
                    Text(pendingUploadText)
                }
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(AICaddieDesignTokens.offline)
            }

            Spacer(minLength: 1)

            Button(action: onConfirmFinish) {
                Text(primaryActionLabel)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity, minHeight: 34)
                    .background(
                        Color(red: 0.28, green: 0.86, blue: 0.46),
                        in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                    )
            }
            .buttonStyle(.plain)

            Button(action: onKeepPlaying) {
                Text(secondaryActionLabel)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.78))
                    .frame(maxWidth: .infinity, minHeight: 24)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    var headlineMetrics: [WatchFinishMetric] {
        [
            WatchFinishMetric(value: toParText, label: "成绩", tone: .score),
            WatchFinishMetric(value: "\(totalStrokes)", label: "总杆", tone: .neutral),
            WatchFinishMetric(value: totalPutts.map(String.init) ?? "—", label: "推杆", tone: .neutral),
        ]
    }

    var outcomeMetrics: [WatchFinishMetric] {
        var metrics: [WatchFinishMetric] = []
        if let girSummary, girSummary.recorded > 0 {
            metrics.append(
                WatchFinishMetric(
                    value: percentageText(girSummary),
                    label: "GIR",
                    detail: "\(girSummary.hits)/\(girSummary.recorded)",
                    tone: .gir
                )
            )
        }
        if let fairwaySummary, fairwaySummary.recorded > 0 {
            metrics.append(
                WatchFinishMetric(
                    value: percentageText(fairwaySummary),
                    label: "球道",
                    detail: "\(fairwaySummary.hits)/\(fairwaySummary.recorded)",
                    tone: .fairway
                )
            )
        }
        return metrics
    }

    var pendingUploadText: String? {
        pendingUploads > 0 ? "结束前保存 \(pendingUploads) 条" : nil
    }

    var primaryActionLabel: String { "保存并结束" }
    var secondaryActionLabel: String { "继续打球" }

    private var toParText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }

    private func percentageText(_ summary: WatchOutcomeSummary) -> String {
        let percentage = Int((Double(summary.hits) / Double(summary.recorded) * 100).rounded())
        return "\(percentage)%"
    }

    private func finishMetric(_ metric: WatchFinishMetric, valueSize: CGFloat) -> some View {
        VStack(spacing: 1) {
            Text(metric.value)
                .font(.system(size: valueSize, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(metricColor(metric.tone))
                .minimumScaleFactor(0.72)
                .lineLimit(1)
            Text(metric.label)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.secondary)
            if let detail = metric.detail {
                Text(detail)
                    .font(.system(size: 7, weight: .medium, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.secondary.opacity(0.72))
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            [metric.label, metric.value, metric.detail].compactMap { $0 }.joined(separator: " ")
        )
    }

    private func metricColor(_ tone: WatchFinishMetricTone) -> Color {
        switch tone {
        case .score:
            return Color(red: 1.0, green: 0.82, blue: 0.16)
        case .neutral:
            return .white
        case .gir:
            return Color(red: 0.28, green: 0.86, blue: 0.46)
        case .fairway:
            return Color(red: 0.18, green: 0.67, blue: 1.0)
        }
    }
}
