import SwiftUI

enum WatchScoreHoleLayout {
    /// watchOS owns the top-right corner for the system clock. Keep the score title inside the
    /// remaining glance area so it never reads as one string with the time (for example Par 42:04).
    static let systemTimeTrailingClearance: CGFloat = 48
    /// Horizontal drag distance for one stroke on the total band.
    static let bandStepPoints: CGFloat = 28
    /// Vertical drag distance for one step on an open putts / penalties wheel.
    static let wheelStepPoints: CGFloat = 22
}

/// Which inline wheel is open on 本洞成绩.
public enum WatchScoreWheel: String, Equatable {
    case putts, penalty
}

/// B6 本洞成绩 (README §3): one screen. The total is a horizontal number band (drag or Crown; the
/// middle number is the value, its neighbours smaller and fainter). Putts and penalties are inline
/// wheels: tap to open, roll up/down (or the Crown) in a loop, and they close once left alone.
/// Par 4/5 add the three tee-shot cells. 保存 confirms; an unconfirmed hole is saved by the next
/// hole's tee shot. Presentational and driven by `WatchRoundModel`.
public struct WatchScoreHoleView: View {
    public let hole: Int
    public let par: Int
    public let score: Int
    public let putts: Int
    public let penalty: Int
    public let courseDataPending: Bool
    public let fairway: WatchFairwayResult?
    /// The ordered next hole when its first shot was captured before this hole was confirmed.
    public let candidateNextHole: Int?
    public let onScore: (Int) -> Void
    public let onPutts: (Int) -> Void
    public let onPenalty: (Int) -> Void
    public let onFairway: (WatchFairwayResult) -> Void
    public let onSave: () -> Void
    public let onCancel: () -> Void

    @State private var openWheel: WatchScoreWheel?
    @State private var crown: Double = 0
    @State private var crownBase: Double = 0
    @State private var bandDrag: CGFloat = 0
    @State private var wheelDrag: CGFloat = 0

    public init(
        hole: Int,
        par: Int,
        score: Int,
        putts: Int,
        penalty: Int,
        courseDataPending: Bool = false,
        fairway: WatchFairwayResult? = nil,
        candidateNextHole: Int? = nil,
        openWheel: WatchScoreWheel? = nil,
        onScore: @escaping (Int) -> Void = { _ in },
        onPutts: @escaping (Int) -> Void = { _ in },
        onPenalty: @escaping (Int) -> Void = { _ in },
        onFairway: @escaping (WatchFairwayResult) -> Void = { _ in },
        onSave: @escaping () -> Void = {},
        onCancel: @escaping () -> Void = {}
    ) {
        self.hole = hole
        self.par = par
        self.score = score
        self.putts = putts
        self.penalty = penalty
        self.courseDataPending = courseDataPending
        self.fairway = fairway
        self.candidateNextHole = candidateNextHole
        self._openWheel = State(initialValue: openWheel)
        self.onScore = onScore
        self.onPutts = onPutts
        self.onPenalty = onPenalty
        self.onFairway = onFairway
        self.onSave = onSave
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(spacing: 4) {
            header
            if let openWheel {
                wheel(openWheel)
            } else {
                scoreBand
                HStack(spacing: 6) {
                    wheelChip(.putts)
                    wheelChip(.penalty)
                }
                if par != 3 {
                    fairwayCells
                }
            }
            Spacer(minLength: 0)
            saveButton
        }
        .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
        .padding(.top, 3)
        .padding(.bottom, 7)
        // Padding must participate in the proposed Watch content size (see the 45 mm runtime).
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        // The title already reserves the top-right clock lane.
        .ignoresSafeArea(edges: .top)
        .focusable()
        .digitalCrownRotation($crown, from: -1_000, through: 1_000, by: 1, sensitivity: .low,
                              isContinuous: true, isHapticFeedbackEnabled: true)
        .onChange(of: crown) { _, value in
            let steps = Int((value - crownBase).rounded())
            guard steps != 0 else { return }
            crownBase += Double(steps)
            step(steps)
        }
        .task(id: wheelIdentity) {
            // An open wheel closes once left alone ("停手即选定并收起").
            guard openWheel != nil else { return }
            try? await Task.sleep(nanoseconds: 1_600_000_000)
            guard !Task.isCancelled else { return }
            withAnimation(.easeOut(duration: 0.2)) { openWheel = nil }
        }
        .animation(.spring(response: 0.28, dampingFraction: 0.8), value: score)
    }

    /// Changes whenever the open wheel or its value changes, restarting the close timer.
    private var wheelIdentity: String {
        switch openWheel {
        case .putts: return "putts-\(putts)"
        case .penalty: return "penalty-\(penalty)"
        case nil: return "closed"
        }
    }

    private func step(_ delta: Int) {
        switch openWheel {
        case .putts: onPutts(putts + delta)
        case .penalty: onPenalty(penalty + delta)
        case nil: onScore(score + delta)
        }
    }

    private var header: some View {
        HStack(spacing: 5) {
            Button(action: onCancel) {
                Image(systemName: "chevron.backward")
                    .font(.system(size: 17, weight: .black))
                    .frame(width: WatchDisplayGeometry.instrumentVisualControlSize,
                           height: WatchDisplayGeometry.instrumentVisualControlSize)
                    .frame(width: WatchDisplayGeometry.instrumentControlSize,
                           height: WatchDisplayGeometry.instrumentControlSize)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("取消记分")
            Text(courseDataPending ? "H\(hole) · 等待球场数据" : "H\(hole) · P\(par)")
                .font(.system(size: 18, weight: .black))
                .lineLimit(1)
                .minimumScaleFactor(0.62)
                .layoutPriority(1)
            Spacer(minLength: WatchScoreHoleLayout.systemTimeTrailingClearance)
        }
    }

    // MARK: 总杆 band

    private var scoreBand: some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: 0) {
                ForEach(-2...2, id: \.self) { offset in
                    let value = score + offset
                    Text(WatchScoreRules.scoreRange.contains(value) ? "\(value)" : "")
                        .font(.system(size: offset == 0 ? 50 : (abs(offset) == 1 ? 24 : 16),
                                      weight: .black, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.white.opacity(offset == 0 ? 1 : (abs(offset) == 1 ? 0.45 : 0.2)))
                        .frame(maxWidth: .infinity)
                        .onTapGesture { if offset != 0 { onScore(value) } }
                }
            }
            .offset(x: bandDrag)
            .frame(height: 58)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 6)
                    .onChanged { bandDrag = $0.translation.width }
                    .onEnded { value in
                        let steps = Int((-value.translation.width / WatchScoreHoleLayout.bandStepPoints).rounded())
                        bandDrag = 0
                        if steps != 0 { onScore(score + steps) }
                    }
            )
            .accessibilityElement()
            .accessibilityLabel("总杆 \(score)")
            .accessibilityAdjustableAction { direction in
                onScore(score + (direction == .increment ? 1 : -1))
            }
            .accessibilityIdentifier("watch-score-band")
            Text(noteText)
                .font(.system(size: 13, weight: .black, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(candidateNextHole == nil
                    ? AICaddieDesignTokens.scoreColor(toPar: score - par)
                    : AICaddieDesignTokens.par)
        }
    }

    private var noteText: String {
        if let candidateNextHole { return "第 \(candidateNextHole) 洞首杆已暂存" }
        let diff = score - par
        if diff == 0 { return "标准杆" }
        return diff > 0 ? "+\(diff)" : "\(diff)"
    }

    // MARK: 推 / 罚 wheels

    private func wheelChip(_ wheel: WatchScoreWheel) -> some View {
        Button {
            withAnimation(.easeOut(duration: 0.2)) { openWheel = wheel }
        } label: {
            HStack(spacing: 4) {
                Text(wheel == .putts ? "推" : "罚")
                    .font(.system(size: 14, weight: .heavy))
                    .foregroundStyle(.secondary)
                Text("\(wheel == .putts ? putts : penalty)")
                    .font(.system(size: 22, weight: .black, design: .rounded))
                    .monospacedDigit()
            }
            .frame(maxWidth: .infinity)
            .frame(height: 38)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.2)))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(wheel == .putts ? "推杆" : "罚杆") \(wheel == .putts ? putts : penalty)")
        .accessibilityIdentifier("watch-score-\(wheel.rawValue)")
    }

    private func wheel(_ wheel: WatchScoreWheel) -> some View {
        let range = wheel == .putts ? WatchScoreRules.puttRange : WatchScoreRules.penaltyRange
        let value = wheel == .putts ? putts : penalty
        return VStack(spacing: 0) {
            Text(wheel == .putts ? "推杆" : "罚杆")
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(.secondary)
            ForEach(-1...1, id: \.self) { offset in
                Text("\(WatchScoreRules.wrap(value + offset, in: range))")
                    .font(.system(size: offset == 0 ? 44 : 22, weight: .black, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(offset == 0 ? 1 : 0.35))
                    .frame(maxWidth: .infinity)
                    .frame(height: offset == 0 ? 52 : 28)
            }
            Text("总杆 \(score)")
                .font(.system(size: 12, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(.secondary)
        }
        .offset(y: wheelDrag)
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 4)
                .onChanged { wheelDrag = $0.translation.height / 3 }
                .onEnded { drag in
                    // Rolling up brings the next number in.
                    let steps = Int((-drag.translation.height / WatchScoreHoleLayout.wheelStepPoints).rounded())
                    wheelDrag = 0
                    if steps != 0 { step(steps) }
                }
        )
        .onTapGesture { withAnimation(.easeOut(duration: 0.2)) { openWheel = nil } }
        .accessibilityElement()
        .accessibilityLabel("\(wheel == .putts ? "推杆" : "罚杆") \(value)")
        .accessibilityAdjustableAction { direction in step(direction == .increment ? 1 : -1) }
        .accessibilityIdentifier("watch-score-wheel-\(wheel.rawValue)")
    }

    // MARK: 开球三格

    private var fairwayCells: some View {
        HStack(spacing: 5) {
            fairwayCell("左", .left)
            fairwayCell("中", .hit)
            fairwayCell("右", .right)
        }
    }

    private func fairwayCell(_ label: String, _ result: WatchFairwayResult) -> some View {
        Button { onFairway(result) } label: {
            Text(label)
                .font(.system(size: 15, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 30)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(fairway == result ? AICaddieDesignTokens.par : Color.white.opacity(0.2))
                )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("开球\(label == "中" ? "上球道" : "偏\(label)")")
        .accessibilityAddTraits(fairway == result ? .isSelected : [])
        .accessibilityIdentifier("watch-score-fairway-\(result.rawValue)")
    }

    private var saveButton: some View {
        Button(action: onSave) {
            Text("保存 \(score) 杆")
                .font(.system(size: 17, weight: .black))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .buttonStyle(.plain)
        .frame(height: 40)
        .background(Capsule().fill(AICaddieDesignTokens.par))
        .accessibilityIdentifier("watch-score-save")
    }
}
