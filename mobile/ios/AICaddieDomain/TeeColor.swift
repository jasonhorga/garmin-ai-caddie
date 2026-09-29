import Foundation

/// The one tee-box colour mapping (README §8: tees are coloured dots), shared by the phone's
/// 开始一场 tee row and the Watch round setup. It returns plain RGB components so the framework stays
/// UI-free; each target builds its own `Color` from them.
public struct TeeColor: Equatable, Hashable, Sendable {
    public let red: Double
    public let green: Double
    public let blue: Double

    public init(red: Double, green: Double, blue: Double) {
        self.red = red
        self.green = green
        self.blue = blue
    }

    /// A near-white dot needs an outline on a light surface.
    public var isLight: Bool {
        0.299 * red + 0.587 * green + 0.114 * blue > 0.8
    }

    public static let blueTee = TeeColor(red: 0.184, green: 0.435, blue: 0.839)   // #2F6FD6
    public static let whiteTee = TeeColor(red: 0.957, green: 0.965, blue: 0.949)  // #F4F6F2
    public static let redTee = TeeColor(red: 0.839, green: 0.271, blue: 0.227)    // #D6453A
    public static let goldTee = TeeColor(red: 0.851, green: 0.647, blue: 0.125)   // #D9A520
    public static let yellowTee = TeeColor(red: 0.949, green: 0.788, blue: 0.298) // #F2C94C
    public static let blackTee = TeeColor(red: 0.25, green: 0.26, blue: 0.25)     // #404240, visible on dark Watch too
    public static let greenTee = TeeColor(red: 0.184, green: 0.620, blue: 0.333)  // #2F9E55
    public static let silverTee = TeeColor(red: 0.722, green: 0.737, blue: 0.753) // #B8BCC0
    /// Unknown / course-default tees.
    public static let unknownTee = TeeColor(red: 0.56, green: 0.58, blue: 0.56)

    /// Colour for a tee-box key (`blue`, `White`, `tee:gold`, …). Unknown keys are neutral grey —
    /// never a guessed colour.
    public static func forTee(_ teeBox: String) -> TeeColor {
        var key = teeBox.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if key.hasPrefix("tee:") {
            key.removeFirst(4)
        }
        switch key {
        case "blue": return .blueTee
        case "white": return .whiteTee
        case "red": return .redTee
        case "gold": return .goldTee
        case "yellow": return .yellowTee
        case "black", "championship", "tips": return .blackTee
        case "green": return .greenTee
        case "silver": return .silverTee
        default: return .unknownTee
        }
    }
}
