import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the LAST batch — PinPointer (compass to the pin when the
/// green is blind) and the Big-Numbers mode (F/C/B green in huge type, no map). Same black / HIG / green
/// language; Canvas + Text only (ImageRenderer-safe).
private enum Flow3 {
    static let green = Color(red: 0.30, green: 0.86, blue: 0.46)
    static let yellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    static let blue = Color(red: 0.35, green: 0.72, blue: 1.0)
    static let red = Color(red: 0.94, green: 0.28, blue: 0.24)
}
private extension View {
    func flow3Screen() -> some View { frame(width: 198, height: 242, alignment: .center).background(Color.black) }
}

// MARK: - PinPointer (compass arrow to the pin, for blind shots)
public struct WatchPinPointerView: View {
    public let bearingDegrees: Double   // 0 = up; clockwise
    public let distance: Int
    public init(bearingDegrees: Double, distance: Int) { self.bearingDegrees = bearingDegrees; self.distance = distance }
    public var body: some View {
        ZStack {
            Canvas { ctx, size in
                ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))
                let c = CGPoint(x: size.width / 2, y: size.height * 0.5)
                let r: CGFloat = 76
                // compass ring
                ctx.stroke(Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2)),
                           with: .color(.white.opacity(0.18)), style: StrokeStyle(lineWidth: 2))
                // ticks
                for i in 0..<12 {
                    let a = Double(i) / 12 * 2 * .pi
                    let p1 = CGPoint(x: c.x + CGFloat(sin(a)) * (r - 6), y: c.y - CGFloat(cos(a)) * (r - 6))
                    let p2 = CGPoint(x: c.x + CGFloat(sin(a)) * r, y: c.y - CGFloat(cos(a)) * r)
                    ctx.stroke(Path { $0.move(to: p1); $0.addLine(to: p2) }, with: .color(.white.opacity(0.3)), style: StrokeStyle(lineWidth: 1.5))
                }
                // arrow FROM the centre (origin at the circle centre, per review "不是从圆心画出来的") out to
                // the pin — bigger, thicker head.
                let a = bearingDegrees * .pi / 180
                let dir = CGPoint(x: CGFloat(sin(a)), y: -CGFloat(cos(a)))
                let tip = CGPoint(x: c.x + dir.x * (r - 6), y: c.y + dir.y * (r - 6))
                ctx.stroke(Path { $0.move(to: c); $0.addLine(to: tip) }, with: .color(Flow3.red), style: StrokeStyle(lineWidth: 7, lineCap: .round))
                let perp = CGPoint(x: -dir.y, y: dir.x)
                var head = Path()
                head.move(to: tip)
                head.addLine(to: CGPoint(x: tip.x - dir.x * 22 + perp.x * 13, y: tip.y - dir.y * 22 + perp.y * 13))
                head.addLine(to: CGPoint(x: tip.x - dir.x * 22 - perp.x * 13, y: tip.y - dir.y * 22 - perp.y * 13))
                head.closeSubpath()
                ctx.fill(head, with: .color(Flow3.red))
                // centre hub = the origin the arrow is drawn from
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - 5, y: c.y - 5, width: 10, height: 10)), with: .color(.white))
                ctx.fill(Path(ellipseIn: CGRect(x: c.x - 2.5, y: c.y - 2.5, width: 5, height: 5)), with: .color(Flow3.red))
            }
            VStack {
                Text("PinPointer · 旗桿方向").font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                Spacer()
                VStack(spacing: 0) {
                    Text("\(distance)").font(.system(size: 30, weight: .bold, design: .rounded)).monospacedDigit().foregroundStyle(.white)
                    Text("码 · 到旗桿").font(.system(size: 9)).foregroundStyle(.secondary)
                }
                .padding(.bottom, 16)
            }
            .padding(.top, 12)
        }
        .flow3Screen()
    }
}

// MARK: - 大字模式 (Big Numbers: F/C/B green, no map)
public struct WatchBigNumbersView: View {
    public let front: Int
    public let center: Int
    public let back: Int
    public let lastShot: Int
    public init(front: Int, center: Int, back: Int, lastShot: Int = 0) { self.front = front; self.center = center; self.back = back; self.lastShot = lastShot }
    public var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("到果岭速览 · 码").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            Spacer(minLength: 2)
            row("后", back, Color(red: 0.72, green: 0.74, blue: 0.78), 30)
            row("中", center, .white, 54)
            row("前", front, Flow3.blue, 30)
            Spacer(minLength: 2)
            Text(lastShot > 0 ? "上一杆 \(lastShot) 码 · 抬腕即见" : "抬腕即见 · 免看地图").font(.system(size: 8.5)).foregroundStyle(.white.opacity(0.55))
        }
        .padding(.horizontal, 18).padding(.vertical, 18)
        .frame(width: 198, height: 242, alignment: .leading)
        .background(Color.black)
    }
    private func row(_ l: String, _ v: Int, _ c: Color, _ s: CGFloat) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(l).font(.system(size: s * 0.4)).foregroundStyle(.secondary)
            Text("\(v)").font(.system(size: s, weight: .bold, design: .rounded)).monospacedDigit().foregroundStyle(c)
        }
    }
}
