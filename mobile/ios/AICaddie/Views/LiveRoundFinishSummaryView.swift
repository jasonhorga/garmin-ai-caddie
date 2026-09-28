import SwiftUI

/// 本场汇总 (README §2, `score.html` screen 3): the same layout as the post-round review — the big
/// score, the scorecard, then 球道命中 / GIR (按推杆推算) / 推杆 / 罚杆 — so saving it simply becomes
/// the review. No sync status: saving lands locally first and uploads in the background. Nothing
/// is deleted by opening or dismissing it; 放弃本场 asks first.
struct LiveRoundFinishSummaryView: View {
    let courseName: String
    let holes: [Hole]
    let scores: [Int: LiveHoleScore]
    let isFinishingRound: Bool
    let finishErrorMessage: String?
    let onFinish: () -> Void
    let onContinue: () -> Void
    let onDiscard: () -> Void

    private var orderedHoles: [Hole] { holes.sorted { $0.number < $1.number } }
    private var summary: LiveRoundScoreSummary {
        LiveRoundScoreSummary(holes: orderedHoles.compactMap { scores[$0.number] })
    }

    var body: some View {
        ZStack {
            LivePlayStyle.base.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 16) {
                    Text(localizedCourseDisplayName(courseName))
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(LivePlayStyle.ink60)
                        .lineLimit(1)
                    scoreHero
                    scorecard
                    tiles
                    if let finishErrorMessage {
                        Label(finishErrorMessage, systemImage: "exclamationmark.triangle.fill")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(LivePlayStyle.hazard)
                    }
                    actions
                }
                .padding(.horizontal, 20)
                .padding(.top, 24)
                .padding(.bottom, 24)
            }
        }
        .preferredColorScheme(.dark)
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(isFinishingRound)
    }

    private var scoreHero: some View {
        HStack(alignment: .bottom, spacing: 16) {
            Text(summary.toPar.map(LiveRoundScoreSummary.toParText) ?? "—")
                .font(.system(size: 96, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
                .accessibilityIdentifier("live-finish-to-par")
            VStack(alignment: .leading, spacing: 2) {
                Text(summary.holes.isEmpty ? "—" : "\(summary.strokes) 杆")
                    .font(.system(size: 24, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                Text(Self.parLine(summary: summary, holes: orderedHoles))
                    .font(.system(size: 13))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            .padding(.bottom, 6)
        }
    }

    /// "Par 36 · 9/18 洞": the Par of the holes actually recorded (the whole course before any is).
    static func parLine(summary: LiveRoundScoreSummary, holes: [Hole]) -> String {
        let par = summary.holes.isEmpty ? holes.reduce(0) { $0 + $1.par } : summary.par
        return "Par \(par) · \(summary.holes.count)/\(holes.count) 洞"
    }

    private var scorecard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("记分卡")
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(LivePlayStyle.ink)
                .padding(.horizontal, 4)
            LiveNineCard(label: "OUT", holes: Array(orderedHoles.prefix(9)), scores: scores)
            if orderedHoles.count > 9 {
                LiveNineCard(label: "IN", holes: Array(orderedHoles.dropFirst(9).prefix(9)), scores: scores)
            }
        }
    }

    private var tiles: some View {
        let summary = summary
        return Grid(horizontalSpacing: 8, verticalSpacing: 8) {
            GridRow {
                tile(
                    title: "球道命中",
                    value: LiveRoundScoreSummary.percent(summary.fairwaysHit, of: summary.fairwaysRecorded).map { "\($0)%" },
                    detail: summary.fairwaysRecorded > 0 ? "\(summary.fairwaysHit)/\(summary.fairwaysRecorded)" : nil,
                    identifier: "live-finish-fairways"
                )
                tile(
                    title: "GIR 上果岭 · 按推杆推算",
                    value: LiveRoundScoreSummary.percent(summary.girHit, of: summary.girRecorded).map { "\($0)%" },
                    detail: summary.girRecorded > 0 ? "\(summary.girHit)/\(summary.girRecorded)" : nil,
                    identifier: "live-finish-gir"
                )
            }
            GridRow {
                tile(
                    title: "推杆",
                    value: summary.putts.map(String.init),
                    detail: summary.putts.map { String(format: "%.1f/洞", Double($0) / Double(max(summary.puttHoles, 1))) },
                    identifier: "live-finish-putts"
                )
                tile(
                    title: "罚杆",
                    value: summary.holes.isEmpty ? nil : "\(summary.penalties)",
                    detail: nil,
                    identifier: "live-finish-penalties"
                )
            }
        }
    }

    private func tile(title: String, value: String?, detail: String?, identifier: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(LivePlayStyle.ink60)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(value ?? "—")
                    .font(.system(size: 24, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                if let detail {
                    Text(detail)
                        .font(.system(size: 12))
                        .monospacedDigit()
                        .foregroundStyle(LivePlayStyle.ink60)
                }
            }
        }
        .padding(.horizontal, 13)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(LivePlayStyle.stroke14, lineWidth: 0.5))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title) \(value ?? "未记") \(detail ?? "")")
        .accessibilityIdentifier(identifier)
    }

    private var actions: some View {
        VStack(spacing: 10) {
            Button(action: onFinish) {
                HStack(spacing: 8) {
                    if isFinishingRound {
                        ProgressView().tint(LiveScoreStyle.primaryInk)
                    }
                    Text("保存并结束")
                        .font(.system(size: 17, weight: .bold))
                }
                .foregroundStyle(LiveScoreStyle.primaryInk)
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .background(LiveScoreStyle.primaryFill, in: Capsule())
            }
            .buttonStyle(.plain)
            .disabled(isFinishingRound)
            .accessibilityIdentifier("live-finish-save")

            Button(action: onContinue) {
                Text("继续打球")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink)
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .background(LivePlayStyle.fill08, in: Capsule())
                    .overlay(Capsule().stroke(LivePlayStyle.stroke14, lineWidth: 0.5))
            }
            .buttonStyle(.plain)
            .disabled(isFinishingRound)

            Button("放弃本场", role: .destructive, action: onDiscard)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(LiveScoreStyle.bad)
                .buttonStyle(.plain)
                .disabled(isFinishingRound)
                .padding(.top, 4)
                .accessibilityIdentifier("live-finish-discard")
        }
    }
}
