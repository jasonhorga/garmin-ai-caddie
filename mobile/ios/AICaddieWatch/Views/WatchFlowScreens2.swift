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
    public let front: Int
    public let center: Int
    public let back: Int
    public init(front: Int, center: Int, back: Int) { self.front = front; self.center = center; self.back = back }
    public var body: some View {
        Canvas { ctx, size in
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: WatchHoleMapSample.pinPx,
                                                centerCanvas: CGPoint(x: size.width / 2, y: size.height * 0.54), scale: 2.4)
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.10)))
            let pin = t(WatchHoleMapSample.pinPx)
            // FIXED targeting RETICLE at screen centre: the pin lands here — you PAN THE MAP under it
            // (Gemini/HIG, user-chosen: dragging the pin itself would occlude the target). SOLID ring = fixed.
            let R: CGFloat = 24
            ctx.stroke(Path { $0.move(to: CGPoint(x: pin.x - R - 9, y: pin.y)); $0.addLine(to: CGPoint(x: pin.x + R + 9, y: pin.y)) }, with: .color(.white.opacity(0.7)), style: StrokeStyle(lineWidth: 1))
            ctx.stroke(Path { $0.move(to: CGPoint(x: pin.x, y: pin.y - R - 9)); $0.addLine(to: CGPoint(x: pin.x, y: pin.y + R + 9)) }, with: .color(.white.opacity(0.7)), style: StrokeStyle(lineWidth: 1))
            ctx.fill(Path(ellipseIn: CGRect(x: pin.x - R, y: pin.y - R, width: R * 2, height: R * 2)), with: .color(.black.opacity(0.10)))
            ctx.stroke(Path(ellipseIn: CGRect(x: pin.x - R, y: pin.y - R, width: R * 2, height: R * 2)), with: .color(.white), style: StrokeStyle(lineWidth: 2.5))
            // flag at the reticle centre (the pin preview)
            ctx.stroke(Path { $0.move(to: pin); $0.addLine(to: CGPoint(x: pin.x, y: pin.y - 19)) }, with: .color(.white), style: StrokeStyle(lineWidth: 2))
            var flag = Path(); flag.move(to: CGPoint(x: pin.x, y: pin.y - 19)); flag.addLine(to: CGPoint(x: pin.x + 13, y: pin.y - 15)); flag.addLine(to: CGPoint(x: pin.x, y: pin.y - 11)); flag.closeSubpath()
            ctx.fill(flag, with: .color(Flow2.red))
            ctx.fill(Path(ellipseIn: CGRect(x: pin.x - 3, y: pin.y - 3, width: 6, height: 6)), with: .color(.white))
            ctx.fill(Path(ellipseIn: CGRect(x: pin.x - 1.5, y: pin.y - 1.5, width: 3, height: 3)), with: .color(Flow2.red))
            // GREEN front & back EDGE distances (more critical than the pin) — dots + pills on the real green.
            func edgePill(_ p: CGPoint, _ s: String, _ c: Color) {
                let w: CGFloat = 48, h: CGFloat = 19
                ctx.fill(Path(roundedRect: CGRect(x: p.x - w / 2, y: p.y - h / 2, width: w, height: h), cornerRadius: h / 2), with: .color(.black.opacity(0.7)))
                ctx.draw(ctx.resolve(Text(s).font(.system(size: 12, weight: .bold, design: .rounded)).foregroundColor(c)), at: p)
            }
            let backGrey = Color(white: 0.82), frontBlue = Color(red: 0.35, green: 0.72, blue: 1.0)
            let backEdge = t(CGPoint(x: 431, y: 270)), frontEdge = t(CGPoint(x: 427, y: 298))
            ctx.fill(Path(ellipseIn: CGRect(x: backEdge.x - 3, y: backEdge.y - 3, width: 6, height: 6)), with: .color(backGrey))
            edgePill(CGPoint(x: backEdge.x + 4, y: backEdge.y - 13), "后 \(back)", backGrey)
            ctx.fill(Path(ellipseIn: CGRect(x: frontEdge.x - 3, y: frontEdge.y - 3, width: 6, height: 6)), with: .color(frontBlue))
            edgePill(CGPoint(x: frontEdge.x, y: frontEdge.y + 13), "前 \(front)", frontBlue)
            // dark scrims so text survives on the bright green (both reviewers flagged unreadable text)
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 46, y: 10, width: 92, height: 46), cornerRadius: 12), with: .color(.black.opacity(0.5)))
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 72, y: size.height - 28, width: 144, height: 22), cornerRadius: 11), with: .color(.black.opacity(0.5)))
            ctx.draw(ctx.resolve(Text("\(center)").font(.system(size: 27, weight: .bold, design: .rounded)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: 27))
            ctx.draw(ctx.resolve(Text("码 · 到旗桿").font(.system(size: 9)).foregroundColor(Color(white: 0.82))), at: CGPoint(x: size.width / 2, y: 47))
            ctx.draw(ctx.resolve(Text("拖动地图 · 十字对准旗桿").font(.system(size: 9, weight: .semibold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: size.height - 16))
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
            let amber = Color(red: 0.96, green: 0.62, blue: 0.16)
            let aim = Color(red: 0.30, green: 0.86, blue: 0.46)
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: CGPoint(x: 496, y: 303),
                                                centerCanvas: CGPoint(x: size.width * 0.5, y: size.height * 0.5), scale: 2.1)
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.08)))
            // YOUR line of play: a ray from your position (below, off-screen) up through the sand toward the
            // target. 进(会进)/过(能过) are where THIS ray CROSSES the sand — measured from your current
            // position along your aim, NOT the blob's side edges. Intersections found by ray-marching the
            // real sand pixels (you→sand-centroid).
            var ray = Path(); ray.move(to: t(CGPoint(x: 497, y: 352))); ray.addLine(to: t(CGPoint(x: 495, y: 284)))
            ctx.stroke(ray, with: .color(.black.opacity(0.5)), style: StrokeStyle(lineWidth: 4.5, lineCap: .round))
            ctx.stroke(ray, with: .color(aim), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
            let tip = t(CGPoint(x: 495, y: 284))
            var head = Path(); head.move(to: CGPoint(x: tip.x, y: tip.y - 2)); head.addLine(to: CGPoint(x: tip.x - 5, y: tip.y + 8)); head.addLine(to: CGPoint(x: tip.x + 5, y: tip.y + 8)); head.closeSubpath()
            ctx.fill(head, with: .color(aim))
            func pill(_ p: CGPoint, _ s: String) {
                let w: CGFloat = 58, h: CGFloat = 22
                ctx.fill(Path(roundedRect: CGRect(x: p.x - w / 2, y: p.y - h / 2, width: w, height: h), cornerRadius: h / 2), with: .color(.black.opacity(0.78)))
                ctx.draw(ctx.resolve(Text(s).font(.system(size: 14.5, weight: .bold, design: .rounded)).foregroundColor(amber)), at: p)
            }
            func dot(_ p: CGPoint) {
                ctx.fill(Path(ellipseIn: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10)), with: .color(amber))
                ctx.stroke(Path(ellipseIn: CGRect(x: p.x - 5, y: p.y - 5, width: 10, height: 10)), with: .color(.white), style: StrokeStyle(lineWidth: 1.6))
            }
            // EXIT (far, toward green) — carry THIS to clear it (能过); ENTRY (near) — carry THIS and you're in.
            let exit = t(CGPoint(x: 496, y: 295)); dot(exit); pill(CGPoint(x: exit.x, y: exit.y - 17), "过 \(clear)")
            let entry = t(CGPoint(x: 496, y: 310)); dot(entry); pill(CGPoint(x: entry.x, y: entry.y + 17), "进 \(carry)")
            // origin hint: the ray comes from YOU (below)
            let base = t(CGPoint(x: 497, y: 350))
            ctx.fill(Path(roundedRect: CGRect(x: base.x - 26, y: base.y - 8, width: 52, height: 16), cornerRadius: 8), with: .color(.black.opacity(0.6)))
            ctx.draw(ctx.resolve(Text("你 ↑").font(.system(size: 9, weight: .semibold)).foregroundColor(.white)), at: base)
            // title
            ctx.fill(Path(roundedRect: CGRect(x: size.width / 2 - 62, y: 6, width: 124, height: 18), cornerRadius: 9), with: .color(.black.opacity(0.6)))
            ctx.draw(ctx.resolve(Text("沙坑 · 沿你的打球线(码)").font(.system(size: 9.5, weight: .semibold)).foregroundColor(.white)), at: CGPoint(x: size.width / 2, y: 15))
        }
        .flow2Screen()
    }
}
