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
    /// B1: the live screen's 返回 opens this sheet, so the round-level actions live here.
    let onFinishRound: (() -> Void)?
    let onLeaveToHome: (() -> Void)?
    let roundAdjustments: AnyView?

    @State private var selectedHole: Int

    init(
        courseName: String,
        holes: [Hole],
        liveRoundState: LiveRoundStateSnapshot?,
        recordedScoreHoles: Set<Int>,
        gpsCandidate: LiveHoleGPSCandidate? = nil,
        onGoToHole: @escaping (Int) -> Void = { _ in },
        onEdit: @escaping (Int) -> Void,
        onFinishRound: (() -> Void)? = nil,
        onLeaveToHome: (() -> Void)? = nil,
        roundAdjustments: AnyView? = nil
    ) {
        self.courseName = courseName
        self.holes = holes.sorted { $0.number < $1.number }
        self.liveRoundState = liveRoundState
        self.recordedScoreHoles = recordedScoreHoles
        self.gpsCandidate = gpsCandidate
        self.onGoToHole = onGoToHole
        self.onEdit = onEdit
        self.onFinishRound = onFinishRound
        self.onLeaveToHome = onLeaveToHome
        self.roundAdjustments = roundAdjustments
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
                VStack(alignment: .leading, spacing: 14) {
                    header
                    if let gpsCandidate,
                       gpsCandidate.hole != liveRoundState?.activeHole {
                        gpsSuggestion(gpsCandidate)
                    }
                    scoreHero
                    LiveCumulativeTrend(values: summary.cumulativeToPar, holeCount: holes.count)
                        .frame(height: 84)
                    LiveNineCard(
                        label: "OUT",
                        holes: Array(holes.prefix(9)),
                        scores: holeScores,
                        currentHole: liveRoundState?.activeHole,
                        selectedHole: selectedHole,
                        onSelect: { selectedHole = $0 }
                    )
                    if holes.count > 9 {
                        LiveNineCard(
                            label: "IN",
                            holes: Array(holes.dropFirst(9).prefix(9)),
                            scores: holeScores,
                            currentHole: liveRoundState?.activeHole,
                            selectedHole: selectedHole,
                            onSelect: { selectedHole = $0 }
                        )
                    }
                    selectedActions
                    if let roundAdjustments {
                        roundAdjustments
                    }
                    if onFinishRound != nil || onLeaveToHome != nil {
                        roundActions
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 18)
                .padding(.bottom, 24)
            }
        }
        .preferredColorScheme(.dark)
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("计分卡")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink)
                    .accessibilityAddTraits(.isHeader)
                Text("\(localizedCourseDisplayName(courseName)) · 已记 \(recordedScoreHoles.count)/\(holes.count) 洞")
                    .font(.system(size: 13))
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            Spacer(minLength: 0)
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .frame(width: 30, height: 30)
                    .background(LivePlayStyle.fill12, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("关闭计分卡")
        }
    }

    /// The big "+4", then strokes and the two nines.
    private var scoreHero: some View {
        HStack(alignment: .bottom, spacing: 14) {
            Text(summary.toPar.map(LiveRoundScoreSummary.toParText) ?? "—")
                .font(.system(size: 56, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .accessibilityLabel(summary.toPar.map { "本场 \(LiveRoundScoreSummary.toParText($0))" } ?? "本场还没有成绩")
                .accessibilityIdentifier("live-scorecard-total-summary")
            VStack(alignment: .leading, spacing: 1) {
                Text(summary.holes.isEmpty ? "—" : "\(summary.strokes) 杆")
                    .font(.system(size: 17, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                    .accessibilityIdentifier("live-scorecard-total-score")
                Text(ninesText)
                    .font(.system(size: 12.5))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            .padding(.bottom, 4)
        }
    }

    private var ninesText: String {
        func nine(_ slice: ArraySlice<Hole>) -> String {
            let recorded = slice.compactMap { holeScores[$0.number]?.score }
            return recorded.isEmpty ? "—" : "\(recorded.reduce(0, +))"
        }
        guard holes.count > 9 else { return "前九 \(nine(holes.prefix(9)))" }
        return "前九 \(nine(holes.prefix(9))) · 后九 \(nine(holes.dropFirst(9).prefix(9)))"
    }

    private func gpsSuggestion(_ candidate: LiveHoleGPSCandidate) -> some View {
        Button {
            selectedHole = candidate.hole
        } label: {
            HStack(spacing: 9) {
                Image(systemName: "location.fill")
                    .foregroundStyle(LivePlayStyle.greenLabel)
                Text("你在第 \(candidate.hole) 洞附近")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(LivePlayStyle.ink)
                Spacer()
                Image(systemName: "chevron.forward")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            .padding(11)
            .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 13))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("live-scorecard-gps-candidate")
    }

    private var selectedActions: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                Text(selectedTitle)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink)
                Text(selectedStatus)
                    .font(.system(size: 12.5))
                    .foregroundStyle(LivePlayStyle.ink60)
            }
            HStack(spacing: 10) {
                Button {
                    onGoToHole(selectedHole)
                } label: {
                    Text("去第 \(selectedHole) 洞")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(LiveScoreStyle.primaryInk)
                        .frame(maxWidth: .infinity)
                        .frame(height: 46)
                        .background(LiveScoreStyle.primaryFill, in: Capsule())
                }
                .buttonStyle(.plain)
                .disabled(selectedHole == liveRoundState?.activeHole)
                .opacity(selectedHole == liveRoundState?.activeHole ? 0.35 : 1)
                .accessibilityIdentifier("live-scorecard-go-hole")

                Button {
                    onEdit(selectedHole)
                } label: {
                    Text("改成绩")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(LivePlayStyle.ink)
                        .frame(maxWidth: .infinity)
                        .frame(height: 46)
                        .background(LivePlayStyle.fill08, in: Capsule())
                        .overlay(Capsule().stroke(LivePlayStyle.stroke14, lineWidth: 0.5))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("改第 \(selectedHole) 洞成绩")
                .accessibilityIdentifier("live-scorecard-edit-hole")
            }
        }
        .padding(.top, 4)
    }

    private var selectedTitle: String {
        let par = holes.first(where: { $0.number == selectedHole })?.par
        return par.map { "第 \(selectedHole) 洞 · Par \($0)" } ?? "第 \(selectedHole) 洞"
    }

    private var selectedStatus: String {
        if let recorded = holeScores[selectedHole] {
            return "\(recorded.score) 杆 · \(ScoreChip.name(toPar: recorded.score - recorded.par)) · \(recorded.putts) 推"
        }
        return selectedHole == liveRoundState?.activeHole ? "正在打这一洞" : "还没记成绩"
    }

    /// 回到首页 keeps the round; 结束本场… opens the round summary (README §2).
    private var roundActions: some View {
        HStack(spacing: 28) {
            if let onLeaveToHome {
                Button("回到首页", action: onLeaveToHome)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .buttonStyle(.plain)
                    .accessibilityHint("本场保留，可以随时继续")
                    .accessibilityIdentifier("live-scorecard-leave-home")
            }
            if let onFinishRound {
                Button("结束本场…", action: onFinishRound)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .buttonStyle(.plain)
                    .accessibilityLabel("结束或放弃本场")
                    .accessibilityIdentifier("live-round-end-menu")
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var holeScores: [Int: LiveHoleScore] {
        var result: [Int: LiveHoleScore] = [:]
        for hole in holes where recordedScoreHoles.contains(hole.number) {
            guard let state = liveRoundState?.holeState(for: hole.number) else { continue }
            result[hole.number] = LiveHoleScore(
                hole: hole.number,
                par: hole.par,
                score: state.score,
                putts: state.putts,
                penalties: state.penaltyCount,
                fairway: state.fairwayResult,
                source: state.scoreSource
            )
        }
        return result
    }

    private var summary: LiveRoundScoreSummary {
        let scores = holeScores
        return LiveRoundScoreSummary(holes: holes.compactMap { scores[$0.number] })
    }
}
