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

// MARK: - 障碍 (centre on the REAL rendered greenside bunker; tether carry/clear DOTS to the actual sand —
// no drawn hazard shape. Bunker px from detecting the tan sand pixels in the render.)
public struct WatchTargetView: View {
    public let carry: Int    // to reach the near edge of the sand
    public let clear: Int    // to clear the far edge
    public init(carry: Int, clear: Int) { self.carry = carry; self.clear = clear }
    public var body: some View {
        Canvas { ctx, size in
            // centre + zoom on the real greenside bunker (detected sand ~x460–500, y260–305) so the actual
            // sand fills the frame.
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: CGPoint(x: 458, y: 290),
                                                centerCanvas: CGPoint(x: size.width * 0.48, y: size.height * 0.52), scale: 1.85)
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.10)))
            let amber = Color(red: 0.96, green: 0.62, blue: 0.16), green = Color(red: 0.30, green: 0.86, blue: 0.46)
            // DOT on the real sand (amber) + DOT on the real putting-green (green target) + connector to
            // side numbers. Both land on actual rendered features — marking, not fabricating.
            let hazardPt = t(CGPoint(x: 495, y: 301)), greenPt = t(CGPoint(x: 440, y: 284))
            let lx = size.width - 20
            for (p, val, col) in [(hazardPt, carry, amber), (greenPt, clear, green)] {
                ctx.stroke(Path(ellipseIn: CGRect(x: p.x - 6, y: p.y - 6, width: 12, height: 12)), with: .color(col), style: StrokeStyle(lineWidth: 2))
                ctx.fill(Path(ellipseIn: CGRect(x: p.x - 2.5, y: p.y - 2.5, width: 5, height: 5)), with: .color(col))
                ctx.stroke(Path { $0.move(to: CGPoint(x: p.x + 7, y: p.y)); $0.addLine(to: CGPoint(x: lx - 12, y: p.y)) }, with: .color(col.opacity(0.7)), style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
                ctx.draw(ctx.resolve(Text("\(val)").font(.system(size: 16, weight: .bold, design: .rounded)).foregroundColor(.white)), at: CGPoint(x: lx, y: p.y))
            }
            // title scrim + legend + ∧∨
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 54, y: 6, width: 108, height: 18), cornerRadius: 9), with: .color(.black.opacity(0.55)))
            ctx.draw(ctx.resolve(Text("障碍 · 沙坑/果岭(码)").font(.system(size: 10, weight: .semibold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: 15))
            ctx.draw(ctx.resolve(Text("● 碳沙坑").font(.system(size: 9, weight: .semibold)).foregroundColor(amber)), at: CGPoint(x: 34, y: size.height - 32))
            ctx.draw(ctx.resolve(Text("● 到果岭").font(.system(size: 9, weight: .semibold)).foregroundColor(green)), at: CGPoint(x: 34, y: size.height - 19))
            ctx.draw(ctx.resolve(Text("∧").font(.system(size: 17, weight: .bold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2 - 16, y: size.height - 14))
            ctx.draw(ctx.resolve(Text("∨").font(.system(size: 17, weight: .bold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2 + 16, y: size.height - 14))
        }
        .flow2Screen()
    }
}
