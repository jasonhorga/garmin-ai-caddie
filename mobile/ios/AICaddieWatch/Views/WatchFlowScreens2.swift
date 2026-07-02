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
            // draggable pin (flag) — dashed ring = movable
            ctx.stroke(Path { $0.move(to: pin); $0.addLine(to: CGPoint(x: pin.x, y: pin.y - 22)) }, with: .color(.white), style: StrokeStyle(lineWidth: 1.5))
            var flag = Path(); flag.move(to: CGPoint(x: pin.x, y: pin.y - 22)); flag.addLine(to: CGPoint(x: pin.x + 12, y: pin.y - 18)); flag.addLine(to: CGPoint(x: pin.x, y: pin.y - 14)); flag.closeSubpath()
            ctx.fill(flag, with: .color(Flow2.red))
            ctx.fill(Path(ellipseIn: CGRect(x: pin.x - 3.5, y: pin.y - 3.5, width: 7, height: 7)), with: .color(.white))
            ctx.stroke(Path(ellipseIn: CGRect(x: pin.x - 7, y: pin.y - 7, width: 14, height: 14)), with: .color(Flow2.green), style: StrokeStyle(lineWidth: 1.4, dash: [2, 2]))
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

// MARK: - 障碍 (REAL bunker highlighted in AMBER + carry/clear tethered to its edges + ∧∨ to cycle)
public struct WatchTargetView: View {
    public let carry: Int    // to reach the near edge of the hazard
    public let clear: Int    // to clear the far edge
    public init(carry: Int, clear: Int) { self.carry = carry; self.clear = clear }
    public var body: some View {
        Canvas { ctx, size in
            // centre on the greenside bunker region so the hazard is actually in frame.
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: CGPoint(x: 390, y: 320),
                                                centerCanvas: CGPoint(x: size.width * 0.55, y: size.height * 0.52), scale: 1.4)
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.12)))
            let amber = Color(red: 0.96, green: 0.62, blue: 0.16)
            // AMBER hazard highlight over the real greenside bunker + a "沙坑" tag.
            let b = t(CGPoint(x: 366, y: 300))
            let hz = CGRect(x: b.x - 26, y: b.y - 16, width: 52, height: 32)
            ctx.fill(Path(ellipseIn: hz), with: .color(amber.opacity(0.38)))
            ctx.stroke(Path(ellipseIn: hz), with: .color(amber), style: StrokeStyle(lineWidth: 2.2))
            ctx.draw(ctx.resolve(Text("沙坑").font(.system(size: 10, weight: .bold)).foregroundColor(.black)), at: b)
            // TETHER carry (near edge) + clear (far edge) to the hazard with dots + connector to a label.
            let near = CGPoint(x: b.x - 4, y: b.y + 16), far = CGPoint(x: b.x + 4, y: b.y - 16)
            let lx = size.width - 24
            let green = Color(red: 0.30, green: 0.86, blue: 0.46)
            for (p, val, col) in [(near, carry, amber), (far, clear, green)] {
                ctx.fill(Path(ellipseIn: CGRect(x: p.x - 3, y: p.y - 3, width: 6, height: 6)), with: .color(col))
                ctx.stroke(Path { $0.move(to: p); $0.addLine(to: CGPoint(x: lx - 14, y: p.y)) }, with: .color(col.opacity(0.65)), style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
                ctx.draw(ctx.resolve(Text("\(val)").font(.system(size: 16, weight: .bold, design: .rounded)).foregroundColor(.white)), at: CGPoint(x: lx, y: p.y))
            }
            // legend: amber=碳(reach) green=越(clear)
            ctx.draw(ctx.resolve(Text("碳 沙坑").font(.system(size: 9, weight: .semibold)).foregroundColor(amber)), at: CGPoint(x: 34, y: size.height - 34))
            ctx.draw(ctx.resolve(Text("越 沙坑").font(.system(size: 9, weight: .semibold)).foregroundColor(green)), at: CGPoint(x: 34, y: size.height - 20))
            // title with a dark scrim so it survives on the map
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 52, y: 6, width: 104, height: 18), cornerRadius: 9), with: .color(.black.opacity(0.5)))
            ctx.draw(ctx.resolve(Text("障碍 · 到沙坑").font(.system(size: 10.5, weight: .semibold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: 15))
            ctx.draw(ctx.resolve(Text("∧").font(.system(size: 17, weight: .bold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2 - 16, y: size.height - 14))
            ctx.draw(ctx.resolve(Text("∨").font(.system(size: 17, weight: .bold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2 + 16, y: size.height - 14))
        }
        .flow2Screen()
    }
}
