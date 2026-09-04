import SwiftUI

public enum AICaddieDesignTokens {
    public static let par = Color(red: 0.10, green: 0.44, blue: 0.25)
    public static let birdie = Color(red: 0.18, green: 0.57, blue: 0.84)
    public static let eagle = Color(red: 0.04, green: 0.23, blue: 0.62)
    public static let bogey = Color(red: 0.74, green: 0.45, blue: 0.13)
    public static let doubleBogey = Color(red: 0.70, green: 0.16, blue: 0.12)
    public static let neutral = Color(red: 0.36, green: 0.39, blue: 0.43)
    public static let offline = Color(red: 0.56, green: 0.45, blue: 0.18)

    /// High-contrast instrument accents shared by the Watch's in-round HUD. These are intentionally
    /// stronger than the phone palette: the player should recognize the active action at a glance,
    /// in sunlight and while moving, without relying on a tiny explanatory label.
    public static let hudGreen = Color(red: 0.19, green: 0.86, blue: 0.43)
    public static let hudYellow = Color(red: 1.0, green: 0.82, blue: 0.20)
    public static let hudBlue = Color(red: 0.18, green: 0.65, blue: 1.0)
    public static let hudPanel = Color.white.opacity(0.16)

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

/// Geometry shared by every full-screen Watch surface.
///
/// The simulator framebuffer is rectangular, but the physical display is a rounded rectangle.
/// Background imagery may bleed beneath that mask; readable text, controls, markers and callouts
/// must remain inside `contentRect`. The conservative rectangular guide is valid for the 41, 45 and
/// 49 mm displays and also grows if a future Watch has a wider face.
public enum WatchDisplayGeometry {
    public static let minimumContentInset: CGFloat = 10
    public static let cornerRadiusFraction: CGFloat = 0.12

    /// A visible control should feel like a physical instrument button, not a text link. Keep the
    /// target large on the 41 mm face while allowing a little more room on Ultra without letting a
    /// button touch the rounded mask.
    public static let instrumentControlSize: CGFloat = 50

    /// Shared instrument typography/control rhythm. These are deliberately a little larger than
    /// ordinary watchOS list defaults: in a round the watch is read at arm's length and the action
    /// should feel like a physical game control, not a phone-style table row.
    public static let instrumentHeaderFontSize: CGFloat = 19
    public static let instrumentRowFontSize: CGFloat = 18
    public static let instrumentBodyFontSize: CGFloat = 16
    public static let instrumentActionHeight: CGFloat = 48
    public static let instrumentRowHeight: CGFloat = 48
    public static let instrumentVisualControlSize: CGFloat = 40

    public static func instrumentControlSize(for size: CGSize) -> CGFloat {
        min(52, max(instrumentControlSize, min(size.width, size.height) * 0.23))
    }

    public static func cornerRadius(for size: CGSize) -> CGFloat {
        max(0, min(size.width, size.height) * cornerRadiusFraction)
    }

    public static func contentInset(for size: CGSize) -> CGFloat {
        let radius = cornerRadius(for: size)
        // Inset of the largest axis-aligned rectangle inside a quarter circle, plus two points of
        // optical/stroke clearance so anti-aliased glyphs do not sit on the hardware mask.
        let tangentInset = radius * (1 - 1 / CGFloat(2).squareRoot()) + 2
        return ceil(max(minimumContentInset, tangentInset))
    }

    public static func horizontalContentInset(forWidth width: CGFloat) -> CGFloat {
        contentInset(for: CGSize(width: width, height: width * 1.25))
    }

    public static func contentRect(in size: CGSize) -> CGRect {
        let inset = min(contentInset(for: size), max(0, min(size.width, size.height) / 2))
        return CGRect(
            x: inset,
            y: inset,
            width: max(0, size.width - inset * 2),
            height: max(0, size.height - inset * 2)
        )
    }

    /// Testable representation of the physical rounded display mask.
    public static func contains(_ point: CGPoint, in size: CGSize, tolerance: CGFloat = 0) -> Bool {
        guard size.width > 0, size.height > 0,
              point.x >= -tolerance, point.y >= -tolerance,
              point.x <= size.width + tolerance, point.y <= size.height + tolerance else {
            return false
        }
        let radius = cornerRadius(for: size)
        guard radius > 0 else { return true }
        if (radius...(size.width - radius)).contains(point.x)
            || (radius...(size.height - radius)).contains(point.y) {
            return true
        }
        let cornerX = point.x < radius ? radius : size.width - radius
        let cornerY = point.y < radius ? radius : size.height - radius
        return hypot(point.x - cornerX, point.y - cornerY) <= radius + tolerance
    }
}
