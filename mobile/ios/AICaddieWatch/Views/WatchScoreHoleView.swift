import SwiftUI

enum WatchScoreHoleLayout {
    /// The band follows the dominant drag axis: left/right, or up/down. Up behaves like left:
    /// it brings the bigger numbers to the middle.
    static func bandTravel(_ translation: CGSize) -> CGFloat {
        abs(translation.width) >= abs(translation.height) ? translation.width : translation.height
    }

    static func bandSteps(_ translation: CGSize) -> Int {
        Int((-bandTravel(translation) / bandStepPoints).rounded())
    }

    /// watchOS owns the top-right corner for the system clock. Keep the score title inside the
    /// remaining glance area so it never reads as one string with the time (for example Par 42:04).
    static let systemTimeTrailingClearance: CGFloat = 48
    /// Horizontal drag distance for one stroke on the total band.
    static let bandStepPoints: CGFloat = 28
    /// Vertical drag distance for one step on the open putts / penalties picker (full screen).
    static let wheelStepPoints: CGFloat = 30
    /// Rolling up brings the next number in.
    static func wheelSteps(_ translationHeight: CGFloat) -> Int {
        Int((-translationHeight / wheelStepPoints).rounded())
    }

    /// How far the digits follow the finger: a short peek toward the next number.
    static func wheelPeek(_ translationHeight: CGFloat) -> CGFloat {
        let limit = wheelStepPoints * 0.6
        return min(max(translationHeight / 2, -limit), limit)
    }

    /// Owner feedback 2026-10-11: the in-chip wheel (36 pt, folding 0.45 s after the finger lifted)
    /// could not be operated on the wrist. The picker now opens full screen and folds back only
    /// after the golfer has left it alone this long, or on 完成.
    static func wheelCloseDelayNanoseconds(settled: Bool) -> UInt64 {
        settled ? 2_500_000_000 : 4_000_000_000
    }

    /// Below this content height (41 mm / 40 mm) the compact metrics are used so every row — the
    /// 保存 button included — stays fully on screen and tappable.
    static let compactHeight: CGFloat = 236

    struct Metrics: Equatable {
        let header: CGFloat
        let bandFont: CGFloat
        let band: CGFloat
        let chip: CGFloat
        let cell: CGFloat
        let save: CGFloat
        let spacing: CGFloat

        static let regular = Metrics(header: 32, bandFont: 48, band: 54, chip: 40, cell: 28, save: 38, spacing: 3)
        static let compact = Metrics(header: 24, bandFont: 38, band: 42, chip: 36, cell: 24, save: 32, spacing: 2)
    }

    static func metrics(forHeight height: CGFloat) -> Metrics {
        height < compactHeight ? .compact : .regular
    }

    /// Total height the one-screen layout needs (header, band + note, chips, cells, 保存).
    static func requiredHeight(_ m: Metrics, showsFairway: Bool) -> CGFloat {
        let note: CGFloat = 15
        let rows: [CGFloat] = [m.header, m.band + note, m.chip] + (showsFairway ? [m.cell] : []) + [m.save]
        return rows.reduce(0, +) + m.spacing * CGFloat(rows.count) + 3 + 7
    }
}

/// Which putts / penalties picker is open on 本洞成绩.
public enum WatchScoreWheel: String, Equatable {
    case putts, penalty
}

/// B6 本洞成绩 (README §3): one screen. The total is a horizontal number band (drag or Crown; the
/// middle number is the value, its neighbours smaller and fainter). Putts and penalties are chips
/// that open a full-screen picker (- / +, roll up/down, or the Crown, in a loop; 完成 or left alone).
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
    /// A roll on the open wheel has ended; it folds back after a short pause.
    @State private var wheelSettled = false
    /// A finger is on the open picker: it never folds mid-drag.
    @State private var wheelDragging = false
    /// DEBUG evidence only (`WatchUITestRoot` score-putts / score-penalty): keep the fixture's open
    /// wheel open so a runtime capture shows it. Production always folds it back.
    private let holdsOpenWheel: Bool

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
        holdsOpenWheel: Bool = false,
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
        self.holdsOpenWheel = holdsOpenWheel
        self.onScore = onScore
        self.onPutts = onPutts
        self.onPenalty = onPenalty
        self.onFairway = onFairway
        self.onSave = onSave
        self.onCancel = onCancel
    }

    public var body: some View {
        GeometryReader { proxy in
            let m = WatchScoreHoleLayout.metrics(forHeight: proxy.size.height)
            VStack(spacing: m.spacing) {
                header(m)
                scoreBand(m)
                // 推 / 罚 open a full-screen picker (owner feedback 2026-10-11 supersedes README §3
                // 原地上下滚: the in-chip wheel was too small to operate on the wrist).
                HStack(spacing: 6) {
                    wheelChip(.putts, m)
                    wheelChip(.penalty, m)
                }
                if par != 3 {
                    fairwayCells(m)
                }
                Spacer(minLength: 0)
                saveButton(m)
            }
            .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
            .padding(.top, 3)
            .padding(.bottom, 7)
            .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            .overlay {
                if let openWheel {
                    wheelPicker(openWheel, size: proxy.size)
                        .transition(.opacity)
                }
            }
        }
        // The title already reserves the top-right clock lane.
        .ignoresSafeArea(edges: .top)
        .focusable()
        .digitalCrownRotation($crown, from: -1_000, through: 1_000, by: 1, sensitivity: .low,
                              isContinuous: true, isHapticFeedbackEnabled: true)
        .onChange(of: crown) { _, value in
            let steps = Int((value - crownBase).rounded())
            guard steps != 0 else { return }
            crownBase += Double(steps)
            wheelSettled = false
            step(steps)
        }
        .task(id: wheelIdentity) {
            // An open wheel closes once left alone ("停手即选定并收起").
            guard openWheel != nil, !holdsOpenWheel, !wheelDragging else { return }
            try? await Task.sleep(nanoseconds: WatchScoreHoleLayout.wheelCloseDelayNanoseconds(settled: wheelSettled))
            guard !Task.isCancelled else { return }
            wheelDrag = 0
            withAnimation(.easeOut(duration: 0.2)) { openWheel = nil }
        }
        .animation(.spring(response: 0.28, dampingFraction: 0.8), value: score)
    }

    /// Changes whenever the open wheel or its value changes, restarting the close timer.
    private var wheelIdentity: String {
        switch openWheel {
        case .putts: return "putts-\(putts)-\(wheelSettled)-\(wheelDragging)"
        case .penalty: return "penalty-\(penalty)-\(wheelSettled)-\(wheelDragging)"
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

    private func header(_ m: WatchScoreHoleLayout.Metrics) -> some View {
        HStack(spacing: 5) {
            Button(action: onCancel) {
                Image(systemName: "chevron.backward")
                    .font(.system(size: 17, weight: .black))
                    .frame(width: m.header, height: m.header)
                    .contentShape(Rectangle().inset(by: -8))
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
        .frame(height: m.header)
    }

    // MARK: 总杆 band

    private func scoreBand(_ m: WatchScoreHoleLayout.Metrics) -> some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: 0) {
                ForEach(-2...2, id: \.self) { offset in
                    let value = score + offset
                    // Audit #417: five equal columns clipped a two-digit total to "…"; the centre
                    // column is sized for two digits and every number may shrink rather than clip.
                    Text(WatchScoreRules.scoreRange.contains(value) ? "\(value)" : "")
                        .font(.system(size: offset == 0 ? m.bandFont : (abs(offset) == 1 ? m.bandFont * 0.48 : m.bandFont * 0.32),
                                      weight: .black, design: .rounded))
                        .monospacedDigit()
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                        .foregroundStyle(.white.opacity(offset == 0 ? 1 : (abs(offset) == 1 ? 0.45 : 0.2)))
                        .frame(minWidth: offset == 0 ? m.bandFont * 1.3 : 0, maxWidth: offset == 0 ? m.bandFont * 1.3 : .infinity)
                        .onTapGesture { if offset != 0 { onScore(value) } }
                }
            }
            .offset(x: bandDrag)
            .frame(height: m.band)
            .contentShape(Rectangle())
            .gesture(
                // Left/right like the band itself, and up/down too (README §3: 上下拖也可).
                DragGesture(minimumDistance: 6)
                    .onChanged { bandDrag = WatchScoreHoleLayout.bandTravel($0.translation) }
                    .onEnded { value in
                        bandDrag = 0
                        let steps = WatchScoreHoleLayout.bandSteps(value.translation)
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

    private func wheelChip(_ wheel: WatchScoreWheel, _ m: WatchScoreHoleLayout.Metrics) -> some View {
        let value = wheel == .putts ? putts : penalty
        let name = wheel == .putts ? "推杆" : "罚杆"
        // Owner feedback 2026-10-11 supersedes README §3 "原地上下滚": the chip only shows the value;
        // a tap opens the full-screen picker (`wheelPicker`), which a gloved finger can operate.
        return HStack(spacing: 4) {
            Text(wheel == .putts ? "推" : "罚")
                .font(.system(size: 15, weight: .heavy))
                .foregroundStyle(.secondary)
            Text("\(value)")
                .font(.system(size: m.chip * 0.6, weight: .black, design: .rounded))
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity)
        .frame(height: m.chip)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.2)))
        .contentShape(Rectangle())
        .onTapGesture {
            wheelSettled = false
            withAnimation(.easeOut(duration: 0.2)) { openWheel = wheel }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(name) \(value)")
        .accessibilityAddTraits(.isButton)
        .accessibilityAdjustableAction { direction in
            let delta = direction == .increment ? 1 : -1
            if wheel == .putts { onPutts(putts + delta) } else { onPenalty(penalty + delta) }
        }
        .accessibilityIdentifier("watch-score-\(wheel.rawValue)")
    }

    /// The open putts / penalties picker, full screen: a large value with its neighbours, big − / +
    /// buttons, a vertical drag anywhere on the sheet, the Crown, and 完成.
    private func wheelPicker(_ wheel: WatchScoreWheel, size: CGSize) -> some View {
        let value = wheel == .putts ? putts : penalty
        let range = wheel == .putts ? WatchScoreRules.puttRange : WatchScoreRules.penaltyRange
        let name = wheel == .putts ? "推杆" : "罚杆"
        let compact = size.height < WatchScoreHoleLayout.compactHeight
        let digit: CGFloat = compact ? 50 : 64
        let button: CGFloat = compact ? 44 : 50
        return ZStack {
            Color.black // opaque: the score screen underneath must not show through
            VStack(spacing: compact ? 2 : 4) {
                Text(name)
                    .font(.system(size: 17, weight: .black))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.trailing, WatchScoreHoleLayout.systemTimeTrailingClearance)
                HStack(spacing: 4) {
                    pickerStep("minus", label: "\(name)减一", size: button) { nudge(-1) }
                    VStack(spacing: 0) {
                        ForEach(-1...1, id: \.self) { offset in
                            Text("\(WatchScoreRules.wrap(value + offset, in: range))")
                                .font(.system(size: offset == 0 ? digit : digit * 0.4, weight: .black, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(.white.opacity(offset == 0 ? 1 : 0.4))
                        }
                    }
                    .offset(y: wheelDrag)
                    .frame(maxWidth: .infinity)
                    pickerStep("plus", label: "\(name)加一", size: button) { nudge(1) }
                }
                .frame(maxHeight: .infinity)
                Button {
                    withAnimation(.easeOut(duration: 0.2)) { openWheel = nil }
                } label: {
                    Text("完成")
                        .font(.system(size: 17, weight: .black))
                        .foregroundStyle(.black)
                        .frame(maxWidth: .infinity)
                        .frame(height: button)
                        .background(Capsule().fill(AICaddieDesignTokens.par))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch-score-wheel-done")
            }
            .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
            .padding(.top, 3)
            .padding(.bottom, 7)
        }
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 6)
                .onChanged { drag in
                    wheelSettled = false
                    wheelDragging = true
                    wheelDrag = WatchScoreHoleLayout.wheelPeek(drag.translation.height)
                }
                .onEnded { drag in
                    wheelDragging = false
                    wheelDrag = 0
                    let steps = WatchScoreHoleLayout.wheelSteps(drag.translation.height)
                    if steps != 0 { step(steps) }
                    wheelSettled = true
                }
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(name) \(value)")
        .accessibilityIdentifier("watch-score-wheel-\(wheel.rawValue)")
    }

    private func nudge(_ delta: Int) {
        wheelSettled = false
        step(delta)
    }

    private func pickerStep(_ symbol: String, label: String, size: CGFloat, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: size * 0.42, weight: .black))
                .foregroundStyle(.white)
                .frame(width: size, height: size)
                .background(Circle().fill(Color.white.opacity(0.22)))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }

    // MARK: 开球三格

    private func fairwayCells(_ m: WatchScoreHoleLayout.Metrics) -> some View {
        HStack(spacing: 5) {
            fairwayCell("左", .left, m)
            fairwayCell("中", .hit, m)
            fairwayCell("右", .right, m)
        }
    }

    private func fairwayCell(_ label: String, _ result: WatchFairwayResult, _ m: WatchScoreHoleLayout.Metrics) -> some View {
        Button { onFairway(result) } label: {
            Text(label)
                .font(.system(size: 15, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .frame(height: m.cell)
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

    private func saveButton(_ m: WatchScoreHoleLayout.Metrics) -> some View {
        Button(action: onSave) {
            Text("保存 \(score) 杆")
                .font(.system(size: 17, weight: .black))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .buttonStyle(.plain)
        .frame(height: m.save)
        .background(Capsule().fill(AICaddieDesignTokens.par))
        .accessibilityIdentifier("watch-score-save")
    }
}
