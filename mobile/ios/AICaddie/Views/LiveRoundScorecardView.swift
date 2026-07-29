import SwiftUI

/// The in-round scorecard is a quick correction surface, not a second play cursor. Every row can
/// open score editing, while the highlighted active hole remains the hole the player is actually on.
struct LiveRoundScorecardView: View {
    @Environment(\.dismiss) private var dismiss

    let courseName: String
    let holes: [Hole]
    let liveRoundState: LiveRoundStateSnapshot?
    let recordedScoreHoles: Set<Int>
    let onEdit: (Int) -> Void

    var body: some View {
        ZStack {
            LivePlayStyle.panelFill.ignoresSafeArea()
            VStack(spacing: 14) {
                header
                ScrollView(showsIndicators: false) {
                    LazyVStack(spacing: 8) {
                        ForEach(holes) { hole in
                            scoreRow(hole)
                        }
                    }
                    .padding(.bottom, 10)
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 18)
        }
        .preferredColorScheme(.dark)
        .presentationDetents([.fraction(0.68), .large])
        .presentationDragIndicator(.visible)
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("本场计分卡")
                    .font(.title2.weight(.heavy))
                    .foregroundStyle(LivePlayStyle.ink)
                Text("\(courseName) · 已记 \(recordedScoreHoles.count)/\(holes.count) 洞")
                    .font(.caption)
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            Spacer(minLength: 0)
            if let totalToPar {
                Text(toParText(totalToPar))
                    .font(.headline.monospacedDigit().weight(.heavy))
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: totalToPar))
                    .padding(.vertical, 6)
                    .padding(.horizontal, 10)
                    .background(LivePlayStyle.fill08, in: Capsule())
            }
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title2)
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("关闭计分卡")
        }
    }

    private func scoreRow(_ hole: Hole) -> some View {
        let score = recordedScoreHoles.contains(hole.number)
            ? liveRoundState?.holeState(for: hole.number)?.score
            : nil
        let isActive = liveRoundState?.activeHole == hole.number

        return Button {
            onEdit(hole.number)
        } label: {
            HStack(spacing: 12) {
                Text("\(hole.number)")
                    .font(.headline.monospacedDigit().weight(.heavy))
                    .foregroundStyle(isActive ? LivePlayStyle.onAccent : LivePlayStyle.ink)
                    .frame(width: 38, height: 38)
                    .background(isActive ? LivePlayStyle.accent : LivePlayStyle.fill08, in: Circle())

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 7) {
                        Text("第 \(hole.number) 洞")
                            .font(.subheadline.weight(.bold))
                            .foregroundStyle(LivePlayStyle.ink)
                        if isActive {
                            Text("当前")
                                .font(.caption2.weight(.heavy))
                                .foregroundStyle(LivePlayStyle.greenLabel)
                        }
                    }
                    Text("Par \(hole.par)")
                        .font(.caption)
                        .foregroundStyle(LivePlayStyle.ink60)
                }

                Spacer(minLength: 0)
                if let score {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(score)")
                            .font(.title3.monospacedDigit().weight(.heavy))
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: score - hole.par))
                        Text(toParText(score - hole.par))
                            .font(.caption2.monospacedDigit().weight(.semibold))
                            .foregroundStyle(LivePlayStyle.ink60)
                    }
                } else {
                    Text("—")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(LivePlayStyle.ink45)
                }
                Image(systemName: "chevron.forward")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 15, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 15).stroke(LivePlayStyle.stroke10))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("编辑第 \(hole.number) 洞成绩")
    }

    private var totalToPar: Int? {
        let recorded = holes.compactMap { hole -> Int? in
            guard recordedScoreHoles.contains(hole.number),
                  let score = liveRoundState?.holeState(for: hole.number)?.score else {
                return nil
            }
            return score - hole.par
        }
        return recorded.isEmpty ? nil : recorded.reduce(0, +)
    }

    private func toParText(_ value: Int) -> String {
        if value == 0 { return "E" }
        return value > 0 ? "+\(value)" : "\(value)"
    }
}
