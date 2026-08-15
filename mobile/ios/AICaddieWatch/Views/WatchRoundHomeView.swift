import SwiftUI

enum WatchRoundHomeLayout {
    static let systemTimeTrailingClearance: CGFloat = 48
}

/// Honest current-hole fallback when neither a map nor a live green distance is available. It is not a
/// second dashboard: lifecycle, hole navigation and scoring stay in Golf Menu, just as on S70.
public struct WatchRoundHomeView: View {
    public let courseName: String
    public let hole: Int
    public let par: Int
    public let holeCount: Int
    public let scoredHoles: Int
    public let toPar: Int?
    public let distanceText: String?
    public let pendingUploads: Int
    public let canRecordShot: Bool
    public let onRecordShot: () -> Void
    public let onScoreHole: () -> Void
    public let onPreviousHole: () -> Void
    public let onNextHole: () -> Void
    public let onFinish: () -> Void
    public let onMenu: () -> Void
    public let hasHoleMap: Bool           // watch P1b: 本洞有真几何底图时才显示「球道图」入口
    public let onHoleMap: () -> Void

    public init(
        courseName: String,
        hole: Int,
        par: Int,
        holeCount: Int,
        scoredHoles: Int,
        toPar: Int?,
        distanceText: String? = nil,
        pendingUploads: Int = 0,
        hasHoleMap: Bool = false,
        canRecordShot: Bool = false,
        onHoleMap: @escaping () -> Void = {},
        onRecordShot: @escaping () -> Void = {},
        onScoreHole: @escaping () -> Void = {},
        onPreviousHole: @escaping () -> Void = {},
        onNextHole: @escaping () -> Void = {},
        onFinish: @escaping () -> Void = {},
        onMenu: @escaping () -> Void = {}
    ) {
        self.courseName = courseName
        self.hole = hole
        self.par = par
        self.holeCount = holeCount
        self.scoredHoles = scoredHoles
        self.toPar = toPar
        self.distanceText = distanceText
        self.pendingUploads = pendingUploads
        self.hasHoleMap = hasHoleMap
        self.canRecordShot = canRecordShot
        self.onHoleMap = onHoleMap
        self.onRecordShot = onRecordShot
        self.onScoreHole = onScoreHole
        self.onPreviousHole = onPreviousHole
        self.onNextHole = onNextHole
        self.onFinish = onFinish
        self.onMenu = onMenu
    }

    public var body: some View {
        content
    }

    private var content: some View {
        GeometryReader { proxy in
            let safeRect = WatchDisplayGeometry.contentRect(in: proxy.size)
            VStack(spacing: 5) {
                HStack(spacing: 7) {
                    Text("H\(hole) · P\(par)")
                        .font(.system(size: 13, weight: .bold))
                        .lineLimit(1)
                    if toPar != nil {
                        Text(toParText)
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                    }
                    Spacer(minLength: WatchRoundHomeLayout.systemTimeTrailingClearance)
                }
                Spacer(minLength: 2)
                Text(distanceText ?? "—")
                    .font(.system(size: distanceText == nil ? 34 : 30, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .lineLimit(1)
                    .foregroundStyle(distanceText == nil ? Color.secondary : Color.white)
                Text(distanceText == nil ? "距离不可用" : "到果岭中")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
                Spacer(minLength: 2)
                HStack {
                    compactControl(
                        systemName: "line.3.horizontal",
                        label: "球局菜单",
                        isEnabled: true,
                        action: onMenu
                    )
                    Spacer()
                    compactControl(
                        systemName: "plus",
                        label: "手动记杆",
                        isEnabled: canRecordShot,
                        action: onRecordShot
                    )
                }
            }
            .frame(width: safeRect.width, height: safeRect.height)
            .position(x: safeRect.midX, y: safeRect.midY)
        }
        .background(Color.black)
        .ignoresSafeArea()
        .accessibilityIdentifier("watch-score-only-root")
    }

    private func compactControl(
        systemName: String,
        label: String,
        isEnabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 12, weight: .bold))
                .frame(width: 34, height: 34)
                .background(Color.white.opacity(0.12), in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(!isEnabled)
        .opacity(isEnabled ? 1 : 0.45)
        .accessibilityLabel(label)
    }

    private var toParText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}
