import SwiftUI

/// 首页 C 版(拼块仪表盘, owner-approved 2026-10-04): a large course card on top, then small
/// widget-like tiles — 成绩 / 备战 / 球包 / 今天 — and 上一场. Pure presentation (inputs only), so
/// the CI design snapshots render every state without a backend.
enum HubBentoStyle {
    /// Warm off-white page ground = #F3F1EA.
    static let ground = Color(red: 243 / 255, green: 241 / 255, blue: 234 / 255)
    /// Course-card / 备战 tile green = #12382B.
    static let deepGreen = Color(red: 18 / 255, green: 56 / 255, blue: 43 / 255)
    /// Fairway green behind a course card without a topo image = #2B6A45.
    static let fairway = Color(red: 43 / 255, green: 106 / 255, blue: 69 / 255)
    /// Lighter fairway (the drawn fairway band and the search card) = #3F8F52.
    static let leaf = Color(red: 63 / 255, green: 143 / 255, blue: 82 / 255)
    /// Putting-green fill = #8BCB7E.
    static let lightGreen = Color(red: 139 / 255, green: 203 / 255, blue: 126 / 255)
    /// Secondary text on the green cards = #DCEFD9.
    static let onGreenSecondary = Color(red: 220 / 255, green: 239 / 255, blue: 217 / 255)
    /// 今天 tile = #FCE9D9 with ink #6B3A16; the clay accent = #B4561B.
    static let warm = Color(red: 252 / 255, green: 233 / 255, blue: 217 / 255)
    static let warmInk = Color(red: 107 / 255, green: 58 / 255, blue: 22 / 255)
    static let clay = Color(red: 180 / 255, green: 86 / 255, blue: 27 / 255)
    /// 球包 tile = #E1ECF7 with ink #2E4A66 and bars #2E5F8F.
    static let sky = Color(red: 225 / 255, green: 236 / 255, blue: 247 / 255)
    static let skyInk = Color(red: 46 / 255, green: 74 / 255, blue: 102 / 255)
    static let navy = Color(red: 46 / 255, green: 95 / 255, blue: 143 / 255)
    /// Flag pennant = #F28C38.
    static let flag = Color(red: 242 / 255, green: 140 / 255, blue: 56 / 255)

    static let heroHeight: CGFloat = 236
    static let tallTileHeight: CGFloat = 150
    static let shortTileHeight: CGFloat = 128
}

extension View {
    /// A bento tile surface: solid fill, 22 pt continuous corners, fixed height.
    func hubBentoTile(_ fill: Color, height: CGFloat) -> some View {
        self
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: height, maxHeight: height, alignment: .topLeading)
            .background(fill)
            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
    }

    /// The large course card surface: at least `heroHeight` tall, the background filling it.
    func hubBentoHero<Background: View>(@ViewBuilder background: () -> Background) -> some View {
        self
            .frame(maxWidth: .infinity, minHeight: HubBentoStyle.heroHeight, alignment: .topLeading)
            .background(background())
            .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
    }
}

/// The white "开球" / "继续第 N 洞" button on a green card.
struct HubBentoPrimaryButtonLabel: View {
    let title: String
    var fullWidth = false

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "play.fill").font(.system(size: 15, weight: .bold))
            Text(title).font(.system(size: 18, weight: .heavy)).lineLimit(1)
        }
        .foregroundStyle(HubBentoStyle.deepGreen)
        .padding(.horizontal, 24)
        .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: 52)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

/// The outlined secondary button on a green card ("结束").
struct HubBentoOutlineButtonLabel: View {
    let title: String
    var width: CGFloat? = nil

    var body: some View {
        Text(title)
            .font(.system(size: 15, weight: .bold))
            .foregroundStyle(.white)
            .frame(width: width, height: 52)
            .frame(minWidth: 44)
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(Color.white.opacity(0.5), lineWidth: 1.5)
            )
            .contentShape(Rectangle())
    }
}

/// A drawn hole (fairway band, green, bunker, flag) behind a course card while its real topo image
/// loads, or when the course has none. Decoration only.
struct HubDrawnHole: View {
    var body: some View {
        GeometryReader { proxy in
            let w = proxy.size.width
            let h = proxy.size.height
            ZStack {
                HubBentoStyle.fairway
                Path { path in
                    path.move(to: CGPoint(x: w * 0.18, y: h + 20))
                    path.addCurve(
                        to: CGPoint(x: w * 0.86, y: h * 0.32),
                        control1: CGPoint(x: w * 0.45, y: h * 0.75),
                        control2: CGPoint(x: w * 0.62, y: h * 0.42)
                    )
                }
                .stroke(HubBentoStyle.leaf, style: StrokeStyle(lineWidth: 44, lineCap: .round))
                Ellipse()
                    .fill(HubBentoStyle.lightGreen)
                    .frame(width: 62, height: 44)
                    .position(x: w * 0.87, y: h * 0.3)
                Ellipse()
                    .fill(Color(red: 232 / 255, green: 215 / 255, blue: 168 / 255))
                    .frame(width: 28, height: 15)
                    .position(x: w * 0.74, y: h * 0.45)
                Path { path in
                    path.move(to: CGPoint(x: w * 0.87, y: h * 0.3))
                    path.addLine(to: CGPoint(x: w * 0.87, y: h * 0.3 - 34))
                }
                .stroke(Color.white, lineWidth: 2)
                Path { path in
                    let top = CGPoint(x: w * 0.87, y: h * 0.3 - 34)
                    path.move(to: top)
                    path.addLine(to: CGPoint(x: top.x + 17, y: top.y + 6))
                    path.addLine(to: CGPoint(x: top.x, y: top.y + 12))
                    path.closeSubpath()
                }
                .fill(HubBentoStyle.flag)
            }
        }
        .accessibilityHidden(true)
    }
}

/// One hole of the in-progress loop on the live card.
struct HubHoleDot: Equatable, Identifiable {
    let hole: Int
    /// Strokes to par on a scored hole; nil when not scored yet.
    let toPar: Int?
    let isCurrent: Bool
    var id: Int { hole }

    var fill: Color {
        guard let toPar else { return Color.white.opacity(isCurrent ? 0 : 0.16) }
        switch toPar {
        case ...(-1): return Color(red: 127 / 255, green: 184 / 255, blue: 232 / 255)
        case 0: return Color(red: 157 / 255, green: 184 / 255, blue: 166 / 255)
        case 1: return Color(red: 233 / 255, green: 160 / 255, blue: 106 / 255)
        default: return Color(red: 224 / 255, green: 122 / 255, blue: 95 / 255)
        }
    }

    /// The nine (or fewer) holes of the loop that holds `activeHole`, coloured by their scores.
    static func loopDots(
        roundHoles: [Int],
        activeHole: Int,
        scoredToPar: (Int) -> Int?
    ) -> [HubHoleDot] {
        let sorted = roundHoles.sorted()
        guard let index = sorted.firstIndex(of: activeHole) else { return [] }
        let start = (index / 9) * 9
        return sorted[start..<min(start + 9, sorted.count)].map { hole in
            HubHoleDot(hole: hole, toPar: scoredToPar(hole), isCurrent: hole == activeHole)
        }
    }
}

/// 成绩: the recent scores as a small line, the latest score and the recent average.
struct HubScoresTile: View {
    /// Oldest → newest, comparable rounds only (see `HubScoresTile.recentScores`).
    let scores: [Int]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("成绩").font(.subheadline.weight(.bold)).foregroundStyle(.primary)
                Spacer()
                if scores.count >= 2 {
                    Text("近 \(scores.count) 场").font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 6)
            if scores.count >= 2 {
                HubSparkline(values: scores.map(Double.init))
                    .stroke(HubBentoStyle.clay, style: StrokeStyle(lineWidth: 2.4, lineCap: .round, lineJoin: .round))
                    .frame(height: 44)
                    .accessibilityHidden(true)
            } else {
                Text("打完一场就有走势")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 6)
            if let latest = scores.last {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("\(latest)")
                        .font(.system(size: 26, weight: .heavy, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.primary)
                    if let averageText {
                        Text(averageText).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    }
                }
            } else {
                Text("球局 · 统计").font(.caption).foregroundStyle(.secondary)
            }
        }
        .hubBentoTile(.white, height: HubBentoStyle.tallTileHeight)
        .accessibilityElement(children: .combine)
    }

    private var averageText: String? {
        guard scores.count >= 2 else { return nil }
        let average = Double(scores.reduce(0, +)) / Double(scores.count)
        return "均 \(Int(average.rounded()))"
    }

    /// The last eight full rounds (18 holes), oldest first; nine-hole rounds are not comparable.
    static func recentScores(history: [HistoryRoundCard], limit: Int = 8) -> [Int] {
        let full = history.compactMap { card -> Int? in
            guard (card.holesCompleted ?? 0) >= 18, let score = card.score, score > 0 else { return nil }
            return score
        }
        return Array(full.prefix(limit).reversed())
    }
}

/// A line through `values` scaled to the frame. Higher (worse) scores sit higher, so a falling
/// line reads as improving.
struct HubSparkline: Shape {
    let values: [Double]

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard values.count >= 2, let low = values.min(), let high = values.max() else { return path }
        let span = max(high - low, 1)
        let step = rect.width / CGFloat(values.count - 1)
        for (index, value) in values.enumerated() {
            let point = CGPoint(
                x: rect.minX + CGFloat(index) * step,
                y: rect.minY + rect.height * CGFloat((high - value) / span)
            )
            if index == 0 { path.move(to: point) } else { path.addLine(to: point) }
        }
        return path
    }
}

/// 备战: the downloaded courses count on the deep-green tile.
struct HubPrepTile: View {
    let downloadedCount: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("备战").font(.subheadline.weight(.bold)).foregroundStyle(.white)
            Spacer(minLength: 4)
            Image(systemName: "scope")
                .font(.system(size: 40, weight: .regular))
                .foregroundStyle(HubBentoStyle.lightGreen)
                .accessibilityHidden(true)
            Spacer(minLength: 4)
            Text(downloadedCount > 0 ? "逐洞攻略 · 已下载 \(downloadedCount) 个" : "逐洞攻略 · 搜索球场")
                .font(.caption)
                .foregroundStyle(HubBentoStyle.onGreenSecondary)
                .lineLimit(2)
        }
        .hubBentoTile(HubBentoStyle.deepGreen, height: HubBentoStyle.tallTileHeight)
        .accessibilityElement(children: .combine)
    }
}

/// 球包: the bag's carries as bars, longest first, and the longest club.
struct HubBagTile: View {
    /// Longest first; at most seven.
    let carries: [(club: String, yards: Int)]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("球包").font(.subheadline.weight(.bold)).foregroundStyle(.primary)
            Spacer(minLength: 4)
            if let longest = carries.first?.yards, longest > 0 {
                HStack(alignment: .bottom, spacing: 5) {
                    ForEach(Array(carries.enumerated()), id: \.offset) { index, row in
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .fill(HubBentoStyle.navy.opacity(1 - Double(index) * 0.09))
                            .frame(width: 12, height: max(8, 48 * CGFloat(row.yards) / CGFloat(longest)))
                    }
                }
                .frame(height: 48, alignment: .bottom)
                .accessibilityHidden(true)
                Spacer(minLength: 4)
                Text("\(carries[0].club) \(longest) 码")
                    .font(.caption)
                    .foregroundStyle(HubBentoStyle.skyInk)
                    .lineLimit(1)
            } else {
                Text("设置你的球杆和距离")
                    .font(.caption)
                    .foregroundStyle(HubBentoStyle.skyInk)
            }
        }
        .hubBentoTile(HubBentoStyle.sky, height: HubBentoStyle.shortTileHeight)
        .accessibilityElement(children: .combine)
    }

    static func carries(from profiles: [ClubProfile], limit: Int = 7) -> [(club: String, yards: Int)] {
        profiles
            .filter { $0.medianM.isFinite && $0.medianM > 0 }
            .sorted { $0.medianM > $1.medianM }
            .prefix(limit)
            .map { (club: zhClubName($0.clubName), yards: Int(($0.medianM * 1.0936133).rounded())) }
    }
}

/// 今天: temperature, condition, wind and rain chance; quiet when the weather is unknown.
struct HubWeatherTile: View {
    let weather: HomeWeatherPresentation?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("今天").font(.subheadline.weight(.bold)).foregroundStyle(.primary)
            Spacer(minLength: 2)
            if let weather {
                HStack(alignment: .center, spacing: 6) {
                    Image(systemName: weather.symbolName)
                        .font(.system(size: 24, weight: .medium))
                        .foregroundStyle(HubBentoStyle.clay)
                        .accessibilityHidden(true)
                    Text(weather.temperatureText)
                        .font(.system(size: 26, weight: .heavy, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.primary)
                    if let condition = weather.conditionText {
                        Text(condition)
                            .font(.subheadline.weight(.bold))
                            .foregroundStyle(HubBentoStyle.warmInk)
                    }
                }
                Spacer(minLength: 2)
                VStack(alignment: .leading, spacing: 1) {
                    if let wind = weather.windText { Text(wind) }
                    if let rain = weather.rainText { Text(rain) }
                }
                .font(.caption)
                .foregroundStyle(HubBentoStyle.warmInk)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
            } else {
                Image(systemName: "cloud.sun")
                    .font(.system(size: 24, weight: .medium))
                    .foregroundStyle(HubBentoStyle.clay.opacity(0.6))
                    .accessibilityHidden(true)
                Spacer(minLength: 2)
                Text("暂无天气")
                    .font(.caption)
                    .foregroundStyle(HubBentoStyle.warmInk)
            }
        }
        .hubBentoTile(HubBentoStyle.warm, height: HubBentoStyle.shortTileHeight)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("home-tile-weather")
    }
}
