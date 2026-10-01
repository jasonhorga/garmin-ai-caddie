import Combine
import Foundation
import SwiftUI

/// 表现分析 (README §9, `stats.html` 2): no charts and no cards. One "最该练" line, then the four
/// phases written the same way — a big number, how it compares with the previous comparable period,
/// and one split bar (good segment green, most common miss yellow, the rest grey).
public struct StatsView: View {
    public let apiBaseURL: URL?
    public let adminToken: String?

    /// Window, its stats (with their previous period) and loading / failure, committed together.
    @State private var load = AnalysisLoadState()
    @State private var inFlight: Task<Void, Never>?

    public init(apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
    }

    public var body: some View {
        ScrollView {
            AnalysisPageContent(
                window: Binding(get: { load.window }, set: { start(load.select($0)) }),
                state: load
            )
        }
        .background(Color.white)
        .navigationTitle("表现分析")
        .task { start(load.currentRequest) }
        .onDisappear { inFlight?.cancel() }
        .onReceive(NotificationCenter.default.publisher(for: .garminDataDidRefresh)) { _ in
            start(load.refresh())
        }
    }

    /// One request per window selection / refresh; only the current generation may write back.
    private func start(_ request: AnalysisLoadState.Request) {
        inFlight?.cancel()
        guard let apiBaseURL else {
            load.complete(request, stats: nil)
            return
        }
        let client = SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
        inFlight = Task { @MainActor in
            let stats = try? await client.fetchMobileStats(window: request.window)
            guard !Task.isCancelled else { return }
            load.complete(request, stats: stats)
        }
    }
}

/// The 表现分析 page for one load state: the window picker and that window's content. Pure, so
/// the design snapshots render the real page including its picker.
struct AnalysisPageContent: View {
    @Binding var window: String
    let state: AnalysisLoadState

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Picker("统计范围", selection: $window) {
                ForEach(AnalysisLoadState.windows) { option in
                    Text(option.title).tag(option.id)
                }
            }
            .pickerStyle(.segmented)
            .accessibilityIdentifier("analysis-window")
            .padding(.bottom, 16)
            switch state.phase {
            case .loading:
                ProgressView("载入统计…").frame(maxWidth: .infinity).padding(.top, 40)
            case .failed(let message):
                VStack(spacing: 8) {
                    Image(systemName: "chart.bar.xaxis").font(.title).foregroundStyle(.secondary)
                    Text(message).font(.subheadline).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 40)
                .accessibilityIdentifier("analysis-failed")
            case .loaded(let stats):
                StatsContent(
                    stats: stats,
                    baseline: ResultsPresentation.baseline(stats),
                    comparison: AnalysisLoadState.comparisonLabel(state.window)
                )
            }
        }
        .padding(16)
    }
}

struct StatsContent: View {
    let stats: MobileStats
    var baseline: MobileStats? = nil
    /// What ↑ / ↓ compare against ("和前 10 场比"); nil for 全部.
    var comparison: String? = nil

    private static let good = LiveHoleStyle.green
    private static let warn = HubStyle.bogey

    var body: some View {
        let analysis = ResultsPresentation.analysis(stats, baseline: baseline)
        VStack(alignment: .leading, spacing: 0) {
            focus(analysis.focus)
            ForEach(analysis.rows) { row in
                phaseRow(row)
            }
            if analysis.rows.isEmpty {
                Text("这段时间还没有记录开球、攻果岭、救球或推杆")
                    .font(.subheadline).foregroundStyle(.secondary)
                    .padding(.vertical, 30)
            }
            if let comparison {
                Text(baseline == nil ? "前一段没有球局，暂不比较" : "↑ ↓ \(comparison)")
                    .font(.caption2).foregroundStyle(.tertiary)
                    .padding(.top, 14)
                    .accessibilityIdentifier("analysis-comparison")
            }
        }
    }

    @ViewBuilder
    private func focus(_ focus: ResultsPresentation.Focus?) -> some View {
        if let focus {
            VStack(alignment: .leading, spacing: 4) {
                Text("最该练").font(.footnote.weight(.semibold)).foregroundStyle(Self.warn)
                Text(focus.title).font(.system(size: 26, weight: .bold))
                Text(focus.detail).font(.subheadline).foregroundStyle(.secondary).monospacedDigit()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.bottom, 18)
            .overlay(alignment: .bottom) { Divider() }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("analysis-focus")
        }
    }

    private func phaseRow(_ row: ResultsPresentation.PhaseRow) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(row.title).font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
            HStack(alignment: .lastTextBaseline) {
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    Text(row.value + row.unit).font(.system(size: 34, weight: .bold)).monospacedDigit()
                    Text(row.caption).font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                if let delta = row.delta {
                    Text(delta.text)
                        .font(.subheadline.weight(.semibold)).monospacedDigit()
                        .foregroundStyle(delta.isBetter.map { $0 ? Self.good : Self.warn } ?? Color.secondary)
                }
            }
            splitBar(row.segments)
            if let note = row.note {
                Text(note).font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }
        }
        .padding(.vertical, 16)
        .overlay(alignment: .bottom) { Divider() }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("analysis-phase-\(row.title)")
    }

    private func splitBar(_ segments: [ResultsPresentation.Segment]) -> some View {
        let shown = segments.filter { $0.pct > 0 }
        let total = max(shown.reduce(0) { $0 + $1.pct }, 0.0001)
        return VStack(spacing: 4) {
            GeometryReader { proxy in
                HStack(spacing: 2) {
                    ForEach(shown) { segment in
                        RoundedRectangle(cornerRadius: 3, style: .continuous)
                            .fill(color(segment.tone))
                            .frame(width: max(2, (proxy.size.width - CGFloat(shown.count - 1) * 2) * segment.pct / total))
                    }
                }
            }
            .frame(height: 10)
            GeometryReader { proxy in
                HStack(spacing: 2) {
                    ForEach(shown) { segment in
                        Text(segment.pct >= 8 ? "\(segment.label) \(ResultsPresentation.whole(segment.pct))%" : "")
                            .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                            .lineLimit(1).minimumScaleFactor(0.7)
                            .frame(width: max(2, (proxy.size.width - CGFloat(shown.count - 1) * 2) * segment.pct / total),
                                   alignment: .leading)
                    }
                }
            }
            .frame(height: 14)
        }
    }

    private func color(_ tone: ResultsPresentation.SegmentTone) -> Color {
        switch tone {
        case .good: return Self.good
        case .warn: return Self.warn
        case .neutral: return Color.primary.opacity(0.22)
        }
    }
}

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
        .navigationTitle(course.localizedCourseDisplayName)
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
                        RoundReviewView(roundRef: ref, fallbackCourseName: course.localizedCourseDisplayName,
                                        apiBaseURL: apiBaseURL, adminToken: adminToken,
                                        globalId: r.globalId ?? course.globalId,
                                        backGlobalId: r.backGlobalId ?? course.backGlobalId,
                                        nine: r.nine, teeBox: r.teeBox ?? course.teeBox)
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
