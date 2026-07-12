import SwiftUI

/// Watch unified design system (定稿 2026-07-10, `docs/superpowers/specs/2026-07-10-watch-design-system.md`):
/// ONE bright caddie-green accent + ONE ScoreChip colour scale used by every scoring surface (成绩环 /
/// 计分卡 / 洞详情). Colours are the exact spec RGBs. The chip carries a redundant SHAPE channel
/// (circle / square / triangle) so it reads in greyscale and for colour-blind players.
///
/// API is kept backward compatible: every existing call site (`.par` / `.birdie` / `.eagle` / `.bogey`
/// / `.doubleBogey` / `.scoreColor` / `.confidenceColor` / `.strategyColor` / `.riskColor`) still resolves.
public enum AICaddieDesignTokens {
    // MARK: - Unified palette (spec §1: 统一 ScoreChip 色阶 + 亮球童绿)
    /// 球童绿 `#3DDC84` — the single accent (推荐 / 选中 / 主按钮 / 当前打法档) AND par.
    public static let par = Color(red: 0.24, green: 0.86, blue: 0.52)
    /// The one accent colour; alias of `par` so intent reads clearly at call sites.
    public static let accent = par

    public static let eagle = Color(red: 0.12, green: 0.35, blue: 0.88)   // 鹰 深蓝
    public static let birdie = Color(red: 0.24, green: 0.61, blue: 1.0)   // 鸟 浅蓝
    public static let bogey = Color(red: 1.0, green: 0.83, blue: 0.28)    // 柏忌 黄 (= 高尔夫金 #FFD447)
    public static let doubleBogey = Color(red: 1.0, green: 0.54, blue: 0.24) // 双柏忌 橙
    /// Semantic alias for `doubleBogey`.
    public static let double = doubleBogey
    public static let triple = Color(red: 1.0, green: 0.27, blue: 0.23)   // 三柏忌 红
    public static let worse = Color(red: 0.65, green: 0.42, blue: 1.0)    // 更差 紫

    public static let neutral = Color(red: 0.36, green: 0.39, blue: 0.43)
    public static let offline = Color(red: 0.56, green: 0.45, blue: 0.18)

    /// Score → colour. `≤ -2` eagle, `-1` birdie, `0` par, `+1` bogey, `+2` double, `+3` triple, `≥ +4` worse.
    public static func scoreColor(toPar: Int?) -> Color {
        guard let toPar else {
            return neutral
        }
        if toPar <= -2 {
            return eagle
        }
        if toPar == -1 {
            return birdie
        }
        if toPar == 0 {
            return par
        }
        if toPar == 1 {
            return bogey
        }
        if toPar == 2 {
            return doubleBogey
        }
        if toPar == 3 {
            return triple
        }
        return worse
    }

    // MARK: - ScoreChip shape encoding (spec §1: 圈 ○ / 方 □ / 三角 △ 形状冗余)
    /// The redundant shape channel for a score, so the chip is legible without colour.
    /// 鹰/鸟 = 圈 (eagle 双环), Par = 无框, 柏忌/双柏忌 = 方 (双柏忌 双框), 三柏忌/更差 = 三角.
    public enum ScoreChipShape: Equatable {
        case none       // par — number only, no frame
        case circle     // birdie / eagle
        case square     // bogey / double
        case triangle   // triple / worse
    }

    public static func scoreChipShape(toPar: Int?) -> ScoreChipShape {
        guard let toPar else {
            return .none
        }
        if toPar <= -1 {
            return .circle
        }
        if toPar == 0 {
            return .none
        }
        if toPar <= 2 {
            return .square
        }
        return .triangle
    }

    /// The two extreme bands (eagle ◎ / double ⊡) get a second inner outline to set them apart from
    /// their same-shape neighbour (birdie ○ / bogey □) even in greyscale.
    public static func scoreChipDoubled(toPar: Int?) -> Bool {
        guard let toPar else {
            return false
        }
        return toPar <= -2 || toPar == 2
    }

    public static func confidenceColor(_ confidence: String) -> Color {
        switch confidence.lowercased() {
        case "high", "ready":
            return par
        case "medium":
            return bogey
        case "offline":
            return offline
        default:
            return doubleBogey
        }
    }

    public static func strategyColor(_ strategy: String) -> Color {
        switch strategy.lowercased() {
        case "safe", "protect", "protect_score":
            return par
        case "attack":
            return eagle
        case "stock":
            return birdie
        default:
            return neutral
        }
    }

    public static func riskColor(_ riskScore: Double) -> Color {
        if riskScore >= 4 {
            return doubleBogey
        }
        if riskScore >= 2 {
            return bogey
        }
        return par
    }
}

/// The colour-blind-safe score chip: the number in its score colour, wrapped in a shape that encodes the
/// score band as a redundant channel (design-system §1). Built from plain `Shape`s (no lazy container) so
/// it renders in `ImageRenderer` CI snapshots.
public struct ScoreChipView: View {
    public let toPar: Int?
    public let text: String
    public let diameter: CGFloat

    public init(toPar: Int?, text: String, diameter: CGFloat = 26) {
        self.toPar = toPar
        self.text = text
        self.diameter = diameter
    }

    public var body: some View {
        let color = AICaddieDesignTokens.scoreColor(toPar: toPar)
        let shape = AICaddieDesignTokens.scoreChipShape(toPar: toPar)
        let doubled = AICaddieDesignTokens.scoreChipDoubled(toPar: toPar)
        ZStack {
            chipFrame(shape, doubled: doubled, color: color)
            Text(text)
                .font(.system(size: diameter * 0.46, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(color)
        }
        .frame(width: diameter, height: diameter)
    }

    @ViewBuilder
    private func chipFrame(_ shape: AICaddieDesignTokens.ScoreChipShape, doubled: Bool, color: Color) -> some View {
        switch shape {
        case .none:
            EmptyView()
        case .circle:
            Circle().stroke(color, lineWidth: 1.8)
            if doubled {
                Circle().stroke(color, lineWidth: 1.2).padding(4)
            }
        case .square:
            RoundedRectangle(cornerRadius: 4).stroke(color, lineWidth: 1.8)
            if doubled {
                RoundedRectangle(cornerRadius: 2).stroke(color, lineWidth: 1.2).padding(4)
            }
        case .triangle:
            ScoreChipTriangle().stroke(color, style: StrokeStyle(lineWidth: 1.8, lineJoin: .round))
        }
    }
}

/// An upward triangle inset to sit inside the chip's square bounds (used by 三柏忌 / 更差).
public struct ScoreChipTriangle: Shape {
    public init() {}
    public func path(in rect: CGRect) -> Path {
        var p = Path()
        let inset: CGFloat = 1.5
        p.move(to: CGPoint(x: rect.midX, y: rect.minY + inset))
        p.addLine(to: CGPoint(x: rect.maxX - inset, y: rect.maxY - inset))
        p.addLine(to: CGPoint(x: rect.minX + inset, y: rect.maxY - inset))
        p.closeSubpath()
        return p
    }
}
