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
    public let gpsUnavailable: Bool

    public init(
        frontYd: Int?,
        centerYd: Int?,
        backYd: Int?,
        caddieLine: String? = nil,
        bigText: Bool = false,
        gpsUnavailable: Bool = false
    ) {
        self.frontYd = frontYd
        self.centerYd = centerYd
        self.backYd = backYd
        self.caddieLine = caddieLine
        self.bigText = bigText
        self.gpsUnavailable = gpsUnavailable
    }

    public var body: some View {
        if frontYd == nil, centerYd == nil, backYd == nil {
            EmptyView()
        } else {
            GeometryReader { proxy in
                let approvedHeight = min(proxy.size.height, 198)
                Group {
                    if bigText {
                        big
                    } else {
                        normal
                    }
                }
                .frame(width: proxy.size.width, height: approvedHeight)
                .position(x: proxy.size.width / 2, y: approvedHeight / 2)
            }
            .ignoresSafeArea()
        }
    }

    // 抬手一眼:中间到旗大字,前 / 后翼在两侧,下面一句话球童。
    private var normal: some View {
        VStack(spacing: 1) {
            HStack(alignment: .lastTextBaseline, spacing: 12) {
                pip("前", frontYd)
                center(size: 52)
                pip("后", backYd)
            }
            if let caddieLine {
                Text(caddieLine)
                    .font(.system(size: 12, weight: .semibold))
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
            // Still an arm's-length hero, but leave a real glass margin around three digits. The
            // former 92 pt value visually touched the rounded face on the 45 mm runtime.
            center(size: 78)
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
                Text(WatchGeoMath.greenRangeText(centerYd))
                    .font(.system(size: size, weight: .heavy, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(AICaddieDesignTokens.par)
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                Text(centerStatus)
                    .font(.system(size: bigText ? 17 : 12, weight: .bold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
        }
    }

    private func pip(_ label: String, _ yd: Int?, compact: Bool = false) -> some View {
        VStack(spacing: 0) {
            Text(WatchGeoMath.greenRangeText(yd))
                .font(.system(size: compact ? 20 : 22, weight: .heavy, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.55)
            Text(label)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(.secondary)
        }
    }

    private var centerStatus: String {
        if gpsUnavailable { return "等待定位" }
        if WatchGeoMath.isBeyondUsefulGreenRange(centerYd) { return "离本洞较远" }
        return "中 · 码"
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
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.white.opacity(0.42))
                .offset(y: -1.5)
            Spacer().frame(height: 1)
            Text(WatchGeoMath.greenRangeText(centerYd))
                .font(.system(size: 68, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white.opacity(0.62))
                .lineLimit(1)
                .minimumScaleFactor(0.62)
                .frame(maxWidth: .infinity)
                .offset(y: -0.5)
            Text(alwaysOnStatus)
                .font(.system(size: 11))
                .foregroundStyle(.white.opacity(0.40))
                .offset(y: 1.5)
            Spacer(minLength: 18)
        }
        // Claim the full canvas, then restore the approved content origin below the system-time lane.
        // This keeps the runtime frame aligned with the approved renderer instead of letting watchOS
        // either push the whole stack down or place the header underneath the clock.
        .padding(.top, 39)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .ignoresSafeArea()
        .accessibilityElement(children: .combine)
    }

    private var alwaysOnStatus: String {
        if WatchGeoMath.isBeyondUsefulGreenRange(centerYd) { return "离本洞较远" }
        return centerYd == nil ? "等待定位" : "码 · 到果岭"
    }
}
