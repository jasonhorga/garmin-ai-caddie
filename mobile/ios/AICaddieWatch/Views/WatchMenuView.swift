import SwiftUI

/// The in-round equivalent of S70's Golf Menu. S70 opens this list with its physical Action key;
/// Apple Watch opens it from the compact Hole Root menu control and keeps a visible Back equivalent.
public struct WatchMenuView: View {
    enum Item: String, Hashable {
        case recordShot = "记一杆"
        case viewGreen = "查看果岭"
        case scoreHole = "本洞成绩"
        case caddie = "球童建议"
        case hazards = "障碍与铺垫"
        case currentHoleShots = "本洞击球"
        case holeSelect = "选洞"
        case scorecard = "计分卡"
        case flagDirection = "旗向指引"
        case clubStats = "球杆数据"
        case settings = "设置"
        case moreTools = "更多工具"
        case finish = "结束本场"
    }

    public let hasCaddie: Bool
    public let hasViewGreen: Bool
    public let hasHazards: Bool
    public let canRecordShot: Bool
    public let hasClubStats: Bool
    public let hasFlagDirection: Bool
    public let onRecordShot: () -> Void
    public let onViewGreen: () -> Void
    public let onScoreHole: () -> Void
    public let onCaddie: () -> Void
    public let onHazards: () -> Void
    public let onScorecard: () -> Void
    public let onCurrentHoleShots: () -> Void
    public let onHoleSelect: () -> Void
    public let onClubStats: () -> Void
    public let onSettings: () -> Void
    public let onFlagDirection: () -> Void
    public let onFinish: () -> Void
    public let onBack: () -> Void

    @State private var showingMoreTools = false

    public init(
        hasCaddie: Bool = false,
        hasViewGreen: Bool = false,
        hasHazards: Bool = false,
        canRecordShot: Bool = false,
        hasClubStats: Bool = false,
        hasFlagDirection: Bool = false,
        onRecordShot: @escaping () -> Void = {},
        onViewGreen: @escaping () -> Void = {},
        onScoreHole: @escaping () -> Void = {},
        onCaddie: @escaping () -> Void = {},
        onHazards: @escaping () -> Void = {},
        onScorecard: @escaping () -> Void = {},
        onCurrentHoleShots: @escaping () -> Void = {},
        onHoleSelect: @escaping () -> Void = {},
        onClubStats: @escaping () -> Void = {},
        onSettings: @escaping () -> Void = {},
        onFlagDirection: @escaping () -> Void = {},
        onFinish: @escaping () -> Void = {},
        onBack: @escaping () -> Void = {}
    ) {
        self.hasCaddie = hasCaddie
        self.hasViewGreen = hasViewGreen
        self.hasHazards = hasHazards
        self.canRecordShot = canRecordShot
        self.hasClubStats = hasClubStats
        self.hasFlagDirection = hasFlagDirection
        self.onRecordShot = onRecordShot
        self.onViewGreen = onViewGreen
        self.onScoreHole = onScoreHole
        self.onCaddie = onCaddie
        self.onHazards = onHazards
        self.onScorecard = onScorecard
        self.onCurrentHoleShots = onCurrentHoleShots
        self.onHoleSelect = onHoleSelect
        self.onClubStats = onClubStats
        self.onSettings = onSettings
        self.onFlagDirection = onFlagDirection
        self.onFinish = onFinish
        self.onBack = onBack
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Button(action: navigateBack) {
                        Image(systemName: "chevron.backward")
                            .font(.system(size: 12, weight: .bold))
                            .frame(width: 26, height: 26)
                            .background(Color.black.opacity(0.68), in: Circle())
                            .frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(showingMoreTools ? "返回高尔夫菜单" : "返回球洞")
                    Text(showingMoreTools ? "更多" : "菜单")
                        .font(.system(size: 15, weight: .bold))
                        .lineLimit(1)
                        .accessibilityLabel(showingMoreTools ? "更多工具" : "高尔夫菜单")
                    Spacer(minLength: 48)
                }
                .padding(.bottom, 2)

                // The root menu keeps only the Garmin-like in-play decisions. Manual shot capture is
                // already a fixed Hole Root control; diagnostic/correction tools live one level down.
                ForEach(renderedItems, id: \.self) { item in
                    menuRow(item)
                }
            }
            .padding(.horizontal, 8)
            .padding(.top, 2)
            .padding(.bottom, 8)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard WatchEdgeBackGesture.shouldTrigger(
                        startX: value.startLocation.x,
                        translation: value.translation
                    ) else { return }
                    navigateBack()
                }
        )
        .accessibilityIdentifier("watch-golf-menu")
    }

    private var renderedItems: [Item] {
        if showingMoreTools {
            return Self.moreToolItems(
                hasClubStats: hasClubStats,
                hasFlagDirection: hasFlagDirection
            )
        }
        return Self.visibleItems(
            hasViewGreen: hasViewGreen,
            hasCaddie: hasCaddie,
            hasHazards: hasHazards,
            hasClubStats: hasClubStats,
            hasFlagDirection: hasFlagDirection
        )
    }

    /// The same list drives rendering and tests. Duplicate shot capture and low-frequency diagnostics
    /// must not creep back onto the first level merely because the list can scroll.
    static func visibleItems(
        hasViewGreen: Bool = false,
        hasCaddie: Bool,
        hasHazards: Bool,
        hasClubStats: Bool,
        hasFlagDirection: Bool
    ) -> [Item] {
        var items: [Item] = []
        if hasViewGreen { items.append(.viewGreen) }
        if hasCaddie { items.append(.caddie) }
        items += [.holeSelect, .scorecard]
        if hasHazards { items.append(.hazards) }
        items += [.scoreHole, .moreTools, .finish]
        return items
    }

    static func moreToolItems(
        hasClubStats: Bool,
        hasFlagDirection: Bool
    ) -> [Item] {
        var items: [Item] = [.currentHoleShots]
        if hasFlagDirection { items.append(.flagDirection) }
        if hasClubStats { items.append(.clubStats) }
        items.append(.settings)
        return items
    }

    private func menuRow(_ item: Item) -> some View {
        Button(role: item == .finish ? .destructive : nil, action: action(for: item)) {
            HStack {
                Text(item.rawValue)
                    .font(.system(size: 14, weight: .regular))
                    .lineLimit(1)
                Spacer()
                if item == .moreTools {
                    Image(systemName: "chevron.forward")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
            }
            .contentShape(Rectangle())
            .padding(.vertical, 7)
        }
        .buttonStyle(.plain)
        .disabled(item == .recordShot && !canRecordShot)
        .accessibilityHint(
            item == .recordShot
                ? (canRecordShot ? "先保存当前位置，再选择实际球杆" : "等待 GPS 定位")
                : ""
        )
        .overlay(alignment: .bottom) { Divider() }
    }

    private func action(for item: Item) -> () -> Void {
        switch item {
        case .recordShot: return onRecordShot
        case .viewGreen: return onViewGreen
        case .scoreHole: return onScoreHole
        case .caddie: return onCaddie
        case .hazards: return onHazards
        case .currentHoleShots: return onCurrentHoleShots
        case .holeSelect: return onHoleSelect
        case .scorecard: return onScorecard
        case .flagDirection: return onFlagDirection
        case .clubStats: return onClubStats
        case .settings: return onSettings
        case .moreTools: return { showingMoreTools = true }
        case .finish: return onFinish
        }
    }

    private func navigateBack() {
        if showingMoreTools {
            showingMoreTools = false
        } else {
            onBack()
        }
    }
}
