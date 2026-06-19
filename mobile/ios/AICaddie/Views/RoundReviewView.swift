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
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("单场复盘")
        .task(id: roundRef) { await load() }
        .sheet(item: $shotMapHole) { item in
            NavigationStack {
                RoundHoleShotMapScreen(roundRef: roundRef, hole: item.hole, apiBaseURL: apiBaseURL, adminToken: adminToken)
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("完成") { shotMapHole = nil } } }
            }
        }
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
        VStack(spacing: 12) {
            if let detail, detail.found {
                headerCard(detail)
                if !detail.scorecard.isEmpty {
                    scoreStrip(detail.scorecard)
                    scorecardCard(detail.scorecard)
                }
                if !detail.phaseSummary.isEmpty {
                    phaseCard(detail.phaseSummary)
                }
                if !detail.missingData.isEmpty {
                    missingCard(detail.missingData)
                }
            } else if isLoading {
                ProgressView("载入这场…").padding(.top, 40)
            } else {
                emptyCard
            }
        }
        .padding(14)
    }

    // MARK: header

    private func headerCard(_ detail: RoundDetail) -> some View {
        let round = detail.round
        return VStack(alignment: .leading, spacing: 6) {
            Text(round?.courseName ?? fallbackCourseName ?? "这一场").font(.title3.weight(.bold))
            HStack(spacing: 10) {
                if let date = round?.date { Text(aiCaddieShortDate(date)).font(.caption).foregroundStyle(.secondary) }
                if let holes = round?.holesCompleted { Text("\(holes) 洞").font(.caption).foregroundStyle(.secondary) }
                if let par = round?.par { Text("Par \(par)").font(.caption).foregroundStyle(.secondary) }
                Spacer()
                if let score = round?.score {
                    Text("\(score)").font(.title2.monospacedDigit().weight(.heavy))
                    Text(toParText(round?.toPar))
                        .font(.caption.monospacedDigit())
                        .padding(.vertical, 3).padding(.horizontal, 8)
                        .background(AICaddieDesignTokens.scoreColor(toPar: round?.toPar).opacity(0.16))
                        .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: round?.toPar))
                        .clipShape(Capsule())
                }
            }
        }
        .liveCard()
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
                        .background(scoreColor(hole).opacity(0.18))
                        .foregroundStyle(scoreColor(hole))
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
            }
        }
        .liveCard()
    }

    // MARK: per-hole scorecard

    private func scorecardCard(_ holes: [RoundDetailHole]) -> some View {
        VStack(spacing: 0) {
            HStack {
                Text("点一洞看落点图 →").font(.caption2).foregroundStyle(LiveHoleStyle.green)
                Spacer()
            }
            .padding(.bottom, 4)
            HStack {
                Text("洞").frame(width: 32, alignment: .leading)
                Text("Par").frame(width: 40, alignment: .trailing)
                Text("成绩").frame(width: 48, alignment: .trailing)
                Text("推").frame(width: 32, alignment: .trailing)
                Text("果岭/球道").frame(maxWidth: .infinity, alignment: .trailing)
            }
            .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            .padding(.vertical, 6)
            Divider()
            ForEach(holes) { hole in
                Button {
                    onSelectHole(hole.hole)
                } label: {
                    HStack {
                        Text("\(hole.hole)").font(.subheadline.monospacedDigit().weight(.semibold)).frame(width: 32, alignment: .leading)
                        Text(hole.par.map(String.init) ?? "–").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary).frame(width: 40, alignment: .trailing)
                        Text(hole.score.map(String.init) ?? "–")
                            .font(.subheadline.monospacedDigit().weight(.bold))
                            .foregroundStyle(scoreColor(hole))
                            .frame(width: 48, alignment: .trailing)
                        Text(hole.putts.map(String.init) ?? "–").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary).frame(width: 32, alignment: .trailing)
                        Text(girFairwayText(hole)).font(.caption2).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .trailing)
                        Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                    }
                    .padding(.vertical, 7)
                    .contentShape(Rectangle())
                    .overlay(alignment: .bottom) { Divider() }
                }
                .buttonStyle(.plain)
                .foregroundStyle(.primary)
            }
            totalRow(holes)
        }
        .liveCard()
    }

    private func totalRow(_ holes: [RoundDetailHole]) -> some View {
        let totalScore = holes.compactMap(\.score).reduce(0, +)
        let totalPar = holes.compactMap(\.par).reduce(0, +)
        let totalPutts = holes.compactMap(\.putts).reduce(0, +)
        return HStack {
            Text("合计").font(.subheadline.weight(.bold)).frame(width: 36, alignment: .leading)
            Text("\(totalPar)").font(.subheadline.monospacedDigit().weight(.semibold)).foregroundStyle(.secondary).frame(width: 44, alignment: .trailing)
            Text("\(totalScore)").font(.subheadline.monospacedDigit().weight(.heavy)).frame(width: 52, alignment: .trailing)
            Text(totalPutts > 0 ? "\(totalPutts)" : "–").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary).frame(width: 36, alignment: .trailing)
            Text("").frame(maxWidth: .infinity)
        }
        .padding(.vertical, 8)
    }

    // MARK: phase summary

    private func phaseCard(_ phases: [RoundDetailPhase]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("各环节").font(.caption).foregroundStyle(.secondary)
            ForEach(phases) { phase in
                HStack {
                    Text(zhPhase(phase.phase)).font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(phase.primary ?? "—").font(.subheadline.monospacedDigit()).foregroundStyle(phase.state == "missing" ? .secondary : .primary)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .liveCard()
    }

    // MARK: missing-data (graceful, never blank)

    private func missingCard(_ rows: [RoundDetailMissing]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("数据缺口").font(.caption).foregroundStyle(.secondary)
            ForEach(rows) { row in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "info.circle").font(.caption).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(zhMissingLabel(row.label)).font(.subheadline)
                        if let reason = row.reason { Text(reason).font(.caption2).foregroundStyle(.secondary) }
                    }
                    Spacer(minLength: 0)
                }
            }
        }
        .liveCard()
    }

    private var emptyCard: some View {
        VStack(spacing: 8) {
            Image(systemName: "doc.text.magnifyingglass").font(.title).foregroundStyle(.secondary)
            Text(errorText ?? "这场没有可显示的记录").font(.subheadline).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 40)
        .liveCard()
    }

    // MARK: helpers

    private func scoreColor(_ hole: RoundDetailHole) -> Color {
        switch hole.className {
        case "eagle": return Color(red: 37 / 255, green: 99 / 255, blue: 235 / 255)
        case "birdie": return Color(red: 56 / 255, green: 152 / 255, blue: 236 / 255)
        case "par": return LiveHoleStyle.green
        case "bogey": return Color(red: 202 / 255, green: 138 / 255, blue: 4 / 255)
        case "double": return Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255)
        default: return AICaddieDesignTokens.scoreColor(toPar: hole.toPar)
        }
    }

    private func girFairwayText(_ hole: RoundDetailHole) -> String {
        var parts: [String] = []
        if let gir = hole.gir { parts.append(gir ? "果岭✓" : "果岭✗") }
        if let fairway = hole.fairway, !fairway.isEmpty { parts.append(zhFairway(fairway)) }
        return parts.isEmpty ? "—" : parts.joined(separator: " ")
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
