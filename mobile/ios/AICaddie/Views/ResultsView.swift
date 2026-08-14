import Charts
import Foundation
import SwiftUI

/// The single history/performance destination. It answers the career/recent-state
/// question first, then offers explicit drill-downs; it is not a four-tab container.
public struct ResultsView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?

    @State private var stats: MobileStats?
    @State private var archive: HistoryRoundsArchive?
    @State private var isLoading = true
    @State private var errorText: String?

    public init(apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
    }

    public var body: some View {
        Group {
            if isLoading && stats == nil && archive == nil {
                AICaddieLoadingView(text: "载入成绩…")
            } else {
                ScrollView {
                    ResultsLandingContent(
                        stats: stats,
                        archive: archive,
                        errorText: errorText,
                        apiBaseURL: apiBaseURL,
                        adminToken: adminToken
                    )
                }
            }
        }
        .background(HubStyle.grouped)
        .navigationTitle("成绩")
        .task { await load() }
        .refreshable { await load() }
    }

    @MainActor
    private func load() async {
        guard let apiBaseURL else {
            isLoading = false
            errorText = "未配置后端地址"
            return
        }
        isLoading = true
        errorText = nil
        let client = SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
        async let statsRequest = client.fetchMobileStats()
        async let archiveRequest = client.fetchHistoryRounds()
        var failedSections: [String] = []
        do { stats = try await statsRequest } catch { failedSections.append("生涯与趋势") }
        do { archive = try await archiveRequest } catch { failedSections.append("球局档案") }
        guard !Task.isCancelled else { return }
        if !failedSections.isEmpty {
            errorText = "\(failedSections.joined(separator: "、"))暂时取不到"
        }
        isLoading = false
    }
}

struct ResultsLandingContent: View {
    let stats: MobileStats?
    let archive: HistoryRoundsArchive?
    let errorText: String?
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil

    var body: some View {
        VStack(spacing: 12) {
            recentRoundsCard
            if let summary = stats?.summary { recentCard(summary, points: stats?.trend?.points ?? []) }
            quickDestinations
            if let summary = stats?.summary { careerCard(summary) }
            libraryDestinations
            if let errorText, stats != nil || archive != nil {
                Label(errorText, systemImage: "exclamationmark.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .hubCard()
            }
            if stats == nil && archive == nil {
                Text(errorText ?? "暂无成绩")
                    .font(.subheadline).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity).padding(.vertical, 40).hubCard()
            }
        }
        .padding(14)
    }

    private func careerCard(_ summary: StatsSummary) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("我的高尔夫生涯").font(.caption).foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline) {
                Text("\(summary.totalRounds ?? archive?.total ?? 0)")
                    .font(.system(size: 38, weight: .heavy)).monospacedDigit()
                Text("场球 · \(summary.courseCount ?? 0) 个球场")
                    .font(.subheadline).foregroundStyle(.secondary)
                Spacer()
                Text("\(summary.eighteenHoleRounds ?? 0) 场完整 18 洞")
                    .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            }
            HStack(spacing: 8) {
                resultKPI("18 洞均杆", summary.average18.map(oneDecimal) ?? "—")
                resultKPI("历史最佳", summary.bestScore.map(String.init) ?? "—")
                resultKPI("差点估算", summary.handicapEstimate.map(oneDecimal) ?? "—")
            }
        }
        .hubCard()
    }

    private func recentCard(_ summary: StatsSummary, points: [StatsTrendPoint]) -> some View {
        NavigationLink {
            ResultsTrendView(apiBaseURL: apiBaseURL, adminToken: adminToken)
        } label: {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("最近状态").font(.headline)
                        Text("近 10 场 \(summary.recent10Average.map(oneDecimal) ?? "—") · 近 20 场 \(summary.recent20Average.map(oneDecimal) ?? "—")")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text("看趋势 ›").font(.caption.weight(.bold)).foregroundStyle(LiveHoleStyle.green)
                }
                if !points.isEmpty {
                    Chart(Array(points.suffix(20))) { point in
                        if let score = point.score {
                            LineMark(x: .value("日期", point.date), y: .value("成绩", score))
                                .foregroundStyle(LiveHoleStyle.green)
                                .interpolationMethod(.catmullRom)
                        }
                    }
                    .frame(height: 82)
                    .chartYScale(domain: resultsScoreDomain(points.compactMap { $0.score.map(Double.init) }))
                    .chartXAxis(.hidden).chartYAxis(.hidden)
                }
            }
        }
        .buttonStyle(.plain).foregroundStyle(.primary).hubCard()
    }

    @ViewBuilder private var recentRoundsCard: some View {
        let rounds = archive?.groups.flatMap(\.rounds) ?? []
        if !rounds.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("球局活动").font(.title3.weight(.bold))
                    Spacer()
                    NavigationLink("全部 \(archive?.total ?? rounds.count) 场 ›") {
                        ResultsArchiveView(apiBaseURL: apiBaseURL, adminToken: adminToken, initialArchive: archive)
                    }
                    .font(.caption.weight(.bold)).foregroundStyle(LiveHoleStyle.green)
                }
                ForEach(rounds.prefix(3)) { round in
                    NavigationLink {
                        RoundReviewView(roundRef: round.id, fallbackCourseName: round.courseName,
                                        apiBaseURL: apiBaseURL, adminToken: adminToken)
                    } label: { ResultsRoundRow(round: round, showsScoreStrip: true) }
                    .buttonStyle(.plain)
                    .foregroundStyle(.primary)
                    .hubCard(padding: 14)
                }
            }
        }
    }

    private var quickDestinations: some View {
        HStack(spacing: 10) {
            resultFeatureDestination("表现分析", "四阶段空间分析", "scope") {
                StatsView(apiBaseURL: apiBaseURL, adminToken: adminToken, mode: .analysis)
            }
            resultFeatureDestination("全部球局", "搜索 · 年份 · 球场", "clock.arrow.circlepath") {
                ResultsArchiveView(apiBaseURL: apiBaseURL, adminToken: adminToken, initialArchive: archive)
            }
        }
    }

    private var libraryDestinations: some View {
        VStack(spacing: 0) {
            resultDestination("时间趋势", "近 10 / 20 场 · 年 · 季 · 月 · 频率", "chart.xyaxis.line") {
                ResultsTrendView(apiBaseURL: apiBaseURL, adminToken: adminToken)
            }
            Divider()
            resultDestination("球场", "\(stats?.courses.count ?? 0) 个球场 · 九洞组合", "map") {
                ResultsCoursesView(courses: stats?.courses ?? [], apiBaseURL: apiBaseURL, adminToken: adminToken)
            }
            Divider()
            resultDestination("球杆", "中位距离 · p10–p90 · 样本数", "figure.golf") {
                ResultsClubsView(clubs: stats?.clubs ?? [])
            }
        }
        .hubCard(padding: 0)
    }

    private func resultDestination<Destination: View>(
        _ title: String, _ detail: String, _ icon: String, @ViewBuilder destination: () -> Destination
    ) -> some View {
        NavigationLink(destination: destination()) {
            HStack(spacing: 12) {
                HubIconSquare(system: icon)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.subheadline.weight(.bold))
                    Text(detail).font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14).padding(.vertical, 11)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain).foregroundStyle(.primary)
    }

    private func resultFeatureDestination<Destination: View>(
        _ title: String, _ detail: String, _ icon: String, @ViewBuilder destination: () -> Destination
    ) -> some View {
        NavigationLink(destination: destination()) {
            VStack(alignment: .leading, spacing: 9) {
                HStack {
                    Image(systemName: icon)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(LiveHoleStyle.green)
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.tertiary)
                }
                Text(title).font(.subheadline.weight(.bold))
                Text(detail).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
            // The two-column card contains deliberate whitespace between its title and chevron.
            // Without an explicit shape SwiftUI exposes one accessibility "Button" whose visual
            // bounds include that gap, but a tap in the gap can miss the NavigationLink entirely.
            // Make the whole visible card content plane the link target.
            .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(.primary)
        .hubCard(padding: 13)
    }

    private func resultKPI(_ label: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.title3.weight(.heavy)).monospacedDigit()
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 9)
        .background(HubStyle.iconTint).clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

public struct ResultsArchiveView: View {
    let apiBaseURL: URL?
    let adminToken: String?
    let initialArchive: HistoryRoundsArchive?
    @State private var archive: HistoryRoundsArchive?
    @State private var search = ""
    @State private var year = ""
    @State private var course = ""
    @State private var hasShotsOnly = false
    @State private var period: String?
    @State private var scoreBand: String?
    @State private var isLoading = false

    public init(
        apiBaseURL: URL?, adminToken: String?, initialArchive: HistoryRoundsArchive? = nil,
        initialPeriod: String? = nil, initialScoreBand: String? = nil
    ) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.initialArchive = initialArchive
        _archive = State(initialValue: initialArchive)
        _period = State(initialValue: initialPeriod)
        _scoreBand = State(initialValue: initialScoreBand)
    }

    public var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                filterCard
                if isLoading && archive == nil { ProgressView("载入球局…").padding(.top, 40) }
                ForEach(filteredGroups) { group in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(monthLabel(group.key)).font(.footnote.weight(.bold))
                            Spacer()
                            Text("\(group.rounds.count) 场 · 均杆 \(group.average18.map(oneDecimal) ?? "—")")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        VStack(spacing: 0) {
                            ForEach(group.rounds) { round in
                                NavigationLink {
                                    RoundReviewView(roundRef: round.id, fallbackCourseName: round.courseName,
                                                    apiBaseURL: apiBaseURL, adminToken: adminToken)
                                } label: { ResultsRoundRow(round: round, showsScoreStrip: true) }
                                .buttonStyle(.plain).foregroundStyle(.primary)
                                if round.id != group.rounds.last?.id { Divider() }
                            }
                        }.hubCard(padding: 12)
                    }
                }
                if !isLoading && filteredGroups.isEmpty {
                    Text("没有符合条件的球局").font(.subheadline).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity).padding(.vertical, 40).hubCard()
                }
            }.padding(14)
        }
        .background(HubStyle.grouped)
        .navigationTitle("全部球局")
        .task(id: "\(year)|\(course)|\(hasShotsOnly)|\(period ?? "")|\(scoreBand ?? "")|\(search)") {
            do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
            await load()
        }
    }

    private var filterCard: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("搜索球场或日期", text: $search)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            }
            .padding(.horizontal, 11)
            .frame(height: 42)
            .background(HubStyle.grouped)
            .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
            HStack(spacing: 8) {
                Menu {
                    Button("所有年份") { year = "" }
                    ForEach(archive?.availableYears ?? [], id: \.self) { option in
                        Button(option) { year = option }
                    }
                } label: {
                    filterMenuLabel(year.isEmpty ? "所有年份" : year)
                }
                Menu {
                    Button("所有球场") { course = "" }
                    ForEach(archive?.availableCourses ?? []) { option in
                        Button(option.label) { course = option.key }
                    }
                } label: {
                    filterMenuLabel(selectedCourseLabel)
                }
                Button { hasShotsOnly.toggle() } label: {
                    HStack(spacing: 5) {
                        Image(systemName: hasShotsOnly ? "checkmark.circle.fill" : "circle")
                        Text("逐杆")
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(hasShotsOnly ? LiveHoleStyle.green : .secondary)
                    .padding(.horizontal, 8)
                    .frame(minHeight: 38)
                    .background(HubStyle.grouped)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("只看有逐杆数据")
                .accessibilityValue(hasShotsOnly ? "已开启" : "已关闭")
            }
            if period != nil || scoreBand != nil {
                HStack {
                    Text("已筛选：\(period ?? scoreBand ?? "")").font(.caption.weight(.semibold))
                    Spacer()
                    Button("清除") { period = nil; scoreBand = nil }
                        .font(.caption.weight(.bold)).foregroundStyle(LiveHoleStyle.green)
                }
            }
        }.hubCard()
    }

    private var selectedCourseLabel: String {
        guard !course.isEmpty else { return "所有球场" }
        return archive?.availableCourses.first { $0.key == course }?.label ?? "已选球场"
    }

    private func filterMenuLabel(_ text: String) -> some View {
        HStack(spacing: 6) {
            Text(text).lineLimit(1)
            Spacer(minLength: 2)
            Image(systemName: "chevron.down").font(.caption2.weight(.bold))
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(.primary)
        .padding(.horizontal, 10)
        .frame(maxWidth: .infinity, minHeight: 38)
        .background(HubStyle.grouped)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var filteredGroups: [HistoryMonthGroup] {
        let needle = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return archive?.groups ?? [] }
        return (archive?.groups ?? []).compactMap { group in
            let rounds = group.rounds.filter {
                $0.courseName.lowercased().contains(needle) || ($0.date ?? "").contains(needle)
            }
            return rounds.isEmpty ? nil : HistoryMonthGroup(
                key: group.key, label: group.label, count: rounds.count,
                average18: group.average18, bestScore: group.bestScore, rounds: rounds
            )
        }
    }

    @MainActor private func load() async {
        guard let apiBaseURL else { return }
        isLoading = true
        let nextArchive = try? await SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
            .fetchHistoryRounds(year: year.isEmpty ? nil : year,
                                course: course.isEmpty ? nil : course,
                                hasShots: hasShotsOnly ? true : nil,
                                period: period,
                                scoreBand: scoreBand,
                                search: search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                    ? nil : search.trimmingCharacters(in: .whitespacesAndNewlines))
        guard !Task.isCancelled else { return }
        if let nextArchive { archive = nextArchive }
        isLoading = false
    }
}

struct ResultsRoundRow: View {
    let round: HistoryRoundCard
    let showsScoreStrip: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 5) {
                Image(systemName: "figure.golf")
                Text("高尔夫")
                Spacer()
                Text(shortDate(round.date) ?? "日期未知")
            }
            .font(.caption2)
            .foregroundStyle(.secondary)

            HStack(alignment: .firstTextBaseline, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(round.courseName)
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(2)
                    Text([round.holesCompleted.map { "\($0) 洞" }, round.par.map { "Par \($0)" },
                          round.source == "manual" ? "手动记录" : nil]
                        .compactMap { $0 }.joined(separator: " · "))
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(round.score.map(String.init) ?? "—")
                        .font(.system(size: 31, weight: .regular))
                        .monospacedDigit()
                    Text(toParText(round.toPar))
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: round.toPar))
                }
            }
            if showsScoreStrip && !round.scoreStrip.isEmpty {
                HStack(spacing: 2) {
                    ForEach(round.scoreStrip.prefix(18)) { cell in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(AICaddieDesignTokens.scoreColor(toPar: cell.toPar))
                            .frame(maxWidth: .infinity).frame(height: 5)
                    }
                }
            }
        }
        .contentShape(Rectangle())
    }
}

private enum ResultsTrendGrain: String, CaseIterable, Identifiable {
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

private enum ResultsTrendDestination: Hashable, Identifiable {
    case round(String)
    case period(String)
    var id: String {
        switch self {
        case let .round(value): return "round:\(value)"
        case let .period(value): return "period:\(value)"
        }
    }
}

private struct ResultsTrendChartPoint: Identifiable {
    let id: String
    let label: String
    let value: Double
    let destination: ResultsTrendDestination
}

public struct ResultsTrendView: View {
    let apiBaseURL: URL?
    let adminToken: String?
    @State private var window = "last10"
    @State private var grain: ResultsTrendGrain = .round
    @State private var stats: MobileStats?
    @State private var allStats: MobileStats?
    @State private var isLoading = true
    @State private var destination: ResultsTrendDestination?

    public var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                controlCard
                if let stats { trendContent(stats) }
                else if isLoading { ProgressView("载入趋势…").padding(.top, 40) }
            }.padding(14)
        }
        .background(HubStyle.grouped).navigationTitle("时间趋势")
        .navigationDestination(item: $destination) { destination in destinationView(destination) }
        .task(id: window) { await load() }
        .onChange(of: window) { _, value in grain = defaultGrain(for: value) }
    }

    @ViewBuilder private func destinationView(_ value: ResultsTrendDestination) -> some View {
        switch value {
        case let .round(roundId):
            RoundReviewView(roundRef: roundId, fallbackCourseName: nil,
                            apiBaseURL: apiBaseURL, adminToken: adminToken)
        case let .period(period):
            ResultsArchiveView(apiBaseURL: apiBaseURL, adminToken: adminToken, initialPeriod: period)
        }
    }

    private var controlCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("统计范围 · 哪些球局参加计算").font(.caption).foregroundStyle(.secondary)
            Picker("统计范围", selection: $window) {
                Text("近 10 场").tag("last10")
                Text("近 20 场").tag("last20")
                Text("近 12 月").tag("12m")
                Text("全部").tag("all")
            }.pickerStyle(.segmented)
            Text("汇总粒度 · 同一批球局怎样分组").font(.caption).foregroundStyle(.secondary).padding(.top, 4)
            HStack(spacing: 5) {
                ForEach(ResultsTrendGrain.allCases) { option in
                    Button(option.title) { grain = option }
                        .buttonStyle(.borderedProminent)
                        .tint(grain == option ? LiveHoleStyle.green : Color.secondary.opacity(0.18))
                        .foregroundStyle(grain == option ? .white : .secondary)
                        .disabled(!allowedGrains.contains(option))
                        .frame(maxWidth: .infinity)
                }
            }
            Text(grainHint).font(.caption2).foregroundStyle(.secondary)
        }.hubCard()
    }

    @ViewBuilder private func trendContent(_ stats: MobileStats) -> some View {
        let points = chartPoints(stats)
        VStack(alignment: .leading, spacing: 10) {
            Text(rangeLabel).font(.caption).foregroundStyle(.secondary)
            Text(stats.summary?.average18.map(oneDecimal) ?? "—")
                .font(.system(size: 36, weight: .heavy)).monospacedDigit()
            Text("18 洞均杆 · 最佳 \(stats.summary?.bestScore.map(String.init) ?? "—") · 中位 \(stats.summary?.median18.map(oneDecimal) ?? "—")")
                .font(.caption).foregroundStyle(.secondary)
            if points.count >= 2 {
                Chart {
                    ForEach(Array(points.enumerated()), id: \.element.id) { index, point in
                        LineMark(x: .value("序号", index), y: .value("成绩", point.value))
                            .foregroundStyle(LiveHoleStyle.green).interpolationMethod(.catmullRom)
                        PointMark(x: .value("序号", index), y: .value("成绩", point.value))
                            .foregroundStyle(LiveHoleStyle.green).symbolSize(40)
                    }
                }
                .frame(height: 180)
                .chartYScale(domain: resultsScoreDomain(points.map(\.value)))
                .chartXAxis(.hidden).chartYAxis(.hidden)
                .chartOverlay { proxy in
                    GeometryReader { geometry in
                        Rectangle().fill(.clear).contentShape(Rectangle())
                            .gesture(SpatialTapGesture().onEnded { event in
                                guard let anchor = proxy.plotFrame else { return }
                                let frame = geometry[anchor]
                                guard frame.contains(event.location),
                                      let index: Int = proxy.value(atX: event.location.x - frame.origin.x),
                                      points.indices.contains(index) else { return }
                                destination = points[index].destination
                            })
                    }
                }
                HStack { Text(points.first?.label ?? ""); Spacer(); Text(points.last?.label ?? "") }
                    .font(.caption2).foregroundStyle(.secondary)
                Text("轻点图上点位查看对应球局").font(.caption2).foregroundStyle(LiveHoleStyle.green)
            } else {
                Text("当前范围不足两个有效数据点").font(.subheadline).foregroundStyle(.secondary)
            }
        }.hubCard()

        let periods = periods(for: stats)
        if grain != .round, !periods.isEmpty {
            periodCard(title: "周期汇总 · 点击查看球局", periods: Array(periods.prefix(24)))
        }

        if let archiveTime = (allStats ?? stats).time {
            if !archiveTime.byYear.isEmpty {
                periodCard(title: "历年表现", periods: Array(archiveTime.byYear.prefix(12)))
            }
            activityCard(time: archiveTime)
        }
    }

    private func periodCard(title: String, periods: [StatsPeriod]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).font(.caption.weight(.bold)).foregroundStyle(.secondary).padding(.bottom, 6)
            ForEach(periods) { period in
                Button { destination = .period(period.key) } label: {
                    HStack {
                        Text(period.key).font(.subheadline.weight(.bold))
                        Spacer()
                        Text("\(period.roundCount ?? 0) 场 · 均杆 \(period.average18.map(oneDecimal) ?? "—") · 最佳 \(period.bestScore.map(String.init) ?? "—")")
                            .font(.caption).foregroundStyle(.secondary)
                        Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                    }.padding(.vertical, 8).contentShape(Rectangle())
                }.buttonStyle(.plain).foregroundStyle(.primary)
                Divider()
            }
        }.hubCard()
    }

    @ViewBuilder private func activityCard(time: StatsTime) -> some View {
        let year = Int(time.byYear.first?.key ?? "") ?? Calendar.current.component(.year, from: Date())
        let days = time.byDay.filter { $0.key.hasPrefix("\(year)-") }
        let roundCount = days.compactMap(\.roundCount).reduce(0, +)
        let monthCount = Set(days.map { String($0.key.prefix(7)) }).count
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading) {
                    Text("打球频率 · \(year)").font(.subheadline.weight(.bold))
                    if time.playFrequency != nil {
                        Text("\(roundCount) 场 · 活跃 \(monthCount) 个月 · 活跃月均 \(monthCount > 0 ? oneDecimal(Double(roundCount) / Double(monthCount)) : "—") 场")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if let active = time.playFrequency?.mostActiveMonth {
                    Text("生涯最活跃月 \(active.key) · \(active.roundCount ?? 0) 场")
                        .font(.caption.weight(.semibold)).foregroundStyle(LiveHoleStyle.green)
                }
            }
            ResultsActivityCalendar(periods: time.byDay, year: year) { destination = .period($0) }
            HStack { Text("1 月"); Spacer(); Text("4 月"); Spacer(); Text("7 月"); Spacer(); Text("10 月"); Spacer(); Text("12 月") }
                .font(.caption2).foregroundStyle(.secondary)
        }.hubCard()
    }

    private var allowedGrains: [ResultsTrendGrain] {
        switch window {
        case "last10", "last20": return [.round]
        case "12m": return [.round, .month, .quarter]
        default: return [.month, .quarter, .year]
        }
    }

    private func defaultGrain(for value: String) -> ResultsTrendGrain {
        value == "12m" ? .month : value == "all" ? .year : .round
    }

    private var grainHint: String {
        switch window {
        case "last10", "last20": return "近场只按逐场查看"
        case "12m": return "默认按月，也可看逐场或季度"
        default: return "默认按年，也可按月或季度"
        }
    }

    private var rangeLabel: String {
        ["last10": "近 10 场", "last20": "近 20 场", "12m": "近 12 月", "all": "全部历史"][window] ?? "趋势"
    }

    private func periods(for stats: MobileStats) -> [StatsPeriod] {
        guard let time = stats.time else { return [] }
        switch grain {
        case .month: return time.byMonth
        case .quarter: return time.byQuarter
        case .year: return time.byYear
        case .round: return []
        }
    }

    private func chartPoints(_ stats: MobileStats) -> [ResultsTrendChartPoint] {
        if grain == .round {
            return (stats.trend?.points ?? []).compactMap { point in
                guard let score = point.score, let roundId = point.roundId else { return nil }
                return ResultsTrendChartPoint(id: roundId, label: String(point.date.prefix(10)),
                                              value: Double(score), destination: .round(roundId))
            }
        }
        return periods(for: stats).reversed().compactMap { period in
            guard period.key != "unknown", let average = period.average18 else { return nil }
            return ResultsTrendChartPoint(id: period.key, label: period.key,
                                          value: average, destination: .period(period.key))
        }
    }

    @MainActor private func load() async {
        guard let apiBaseURL else { isLoading = false; return }
        isLoading = true
        let client = SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
        var nextStats: MobileStats?
        var nextAllStats: MobileStats?
        if window == "all" {
            let loaded = try? await client.fetchMobileStats(window: "all")
            nextStats = loaded
            nextAllStats = loaded
        } else {
            if allStats == nil {
                async let selected: MobileStats? = try? await client.fetchMobileStats(window: window)
                async let lifetime: MobileStats? = try? await client.fetchMobileStats(window: "all")
                nextStats = await selected
                nextAllStats = await lifetime
            } else {
                nextStats = try? await client.fetchMobileStats(window: window)
            }
        }
        // `.task(id:)` cancels the previous request when the range changes. Do
        // not let a transport that completes after cancellation overwrite the
        // newer selection.
        guard !Task.isCancelled else { return }
        if let nextStats { stats = nextStats }
        if let nextAllStats { allStats = nextAllStats }
        isLoading = false
    }
}

private struct ResultsActivityCalendar: View {
    let periods: [StatsPeriod]
    let year: Int
    let onSelect: (String) -> Void

    var body: some View {
        GeometryReader { geometry in
            Canvas { context, size in
                let cells = calendarCells
                let gap: CGFloat = 2
                let columns = max(calendarColumnCount, 1)
                let cell = min((size.width - gap * CGFloat(columns - 1)) / CGFloat(columns), (size.height - gap * 6) / 7)
                for item in cells {
                    let rect = CGRect(x: CGFloat(item.week) * (cell + gap), y: CGFloat(item.weekday) * (cell + gap), width: cell, height: cell)
                    context.fill(Path(roundedRect: rect, cornerRadius: 1.5), with: .color(color(item.count)))
                }
            }
            .contentShape(Rectangle())
            .gesture(SpatialTapGesture().onEnded { event in
                let gap: CGFloat = 2
                let columns = max(calendarColumnCount, 1)
                let cell = min((geometry.size.width - gap * CGFloat(columns - 1)) / CGFloat(columns), (geometry.size.height - gap * 6) / 7)
                let week = Int(event.location.x / (cell + gap))
                let weekday = Int(event.location.y / (cell + gap))
                if let selected = calendarCells.first(where: { $0.week == week && $0.weekday == weekday && $0.count > 0 }) {
                    onSelect(selected.day)
                }
            })
        }
        .frame(height: 56)
    }

    private var calendarCells: [(day: String, count: Int, week: Int, weekday: Int)] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        guard let start = calendar.date(from: DateComponents(year: year, month: 1, day: 1)),
              let end = calendar.date(from: DateComponents(year: year + 1, month: 1, day: 1)) else { return [] }
        let counts = Dictionary(uniqueKeysWithValues: periods.map { ($0.key, $0.roundCount ?? 0) })
        let offset = calendar.component(.weekday, from: start) - 1
        let formatter = DateFormatter(); formatter.calendar = calendar; formatter.timeZone = calendar.timeZone; formatter.dateFormat = "yyyy-MM-dd"
        var date = start
        var index = 0
        var out: [(String, Int, Int, Int)] = []
        while date < end {
            let position = offset + index
            let key = formatter.string(from: date)
            out.append((key, counts[key] ?? 0, position / 7, position % 7))
            index += 1
            date = calendar.date(byAdding: .day, value: 1, to: date)!
        }
        return out
    }

    private var calendarColumnCount: Int {
        (calendarCells.map(\.week).max() ?? -1) + 1
    }

    private func color(_ count: Int) -> Color {
        switch count {
        case 0: return Color.secondary.opacity(0.12)
        case 1: return LiveHoleStyle.green.opacity(0.28)
        case 2: return LiveHoleStyle.green.opacity(0.55)
        case 3: return LiveHoleStyle.green.opacity(0.78)
        default: return LiveHoleStyle.green
        }
    }
}

struct ResultsCoursesView: View {
    let courses: [StatsCourse]
    let apiBaseURL: URL?
    let adminToken: String?
    var body: some View {
        List(courses) { course in
            NavigationLink {
                CourseStatsDetailView(course: course, apiBaseURL: apiBaseURL, adminToken: adminToken)
            } label: {
                VStack(alignment: .leading) {
                    Text(course.courseName ?? course.courseKey)
                    Text("\(course.roundCount ?? 0) 场 · 均杆 \(course.average18.map(oneDecimal) ?? "—") · 最佳 \(course.bestScore.map(String.init) ?? "—")")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }.navigationTitle("球场")
    }
}

struct ResultsClubsView: View {
    let clubs: [StatsClub]
    var body: some View {
        List {
            Section {
                ForEach(clubs) { club in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(zhClubName(club.club)).font(.headline)
                            Text("\(club.sampleCount ?? 0) 个有效样本").font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing) {
                            Text(club.median.map { "\(CoursePrepRoute.yards(fromMetres: $0)) 码" } ?? "—")
                                .font(.headline.monospacedDigit())
                            if let p10 = club.p10, let p90 = club.p90 {
                                Text("\(CoursePrepRoute.yards(fromMetres: p10))–\(CoursePrepRoute.yards(fromMetres: p90))")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            } header: {
                Text("历史击球 · 不修改球包")
            } footer: {
                Text("这里显示实际击球距离和离散范围；球包配置与自定义杆距在首页的球包设置中修改。")
            }
        }.navigationTitle("球杆")
    }
}

private func oneDecimal(_ value: Double) -> String { String(format: "%.1f", value) }
private func resultsScoreDomain(_ values: [Double]) -> ClosedRange<Double> {
    guard let low = values.min(), let high = values.max() else { return 70...100 }
    if low == high { return (low - 1)...(high + 1) }
    let padding = max(1, (high - low) * 0.14)
    return (low - padding)...(high + padding)
}
private func shortDate(_ raw: String?) -> String? { raw.map { String($0.prefix(10)) } }
private func monthLabel(_ key: String) -> String {
    let parts = key.split(separator: "-")
    guard parts.count == 2 else { return key }
    return "\(parts[0]) 年 \(Int(parts[1]) ?? 0) 月"
}
private func toParText(_ value: Int?) -> String {
    guard let value else { return "" }
    if value == 0 { return "E" }
    return value > 0 ? "+\(value)" : "\(value)"
}
