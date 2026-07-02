import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the remaining golf screens the S70 manual documents that we
/// hadn't drawn — score entry (总杆/推杆/球道/罚杆), end-round summary, the caddie detail (击球建议), the
/// golf menu, club stats, and the per-hole shot list. Same black / HIG / green language; Text + shapes only.
private enum F4 {
    static let green = Color(red: 0.30, green: 0.86, blue: 0.46)
    static let yellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    static let blue = Color(red: 0.35, green: 0.72, blue: 1.0)
    static let red = Color(red: 0.94, green: 0.28, blue: 0.24)
}

/// A ± stepper (crown/tap adjusts on device; here it shows the current value framed by − / +).
private func stepper(_ label: String, _ value: String, big: Bool, color: Color = .white) -> some View {
    VStack(spacing: 3) {
        Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
        HStack(spacing: 12) {
            Text("−").font(.system(size: 18, weight: .bold)).foregroundStyle(.white.opacity(0.8))
                .frame(width: 28, height: 28).background(Circle().fill(Color.white.opacity(0.1)))
            Text(value).font(.system(size: big ? 40 : 24, weight: .bold, design: .rounded)).monospacedDigit()
                .foregroundStyle(color).frame(minWidth: 42)
            Text("+").font(.system(size: 18, weight: .bold)).foregroundStyle(.white.opacity(0.8))
                .frame(width: 28, height: 28).background(Circle().fill(Color.white.opacity(0.1)))
        }
    }
}

// MARK: - 记分 · 杆数 (total strokes + putts)
public struct WatchScoreEntryView: View {
    public let hole: Int, par: Int, strokes: Int, putts: Int
    public init(hole: Int, par: Int, strokes: Int, putts: Int) { self.hole = hole; self.par = par; self.strokes = strokes; self.putts = putts }
    public var body: some View {
        VStack(spacing: 5) {
            Text("第\(hole)洞 · Par \(par) · 记分").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            Spacer(minLength: 2)
            stepper("总杆", "\(strokes)", big: true, color: F4.green)
            Spacer(minLength: 2)
            stepper("推杆", "\(putts)", big: false)
            Spacer(minLength: 2)
            Text("下一步 · 球道命中 ›").font(.system(size: 10, weight: .semibold)).foregroundStyle(F4.green)
        }
        .padding(.horizontal, 14).padding(.vertical, 15)
        .frame(width: 198, height: 242).background(Color.black)
    }
}

// MARK: - 记分 · 球道 + 罚杆
public struct WatchScoreFairwayView: View {
    public let fairway: Int   // -1 left, 0 centre, 1 right
    public let penalty: Int
    public init(fairway: Int, penalty: Int) { self.fairway = fairway; self.penalty = penalty }
    public var body: some View {
        VStack(spacing: 9) {
            Text("球道命中").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            HStack(spacing: 6) { fw("左偏", -1); fw("中", 0); fw("右偏", 1) }
            Spacer(minLength: 2)
            stepper("罚杆", "\(penalty)", big: false)
            Spacer(minLength: 2)
            Text("完成 ✓").font(.system(size: 13, weight: .bold)).foregroundStyle(.black)
                .frame(maxWidth: .infinity, minHeight: 34).background(RoundedRectangle(cornerRadius: 11).fill(F4.green))
        }
        .padding(.horizontal, 14).padding(.vertical, 15)
        .frame(width: 198, height: 242).background(Color.black)
    }
    private func fw(_ t: String, _ v: Int) -> some View {
        Text(t).font(.system(size: 11.5, weight: .semibold)).foregroundStyle(fairway == v ? .black : .white)
            .frame(maxWidth: .infinity, minHeight: 42)
            .background(RoundedRectangle(cornerRadius: 10).fill(fairway == v ? F4.green : Color.white.opacity(0.08)))
    }
}

// MARK: - 结束球局 (summary + actions)
public struct WatchEndRoundView: View {
    public let course: String, toPar: Int, strokes: Int, putts: Int, gir: Int, fir: Int
    public init(course: String, toPar: Int, strokes: Int, putts: Int, gir: Int, fir: Int) {
        self.course = course; self.toPar = toPar; self.strokes = strokes; self.putts = putts; self.gir = gir; self.fir = fir
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("结束球局").font(.system(size: 14, weight: .bold)).foregroundStyle(.white)
            Text(course).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
            HStack(spacing: 10) {
                stat("成绩", toPar == 0 ? "E" : (toPar > 0 ? "+\(toPar)" : "\(toPar)"), F4.yellow)
                stat("总杆", "\(strokes)", .white)
                stat("推杆", "\(putts)", .white)
            }
            HStack(spacing: 10) { stat("GIR", "\(gir)%", F4.green); stat("球道", "\(fir)%", F4.blue) }
            Spacer(minLength: 2)
            Text("保存").font(.system(size: 13, weight: .bold)).foregroundStyle(.black)
                .frame(maxWidth: .infinity, minHeight: 32).background(RoundedRectangle(cornerRadius: 10).fill(F4.green))
            HStack(spacing: 6) { minor("编辑分数"); minor("暂停"); minor("放弃") }
        }
        .padding(.horizontal, 14).padding(.top, 16)
        .frame(width: 198, height: 242, alignment: .topLeading).background(Color.black)
    }
    private func stat(_ l: String, _ v: String, _ c: Color) -> some View {
        VStack(spacing: 0) {
            Text(v).font(.system(size: 17, weight: .bold, design: .rounded)).monospacedDigit().foregroundStyle(c)
            Text(l).font(.system(size: 8.5)).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity)
    }
    private func minor(_ t: String) -> some View {
        Text(t).font(.system(size: 9.5, weight: .medium)).foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 26).background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.08)))
    }
}

// MARK: - 击球建议 (Virtual Caddie) on the REAL hole map — club combo + avg strokes + dispersion box + line
public struct WatchCaddieDetailView: View {
    public let club: String        // combo, e.g. "3木 · PW"
    public let expStrokes: Double
    public let onGreenPct: Int
    public init(club: String, expStrokes: Double, onGreenPct: Int) {
        self.club = club; self.expStrokes = expStrokes; self.onGreenPct = onGreenPct
    }
    public var body: some View {
        Canvas { ctx, size in
            let mapCX = size.width * 0.66
            let t = WatchHoleMapSample.drawInto(&ctx, size: size, centerImg: WatchHoleMapSample.youPx,
                                                centerCanvas: CGPoint(x: mapCX, y: size.height * 0.62), scale: 0.34)
            // mask left 40% (stats column) to black
            ctx.fill(Path(CGRect(x: 0, y: 0, width: size.width * 0.40, height: size.height)), with: .color(.black))
            let you = t(WatchHoleMapSample.youPx), layup = t(WatchHoleMapSample.layupPx)
            let green = t(WatchHoleMapSample.pinPx), apex = t(WatchHoleMapSample.apexPx)
            // caddie line you→lay-up (solid) → green (dashed)
            var dash = Path(); dash.move(to: layup); dash.addQuadCurve(to: green, control: t(WatchHoleMapSample.greenCtrlPx))
            ctx.stroke(dash, with: .color(.white.opacity(0.8)), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [4, 3]))
            var solid = Path(); solid.move(to: you); solid.addQuadCurve(to: layup, control: apex)
            ctx.stroke(solid, with: .color(F4.green), style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
            // shot-DISPERSION BOX at the lay-up (Garmin's white rectangle)
            let box = CGRect(x: layup.x - 17, y: layup.y - 15, width: 34, height: 30)
            ctx.stroke(Path(roundedRect: box, cornerRadius: 3), with: .color(.white.opacity(0.85)), style: StrokeStyle(lineWidth: 1.4))
            ctx.fill(Path(ellipseIn: CGRect(x: layup.x - 3, y: layup.y - 3, width: 6, height: 6)), with: .color(.white))
            // you dot
            let yr = CGRect(x: you.x - 4, y: you.y - 4, width: 8, height: 8)
            ctx.fill(Path(ellipseIn: yr), with: .color(F4.blue))
            ctx.stroke(Path(ellipseIn: yr), with: .color(.white), style: StrokeStyle(lineWidth: 1.3))
            // labels: club combo (top over map), 平均杆数 (left), on-green %, ‹ › arrows
            ctx.draw(ctx.resolve(Text(club).font(.system(size: 14, weight: .bold)).foregroundColor(.white)), at: CGPoint(x: mapCX, y: 16))
            ctx.draw(ctx.resolve(Text("平均杆数").font(.system(size: 11)).foregroundColor(Color(white: 0.8))), at: CGPoint(x: size.width * 0.20, y: size.height * 0.36))
            ctx.draw(ctx.resolve(Text(String(format: "%.1f", expStrokes)).font(.system(size: 36, weight: .bold, design: .rounded)).foregroundColor(.white)), at: CGPoint(x: size.width * 0.20, y: size.height * 0.52))
            ctx.draw(ctx.resolve(Text("上果岭 \(onGreenPct)%").font(.system(size: 10, weight: .semibold)).foregroundColor(F4.green)), at: CGPoint(x: size.width * 0.20, y: size.height * 0.68))
            ctx.draw(ctx.resolve(Text("‹").font(.system(size: 20, weight: .bold)).foregroundColor(.gray)), at: CGPoint(x: 9, y: size.height * 0.5))
            ctx.draw(ctx.resolve(Text("›").font(.system(size: 20, weight: .bold)).foregroundColor(.gray)), at: CGPoint(x: size.width - 9, y: size.height * 0.5))
        }
        .frame(width: 198, height: 242).background(Color.black)
    }
}

// MARK: - 高尔夫菜单 (action-button menu)
public struct WatchGolfMenuView: View {
    public let items: [String]
    public init(items: [String]) { self.items = items }
    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("高尔夫菜单").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            ForEach(0..<min(items.count, 7), id: \.self) { i in
                HStack {
                    Text(items[i]).font(.system(size: 13, weight: .medium)).foregroundStyle(.white)
                    Spacer(minLength: 0)
                    Text("›").font(.system(size: 15)).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 11).padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: 9).fill(Color.white.opacity(0.07)))
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 13).padding(.top, 14)
        .frame(width: 198, height: 242, alignment: .topLeading).background(Color.black)
    }
}

// MARK: - 球杆数据 (per-club stats)
public struct WatchClubStatsView: View {
    public let clubs: [(name: String, dist: Int, acc: String)]
    public init(clubs: [(name: String, dist: Int, acc: String)]) { self.clubs = clubs }
    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("球杆数据 · 平均").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            ForEach(0..<min(clubs.count, 7), id: \.self) { i in
                let c = clubs[i]
                HStack {
                    Text(c.name).font(.system(size: 12.5, weight: .semibold)).foregroundStyle(.white).frame(width: 56, alignment: .leading)
                    Spacer(minLength: 0)
                    Text("\(c.dist)").font(.system(size: 14, weight: .bold, design: .rounded)).monospacedDigit().foregroundStyle(.white)
                    Text("码").font(.system(size: 9)).foregroundStyle(.secondary)
                    Text(c.acc).font(.system(size: 9.5)).foregroundStyle(F4.green).frame(width: 30, alignment: .trailing)
                }
                .padding(.vertical, 2)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.top, 14)
        .frame(width: 198, height: 242, alignment: .topLeading).background(Color.black)
    }
}

// MARK: - 本洞击球 (per-hole AutoShot list)
public struct WatchShotsView: View {
    public let shots: [(n: Int, club: String, dist: Int)]
    public init(shots: [(n: Int, club: String, dist: Int)]) { self.shots = shots }
    public var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("本洞击球").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            ForEach(0..<min(shots.count, 7), id: \.self) { i in
                let s = shots[i]
                HStack {
                    Text("\(s.n)").font(.system(size: 12, weight: .bold)).foregroundStyle(F4.green).frame(width: 18, alignment: .leading)
                    Text(s.club).font(.system(size: 12, weight: .medium)).foregroundStyle(.white)
                    Spacer(minLength: 0)
                    Text("\(s.dist)").font(.system(size: 13, weight: .semibold, design: .rounded)).monospacedDigit().foregroundStyle(.white)
                    Text("码").font(.system(size: 9)).foregroundStyle(.secondary)
                }
                .padding(.vertical, 2.5)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.top, 14)
        .frame(width: 198, height: 242, alignment: .topLeading).background(Color.black)
    }
}
