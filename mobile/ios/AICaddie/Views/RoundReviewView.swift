import Foundation
import SwiftUI

/// 单场复盘:点一场历史球局进来,先看本场核心指标，再从紧凑的前九/后九网格点进任一
/// 球洞查看落点。缺数据时优雅兜底(显示已有的 + 为什么缺),绝不空白白屏
/// (用户痛点:"复盘点进去没数据")。数据来自 /api/v2/history/rounds/{ref}。
public struct RoundReviewView: View {
    public let roundRef: String
    public let fallbackCourseName: String?
    public let apiBaseURL: URL?
    public let adminToken: String?

    @State private var detail: RoundDetail?
    @State private var isLoading = true
    @State private var errorText: String?
    @State private var shotMapHole: ShotMapHole?
    @StateObject private var shotMapRepository: RoundShotMapRepository

    public init(roundRef: String, fallbackCourseName: String? = nil, apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.roundRef = roundRef
        self.fallbackCourseName = fallbackCourseName
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        _shotMapRepository = StateObject(
            wrappedValue: RoundShotMapRepository(
                roundRef: roundRef,
                apiBaseURL: apiBaseURL,
                adminToken: adminToken
            )
        )
    }

    public var body: some View {
        Group {
            if isLoading && detail == nil {
                AICaddieLoadingView(text: "载入这场…")
            } else {
                ScrollView {
                    RoundReviewContent(
                        detail: detail, isLoading: isLoading, errorText: errorText,
                        fallbackCourseName: fallbackCourseName,
                        onSelectHole: { shotMapHole = ShotMapHole(hole: $0) },
                        onRetry: { Task { await load() } }
                    )
                }
            }
        }
        .background(HubStyle.grouped)
        .navigationTitle("单场复盘")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: roundRef) {
            await load()
        }
        .sheet(item: $shotMapHole) { item in
            NavigationStack {
                RoundShotMapPagerScreen(
                    roundRef: roundRef, holes: roundHoles, startHole: item.hole,
                    apiBaseURL: apiBaseURL, adminToken: adminToken,
                    onClose: { shotMapHole = nil },
                    mapRepository: shotMapRepository
                )
            }
        }
    }

    /// Page and prefetch only holes that were actually scored. A 9-of-18 round keeps blank cells in
    /// the backend scorecard for context; treating those blanks as played would fabricate maps and
    /// waste nine requests.
    private var roundHoles: [Int] {
        let scorecard = detail?.scorecard ?? []
        let played = scorecard.filter { $0.score != nil }.map(\.hole)
        return played.isEmpty ? scorecard.map(\.hole) : played
    }

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
            let fresh = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).fetchRoundDetail(roundRef: roundRef)
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
    var onSelectHole: (Int) -> Void = { _ in }
    var onRetry: () -> Void = {}

    private struct ReviewMetric: Identifiable {
        let id: String
        let title: String
        let value: String
        let detail: String?
        let icon: String
        var bad = false
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let detail, detail.found {
                summaryCard(detail)
                if !detail.scorecard.isEmpty {
                    scorecardGrid(detail.scorecard)
                }
                let metrics = reviewMetrics(detail)
                if !metrics.isEmpty {
                    metricGrid(metrics)
                }
                if !detail.missingData.isEmpty {
                    missingCard(detail.missingData)
                }
            } else if isLoading {
                ProgressView("载入这场…").frame(maxWidth: .infinity).padding(.top, 40)
            } else {
                emptyCard
            }
        }
        .padding(16)
    }

    // MARK: summary card (course · date/holes + score)

    private func summaryCard(_ detail: RoundDetail) -> some View {
        let round = detail.round
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                summaryTitle(round)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let score = round?.score {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(score)")
                            .font(.system(size: 34, weight: .heavy))
                            .monospacedDigit()
                            .foregroundStyle(.primary)
                        if let toPar = round?.toPar {
                            Text(toParText(toPar))
                                .font(.caption.monospacedDigit().weight(.bold))
                                .foregroundStyle(toPar > 0 ? HubStyle.warmBad : LiveHoleStyle.green)
                        }
                    }
                }
            }
        }
        .hubCard()
        // Keep the load-ready marker on the summary itself. Putting it on the outer
        // RoundReviewContent VStack causes SwiftUI to replace every descendant's identifier,
        // including the individually tappable `round-review-hole-N` rows.
        .accessibilityIdentifier("round-review-content-ready")
    }

    /// Keep compact course names and metadata on one baseline, while allowing a real long name to
    /// own its full line before the metadata flows below it. The score remains a stable trailing
    /// anchor in both layouts.
    private func summaryTitle(_ round: RoundDetailSummary?) -> some View {
        let courseName = round?.courseName ?? fallbackCourseName ?? "这一场"
        let subtitle = summarySubtitle(round)
        return ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(courseName)
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Text(subtitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize()
            }
            .fixedSize(horizontal: true, vertical: false)

            VStack(alignment: .leading, spacing: 3) {
                Text(courseName)
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(subtitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
    }

    /// tee/holes subtitle from what's present (date · 已打 N/M 洞 · Par); never fabricates a tee colour.
    private func summarySubtitle(_ round: RoundDetailSummary?) -> String {
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
        if let par = round?.par { parts.append("Par \(par)") }
        return parts.joined(separator: " · ")
    }

    // MARK: decision-first metrics

    /// Prefer recorded per-hole facts; older rounds fall back to Garmin's round-level phase totals.
    /// Missing coverage removes a tile instead of presenting a misleading 0%.
    private func reviewMetrics(_ detail: RoundDetail) -> [ReviewMetric] {
        let holes = detail.scorecard
        var metrics: [ReviewMetric] = []
        let girHoles = holes.filter { $0.gir != nil }
        let girHit = girHoles.filter { $0.gir == true }.count
        let fairwayHoles = holes.filter { ($0.fairway.map { !$0.isEmpty }) ?? false }
        let fairwayHit = fairwayHoles.filter { isFairwayHit($0.fairway) }.count
        if !fairwayHoles.isEmpty {
            metrics.append(ReviewMetric(
                id: "fairway", title: "球道命中", value: "\(percent(fairwayHit, fairwayHoles.count))%",
                detail: "\(fairwayHit)/\(fairwayHoles.count)", icon: "arrow.up.to.line.compact"
            ))
        } else if let tee = phaseMetrics("tee", in: detail),
                  let hit = tee.fairwaysHit,
                  let recorded = tee.fairwaysRecorded,
                  recorded > 0 {
            metrics.append(ReviewMetric(
                id: "fairway", title: "球道命中", value: "\(percent(hit, recorded))%",
                detail: "\(hit)/\(recorded)", icon: "arrow.up.to.line.compact"
            ))
        }
        if !girHoles.isEmpty {
            metrics.append(ReviewMetric(
                id: "gir", title: "GIR", value: "\(percent(girHit, girHoles.count))%",
                detail: "\(girHit)/\(girHoles.count)", icon: "flag.fill"
            ))
        } else if let approach = phaseMetrics("approach", in: detail),
                  let hit = approach.gir,
                  let recorded = approach.girRecorded,
                  recorded > 0 {
            metrics.append(ReviewMetric(
                id: "gir", title: "GIR", value: "\(percent(hit, recorded))%",
                detail: "\(hit)/\(recorded)", icon: "flag.fill"
            ))
        }
        let puttHoles = holes.compactMap(\.putts)
        if !puttHoles.isEmpty {
            let total = puttHoles.reduce(0, +)
            metrics.append(ReviewMetric(
                id: "putts", title: "推杆", value: "\(total)",
                detail: String(format: "%.1f/洞", Double(total) / Double(puttHoles.count)),
                icon: "circle.circle"
            ))
        } else if let total = phaseMetrics("putting", in: detail)?.totalPutts {
            metrics.append(ReviewMetric(
                id: "putts", title: "推杆", value: "\(total)", detail: nil,
                icon: "circle.circle"
            ))
        }
        let penaltyHoles = holes.compactMap(\.penalties)
        if !penaltyHoles.isEmpty {
            let total = penaltyHoles.reduce(0, +)
            metrics.append(ReviewMetric(
                id: "penalties", title: "罚杆", value: "\(total)",
                detail: total == 0 ? "无罚杆" : nil, icon: "exclamationmark.triangle.fill", bad: total > 0
            ))
        } else if let total = phaseMetrics("penalty / damage", in: detail)?.totalPenalties {
            metrics.append(ReviewMetric(
                id: "penalties", title: "罚杆", value: "\(total)",
                detail: total == 0 ? "无罚杆" : nil,
                icon: "exclamationmark.triangle.fill", bad: total > 0
            ))
        }
        return metrics
    }

    private func phaseMetrics(_ phase: String, in detail: RoundDetail) -> RoundDetailPhaseMetrics? {
        detail.phaseSummary.first { $0.phase.lowercased() == phase }?.metrics
    }

    private func metricGrid(_ metrics: [ReviewMetric]) -> some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 2), spacing: 10) {
            ForEach(metrics) { metric in
                VStack(alignment: .leading, spacing: 7) {
                    Label(metric.title, systemImage: metric.icon)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(metric.value)
                            .font(.title2.monospacedDigit().weight(.heavy))
                            .foregroundStyle(metric.bad ? HubStyle.warmBad : Color.primary)
                        if let detail = metric.detail {
                            Text(detail).font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(13)
                .frame(maxWidth: .infinity, minHeight: 78, alignment: .leading)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .shadow(color: Color.black.opacity(0.04), radius: 3, y: 1)
            }
        }
    }

    private func percent(_ hit: Int, _ total: Int) -> Int {
        guard total > 0 else { return 0 }
        return Int((Double(hit) / Double(total) * 100).rounded())
    }

    private func isFairwayHit(_ fairway: String?) -> Bool {
        switch (fairway ?? "").lowercased() {
        case "hit", "fairway", "center", "centre", "true", "1": return true
        default: return false
        }
    }

    // MARK: compact front/back-nine scorecard (every cell opens its shot map)

    private func scorecardGrid(_ holes: [RoundDetailHole]) -> some View {
        let played = holes.filter { $0.score != nil }
        let sorted = (played.isEmpty ? holes : played).sorted { $0.hole < $1.hole }
        let front = Array(sorted.prefix(9))
        let back = Array(sorted.dropFirst(9))
        return VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("逐洞成绩").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer()
                Text("点球洞看落点 →").font(.caption2.weight(.semibold)).foregroundStyle(LiveHoleStyle.green)
            }
            nineGrid(title: sorted.count > 9 ? "前九" : "本场", holes: front)
            if !back.isEmpty { nineGrid(title: "后九", holes: back) }
        }
        .hubCard()
    }

    private func nineGrid(title: String, holes: [RoundDetailHole]) -> some View {
        let scored = holes.filter { $0.score != nil }
        let totalScore = scored.compactMap(\.score).reduce(0, +)
        let totalPar = scored.compactMap(\.par).reduce(0, +)
        let relative = totalScore - totalPar
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.subheadline.weight(.bold))
                Spacer()
                if totalPar > 0 {
                    Text("\(totalScore) · Par \(totalPar) · \(toParText(relative))")
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(relative > 0 ? HubStyle.warmBad : Color.secondary)
                }
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 9), spacing: 4) {
                ForEach(holes) { hole in
                    Button { onSelectHole(hole.hole) } label: {
                        VStack(spacing: 2) {
                            Text("\(hole.hole)")
                                .font(.system(size: 9, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                            Text(hole.score.map(String.init) ?? "–")
                                .font(.system(size: 15, weight: .heavy, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(scoreColor(hole))
                        }
                        .frame(maxWidth: .infinity, minHeight: 43)
                        .background(scoreColor(hole).opacity(hole.score == nil ? 0.05 : 0.14))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(holeAccessibilityLabel(hole))
                    .accessibilityHint("打开这一洞的逐杆落点")
                    .accessibilityIdentifier("round-review-hole-\(hole.hole)")
                }
            }
        }
    }

    private func holeAccessibilityLabel(_ hole: RoundDetailHole) -> String {
        var parts = ["第 \(hole.hole) 洞"]
        if let par = hole.par { parts.append("标准杆 \(par)") }
        if let score = hole.score { parts.append("成绩 \(score)") }
        if let putts = hole.putts { parts.append("推 \(putts)") }
        if let penalties = hole.penalties { parts.append("罚 \(penalties)") }
        if let gir = hole.gir { parts.append(gir ? "果岭✓" : "果岭✗") }
        if let fairway = hole.fairway, !fairway.isEmpty { parts.append(zhFairway(fairway)) }
        return parts.joined(separator: "，")
    }

    // MARK: missing-data (graceful, never blank)

    private func missingCard(_ rows: [RoundDetailMissing]) -> some View {
        // De-engineered: the user sees one soft caveat, not the raw per-field gap list + reasons.
        // (`rows`/`zhMissingLabel` kept for the diagnostic build / future detail view.)
        _ = rows
        return HStack(alignment: .top, spacing: 8) {
            Image(systemName: "info.circle").font(.caption).foregroundStyle(.secondary)
            Text("部分球洞的数据有限,以下内容仅供参考。").font(.caption).foregroundStyle(.secondary)
            Spacer(minLength: 0)
        }
        .hubCard()
    }

    private var emptyCard: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass").font(.title).foregroundStyle(.secondary)
            Text(errorText ?? "这场没有可显示的记录").font(.subheadline).foregroundStyle(.secondary)
            if errorText != nil {
                Button("重新载入", action: onRetry)
                    .buttonStyle(.borderedProminent)
                    .tint(LiveHoleStyle.green)
                    .accessibilityIdentifier("round-review-retry")
            }
        }
        .frame(maxWidth: .infinity).padding(.vertical, 40)
        .hubCard()
    }

    // MARK: helpers

    private func scoreColor(_ hole: RoundDetailHole) -> Color {
        switch hole.className {
        case "eagle": return HubStyle.eagle
        case "birdie": return HubStyle.birdie
        case "par": return HubStyle.par
        case "bogey": return HubStyle.bogey
        case "double": return HubStyle.double
        default: return AICaddieDesignTokens.scoreColor(toPar: hole.toPar)
        }
    }

    private func zhFairway(_ value: String) -> String {
        switch value.lowercased() {
        case "hit", "fairway", "center", "centre", "true", "1": return "球道✓"
        case "left": return "偏左"
        case "right": return "偏右"
        case "miss", "false", "0": return "球道✗"
        default: return value
        }
    }

    private func zhMissingLabel(_ label: String) -> String {
        switch label.lowercased() {
        case "scorecard": return "无记分卡"
        case "hole scores": return "部分洞缺成绩"
        case "shot rows": return "无逐杆数据"
        case "putts": return "无推杆数"
        case "round par": return "无标准杆"
        default: return label
        }
    }

    private func toParText(_ toPar: Int?) -> String {
        guard let toPar, toPar != 0 else { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}
