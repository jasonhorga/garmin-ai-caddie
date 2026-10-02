import Foundation

/// B5b 时间与频率 (README §9, `stats.html` 4): one chart switched between 逐场 / 月 / 季 / 年 over
/// the whole history, the quarter (or year) cards under it, and the play calendar. Pure, so the
/// grouping is testable against fixture payloads.
enum ResultsTimePresentation {
    enum Grain: String, CaseIterable, Identifiable {
        case round, month, quarter, year
        var id: String { rawValue }
        var title: String {
            switch self {
            case .round: return "逐场"
            case .month: return "月"
            case .quarter: return "季"
            case .year: return "年"
            }
        }
    }

    /// 逐场 shows the newest rounds only; the period grains cover the whole history.
    static let roundChartLimit = 30

    enum Target: Equatable {
        case round(StatsTrendPoint)
        case period(String)
    }

    struct ChartRow: Equatable, Identifiable {
        var id: Int { index }
        /// 0 = oldest shown.
        let index: Int
        let label: String
        let value: Double
        let target: Target
    }

    /// The chart for `grain`, oldest first: each 18-hole score (逐场), or each period's 18-hole
    /// average. Periods without a scored 18-hole round, and the "unknown" bucket, are left out.
    static func chartRows(_ stats: MobileStats, grain: Grain) -> [ChartRow] {
        let rows: [(String, Double, Target)]
        switch grain {
        case .round:
            rows = (stats.trend?.points ?? []).suffix(roundChartLimit).compactMap { point in
                point.score.map { (String(point.date.prefix(10)), Double($0), Target.round(point)) }
            }
        case .month, .quarter, .year:
            rows = periods(stats.time, grain).reversed().compactMap { period in
                guard period.key != "unknown", let average = period.average18 else { return nil }
                return (period.key, average, Target.period(period.key))
            }
        }
        return rows.enumerated().map { ChartRow(index: $0.offset, label: $0.element.0, value: $0.element.1, target: $0.element.2) }
    }

    static func periods(_ time: StatsTime?, _ grain: Grain) -> [StatsPeriod] {
        guard let time else { return [] }
        switch grain {
        case .round: return []
        case .month: return time.byMonth
        case .quarter: return time.byQuarter
        case .year: return time.byYear
        }
    }

    struct PeriodCard: Equatable, Identifiable {
        var id: String { key }
        let key: String
        let title: String
        /// "4 场 · 均杆 87.5"; a missing average reads "—".
        let headline: String
        /// 最佳 / 最差 / 鸟 / 场 / 双柏+ / 场, each "—" when unknown.
        let best: String
        let worst: String
        let birdiesPerRound: String
        let doublesPerRound: String
    }

    /// The cards under the chart: years for 年, otherwise the newest quarters (README §9 "季度（或
    /// 历年）卡片"). `heading` names what is listed.
    static func periodCards(_ time: StatsTime?, grain: Grain, limit: Int = 8) -> (heading: String, cards: [PeriodCard]) {
        let isYear = grain == .year
        let source = (isYear ? time?.byYear : time?.byQuarter) ?? []
        let cards = source.filter { $0.key != "unknown" }.prefix(limit).map(card)
        return (isYear ? "历年" : "按季度", Array(cards))
    }

    static func card(_ period: StatsPeriod) -> PeriodCard {
        let rounds = period.roundCount ?? 0
        func perRound(_ count: Int?) -> String {
            guard let count, rounds > 0 else { return "—" }
            // Half away from zero (9 / 4 = 2.25 reads 2.3); "%.1f" alone rounds half to even.
            return String(format: "%.1f", (Double(count) / Double(rounds) * 10).rounded() / 10)
        }
        return PeriodCard(
            key: period.key,
            title: periodTitle(period.key),
            headline: "\(rounds) 场 · 均杆 \(period.average18.map { String(format: "%.1f", $0) } ?? "—")",
            best: period.bestScore.map(String.init) ?? "—",
            worst: period.worstScore.map(String.init) ?? "—",
            birdiesPerRound: perRound(period.outcomes?.birdie),
            doublesPerRound: perRound(period.outcomes?.doubleOrWorse)
        )
    }

    /// "2026-Q2" -> "2026 年第 2 季度", "2026-05" -> "2026 年 5 月", "2026" -> "2026 年".
    static func periodTitle(_ key: String) -> String {
        let parts = key.split(separator: "-").map(String.init)
        if parts.count == 2, parts[1].hasPrefix("Q") { return "\(parts[0]) 年第 \(parts[1].dropFirst()) 季度" }
        if parts.count == 2, let month = Int(parts[1]) { return "\(parts[0]) 年 \(month) 月" }
        if parts.count == 1, parts[0].count == 4 { return "\(parts[0]) 年" }
        return key
    }

    // MARK: 打球日历

    struct CalendarSummary: Equatable {
        let year: Int
        let rounds: Int
        /// Rounds per calendar month of the represented year — January through the latest month
        /// with a round, months without one counted as zero ("月均场数"); nil without any round.
        let perMonth: Double?
        /// The month of `year` with the most rounds (ties: the earlier month).
        let busiestMonth: Int?

        var text: String {
            var parts = ["\(rounds) 场"]
            if let perMonth { parts.append("月均 \(String(format: "%.1f", (perMonth * 10).rounded() / 10))") }
            if let busiestMonth { parts.append("\(busiestMonth) 月最多") }
            return parts.joined(separator: " · ")
        }
    }

    /// The newest year with a played day, summarised from `byDay` (keys "YYYY-MM-DD").
    static func calendarSummary(_ time: StatsTime?) -> CalendarSummary? {
        let days = (time?.byDay ?? []).filter { $0.key.count >= 10 && ($0.roundCount ?? 0) > 0 }
        guard let year = days.compactMap({ Int($0.key.prefix(4)) }).max() else { return nil }
        var months: [Int: Int] = [:]
        for day in days where day.key.hasPrefix("\(year)-") {
            if let month = Int(day.key.dropFirst(5).prefix(2)) {
                months[month, default: 0] += day.roundCount ?? 0
            }
        }
        let rounds = months.values.reduce(0, +)
        let busiest = months.max { $0.value < $1.value || ($0.value == $1.value && $0.key > $1.key) }?.key
        let calendarMonths = months.keys.max()
        return CalendarSummary(
            year: year,
            rounds: rounds,
            perMonth: calendarMonths.map { Double(rounds) / Double($0) },
            busiestMonth: busiest
        )
    }
}
