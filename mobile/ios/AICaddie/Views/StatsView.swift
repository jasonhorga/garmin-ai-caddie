import Charts
import Foundation
import SwiftUI

/// 数据统计:历史宏观汇总 —— 基础(均杆/差点/抓鸟/保帕)、各杆型(三/四/五杆洞)、推杆、
/// 在恶化/改善的环节、季度走势、各球场专项、各球杆距离模型。数据来自 /api/v2/history/stats/mobile
/// (紧凑 ~180KB)。与「历史复盘」(单场逐洞)分开。距离按码显示。
public struct StatsView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?

    @State private var stats: MobileStats?
    @State private var isLoading = true
    @State private var errorText: String?

    public init(apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
    }

    public var body: some View {
        Group {
            if isLoading && stats == nil {
                AICaddieLoadingView(text: "载入统计…")
            } else {
                ScrollView {
                    StatsContent(stats: stats, isLoading: isLoading, errorText: errorText)
                }
            }
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("数据统计")
        .task { await load() }
    }

    @MainActor
    private func load() async {
        guard let apiBaseURL else { isLoading = false; errorText = "未配置后端地址"; return }
        isLoading = true
        errorText = nil
        do {
            stats = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).fetchMobileStats()
        } catch {
            errorText = "统计暂时取不到(网络或数据)"
        }
        isLoading = false
    }
}

struct StatsContent: View {
    let stats: MobileStats?
    let isLoading: Bool
    let errorText: String?

    var body: some View {
        VStack(spacing: 12) {
            if let stats {
                if let s = stats.summary { overviewCard(s) }
                if let trend = stats.trend, !trend.points.isEmpty { trendCard(trend) }
                if let bands = stats.scoring?.scoreBands, !bands.isEmpty { distributionCard(bands) }
                let byPar = (stats.scoring?.byPar ?? []).filter { (3...5).contains($0.par ?? 0) }
                if !byPar.isEmpty { byParCard(byPar) }
                if let putting = stats.scoring?.putting { puttingCard(putting) }
                if let trends = stats.diagnosis?.issueTrends, !trends.isEmpty { trendsCard(trends) }
                if let q = stats.time?.byQuarter, !q.isEmpty { periodCard(q) }
                if !stats.courses.isEmpty { coursesCard(stats.courses) }
                if !stats.clubs.isEmpty { clubsCard(stats.clubs) }
            } else if isLoading {
                ProgressView("载入统计…").padding(.top, 40)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "chart.bar.xaxis").font(.title).foregroundStyle(.secondary)
                    Text(errorText ?? "暂无统计").font(.subheadline).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity).padding(.vertical, 40).liveCard()
            }
        }
        .padding(14)
    }

    // MARK: 概览

    private func overviewCard(_ s: StatsSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("概览 · \(s.totalRounds ?? 0) 场").font(.caption).foregroundStyle(.secondary)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                kpi("均杆", s.average18.map { String(format: "%.1f", $0) } ?? "—")
                kpi("近10场", s.recent10Average.map { String(format: "%.1f", $0) } ?? "—")
                kpi("最佳", s.bestScore.map(String.init) ?? "—")
                kpi("差点", s.handicapEstimate.map { String(format: "%.1f", $0) } ?? "—")
                kpi("最差", s.worstScore.map(String.init) ?? "—")
                kpi("中位", s.median18.map { String(format: "%.0f", $0) } ?? "—")
            }
        }
        .liveCard()
    }

    // MARK: 近场走势(折线图 + 窗口内抓鸟/柏忌)

    private func trendCard(_ trend: StatsTrend) -> some View {
        let points = trend.points
        let scores = points.compactMap(\.score)
        let birdies = points.compactMap(\.birdies).reduce(0, +)
        let bogeys = points.compactMap(\.bogeys).reduce(0, +)
        let doubles = points.compactMap(\.doublesPlus).reduce(0, +)
        return VStack(alignment: .leading, spacing: 10) {
            Text("近 \(points.count) 场走势 · 18 洞").font(.caption).foregroundStyle(.secondary)
            Chart {
                ForEach(Array(points.enumerated()), id: \.offset) { index, point in
                    if let score = point.score {
                        LineMark(x: .value("场次", index), y: .value("成绩", score))
                            .foregroundStyle(LiveHoleStyle.green)
                            .interpolationMethod(.catmullRom)
                        PointMark(x: .value("场次", index), y: .value("成绩", score))
                            .foregroundStyle(LiveHoleStyle.green).symbolSize(36)
                    }
                }
            }
            .frame(height: 150)
            .chartXAxis(.hidden)
            .chartYScale(domain: scoreDomain(scores))
            .chartYAxis { AxisMarks(position: .leading) }
            HStack(spacing: 8) {
                outcomeChip("抓鸟", birdies, color: Color(red: 56 / 255, green: 152 / 255, blue: 236 / 255))
                outcomeChip("柏忌", bogeys, color: Color(red: 202 / 255, green: 138 / 255, blue: 4 / 255))
                outcomeChip("双柏+", doubles, color: Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255))
            }
        }
        .liveCard()
    }

    private func scoreDomain(_ scores: [Int]) -> ClosedRange<Int> {
        guard let lo = scores.min(), let hi = scores.max(), lo < hi else { return 70...100 }
        return (lo - 2)...(hi + 2)
    }

    // MARK: 成绩分布

    private func distributionCard(_ bands: [StatsScoreBand]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("成绩分布").font(.caption).foregroundStyle(.secondary)
            ForEach(bands) { band in
                HStack {
                    Text(band.label).font(.subheadline).frame(width: 56, alignment: .leading)
                    bandBar(count: band.count ?? 0, maxCount: bands.map { $0.count ?? 0 }.max() ?? 1)
                    Text("\(band.count ?? 0)").font(.subheadline.monospacedDigit().weight(.semibold)).frame(width: 40, alignment: .trailing)
                }
            }
        }
        .liveCard()
    }

    // MARK: 各杆型(三/四/五杆洞)

    private func byParCard(_ rows: [StatsByPar]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("各杆型表现").font(.caption).foregroundStyle(.secondary)
            HStack {
                Text("杆型").frame(width: 64, alignment: .leading)
                Text("平均±标准").frame(maxWidth: .infinity, alignment: .trailing)
                Text("保帕率").frame(width: 64, alignment: .trailing)
            }.font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            Divider()
            ForEach(rows) { row in
                HStack {
                    Text(parLabel(row)).font(.subheadline.weight(.semibold)).frame(width: 64, alignment: .leading)
                    Text(row.averageToPar.map { String(format: "%+.2f", $0) } ?? "—").font(.subheadline.monospacedDigit()).frame(maxWidth: .infinity, alignment: .trailing)
                    Text(row.parOrBetterPct.map { String(format: "%.0f%%", $0 * (($0 <= 1) ? 100 : 1)) } ?? "—").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary).frame(width: 64, alignment: .trailing)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .liveCard()
    }

    // MARK: 推杆

    private func puttingCard(_ p: StatsPutting) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("推杆").font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 8) {
                kpi("场均推杆", p.averagePutts.map { String(format: "%.1f", $0) } ?? "—")
                kpi("三推次数", p.threePutts.map(String.init) ?? "—")
            }
        }
        .liveCard()
    }

    // MARK: 在恶化/改善的环节

    private func trendsCard(_ trends: [StatsIssueTrend]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("近期趋势(对比基线)").font(.caption).foregroundStyle(.secondary)
            ForEach(trends.prefix(6)) { t in
                HStack {
                    Image(systemName: directionIcon(t.direction)).foregroundStyle(directionColor(t.direction)).font(.caption)
                    Text(zhIssue(t.issue)).font(.subheadline)
                    Spacer()
                    if let lost = t.estimatedStrokesLost, abs(lost) >= 0.1 {
                        Text(String(format: "%+.1f 杆", lost)).font(.caption.monospacedDigit()).foregroundStyle(directionColor(t.direction))
                    }
                }
                .padding(.vertical, 4)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .liveCard()
    }

    // MARK: 季度走势

    private func periodCard(_ periods: [StatsPeriod]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("季度走势").font(.caption).foregroundStyle(.secondary)
            ForEach(periods.prefix(8)) { p in
                HStack {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(p.key).font(.subheadline.weight(.semibold))
                        Text("\(p.roundCount ?? 0) 场").font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let birdie = p.outcomes?.birdie { Text("鸟 \(birdie)").font(.caption2).foregroundStyle(.secondary) }
                    if let dbl = p.outcomes?.doubleOrWorse { Text("双柏+ \(dbl)").font(.caption2).foregroundStyle(.secondary) }
                    Text(p.average18.map { String(format: "%.1f", $0) } ?? "—").font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 56, alignment: .trailing)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .liveCard()
    }

    // MARK: 各球场专项

    private func coursesCard(_ courses: [StatsCourse]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("各球场").font(.caption).foregroundStyle(.secondary)
            Text("点进去看在这球场打过的各九洞组合 →").font(.caption2).foregroundStyle(LiveHoleStyle.green)
            ForEach(courses.prefix(12)) { c in
                NavigationLink {
                    CourseStatsDetailView(course: c)
                } label: {
                    courseRow(c)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.primary)
            }
        }
        .liveCard()
    }

    private func courseRow(_ c: StatsCourse) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text(c.courseName ?? c.courseKey).font(.subheadline.weight(.semibold)).lineLimit(1)
                Text("\(c.roundCount ?? 0) 次 · 最佳 \(c.bestScore.map(String.init) ?? "—")").font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            Text(c.average18.map { String(format: "%.1f", $0) } ?? "—").font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 56, alignment: .trailing)
            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .overlay(alignment: .bottom) { Divider() }
    }

    // MARK: 各球杆(距离按码)

    private func clubsCard(_ clubs: [StatsClub]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("各球杆 · 距离按码").font(.caption).foregroundStyle(.secondary)
            HStack {
                Text("球杆").frame(width: 72, alignment: .leading)
                Text("常用").frame(maxWidth: .infinity, alignment: .trailing)
                Text("区间(码)").frame(width: 96, alignment: .trailing)
            }.font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            Divider()
            ForEach(clubs) { club in
                HStack {
                    Text(zhClubName(club.club)).font(.subheadline).frame(width: 72, alignment: .leading)
                    Text(club.median.map { "\(CoursePrepRoute.yards(fromMetres: $0))" } ?? "—").font(.subheadline.monospacedDigit().weight(.semibold)).frame(maxWidth: .infinity, alignment: .trailing)
                    Text(rangeText(club)).font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 96, alignment: .trailing)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .liveCard()
    }

    // MARK: helpers

    private func kpi(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title3.weight(.heavy))
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 10)
        .background(LiveHoleStyle.tint).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func outcomeChip(_ title: String, _ count: Int, color: Color) -> some View {
        VStack(spacing: 2) {
            Text("\(count)").font(.title3.monospacedDigit().weight(.heavy)).foregroundStyle(color)
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 8)
        .background(color.opacity(0.12)).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func bandBar(count: Int, maxCount: Int) -> some View {
        GeometryReader { geo in
            let frac = maxCount > 0 ? CGFloat(count) / CGFloat(maxCount) : 0
            RoundedRectangle(cornerRadius: 4).fill(LiveHoleStyle.green.opacity(0.5))
                .frame(width: max(4, geo.size.width * frac), height: 12)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(height: 12)
    }

    private func rangeText(_ club: StatsClub) -> String {
        guard let p10 = club.p10, let p90 = club.p90 else { return "—" }
        return "\(CoursePrepRoute.yards(fromMetres: p10))–\(CoursePrepRoute.yards(fromMetres: p90))"
    }

    private func parLabel(_ row: StatsByPar) -> String {
        if let par = row.par { return "\(par) 杆洞" }
        return row.label ?? row.key ?? "—"
    }

    private func directionIcon(_ direction: String?) -> String {
        switch (direction ?? "").lowercased() {
        case "worsening", "up", "worse": return "arrow.up.right"
        case "improving", "down", "better": return "arrow.down.right"
        default: return "minus"
        }
    }

    private func directionColor(_ direction: String?) -> Color {
        switch (direction ?? "").lowercased() {
        case "worsening", "up", "worse": return Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255)
        case "improving", "down", "better": return LiveHoleStyle.green
        default: return .secondary
        }
    }

    private func zhIssue(_ issue: String) -> String {
        switch issue.lowercased() {
        case "double_or_worse": return "双柏忌及以上"
        case "tee_miss", "tee_direction": return "开球偏差"
        case "hazard_result", "hazard": return "下水/沙坑"
        case "missing_shots": return "缺击球数据"
        case "three_putt", "three_putts": return "三推"
        case "approach_miss": return "攻果岭偏差"
        case "short_game": return "短杆"
        default: return issue.replacingOccurrences(of: "_", with: " ")
        }
    }
}

/// Drill-in for one course (D1): overall play count + per nine-combo breakdown (A / C/A / B/C …),
/// so the 各球场 list aggregates by BASE course and the detail shows how many times each nine.
struct CourseStatsDetailView: View {
    let course: StatsCourse

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("总览").font(.caption).foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        kpi("打过", "\(course.roundCount ?? 0) 次")
                        kpi("均杆", course.average18.map { String(format: "%.1f", $0) } ?? "—")
                        kpi("最佳", course.bestScore.map(String.init) ?? "—")
                    }
                }
                .liveCard()
                if let breakdown = course.nineBreakdown, !breakdown.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("各九洞组合").font(.caption).foregroundStyle(.secondary)
                        ForEach(breakdown) { n in
                            HStack {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(n.label).font(.subheadline.weight(.semibold)).lineLimit(1)
                                    Text("\(n.roundCount ?? 0) 次").font(.caption2).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if let best = n.bestScore { Text("最佳 \(best)").font(.caption2).foregroundStyle(.secondary) }
                                Text(n.average.map { String(format: "%.1f", $0) } ?? "—")
                                    .font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 56, alignment: .trailing)
                            }
                            .padding(.vertical, 6)
                            .overlay(alignment: .bottom) { Divider() }
                        }
                    }
                    .liveCard()
                } else {
                    Text("暂无各九洞明细").font(.subheadline).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity).padding(.vertical, 30).liveCard()
                }
            }
            .padding(14)
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle(course.courseName ?? "球场")
    }

    private func kpi(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title3.weight(.heavy))
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 10)
        .background(LiveHoleStyle.tint).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
