import SwiftUI

/// round-13 (Watch standalone): the menu hub (spec screen ⑩) — a plain text list (S70-style, no
/// icons) of the round actions. The list scrolls so every action remains reachable as capabilities grow.
public struct WatchMenuView: View {
    public let hasCaddie: Bool
    public let hasHazards: Bool
    public let autoShotSupported: Bool
    public let autoShotEnabled: Bool
    public let autoShotStatus: String
    public let onCaddie: () -> Void
    public let onHazards: () -> Void
    public let onToggleAutoShot: () -> Void
    public let onScorecard: () -> Void
    public let onHoleSelect: () -> Void
    public let onFinish: () -> Void
    public let onClose: () -> Void

    public init(
        hasCaddie: Bool = false,
        hasHazards: Bool = false,
        autoShotSupported: Bool = false,
        autoShotEnabled: Bool = false,
        autoShotStatus: String = "本机不支持",
        onCaddie: @escaping () -> Void = {},
        onHazards: @escaping () -> Void = {},
        onToggleAutoShot: @escaping () -> Void = {},
        onScorecard: @escaping () -> Void = {},
        onHoleSelect: @escaping () -> Void = {},
        onFinish: @escaping () -> Void = {},
        onClose: @escaping () -> Void = {}
    ) {
        self.hasCaddie = hasCaddie
        self.hasHazards = hasHazards
        self.autoShotSupported = autoShotSupported
        self.autoShotEnabled = autoShotEnabled
        self.autoShotStatus = autoShotStatus
        self.onCaddie = onCaddie
        self.onHazards = onHazards
        self.onToggleAutoShot = onToggleAutoShot
        self.onScorecard = onScorecard
        self.onHoleSelect = onHoleSelect
        self.onFinish = onFinish
        self.onClose = onClose
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 2) {
                Text("菜单").font(.headline.weight(.bold)).padding(.bottom, 2)
                if hasCaddie { menuRow("球童建议", action: onCaddie) }
                if hasHazards { menuRow("障碍", action: onHazards) }
                menuRow(
                    "AutoShot Beta · \(autoShotEnabled ? autoShotStatus : (autoShotSupported ? "关闭" : "本机不支持"))",
                    action: onToggleAutoShot
                )
                .disabled(!autoShotSupported)
                menuRow("计分卡", action: onScorecard)
                menuRow("选洞", action: onHoleSelect)
                menuRow("结束本场", role: .destructive, action: onFinish)
                menuRow("继续打球", action: onClose)
            }
            .padding(.horizontal, 6)
            .padding(.top, 18)
            .padding(.bottom, 8)
        }
        .scrollIndicators(.hidden)
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
