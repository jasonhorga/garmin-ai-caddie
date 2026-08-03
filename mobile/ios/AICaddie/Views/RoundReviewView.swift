import Foundation
import SwiftUI

/// 单场复盘:点一场历史球局进来,逐洞看「我这场怎么打的」—— 成绩条 + 逐洞记分卡(杆/推/
/// 果岭/球道)+ 各环节小结。缺数据时优雅兜底(显示已有的 + 为什么缺),绝不空白白屏
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

    public init(roundRef: String, fallbackCourseName: String? = nil, apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.roundRef = roundRef
        self.fallbackCourseName = fallbackCourseName
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
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
                        onSelectHole: { shotMapHole = ShotMapHole(hole: $0) }
                    )
                }
            }
        }
        .background(HubStyle.grouped)
        .navigationTitle("单场复盘")
        .navigationBarTitleDisplayMode(.large)
        .task(id: roundRef) { await load() }
        .sheet(item: $shotMapHole) { item in
            NavigationStack {
                RoundShotMapPagerScreen(
                    roundRef: roundRef, holes: roundHoles, startHole: item.hole,
                    apiBaseURL: apiBaseURL, adminToken: adminToken
                )
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("关闭") { shotMapHole = nil }
                    }
                }
            }
        }
    }

    /// The holes to page through in the shot-map (this round's scorecard holes; fallback 1–18).
    private var roundHoles: [Int] {
        let holes = (detail?.scorecard ?? []).map(\.hole)
        return holes.isEmpty ? Array(1...18) : holes
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
        isLoading = true
        errorText = nil
        do {
            detail = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).fetchRoundDetail(roundRef: roundRef)
        } catch {
            errorText = "这场暂时取不到(网络或数据)"
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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let detail, detail.found {
                summaryCard(detail)
                if !detail.scorecard.isEmpty {
                    scoreStrip(detail.scorecard)
                    HubSectionLabel("逐洞").padding(.top, 6)
                    scorecardCard(detail.scorecard)
                }
                if !detail.phaseSummary.isEmpty {
                    HubSectionLabel("各环节").padding(.top, 6)
                    phaseCard(detail.phaseSummary)
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
        .accessibilityIdentifier("round-review-content-ready")
    }

    // MARK: summary card (course · tee/holes + big score + derived stat row)

    private func summaryCard(_ detail: RoundDetail) -> some View {
        let round = detail.round
        return VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(round?.courseName ?? fallbackCourseName ?? "这一场")
                    .font(.title3.weight(.bold)).foregroundStyle(.primary)
                Text(summarySubtitle(round)).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer(minLength: 8)
                if let score = round?.score {
                    Text("\(score)").font(.system(size: 32, weight: .heavy)).monospacedDigit().foregroundStyle(.primary)
                }
            }
            summaryStatRow(detail)
        }
        .hubCard()
    }

    /// tee/holes subtitle from what's present (date · 已打 N/M 洞 · Par); never fabricates a tee colour.
    private func summarySubtitle(_ round: RoundDetailSummary?) -> String {
        var parts: [String] = []
        if let course = round?.courseHoles, course > 0, course != (round?.holesScored ?? round?.holesCompleted) {
            let played = round?.holesScored ?? round?.holesCompleted ?? 0
            parts.append("已打 \(played)/\(course) 洞")
        } else if let holes = round?.holesCompleted {
            parts.append("\(holes) 洞")
        }
        if let par = round?.par { parts.append("Par \(par)") }
        return parts.joined(separator: " · ")
    }

    /// 相对标准 / GIR / 推杆 / 球道 — derived from the per-hole scorecard already on screen; each cell
    /// only appears when the underlying data exists (no fabricated 「—」noise).
    private func summaryStatRow(_ detail: RoundDetail) -> some View {
        let holes = detail.scorecard
        let toPar = detail.round?.toPar
        let putts = holes.compactMap(\.putts).reduce(0, +)
        let girHoles = holes.filter { $0.gir != nil }
        let girHit = girHoles.filter { $0.gir == true }.count
        let fairwayHoles = holes.filter { ($0.fairway.map { !$0.isEmpty }) ?? false }
        let fairwayHit = fairwayHoles.filter { isFairwayHit($0.fairway) }.count
        return HStack(alignment: .top, spacing: 20) {
            if let toPar {
                summaryStat("相对标准", toParText(toPar), bad: toPar > 0)
            }
            if !girHoles.isEmpty {
                summaryStat("GIR", "\(percent(girHit, girHoles.count))%")
            }
            if putts > 0 {
                summaryStat("推杆", "\(putts)")
            }
            if !fairwayHoles.isEmpty {
                summaryStat("球道", "\(percent(fairwayHit, fairwayHoles.count))%")
            }
            Spacer(minLength: 0)
        }
    }

    private func summaryStat(_ key: String, _ value: String, bad: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(key).font(.caption2.weight(.bold)).foregroundStyle(.secondary)
            Text(value)
                .font(.callout.weight(.heavy)).monospacedDigit()
                .foregroundStyle(bad ? HubStyle.warmBad : Color.primary)
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

    // MARK: score strip (one colored cell per hole)

    private func scoreStrip(_ holes: [RoundDetailHole]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("成绩条").font(.caption).foregroundStyle(.secondary)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 9), spacing: 4) {
                ForEach(holes) { hole in
                    Text(hole.score.map(String.init) ?? "–")
                        .font(.caption2.monospacedDigit().weight(.bold))
                        .frame(maxWidth: .infinity, minHeight: 26)
                        .background(scoreColor(hole).opacity(0.16))
                        .foregroundStyle(scoreColor(hole))
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
            }
        }
        .hubCard()
    }

    // MARK: per-hole scorecard (tap a hole → 落点图), shape-coded score chip per row

    private func scorecardCard(_ holes: [RoundDetailHole]) -> some View {
        VStack(spacing: 0) {
            HStack {
                Text("点一洞看落点图 →").font(.caption2).foregroundStyle(LiveHoleStyle.green)
                Spacer()
            }
            .padding(.bottom, 6)
            ForEach(holes) { hole in
                Button {
                    onSelectHole(hole.hole)
                } label: {
                    HStack(spacing: 12) {
                        Text("\(hole.hole)")
                            .font(.subheadline.monospacedDigit().weight(.bold))
                            .foregroundStyle(.secondary)
                            .frame(width: 22, alignment: .leading)
                        Text(rowMeta(hole)).font(.subheadline).foregroundStyle(.secondary)
                        Spacer(minLength: 8)
                        Text(hole.par.map { "P\($0)" } ?? "")
                            .font(.caption.weight(.semibold)).monospacedDigit()
                            .foregroundStyle(.secondary)
                        ScoreChip(score: hole.score, toPar: holeToPar(hole))
                    }
                    .padding(.vertical, 8)
                    .contentShape(Rectangle())
                    .overlay(alignment: .bottom) { Divider() }
                }
                .buttonStyle(.plain)
                .foregroundStyle(.primary)
                .accessibilityIdentifier("round-review-hole-\(hole.hole)")
            }
            totalRow(holes)
        }
        .hubCard()
    }

    private func totalRow(_ holes: [RoundDetailHole]) -> some View {
        let totalScore = holes.compactMap(\.score).reduce(0, +)
        let totalPar = holes.compactMap(\.par).reduce(0, +)
        let totalPutts = holes.compactMap(\.putts).reduce(0, +)
        let recordedPenalties = holes.compactMap(\.penalties)
        return HStack(spacing: 12) {
            Text("合计").font(.subheadline.weight(.bold)).frame(width: 40, alignment: .leading)
            if totalPutts > 0 {
                Text("推 \(totalPutts)").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            }
            if !recordedPenalties.isEmpty {
                Text("罚 \(recordedPenalties.reduce(0, +))").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Text("Par \(totalPar)").font(.caption.weight(.semibold)).monospacedDigit().foregroundStyle(.secondary)
            Text("\(totalScore)").font(.title3.monospacedDigit().weight(.heavy)).foregroundStyle(.primary)
        }
        .padding(.top, 10)
    }

    /// A compact per-hole metadata line (推 · 罚 · 果岭 · 球道) built only from present fields.
    private func rowMeta(_ hole: RoundDetailHole) -> String {
        var parts: [String] = []
        if let putts = hole.putts { parts.append("推 \(putts)") }
        if let penalties = hole.penalties { parts.append("罚 \(penalties)") }
        if let gir = hole.gir { parts.append(gir ? "果岭✓" : "果岭✗") }
        if let fairway = hole.fairway, !fairway.isEmpty { parts.append(zhFairway(fairway)) }
        return parts.isEmpty ? "—" : parts.joined(separator: " · ")
    }

    private func holeToPar(_ hole: RoundDetailHole) -> Int? {
        if let toPar = hole.toPar { return toPar }
        if let score = hole.score, let par = hole.par { return score - par }
        return nil
    }

    // MARK: phase summary

    private func phaseCard(_ phases: [RoundDetailPhase]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(phases.enumerated()), id: \.element.id) { index, phase in
                HStack {
                    Text(zhPhase(phase.phase)).font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(phase.primary ?? "—").font(.subheadline.monospacedDigit()).foregroundStyle(phase.state == "missing" ? .secondary : .primary)
                }
                .padding(.vertical, 9)
                if index < phases.count - 1 { Divider() }
            }
        }
        .hubCard()
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
        VStack(spacing: 8) {
            Image(systemName: "doc.text.magnifyingglass").font(.title).foregroundStyle(.secondary)
            Text(errorText ?? "这场没有可显示的记录").font(.subheadline).foregroundStyle(.secondary)
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

    private func zhPhase(_ phase: String) -> String {
        switch phase.lowercased() {
        case "tee": return "开球"
        case "approach": return "攻果岭"
        case "short game": return "短杆"
        case "putting": return "推杆"
        case "penalty / damage": return "失误/罚杆"
        default: return phase
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
