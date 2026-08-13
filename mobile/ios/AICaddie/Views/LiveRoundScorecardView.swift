import SwiftUI

/// Compact front/back scorecard plus an explicit hole picker. Tapping a cell only selects it; the
/// player then chooses either “go to this hole” or “edit score”, so navigation and score correction
/// can no longer be confused. GPS is a proposal only and requires the same confirmation.
struct LiveRoundScorecardView: View {
    @Environment(\.dismiss) private var dismiss

    let courseName: String
    let holes: [Hole]
    let liveRoundState: LiveRoundStateSnapshot?
    let recordedScoreHoles: Set<Int>
    let gpsCandidate: LiveHoleGPSCandidate?
    let onGoToHole: (Int) -> Void
    let onEdit: (Int) -> Void

    @State private var selectedHole: Int

    init(
        courseName: String,
        holes: [Hole],
        liveRoundState: LiveRoundStateSnapshot?,
        recordedScoreHoles: Set<Int>,
        gpsCandidate: LiveHoleGPSCandidate? = nil,
        onGoToHole: @escaping (Int) -> Void = { _ in },
        onEdit: @escaping (Int) -> Void
    ) {
        self.courseName = courseName
        self.holes = holes.sorted { $0.number < $1.number }
        self.liveRoundState = liveRoundState
        self.recordedScoreHoles = recordedScoreHoles
        self.gpsCandidate = gpsCandidate
        self.onGoToHole = onGoToHole
        self.onEdit = onEdit
        _selectedHole = State(
            initialValue: liveRoundState?.activeHole
                ?? holes.sorted { $0.number < $1.number }.first?.number
                ?? 1
        )
    }

    var body: some View {
        ZStack {
            LivePlayStyle.panelFill.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(spacing: 14) {
                    header
                    if let gpsCandidate,
                       gpsCandidate.hole != liveRoundState?.activeHole {
                        gpsSuggestion(gpsCandidate)
                    }
                    scoreNine(title: "前九", holes: Array(holes.prefix(9)))
                    if holes.count > 9 {
                        scoreNine(title: "后九", holes: Array(holes.dropFirst(9).prefix(9)))
                    }
                    selectedActions
                }
                .padding(.horizontal, 14)
                .padding(.top, 18)
                .padding(.bottom, 24)
            }
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
            Button { dismiss() } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title2)
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("关闭计分卡")
        }
    }

    private func gpsSuggestion(_ candidate: LiveHoleGPSCandidate) -> some View {
        Button {
            selectedHole = candidate.hole
        } label: {
            HStack(spacing: 9) {
                Image(systemName: "location.fill")
                    .foregroundStyle(LivePlayStyle.greenLabel)
                VStack(alignment: .leading, spacing: 2) {
                    Text("GPS 建议第 \(candidate.hole) 洞")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(LivePlayStyle.ink)
                    Text("距离发球台约 \(Int(candidate.distanceM.rounded())) 米 · 点此后确认")
                        .font(.caption2)
                        .foregroundStyle(LivePlayStyle.ink60)
                }
                Spacer()
                Image(systemName: "chevron.forward")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            .padding(11)
            .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 13))
            .overlay(RoundedRectangle(cornerRadius: 13).stroke(LivePlayStyle.greenLabel.opacity(0.35)))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("live-scorecard-gps-candidate")
    }

    private func scoreNine(title: String, holes: [Hole]) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.caption.weight(.bold))
                .foregroundStyle(LivePlayStyle.ink60)
            scoreRow(label: "洞", holes: holes) { hole in
                Text("\(hole.number)")
                    .font(.caption.monospacedDigit().weight(.heavy))
                    .foregroundStyle(cellInk(hole))
                    .accessibilityIdentifier("live-scorecard-hole-index-\(hole.number)")
            }
            scoreRow(label: "Par", holes: holes) { hole in
                Text("\(hole.par)")
                    .font(.caption2.monospacedDigit().weight(.semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            scoreRow(label: "成绩", holes: holes) { hole in
                if let score = score(for: hole) {
                    ScoreChip(score: score, toPar: score - hole.par, size: 27)
                        .accessibilityIdentifier("live-scorecard-score-chip-\(hole.number)")
                } else {
                    Text("—")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(LivePlayStyle.ink45)
                }
            }
        }
        .padding(10)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 15))
        .overlay(RoundedRectangle(cornerRadius: 15).stroke(LivePlayStyle.stroke10))
    }

    private func scoreRow<Content: View>(
        label: String,
        holes: [Hole],
        @ViewBuilder content: @escaping (Hole) -> Content
    ) -> some View {
        HStack(spacing: 3) {
            Text(label)
                .font(.caption2.weight(.bold))
                .foregroundStyle(LivePlayStyle.ink45)
                .frame(width: 34, alignment: .leading)
            ForEach(holes) { hole in
                Button {
                    selectedHole = hole.number
                } label: {
                    content(hole)
                        .frame(maxWidth: .infinity, minHeight: 29)
                        .background(cellFill(hole), in: RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(cellStroke(hole)))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("选择第 \(hole.number) 洞")
            }
        }
    }

    private var selectedActions: some View {
        VStack(spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("第 \(selectedHole) 洞")
                        .font(.headline.weight(.heavy))
                        .foregroundStyle(LivePlayStyle.ink)
                    if selectedHole == liveRoundState?.activeHole {
                        Text("当前正在记录")
                            .font(.caption)
                            .foregroundStyle(LivePlayStyle.greenLabel)
                    } else {
                        Text("选择去此洞或只修改成绩")
                            .font(.caption)
                            .foregroundStyle(LivePlayStyle.ink60)
                    }
                }
                Spacer()
                if let hole = holes.first(where: { $0.number == selectedHole }),
                   let score = score(for: hole) {
                    Text("\(score) 杆 · \(toParText(score - hole.par))")
                        .font(.subheadline.monospacedDigit().weight(.bold))
                        .foregroundStyle(LivePlayStyle.ink)
                }
            }
            HStack(spacing: 9) {
                Button {
                    onGoToHole(selectedHole)
                } label: {
                    Label("去第 \(selectedHole) 洞", systemImage: "location.circle.fill")
                        .font(.subheadline.weight(.bold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(LivePlayStyle.onAccent)
                        .background(LivePlayStyle.accent, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .disabled(selectedHole == liveRoundState?.activeHole)
                .opacity(selectedHole == liveRoundState?.activeHole ? 0.45 : 1)
                .accessibilityIdentifier("live-scorecard-go-hole")

                Button {
                    onEdit(selectedHole)
                } label: {
                    Label("编辑成绩", systemImage: "pencil")
                        .font(.subheadline.weight(.bold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(LivePlayStyle.ink)
                        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LivePlayStyle.stroke14))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("live-scorecard-edit-hole")
            }
        }
        .padding(12)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 15))
        .overlay(RoundedRectangle(cornerRadius: 15).stroke(LivePlayStyle.stroke10))
    }

    private func score(for hole: Hole) -> Int? {
        recordedScoreHoles.contains(hole.number)
            ? liveRoundState?.holeState(for: hole.number)?.score
            : nil
    }

    private func cellFill(_ hole: Hole) -> Color {
        if selectedHole == hole.number { return LivePlayStyle.accent.opacity(0.22) }
        if liveRoundState?.activeHole == hole.number { return LivePlayStyle.greenLabel.opacity(0.10) }
        return .clear
    }

    private func cellStroke(_ hole: Hole) -> Color {
        if selectedHole == hole.number { return LivePlayStyle.accent.opacity(0.8) }
        if liveRoundState?.activeHole == hole.number { return LivePlayStyle.greenLabel.opacity(0.5) }
        return .clear
    }

    private func cellInk(_ hole: Hole) -> Color {
        liveRoundState?.activeHole == hole.number ? LivePlayStyle.greenLabel : LivePlayStyle.ink
    }

    private var totalToPar: Int? {
        let recorded = holes.compactMap { hole -> Int? in
            score(for: hole).map { $0 - hole.par }
        }
        return recorded.isEmpty ? nil : recorded.reduce(0, +)
    }

    private func toParText(_ value: Int) -> String {
        if value == 0 { return "E" }
        return value > 0 ? "+\(value)" : "\(value)"
    }
}
