import SwiftUI

/// round-15 (unified tri-surface spec §四 第一层「抬手一眼」): front / center / back green distances as
/// the HERO of the playing screen — center biggest (matching Garmin S70), front/back flanking — plus a
/// one-line caddie note. `bigText` (大字模式) blows the center number up for reading at arm's length /
/// in bright sun. Pure presentational: the parent owns the toggle so both states are snapshot-testable.
/// A hole without geometry (all three nil) renders nothing rather than "0 码" noise.
public struct WatchDistanceHero: View {
    public let frontYd: Int?
    public let centerYd: Int?
    public let backYd: Int?
    public let caddieLine: String?
    public let bigText: Bool

    public init(
        frontYd: Int?,
        centerYd: Int?,
        backYd: Int?,
        caddieLine: String? = nil,
        bigText: Bool = false
    ) {
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.caddieLine = caddieLine
        self.bigText = bigText
    }

    public var body: some View {
        if frontYd == nil, centerYd == nil, backYd == nil {
            EmptyView()
        } else if bigText {
            big
        } else {
            normal
        }
    }

    // 抬手一眼:中间到旗大字,前 / 后翼在两侧,下面一句话球童。
    private var normal: some View {
        VStack(spacing: 1) {
            HStack(alignment: .lastTextBaseline, spacing: 12) {
                pip("前", frontYd)
                center(size: 48)
                pip("后", backYd)
            }
            if let caddieLine {
                Text(caddieLine)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
        }
        .frame(maxWidth: .infinity)
    }

    // 大字模式:中间数字撑满,前 / 后缩到底部一行。
    private var big: some View {
        VStack(spacing: 2) {
            center(size: 92)
            HStack(spacing: 16) {
                pip("前", frontYd, compact: true)
                pip("后", backYd, compact: true)
            }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func center(size: CGFloat) -> some View {
        if let centerYd {
            VStack(spacing: -1) {
                Text("\(centerYd)")
                    .font(.system(size: size, weight: .heavy, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(AICaddieDesignTokens.par)
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                Text("中 · 码")
                    .font(bigText ? .headline : .caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func pip(_ label: String, _ yd: Int?, compact: Bool = false) -> some View {
        VStack(spacing: 0) {
            Text(yd.map(String.init) ?? "–")
                .font((compact ? Font.headline : Font.title3).weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(.primary)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}

/// Low-luminance current-hole glance for Apple Watch Always On. It deliberately removes colour,
/// map detail, controls, and secondary distances so the approved center-green fact remains readable
/// without presenting stale Tee data as a live range.
public struct WatchAlwaysOnDistanceView: View {
    public let hole: Int
    public let par: Int
    public let centerYd: Int?

    public init(hole: Int, par: Int, centerYd: Int?) {
        self.hole = hole
        self.par = par
        self.centerYd = centerYd
    }

    public var body: some View {
        VStack(spacing: 0) {
            Text("第\(hole)洞 · P\(par)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.42))
            Spacer().frame(height: 18)
            Text(centerYd.map(String.init) ?? "—")
                .font(.system(size: 68, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white.opacity(0.62))
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            Text(centerYd == nil ? "等待定位" : "码 · 到果岭")
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.40))
            Spacer(minLength: 18)
        }
        .padding(.top, 39)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .accessibilityElement(children: .combine)
    }
}
