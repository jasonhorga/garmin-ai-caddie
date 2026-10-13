import SwiftUI

/// The rows of 本洞成绩 that the − / + buttons and the Crown change.
public enum WatchScoreField: String, CaseIterable, Equatable {
    case total, putts, penalty

    var name: String {
        switch self {
        case .total: return "总杆"
        case .putts: return "推杆"
        case .penalty: return "罚杆"
        }
    }
}

enum WatchScoreHoleLayout {
    static let gap: CGFloat = 4
    static let stepWidth: CGFloat = 46

    /// Three stepper rows and the 开球 / 保存 row share the space between the clock band and the
    /// bottom inset equally (41 mm: 33 pt each; 49 mm: 36 pt), the geometry the #422 audit tapped
    /// 10/10 on every face.
    static func rowHeight(available: CGFloat) -> CGFloat {
        max(28, (available - gap * 3) / 4)
    }
}

/// 本洞成绩 (owner choice 2026-10-12, layout B of the #422 prototypes): 总杆, 推杆 and 罚杆 each on a
/// row with − on the left and + on the right, one tap per change, no picker. The Crown changes the
/// outlined row (the last one touched; 总杆 at first). 开球 (preselected from where the tee shot
/// landed; not on a Par 3) turns its own row into 左 / 中 / 右 in place: one tap picks and the row
/// returns to 开球 / 保存 (owner request 2026-10-13: no separate page).
/// The values follow the rule the phone uses (`HoleScoreValues`, README §3). Presentational and
/// driven by `WatchRoundModel`.
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
    private let snapshotInsets: Bool

    @State private var selected: WatchScoreField
    @State private var showsFairway: Bool
    @State private var crown: Double = 0
    @State private var crownBase: Double = 0

    public init(
        hole: Int,
        par: Int,
        score: Int,
        putts: Int,
        penalty: Int,
        courseDataPending: Bool = false,
        fairway: WatchFairwayResult? = nil,
        candidateNextHole: Int? = nil,
        selected: WatchScoreField = .total,
        showsFairway: Bool = false,
        snapshotInsets: Bool = false,
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
        self._selected = State(initialValue: selected)
        self._showsFairway = State(initialValue: showsFairway && par != 3)
        self.snapshotInsets = snapshotInsets
        self.onScore = onScore
        self.onPutts = onPutts
        self.onPenalty = onPenalty
        self.onFairway = onFairway
        self.onSave = onSave
        self.onCancel = onCancel
    }

    public var body: some View {
        WatchFullWindowCanvas(snapshotInsets: snapshotInsets) { size, safeTop, interactiveBottom in
            let available = interactiveBottom - safeTop
            let row = WatchScoreHoleLayout.rowHeight(available: available)
            ZStack(alignment: .topLeading) {
                watchTitleBand(titleBand, size: size, safeTop: safeTop)
                VStack(spacing: WatchScoreHoleLayout.gap) {
                    ForEach(WatchScoreField.allCases, id: \.self) { field in
                        stepperRow(field, height: row)
                    }
                    bottomRow.frame(height: row)
                }
                .padding(.horizontal, WatchFaceInsets.edge)
                .frame(width: size.width, height: available, alignment: .top)
                .offset(y: safeTop)
            }
        }
        .focusable()
        .digitalCrownRotation($crown, from: -1_000, through: 1_000, by: 1, sensitivity: .low,
                              isContinuous: true, isHapticFeedbackEnabled: true)
        .onChange(of: crown) { _, value in
            let steps = Int((value - crownBase).rounded())
            guard steps != 0 else { return }
            crownBase += Double(steps)
            adjust(selected, by: steps)
        }
    }

    // MARK: title (shares the clock band)

    private var titleBand: some View {
        HStack(spacing: 4) {
            Button(action: onCancel) {
                Image(systemName: "chevron.backward")
                    .font(.system(size: 15, weight: .black))
                    .frame(width: 26, height: 34)
                    .contentShape(Rectangle().inset(by: -8))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("取消记分")
            .accessibilityIdentifier("watch-score-cancel")
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 5) {
                    Text(courseDataPending ? "H\(hole) · 等待球场数据" : "H\(hole) · P\(par)")
                        .font(.system(size: 15, weight: .black))
                    if !courseDataPending {
                        Text(toParText)
                            .font(.system(size: 15, weight: .black, design: .rounded))
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: score - par))
                    }
                }
                if let candidateNextHole {
                    Text("第 \(candidateNextHole) 洞首杆已暂存")
                        .font(.system(size: 12, weight: .heavy))
                        .foregroundStyle(AICaddieDesignTokens.par)
                }
            }
            .lineLimit(1)
            .minimumScaleFactor(0.7)
        }
    }

    private var toParText: String {
        let diff = score - par
        if diff == 0 { return "E" }
        return diff > 0 ? "+\(diff)" : "\(diff)"
    }

    // MARK: rows

    private func value(_ field: WatchScoreField) -> Int {
        switch field {
        case .total: return score
        case .putts: return putts
        case .penalty: return penalty
        }
    }

    private func adjust(_ field: WatchScoreField, by delta: Int) {
        switch field {
        case .total: onScore(score + delta)
        case .putts: onPutts(putts + delta)
        case .penalty: onPenalty(penalty + delta)
        }
    }

    private func stepperRow(_ field: WatchScoreField, height: CGFloat) -> some View {
        HStack(spacing: 4) {
            stepButton("minus", label: "\(field.name)减一", id: "watch-score-\(field.rawValue)-minus") {
                selected = field
                adjust(field, by: -1)
            }
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(field.name)
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(.secondary)
                Text("\(value(field))")
                    .font(.system(size: min(28, height * 0.8), weight: .black, design: .rounded))
                    .monospacedDigit()
                    .contentTransition(.numericText())
            }
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            // The Crown changes the outlined row.
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(selected == field ? AICaddieDesignTokens.hudGreen : Color.clear, lineWidth: 2)
            )
            .contentShape(Rectangle())
            .onTapGesture { selected = field }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(field.name) \(value(field))")
            .accessibilityAddTraits(selected == field ? [.isSelected] : [])
            .accessibilityAdjustableAction { direction in
                adjust(field, by: direction == .increment ? 1 : -1)
            }
            .accessibilityIdentifier("watch-score-\(field.rawValue)")
            stepButton("plus", label: "\(field.name)加一", id: "watch-score-\(field.rawValue)-plus") {
                selected = field
                adjust(field, by: 1)
            }
        }
        .frame(height: height)
    }

    private func stepButton(_ symbol: String, label: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 20, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: WatchScoreHoleLayout.stepWidth, maxHeight: .infinity)
                .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.22)))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityIdentifier(id)
    }

    // MARK: 开球 / 保存

    private var fairwayText: String {
        switch fairway {
        case .left: return "左"
        case .hit: return "中"
        case .right: return "右"
        case nil: return "—"
        }
    }

    @ViewBuilder
    private var bottomRow: some View {
        if showsFairway {
            // 开球 opened in place: the same row offers 左 / 中 / 右; a tap picks and closes it.
            HStack(spacing: 6) {
                fairwayCell("左", .left)
                fairwayCell("中", .hit)
                fairwayCell("右", .right)
            }
        } else {
            chipAndSaveRow
        }
    }

    private var chipAndSaveRow: some View {
        HStack(spacing: 6) {
            if par != 3 {
                Button { showsFairway = true } label: {
                    Text("开球 \(fairwayText)")
                        .font(.system(size: 15, weight: .black))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.16)))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch-score-fairway")
            }
            Button(action: onSave) {
                Text("保存")
                    .font(.system(size: 17, weight: .black))
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Capsule().fill(AICaddieDesignTokens.hudGreen))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("保存 \(score) 杆")
            .accessibilityIdentifier("watch-score-save")
        }
    }

    /// Picking the side already chosen keeps it (the model's tap-to-clear would empty it).
    private func fairwayCell(_ label: String, _ result: WatchFairwayResult) -> some View {
        Button {
            if fairway != result { onFairway(result) }
            showsFairway = false
        } label: {
            Text(label)
                .font(.system(size: 17, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(fairway == result ? AICaddieDesignTokens.par : Color.white.opacity(0.16))
                )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("开球\(label == "中" ? "上球道" : "偏\(label)")")
        .accessibilityAddTraits(fairway == result ? .isSelected : [])
        .accessibilityIdentifier("watch-score-fairway-\(result.rawValue)")
    }
}
