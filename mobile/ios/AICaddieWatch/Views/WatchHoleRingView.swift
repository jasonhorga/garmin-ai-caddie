import SwiftUI

/// round-13 (Watch standalone): the 18-hole ring that hugs the rounded-rect watch screen EDGE
/// (spec screen ①, the user's explicit "贴着屏幕边缘,不要一个居中的圆"). Each hole is drawn as a thin
/// short capsule placed on the physical rounded-rectangle perimeter — so the marks ride the visible
/// rim and stay slim enough not to cover the centre distance/number (the user's
/// "沿着手表边缘做一些小横线,做得细一点,这样不会覆盖其他元素"). 1号洞从3点位置起、顺时针到12点结束;
/// 当前洞用更长更亮的白色刻度高亮,已记洞按成绩着色。Plain shape layers → renders in ImageRenderer snapshots.
public struct WatchRingPip: Identifiable, Equatable {
    public var id: Int { hole }
    public let hole: Int
    public let toPar: Int?   // nil = not yet scored
    public let isCurrent: Bool

    public init(hole: Int, toPar: Int?, isCurrent: Bool) {
        self.hole = hole
        self.toPar = toPar
        self.isCurrent = isCurrent
    }
}

public struct WatchHoleRingView<Center: View>: View {
    public let pips: [WatchRingPip]
    public let center: Center

    public init(pips: [WatchRingPip], @ViewBuilder center: () -> Center) {
        self.pips = pips
        self.center = center()
    }

    public var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let inset: CGFloat = 6
            let centerPoint = CGPoint(x: w / 2, y: h / 2)
            let halfW = max(0, w / 2 - inset)
            let halfH = max(0, h / 2 - inset)
            let corner = max(
                0,
                min(WatchDisplayGeometry.cornerRadius(for: geo.size) - inset, min(halfW, halfH))
            )
            ZStack {
                center
                    .frame(width: max(0, w - inset * 5), height: max(0, h - inset * 5))
                    .position(x: w / 2, y: h / 2)
                ForEach(Array(pips.enumerated()), id: \.element.hole) { index, pip in
                    let distance = WatchHoleMapView.scoringRingDistance(
                        index: index,
                        count: pips.count,
                        halfW: halfW,
                        halfH: halfH,
                        corner: corner
                    )
                    let (point, tangent) = WatchHoleMapView.perimeterPointTangent(
                        s: distance,
                        center: centerPoint,
                        halfW: halfW,
                        halfH: halfH,
                        corner: corner
                    )
                    let tangentAngle = atan2(tangent.y, tangent.x)
                    tickView(pip)
                        .rotationEffect(.radians(Double(tangentAngle - .pi / 2)))
                        .position(x: point.x, y: point.y)
                }
            }
        }
    }

    /// A thin perimeter tick (short capsule) drawn upright — the caller rotates it onto the tangent. Scored
    /// holes use the score colour, not-yet-played holes a dim grey, and the current hole a brighter,
    /// longer white tick so "you are here" stands out subtly without a centre-covering ring.
    private func tickView(_ pip: WatchRingPip) -> some View {
        let length: CGFloat = pip.isCurrent ? 11 : 7
        let thickness: CGFloat = pip.isCurrent ? 2.5 : 2
        let color: Color = pip.isCurrent
            ? Color.white
            : (pip.toPar == nil ? Color.gray.opacity(0.45) : AICaddieDesignTokens.scoreColor(toPar: pip.toPar))
        return Capsule(style: .continuous)
            .fill(color)
            .frame(width: thickness, height: length)
    }
}
