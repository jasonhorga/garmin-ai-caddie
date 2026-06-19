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
                if let sc = stats.scoring { outcomesCard(sc) }
                if let byPar = stats.scoring?.byPar, !byPar.isEmpty { byParCard(byPar) }
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

    // MARK: 得分构成

    private func outcomesCard(_ sc: StatsScoring) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("得分构成").font(.caption).foregroundStyle(.secondary)
            if let o = sc.outcomes {
                HStack(spacing: 8) {
                    outcomeChip("抓鸟+", (o.birdie ?? 0) + (o.eagleOrBetter ?? 0), color: Color(red: 56 / 255, green: 152 / 255, blue: 236 / 255))
                    outcomeChip("保帕", o.par ?? 0, color: LiveHoleStyle.green)
                    outcomeChip("柏忌", o.bogey ?? 0, color: Color(red: 202 / 255, green: 138 / 255, blue: 4 / 255))
                    outcomeChip("双柏+", o.doubleOrWorse ?? 0, color: Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255))
                }
            }
            if !sc.scoreBands.isEmpty {
                Divider()
                Text("成绩分布").font(.caption2).foregroundStyle(.secondary)
                ForEach(sc.scoreBands) { band in
                    HStack {
                        Text(band.label).font(.subheadline).frame(width: 56, alignment: .leading)
                        bandBar(count: band.count ?? 0, maxCount: sc.scoreBands.map { $0.count ?? 0 }.max() ?? 1)
                        Text("\(band.count ?? 0)").font(.subheadline.monospacedDigit().weight(.semibold)).frame(width: 40, alignment: .trailing)
                    }
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
            ForEach(courses.prefix(10)) { c in
                HStack {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(c.courseName ?? c.courseKey).font(.subheadline.weight(.semibold)).lineLimit(1)
                        Text("\(c.roundCount ?? 0) 场 · 最佳 \(c.bestScore.map(String.init) ?? "—")").font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(c.average18.map { String(format: "%.1f", $0) } ?? "—").font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 56, alignment: .trailing)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .liveCard()
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
