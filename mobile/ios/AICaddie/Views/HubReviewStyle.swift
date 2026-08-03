import SwiftUI

// Light iOS-native design language for the OFF-COURSE 首页 / 复盘 screens (下场后用).
// Distinct from the DARK 打球屏 (LivePlayStyle): systemGroupedBackground gray base + white
// grouped-inset cards with generous padding + a subtle shadow (no hard borders), SF big-number
// hierarchy, tabular figures. Mirrors the approved `ios_light.html` mockup. Pure presentation —
// no state / networking — so the CI ImageRenderer + window snapshots capture it cleanly.
enum HubStyle {
    /// systemGroupedBackground (light) = #f2f2f7.
    static let grouped = Color(red: 242 / 255, green: 242 / 255, blue: 247 / 255)
    /// Green-tint square behind a tile's line icon = #e8f5ec.
    static let iconTint = Color(red: 232 / 255, green: 245 / 255, blue: 236 / 255)
    /// Faint green ring around the in-progress hero card = #dcefe2.
    static let heroBorder = Color(red: 220 / 255, green: 239 / 255, blue: 226 / 255)
    /// The pulsing "进行中" dot (system green) = #34c759.
    static let liveDot = Color(red: 52 / 255, green: 199 / 255, blue: 89 / 255)
    static let neutralInk = Color(red: 0.36, green: 0.39, blue: 0.43)

    // Score-token colours in the approved LIGHT palette. Paired with a SHAPE (circle / square /
    // triangle) so a score reads without relying on colour alone (design-system §一).
    static let eagle = Color(red: 7 / 255, green: 89 / 255, blue: 133 / 255)    // #075985
    static let birdie = Color(red: 3 / 255, green: 105 / 255, blue: 161 / 255)  // #0369a1
    static let par = Color(red: 22 / 255, green: 163 / 255, blue: 74 / 255)     // #16a34a
    static let bogey = Color(red: 161 / 255, green: 98 / 255, blue: 7 / 255)    // #a16207
    static let double = Color(red: 194 / 255, green: 65 / 255, blue: 12 / 255)  // #c2410c
    static let triple = Color(red: 154 / 255, green: 52 / 255, blue: 18 / 255)  // #9a3412
    /// Warm accent for a bad to-par readout (mockup `--orange`).
    static let warmBad = double
}

extension View {
    /// White grouped-inset card: generous padding, 18pt continuous radius, a subtle drop shadow and
    /// no hard border — the clean light iOS-native surface used across 首页/复盘. (The dark
    /// `liveCard()` bordered look stays on the play screen.)
    func hubCard(padding: CGFloat = 16) -> some View {
        self
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .shadow(color: Color.black.opacity(0.05), radius: 3, x: 0, y: 1)
    }
}

/// A small caption-style section label sitting on the gray background above a card (e.g. 上一场).
struct HubSectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text)
            .font(.footnote.weight(.bold))
            .foregroundStyle(.secondary)
            .padding(.leading, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A rounded green icon square (line icon on green-tint, or white icon on solid green when `filled`).
struct HubIconSquare: View {
    let system: String
    var filled: Bool = false
    var body: some View {
        Image(systemName: system)
            .font(.system(size: 18, weight: .semibold))
            .foregroundStyle(filled ? Color.white : LiveHoleStyle.green)
            .frame(width: 38, height: 38)
            .background(filled ? LiveHoleStyle.green : HubStyle.iconTint)
            .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
    }
}

/// 成绩圈方码:分数 + 形状(圈=低于标准杆 ○/◎、方=高于 □/⊡、无框=标准杆、三角=+3 及以上)在
/// 亮色配色下。形状 + 颜色双编码 → 色盲也能读(design-system §一)。
struct ScoreChip: View {
    let score: Int?
    let toPar: Int?
    var size: CGFloat = 30

    private enum Frame { case doubleCircle, circle, none, square, doubleSquare, triangle }

    private var frame: Frame {
        guard let toPar else { return .none }
        switch toPar {
        case ...(-2): return .doubleCircle
        case -1: return .circle
        case 0: return .none
        case 1: return .square
        case 2: return .doubleSquare
        default: return .triangle
        }
    }

    private var color: Color {
        guard let toPar else { return HubStyle.neutralInk }
        switch toPar {
        case ...(-2): return HubStyle.eagle
        case -1: return HubStyle.birdie
        case 0: return HubStyle.par
        case 1: return HubStyle.bogey
        case 2: return HubStyle.double
        default: return HubStyle.triple
        }
    }

    var body: some View {
        ZStack {
            shapeOverlay
            Text(score.map(String.init) ?? "–")
                .font(.system(size: size * (frame == .triangle ? 0.38 : 0.47), weight: .heavy))
                .monospacedDigit()
                .foregroundStyle(color)
                .offset(y: frame == .triangle ? size * 0.07 : 0)
        }
        .frame(width: size, height: size)
    }

    @ViewBuilder private var shapeOverlay: some View {
        switch frame {
        case .none:
            EmptyView()
        case .circle:
            Circle().stroke(color, lineWidth: 2).padding(2)
        case .doubleCircle:
            ZStack {
                Circle().stroke(color, lineWidth: 2).padding(1)
                Circle().stroke(color, lineWidth: 2).padding(5)
            }
        case .square:
            RoundedRectangle(cornerRadius: 3, style: .continuous).stroke(color, lineWidth: 2).padding(3)
        case .doubleSquare:
            ZStack {
                RoundedRectangle(cornerRadius: 3, style: .continuous).stroke(color, lineWidth: 2).padding(1)
                RoundedRectangle(cornerRadius: 2, style: .continuous).stroke(color, lineWidth: 2).padding(5)
            }
        case .triangle:
            ScoreTriangle().stroke(color, style: StrokeStyle(lineWidth: 2, lineJoin: .round)).padding(2)
        }
    }
}

/// An upward triangle used by the triple-bogey-or-worse score chip.
struct ScoreTriangle: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.midX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        p.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        p.closeSubpath()
        return p
    }
}
