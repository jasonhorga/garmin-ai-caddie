import SwiftUI

/// round-13 (Watch standalone): the menu hub (spec screen ⑩) — a plain text list (S70-style, no
/// icons) of the round actions. The list scrolls so every action remains reachable as capabilities grow.
public struct WatchMenuView: View {
    public let hasCaddie: Bool
    public let hasHazards: Bool
    public let canRecordShot: Bool
    public let autoShotSupported: Bool
    public let autoShotEnabled: Bool
    public let autoShotStatus: String
    public let hasClubStats: Bool
    public let hasFlagDirection: Bool
    public let onRecordShot: () -> Void
    public let onScoreHole: () -> Void
    public let onCaddie: () -> Void
    public let onHazards: () -> Void
    public let onToggleAutoShot: () -> Void
    public let onScorecard: () -> Void
    public let onCurrentHoleShots: () -> Void
    public let onHoleSelect: () -> Void
    public let onClubStats: () -> Void
    public let onSettings: () -> Void
    public let onFlagDirection: () -> Void
    public let onFinish: () -> Void
    public let onAbandon: () -> Void
    public let onClose: () -> Void

    public init(
        hasCaddie: Bool = false,
        hasHazards: Bool = false,
        canRecordShot: Bool = false,
        autoShotSupported: Bool = false,
        autoShotEnabled: Bool = false,
        autoShotStatus: String = "本机不支持",
        hasClubStats: Bool = false,
        hasFlagDirection: Bool = false,
        onRecordShot: @escaping () -> Void = {},
        onScoreHole: @escaping () -> Void = {},
        onCaddie: @escaping () -> Void = {},
        onHazards: @escaping () -> Void = {},
        onToggleAutoShot: @escaping () -> Void = {},
        onScorecard: @escaping () -> Void = {},
        onCurrentHoleShots: @escaping () -> Void = {},
        onHoleSelect: @escaping () -> Void = {},
        onClubStats: @escaping () -> Void = {},
        onSettings: @escaping () -> Void = {},
        onFlagDirection: @escaping () -> Void = {},
        onFinish: @escaping () -> Void = {},
        onAbandon: @escaping () -> Void = {},
        onClose: @escaping () -> Void = {}
    ) {
        self.hasCaddie = hasCaddie
        self.hasHazards = hasHazards
        self.canRecordShot = canRecordShot
        self.autoShotSupported = autoShotSupported
        self.autoShotEnabled = autoShotEnabled
        self.autoShotStatus = autoShotStatus
        self.hasClubStats = hasClubStats
        self.hasFlagDirection = hasFlagDirection
        self.onRecordShot = onRecordShot
        self.onScoreHole = onScoreHole
        self.onCaddie = onCaddie
        self.onHazards = onHazards
        self.onToggleAutoShot = onToggleAutoShot
        self.onScorecard = onScorecard
        self.onCurrentHoleShots = onCurrentHoleShots
        self.onHoleSelect = onHoleSelect
        self.onClubStats = onClubStats
        self.onSettings = onSettings
        self.onFlagDirection = onFlagDirection
        self.onFinish = onFinish
        self.onAbandon = onAbandon
        self.onClose = onClose
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 2) {
                Text("菜单").font(.headline.weight(.bold)).padding(.bottom, 2)
                // Keep the approved S70-like round-navigation quartet on the first glance. The
                // additional correction and telemetry tools remain reachable immediately below.
                menuRow("计分卡", action: onScorecard)
                menuRow("选洞", action: onHoleSelect)
                menuRow("结束本场", role: .destructive, action: onFinish)
                menuRow("继续打球", action: onClose)
                menuRow("放弃本场", role: .destructive, action: onAbandon)

                Text("本洞")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.top, 5)
                menuRow("记一杆", action: onRecordShot)
                    .disabled(!canRecordShot)
                    .accessibilityHint(canRecordShot ? "先保存当前位置，再选择实际球杆" : "等待 GPS 定位")
                menuRow("本洞成绩", action: onScoreHole)
                menuRow("本洞击球", action: onCurrentHoleShots)
                if hasCaddie { menuRow("球童建议", action: onCaddie) }
                if hasHazards { menuRow("障碍", action: onHazards) }
                if hasFlagDirection { menuRow("旗向指引", action: onFlagDirection) }
                if hasClubStats { menuRow("球杆数据", action: onClubStats) }
                menuRow("设置", action: onSettings)
                menuRow(
                    "AutoShot Beta · \(autoShotEnabled ? autoShotStatus : (autoShotSupported ? "关闭" : "本机不支持"))",
                    action: onToggleAutoShot
                )
                .disabled(!autoShotSupported)
            }
            .padding(.horizontal, 6)
            .padding(.top, 2)
            .padding(.bottom, 8)
        }
        .ignoresSafeArea(edges: .top)
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
