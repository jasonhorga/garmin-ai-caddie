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

// MARK: - 击球建议 detail (club, alternatives, expected strokes, on-green %)
public struct WatchCaddieDetailView: View {
    public let club: String, note: String
    public let expStrokes: Double, onGreenPct: Int
    public init(club: String, note: String, expStrokes: Double, onGreenPct: Int) {
        self.club = club; self.note = note; self.expStrokes = expStrokes; self.onGreenPct = onGreenPct
    }
    public var body: some View {
        VStack(spacing: 5) {
            Text("球童建议").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            HStack(spacing: 12) {
                Text("‹").font(.system(size: 22, weight: .bold)).foregroundStyle(.white.opacity(0.6))
                Text(club).font(.system(size: 22, weight: .bold)).foregroundStyle(.white)
                Text("›").font(.system(size: 22, weight: .bold)).foregroundStyle(.white.opacity(0.6))
            }
            Text(note).font(.system(size: 10, weight: .medium)).foregroundStyle(F4.green)
            HStack(spacing: 18) {
                col2("预期杆数", String(format: "%.1f", expStrokes), F4.yellow)
                col2("上果岭", "\(onGreenPct)%", F4.green)
            }
            .padding(.top, 2)
            // dispersion box mini
            ZStack {
                RoundedRectangle(cornerRadius: 8).stroke(F4.green.opacity(0.5), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .frame(width: 84, height: 40)
                Circle().fill(F4.green).frame(width: 7, height: 7)
            }
            .padding(.top, 2)
            Text("落点分布(基于你的历史)").font(.system(size: 8.5)).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14).padding(.vertical, 14)
        .frame(width: 198, height: 242).background(Color.black)
    }
    private func col2(_ l: String, _ v: String, _ c: Color) -> some View {
        VStack(spacing: 0) {
            Text(v).font(.system(size: 19, weight: .bold, design: .rounded)).foregroundStyle(c)
            Text(l).font(.system(size: 8.5)).foregroundStyle(.secondary)
        }
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
