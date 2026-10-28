import SwiftUI

/// C99 home surfaces: the play entry, shortcut chips, trend bars and live progress card.
enum HubBentoStyle {
    /// Warm off-white page ground = #F3F1EA.
    static let ground = Color(red: 243 / 255, green: 241 / 255, blue: 234 / 255)
    /// Primary green = #12382B.
    static let deepGreen = Color(red: 18 / 255, green: 56 / 255, blue: 43 / 255)
    /// Putting-green fill = #8BCB7E.
    static let lightGreen = Color(red: 139 / 255, green: 203 / 255, blue: 126 / 255)
    /// Secondary text on the green cards = #DCEFD9.
    static let onGreenSecondary = Color(red: 220 / 255, green: 239 / 255, blue: 217 / 255)
    static let clay = Color(red: 180 / 255, green: 86 / 255, blue: 27 / 255)

    static let heroHeight: CGFloat = 236
}

extension View {
    /// The large course card surface: at least `heroHeight` tall, the background filling it.
    func hubBentoHero<Background: View>(@ViewBuilder background: () -> Background) -> some View {
        self
            .frame(maxWidth: .infinity, minHeight: HubBentoStyle.heroHeight, alignment: .topLeading)
            .background(background())
            .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
    }
}

/// The white "继续" button on the live card.
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

/// C99's single home entry: course discovery starts here, then the selected course opens its tee page.
struct HubStartPlayCard: View {
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "figure.golf")
                .font(.system(size: 28, weight: .bold))
                .foregroundStyle(HubBentoStyle.lightGreen)
            VStack(alignment: .leading, spacing: 3) {
                Text("打一场球")
                    .font(.title2.weight(.heavy))
                Text("找球场，选发球台后开始")
                    .font(.subheadline)
                    .foregroundStyle(HubBentoStyle.onGreenSecondary)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.headline.weight(.bold))
                .foregroundStyle(HubBentoStyle.onGreenSecondary)
        }
        .foregroundStyle(.white)
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .leading)
        .background(HubBentoStyle.deepGreen)
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
    }
}

/// Recovery card for a deferred finish rejected after the round left the live screen.
struct HubDeferredFinishRecoveryCard: View {
    let recovery: DeferredFinishRecovery
    let onResume: () -> Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(HubBentoStyle.clay)
                Text("第 \(recovery.hole) 洞记分被拒 · 去重录")
                    .font(.title3.weight(.heavy))
            }
            Text(recovery.prompt)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if recovery.holeAvailable {
                Button("去重录") {
                    _ = onResume()
                }
                .buttonStyle(.borderedProminent)
                .tint(HubBentoStyle.deepGreen)
            } else {
                Text("第 \(recovery.hole) 洞已从当前球局移除，请恢复该九洞后再处理")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(HubBentoStyle.clay)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("home-deferred-finish-recovery")
    }
}

struct HubQuickCourseChip: View {
    let title: String
    let isNearby: Bool

    var body: some View {
        HStack(spacing: 5) {
            if isNearby { Image(systemName: "location.fill").font(.caption2) }
            Text(title).lineLimit(1)
        }
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(HubBentoStyle.deepGreen)
        .padding(.horizontal, 13)
        .frame(minHeight: 38)
        .background(Color.white)
        .clipShape(Capsule())
    }
}

struct HubRecentTrendRow: View {
    let scores: [Int]

    /// Oldest → newest full rounds only; nine-hole scores do not mix into the trend.
    static func recentScores(history: [HistoryRoundCard], limit: Int = 5) -> [Int] {
        let full = history.compactMap { card -> Int? in
            guard (card.holesCompleted ?? 0) >= 18, let score = card.score, score > 0 else { return nil }
            return score
        }
        return Array(full.prefix(limit).reversed())
    }

    var body: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("最近走势").font(.subheadline.weight(.bold))
                Text("最近 \(scores.count) 场 · 平均 \(average)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 4)
            HubScoreBars(values: scores)
                .frame(width: 92, height: 34)
            Image(systemName: "chevron.right")
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14)
        .frame(maxWidth: .infinity, minHeight: 72)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var average: Int {
        Int((Double(scores.reduce(0, +)) / Double(scores.count)).rounded())
    }
}

struct HubScoreBars: View {
    let values: [Int]

    var body: some View {
        let low = values.min() ?? 0
        let high = max(values.max() ?? 0, low + 1)
        HStack(alignment: .bottom, spacing: 5) {
            ForEach(Array(values.enumerated()), id: \.offset) { _, value in
                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .fill(HubBentoStyle.clay)
                    .frame(height: max(5, CGFloat(value - low + 1) / CGFloat(high - low + 1) * 30))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
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

/// 主卡 · 进行中, before the round's package has loaded: the same deep-green card, 进行中 and a
/// spinner instead of a blank top. Informational only; the full card replaces it.
struct HubInProgressLoadingCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Circle().fill(HubBentoStyle.lightGreen).frame(width: 8, height: 8)
                Text("进行中")
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(HubBentoStyle.lightGreen)
            }
            Text("正在载入这场的球场数据")
                .font(.title3.weight(.heavy))
                .foregroundStyle(.white)
            Text("载入后可继续记分")
                .font(.subheadline)
                .foregroundStyle(HubBentoStyle.onGreenSecondary)
            Spacer(minLength: 12)
            ProgressView()
                .tint(.white)
        }
        .padding(18)
        .hubBentoHero { HubBentoStyle.deepGreen }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("home-in-progress-loading")
    }
}
