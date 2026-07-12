import SwiftUI

/// round-13 (Watch standalone): 计分卡逐洞列表 — tap a hole to jump to it (spec screen ⑨).
/// Presentational + a plain VStack (no List) so it renders in ImageRenderer snapshots; the
/// container wraps it in a ScrollView for the real watch.
public struct WatchScorecardRow: Identifiable, Equatable {
    public var id: Int { hole }
    public let hole: Int
    public let par: Int
    public let score: Int

    public init(hole: Int, par: Int, score: Int) {
        self.hole = hole
        self.par = par
        self.score = score
    }
}

public struct WatchScorecardView: View {
    public let holes: [WatchScorecardRow]
    public let totalToPar: Int?
    public let onSelectHole: (Int) -> Void
    public let onBack: () -> Void

    public init(
        holes: [WatchScorecardRow],
        totalToPar: Int? = nil,
        onSelectHole: @escaping (Int) -> Void = { _ in },
        onBack: @escaping () -> Void = {}
    ) {
        self.holes = holes
        self.totalToPar = totalToPar
        self.onSelectHole = onSelectHole
        self.onBack = onBack
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text("计分卡").font(.headline.weight(.bold))
                Spacer()
                Text(totalToParText)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: totalToPar))
                Button(action: onBack) { Image(systemName: "xmark.circle.fill") }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
            }
            ForEach(holes) { row in
                Button { onSelectHole(row.hole) } label: {
                    HStack(spacing: 6) {
                        Text("\(row.hole)").font(.caption.monospacedDigit())
                            .frame(width: 22, alignment: .leading).foregroundStyle(.secondary)
                        Text("Par \(row.par)").font(.caption2).foregroundStyle(.secondary)
                        Spacer()
                        if row.score > 0 {
                            // 形状接线(合并 Opus 地基 + Codex 接线思路):逐洞分用色盲安全的 ScoreChip
                            // (圈=低于标准杆 / 无框=Par / 方=柏忌·双 / 三角=三柏忌+),Opus 的正确映射。
                            ScoreChipView(toPar: row.score - row.par, text: "\(row.score)", diameter: 26)
                        } else {
                            Text("—")
                                .font(.body.monospacedDigit().weight(.semibold))
                                .foregroundStyle(.secondary)
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                Divider()
            }
        }
        .padding(6)
    }

    private var totalToParText: String {
        guard let totalToPar else { return "" }
        if totalToPar == 0 { return "E" }
        return totalToPar > 0 ? "+\(totalToPar)" : "\(totalToPar)"
    }
}
