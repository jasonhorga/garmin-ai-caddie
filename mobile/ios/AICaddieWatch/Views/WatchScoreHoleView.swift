import SwiftUI

/// Per-hole confirmation: accept the recommendation in one tap, or walk through total strokes, putts,
/// fairway result (Par 4/5), and penalties. Presentational and driven by `WatchRoundModel`.
public struct WatchScoreHoleView: View {
    public let hole: Int
    public let par: Int
    public let score: Int
    public let putts: Int
    public let penalty: Int
    public let step: WatchScoreFlowStep
    public let fairway: WatchFairwayResult?
    public let onScoreDelta: (Int) -> Void
    public let onPuttsDelta: (Int) -> Void
    public let onPenaltyDelta: (Int) -> Void
    public let onAcceptRecommended: () -> Void
    public let onManualEntry: () -> Void
    public let onAdvance: () -> Void
    public let onFairway: (WatchFairwayResult) -> Void
    public let onSave: () -> Void
    public let onCancel: () -> Void

    public init(
        hole: Int,
        par: Int,
        score: Int,
        putts: Int,
        penalty: Int,
        step: WatchScoreFlowStep = .recommendation,
        fairway: WatchFairwayResult? = nil,
        onScoreDelta: @escaping (Int) -> Void = { _ in },
        onPuttsDelta: @escaping (Int) -> Void = { _ in },
        onPenaltyDelta: @escaping (Int) -> Void = { _ in },
        onAcceptRecommended: @escaping () -> Void = {},
        onManualEntry: @escaping () -> Void = {},
        onAdvance: @escaping () -> Void = {},
        onFairway: @escaping (WatchFairwayResult) -> Void = { _ in },
        onSave: @escaping () -> Void = {},
        onCancel: @escaping () -> Void = {}
    ) {
        self.hole = hole
        self.par = par
        self.score = score
        self.putts = putts
        self.penalty = penalty
        self.step = step
        self.fairway = fairway
        self.onScoreDelta = onScoreDelta
        self.onPuttsDelta = onPuttsDelta
        self.onPenaltyDelta = onPenaltyDelta
        self.onAcceptRecommended = onAcceptRecommended
        self.onManualEntry = onManualEntry
        self.onAdvance = onAdvance
        self.onFairway = onFairway
        self.onSave = onSave
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("第 \(hole) 洞 · Par \(par)")
                .font(.headline.weight(.bold))

            stepContent

            Button(action: onCancel) {
                Text("取消").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
        .padding(8)
    }

    @ViewBuilder
    private var stepContent: some View {
        switch step {
        case .recommendation:
            VStack(spacing: 4) {
                Text("推荐 \(score) 杆")
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .monospacedDigit()
                Text("默认 \(putts) 推 · \(penalty) 罚")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            Button(action: onAcceptRecommended) {
                Text("确认 \(score) 杆").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)
            Button(action: onManualEntry) {
                Text("手动确认").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        case .score:
            Text("总杆").font(.caption).foregroundStyle(.secondary)
            scoreStepper
            nextButton
        case .putts:
            Text("推杆").font(.caption).foregroundStyle(.secondary)
            stepperRow(label: "推杆", value: putts) { onPuttsDelta($0) }
            nextButton
        case .fairway:
            Text("开球结果").font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 5) {
                fairwayButton("偏左", .left)
                fairwayButton("上球道", .hit)
                fairwayButton("偏右", .right)
            }
        case .penalty:
            Text("罚杆").font(.caption).foregroundStyle(.secondary)
            stepperRow(label: "罚杆", value: penalty) { onPenaltyDelta($0) }
            Button(action: onSave) {
                Text("保存本洞").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)
        }
    }

    private var scoreStepper: some View {
        HStack(spacing: 14) {
            stepButton("minus") { onScoreDelta(-1) }
            VStack(spacing: 0) {
                Text("\(score)")
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                    .monospacedDigit()
                Text(diffText)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: score - par))
            }
            .frame(maxWidth: .infinity)
            stepButton("plus") { onScoreDelta(1) }
        }
    }

    private var nextButton: some View {
        Button(action: onAdvance) {
            Text("下一步").frame(maxWidth: .infinity)
        }
        .tint(AICaddieDesignTokens.par)
    }

    private func fairwayButton(_ label: String, _ result: WatchFairwayResult) -> some View {
        Button(action: { onFairway(result) }) {
            Text(label).font(.caption2).frame(maxWidth: .infinity)
        }
        .tint(fairway == result ? AICaddieDesignTokens.par : .gray)
        .accessibilityLabel("\(label), \(result.rawValue)")
    }

    private var diffText: String {
        let diff = score - par
        if diff == 0 { return "标准杆" }
        return diff > 0 ? "+\(diff)" : "\(diff)"
    }

    private func stepperRow(label: String, value: Int, onDelta: @escaping (Int) -> Void) -> some View {
        HStack(spacing: 8) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Spacer()
            stepButton("minus") { onDelta(-1) }
            Text("\(value)").font(.body.monospacedDigit()).frame(minWidth: 22)
            stepButton("plus") { onDelta(1) }
        }
    }

    private func stepButton(_ systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
        }
        .buttonStyle(.bordered)
    }
}
