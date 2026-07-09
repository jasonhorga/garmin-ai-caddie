import SwiftUI

/// round-12 P3.3 (Watch standalone): the round overview shown on the watch — the standalone entry that
/// ties a round together (course, current hole, progress, distance) with the core actions: score this
/// hole, move between holes, finish. Presentational (driven by the standalone round model); kept as a
/// VStack (not a List) so it renders in ImageRenderer snapshots for CI visual review.
public struct WatchRoundHomeView: View {
    public let courseName: String
    public let hole: Int
    public let par: Int
    public let holeCount: Int
    public let scoredHoles: Int
    public let toPar: Int?
    public let distanceText: String?
    public let pendingUploads: Int
    public let onScoreHole: () -> Void
    public let onPreviousHole: () -> Void
    public let onNextHole: () -> Void
    public let onFinish: () -> Void
    public let onMenu: () -> Void
    public let ringPips: [WatchRingPip]   // round-13: 18-hole edge ring (empty = no ring)
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
        ringPips: [WatchRingPip] = [],
        hasHoleMap: Bool = false,
        onHoleMap: @escaping () -> Void = {},
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
        self.ringPips = ringPips
        self.hasHoleMap = hasHoleMap
        self.onHoleMap = onHoleMap
        self.onScoreHole = onScoreHole
        self.onPreviousHole = onPreviousHole
        self.onNextHole = onNextHole
        self.onFinish = onFinish
        self.onMenu = onMenu
    }

    public var body: some View {
        if ringPips.isEmpty {
            content
        } else {
            WatchHoleRingView(pips: ringPips) { content }
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(courseName)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            HStack {
                Text("第 \(hole) 洞 · Par \(par)").font(.headline.weight(.bold))
                Spacer()
                if let distanceText {
                    Text(distanceText).font(.headline.monospacedDigit()).foregroundStyle(AICaddieDesignTokens.par)
                }
            }
            HStack(spacing: 6) {
                Text("已记 \(scoredHoles)/\(holeCount)").font(.caption2).foregroundStyle(.secondary)
                Text(toParText)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                if pendingUploads > 0 {
                    Spacer()
                    Label("\(pendingUploads)", systemImage: "arrow.up.circle")
                        .font(.caption2)
                        .foregroundStyle(AICaddieDesignTokens.offline)
                }
            }
            if hasHoleMap {
                Button(action: onHoleMap) {
                    Label("球道图", systemImage: "map.fill").frame(maxWidth: .infinity)
                }
                .tint(AICaddieDesignTokens.par)
            }
            Button(action: onScoreHole) {
                Text("记这一洞").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)
            HStack(spacing: 10) {
                Button(action: onPreviousHole) {
                    Image(systemName: "chevron.left")
                }
                Button(action: onNextHole) {
                    Image(systemName: "chevron.right")
                }
                Button(action: onMenu) {
                    Image(systemName: "list.bullet")
                }
                Spacer()
                Button(role: .destructive, action: onFinish) {
                    Text("结束").font(.caption2)
                }
            }
            .buttonStyle(.bordered)
        }
        .padding(8)
    }

    private var toParText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}
