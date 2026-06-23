import SwiftUI

/// round-13 (Watch standalone): the 18-hole ring that hugs the rounded-rect watch screen EDGE
/// (spec screen ①, the user's explicit "贴着屏幕边缘,不要一个居中的圆"). Each hole is a pip placed
/// where a ray from the centre meets the screen rectangle (so pips ride the edge, denser at the
/// corners — conforming to the watch face rather than an inscribed circle). 1号洞上方居中起、顺时针,
/// 首尾留缺口;当前洞放大高亮,已记洞按成绩着色。Plain shape layers → renders in ImageRenderer snapshots.
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
                    let pt = edgePoint(index: index, count: pips.count, w: w, h: h, inset: inset)
                    pipView(pip).position(x: pt.x, y: pt.y)
                }
            }
        }
    }

    /// Point where the ray at this pip's angle meets the screen rectangle (edge-hugging), inset.
    private func edgePoint(index: Int, count: Int, w: CGFloat, h: CGFloat, inset: CGFloat) -> CGPoint {
        let cx = w / 2, cy = h / 2
        // Start at top-centre (−90°), sweep clockwise across the full circle minus the top gap.
        let span = (2 * CGFloat.pi) - gap
        let denom = max(1, count - 1)
        let angle = -CGFloat.pi / 2 + gap / 2 + span * CGFloat(index) / CGFloat(denom)
        let dx = cos(angle), dy = sin(angle)
        let halfW = cx - inset, halfH = cy - inset
        // distance along the ray until it meets the nearer of the vertical/horizontal edges
        let tx = abs(dx) < 0.0001 ? CGFloat.greatestFiniteMagnitude : halfW / abs(dx)
        let ty = abs(dy) < 0.0001 ? CGFloat.greatestFiniteMagnitude : halfH / abs(dy)
        let t = min(tx, ty)
        return CGPoint(x: cx + dx * t, y: cy + dy * t)
    }

    private func pipView(_ pip: WatchRingPip) -> some View {
        let size: CGFloat = pip.isCurrent ? 16 : 11
        return ZStack {
            Circle()
                .fill(pip.toPar == nil ? Color.gray.opacity(0.35) : AICaddieDesignTokens.scoreColor(toPar: pip.toPar))
                .frame(width: size, height: size)
            if pip.isCurrent {
                Circle().stroke(Color.white, lineWidth: 1.5).frame(width: size, height: size)
                Text("\(pip.hole)").font(.system(size: 9, weight: .bold)).foregroundStyle(.white)
            }
        }
    }
}
