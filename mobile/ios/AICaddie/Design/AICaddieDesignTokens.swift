import SwiftUI

public enum AICaddieDesignTokens {
    public static let par = Color(red: 0.10, green: 0.44, blue: 0.25)
    public static let birdie = Color(red: 0.18, green: 0.57, blue: 0.84)
    public static let eagle = Color(red: 0.04, green: 0.23, blue: 0.62)
    public static let bogey = Color(red: 0.74, green: 0.45, blue: 0.13)
    public static let doubleBogey = Color(red: 0.70, green: 0.16, blue: 0.12)
    public static let neutral = Color(red: 0.36, green: 0.39, blue: 0.43)
    public static let offline = Color(red: 0.56, green: 0.45, blue: 0.18)

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
        return doubleBogey
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

    /// Colour a strategy/route by SEMANTICS, matching both the offline option ids (safe/stock/attack)
    /// and the live decision route ids (conservative_layup / stock_line / aggressive_line) — the old
    /// exact-match switch left every live route neutral.
    public static func strategyColor(_ strategy: String) -> Color {
        let s = strategy.lowercased()
        if s.contains("attack") || s.contains("aggressive") || s.contains("go_for") {
            return eagle
        }
        if s.contains("safe") || s.contains("conservative") || s.contains("protect") || s.contains("layup") || s.contains("lay_up") {
            return par
        }
        if s.contains("stock") || s.contains("standard") || s.contains("neutral") {
            return birdie
        }
        return neutral
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
