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
            // labels
            ctx.draw(ctx.resolve(Text("\(center)").font(.system(size: 27, weight: .bold, design: .rounded)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: 26))
            ctx.draw(ctx.resolve(Text("码 · 到旗桿").font(.system(size: 9)).foregroundColor(.gray)), at: CGPoint(x: size.width / 2, y: 46))
            ctx.draw(ctx.resolve(Text("预览果岭 · 拖动旗桿").font(.system(size: 9.5, weight: .semibold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: size.height - 16))
        }
        .flow2Screen()
    }
}

// MARK: - 障碍 / 目标 (REAL hole map + front/back carry numbers + ∧∨ to cycle)
public struct WatchTargetView: View {
    public let frontCarry: Int
    public let backCarry: Int
    public init(frontCarry: Int, backCarry: Int) { self.frontCarry = frontCarry; self.backCarry = backCarry }
    public var body: some View {
        Canvas { ctx, size in
            // whole-ish hole, centred a bit above the middle so the fairway hazard region shows.
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: CGPoint(x: 520, y: 640),
                                                centerCanvas: CGPoint(x: size.width / 2, y: size.height * 0.5), scale: 0.52)
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.08)))
            // hazard front/back markers along the fairway (dashed lines across, like Garmin)
            let frontP = t(CGPoint(x: 512, y: 700))   // near carry
            let backP = t(CGPoint(x: 526, y: 628))    // far carry (clear it)
            for (p, dist) in [(frontP, frontCarry), (backP, backCarry)] {
                ctx.stroke(Path { $0.move(to: CGPoint(x: p.x - 22, y: p.y)); $0.addLine(to: CGPoint(x: p.x + 22, y: p.y)) },
                           with: .color(.white.opacity(0.85)), style: StrokeStyle(lineWidth: 1.4, dash: [3, 3]))
                ctx.draw(ctx.resolve(Text("\(dist)").font(.system(size: 16, weight: .bold, design: .rounded)).foregroundColor(.white)),
                         at: CGPoint(x: p.x, y: p.y - 12))
            }
            ctx.draw(ctx.resolve(Text("障碍 · 碳距(码)").font(.system(size: 10, weight: .semibold)).foregroundColor(.gray)), at: CGPoint(x: size.width / 2, y: 15))
            ctx.draw(ctx.resolve(Text("∧").font(.system(size: 17, weight: .bold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2 - 16, y: size.height - 15))
            ctx.draw(ctx.resolve(Text("∨").font(.system(size: 17, weight: .bold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2 + 16, y: size.height - 15))
        }
        .flow2Screen()
    }
}
