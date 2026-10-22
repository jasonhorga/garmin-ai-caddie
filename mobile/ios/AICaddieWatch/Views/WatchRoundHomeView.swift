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
    public let courseDataPending: Bool
    public let pendingUploads: Int
    public let canRecordShot: Bool
    public let manualShotNeedsGPS: Bool
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
        courseDataPending: Bool = false,
        pendingUploads: Int = 0,
        hasHoleMap: Bool = false,
        canRecordShot: Bool = false,
        manualShotNeedsGPS: Bool = false,
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
        self.courseDataPending = courseDataPending
        self.pendingUploads = pendingUploads
        self.hasHoleMap = hasHoleMap
        self.canRecordShot = canRecordShot
        self.manualShotNeedsGPS = manualShotNeedsGPS
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
                    Text(courseDataPending ? "H\(hole) · 等待球场数据" : "H\(hole) · P\(par)")
                        .font(.system(size: 18, weight: .black))
                        .lineLimit(1)
                        .minimumScaleFactor(0.62)
                        .layoutPriority(1)
                    if toPar != nil {
                        scoreLabel
                    }
                    Spacer(minLength: WatchRoundHomeLayout.systemTimeTrailingClearance)
                }
                Spacer(minLength: 2)
                distanceValueLabel
                distanceStatusLabel
                Spacer(minLength: 2)
                HStack {
                    compactControl(
                        systemName: "line.3.horizontal",
                        label: "高尔夫菜单",
                        primary: false,
                        action: onMenu
                    )
                    Spacer()
                    compactControl(
                        systemName: "plus",
                        label: "手动记杆",
                        dimmed: !canRecordShot,
                        primary: true,
                        action: onRecordShot
                    )
                    .overlay(alignment: .top) {
                        if manualShotNeedsGPS { WatchManualShotGPSPrompt() }
                    }
                    .accessibilityIdentifier("watch-hole-record-shot")
                }
            }
            .frame(width: safeRect.width, height: safeRect.height)
            .position(x: safeRect.midX, y: safeRect.midY)
        }
        .background(Color.black)
        .ignoresSafeArea()
        .accessibilityIdentifier("watch-score-only-root")
    }

    // Keep the range's type size independent of a cold-GPS/loading status on the compact face.
    var distanceValueText: String {
        distanceText?.components(separatedBy: " · ").first ?? "—"
    }

    var distanceStatusText: String {
        if courseDataPending { return "等待球场数据" }
        let parts = distanceText?.components(separatedBy: " · ") ?? []
        if parts.count > 1 { return parts.dropFirst().joined(separator: " · ") }
        return distanceText == nil ? "距离不可用" : "到果岭中"
    }

    var distanceValueLabel: some View {
        Text(distanceValueText)
            .font(.system(size: distanceText == nil ? 46 : 45, weight: .black, design: .rounded))
            .monospacedDigit()
            .lineLimit(1)
            .minimumScaleFactor(0.52)
            .allowsTightening(false)
            .foregroundStyle(distanceText == nil ? Color.secondary : Color.white)
    }

    var distanceStatusLabel: some View {
        Text(distanceStatusText)
            .font(.system(size: 14, weight: .bold))
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .minimumScaleFactor(0.75)
            // The 等待定位 capsule over ＋ already says it; keep the line's space so nothing moves.
            .opacity(manualShotNeedsGPS ? 0 : 1)
    }

    var scoreLabel: some View {
        Text(toParText)
            .font(.system(size: 16, weight: .black, design: .rounded))
            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .layoutPriority(2)
    }

    private func compactControl(
        systemName: String,
        label: String,
        dimmed: Bool = false,
        primary: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 22, weight: .black))
                .foregroundStyle(primary ? Color.black : Color.white)
                .frame(width: WatchDisplayGeometry.instrumentVisualControlSize, height: WatchDisplayGeometry.instrumentVisualControlSize)
                .background(primary ? AICaddieDesignTokens.hudGreen : Color.white.opacity(0.14), in: Circle())
                .overlay(Circle().stroke(primary ? AICaddieDesignTokens.hudGreen.opacity(0.9) : Color.white.opacity(0.32), lineWidth: 1.2))
                .frame(
                    width: WatchDisplayGeometry.instrumentControlSize,
                    height: WatchDisplayGeometry.instrumentControlSize
                )
        }
        .buttonStyle(.plain)
        .opacity(dimmed ? 0.45 : 1)
        .accessibilityLabel(label)
    }

    private var toParText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}
