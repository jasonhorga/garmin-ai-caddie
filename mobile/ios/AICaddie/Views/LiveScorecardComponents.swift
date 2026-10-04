import SwiftUI

/// Scorecard titles for a live round's loops (B4b-2): "第一环 · 后九", "第二环 · A 场".
enum LiveScorecardLoops {
    static let ordinals = ["第一环", "第二环"]

    static func titles(package: LiveRoundPackage, catalogue: [MobileCourseOption]) -> [String] {
        package.roundLoops.prefix(ordinals.count).enumerated().map { index, loop in
            "\(ordinals[index]) · \(NineLoopTurn.loopName(loop, catalogue: catalogue))"
        }
    }

    static func title(_ titles: [String], index: Int) -> String {
        index < titles.count ? titles[index] : ordinals[min(index, ordinals.count - 1)]
    }
}

/// The two facts a scorecard column needs; live rounds build it from `Hole`, the review from the
/// round detail's scorecard.
struct ScorecardHole: Identifiable, Equatable {
    let number: Int
    let par: Int
    /// The number the course prints (B4b-2 `courseHoleNumber`); `number` stays the round-hole key.
    var displayNumber: Int? = nil
    var id: Int { number }
}

/// One nine of the scorecard (`score.html`): hole numbers, pars and score symbols in a grid with an
/// OUT / IN subtotal. Shared by the live scorecard, the round summary and the round review.
struct LiveNineCard: View {
    let label: String
    /// The loop's name above the grid ("第一环 · 后九"); nil keeps the OUT / IN-only card.
    var title: String? = nil
    let holes: [ScorecardHole]
    let scores: [Int: LiveHoleScore]
    var currentHole: Int? = nil
    var selectedHole: Int? = nil
    var onSelect: ((Int) -> Void)? = nil
    /// Accessibility id of a tappable score cell (the review keeps `round-review-hole-N`).
    var cellIdentifier: ((Int) -> String)? = nil
    /// Holes whose cell can be tapped; others render as blank, disabled cells (an unplayed hole of a
    /// 9-of-18 review). nil ⇒ every cell is tappable.
    var canSelect: ((Int) -> Bool)? = nil

    init(
        label: String,
        holes: [ScorecardHole],
        scores: [Int: LiveHoleScore],
        currentHole: Int? = nil,
        selectedHole: Int? = nil,
        onSelect: ((Int) -> Void)? = nil,
        cellIdentifier: ((Int) -> String)? = nil,
        canSelect: ((Int) -> Bool)? = nil
    ) {
        self.label = label
        self.holes = holes
        self.scores = scores
        self.currentHole = currentHole
        self.selectedHole = selectedHole
        self.onSelect = onSelect
        self.cellIdentifier = cellIdentifier
        self.canSelect = canSelect
    }

    /// A live round's loop: titled by the loop in play order, columns show `courseHoleNumber`, and
    /// the subtotal is "合计" — a physical half is never relabelled OUT / IN (B4b-2).
    init(
        title: String,
        holes: [Hole],
        scores: [Int: LiveHoleScore],
        currentHole: Int? = nil,
        selectedHole: Int? = nil,
        onSelect: ((Int) -> Void)? = nil
    ) {
        self.init(
            label: "合计",
            holes: holes.map {
                ScorecardHole(number: $0.number, par: $0.par, displayNumber: $0.courseHoleNumber)
            },
            scores: scores,
            currentHole: currentHole,
            selectedHole: selectedHole,
            onSelect: onSelect
        )
        self.title = title
    }

    private var subtotal: Int? {
        let recorded = holes.compactMap { scores[$0.number]?.score }
        return recorded.isEmpty ? nil : recorded.reduce(0, +)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let title {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .padding(.horizontal, 4)
                    .accessibilityAddTraits(.isHeader)
            }
            grid
        }
    }

    private var grid: some View {
        Grid(horizontalSpacing: 2, verticalSpacing: 4) {
            GridRow {
                Text("洞").gridLabel()
                ForEach(holes) { hole in
                    Text("\(hole.displayNumber ?? hole.number)")
                        .font(.system(size: 12, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(hole.number == currentHole ? LiveScoreStyle.good : LivePlayStyle.ink60)
                        .accessibilityIdentifier("live-scorecard-hole-index-\(hole.number)")
                }
                Text(label)
                    .font(.system(size: 10.5, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            GridRow {
                Text("Par").gridLabel()
                ForEach(holes) { hole in
                    Text("\(hole.par)")
                        .font(.system(size: 11))
                        .monospacedDigit()
                        .foregroundStyle(LivePlayStyle.ink45)
                }
                Text("\(holes.reduce(0) { $0 + $1.par })")
                    .font(.system(size: 11))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink45)
            }
            GridRow {
                Text("成绩").gridLabel()
                ForEach(holes) { hole in
                    cell(hole)
                }
                Text(subtotal.map(String.init) ?? "—")
                    .font(.system(size: 14, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink)
                    .accessibilityLabel("\(label) \(subtotal.map { "\($0) 杆" } ?? "未记")")
            }
        }
        .padding(.horizontal, 10)
        .padding(.top, 12)
        .padding(.bottom, 10)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(LivePlayStyle.stroke14, lineWidth: 0.5))
    }

    @ViewBuilder
    private func cell(_ hole: ScorecardHole) -> some View {
        let content = Group {
            if let score = scores[hole.number]?.score {
                ScoreChip(score: score, toPar: score - hole.par, size: 26, dark: true)
                    .accessibilityIdentifier("live-scorecard-score-chip-\(hole.number)")
            } else {
                Text("–")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink45)
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: 38)
        .background(
            hole.number == selectedHole ? Color.white.opacity(0.16) : Color.clear,
            in: RoundedRectangle(cornerRadius: 10, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(hole.number == currentHole ? LiveScoreStyle.good.opacity(0.8) : .clear, lineWidth: 1.2)
        )
        if let onSelect {
            let enabled = canSelect?(hole.number) ?? true
            let button = Button { onSelect(hole.number) } label: { content }
                .buttonStyle(.plain)
                .disabled(!enabled)
                .accessibilityLabel(cellLabel(hole))
                .accessibilityAddTraits(hole.number == selectedHole ? [.isSelected] : [])
            // An identifier on the button replaces the ones inside it, so only callers that need a
            // cell id (the review's `round-review-hole-N`) set one; the live scorecard keeps its
            // `live-scorecard-score-chip-N` on the score symbol.
            if let cellIdentifier {
                button.accessibilityIdentifier(cellIdentifier(hole.number))
            } else {
                button
            }
        } else {
            content
        }
    }
}

private extension LiveNineCard {
    func cellLabel(_ hole: ScorecardHole) -> String {
        guard cellIdentifier != nil else { return "选择第 \(hole.number) 洞" }
        guard let score = scores[hole.number] else { return "第 \(hole.number) 洞，未记" }
        return "第 \(hole.number) 洞，\(score.score) 杆，\(ScoreChip.name(toPar: score.score - hole.par))"
    }
}

/// One summary tile (球道命中 / GIR / 推杆 / 罚杆), shared by the round summary and the review.
struct LiveSummaryTile: View {
    let title: String
    let value: String?
    let detail: String?
    let identifier: String

    var body: some View {
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
}

private extension Text {
    func gridLabel() -> some View {
        self
            .font(.system(size: 10.5, weight: .semibold))
            .foregroundStyle(LivePlayStyle.ink45)
            .frame(width: 30, alignment: .leading)
    }
}

/// `score.html` status colours on the dark live surfaces.
enum LiveScoreStyle {
    static let good = Color(red: 0.361, green: 0.769, blue: 0.498)
    static let bad = Color(red: 1.0, green: 0.420, blue: 0.369)
    static let primaryFill = Color(red: 0.957, green: 0.965, blue: 0.949)
    static let primaryInk = Color(red: 0.043, green: 0.059, blue: 0.047)

    static func toParColor(_ value: Int) -> Color {
        if value < 0 { return ScoreChip.darkColor(toPar: -1) }
        if value == 0 { return ScoreChip.darkColor(toPar: 0) }
        return value <= 5 ? ScoreChip.darkColor(toPar: 1) : ScoreChip.darkColor(toPar: 2)
    }
}
