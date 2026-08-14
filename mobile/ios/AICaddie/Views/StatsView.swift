import Charts
import Foundation
import SwiftUI

public enum StatsViewMode { case all, analysis }

/// Aggregate performance detail inside the unified 成绩 destination. `.analysis` omits the career
/// and archive navigation already owned by ResultsView and keeps the evidence-backed metrics.
public struct StatsView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let mode: StatsViewMode

    @State private var stats: MobileStats?
    @State private var isLoading = true
    @State private var errorText: String?
    @State private var window = "last10"

    public init(apiBaseURL: URL? = nil, adminToken: String? = nil, mode: StatsViewMode = .all) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.mode = mode
    }

    public var body: some View {
        Group {
            if isLoading && stats == nil {
                AICaddieLoadingView(text: "载入统计…")
            } else {
                ScrollView {
                    VStack(spacing: 0) {
                        if mode == .analysis {
                            VStack(alignment: .leading, spacing: 7) {
                                Text("统计范围").font(.caption).foregroundStyle(.secondary)
                                Picker("统计范围", selection: $window) {
                                    Text("近 10 场").tag("last10")
                                    Text("近 20 场").tag("last20")
                                    Text("近 12 月").tag("12m")
                                    Text("全部").tag("all")
                                }.pickerStyle(.segmented)
                            }
                            .padding(.horizontal, 14)
                            .padding(.top, 12)
                            .padding(.bottom, 10)
                            Divider()
                        }
                        StatsContent(stats: stats, isLoading: isLoading, errorText: errorText,
                                     apiBaseURL: apiBaseURL, adminToken: adminToken, mode: mode)
                    }
                }
            }
        }
        .background(mode == .analysis ? Color.white : HubStyle.grouped)
        .navigationTitle(mode == .analysis ? "表现分析" : "成绩统计")
        .task(id: window) { await load() }
    }

    @MainActor
    private func load() async {
        guard let apiBaseURL else { isLoading = false; errorText = "未配置后端地址"; return }
        isLoading = true
        errorText = nil
        do {
            stats = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
                .fetchMobileStats(window: mode == .analysis ? window : "all")
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
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil
    var mode: StatsViewMode = .all
    @State private var selectedPhase: PerformancePhase = .drive

    private enum PerformancePhase: String, CaseIterable, Identifiable {
        case drive, approach, shortGame, putting
        var id: String { rawValue }
        var title: String {
            switch self {
            case .drive: return "开球"
            case .approach: return "攻果岭"
            case .shortGame: return "短杆"
            case .putting: return "推杆"
            }
        }
    }

    var body: some View {
        VStack(spacing: 12) {
            if let stats {
                if mode == .all, let s = stats.summary { overviewCard(s) }
                if mode == .all, let trend = stats.trend, !trend.points.isEmpty { trendCard(trend) }
                if mode == .analysis { performanceOverview(stats) }
                if mode == .all, let spread = stats.scoring?.outcomeDistribution, !spread.isEmpty { spreadCard(spread) }
                if mode == .all, let bands = stats.scoring?.scoreBands, !bands.isEmpty {
                    distributionCard(bands, apiBaseURL: apiBaseURL, adminToken: adminToken)
                }
                let byPar = (stats.scoring?.byPar ?? []).filter { (3...5).contains($0.par ?? 0) }
                if mode == .all, !byPar.isEmpty { byParCard(byPar) }
                if mode == .all, let phases = stats.scoring?.phaseStats, !phases.isEmpty { phaseCard(phases) }
                if mode == .all, let putting = stats.scoring?.putting { puttingCard(putting) }
                // The issue engine is not a benchmarked strokes-gained model. Keep estimated
                // strokes-lost claims out of the consumer analysis surface.
                if mode == .all, let q = stats.time?.byQuarter, !q.isEmpty { periodCard(q) }
                if mode == .all, !stats.courses.isEmpty { coursesCard(stats.courses) }
                if mode == .all, !stats.clubs.isEmpty { clubsCard(stats.clubs) }
            } else if isLoading {
                ProgressView("载入统计…").padding(.top, 40)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "chart.bar.xaxis").font(.title).foregroundStyle(.secondary)
                    Text(errorText ?? "暂无统计").font(.subheadline).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity).padding(.vertical, 40).hubCard()
            }
        }
        .padding(mode == .analysis ? 0 : 14)
    }

    // MARK: Garmin-style shot overview

    /// Garmin Golf makes the shot phase the navigation, then lets the graphic answer one question
    /// at a time.  Keep scoring distribution available below, but do not lead analysis with a long
    /// stack of unrelated report cards.
    private func performanceOverview(_ stats: MobileStats) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Picker("击球阶段", selection: $selectedPhase) {
                ForEach(PerformancePhase.allCases) { phase in
                    Text(phase.title).tag(phase)
                }
            }
            .pickerStyle(.segmented)
            performancePhaseContent(stats, phase: selectedPhase)
        }
        .padding(.horizontal, 14)
        .padding(.top, 12)
        .padding(.bottom, 18)
        .background(Color.white)
    }

    @ViewBuilder
    private func performancePhaseContent(_ stats: MobileStats, phase: PerformancePhase) -> some View {
        switch phase {
        case .drive:
            drivePhase(stats)
        case .approach:
            approachPhase(stats)
        case .shortGame:
            shortGamePhase(stats)
        case .putting:
            puttingPhase(stats)
        }
    }

    private func drivePhase(_ stats: MobileStats) -> some View {
        let tee = phase(named: "Tee", in: stats)
        let left = stats.scoring?.teeDirection?.left ?? tee?.fairwayMissLeft
        let hit = stats.scoring?.teeDirection?.hit ?? tee?.fairwaysHit
        let right = stats.scoring?.teeDirection?.right ?? tee?.fairwayMissRight
        let recorded = stats.scoring?.teeDirection?.recorded ?? tee?.fairwaysRecorded
        return VStack(alignment: .leading, spacing: 12) {
            phaseHeading("开球方向", detail: coverageText(ready: recorded, total: tee?.coverage?.total))
            phaseMetricRow([
                ("↶ 偏左", percentText(left, recorded)),
                ("↑ 球道", percentText(hit, recorded)),
                ("↷ 偏右", percentText(right, recorded)),
            ])
            DirectionRangeGraphic(left: left, center: hit, right: right)
            phaseEvidenceFooter(ready: recorded, total: tee?.coverage?.total,
                                note: "按记分卡方向分区汇总，不生成模拟落点")
        }
    }

    private func approachPhase(_ stats: MobileStats) -> some View {
        let approach = phase(named: "Approach", in: stats)
        let miss = stats.scoring?.approachMiss
        let hit = miss?.gir ?? approach?.gir
        let recorded = miss?.recorded ?? approach?.girRecorded
        return VStack(alignment: .leading, spacing: 12) {
            phaseHeading("攻果岭落点", detail: coverageText(ready: recorded, total: approach?.coverage?.total))
            phaseMetricRow([
                ("GIR", percentText(hit, recorded)),
                ("主要失误", approachMissLabel(miss?.dominantMiss)),
            ])
            ApproachTargetGraphic(
                short: miss?.short, long: miss?.long, left: miss?.left, right: miss?.right,
                green: hit
            )
            phaseEvidenceFooter(ready: recorded, total: approach?.coverage?.total,
                                note: "按果岭命中与失误方向分区汇总")
        }
    }

    private func shortGamePhase(_ stats: MobileStats) -> some View {
        let shortGame = phase(named: "Short Game", in: stats)
        let shots = shortGame?.roughOrBunkerShots
        return VStack(alignment: .leading, spacing: 12) {
            phaseHeading("果岭周边", detail: sampleText(shots).map { "\($0) 次已记录" })
            phaseMetricRow([
                ("长草 / 沙坑起杆", shots.map(String.init) ?? "—"),
                ("全部逐杆样本", shortGame?.coverage?.total.map(String.init) ?? "—"),
            ])
            ShortGameGraphic(shotCount: shots)
            phaseEvidenceFooter(ready: shots, total: nil, note: "只统计有球位记录的长草与沙坑击球")
        }
    }

    private func puttingPhase(_ stats: MobileStats) -> some View {
        let putting = stats.scoring?.putting
        let phase = phase(named: "Putting", in: stats)
        let rounds = putting?.roundsWithPutts
        let threePuttsPerRound: String = {
            guard let total = putting?.threePutts, let rounds, rounds > 0 else { return "—" }
            return String(format: "%.1f", Double(total) / Double(rounds))
        }()
        return VStack(alignment: .leading, spacing: 12) {
            phaseHeading("推杆", detail: coverageText(ready: phase?.coverage?.ready,
                                                    total: phase?.coverage?.total))
            phaseMetricRow([
                ("场均推杆", putting?.averagePuttsPerRound.map { String(format: "%.1f", $0) } ?? "—"),
                ("场均三推", threePuttsPerRound),
            ])
            PuttingGreenGraphic(average: putting?.averagePutts ?? phase?.averagePutts)
            phaseEvidenceFooter(ready: phase?.coverage?.ready, total: phase?.coverage?.total,
                                note: "推杆位置不完整时只显示记分卡推杆统计")
        }
    }

    private func phase(named name: String, in stats: MobileStats) -> StatsPhase? {
        stats.scoring?.phaseStats.first { $0.phase.caseInsensitiveCompare(name) == .orderedSame }
    }

    private func phaseHeading(_ title: String, detail: String?) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.headline)
            Spacer()
            if let detail { Text(detail).font(.caption).foregroundStyle(.secondary) }
        }
    }

    private func phaseMetricRow(_ values: [(String, String)]) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ForEach(Array(values.enumerated()), id: \.offset) { _, item in
                VStack(spacing: 3) {
                    Text(item.1)
                        .font(.title2.monospacedDigit().weight(.semibold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Text(item.0)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity)
            }
        }
    }

    @ViewBuilder
    private func phaseEvidenceFooter(ready: Int?, total: Int?, note: String) -> some View {
        if let ready, let total, total > 0 {
            Text("\(note) · \(ready)/\(total)")
                .font(.caption2).foregroundStyle(.secondary)
        } else if let ready {
            Text("\(note) · \(ready) 条")
                .font(.caption2).foregroundStyle(.secondary)
        } else {
            Text("\(note) · 这段时间没有足够数据")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func coverageText(ready: Int?, total: Int?) -> String? {
        guard let ready else { return nil }
        guard let total, total > 0 else { return "\(ready) 条记录" }
        return "覆盖 \(ready)/\(total)"
    }

    private func sampleText(_ count: Int?) -> String? { count.map(String.init) }

    private func percentText(_ value: Int?, _ total: Int?) -> String {
        guard let value, let total, total > 0 else { return "—" }
        return String(format: "%.0f%%", Double(value) / Double(total) * 100)
    }

    private func approachMissLabel(_ raw: String?) -> String {
        switch raw?.lowercased() {
        case "short": return "偏短"
        case "long": return "偏长"
        case "left": return "偏左"
        case "right": return "偏右"
        default: return "—"
        }
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
        .hubCard()
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
        .hubCard()
    }

    private func scoreDomain(_ scores: [Int]) -> ClosedRange<Int> {
        guard let lo = scores.min(), let hi = scores.max(), lo < hi else { return 70...100 }
        return (lo - 2)...(hi + 2)
    }

    // MARK: 成绩构成(GolfLive 7 维,按洞)

    private func spreadCard(_ buckets: [StatsOutcomeBucket]) -> some View {
        let zh: [String: String] = [
            "eagleOrBetter": "老鹰", "birdie": "小鸟", "par": "标准杆",
            "bogey": "柏忌", "double": "双柏忌", "triple": "+3", "quadPlus": "+4",
        ]
        let maxPct = buckets.compactMap(\.pct).max() ?? 1
        return VStack(alignment: .leading, spacing: 8) {
            Text("成绩构成 · 按洞").font(.caption).foregroundStyle(.secondary)
            ForEach(buckets) { b in
                HStack {
                    Text(zh[b.key] ?? b.label ?? b.key).font(.subheadline).frame(width: 56, alignment: .leading)
                    bandBar(count: Int(((b.pct ?? 0) * 10).rounded()), maxCount: Int((maxPct * 10).rounded()))
                    Text(b.pct.map { String(format: "%.1f%%", $0) } ?? "—")
                        .font(.subheadline.monospacedDigit().weight(.semibold)).frame(width: 56, alignment: .trailing)
                }
            }
        }
        .hubCard()
    }

    // MARK: 成绩分布

    private func distributionCard(
        _ bands: [StatsScoreBand],
        apiBaseURL: URL?,
        adminToken: String?
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("成绩分布 · 点击查看球局").font(.caption).foregroundStyle(.secondary)
            ForEach(bands) { band in
                NavigationLink {
                    ResultsArchiveView(
                        apiBaseURL: apiBaseURL,
                        adminToken: adminToken,
                        initialScoreBand: band.label
                    )
                } label: {
                    HStack {
                        Text(scoreBandLabel(band.label))
                            .font(.subheadline)
                            .frame(width: 86, alignment: .leading)
                        bandBar(
                            count: band.count ?? 0,
                            maxCount: bands.map { $0.count ?? 0 }.max() ?? 1
                        )
                        Text("\(band.count ?? 0) 场 ›")
                            .font(.subheadline.monospacedDigit().weight(.semibold))
                            .frame(width: 64, alignment: .trailing)
                    }
                }
                .buttonStyle(.plain)
                .foregroundStyle(.primary)
            }
        }
        .hubCard()
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
                    Text(row.parOrBetterPct.map { String(format: "%.0f%%", $0) } ?? "—").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary).frame(width: 64, alignment: .trailing)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .hubCard()
    }

    // MARK: 表现统计(开球 / 攻果岭)

    private func phaseCard(_ phases: [StatsPhase]) -> some View {
        let byPhase = Dictionary(phases.map { ($0.phase, $0) }, uniquingKeysWith: { a, _ in a })
        let tee = byPhase["Tee"]
        let approach = byPhase["Approach"]
        let fairwayText: String = {
            guard let rec = tee?.fairwaysRecorded, rec > 0, let hit = tee?.fairwaysHit else { return "—" }
            return String(format: "%.0f%%", Double(hit) / Double(rec) * 100)
        }()
        return VStack(alignment: .leading, spacing: 10) {
            Text("表现统计").font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 8) {
                kpi("球道命中", fairwayText)
                kpi("攻果岭 GIR", approach?.girPct.map { String(format: "%.0f%%", $0) } ?? "—")
            }
            if let l = tee?.fairwayMissLeft, let r = tee?.fairwayMissRight, (l + r) > 0 {
                Text("开球偏向:偏左 \(l) · 偏右 \(r)").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .hubCard()
    }

    // MARK: 推杆

    private func puttingCard(_ p: StatsPutting) -> some View {
        // 场均推杆 = per-ROUND total (~33), not the per-hole average (~1.9). 场均三推 = three-putts/round.
        let perRoundThreePutts: String = {
            guard let tp = p.threePutts, let rounds = p.roundsWithPutts, rounds > 0 else { return "—" }
            return String(format: "%.1f", Double(tp) / Double(rounds))
        }()
        return VStack(alignment: .leading, spacing: 10) {
            Text("推杆").font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 8) {
                kpi("场均推杆", p.averagePuttsPerRound.map { String(format: "%.1f", $0) } ?? "—")
                kpi("场均三推", perRoundThreePutts)
            }
            if let total = p.threePutts {
                Text("累计三推 \(total) 次").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .hubCard()
    }

    // MARK: 在恶化/改善的环节

    private func trendsCard(_ trends: [StatsIssueTrend]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("近期趋势(对比基线)").font(.caption).foregroundStyle(.secondary)
            ForEach(trends.prefix(6)) { t in
                HStack {
                    Image(systemName: directionIcon(t.direction)).foregroundStyle(directionColor(t.direction)).font(.caption)
                    Text(zhIssueLabel(t.issue)).font(.subheadline)
                    Spacer()
                    if let lost = t.estimatedStrokesLost, abs(lost) >= 0.1 {
                        Text(String(format: "%+.1f 杆", lost)).font(.caption.monospacedDigit()).foregroundStyle(directionColor(t.direction))
                    }
                }
                .padding(.vertical, 4)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .hubCard()
    }

    // MARK: 季度走势

    private func periodCard(_ periods: [StatsPeriod]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("季度走势 · 每场平均").font(.caption).foregroundStyle(.secondary)
            ForEach(periods.prefix(8)) { p in
                let rc = p.roundCount ?? 0
                HStack {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(p.key).font(.subheadline.weight(.semibold))
                        Text("\(rc) 场").font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let birdie = p.outcomes?.birdie { Text("鸟 \(perRound(birdie, rc))").font(.caption2).foregroundStyle(.secondary) }
                    if let dbl = p.outcomes?.doubleOrWorse { Text("双柏+ \(perRound(dbl, rc))").font(.caption2).foregroundStyle(.secondary) }
                    Text(p.average18.map { String(format: "%.1f", $0) } ?? "—").font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 56, alignment: .trailing)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .hubCard()
    }

    /// Per-round average of a quarter total (用户:季度想看"平均每场"而不是累计次数).
    private func perRound(_ total: Int, _ rounds: Int) -> String {
        guard rounds > 0 else { return "—" }
        return String(format: "%.1f", Double(total) / Double(rounds))
    }

    // MARK: 各球场专项

    private func coursesCard(_ courses: [StatsCourse]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("各球场 · \(courses.count) 个").font(.caption).foregroundStyle(.secondary)
            Text("点进去看各九洞组合,并列出每一场(点单场看复盘)→").font(.caption2).foregroundStyle(LiveHoleStyle.green)
            ForEach(courses) { c in
                NavigationLink {
                    CourseStatsDetailView(course: c, apiBaseURL: apiBaseURL, adminToken: adminToken)
                } label: {
                    courseRow(c)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.primary)
            }
        }
        .hubCard()
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
        .hubCard()
    }

    // MARK: helpers

    private func kpi(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title3.weight(.heavy)).monospacedDigit()
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 10)
        .background(HubStyle.iconTint).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
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

    private func scoreBandLabel(_ value: String) -> String {
        switch value {
        case "70s": return "70–79"
        case "80s": return "80–89"
        case "90s": return "90–99"
        case "100+": return "100 杆以上"
        default: return value
        }
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

}

/// Drill-in for one course (D1): overall play count + per nine-combo breakdown (A / C/A / B/C …),
/// so the 各球场 list aggregates by BASE course and the detail shows how many times each nine.
struct CourseStatsDetailView: View {
    let course: StatsCourse
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil

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
                .hubCard()
                roundsSection
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
                    .hubCard()
                } else {
                    Text("暂无各九洞明细").font(.subheadline).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity).padding(.vertical, 30).hubCard()
                }
            }
            .padding(14)
        }
        .background(HubStyle.grouped)
        .navigationTitle(course.courseName ?? "球场")
    }

    // MARK: 所有比赛(用户:直接列出每一场 时间·成绩,点单场看复盘)

    @ViewBuilder private var roundsSection: some View {
        let rounds = course.rounds ?? []
        if rounds.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("所有比赛 · \(rounds.count) 场").font(.caption).foregroundStyle(.secondary)
                ForEach(rounds) { r in
                    if let ref = r.roundId, !ref.isEmpty {
                        NavigationLink {
                            RoundReviewView(roundRef: ref, fallbackCourseName: course.courseName,
                                            apiBaseURL: apiBaseURL, adminToken: adminToken)
                        } label: { roundRow(r) }
                        .buttonStyle(.plain).foregroundStyle(.primary)
                    } else {
                        roundRow(r)
                    }
                }
            }
            .hubCard()
        }
    }

    private func roundRow(_ r: StatsCourseRound) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text(prettyDate(r.date)).font(.subheadline.weight(.semibold))
                let nineText = (r.nine?.isEmpty == false) ? "\(r.nine!) 九洞" : nil
                let parts = [nineText, r.holesCompleted.map { "\($0) 洞" }].compactMap { $0 }
                if !parts.isEmpty {
                    Text(parts.joined(separator: " · ")).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer()
            if let toPar = r.toPar {
                Text(toPar == 0 ? "E" : String(format: "%+d", toPar))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(toPar > 0 ? Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255) : LiveHoleStyle.green)
            }
            Text(r.score.map(String.init) ?? "—").font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 44, alignment: .trailing)
            if r.roundId?.isEmpty == false { Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary) }
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .overlay(alignment: .bottom) { Divider() }
    }

    /// Trim an ISO/`YYYY-MM-DD` date to the day part for the round list.
    private func prettyDate(_ raw: String) -> String {
        if raw.isEmpty { return "—" }
        return String(raw.prefix(10))
    }

    private func kpi(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title3.weight(.heavy)).monospacedDigit()
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 10)
        .background(HubStyle.iconTint).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
