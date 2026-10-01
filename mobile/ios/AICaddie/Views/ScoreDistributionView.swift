import SwiftUI

/// 成绩分布 (README §9, `stats.html` 5): every complete 18-hole round in 5-stroke bins (the most
/// common bin solid; a bar opens its rounds), the result of every recorded hole, and Par 3 / 4 / 5
/// (average over par and par-save rate). It reads the 成绩 page's all-time stats.
struct ScoreDistributionView: View {
    let stats: MobileStats?
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil
    var initialArchive: HistoryRoundsArchive? = nil

    var body: some View {
        ScrollView {
            ScoreDistributionContent(stats: stats, apiBaseURL: apiBaseURL, adminToken: adminToken,
                                     initialArchive: initialArchive)
        }
        .background(HubStyle.grouped)
        .navigationTitle("成绩分布")
    }
}

struct ScoreDistributionContent: View {
    let stats: MobileStats?
    var apiBaseURL: URL? = nil
    var adminToken: String? = nil
    var initialArchive: HistoryRoundsArchive? = nil

    var body: some View {
        let bins = ResultsPresentation.scoreBins(stats?.trend?.points ?? [])
        let outcomes = ResultsPresentation.outcomeSegments(stats?.scoring?.outcomeDistribution ?? [])
        let byPar = (stats?.scoring?.byPar ?? [])
            .filter { (3...5).contains($0.par ?? 0) }
            .sorted { ($0.par ?? 0) < ($1.par ?? 0) }
        VStack(alignment: .leading, spacing: 14) {
            if bins.isEmpty && outcomes.isEmpty && byPar.isEmpty {
                Text("还没有完整 18 洞的成绩")
                    .font(.subheadline).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity).padding(.vertical, 40).hubCard()
            }
            if !bins.isEmpty {
                Text("全部 \(bins.reduce(0) { $0 + $1.count }) 场完整 18 洞")
                    .font(.footnote).foregroundStyle(.secondary).monospacedDigit()
                histogram(bins)
            }
            if !outcomes.isEmpty {
                HubSectionLabel("每一洞的结果")
                outcomeBar(outcomes)
            }
            if !byPar.isEmpty {
                HubSectionLabel("按 Par")
                VStack(spacing: 8) {
                    ForEach(byPar) { row in parRow(row, maxOver: byPar.compactMap(\.averageToPar).max() ?? 1) }
                }
            }
        }
        .padding(16)
    }

    // MARK: 每 5 杆一根柱

    private func histogram(_ bins: [ResultsPresentation.ScoreBin]) -> some View {
        let top = max(1, bins.map(\.count).max() ?? 1)
        return HStack(alignment: .bottom, spacing: 4) {
            ForEach(bins) { bin in
                NavigationLink {
                    ResultsArchiveView(apiBaseURL: apiBaseURL, adminToken: adminToken,
                                       initialArchive: initialArchive, roundIds: bin.roundIds,
                                       title: "\(bin.label) 杆")
                } label: {
                    VStack(spacing: 4) {
                        Text("\(bin.count)").font(.caption.weight(.bold)).monospacedDigit()
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .fill(LiveHoleStyle.green.opacity(bin.isMostCommon ? 1 : 0.4))
                            .frame(height: max(bin.count > 0 ? 4 : 1, 104 * CGFloat(bin.count) / CGFloat(top)))
                        Text(bin.label).font(.system(size: 9.5)).foregroundStyle(.secondary)
                            .lineLimit(1).minimumScaleFactor(0.7)
                    }
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(.primary)
                .disabled(bin.count == 0)
                .accessibilityLabel("\(bin.label) 杆 \(bin.count) 场")
                .accessibilityIdentifier("distribution-bin-\(bin.lower)")
            }
        }
        .frame(height: 150, alignment: .bottom)
        .hubCard(padding: 12)
    }

    // MARK: 每一洞的结果

    private func outcomeBar(_ segments: [ResultsPresentation.OutcomeSegment]) -> some View {
        let shown = segments.filter { $0.pct > 0 }
        return VStack(alignment: .leading, spacing: 8) {
            GeometryReader { proxy in
                HStack(spacing: 2) {
                    ForEach(shown) { segment in
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .fill(color(segment.tone))
                            .frame(width: max(2, (proxy.size.width - CGFloat(shown.count - 1) * 2) * segment.pct / 100))
                    }
                }
            }
            .frame(height: 16)
            HStack(alignment: .top, spacing: 10) {
                ForEach(shown) { segment in
                    VStack(alignment: .leading, spacing: 1) {
                        Text(percentText(segment.pct)).font(.caption.weight(.bold)).monospacedDigit()
                        Text(segment.label).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("distribution-outcomes")
        .hubCard(padding: 14)
    }

    private func color(_ tone: ResultsPresentation.OutcomeTone) -> Color {
        switch tone {
        case .eagle: return HubStyle.eagle
        case .birdie: return HubStyle.birdie
        case .par: return HubStyle.par
        case .bogey: return HubStyle.bogey
        case .double: return HubStyle.double
        }
    }

    // MARK: 按 Par

    /// A missing field shows as missing (`—` / left out), never as 0 (`ResultsPresentation.parRow`).
    private func parRow(_ row: StatsByPar, maxOver: Double) -> some View {
        let text = ResultsPresentation.parRow(row, maxOver: maxOver)
        return HStack(spacing: 12) {
            Text(text.title).font(.subheadline.weight(.bold)).frame(width: 52, alignment: .leading)
            VStack(alignment: .leading, spacing: 4) {
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.primary.opacity(0.08))
                        if let fraction = text.fraction {
                            Capsule().fill(HubStyle.bogey)
                                .frame(width: proxy.size.width * CGFloat(min(1, fraction)))
                        }
                    }
                }
                .frame(height: 8)
                if !text.detail.isEmpty {
                    Text(text.detail).font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                }
            }
            Text(text.overPar).font(.headline).monospacedDigit()
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("distribution-par-\(row.par.map(String.init) ?? "unknown")")
        .hubCard(padding: 12)
    }

    private func percentText(_ value: Double) -> String {
        value > 0 && value < 1 ? String(format: "%.1f%%", value) : "\(Int(value.rounded()))%"
    }
}
