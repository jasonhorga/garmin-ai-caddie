import Foundation

/// Display-only normalization for raw Garmin/backend club tokens on the independent Watch target.
/// Event payloads keep their original value; every customer-facing Watch surface uses this copy.
enum WatchClubDisplay {
    private static let chineseNumber = [
        "1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
        "6": "六", "7": "七", "8": "八", "9": "九",
    ]

    static func name(_ raw: String) -> String {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return value }
        let lower = value.lowercased()

        if let degrees = Int(value), (44...64).contains(degrees) {
            return "\(degrees)° 挖起杆"
        }
        if lower.hasPrefix("wedge"),
           let degrees = Int(lower.dropFirst("wedge".count)),
           (44...64).contains(degrees) {
            return "\(degrees)° 挖起杆"
        }
        if lower == "driver" || lower == "d" || lower == "1w" { return "一号木" }
        if value.contains("小鸡腿") && !value.contains(where: \.isNumber) { return value }
        if lower.contains("hybrid") || lower.contains("rescue") || lower.hasSuffix("h") {
            return numbered(value, suffix: "号小鸡腿") ?? "小鸡腿"
        }

        // Wedge abbreviations also end in "w". Resolve them before the generic fairway-wood
        // branch so PW/GW/SW/LW do not leak through as raw backend tokens.
        switch lower.replacingOccurrences(of: " ", with: "") {
        case "pw", "p", "pwedge", "p杆": return "P 杆"
        case "gw", "aw", "a", "ap", "gap", "a杆": return "A 杆"
        case "sw", "s", "sand", "s杆": return "S 杆"
        case "lw", "l", "lob", "l杆": return "L 杆"
        case "putter", "putt", "pt", "推杆": return "推杆"
        default: break
        }
        if lower.hasPrefix("wood") || lower.hasSuffix("w") || value.contains("号木") {
            return numbered(value, suffix: "号木") ?? value
        }
        if lower.hasPrefix("iron") || lower.hasSuffix("i") || value.contains("号铁") {
            return numbered(value, suffix: "号铁") ?? value
        }

        return value
    }

    /// The hole-map recommendation card is intentionally narrow beside the map. A loft already
    /// identifies a wedge unambiguously, so prefer `50°` there instead of rendering `50...`.
    /// Full club prompts and statistics continue to use the complete Chinese display name.
    static func compactMapName(_ raw: String) -> String {
        let display = name(raw)
        let loft = display.prefix { $0.isNumber || $0 == "°" }
        guard loft.hasSuffix("°"),
              !loft.dropLast().isEmpty,
              loft.dropLast().allSatisfy(\.isNumber) else {
            return display
        }
        return String(loft)
    }

    private static func numbered(_ value: String, suffix: String) -> String? {
        guard let digit = value.first(where: \.isNumber).map(String.init) else { return nil }
        return "\(chineseNumber[digit] ?? digit)\(suffix)"
    }
}
