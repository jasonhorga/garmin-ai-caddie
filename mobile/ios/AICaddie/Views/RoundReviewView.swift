import Foundation
import SwiftUI

/// Closed Garmin fairway vocabulary. Unknown or absent values are not misses and
/// must stay out of the FIR denominator.
func roundReviewFairwayOutcome(_ raw: String?) -> Bool? {
    guard let raw else { return nil }
    switch raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
    case "hit", "fairway", "center", "centre", "true", "1": return true
    case "left", "right", "miss", "false", "0": return false
    default: return nil
    }
}

func roundReviewFairwayCounts(_ values: [String?]) -> (hit: Int, recorded: Int) {
    let outcomes = values.compactMap(roundReviewFairwayOutcome)
    return (outcomes.filter { $0 }.count, outcomes.count)
}

func roundReviewFairwayLabel(_ raw: String?) -> String {
    switch roundReviewFairwayOutcome(raw) {
    case .some(true): return "球道✓"
    case .some(false):
        switch raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "left": return "偏左"
        case "right": return "偏右"
        default: return "球道✗"
        }
    case .none: return "未记录"
    }
}

/// 单场复盘 (B3, `review.html` screen 1): the saved round summary in the same layout as 本场汇总 —
/// the big to-par, the cumulative trend, the OUT / IN scorecard (tap a score to open that hole's
/// shots), the four tiles, then 分享. Missing data is not called out: a tile without data is simply
/// not shown. Data comes from /api/v2/history/rounds/{ref}.
public struct RoundReviewView: View {
    public let roundRef: String
    public let fallbackCourseName: String?
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let globalId: Int?
    public let backGlobalId: Int?
    public let nine: String?
    public let teeBox: String?

    @State private var detail: RoundDetail?
    @State private var isLoading = true
    @State private var errorText: String?
    @State private var shotMapHole: ShotMapHole?
    @StateObject private var shotMapRepository: RoundShotMapRepository

    public init(roundRef: String, fallbackCourseName: String? = nil, apiBaseURL: URL? = nil, adminToken: String? = nil, globalId: Int? = nil, backGlobalId: Int? = nil, nine: String? = nil, teeBox: String? = nil) {
        self.roundRef = roundRef
        self.fallbackCourseName = fallbackCourseName
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.globalId = globalId
        self.backGlobalId = backGlobalId
        self.nine = nine
        self.teeBox = teeBox
        _shotMapRepository = StateObject(
            wrappedValue: RoundShotMapRepository(
                roundRef: roundRef,
                apiBaseURL: apiBaseURL,
                adminToken: adminToken,
                globalId: globalId,
                backGlobalId: backGlobalId,
                nine: nine,
                teeBox: teeBox
            )
        )
    }

    public var body: some View {
        Group {
            if isLoading && detail == nil {
                AICaddieLoadingView(text: "载入这场…")
            } else {
                ScrollView(showsIndicators: false) {
                    RoundReviewContent(
                        detail: detail, isLoading: isLoading, errorText: errorText,
                        fallbackCourseName: fallbackCourseName,
                        globalId: globalId,
                        onSelectHole: { hole in
                            guard reviewHoles.canOpen(hole) else { return }
                            shotMapHole = ShotMapHole(hole: hole)
                        },
                        onRetry: { Task { await load() } }
                    )
                }
            }
        }
        .background(LivePlayStyle.base.ignoresSafeArea())
        .preferredColorScheme(.dark)
        .navigationTitle("单场复盘")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: roundRef) {
            await load()
        }
        .fullScreenCover(item: $shotMapHole) { item in
            NavigationStack {
                RoundShotMapPagerScreen(
                    roundRef: roundRef, holes: reviewHoles.played, startHole: item.hole,
                    apiBaseURL: apiBaseURL, adminToken: adminToken,
                    onClose: { shotMapHole = nil },
                    mapRepository: shotMapRepository,
                    globalId: globalId,
                    backGlobalId: backGlobalId,
                    nine: nine,
                    teeBox: teeBox,
                    scorecard: detail?.scorecard ?? [],
                    onSaved: { Task { await load() } },
                    canonicalRoundRef: detail?.roundRef,
                    stripHoles: reviewHoles.strip
                )
            }
        }
    }

    private var reviewHoles: RoundReviewHoles { RoundReviewHoles(detail?.scorecard ?? []) }

    struct ShotMapHole: Identifiable {
        let hole: Int
        var id: Int { hole }
    }

    @MainActor
    private func load() async {
        guard let apiBaseURL else {
            isLoading = false
            errorText = "未配置后端地址"
            return
        }
        if detail == nil, let cached = RoundReviewDiskCache.loadDetail(roundRef: roundRef) {
            detail = cached
            isLoading = false
        }
        isLoading = detail == nil
        errorText = nil
        do {
            let fresh = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).fetchRoundDetail(roundRef: roundRef, globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox)
            detail = fresh
            RoundReviewDiskCache.saveDetail(fresh, roundRef: roundRef)
        } catch {
            if detail == nil { errorText = "这场暂时取不到(网络或数据)" }
        }
        isLoading = false
    }
}

/// Split from the ScrollView so the CI ImageRenderer snapshot can render it (ScrollView content does not).
struct RoundReviewContent: View {
    let detail: RoundDetail?
    let isLoading: Bool
    let errorText: String?
    let fallbackCourseName: String?
    let globalId: Int?
    var onSelectHole: (Int) -> Void
    var onRetry: () -> Void

    init(
        detail: RoundDetail?,
        isLoading: Bool,
        errorText: String?,
        fallbackCourseName: String?,
        globalId: Int? = nil,
        onSelectHole: @escaping (Int) -> Void = { _ in },
        onRetry: @escaping () -> Void = {}
    ) {
        self.detail = detail
        self.isLoading = isLoading
        self.errorText = errorText
        self.fallbackCourseName = fallbackCourseName
        self.globalId = globalId
        self.onSelectHole = onSelectHole
        self.onRetry = onRetry
    }

    struct ReviewMetric: Identifiable, Equatable {
        let id: String
        let title: String
        let value: String
        let detail: String?
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let detail, detail.found {
                let card = RoundReviewScorecard(detail.scorecard)
                header(detail.round)
                hero(detail.round, card: card)
                if !card.cumulativeToPar.isEmpty {
                    LiveCumulativeTrend(values: card.cumulativeToPar, holeCount: max(card.holes.count, card.cumulativeToPar.count))
                        .frame(height: 70)
                        .accessibilityIdentifier("round-review-trend")
                }
                if !card.holes.isEmpty {
                    scorecard(card)
                }
                let metrics = Self.reviewMetrics(detail)
                if !metrics.isEmpty {
                    metricGrid(metrics)
                }
                shareButton(detail, card: card)
            } else if isLoading {
                ProgressView("载入这场…")
                    .tint(LivePlayStyle.ink)
                    .foregroundStyle(LivePlayStyle.ink60)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 40)
            } else {
                emptyCard
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 12)
        .padding(.bottom, 28)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: header + hero

    private func courseName(_ round: RoundDetailSummary?) -> String {
        localizedCourseDisplayName(round?.courseName ?? fallbackCourseName, globalId: globalId, fallback: "这一场")
    }

    private func header(_ round: RoundDetailSummary?) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(courseName(round))
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(LivePlayStyle.ink)
                .fixedSize(horizontal: false, vertical: true)
            let subtitle = Self.summarySubtitle(round)
            if !subtitle.isEmpty {
                Text(subtitle)
                    .font(.system(size: 13))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink60)
            }
        }
    }

    private func hero(_ round: RoundDetailSummary?, card: RoundReviewScorecard) -> some View {
        let toPar = round?.toPar ?? card.cumulativeToPar.last
        let strokes = round?.score ?? (card.holes.isEmpty ? nil : card.strokes)
        return HStack(alignment: .bottom, spacing: 16) {
            Text(toPar.map(LiveRoundScoreSummary.toParText) ?? "—")
                .font(.system(size: 88, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
            VStack(alignment: .leading, spacing: 2) {
                Text(strokes.map { "\($0) 杆" } ?? "—")
                    .font(.system(size: 24, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                if let par = round?.par {
                    Text("Par \(par)")
                        .font(.system(size: 13))
                        .monospacedDigit()
                        .foregroundStyle(LivePlayStyle.ink60)
                }
            }
            .padding(.bottom, 6)
        }
        .accessibilityElement(children: .combine)
        // Keep the load-ready marker on the hero itself. Putting it on the outer RoundReviewContent
        // VStack makes SwiftUI replace every descendant's identifier, including the individually
        // tappable `round-review-hole-N` cells.
        .accessibilityIdentifier("round-review-content-ready")
    }

    /// date · 已打 N/M 洞; never fabricates a tee colour.
    static func summarySubtitle(_ round: RoundDetailSummary?) -> String {
        var parts: [String] = []
        if let date = round?.date, !date.isEmpty {
            parts.append(aiCaddieShortDate(date))
        }
        if let course = round?.courseHoles, course > 0, course != (round?.holesScored ?? round?.holesCompleted) {
            let played = round?.holesScored ?? round?.holesCompleted ?? 0
            parts.append("已打 \(played)/\(course) 洞")
        } else if let holes = round?.holesCompleted {
            parts.append("\(holes) 洞")
        }
        return parts.joined(separator: " · ")
    }

    // MARK: scorecard (every score opens its shot map)

    private func scorecard(_ card: RoundReviewScorecard) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("记分卡")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink)
                Spacer()
                Text("点成绩看落点")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            .padding(.horizontal, 4)
            LiveNineCard(
                label: card.holes.count > 9 ? "OUT" : "合计",
                holes: Array(card.holes.prefix(9)),
                scores: card.scores,
                onSelect: onSelectHole,
                cellIdentifier: { "round-review-hole-\($0)" },
                canSelect: card.canOpen
            )
            if card.holes.count > 9 {
                LiveNineCard(
                    label: "IN",
                    holes: Array(card.holes.dropFirst(9).prefix(9)),
                    scores: card.scores,
                    onSelect: onSelectHole,
                    cellIdentifier: { "round-review-hole-\($0)" },
                    canSelect: card.canOpen
                )
            }
        }
    }

    // MARK: tiles

    /// Prefer recorded per-hole facts; older rounds fall back to Garmin's round-level phase totals.
    /// A tile without data is left out rather than shown as a misleading 0%.
    static func reviewMetrics(_ detail: RoundDetail) -> [ReviewMetric] {
        let holes = detail.scorecard
        var metrics: [ReviewMetric] = []
        let girHoles = holes.filter { $0.gir != nil }
        let girHit = girHoles.filter { $0.gir == true }.count
        let fairwayCounts = roundReviewFairwayCounts(holes.map(\.fairway))
        if fairwayCounts.recorded > 0 {
            metrics.append(ReviewMetric(
                id: "fairway", title: "球道命中", value: "\(percent(fairwayCounts.hit, fairwayCounts.recorded))%",
                detail: "\(fairwayCounts.hit)/\(fairwayCounts.recorded)"
            ))
        } else if let tee = phaseMetrics("tee", in: detail),
                  let hit = tee.fairwaysHit,
                  let recorded = tee.fairwaysRecorded,
                  recorded > 0 {
            metrics.append(ReviewMetric(
                id: "fairway", title: "球道命中", value: "\(percent(hit, recorded))%",
                detail: "\(hit)/\(recorded)"
            ))
        }
        if !girHoles.isEmpty {
            metrics.append(ReviewMetric(
                id: "gir", title: "GIR 上果岭", value: "\(percent(girHit, girHoles.count))%",
                detail: "\(girHit)/\(girHoles.count)"
            ))
        } else if let approach = phaseMetrics("approach", in: detail),
                  let hit = approach.gir,
                  let recorded = approach.girRecorded,
                  recorded > 0 {
            metrics.append(ReviewMetric(
                id: "gir", title: "GIR 上果岭", value: "\(percent(hit, recorded))%",
                detail: "\(hit)/\(recorded)"
            ))
        }
        let puttHoles = holes.compactMap(\.putts)
        if !puttHoles.isEmpty {
            let total = puttHoles.reduce(0, +)
            metrics.append(ReviewMetric(
                id: "putts", title: "推杆", value: "\(total)",
                detail: String(format: "%.1f/洞", Double(total) / Double(puttHoles.count))
            ))
        } else if let total = phaseMetrics("putting", in: detail)?.totalPutts {
            metrics.append(ReviewMetric(id: "putts", title: "推杆", value: "\(total)", detail: nil))
        }
        let penaltyHoles = holes.compactMap(\.penalties)
        if !penaltyHoles.isEmpty {
            metrics.append(ReviewMetric(
                id: "penalties", title: "罚杆", value: "\(penaltyHoles.reduce(0, +))", detail: nil
            ))
        } else if let total = phaseMetrics("penalty / damage", in: detail)?.totalPenalties {
            metrics.append(ReviewMetric(id: "penalties", title: "罚杆", value: "\(total)", detail: nil))
        }
        return metrics
    }

    private static func phaseMetrics(_ phase: String, in detail: RoundDetail) -> RoundDetailPhaseMetrics? {
        detail.phaseSummary.first { $0.phase.lowercased() == phase }?.metrics
    }

    private static func percent(_ hit: Int, _ total: Int) -> Int {
        LiveRoundScoreSummary.percent(hit, of: total) ?? 0
    }

    private func metricGrid(_ metrics: [ReviewMetric]) -> some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 2), spacing: 8) {
            ForEach(metrics) { metric in
                LiveSummaryTile(
                    title: metric.title,
                    value: metric.value,
                    detail: metric.detail,
                    identifier: "round-review-metric-\(metric.id)"
                )
            }
        }
    }

    // MARK: share

    private func shareButton(_ detail: RoundDetail, card: RoundReviewScorecard) -> some View {
        ShareLink(item: Self.shareText(course: courseName(detail.round), round: detail.round, card: card)) {
            Label("分享", systemImage: "square.and.arrow.up")
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(LiveScoreStyle.primaryInk)
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .background(LiveScoreStyle.primaryFill, in: Capsule())
        }
        .buttonStyle(.plain)
        .padding(.top, 4)
        .accessibilityIdentifier("round-review-share")
    }

    /// "黑骑士 · 9月21日\n86 杆（+14）· OUT 43 · IN 43".
    static func shareText(course: String, round: RoundDetailSummary?, card: RoundReviewScorecard) -> String {
        var title = course
        if let date = round?.date, !date.isEmpty { title += " · " + aiCaddieShortDate(date) }
        var parts: [String] = []
        let strokes = round?.score ?? (card.holes.isEmpty ? nil : card.strokes)
        let toPar = round?.toPar ?? card.cumulativeToPar.last
        if let strokes {
            parts.append(toPar.map { "\(strokes) 杆（\(LiveRoundScoreSummary.toParText($0))）" } ?? "\(strokes) 杆")
        }
        if card.holes.count > 9 {
            if let out = card.nineTotal(card.holes.prefix(9)) { parts.append("OUT \(out)") }
            if let back = card.nineTotal(card.holes.dropFirst(9)) { parts.append("IN \(back)") }
        }
        return parts.isEmpty ? title : title + "\n" + parts.joined(separator: " · ")
    }

    private var emptyCard: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.title)
                .foregroundStyle(LivePlayStyle.ink45)
            Text(errorText ?? "这场没有可显示的记录")
                .font(.subheadline)
                .foregroundStyle(LivePlayStyle.ink60)
            if errorText != nil {
                Button("重新载入", action: onRetry)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(LiveScoreStyle.primaryInk)
                    .padding(.horizontal, 22)
                    .frame(height: 44)
                    .background(LiveScoreStyle.primaryFill, in: Capsule())
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("round-review-retry")
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

/// The holes of a reviewed round (README B3, `review.html`): the strip and the scorecard keep the
/// course's full width (up to 18) so a 9-of-18 round still shows holes 10–18, while only holes that
/// were actually scored page, prefetch and open a shot map. Treating a blank hole as played would
/// fabricate maps and waste requests. A round with no score at all pages every hole.
struct RoundReviewHoles: Equatable {
    static let maximumHoles = 18

    let strip: [Int]
    let played: [Int]

    init(_ scorecard: [RoundDetailHole]) {
        let rows = RoundReviewHoles.courseRows(scorecard)
        strip = rows.map(\.hole)
        let scored = rows.filter { $0.score != nil }.map(\.hole)
        played = scored.isEmpty ? strip : scored
    }

    func canOpen(_ hole: Int) -> Bool { played.contains(hole) }

    /// One row per hole, in hole order, capped at the course width.
    static func courseRows(_ scorecard: [RoundDetailHole]) -> [RoundDetailHole] {
        var seen = Set<Int>()
        return scorecard
            .sorted { $0.hole < $1.hole }
            .filter { seen.insert($0.hole).inserted }
            .prefix(maximumHoles)
            .map { $0 }
    }
}

/// The round detail's scorecard as the shared nine cards read it: every hole of the course (up to
/// 18), each scored hole with its score. Unplayed holes stay as blank, unselectable cells.
struct RoundReviewScorecard: Equatable {
    let holes: [ScorecardHole]
    let scores: [Int: LiveHoleScore]
    let reviewHoles: RoundReviewHoles

    init(_ scorecard: [RoundDetailHole]) {
        reviewHoles = RoundReviewHoles(scorecard)
        var holes: [ScorecardHole] = []
        var scores: [Int: LiveHoleScore] = [:]
        for row in RoundReviewHoles.courseRows(scorecard) {
            let derivedPar = row.score.flatMap { score in row.toPar.map { score - $0 } }
            guard let par = row.par ?? derivedPar else { continue }
            holes.append(ScorecardHole(number: row.hole, par: par))
            if let score = row.score {
                scores[row.hole] = LiveHoleScore(
                    hole: row.hole, par: par, score: score,
                    putts: row.putts ?? 0, penalties: row.penalties ?? 0,
                    fairway: row.fairway, source: nil
                )
            }
        }
        self.holes = holes
        self.scores = scores
    }

    func canOpen(_ hole: Int) -> Bool { reviewHoles.canOpen(hole) }

    var strokes: Int { scores.values.reduce(0) { $0 + $1.score } }

    /// Cumulative to-par after each scored hole, in hole order (the trend line).
    var cumulativeToPar: [Int] {
        var running = 0
        return holes.compactMap { hole in
            guard let score = scores[hole.number] else { return nil }
            running += score.score - score.par
            return running
        }
    }

    func nineTotal<S: Sequence>(_ slice: S) -> Int? where S.Element == ScorecardHole {
        let recorded = slice.compactMap { scores[$0.number]?.score }
        return recorded.isEmpty ? nil : recorded.reduce(0, +)
    }
}
