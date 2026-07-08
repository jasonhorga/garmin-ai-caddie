import SwiftUI

/// round-14 (Watch standalone, DESIGN REVIEW): the **round-start flow** screens, in the same black / HIG /
/// green-accent design language as `WatchHoleMapView`, so the whole "open watch → play" journey can be
/// reviewed as one strip: 选球场 → 选洞数(9/18 · 哪个9) → 选发球台 → (洞视图) → 积分卡 / 选洞.
///
/// All are plain `VStack`/`HStack` of `Text` + `RoundedRectangle` (safe under watchOS `ImageRenderer`; no
/// `ScrollView` — its content doesn't rasterise — and no free-floating `Path{}.fill()` child views).
private enum Flow {
    static let green = Color(red: 0.30, green: 0.86, blue: 0.46)
    static let yellow = Color(red: 1.0, green: 0.83, blue: 0.28)
    static let blue = Color(red: 0.35, green: 0.72, blue: 1.0)
}

private extension View {
    func flowScreen() -> some View {
        self.frame(width: 198, height: 242, alignment: .topLeading).background(Color.black)
    }
}

private func scoreColor(_ toPar: Int) -> Color {
    switch toPar {
    case ...(-2): return Color(red: 0.20, green: 0.45, blue: 0.95)   // eagle+ dark blue
    case -1: return Flow.blue                                        // birdie
    case 0: return Flow.green                                        // par
    case 1: return Flow.yellow                                       // bogey
    case 2: return Color(red: 1.0, green: 0.62, blue: 0.04)          // double orange
    default: return Color(red: 1.0, green: 0.27, blue: 0.23)         // triple+ red
    }
}

// MARK: - 1) 选球场 (GPS-found nearby courses)
public struct WatchCourseSelectView: View {
    public let rows: [(name: String, meta: String, near: Bool)]
    public init(rows: [(name: String, meta: String, near: Bool)]) { self.rows = rows }
    public var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("附近球场").font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
            ForEach(0..<rows.count, id: \.self) { i in
                let r = rows[i]
                HStack(spacing: 8) {
                    Circle().fill(r.near ? Flow.green : Color.white.opacity(0.25)).frame(width: 7, height: 7)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(r.name).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(.white).lineLimit(1)
                        Text(r.meta).font(.system(size: 10)).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Text("›").font(.system(size: 17)).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 10).padding(.vertical, 8)
                .background(RoundedRectangle(cornerRadius: 11).fill(r.near ? Flow.green.opacity(0.16) : Color.white.opacity(0.06)))
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.top, 18)
        .flowScreen()
    }
}

// MARK: - 2) 选洞数 (9 / 18, or which 9 to start)
public struct WatchNineSelectView: View {
    public let title: String
    public let options: [(label: String, sub: String, primary: Bool)]
    public init(title: String, options: [(label: String, sub: String, primary: Bool)]) {
        self.title = title; self.options = options
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
            ForEach(0..<options.count, id: \.self) { i in
                let o = options[i]
                HStack {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(o.label).font(.system(size: o.primary ? 17 : 14, weight: .bold)).foregroundStyle(.white)
                        Text(o.sub).font(.system(size: 10)).foregroundStyle(o.primary ? Flow.green : Color.secondary)
                    }
                    Spacer(minLength: 0)
                    Text("›").font(.system(size: 16)).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12).padding(.vertical, o.primary ? 12 : 9)
                .background(RoundedRectangle(cornerRadius: 12).fill(o.primary ? Flow.green.opacity(0.18) : Color.white.opacity(0.06)))
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.top, 20)
        .flowScreen()
    }
}

// MARK: - 3) 选发球台 (tee boxes)
public struct WatchTeeSelectView: View {
    public let title: String
    public let tees: [(name: String, yards: Int, color: Color, selected: Bool)]
    public init(title: String, tees: [(name: String, yards: Int, color: Color, selected: Bool)]) {
        self.title = title; self.tees = tees
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
            ForEach(0..<tees.count, id: \.self) { i in
                let t = tees[i]
                HStack(spacing: 9) {
                    RoundedRectangle(cornerRadius: 3).fill(t.color).frame(width: 12, height: 12)
                    Text(t.name).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(.white)
                    Spacer(minLength: 0)
                    Text("\(t.yards)").font(.system(size: 13, weight: .semibold, design: .rounded))
                        .monospacedDigit().foregroundStyle(.white)
                    Text("码").font(.system(size: 9)).foregroundStyle(.secondary)
                    Text(t.selected ? "✓" : " ").font(.system(size: 13, weight: .bold)).foregroundStyle(Flow.green)
                }
                .padding(.horizontal, 10).padding(.vertical, 7)
                .background(RoundedRectangle(cornerRadius: 10).fill(t.selected ? Flow.green.opacity(0.16) : Color.white.opacity(0.06)))
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.top, 16)
        .flowScreen()
    }
}

// MARK: - 4) 积分卡 (front-nine horizontal scorecard)
public struct WatchRoundScorecardView: View {
    public let holes: [(hole: Int, par: Int, score: Int?)]   // score nil = not yet played
    public let toPar: Int
    public init(holes: [(hole: Int, par: Int, score: Int?)], toPar: Int) { self.holes = holes; self.toPar = toPar }
    public var body: some View {
        ZStack(alignment: .topTrailing) {
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text("积分卡").font(.system(size: 14, weight: .bold)).foregroundStyle(.white)
                    Spacer()
                    Text(toPar == 0 ? "E" : (toPar > 0 ? "+\(toPar)" : "\(toPar)"))
                        .font(.system(size: 16, weight: .bold, design: .rounded)).foregroundStyle(Flow.yellow)
                }
                .padding(.bottom, 3)
                ForEach(0..<holes.count, id: \.self) { i in
                    let h = holes[i]
                    HStack(spacing: 0) {
                        Text("\(h.hole)").font(.system(size: 12, weight: .semibold)).monospacedDigit()
                            .foregroundStyle(.white).frame(width: 20, alignment: .leading)
                        Text("Par \(h.par)").font(.system(size: 10)).foregroundStyle(.secondary)
                            .frame(width: 48, alignment: .leading)
                        Spacer(minLength: 0)
                        if let s = h.score {
                            Text("\(s)").font(.system(size: 15, weight: .bold)).monospacedDigit()
                                .foregroundStyle(scoreColor(s - h.par)).frame(width: 28, alignment: .trailing)
                        } else {
                            Text("–").font(.system(size: 12)).foregroundStyle(.secondary).frame(width: 28, alignment: .trailing)
                        }
                    }
                    .padding(.vertical, 1.5)
                }
                Spacer(minLength: 0)
            }
            .padding(.leading, 16).padding(.trailing, 12).padding(.top, 16)
            // crown-scroll indicator on the right (all 18 holes scroll; thumb near top = front nine).
            VStack {
                ZStack(alignment: .top) {
                    Capsule().fill(Color.white.opacity(0.18)).frame(width: 3, height: 150)
                    Capsule().fill(Color.white.opacity(0.7)).frame(width: 3, height: 78)
                }
                .padding(.top, 44).padding(.trailing, 3)
                Spacer()
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .flowScreen()
    }
}

// MARK: - 5) 选洞 (hole grid)
public struct WatchHoleGridView: View {
    public let holes: [(hole: Int, toPar: Int?, current: Bool)]
    public init(holes: [(hole: Int, toPar: Int?, current: Bool)]) { self.holes = holes }
    public var body: some View {
        ZStack(alignment: .topTrailing) {
            VStack(alignment: .leading, spacing: 8) {
                Text("选择球洞 · 转冠滚动").font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
                // 3-col grid, 52pt cells (≥ 44pt HIG target — AI review: 4-col 36pt still too small); 18 holes
                // overflow → crown-scrolls. Bigger targets + scroll beats a flat wall of tiny circles.
                VStack(spacing: 9) {
                    ForEach(0..<6, id: \.self) { row in
                        HStack(spacing: 10) {
                            ForEach(0..<3, id: \.self) { c in
                                let idx = row * 3 + c
                                if idx < holes.count { cell(holes[idx]) } else { Color.clear.frame(width: 52, height: 52) }
                            }
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(.leading, 14).padding(.trailing, 10).padding(.top, 16)
            // crown-scroll indicator (thumb near top = holes 1–16 shown, 17–18 below the fold).
            VStack {
                ZStack(alignment: .top) {
                    Capsule().fill(Color.white.opacity(0.18)).frame(width: 3, height: 150)
                    Capsule().fill(Color.white.opacity(0.7)).frame(width: 3, height: 96)
                }
                .padding(.top, 42).padding(.trailing, 2)
                Spacer()
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .flowScreen()
    }
    private func cell(_ h: (hole: Int, toPar: Int?, current: Bool)) -> some View {
        Text("\(h.hole)")
            .font(.system(size: 19, weight: .bold)).monospacedDigit()
            .foregroundStyle(h.current ? .black : .white)
            .frame(width: 52, height: 52)
            .background(Circle().fill(cellFill(h)))
            .overlay(Circle().stroke(h.current ? Flow.green : Color.clear, lineWidth: 3))
    }
    private func cellFill(_ h: (hole: Int, toPar: Int?, current: Bool)) -> Color {
        if h.current { return Flow.green }
        if let tp = h.toPar { return scoreColor(tp).opacity(0.85) }
        return Color.white.opacity(0.10)
    }
}
