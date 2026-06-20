import SwiftUI

/// round-12 P3.3 (Watch standalone): the per-hole scoring screen reached from `WatchRoundHomeView`'s
/// "记这一洞". Big stroke count with ± (the primary action, Digital-Crown / tap friendly), compact
/// putts / penalty steppers, then save. Presentational (driven by the standalone round model); kept as a
/// VStack (not a List) so it renders in ImageRenderer snapshots for CI visual review.
public struct WatchScoreHoleView: View {
    public let hole: Int
    public let par: Int
    public let score: Int
    public let putts: Int
    public let penalty: Int
    public let onScoreDelta: (Int) -> Void
    public let onPuttsDelta: (Int) -> Void
    public let onPenaltyDelta: (Int) -> Void
    public let onSave: () -> Void
    public let onCancel: () -> Void

    public init(
        hole: Int,
        par: Int,
        score: Int,
        putts: Int,
        penalty: Int,
        onScoreDelta: @escaping (Int) -> Void = { _ in },
        onPuttsDelta: @escaping (Int) -> Void = { _ in },
        onPenaltyDelta: @escaping (Int) -> Void = { _ in },
        onSave: @escaping () -> Void = {},
        onCancel: @escaping () -> Void = {}
    ) {
        self.hole = hole
        self.par = par
        self.score = score
        self.putts = putts
        self.penalty = penalty
        self.onScoreDelta = onScoreDelta
        self.onPuttsDelta = onPuttsDelta
        self.onPenaltyDelta = onPenaltyDelta
        self.onSave = onSave
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("第 \(hole) 洞 · Par \(par)")
                .font(.headline.weight(.bold))

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

            stepperRow(label: "推杆", value: putts) { onPuttsDelta($0) }
            stepperRow(label: "罚杆", value: penalty) { onPenaltyDelta($0) }

            Button(action: onSave) {
                Text("保存本洞").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)
            Button(action: onCancel) {
                Text("取消").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
        .padding(8)
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
