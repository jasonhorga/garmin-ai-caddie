import SwiftUI

/// round-13 (Watch standalone): the menu hub (spec screen ⑩) — a plain text list (S70-style, no
/// icons) of the round actions. Presentational VStack so it renders in ImageRenderer snapshots.
public struct WatchMenuView: View {
    public let onScorecard: () -> Void
    public let onHoleSelect: () -> Void
    public let onFinish: () -> Void
    public let onClose: () -> Void

    public init(
        onScorecard: @escaping () -> Void = {},
        onHoleSelect: @escaping () -> Void = {},
        onFinish: @escaping () -> Void = {},
        onClose: @escaping () -> Void = {}
    ) {
        self.onScorecard = onScorecard
        self.onHoleSelect = onHoleSelect
        self.onFinish = onFinish
        self.onClose = onClose
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("菜单").font(.headline.weight(.bold)).padding(.bottom, 2)
            menuRow("计分卡", action: onScorecard)
            menuRow("选洞", action: onHoleSelect)
            menuRow("结束本场", role: .destructive, action: onFinish)
            menuRow("继续打球", action: onClose)
        }
        .padding(6)
    }

    private func menuRow(_ title: String, role: ButtonRole? = nil, action: @escaping () -> Void) -> some View {
        Button(role: role, action: action) {
            HStack {
                Text(title).font(.body)
                Spacer()
            }
            .contentShape(Rectangle())
            .padding(.vertical, 7)
        }
        .buttonStyle(.plain)
        .overlay(alignment: .bottom) { Divider() }
    }
}
