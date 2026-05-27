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
