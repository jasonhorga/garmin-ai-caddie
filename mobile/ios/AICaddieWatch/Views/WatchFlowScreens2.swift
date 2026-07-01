import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the SECOND batch of flow screens — the round-home hub, the
/// green preview (drag pin), and the hazard/touch-target carry view — in the same black / HIG / green
/// language. Plain `VStack`/`HStack` + `Canvas` (no `ScrollView`/`LazyVGrid`/free `Path{}.fill()`).
private enum Flow2 {
    static let green = Color(red: 0.30, green: 0.86, blue: 0.46)
    static let yellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    static let blue = Color(red: 0.35, green: 0.72, blue: 1.0)
    static let sand = Color(red: 0.82, green: 0.71, blue: 0.46)
    static let water = Color(red: 0.22, green: 0.55, blue: 0.95)
}
private extension View {
    func flow2Screen() -> some View { frame(width: 198, height: 242, alignment: .topLeading).background(Color.black) }
}

// MARK: - 球局主页 (round-home hub, after picking a course)
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
            // Primary: continue playing.
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
            // Secondary tiles.
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

// MARK: - 预览果岭 (green preview + draggable pin, F/C/B update live)
public struct WatchGreenPreviewView: View {
    public let front: Int
    public let center: Int
    public let back: Int
    public init(front: Int, center: Int, back: Int) { self.front = front; self.center = center; self.back = back }
    public var body: some View {
        ZStack(alignment: .top) {
            Canvas { ctx, size in
                ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))
                // green shape (a blob), centred.
                let c = CGPoint(x: size.width * 0.5, y: size.height * 0.56)
                let blob = CGRect(x: c.x - 62, y: c.y - 48, width: 124, height: 104)
                ctx.fill(Path(ellipseIn: blob), with: .color(Color(red: 0.24, green: 0.6, blue: 0.34)))
                ctx.fill(Path(ellipseIn: blob.insetBy(dx: 10, dy: 10)), with: .color(Color(red: 0.30, green: 0.7, blue: 0.40)))
                // front / back edge markers.
                let fEdge = CGPoint(x: c.x, y: blob.maxY - 8), bEdge = CGPoint(x: c.x, y: blob.minY + 8)
                for (p, col) in [(fEdge, Flow2.blue), (bEdge, Color(red: 0.72, green: 0.74, blue: 0.78))] {
                    ctx.fill(Path(ellipseIn: CGRect(x: p.x - 3, y: p.y - 3, width: 6, height: 6)), with: .color(col))
                }
                // draggable pin (centre) + flag.
                let pin = CGPoint(x: c.x + 8, y: c.y - 4)
                ctx.stroke(Path { $0.move(to: CGPoint(x: pin.x, y: pin.y)); $0.addLine(to: CGPoint(x: pin.x, y: pin.y - 20)) },
                           with: .color(.white), style: StrokeStyle(lineWidth: 1.4))
                var flag = Path(); flag.move(to: CGPoint(x: pin.x, y: pin.y - 20))
                flag.addLine(to: CGPoint(x: pin.x + 11, y: pin.y - 16)); flag.addLine(to: CGPoint(x: pin.x, y: pin.y - 12)); flag.closeSubpath()
                ctx.fill(flag, with: .color(Color(red: 0.94, green: 0.28, blue: 0.24)))
                ctx.fill(Path(ellipseIn: CGRect(x: pin.x - 4, y: pin.y - 4, width: 8, height: 8)), with: .color(.white))
                ctx.stroke(Path(ellipseIn: CGRect(x: pin.x - 6, y: pin.y - 6, width: 12, height: 12)),
                           with: .color(Flow2.green), style: StrokeStyle(lineWidth: 1.6, dash: [2, 2]))
            }
            VStack(spacing: 2) {
                Text("预览果岭 · 拖动旗桿").font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                HStack(spacing: 12) {
                    edge("后", back, Color(red: 0.72, green: 0.74, blue: 0.78))
                    edge("中", center, .white)
                    edge("前", front, Flow2.blue)
                }
            }
            .padding(.top, 14)
        }
        .flow2Screen()
    }
    private func edge(_ l: String, _ v: Int, _ c: Color) -> some View {
        HStack(spacing: 3) {
            Text(l).font(.system(size: 9)).foregroundStyle(.secondary)
            Text("\(v)").font(.system(size: 13, weight: .bold)).monospacedDigit().foregroundStyle(c)
        }
    }
}

// MARK: - 目标 / 障碍碳距 (touch-target: you→target + target→green; hazard front/back carry)
public struct WatchTargetView: View {
    public let title: String
    public let toTarget: Int      // you → target
    public let targetToGreen: Int // target → pin
    public let carryFront: Int    // hazard front carry
    public let carryBack: Int     // hazard back carry
    public init(title: String, toTarget: Int, targetToGreen: Int, carryFront: Int, carryBack: Int) {
        self.title = title; self.toTarget = toTarget; self.targetToGreen = targetToGreen
        self.carryFront = carryFront; self.carryBack = carryBack
    }
    public var body: some View {
        ZStack(alignment: .topLeading) {
            Canvas { ctx, size in
                ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))
                let you = CGPoint(x: size.width * 0.5, y: size.height * 0.82)
                let target = CGPoint(x: size.width * 0.5, y: size.height * 0.44)
                let green = CGPoint(x: size.width * 0.5, y: size.height * 0.16)
                // fairway strip.
                ctx.fill(Path(roundedRect: CGRect(x: size.width * 0.36, y: 0, width: size.width * 0.28, height: size.height), cornerRadius: 20),
                         with: .color(Color(red: 0.14, green: 0.30, blue: 0.18)))
                // water hazard band (between target and green).
                ctx.fill(Path(roundedRect: CGRect(x: size.width * 0.30, y: size.height * 0.26, width: size.width * 0.40, height: 20), cornerRadius: 6),
                         with: .color(Flow2.water.opacity(0.85)))
                // you → target solid, target → green dashed.
                ctx.stroke(Path { $0.move(to: you); $0.addLine(to: target) }, with: .color(Flow2.green), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                ctx.stroke(Path { $0.move(to: target); $0.addLine(to: green) }, with: .color(.white.opacity(0.8)), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [4, 3]))
                // target crosshair.
                ctx.stroke(Path(ellipseIn: CGRect(x: target.x - 9, y: target.y - 9, width: 18, height: 18)), with: .color(Flow2.green), style: StrokeStyle(lineWidth: 2))
                ctx.stroke(Path { $0.move(to: CGPoint(x: target.x - 13, y: target.y)); $0.addLine(to: CGPoint(x: target.x + 13, y: target.y)) }, with: .color(Flow2.green), style: StrokeStyle(lineWidth: 1))
                ctx.stroke(Path { $0.move(to: CGPoint(x: target.x, y: target.y - 13)); $0.addLine(to: CGPoint(x: target.x, y: target.y + 13)) }, with: .color(Flow2.green), style: StrokeStyle(lineWidth: 1))
                // you + pin.
                ctx.fill(Path(ellipseIn: CGRect(x: you.x - 5, y: you.y - 5, width: 10, height: 10)), with: .color(Flow2.blue))
                ctx.fill(Path(ellipseIn: CGRect(x: green.x - 4, y: green.y - 4, width: 8, height: 8)), with: .color(.white))
            }
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                HStack(spacing: 3) {
                    Text("到目标").font(.system(size: 9)).foregroundStyle(.secondary)
                    Text("\(toTarget)").font(.system(size: 20, weight: .bold, design: .rounded)).monospacedDigit().foregroundStyle(.white)
                }
                Text("目标→果岭 \(targetToGreen)").font(.system(size: 9.5)).foregroundStyle(.secondary)
                HStack(spacing: 3) {
                    RoundedRectangle(cornerRadius: 2).fill(Flow2.water).frame(width: 8, height: 8)
                    Text("碳距 \(carryFront)–\(carryBack)").font(.system(size: 9.5, weight: .medium)).foregroundStyle(Flow2.blue)
                }
            }
            .padding(.horizontal, 12).padding(.top, 12)
        }
        .flow2Screen()
    }
}
