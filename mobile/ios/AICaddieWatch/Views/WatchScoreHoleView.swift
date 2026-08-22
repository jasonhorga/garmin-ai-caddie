import SwiftUI

enum WatchScoreHoleLayout {
    /// watchOS owns the top-right corner for the system clock. Keep the score title inside the
    /// remaining glance area so it never reads as one string with the time (for example Par 42:04).
    static let systemTimeTrailingClearance: CGFloat = 48
}

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
    /// The ordered next hole when its first shot was captured before this hole was confirmed.
    public let candidateNextHole: Int?
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
        candidateNextHole: Int? = nil,
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
        self.candidateNextHole = candidateNextHole
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
        VStack(spacing: 5) {
            HStack(spacing: 5) {
                Button(action: onCancel) {
                    Image(systemName: "chevron.backward")
                        .font(.system(size: 14, weight: .heavy))
                        .frame(width: 32, height: 32)
                        .frame(
                            width: WatchDisplayGeometry.instrumentControlSize,
                            height: WatchDisplayGeometry.instrumentControlSize
                        )
                }
                .buttonStyle(.plain)
                .accessibilityLabel("取消记分")
                Text("H\(hole) · P\(par)")
                    .font(.system(size: 16, weight: .heavy))
                    .lineLimit(1)
                    .minimumScaleFactor(0.70)
                    .layoutPriority(1)
                Spacer(minLength: WatchScoreHoleLayout.systemTimeTrailingClearance)
            }

            stepContent
        }
        .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
        .padding(.top, 3)
        .padding(.bottom, 7)
        // Padding must participate in the proposed Watch content size. Putting it outside the
        // full-screen frame makes the view 16 pt taller than watchOS's safe content viewport and
        // clips the recommendation actions at the bottom in the real runtime.
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        // The title already reserves the top-right clock lane. Reclaim the unused top-left safe
        // area so watchOS does not push the whole confirmation stack down and crop its bottom row.
        .ignoresSafeArea(edges: .top)
    }

    var stepLabel: String {
        switch step {
        case .recommendation:
            return "推荐成绩"
        case .score:
            return "1/\(manualStepCount) · 总杆"
        case .putts:
            return "2/\(manualStepCount) · 推杆"
        case .fairway:
            return "3/4 · 开球结果"
        case .penalty:
            return "\(par == 3 ? 3 : 4)/\(manualStepCount) · 罚杆"
        }
    }

    private var manualStepCount: Int { par == 3 ? 3 : 4 }

    @ViewBuilder
    private var stepContent: some View {
        switch step {
        case .recommendation:
            // Two action rows must both clear the rounded 45 mm screen edge. The former 6 pt
            // rhythm pushed the secondary row roughly 3 pt below the real simulator viewport.
            VStack(spacing: 3) {
                Text(stepLabel)
                    .font(.system(size: 13, weight: .heavy))
                    .foregroundStyle(.secondary)
                VStack(spacing: 0) {
                    Text("\(score)")
                        .font(.system(size: 44, weight: .heavy, design: .rounded))
                        .monospacedDigit()
                    Text(diffText)
                        .font(.system(size: 14, weight: .heavy, design: .rounded))
                        .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: score - par))
                }
                Text(recommendationNote)
                    .font(.system(size: 11, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(candidateNextHole == nil ? Color.secondary : AICaddieDesignTokens.par)
                Spacer(minLength: 0)
                actionButton("确认 \(score) 杆", primary: true, action: onAcceptRecommended)
                actionButton("修改详情", action: onManualEntry)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .score:
            numericStep(
                value: score,
                detail: diffText,
                onDelta: onScoreDelta,
                primaryTitle: "下一步",
                onPrimary: onAdvance
            )
        case .putts:
            numericStep(
                value: putts,
                onDelta: onPuttsDelta,
                primaryTitle: "下一步",
                onPrimary: onAdvance
            )
        case .fairway:
            VStack(spacing: 5) {
                Text(stepLabel)
                    .font(.system(size: 14, weight: .heavy))
                    .foregroundStyle(.secondary)
                HStack(spacing: 5) {
                    fairwayButton("偏左", .left)
                    fairwayButton("上球道", .hit)
                    fairwayButton("偏右", .right)
                }
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .penalty:
            numericStep(
                value: penalty,
                onDelta: onPenaltyDelta,
                primaryTitle: "保存本洞",
                onPrimary: onSave
            )
        }
    }

    private func numericStep(
        value: Int,
        detail: String? = nil,
        onDelta: @escaping (Int) -> Void,
        primaryTitle: String,
        onPrimary: @escaping () -> Void
    ) -> some View {
        VStack(spacing: 5) {
            Text(stepLabel)
                .font(.system(size: 14, weight: .heavy))
                .foregroundStyle(.secondary)
            HStack(spacing: 14) {
                stepButton("minus") { onDelta(-1) }
                VStack(spacing: 0) {
                    Text("\(value)")
                        .font(.system(size: 44, weight: .heavy, design: .rounded))
                        .monospacedDigit()
                    if let detail {
                        Text(detail)
                            .font(.system(size: 14, weight: .heavy, design: .rounded))
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: score - par))
                    }
                }
                .frame(maxWidth: .infinity)
                stepButton("plus") { onDelta(1) }
            }
            Spacer(minLength: 0)
            actionButton(primaryTitle, primary: true, action: onPrimary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func fairwayButton(_ label: String, _ result: WatchFairwayResult) -> some View {
        Button(action: { onFairway(result) }) {
            Text(label)
                .font(.system(size: 15, weight: .heavy))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .buttonStyle(.plain)
        .frame(height: 48)
        .background(
            RoundedRectangle(cornerRadius: 15)
                .fill(fairway == result ? AICaddieDesignTokens.par : Color.white.opacity(0.27))
        )
        .accessibilityLabel("\(label), \(result.rawValue)")
    }

    private var diffText: String {
        let diff = score - par
        if diff == 0 { return "标准杆" }
        return diff > 0 ? "+\(diff)" : "\(diff)"
    }

    private var recommendationNote: String {
        if let candidateNextHole {
            return "第 \(candidateNextHole) 洞首杆已暂存"
        }
        return "默认 \(putts) 推 · \(penalty) 罚"
    }

    private func actionButton(
        _ title: String,
        primary: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 15, weight: .heavy))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .buttonStyle(.plain)
        .frame(height: 42)
        .background(
            Capsule()
                .fill(primary ? AICaddieDesignTokens.par : Color.white.opacity(0.27))
        )
    }

    private func stepButton(_ systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.title2.weight(.heavy))
                .foregroundStyle(.white)
                .frame(width: 48, height: 48)
        }
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 13)
                .fill(Color.white.opacity(0.27))
        )
    }
}
