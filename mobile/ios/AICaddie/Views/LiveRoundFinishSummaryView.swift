import SwiftUI

/// One honest end-of-round surface shared by the final hole and the in-round menu. Nothing is
/// deleted by opening or dismissing it; the owner only clears the active round after its async
/// save-and-finish transaction succeeds.
struct LiveRoundFinishSummaryView: View {
    let courseName: String
    let holesCompleted: Int
    let holeCount: Int
    let totalStrokes: Int
    let toPar: Int?
    let totalPutts: Int
    let fairwaysHit: Int
    let fairwaysRecorded: Int
    let totalPenalties: Int
    let pendingEventCount: Int
    let isFinishingRound: Bool
    let finishErrorMessage: String?
    let onFinish: () -> Void
    let onContinue: () -> Void

    var body: some View {
        ZStack {
            LivePlayStyle.panelFill.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(spacing: 18) {
                    header
                    scoreHero
                    detailMetrics
                    saveState
                    actions
                }
                .padding(.horizontal, 20)
                .padding(.top, 22)
                .padding(.bottom, 24)
            }
        }
        .preferredColorScheme(.dark)
        .presentationDetents([.fraction(0.72), .large])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(isFinishingRound)
    }

    private var header: some View {
        VStack(spacing: 4) {
            Text("本场汇总")
                .font(.title2.weight(.heavy))
                .foregroundStyle(LivePlayStyle.ink)
            Text(courseName)
                .font(.subheadline)
                .foregroundStyle(LivePlayStyle.ink60)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
    }

    private var scoreHero: some View {
        HStack(alignment: .center, spacing: 20) {
            Text(toParText)
                .font(.system(size: 58, weight: .heavy, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                .minimumScaleFactor(0.7)

            VStack(alignment: .leading, spacing: 5) {
                Text("\(totalStrokes) 杆")
                    .font(.title2.monospacedDigit().weight(.heavy))
                    .foregroundStyle(LivePlayStyle.ink)
                Text("已完成 \(holesCompleted)/\(holeCount) 洞")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(LivePlayStyle.stroke10))
    }

    private var detailMetrics: some View {
        HStack(spacing: 8) {
            metric(value: "\(totalPutts)", label: "推杆", identifier: "live-finish-putts")
            metric(value: fairwayText, label: "球道", identifier: "live-finish-fairways")
            metric(value: "\(totalPenalties)", label: "罚杆", identifier: "live-finish-penalties")
        }
    }

    @ViewBuilder private var saveState: some View {
        if let finishErrorMessage {
            Label(finishErrorMessage, systemImage: "exclamationmark.triangle.fill")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LivePlayStyle.hazard)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(LivePlayStyle.hazard.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
        } else if pendingEventCount > 0 {
            Label("\(pendingEventCount) 条记录将在结束前安全保存", systemImage: "arrow.up.circle")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LivePlayStyle.ink60)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            Label("本场记录已同步", systemImage: "checkmark.circle.fill")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LivePlayStyle.greenLabel)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var actions: some View {
        VStack(spacing: 10) {
            Button(action: onFinish) {
                HStack(spacing: 8) {
                    if isFinishingRound {
                        ProgressView().tint(LivePlayStyle.onAccent)
                    }
                    Text(isFinishingRound ? "正在保存…" : "保存并结束")
                        .font(.headline.weight(.heavy))
                }
                .foregroundStyle(LivePlayStyle.onAccent)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(LivePlayStyle.accent, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(isFinishingRound)

            Button("继续打球", action: onContinue)
                .font(.headline.weight(.bold))
                .foregroundStyle(LivePlayStyle.ink)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 13)
                .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 15).stroke(LivePlayStyle.stroke14))
                .buttonStyle(.plain)
                .disabled(isFinishingRound)
        }
    }

    private var toParText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }

    private var fairwayText: String {
        fairwaysRecorded > 0 ? "\(fairwaysHit)/\(fairwaysRecorded)" : "—"
    }

    private func metric(value: String, label: String, identifier: String) -> some View {
        VStack(spacing: 3) {
            Text(value)
                .font(.title3.monospacedDigit().weight(.heavy))
                .foregroundStyle(LivePlayStyle.ink)
            Text(label)
                .font(.caption)
                .foregroundStyle(LivePlayStyle.ink60)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(LivePlayStyle.stroke10))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label) \(value)")
        .accessibilityIdentifier(identifier)
    }
}
