import Foundation

/// B5 (README §9, `stats.html`): the pure facts behind 成绩 / 表现分析 / 成绩分布, kept out of the
/// views so they can be tested against fixture payloads.
enum ResultsPresentation {
    // MARK: 成绩 · 近 20 场走势

    struct TrendRow: Equatable, Identifiable {
        var id: Int { index }
        /// 0 = the oldest of the shown rounds.
        let index: Int
        let roundId: String?
        let date: String
        let score: Int
        /// Average of this round and up to nine before it, over the whole 18-hole series (so the
        /// first shown dots are not averaged over fewer rounds than exist).
        let rollingAverage: Double
    }

    static let trendRoundCount = 20
    static let rollingWindow = 10

    /// The newest `trendRoundCount` scored 18-hole rounds, oldest first, each with its 10-round
    /// rolling average. `points` is the server's `trend.points` (oldest -> newest).
    static func trendRows(_ points: [StatsTrendPoint]) -> [TrendRow] {
        let scored = points.compactMap { point -> (StatsTrendPoint, Int)? in
            guard let score = point.score else { return nil }
            return (point, score)
        }
        let start = max(0, scored.count - trendRoundCount)
        return (start..<scored.count).map { position in
            let window = scored[max(0, position - rollingWindow + 1)...position].map { $0.1 }
            return TrendRow(
                index: position - start,
                roundId: scored[position].0.roundId,
                date: scored[position].0.date,
                score: scored[position].1,
                rollingAverage: Double(window.reduce(0, +)) / Double(window.count)
            )
        }
    }

    // MARK: 成绩分布 · 每 5 杆一根柱

    struct ScoreBin: Equatable, Identifiable {
        var id: Int { lower }
        let lower: Int
        let count: Int
        let roundIds: [String]
        /// The most common bin (ties: the lower scores), drawn solid.
        let isMostCommon: Bool
        var label: String { "\(lower)–\(lower + 4)" }
    }

    /// Every 5-stroke bin from the best to the worst 18-hole score, empty bins included so the shape
    /// reads truthfully.
    static func scoreBins(_ points: [StatsTrendPoint]) -> [ScoreBin] {
        let scored = points.compactMap { point in point.score.map { (point.roundId, $0) } }
        guard let best = scored.map({ $0.1 }).min(), let worst = scored.map({ $0.1 }).max() else { return [] }
        let first = best / 5 * 5
        let last = worst / 5 * 5
        let bins = stride(from: first, through: last, by: 5).map { lower in
            scored.filter { $0.1 >= lower && $0.1 < lower + 5 }
        }
        let top = bins.map(\.count).max() ?? 0
        let topIndex = bins.firstIndex { $0.count == top }
        return bins.enumerated().map { index, rows in
            ScoreBin(
                lower: first + index * 5,
                count: rows.count,
                roundIds: rows.compactMap { $0.0 },
                isMostCommon: index == topIndex && top > 0
            )
        }
    }

    // MARK: 成绩分布 · 每一洞的结果

    enum OutcomeTone: Equatable { case eagle, birdie, par, bogey, double }

    struct OutcomeSegment: Equatable, Identifiable {
        var id: String { label }
        let label: String
        let pct: Double
        let tone: OutcomeTone
    }

    /// The server's 7 spread buckets folded into the five the screen names (double, triple and +4
    /// are one 双柏忌+ segment). Shares are of every recorded hole.
    static func outcomeSegments(_ distribution: [StatsOutcomeBucket]) -> [OutcomeSegment] {
        func share(_ keys: Set<String>) -> Double {
            distribution.filter { keys.contains($0.key) }.reduce(0) { $0 + ($1.pct ?? 0) }
        }
        let rows: [OutcomeSegment] = [
            OutcomeSegment(label: "老鹰", pct: share(["eagleOrBetter"]), tone: .eagle),
            OutcomeSegment(label: "小鸟", pct: share(["birdie"]), tone: .birdie),
            OutcomeSegment(label: "标准杆", pct: share(["par"]), tone: .par),
            OutcomeSegment(label: "柏忌", pct: share(["bogey"]), tone: .bogey),
            OutcomeSegment(label: "双柏忌+", pct: share(["double", "triple", "quadPlus", "doubleOrWorse"]), tone: .double),
        ]
        return rows.contains { $0.pct > 0 } ? rows : []
    }

    // MARK: 表现分析

    enum SegmentTone: Equatable { case good, warn, neutral }

    struct Segment: Equatable, Identifiable {
        var id: String { label }
        let label: String
        let pct: Double
        let tone: SegmentTone
    }

    struct Delta: Equatable {
        let text: String
        /// nil = unchanged.
        let isBetter: Bool?
    }

    struct PhaseRow: Equatable, Identifiable {
        var id: String { title }
        let title: String
        let value: String
        /// Sticks to the number ("%"); empty for 推 / 洞.
        let unit: String
        let caption: String
        let delta: Delta?
        let segments: [Segment]
        let note: String?
    }

    struct Focus: Equatable {
        let title: String
        let detail: String
    }

    struct Analysis: Equatable {
        let focus: Focus?
        let rows: [PhaseRow]
    }

    /// The four phases written one way (README §9): a big number, how it compares with the
    /// baseline window, and one split bar whose good segment is green and whose most common miss is
    /// yellow. A phase without recorded facts is left out rather than shown as 0%.
    static func analysis(_ stats: MobileStats, baseline: MobileStats? = nil) -> Analysis {
        let scoring = stats.scoring
        let base = baseline?.scoring
        var rows: [PhaseRow] = []
        var misses: [(pct: Double, focus: Focus)] = []

        if let tee = scoring?.teeDirection, let recorded = tee.recorded, recorded > 0 {
            let left = pct(tee.left, recorded), hit = pct(tee.hit, recorded), right = pct(tee.right, recorded)
            let warnLeft = left >= right && left > 0
            let warnRight = right > left
            rows.append(PhaseRow(
                title: "开球", value: whole(hit), unit: "%", caption: "上球道",
                delta: pointsDelta(hit, base?.teeDirection.flatMap(teeHitPct)),
                segments: [
                    Segment(label: "偏左", pct: left, tone: warnLeft ? .warn : .neutral),
                    Segment(label: "球道", pct: hit, tone: .good),
                    Segment(label: "偏右", pct: right, tone: warnRight ? .warn : .neutral),
                ],
                note: nil
            ))
            if left > 0 { misses.append((left, Focus(title: "开球偏左", detail: "\(whole(left))% 的开球偏左，是最常见的失误"))) }
            if right > 0 { misses.append((right, Focus(title: "开球偏右", detail: "\(whole(right))% 的开球偏右，是最常见的失误"))) }
        }

        if let approach = scoring?.approachMiss, let recorded = approach.recorded, recorded > 0 {
            let gir = pct(approach.gir, recorded)
            let parts: [(String, Double, String, String)] = [
                ("短", pct(approach.short, recorded), "攻果岭偏短", "落在果岭前面"),
                ("长", pct(approach.long, recorded), "攻果岭偏长", "落过果岭"),
                ("左", pct(approach.left, recorded), "攻果岭偏左", "落在果岭左边"),
                ("右", pct(approach.right, recorded), "攻果岭偏右", "落在果岭右边"),
            ]
            let worst = parts.filter { $0.1 > 0 }.max { $0.1 < $1.1 }
            rows.append(PhaseRow(
                title: "攻果岭", value: whole(gir), unit: "%", caption: "GIR 上果岭",
                delta: pointsDelta(gir, base?.approachMiss.flatMap(approachGirPct)),
                segments: [Segment(label: "上果岭", pct: gir, tone: .good)] + parts.map {
                    Segment(label: $0.0, pct: $0.1, tone: $0.0 == worst?.0 ? .warn : .neutral)
                },
                note: nil
            ))
            for part in parts where part.1 > 0 {
                misses.append((part.1, Focus(title: part.2, detail: "\(whole(part.1))% 的攻果岭\(part.3)，是最常见的失误")))
            }
        }

        if let scrambling = scoring?.scrambling, let chances = scrambling.chances, chances > 0,
           let saved = scrambling.pct {
            let shots = scoring?.phaseStats.first { $0.phase.caseInsensitiveCompare("Short Game") == .orderedSame }?
                .roughOrBunkerShots
            let rounds = stats.summary?.totalRounds ?? 0
            rows.append(PhaseRow(
                title: "果岭周边", value: whole(saved), unit: "%", caption: "救球成功",
                delta: pointsDelta(saved, base?.scrambling?.pct),
                segments: [
                    Segment(label: "救回", pct: saved, tone: .good),
                    Segment(label: "没救回", pct: max(0, 100 - saved), tone: .neutral),
                ],
                note: shots.flatMap { shots in
                    rounds > 0 ? String(format: "每场从长草、沙坑起杆 %.1f 次", Double(shots) / Double(rounds)) : nil
                }
            ))
        }

        if let putting = scoring?.putting, let holes = putting.holesWithPutts, holes > 0,
           let average = putting.averagePutts {
            var segments: [Segment] = []
            if let zero = putting.zeroPuttPct, zero > 0 {
                segments.append(Segment(label: "零推", pct: zero, tone: .good))
            }
            segments += [
                Segment(label: "一推", pct: putting.onePuttPct ?? 0, tone: .good),
                Segment(label: "两推", pct: putting.twoPuttPct ?? 0, tone: .neutral),
                Segment(label: "三推+", pct: putting.threePlusPuttPct ?? 0, tone: .warn),
            ]
            rows.append(PhaseRow(
                title: "推杆", value: String(format: "%.2f", average), unit: "", caption: "推 / 洞",
                delta: base?.putting?.averagePutts.map { previous -> Delta in
                    let change = (average - previous) * 100
                    guard abs(change.rounded()) >= 1 else { return Delta(text: "和之前持平", isBetter: nil) }
                    return Delta(text: "\(change > 0 ? "↑" : "↓") \(String(format: "%.2f", abs(average - previous)))",
                                 isBetter: change < 0)
                },
                segments: segments,
                note: nil
            ))
            if let three = putting.threePlusPuttPct, three > 0 {
                misses.append((three, Focus(title: "三推偏多", detail: "\(whole(three))% 的洞三推或更多")))
            }
        }

        let focus = misses.max { $0.pct < $1.pct }?.focus
        return Analysis(focus: focus, rows: rows)
    }

    // MARK: helpers

    static func pct(_ count: Int?, _ total: Int) -> Double {
        guard total > 0 else { return 0 }
        return Double(count ?? 0) / Double(total) * 100
    }

    static func whole(_ value: Double) -> String { String(Int(value.rounded())) }

    private static func teeHitPct(_ tee: StatsTeeDirection) -> Double? {
        guard let recorded = tee.recorded, recorded > 0 else { return nil }
        return pct(tee.hit, recorded)
    }

    private static func approachGirPct(_ approach: StatsApproachMiss) -> Double? {
        guard let recorded = approach.recorded, recorded > 0 else { return nil }
        return pct(approach.gir, recorded)
    }

    /// Percentage-point change against the baseline window; higher is better.
    private static func pointsDelta(_ current: Double, _ previous: Double?) -> Delta? {
        guard let previous else { return nil }
        let change = (current - previous).rounded()
        guard change != 0 else { return Delta(text: "和之前持平", isBetter: nil) }
        return Delta(text: "\(change > 0 ? "↑" : "↓") \(Int(abs(change)))%", isBetter: change > 0)
    }
}

// MARK: - 表现分析 loading

/// The 表现分析 page's state, committed atomically (Codex review of #364): the selected window,
/// that window's stats (which carry their own previous period) and loading / failure always
/// describe the same window. A response is applied only to the request generation that is still
/// current, so a slow earlier request can never overwrite a newer selection or a refresh, and a
/// failed request never leaves the previous window's numbers under the new window's label.
struct AnalysisLoadState: Equatable {
    enum Phase: Equatable {
        case loading
        case loaded(MobileStats)
        case failed(String)
    }

    struct Request: Equatable {
        let window: String
        let generation: Int
    }

    private(set) var window: String
    private(set) var phase: Phase = .loading
    private(set) var generation = 0

    init(window: String = "last20") {
        self.window = window
    }

    /// The request that loads the current window (the first appearance).
    var currentRequest: Request { Request(window: window, generation: generation) }

    /// Choose a window: its data is unknown until its own request answers.
    mutating func select(_ newWindow: String) -> Request {
        window = newWindow
        return restart()
    }

    /// New data arrived (Garmin refresh): the current window and its comparison are both stale.
    mutating func refresh() -> Request { restart() }

    /// Apply a response; `stats == nil` is a failure. Returns false when the request is no longer
    /// the current one (it is ignored).
    @discardableResult
    mutating func complete(_ request: Request, stats: MobileStats?) -> Bool {
        guard request.generation == generation, request.window == window else { return false }
        phase = stats.map(Phase.loaded) ?? .failed("统计暂时取不到(网络或数据)")
        return true
    }

    private mutating func restart() -> Request {
        generation += 1
        phase = .loading
        return currentRequest
    }

    struct WindowOption: Identifiable, Equatable {
        /// The `/stats/mobile` window key.
        let id: String
        let title: String
        /// What ↑ / ↓ compare against (nil for 全部).
        let comparison: String?
    }

    static let windows = [
        WindowOption(id: "last10", title: "10 场", comparison: "和前 10 场比"),
        WindowOption(id: "last20", title: "20 场", comparison: "和前 20 场比"),
        WindowOption(id: "12m", title: "近一年", comparison: "和前一年比"),
        WindowOption(id: "all", title: "全部", comparison: nil),
    ]

    static func comparisonLabel(_ window: String) -> String? {
        windows.first { $0.id == window }?.comparison
    }

    /// The line under the phases: what ↑ / ↓ compare against, or why there is no comparison. A
    /// short previous count sample is named as such, never labelled as the full 前 10 / 20 场.
    static func comparisonNote(window: String, previous: MobileStatsPrevious?) -> String? {
        guard let label = comparisonLabel(window) else { return nil }
        guard let previous, let count = previous.roundCount, count > 0 else { return "前一段没有球局，暂不比较" }
        if previous.scoring == nil {
            if let required = previous.requiredRounds, count < required {
                return "前 \(required) 场只有 \(count) 场，暂不比较"
            }
            return "前一段没有球局，暂不比较"
        }
        return "↑ ↓ \(label)"
    }
}

extension ResultsPresentation {
    /// The previous comparable period as a baseline for `analysis` (nil when the response has none).
    static func baseline(_ stats: MobileStats) -> MobileStats? {
        stats.previous?.scoring.map { MobileStats(scoring: $0) }
    }

    // MARK: 成绩 landing state

    enum LandingPhase: Equatable {
        /// Nothing cached and the first requests have not answered: never "暂无成绩".
        case loading
        /// Both requests answered and there is not one round.
        case empty
        /// Nothing could be loaded.
        case failed(String)
        /// Something to show; `notice` names a section that failed, `refreshing` a cached page
        /// being refreshed.
        case content(notice: String?, refreshing: Bool)
    }

    static func landingPhase(stats: MobileStats?, archive: HistoryRoundsArchive?, isLoading: Bool,
                             errorText: String?) -> LandingPhase {
        guard stats != nil || archive != nil else {
            if isLoading { return .loading }
            return errorText.map(LandingPhase.failed) ?? .empty
        }
        let rounds = max(stats?.summary?.totalRounds ?? 0, archive?.total ?? 0,
                         archive?.groups.reduce(0) { $0 + $1.rounds.count } ?? 0)
        if rounds == 0, !isLoading, errorText == nil, stats != nil, archive != nil { return .empty }
        return .content(notice: errorText, refreshing: isLoading)
    }

    // MARK: 成绩分布 · 按 Par

    struct ParRowText: Equatable {
        let title: String
        /// "+0.62"; "—" when the average is missing.
        let overPar: String
        /// "288 洞 · 保帕率 48%", with each missing part left out.
        let detail: String
        /// 0…1 of the bar; nil draws no bar.
        let fraction: Double?
    }

    /// One Par row; a missing field is shown as missing, never as 0 (IMPLEMENTATION_PLAN B5).
    static func parRow(_ row: StatsByPar, maxOver: Double) -> ParRowText {
        let parts = [
            row.holeCount.map { "\($0) 洞" },
            row.parOrBetterPct.map { "保帕率 \(Int($0.rounded()))%" },
        ].compactMap { $0 }
        return ParRowText(
            title: "Par \(row.par.map(String.init) ?? "—")",
            overPar: row.averageToPar.map { String(format: "%+.2f", $0) } ?? "—",
            detail: parts.joined(separator: " · "),
            fraction: row.averageToPar.map { max(0, $0) / max(maxOver * 1.25, 0.01) }
        )
    }
}

// MARK: - 成绩 landing loading

/// The 成绩 page's two sections — stats and the round archive — loaded together but published
/// independently (Codex review of #364). Each `begin()` starts a new generation; only that
/// generation's answers commit, so an older request can neither overwrite a newer one nor clear
/// its loading state. Cached values stay on screen while a refresh is in flight, which is the
/// real `refreshing` state.
struct ResultsLandingLoad: Equatable {
    enum Section: String, Equatable {
        case stats = "生涯与趋势"
        case archive = "球局档案"
    }

    private(set) var stats: MobileStats?
    private(set) var archive: HistoryRoundsArchive?
    private(set) var generation = 0
    private(set) var statsPending = false
    private(set) var archivePending = false
    private(set) var failed: [Section] = []

    init(stats: MobileStats? = nil, archive: HistoryRoundsArchive? = nil) {
        self.stats = stats
        self.archive = archive
    }

    var isLoading: Bool { statsPending || archivePending }

    var errorText: String? {
        let names = [Section.stats, .archive].filter { failed.contains($0) }.map(\.rawValue)
        return names.isEmpty ? nil : "\(names.joined(separator: "、"))暂时取不到"
    }

    var phase: ResultsPresentation.LandingPhase {
        ResultsPresentation.landingPhase(stats: stats, archive: archive, isLoading: isLoading, errorText: errorText)
    }

    /// Show cached sections before the first answer (never replacing anything already loaded).
    mutating func seed(stats cachedStats: MobileStats?, archive cachedArchive: HistoryRoundsArchive?) {
        if stats == nil { stats = cachedStats }
        if archive == nil { archive = cachedArchive }
    }

    /// Start loading both sections; returns the generation their answers must carry.
    mutating func begin() -> Int {
        generation += 1
        statsPending = true
        archivePending = true
        failed = []
        return generation
    }

    /// `value == nil` is a failure; a failure keeps the cached section and names it.
    @discardableResult
    mutating func completeStats(_ requestGeneration: Int, _ value: MobileStats?) -> Bool {
        guard requestGeneration == generation, statsPending else { return false }
        statsPending = false
        if let value { stats = value } else { failed.append(.stats) }
        return true
    }

    @discardableResult
    mutating func completeArchive(_ requestGeneration: Int, _ value: HistoryRoundsArchive?) -> Bool {
        guard requestGeneration == generation, archivePending else { return false }
        archivePending = false
        if let value { archive = value } else { failed.append(.archive) }
        return true
    }

    /// The page went away mid-request: stop showing it as loading (nothing is committed).
    mutating func cancel(_ requestGeneration: Int) {
        guard requestGeneration == generation else { return }
        statsPending = false
        archivePending = false
    }
}
