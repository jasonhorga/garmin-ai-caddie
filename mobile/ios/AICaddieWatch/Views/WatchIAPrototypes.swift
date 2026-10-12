#if DEBUG
import SwiftUI

// Prototypes for the owner-approved Watch information-architecture review (2026-10-12): the hole
// face, a Golfshot-style score screen and the end-of-nine turn. DEBUG only: rendered at
// 40/41/42/45/46/49 mm by `WatchDesignSnapshotTests` and routed by `-uitest-screen proto-*` for the
// #417 element harness. Nothing here is wired into a round; production views are unchanged.

/// The bottom strip of every face where touches arrive but fire no control (#417, watchOS 26.2).
public enum WatchProtoFace {
    /// Bottom safe-area inset in points by face height. 41/46/49 mm are measured; 40/42/45 mm are
    /// estimates until the harness measures them.
    public static func bottomInset(forHeight height: CGFloat) -> CGFloat {
        switch height {
        case ..<206: return 24     // 40 mm (estimate)
        case ..<219: return 26     // 41 mm (measured)
        case ..<232: return 30     // 42 / 44 mm (estimate)
        case ..<245: return 35     // 45 mm (estimate)
        case ..<249.5: return 36   // 46 mm (measured)
        default: return 39         // 49 mm (measured)
        }
    }

    static let edgeInset: CGFloat = 10
    static let controlHit: CGFloat = 50
}

/// Full-window canvas that hands its content the window size and the lowest y a control may use.
/// Snapshots pass the inset explicitly (ImageRenderer has no safe area); a running app reads it.
struct WatchProtoCanvas<Content: View>: View {
    let bottomInset: CGFloat?
    let showsGuide: Bool
    let content: (CGSize, CGFloat) -> Content

    init(bottomInset: CGFloat?, showsGuide: Bool, @ViewBuilder content: @escaping (CGSize, CGFloat) -> Content) {
        self.bottomInset = bottomInset
        self.showsGuide = showsGuide
        self.content = content
    }

    var body: some View {
        GeometryReader { outer in
            let inset = bottomInset ?? outer.safeAreaInsets.bottom
            GeometryReader { full in
                let size = full.size
                let interactiveBottom = size.height - inset
                ZStack(alignment: .topLeading) {
                    content(size, interactiveBottom)
                    if showsGuide {
                        Rectangle()
                            .fill(Color.red.opacity(0.30))
                            .frame(width: size.width, height: max(0, size.height - interactiveBottom))
                            .offset(y: interactiveBottom)
                            .allowsHitTesting(false)
                        Text("点不中")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.white)
                            .position(x: size.width / 2, y: (interactiveBottom + size.height) / 2)
                            .allowsHitTesting(false)
                    }
                }
                .frame(width: size.width, height: size.height, alignment: .topLeading)
            }
            .ignoresSafeArea()
        }
        .background(Color.black.ignoresSafeArea())
    }
}

// MARK: - Hole face

/// The resting hole face: F/M/B and the hole identity top-left with the last-shot distance under it,
/// the map with the player near the bottom (only what is ahead), no blue dot, and two corner
/// controls inside the interactive area: the next-shot club (tap: next plan) and + (mark a shot,
/// hidden when automatic shot detection is on). The golf menu moves to a page above the face.
public struct WatchHoleFacePrototype: View {
    public let autoShotOn: Bool
    public let lastShot: Int
    public let bottomInset: CGFloat?
    public let showsGuide: Bool
    @State private var planIndex = 0
    @State private var shots = 0
    private let plans = ["3W", "5i", "D"]

    public init(autoShotOn: Bool = false, lastShot: Int = 186, bottomInset: CGFloat? = nil, showsGuide: Bool = false) {
        self.autoShotOn = autoShotOn
        self.lastShot = lastShot
        self.bottomInset = bottomInset
        self.showsGuide = showsGuide
    }

    public var body: some View {
        WatchProtoCanvas(bottomInset: bottomInset, showsGuide: showsGuide) { size, interactiveBottom in
            let anchor = min(0.86, max(0.70, (interactiveBottom - 8) / size.height))
            let controlY = interactiveBottom - WatchProtoFace.controlHit / 2
            let chipHeight: CGFloat = size.height < 206 ? 40 : 44
            ZStack(alignment: .topLeading) {
                WatchHoleMapView(
                    lastShot: lastShot,
                    showCaddieRecommendation: true,
                    showPreparedPlan: true,
                    restingPlayerAnchorFraction: anchor,
                    playerMarker: .chevron,
                    lastShotPlacement: .facts,
                    showsRootCaddieChip: false
                )
                .frame(width: size.width, height: size.height)

                Button {
                    planIndex = (planIndex + 1) % plans.count
                } label: {
                    VStack(spacing: 0) {
                        Text(plans[planIndex])
                            .font(.system(size: 19, weight: .black, design: .rounded))
                        Text("\(planIndex + 1)/\(plans.count)")
                            .font(.system(size: 10, weight: .heavy))
                            .opacity(0.75)
                    }
                    .foregroundStyle(.black)
                    .frame(width: 58, height: chipHeight)
                    .background(Capsule().fill(AICaddieDesignTokens.hudGreen))
                    .frame(width: 62, height: WatchProtoFace.controlHit)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("下一杆 \(plans[planIndex])，点按换方案")
                .accessibilityIdentifier("proto-face-plan")
                .position(x: WatchProtoFace.edgeInset + 31, y: controlY)

                if !autoShotOn {
                    Button {
                        shots += 1
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 22, weight: .black))
                            .foregroundStyle(.black)
                            .frame(width: 44, height: 44)
                            .background(Circle().fill(AICaddieDesignTokens.hudGreen))
                            .frame(width: WatchProtoFace.controlHit, height: WatchProtoFace.controlHit)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("记一杆")
                    .accessibilityValue("\(shots)")
                    .accessibilityIdentifier("proto-face-record")
                    .position(x: size.width - WatchProtoFace.edgeInset - WatchProtoFace.controlHit / 2, y: controlY)
                }
            }
        }
    }
}

/// The golf menu as the page above the face (swipe down from the hole): large rows, most used first.
public struct WatchMoreMenuPrototype: View {
    public let bottomInset: CGFloat?
    public let showsGuide: Bool
    private let rows = ["计分卡", "换洞", "本洞记录", "设置", "结束本场"]

    public init(bottomInset: CGFloat? = nil, showsGuide: Bool = false) {
        self.bottomInset = bottomInset
        self.showsGuide = showsGuide
    }

    public var body: some View {
        WatchProtoCanvas(bottomInset: bottomInset, showsGuide: showsGuide) { size, interactiveBottom in
            let top: CGFloat = 34
            let fitting = max(1, Int((interactiveBottom - top) / 48))
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(rows.prefix(fitting)), id: \.self) { row in
                    Text(row)
                        .font(.system(size: 17, weight: .bold))
                        .foregroundStyle(row == "结束本场" ? Color.red : Color.white)
                        .padding(.horizontal, 12)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.14)))
                        .accessibilityIdentifier("proto-menu-\(row)")
                }
            }
            .padding(.horizontal, WatchProtoFace.edgeInset)
            .padding(.top, top)
            .frame(width: size.width, height: size.height, alignment: .top)
        }
    }
}

// MARK: - Score

/// Golfshot-style hole score: 总杆 and 推杆 as two large boxes (tap selects; the − / + row and the
/// Crown change the selected one; putts carry the total along when shots were marked), penalties
/// and the tee result on a secondary sheet, and 保存. Every control sits inside the interactive area.
public struct WatchScoreBoxesPrototype: View {
    public enum Field { case total, putts }

    public let hole: Int
    public let par: Int
    public let bottomInset: CGFloat?
    public let showsGuide: Bool
    @State private var total: Int
    @State private var putts: Int
    @State private var penalty: Int
    @State private var fairway: String
    @State private var selected: Field = .putts
    @State private var showsExtras: Bool
    @State private var crown: Double = 0
    @State private var crownBase: Double = 0

    public init(
        hole: Int = 7,
        par: Int = 4,
        total: Int = 5,
        putts: Int = 2,
        penalty: Int = 0,
        fairway: String = "中",
        showsExtras: Bool = false,
        bottomInset: CGFloat? = nil,
        showsGuide: Bool = false
    ) {
        self.hole = hole
        self.par = par
        self.bottomInset = bottomInset
        self.showsGuide = showsGuide
        _total = State(initialValue: total)
        _putts = State(initialValue: putts)
        _penalty = State(initialValue: penalty)
        _fairway = State(initialValue: fairway)
        _showsExtras = State(initialValue: showsExtras)
    }

    public var body: some View {
        WatchProtoCanvas(bottomInset: bottomInset, showsGuide: showsGuide) { size, interactiveBottom in
            let gap: CGFloat = 4
            let top: CGFloat = 4
            let title: CGFloat = 20
            let row: CGFloat = 44
            let box = max(48, interactiveBottom - top - title - row * 2 - gap * 3)
            ZStack(alignment: .topLeading) {
                VStack(spacing: gap) {
                    HStack(spacing: 6) {
                        // Same identity as the hole face.
                        Text("H\(hole) · P\(par)")
                            .font(.system(size: 15, weight: .black))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                        Text(toParText)
                            .font(.system(size: 15, weight: .black, design: .rounded))
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: total - par))
                        Spacer(minLength: 0)
                    }
                    .frame(height: title)
                    .padding(.trailing, 44)

                    HStack(spacing: 6) {
                        valueBox("总杆", total, field: .total, height: box)
                        valueBox("推杆", putts, field: .putts, height: box)
                    }
                    .frame(height: box)

                    HStack(spacing: 6) {
                        stepButton("minus", label: "减一") { adjust(-1) }
                        stepButton("plus", label: "加一") { adjust(1) }
                    }
                    .frame(height: row)

                    HStack(spacing: 6) {
                        Button { showsExtras = true } label: {
                            Text(par == 3 ? "罚 \(penalty)" : "罚 \(penalty) · \(fairway)")
                                .font(.system(size: 15, weight: .black))
                                .foregroundStyle(.white)
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                                .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.16)))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("proto-score-extras")

                        Button {} label: {
                            Text("保存")
                                .font(.system(size: 17, weight: .black))
                                .foregroundStyle(.black)
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                                .background(Capsule().fill(AICaddieDesignTokens.hudGreen))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("proto-score-save")
                    }
                    .frame(height: row)
                }
                .padding(.horizontal, WatchProtoFace.edgeInset)
                .padding(.top, top)
                .frame(width: size.width, height: size.height, alignment: .top)

                if showsExtras {
                    extrasSheet(size: size, interactiveBottom: interactiveBottom)
                }
            }
        }
        .focusable()
        .digitalCrownRotation($crown, from: -1_000, through: 1_000, by: 1, sensitivity: .low,
                              isContinuous: true, isHapticFeedbackEnabled: true)
        .onChange(of: crown) { _, value in
            let steps = Int((value - crownBase).rounded())
            guard steps != 0 else { return }
            crownBase += Double(steps)
            if showsExtras { penalty = min(max(penalty + steps, 0), 4) } else { adjust(steps) }
        }
    }

    private var toParText: String {
        let diff = total - par
        if diff == 0 { return "E" }
        return diff > 0 ? "+\(diff)" : "\(diff)"
    }

    /// Putts carry the total along (marked shots + putts); the total alone moves only itself. The
    /// total never drops below putts + penalties + 1 and is not capped at 15 (#417 W03).
    private func adjust(_ delta: Int) {
        switch selected {
        case .putts:
            let next = min(max(putts + delta, 0), 6)
            total = min(max(total + (next - putts), 1), 20)
            putts = next
        case .total:
            total = min(max(total + delta, putts + penalty + 1), 20)
        }
    }

    private func valueBox(_ label: String, _ value: Int, field: Field, height: CGFloat) -> some View {
        let isSelected = selected == field
        return VStack(spacing: 0) {
            Text(label)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(.secondary)
            Text("\(value)")
                .font(.system(size: min(56, height * 0.62), weight: .black, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color.white.opacity(isSelected ? 0.20 : 0.12)))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .strokeBorder(isSelected ? AICaddieDesignTokens.hudGreen : Color.clear, lineWidth: 2.5)
        )
        .contentShape(Rectangle())
        .onTapGesture { selected = field }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label) \(value)")
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
        .accessibilityIdentifier(field == .total ? "proto-score-total" : "proto-score-putts")
    }

    private func stepButton(_ symbol: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 20, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.22)))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityIdentifier("proto-score-\(symbol)")
    }

    private func extrasSheet(size: CGSize, interactiveBottom: CGFloat) -> some View {
        VStack(spacing: 6) {
            Text(par == 3 ? "罚杆" : "罚杆 · 开球")
                .font(.system(size: 15, weight: .black))
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.trailing, 44)
            HStack(spacing: 6) {
                stepButton("minus", label: "罚杆减一") { penalty = max(penalty - 1, 0) }
                Text("罚 \(penalty)")
                    .font(.system(size: 22, weight: .black, design: .rounded))
                    .frame(minWidth: 52)
                stepButton("plus", label: "罚杆加一") { penalty = min(penalty + 1, 4) }
            }
            .frame(height: 44)
            if par != 3 {
                HStack(spacing: 6) {
                    ForEach(["左", "中", "右"], id: \.self) { side in
                        Button { fairway = side } label: {
                            Text(side)
                                .font(.system(size: 17, weight: .black))
                                .foregroundStyle(.white)
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                                .background(
                                    RoundedRectangle(cornerRadius: 12)
                                        .fill(fairway == side ? AICaddieDesignTokens.par : Color.white.opacity(0.16))
                                )
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("proto-score-fairway-\(side)")
                    }
                }
                .frame(height: 44)
            }
            Button { showsExtras = false } label: {
                Text("完成")
                    .font(.system(size: 17, weight: .black))
                    .foregroundStyle(.black)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Capsule().fill(AICaddieDesignTokens.hudGreen))
            }
            .buttonStyle(.plain)
            .frame(height: 44)
            .accessibilityIdentifier("proto-score-extras-done")
        }
        .padding(.horizontal, WatchProtoFace.edgeInset)
        .padding(.top, 4)
        .frame(width: size.width, height: size.height, alignment: .top)
        .background(Color.black)
    }
}

// MARK: - End of nine

/// After the ninth hole's score is saved, on every course shape: continue with the usual next nine
/// (one tap), pick another nine, or end the round with nine holes. Never a dead end (S70 ends the
/// round at nine and a different back nine needs a new round).
public struct WatchNineTurnPrototype: View {
    public let bottomInset: CGFloat?
    public let showsGuide: Bool
    @State private var showsAll: Bool
    @State private var next = "B 场"
    private let others = ["C 场", "A 场（再打一次）"]

    public init(showsAll: Bool = false, bottomInset: CGFloat? = nil, showsGuide: Bool = false) {
        self.bottomInset = bottomInset
        self.showsGuide = showsGuide
        _showsAll = State(initialValue: showsAll)
    }

    public var body: some View {
        WatchProtoCanvas(bottomInset: bottomInset, showsGuide: showsGuide) { size, _ in
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("A 场打完")
                        .font(.system(size: 14, weight: .heavy))
                        .foregroundStyle(.secondary)
                    Text("42 杆 +6")
                        .font(.system(size: 18, weight: .black, design: .rounded))
                }
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(height: 24)
                .padding(.trailing, 40)
                if showsAll {
                    ForEach(others, id: \.self) { option in
                        row(option, filled: false, id: "proto-turn-\(option)") {
                            next = option
                            showsAll = false
                        }
                    }
                } else {
                    row("继续 \(next)", filled: true, id: "proto-turn-continue") {}
                    row("换一个 9 洞", filled: false, id: "proto-turn-change") { showsAll = true }
                }
                row("结束本场 · 9 洞", filled: false, id: "proto-turn-finish") {}
            }
            .padding(.horizontal, WatchProtoFace.edgeInset)
            .padding(.top, 4)
            .frame(width: size.width, height: size.height, alignment: .top)
        }
    }

    private func row(_ title: String, filled: Bool, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 16, weight: .black))
                .foregroundStyle(filled ? Color.black : Color.white)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(filled ? AICaddieDesignTokens.hudGreen : Color.white.opacity(0.16))
                )
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }
}
#endif
