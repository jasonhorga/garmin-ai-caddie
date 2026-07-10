import SwiftUI

/// Watch design-system #5: 旗向指引 (was "PinPointer") — the ONE axis-less screen. When you can't see the
/// green (trees / bunker), a compass-style arrow emanating from the centre hub points toward the flag,
/// with the straight-line distance below. Presentational; drawn in a single Canvas so `Path{}.fill()`
/// child views don't nil the ImageRenderer.
public struct WatchPinPointerView: View {
    /// Bearing to the pin in degrees, 0 = up (straight ahead), clockwise positive.
    public let bearingDeg: Double
    public let distanceYd: Int

    public init(bearingDeg: Double = -18, distanceYd: Int = 152) {
        self.bearingDeg = bearingDeg
        self.distanceYd = distanceYd
    }

    public var body: some View {
        VStack(spacing: 2) {
            Text("旗向指引").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            Canvas { ctx, size in
                let c = CGPoint(x: size.width / 2, y: size.height / 2)
                let r: CGFloat = min(size.width, size.height) * 0.42
                // dial ring + ticks
                ctx.stroke(Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2)),
                           with: .color(.white.opacity(0.18)), lineWidth: 2)
                for i in 0..<12 {
                    let a: CGFloat = CGFloat(i) / 12 * 2 * .pi
                    let p1 = CGPoint(x: c.x + cos(a) * r, y: c.y + sin(a) * r)
                    let p2 = CGPoint(x: c.x + cos(a) * (r - 6), y: c.y + sin(a) * (r - 6))
                    var t = Path(); t.move(to: p1); t.addLine(to: p2)
                    ctx.stroke(t, with: .color(.white.opacity(0.28)), lineWidth: 1.5)
                }
                // arrow from centre toward the pin
                let rad: CGFloat = CGFloat(bearingDeg - 90) * .pi / 180
                let tip = CGPoint(x: c.x + cos(rad) * (r - 8), y: c.y + sin(rad) * (r - 8))
                let back = CGPoint(x: c.x - cos(rad) * (r * 0.32), y: c.y - sin(rad) * (r * 0.32))
                var shaft = Path(); shaft.move(to: back); shaft.addLine(to: tip)
                ctx.stroke(shaft, with: .color(Color(red: 1.0, green: 0.27, blue: 0.23)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
                // arrowhead
                let ah: CGFloat = 12
                let left = CGPoint(x: tip.x - cos(rad - 0.4) * ah, y: tip.y - sin(rad - 0.4) * ah)
                let right = CGPoint(x: tip.x - cos(rad + 0.4) * ah, y: tip.y - sin(rad + 0.4) * ah)
                var head = Path(); head.move(to: tip); head.addLine(to: left); head.addLine(to: right); head.closeSubpath()
                ctx.fill(head, with: .color(Color(red: 1.0, green: 0.27, blue: 0.23)))
                // centre hub
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - 5, y: c.y - 5, width: 10, height: 10)), with: .color(.white))
            }
            .frame(height: 128)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text("\(distanceYd)").font(.system(size: 30, weight: .bold, design: .rounded)).monospacedDigit()
                Text("码 · 到旗杆").font(.system(size: 10)).foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity)
    }
}
