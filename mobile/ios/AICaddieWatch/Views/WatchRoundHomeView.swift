import SwiftUI

/// round-12 P3.3 (Watch standalone): the round overview shown on the watch — the standalone entry that
/// ties a round together (course, current hole, progress, distance) with the core actions: score this
/// hole, move between holes, finish. Presentational (driven by the standalone round model); kept as a
/// VStack (not a List) so it renders in ImageRenderer snapshots for CI visual review.
///
/// round-15 (unified spec §四 第一层): leads with the front/center/back green distances as a HERO
/// (`WatchDistanceHero`) — the "抬手一眼" glance — with a 大字模式 toggle that blows the center number up
/// and hides the secondary chrome. Falls back to the single `distanceText` when a hole has no geometry.
public struct WatchRoundHomeView: View {
    public let courseName: String
    public let hole: Int
    public let par: Int
    public let holeCount: Int
    public let scoredHoles: Int
    public let toPar: Int?
    public let distanceText: String?
    public let frontYd: Int?
    public let centerYd: Int?
    public let backYd: Int?
    public let caddieLine: String?
    public let pendingUploads: Int
    public let onScoreHole: () -> Void
    public let onPreviousHole: () -> Void
    public let onNextHole: () -> Void
    public let onFinish: () -> Void
    public let onMenu: () -> Void
    public let ringPips: [WatchRingPip]   // round-13: 18-hole edge ring (empty = no ring)

    @State private var bigText = false

    public init(
        courseName: String,
        hole: Int,
        par: Int,
        holeCount: Int,
        scoredHoles: Int,
        toPar: Int?,
        distanceText: String? = nil,
        frontYd: Int? = nil,
        centerYd: Int? = nil,
        backYd: Int? = nil,
        caddieLine: String? = nil,
        pendingUploads: Int = 0,
        ringPips: [WatchRingPip] = [],
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
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.caddieLine = caddieLine
        self.pendingUploads = pendingUploads
        self.ringPips = ringPips
        self.onScoreHole = onScoreHole
        self.onPreviousHole = onPreviousHole
        self.onNextHole = onNextHole
        self.onFinish = onFinish
        self.onMenu = onMenu
    }

    private var hasHero: Bool { frontYd != nil || centerYd != nil || backYd != nil }

    public var body: some View {
        if ringPips.isEmpty || bigText {
            content   // 大字模式:去掉外圈成绩环,整屏留给距离
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
                if hasHero {
                    Button { bigText.toggle() } label: {
                        Image(systemName: bigText ? "arrow.down.right.and.arrow.up.left" : "textformat.size")
                            .font(.headline)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(bigText ? AICaddieDesignTokens.par : .secondary)
                } else if let distanceText {
                    Text(distanceText).font(.headline.monospacedDigit()).foregroundStyle(AICaddieDesignTokens.par)
                }
            }
            if hasHero {
                WatchDistanceHero(
                    frontYd: frontYd, centerYd: centerYd, backYd: backYd,
                    caddieLine: caddieLine, bigText: bigText
                )
                .padding(.vertical, 2)
            }
            if !bigText {
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
            }
            Button(action: onScoreHole) {
                Text("记这一洞").frame(maxWidth: .infinity)
            }
            .tint(AICaddieDesignTokens.par)
            if !bigText {
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
        }
        .padding(8)
    }

    private var toParText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}
