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

    /// Garmin uses short club codes on the watch face and expands them only on larger detail
    /// surfaces. Keeping this mapping here prevents raw backend tokens and long Chinese names from
    /// competing for the map's narrow fact column.
    static func shortCode(_ raw: String) -> String {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = value.lowercased().replacingOccurrences(of: " ", with: "")
        guard !value.isEmpty else { return value }

        if let degrees = Int(value), (44...64).contains(degrees) { return "\(degrees)°" }
        if lower.hasPrefix("wedge"),
           let degrees = Int(lower.dropFirst("wedge".count)),
           (44...64).contains(degrees) { return "\(degrees)°" }
        if ["driver", "d", "1w", "一号木"].contains(lower) { return "D" }
        switch lower {
        case "pw", "p", "pwedge", "p杆": return "PW"
        case "gw", "aw", "a", "ap", "gap", "a杆": return "AW"
        case "sw", "s", "sand", "s杆": return "SW"
        case "lw", "l", "lob", "l杆": return "LW"
        case "putter", "putt", "pt", "推杆": return "PT"
        default: break
        }

        let number = clubNumber(in: value)
        if lower.contains("hybrid") || lower.contains("rescue")
            || lower.hasSuffix("h") || value.contains("小鸡腿") {
            return number.map { "\($0)H" } ?? "H"
        }
        if lower.hasPrefix("wood") || lower.hasSuffix("w") || value.contains("号木") {
            return number.map { "\($0)W" } ?? compactMapName(value)
        }
        if lower.hasPrefix("iron") || lower.hasSuffix("i") || value.contains("号铁") {
            return number.map { "\($0)i" } ?? compactMapName(value)
        }
        return compactMapName(value)
    }

    private static func clubNumber(in value: String) -> String? {
        if let digit = value.first(where: \.isNumber) { return String(digit) }
        let reverse = Dictionary(uniqueKeysWithValues: chineseNumber.map { ($0.value, $0.key) })
        return value.first(where: { reverse[String($0)] != nil }).flatMap { reverse[String($0)] }
    }

    private static func numbered(_ value: String, suffix: String) -> String? {
        guard let digit = value.first(where: \.isNumber).map(String.init) else { return nil }
        return "\(chineseNumber[digit] ?? digit)\(suffix)"
    }
}
