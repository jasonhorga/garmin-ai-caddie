import SwiftUI

/// round-13 (Watch standalone): 选洞 — tap any hole to make it active (spec screen ⑧). A plain
/// VStack of eager HStack rows (not a LazyVGrid) so it renders in ImageRenderer snapshots.
public struct WatchHoleSelectView: View {
    public let holes: [Int]
    public let activeHole: Int
    public let perRow: Int
    public let onSelect: (Int) -> Void
    public let onBack: () -> Void

    public init(
        holes: [Int],
        activeHole: Int,
        perRow: Int = 5,
        onSelect: @escaping (Int) -> Void = { _ in },
        onBack: @escaping () -> Void = {}
    ) {
        self.holes = holes
        self.activeHole = activeHole
        self.perRow = perRow
        self.onSelect = onSelect
        self.onBack = onBack
    }

    private var rows: [[Int]] {
        stride(from: 0, to: holes.count, by: perRow).map { start in
            Array(holes[start..<min(start + perRow, holes.count)])
        }
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("选洞").font(.headline.weight(.bold))
                Spacer()
                Button(action: onBack) { Image(systemName: "xmark.circle.fill") }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(spacing: 6) {
                    ForEach(row, id: \.self) { hole in
                        Button { onSelect(hole) } label: {
                            Text("\(hole)")
                                .font(.caption.monospacedDigit().weight(.semibold))
                                .frame(maxWidth: .infinity, minHeight: 30)
                                .background(hole == activeHole ? AICaddieDesignTokens.par : AICaddieDesignTokens.par.opacity(0.16))
                                .foregroundStyle(hole == activeHole ? .white : .primary)
                                .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(6)
    }
}
