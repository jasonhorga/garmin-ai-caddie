import SwiftUI

/// 本洞记分 (README §2, `score.html` screen 1): one sheet, everything preselected, no source hints.
/// Total on a strip of score symbols starting at 1 (it never auto-centres), putts as segments, the
/// tee result as three small fairway tiles (hidden on a Par 3) and penalties as a small −/+.
struct LiveScoreConfirmationView: View {
    @Binding var draft: LiveScoreDraft
    let nextHole: Int?
    let onAccept: (LiveScoreDraft) -> Void
    let onCancel: () -> Void

    var body: some View {
        ZStack {
            LivePlayStyle.panelFill.ignoresSafeArea()
            VStack(alignment: .leading, spacing: 16) {
                header
                scoreStrip
                puttRow
                if draft.par != 3 {
                    teeRow
                }
                penaltyRow
                Spacer(minLength: 0)
                saveButton
            }
            .padding(.horizontal, 20)
            .padding(.top, 18)
            .padding(.bottom, 16)
        }
        .preferredColorScheme(.dark)
        .presentationDetents([.height(draft.par == 3 ? 400 : 500)])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled()
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("第 \(draft.hole) 洞 · Par \(draft.par)")
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(LivePlayStyle.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer()
            Button("取消", action: onCancel)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(LivePlayStyle.ink60)
                .accessibilityIdentifier("score-cancel")
        }
    }

    /// Starts at 1 and stays there: the player taps where they stop, the strip does not jump to the
    /// preselection.
    private var scoreStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(Array(draft.scoreChoices), id: \.self) { value in
                    scoreCell(value)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 2)
        }
        .padding(.horizontal, -20)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("总杆")
        .accessibilityIdentifier("score-strip")
    }

    private func scoreCell(_ value: Int) -> some View {
        let toPar = value - draft.par
        let selected = value == draft.score
        return Button {
            update { $0.selectScore(value) }
        } label: {
            VStack(spacing: 5) {
                ScoreChip(
                    score: value,
                    toPar: toPar,
                    size: 30,
                    dark: true,
                    ink: selected ? Color(red: 0.043, green: 0.059, blue: 0.047) : nil
                )
                Text(ScoreChip.name(toPar: toPar))
                    .font(.system(size: 10.5, weight: .semibold))
                    .foregroundStyle(selected ? Color.black.opacity(0.62) : LivePlayStyle.ink45)
                    .lineLimit(1)
            }
            .frame(width: 54, height: 78)
            .background(
                selected ? Color(red: 0.957, green: 0.965, blue: 0.949) : LivePlayStyle.fill08,
                in: RoundedRectangle(cornerRadius: 16, style: .continuous)
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(value) 杆 \(ScoreChip.name(toPar: toPar))")
        .accessibilityAddTraits(selected ? [.isSelected] : [])
        .accessibilityIdentifier("score-choice-\(value)")
    }

    /// `0 / 1 / 2 / 3 / 4+`; with `4+` selected a small −/+ sets the real count (4…9).
    private var puttRow: some View {
        HStack(spacing: 8) {
            rowLabel("推杆")
            Spacer()
            if draft.putts >= LiveScoreDraft.fourPlusSegment {
                HStack(spacing: 0) {
                    stepperButton("−", label: "推杆减一", enabled: draft.putts > LiveScoreDraft.fourPlusSegment, width: 30) {
                        update { $0.adjustFourPlusPutts(by: -1) }
                    }
                    Text("\(draft.putts)")
                        .font(.system(size: 15, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(LivePlayStyle.ink)
                        .frame(minWidth: 18)
                        .accessibilityLabel("\(draft.putts) 推")
                        .accessibilityIdentifier("score-putts-count")
                    stepperButton("+", label: "推杆加一", enabled: draft.putts < LiveScoreDraft.maximumPutts, width: 30) {
                        update { $0.adjustFourPlusPutts(by: 1) }
                    }
                }
                .frame(height: 34)
                .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            HStack(spacing: 2) {
                ForEach(LiveScoreDraft.puttSegments, id: \.self) { value in
                    let isFourPlus = value == LiveScoreDraft.fourPlusSegment
                    Button {
                        update { $0.selectPuttSegment(value) }
                    } label: {
                        Text(isFourPlus ? "4+" : "\(value)")
                            .font(.system(size: 15, weight: .semibold))
                            .monospacedDigit()
                            .foregroundStyle(LivePlayStyle.ink)
                            .frame(maxWidth: .infinity)
                            .frame(height: 34)
                            .background(
                                draft.puttSegment == value ? Color.white.opacity(0.22) : Color.clear,
                                in: RoundedRectangle(cornerRadius: 8, style: .continuous)
                            )
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(isFourPlus ? "4 推或更多" : "\(value) 推")
                    .accessibilityAddTraits(draft.puttSegment == value ? [.isSelected] : [])
                    .accessibilityIdentifier(isFourPlus ? "score-putts-4plus" : "score-putts-\(value)")
                }
            }
            .padding(2)
            .frame(width: draft.putts >= LiveScoreDraft.fourPlusSegment ? 170 : 230)
            .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
    }

    private var teeRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            rowLabel("开球")
            HStack(spacing: 8) {
                teeTile(.left, "偏左")
                teeTile(.hit, "球道")
                teeTile(.right, "偏右")
            }
        }
    }

    private func teeTile(_ result: LiveFairwayResult, _ label: String) -> some View {
        let selected = draft.fairway == result
        let tint = result == .hit
            ? Color(red: 0.361, green: 0.769, blue: 0.498)
            : Color(red: 0.902, green: 0.690, blue: 0.306)
        return Button {
            update { $0.selectFairway(result) }
        } label: {
            VStack(spacing: 3) {
                LiveTeeMiniFairway(result: result)
                    .frame(width: 60, height: 30)
                Text(label)
                    .font(.system(size: 12.5, weight: .semibold))
                    .foregroundStyle(selected ? LivePlayStyle.ink : LivePlayStyle.ink60)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 72)
            .background(
                selected ? tint.opacity(0.17) : LivePlayStyle.fill08,
                in: RoundedRectangle(cornerRadius: 14, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(selected ? tint.opacity(0.8) : LivePlayStyle.stroke14, lineWidth: selected ? 1 : 0.5)
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("开球\(label)")
        .accessibilityAddTraits(selected ? [.isSelected] : [])
        .accessibilityIdentifier("score-tee-\(result.rawValue)")
    }

    private var penaltyRow: some View {
        HStack {
            rowLabel("罚杆")
            Spacer()
            HStack(spacing: 0) {
                stepperButton("−", label: "罚杆减一", enabled: draft.penalty > 0) {
                    update { $0.adjustPenalty(by: -1) }
                }
                Rectangle().fill(LivePlayStyle.stroke14).frame(width: 0.5, height: 18)
                Text("\(draft.penalty)")
                    .font(.system(size: 15, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                    .frame(minWidth: 30)
                    .accessibilityIdentifier("score-penalty-value")
                Rectangle().fill(LivePlayStyle.stroke14).frame(width: 0.5, height: 18)
                stepperButton("+", label: "罚杆加一", enabled: draft.penalty < LiveScoreDraft.maximumPenalty) {
                    update { $0.adjustPenalty(by: 1) }
                }
            }
            .frame(height: 34)
            .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
    }

    private func stepperButton(
        _ glyph: String,
        label: String,
        enabled: Bool,
        width: CGFloat = 44,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(glyph)
                .font(.system(size: 20, weight: .medium))
                .foregroundStyle(LivePlayStyle.ink)
                .frame(width: width, height: 34)
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.28)
        .accessibilityLabel(label)
    }

    private var saveButton: some View {
        Button {
            onAccept(draft)
        } label: {
            Text(Self.saveTitle(score: draft.score, nextHole: draft.advanceAfterSave ? nextHole : nil))
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(Color(red: 0.043, green: 0.059, blue: 0.047))
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .background(Color(red: 0.957, green: 0.965, blue: 0.949), in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("score-save")
    }

    /// "保存 5 杆 · 去第 2 洞", or "保存 5 杆" for the last hole or a scorecard edit.
    static func saveTitle(score: Int, nextHole: Int?) -> String {
        guard let nextHole else { return "保存 \(score) 杆" }
        return "保存 \(score) 杆 · 去第 \(nextHole) 洞"
    }

    private func rowLabel(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(LivePlayStyle.ink60)
    }

    private func update(_ change: (inout LiveScoreDraft) -> Void) {
        var next = draft
        change(&next)
        draft = next
    }
}

/// A tiny fairway strip with the ball left of it, on it, or right of it.
struct LiveTeeMiniFairway: View {
    let result: LiveFairwayResult

    var body: some View {
        Canvas { context, size in
            let sx = size.width / 60
            let sy = size.height / 30
            var strip = Path()
            strip.move(to: CGPoint(x: 22 * sx, y: 29 * sy))
            strip.addLine(to: CGPoint(x: 25 * sx, y: 1 * sy))
            strip.addLine(to: CGPoint(x: 35 * sx, y: 1 * sy))
            strip.addLine(to: CGPoint(x: 38 * sx, y: 29 * sy))
            strip.closeSubpath()
            context.fill(strip, with: .color(Color(red: 0.549, green: 0.804, blue: 0.431).opacity(0.55)))
            let bx: CGFloat
            switch result {
            case .left: bx = 9
            case .hit: bx = 30
            case .right: bx = 51
            }
            let ball = Path(ellipseIn: CGRect(x: (bx - 4.2) * sx, y: (13 - 4.2) * sy, width: 8.4 * sx, height: 8.4 * sy))
            context.fill(ball, with: .color(Color(red: 0.957, green: 0.965, blue: 0.949)))
            context.stroke(ball, with: .color(.black.opacity(0.35)), lineWidth: 1)
        }
        .accessibilityHidden(true)
    }
}
