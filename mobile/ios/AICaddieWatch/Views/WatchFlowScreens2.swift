import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): round-home hub + green-preview + hazard/target — the last
/// two now drawn on the REAL baked hole image (`WatchHoleMapSample.drawInto`), matching the S70/S50
/// screenshots, NOT hand-drawn shapes. Labels drawn in-Canvas via `ctx.draw(Text)`.
private enum Flow2 {
    static let green = Color(red: 0.30, green: 0.86, blue: 0.46)
    static let yellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    static let blue = Color(red: 0.35, green: 0.72, blue: 1.0)
    static let red = Color(red: 0.94, green: 0.28, blue: 0.24)
}
private extension View {
    func flow2Screen() -> some View { frame(width: 198, height: 242, alignment: .topLeading).background(Color.black) }
}

// MARK: - 球局主页 (round-home hub — no map)
public struct WatchRoundHubView: View {
    public let course: String
    public let hole: Int
    public let par: Int
    public let toPar: Int
    public init(course: String, hole: Int, par: Int, toPar: Int) {
        self.course = course; self.hole = hole; self.par = par; self.toPar = toPar
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(course).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary).lineLimit(1)
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text("继续打球").font(.system(size: 15, weight: .bold)).foregroundStyle(.black)
                    Text("第\(hole)洞 · Par \(par)").font(.system(size: 10)).foregroundStyle(.black.opacity(0.75))
                }
                Spacer(minLength: 0)
                Text(toPar == 0 ? "E" : (toPar > 0 ? "+\(toPar)" : "\(toPar)"))
                    .font(.system(size: 20, weight: .bold, design: .rounded)).foregroundStyle(.black)
            }
            .padding(.horizontal, 12).padding(.vertical, 11)
            .background(RoundedRectangle(cornerRadius: 13).fill(Flow2.green))
            HStack(spacing: 8) { tile("积分卡"); tile("选洞") }
            HStack(spacing: 8) { tile("球童"); tile("设置") }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.top, 16)
        .flow2Screen()
    }
    private func tile(_ t: String) -> some View {
        Text(t).font(.system(size: 13, weight: .semibold)).foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 40)
            .background(RoundedRectangle(cornerRadius: 11).fill(Color.white.opacity(0.08)))
    }
}

// MARK: - 预览果岭 (hard zoom on the REAL green + crosshair + draggable pin)
public struct WatchGreenPreviewView: View {
    public let center: Int
    public init(center: Int) { self.center = center }
    public var body: some View {
        Canvas { ctx, size in
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: WatchHoleMapSample.pinPx,
                                                centerCanvas: CGPoint(x: size.width / 2, y: size.height * 0.54), scale: 2.4)
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.10)))
            let pin = t(WatchHoleMapSample.pinPx)
            // crosshair centred on the pin
            ctx.stroke(Path { $0.move(to: CGPoint(x: pin.x - 30, y: pin.y)); $0.addLine(to: CGPoint(x: pin.x + 30, y: pin.y)) },
                       with: .color(.white.opacity(0.6)), style: StrokeStyle(lineWidth: 1))
            ctx.stroke(Path { $0.move(to: CGPoint(x: pin.x, y: pin.y - 30)); $0.addLine(to: CGPoint(x: pin.x, y: pin.y + 30)) },
                       with: .color(.white.opacity(0.6)), style: StrokeStyle(lineWidth: 1))
            // Draggable pin: a BIG dashed grab RING (movable, easy target) with the flag inside — per review
            // "大圈套旗、可拖". The dashed ring = draggable.
            let grabR: CGFloat = 23
            ctx.fill(Path(ellipseIn: CGRect(x: pin.x - grabR, y: pin.y - grabR, width: grabR * 2, height: grabR * 2)), with: .color(Flow2.green.opacity(0.14)))
            ctx.stroke(Path(ellipseIn: CGRect(x: pin.x - grabR, y: pin.y - grabR, width: grabR * 2, height: grabR * 2)), with: .color(Flow2.green), style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
            // flagpole + flag (bigger)
            ctx.stroke(Path { $0.move(to: pin); $0.addLine(to: CGPoint(x: pin.x, y: pin.y - 30)) }, with: .color(.white), style: StrokeStyle(lineWidth: 2))
            var flag = Path(); flag.move(to: CGPoint(x: pin.x, y: pin.y - 30)); flag.addLine(to: CGPoint(x: pin.x + 16, y: pin.y - 25)); flag.addLine(to: CGPoint(x: pin.x, y: pin.y - 20)); flag.closeSubpath()
            ctx.fill(flag, with: .color(Flow2.red))
            // pin base
            ctx.fill(Path(ellipseIn: CGRect(x: pin.x - 4, y: pin.y - 4, width: 8, height: 8)), with: .color(.white))
            ctx.fill(Path(ellipseIn: CGRect(x: pin.x - 2, y: pin.y - 2, width: 4, height: 4)), with: .color(Flow2.red))
            // dark scrims so text survives on the bright green (both reviewers flagged unreadable text)
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 46, y: 10, width: 92, height: 46), cornerRadius: 12), with: .color(.black.opacity(0.5)))
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 72, y: size.height - 28, width: 144, height: 22), cornerRadius: 11), with: .color(.black.opacity(0.5)))
            ctx.draw(ctx.resolve(Text("\(center)").font(.system(size: 27, weight: .bold, design: .rounded)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: 27))
            ctx.draw(ctx.resolve(Text("码 · 到旗桿").font(.system(size: 9)).foregroundColor(Color(white: 0.82))), at: CGPoint(x: size.width / 2, y: 47))
            ctx.draw(ctx.resolve(Text("预览果岭 · 拖动旗桿").font(.system(size: 9.5, weight: .semibold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: size.height - 16))
        }
        .flow2Screen()
    }
}

// MARK: - 障碍 (centre on the REAL rendered greenside bunker; tether carry/clear DOTS to the actual sand —
// no drawn hazard shape. Bunker px from detecting the tan sand pixels in the render.)
public struct WatchTargetView: View {
    public let carry: Int    // to reach the near edge of the sand
    public let clear: Int    // to clear the far edge
    public init(carry: Int, clear: Int) { self.carry = carry; self.clear = clear }
    public var body: some View {
        Canvas { ctx, size in
            let amber = Color(red: 0.96, green: 0.62, blue: 0.16), green = Color(red: 0.30, green: 0.86, blue: 0.46)
            // Centre between the real sand bunker and the real green so both fit.
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: CGPoint(x: 467, y: 291),
                                                centerCanvas: CGPoint(x: size.width * 0.5, y: size.height * 0.52), scale: 1.9)
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.08)))
            // Number in an OPAQUE pill (outdoor contrast — both reviewers' #1 fix) placed AT its marker, so
            // the eye reads number+target as one thing (no side numbers, no leader lines, no legend).
            func pill(_ p: CGPoint, _ s: String, _ c: Color, big: Bool) {
                let fs: CGFloat = big ? 18 : 15, w: CGFloat = big ? 42 : 36, h: CGFloat = big ? 24 : 21
                ctx.fill(Path(roundedRect: CGRect(x: p.x - w / 2, y: p.y - h / 2, width: w, height: h), cornerRadius: h / 2), with: .color(.black.opacity(0.72)))
                ctx.draw(ctx.resolve(Text(s).font(.system(size: fs, weight: .bold, design: .rounded)).foregroundColor(c)), at: p)
            }
            func dot(_ p: CGPoint, _ c: Color, _ r: CGFloat) {
                ctx.fill(Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2)), with: .color(c))
                ctx.stroke(Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: r * 2, height: r * 2)), with: .color(.white), style: StrokeStyle(lineWidth: 1.5))
            }
            // amber HAZARD (primary) — solid dot on the real sand + carry number in a pill just below it.
            let hz = t(CGPoint(x: 495, y: 301))
            dot(hz, amber, 5)
            pill(CGPoint(x: hz.x, y: hz.y + 19), "\(carry)", amber, big: true)
            // green TARGET (secondary) — dot on the real green + distance pill just above it.
            let gp = t(CGPoint(x: 440, y: 284))
            dot(gp, green, 4.5)
            pill(CGPoint(x: gp.x, y: gp.y - 17), "\(clear)", green, big: false)
            // title pill (no legend, no leader lines, no ∧∨ carets — crown/swipe cycles hazards)
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 60, y: 6, width: 120, height: 18), cornerRadius: 9), with: .color(.black.opacity(0.6)))
            ctx.draw(ctx.resolve(Text("障碍 · 碳沙坑 / 到果岭").font(.system(size: 9.5, weight: .semibold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: 15))
        }
        .flow2Screen()
    }
}
