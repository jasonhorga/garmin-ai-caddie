import SwiftUI

/// round-13 (Watch standalone): the 18-hole ring that hugs the rounded-rect watch screen EDGE
/// (spec screen ①, the user's explicit "贴着屏幕边缘,不要一个居中的圆"). Each hole is drawn as a thin
/// RADIAL TICK (a short capsule, like a watch-face minute mark) placed where a ray from the centre
/// meets the screen rectangle and rotated to align with that ray — so the marks ride the rim, point
/// inward, and stay slim enough not to cover the centre distance/number (the user's
/// "沿着手表边缘做一些小横线,做得细一点,这样不会覆盖其他元素"). 1号洞上方居中起、顺时针,首尾留缺口;
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
    /// Total angular gap (radians) left open at the top between the last and first hole.
    public let gap: CGFloat

    public init(pips: [WatchRingPip], gap: CGFloat = .pi / 5, @ViewBuilder center: () -> Center) {
        self.pips = pips
        self.center = center()
        self.gap = gap
    }

    public var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let inset: CGFloat = 9   // keep pips fully on-screen
            ZStack {
                center
                    .frame(width: max(0, w - inset * 5), height: max(0, h - inset * 5))
                    .position(x: w / 2, y: h / 2)
                ForEach(Array(pips.enumerated()), id: \.element.hole) { index, pip in
                    let angle = pipAngle(index: index, count: pips.count)
                    let pt = edgePoint(angle: angle, w: w, h: h, inset: inset)
                    tickView(pip)
                        // rotate the upright capsule so its long axis points along the ray from
                        // centre → it reads as a rim tick aiming inward (+π/2: a vertical capsule's
                        // axis is at −π/2, so add π/2 to swing it onto the ray direction `angle`).
                        .rotationEffect(.radians(Double(angle) + .pi / 2))
                        .position(x: pt.x, y: pt.y)
                }
            }
        }
    }

    /// Clockwise angle (from centre) at which this pip sits on the ring. Top-centre (−90°) is hole 1,
    /// sweeping clockwise across the full circle minus the top gap.
    private func pipAngle(index: Int, count: Int) -> CGFloat {
        let span = (2 * CGFloat.pi) - gap
        let denom = max(1, count - 1)
        return -CGFloat.pi / 2 + gap / 2 + span * CGFloat(index) / CGFloat(denom)
    }

    /// Point where the ray at `angle` meets the screen rectangle (edge-hugging), inset.
    private func edgePoint(angle: CGFloat, w: CGFloat, h: CGFloat, inset: CGFloat) -> CGPoint {
        let cx = w / 2, cy = h / 2
        let dx = cos(angle), dy = sin(angle)
        let halfW = cx - inset, halfH = cy - inset
        // distance along the ray until it meets the nearer of the vertical/horizontal edges
        let tx = abs(dx) < 0.0001 ? CGFloat.greatestFiniteMagnitude : halfW / abs(dx)
        let ty = abs(dy) < 0.0001 ? CGFloat.greatestFiniteMagnitude : halfH / abs(dy)
        let t = min(tx, ty)
        return CGPoint(x: cx + dx * t, y: cy + dy * t)
    }

    /// A thin radial tick (short capsule) drawn UPRIGHT — the caller rotates it onto the ray. Scored
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
