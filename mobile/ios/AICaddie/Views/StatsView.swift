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
                    comparisonNote: AnalysisLoadState.comparisonNote(window: state.window, previous: stats.previous)
                )
            }
        }
        .padding(16)
    }
}

struct StatsContent: View {
    let stats: MobileStats
    var baseline: MobileStats? = nil
    /// What ↑ / ↓ compare against, or why there is no comparison; nil for 全部.
    var comparisonNote: String? = nil

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
            if let comparisonNote {
                Text(comparisonNote)
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
    /// The history-wide `scoring` (loops / nine combos), matched to this course by its `loopKeys`.
    var scoring: StatsScoring? = nil
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil
    /// Where a hole's topo comes from; nil uses the backend's topo URL. The design snapshots point
    /// it at local files so the topo-backed page is captured deterministically.
    var topoURL: ((ResultsCoursePresentation.HoleRef) -> URL?)? = nil
    @State private var showsAllCombos = false

    private typealias P = ResultsCoursePresentation

    private func topo(_ ref: P.HoleRef?) -> URL? {
        guard let ref else { return nil }
        if let topoURL { return topoURL(ref) }
        guard let apiBaseURL else { return nil }
        return SyncClient.topoImageURL(baseURL: apiBaseURL, globalId: ref.globalId, localHole: ref.localHole)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                headline
                dotsStrip
                hardHolesSection
                combosSection
                roundsSection
            }
            .padding(14)
        }
        .background(alignment: .top) { backdrop }
        .background(HubStyle.grouped)
        // stats.html 6: the back control, then one 28pt course heading (no second nav title).
        .navigationBarTitleDisplayMode(.inline)
    }

    // MARK: topo 打底 (stats.html 6)

    @ViewBuilder private var backdrop: some View {
        if let url = topo(P.backdrop(course)) {
            TopoHoleBaseImage(topoURL: url, fallback: nil)
                .frame(height: 340)
                .frame(maxWidth: .infinity)
                .clipped()
                .opacity(0.28)
                .overlay {
                    LinearGradient(colors: [HubStyle.grouped.opacity(0.35), HubStyle.grouped],
                                   startPoint: .top, endPoint: .bottom)
                }
                .allowsHitTesting(false)
                .accessibilityHidden(true)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(course.localizedCourseDisplayName)
                .font(.system(size: 28, weight: .bold))
                .lineLimit(2)
            Text(P.subtitle(course)).font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
        }
        .padding(.top, 24)
        .accessibilityIdentifier("course-header")
    }

    private var headline: some View {
        HStack(alignment: .lastTextBaseline, spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
                Text(course.average18.map { String(format: "%.1f", $0) } ?? "—")
                    .font(.system(size: 56, weight: .bold)).monospacedDigit()
                Text("均杆").font(.footnote).foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(course.bestScore.map(String.init) ?? "—")
                    .font(.system(size: 22, weight: .bold)).monospacedDigit()
                    .foregroundStyle(course.bestScore == nil ? Color.secondary : LiveHoleStyle.green)
                Text("最佳").font(.footnote).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("course-average")
    }

    // MARK: 每场一个点 (oldest -> newest, the best green)

    @ViewBuilder private var dotsStrip: some View {
        let dots = P.dots(course)
        if !dots.isEmpty {
            CourseDotsStrip(dots: dots)
                .frame(height: 56)
                .accessibilityIdentifier("course-dots")
        }
    }

    // MARK: 最难的三个洞

    @ViewBuilder private var hardHolesSection: some View {
        let holes = P.hardestHoles(course, loops: scoring?.loops ?? [])
        if !holes.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                HubSectionLabel("最难的三个洞")
                HStack(alignment: .top, spacing: 8) {
                    ForEach(holes) { hole in
                        NavigationLink {
                            CourseHoleHistoryView(course: course, hole: hole, apiBaseURL: apiBaseURL, adminToken: adminToken)
                        } label: { hardHoleCard(hole) }
                        .buttonStyle(.plain)
                        .foregroundStyle(.primary)
                    }
                    ForEach(holes.count..<3, id: \.self) { _ in Color.clear.frame(maxWidth: .infinity) }
                }
            }
            .accessibilityIdentifier("course-hard-holes")
        }
    }

    private func hardHoleCard(_ hole: P.HardHole) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack {
                TopoHoleBaseImage.groundColor
                if let url = topo(hole.topo) {
                    TopoHoleBaseImage(topoURL: url, fallback: nil)
                }
            }
            .frame(height: 96)
            .frame(maxWidth: .infinity)
            .clipped()
            VStack(alignment: .leading, spacing: 2) {
                Text(hole.overPar).font(.headline.monospacedDigit()).foregroundStyle(HubStyle.bogey)
                Text(hardHoleCaption(hole)).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
            .padding(8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .shadow(color: Color.black.opacity(0.05), radius: 3, x: 0, y: 1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("course-hard-\(hole.loopKey)-\(hole.hole)")
    }

    private func hardHoleCaption(_ hole: P.HardHole) -> String {
        var parts = ["\(hole.loopLabel) \(hole.hole) 洞"]
        if let par = hole.par { parts.append("Par \(par)") }
        return parts.joined(separator: " · ")
    }

    // MARK: 常打的组合 (top 3, the rest folded)

    @ViewBuilder private var combosSection: some View {
        let combos = P.combos(course, combos: scoring?.nineCombos ?? [])
        if !combos.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                HubSectionLabel("常打的组合")
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(showsAllCombos ? combos : Array(combos.prefix(3))) { combo in
                        Text(combo.text)
                            .font(.subheadline.monospacedDigit())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 8)
                            .overlay(alignment: .bottom) { Divider() }
                    }
                    if combos.count > 3 || (course.nineOnlyRounds ?? 0) > 0 {
                        Button {
                            showsAllCombos.toggle()
                        } label: {
                            HStack {
                                Text(showsAllCombos ? "收起" : P.allCombosLabel(course, count: combos.count))
                                Spacer()
                                Image(systemName: showsAllCombos ? "chevron.up" : "chevron.down").font(.caption2)
                            }
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .padding(.vertical, 8)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(combos.count <= 3 && !showsAllCombos)
                        .accessibilityIdentifier("course-all-combos")
                    }
                }
                .hubCard(padding: 12)
            }
            .accessibilityIdentifier("course-combos")
        }
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
}

/// 球场详情's thin line with one dot per 18-hole round, oldest left; lower scores sit higher and the
/// best round is the green dot (`stats.html` 6).
struct CourseDotsStrip: View {
    let dots: [ResultsCoursePresentation.Dot]

    var body: some View {
        GeometryReader { geo in
            let scores = dots.map(\.score)
            let low = Double(scores.min() ?? 0)
            let high = Double(scores.max() ?? 0)
            let inset: CGFloat = 6
            let width = max(geo.size.width - inset * 2, 1)
            let height = max(geo.size.height - inset * 2, 1)
            let step = dots.count > 1 ? width / CGFloat(dots.count - 1) : 0
            ZStack(alignment: .topLeading) {
                Rectangle()
                    .fill(Color.primary.opacity(0.15))
                    .frame(width: width, height: 1)
                    .offset(x: inset, y: geo.size.height / 2)
                ForEach(dots) { dot in
                    let fraction = high > low ? (Double(dot.score) - low) / (high - low) : 0.5
                    let x = dots.count > 1 ? inset + step * CGFloat(dot.index) : geo.size.width / 2
                    let y = inset + height * CGFloat(fraction)
                    Circle()
                        .fill(dot.isBest ? LiveHoleStyle.green : Color.primary.opacity(0.35))
                        .frame(width: dot.isBest ? 9 : 6, height: dot.isBest ? 9 : 6)
                        .position(x: x, y: y)
                }
            }
        }
        .accessibilityElement()
        .accessibilityLabel("这个球场每一场的杆数，从旧到新")
    }
}

/// A hardest-hole card's drill-in: every round here that played the hole, each opening that
/// round's shot map on it (每次打这洞的落点).
struct CourseHoleHistoryView: View {
    let course: StatsCourse
    let hole: ResultsCoursePresentation.HardHole
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil

    var body: some View {
        let visits = ResultsCoursePresentation.visits(course, hole: hole)
        List {
            Section {
                ForEach(visits) { visit in
                    NavigationLink {
                        RoundHoleShotMapScreen(
                            roundRef: visit.round.roundId ?? "", hole: visit.displayHole,
                            apiBaseURL: apiBaseURL, adminToken: adminToken,
                            globalId: visit.round.globalId ?? course.globalId,
                            backGlobalId: visit.round.backGlobalId ?? course.backGlobalId,
                            nine: visit.round.nine, teeBox: visit.round.teeBox ?? course.teeBox
                        )
                    } label: {
                        HStack {
                            Text(String(visit.round.date.prefix(10))).monospacedDigit()
                            Spacer()
                            Text("第 \(visit.displayHole) 洞").font(.caption).foregroundStyle(.secondary)
                            Text(visit.round.score.map(String.init) ?? "—")
                                .font(.subheadline.monospacedDigit().weight(.bold))
                                .frame(width: 40, alignment: .trailing)
                        }
                    }
                }
            } header: {
                Text("平均 \(hole.overPar) · \(hole.samples) 次")
            } footer: {
                if visits.isEmpty { Text("没有能打开的球局") }
            }
        }
        .navigationTitle("\(hole.loopLabel) \(hole.hole) 洞")
        .navigationBarTitleDisplayMode(.inline)
    }
}
