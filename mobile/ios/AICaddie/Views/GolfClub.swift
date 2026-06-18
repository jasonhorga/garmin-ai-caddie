import Foundation

private let cnClubNumber = ["1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"]

/// Normalize messy Garmin club names to clear Chinese:
/// 一号木 / 三号木 / 三号小鸡腿(hybrid) / 五号铁 / P杆 / A杆 / S杆 / L杆 / 50°挖起杆 / 推杆.
/// Two raw forms that mean the same club (3W & 3号木杆, PW & Pw & P) normalize to the SAME string,
/// so callers can dedup. Unrecognised values fall through unchanged. Idempotent on its own output.
public func zhClubName(_ raw: String) -> String {
    let s = raw.trimmingCharacters(in: .whitespaces)
    if s.isEmpty { return s }
    let lower = s.lowercased()

    // Wedge by loft degrees (48/50/52/54/56/58/60…).
    if let degrees = Int(s), (44...64).contains(degrees) {
        return "\(degrees)° 挖起杆"
    }
    func firstDigit(_ text: String) -> String? {
        text.first(where: { $0.isNumber }).map(String.init)
    }

    // Driver.
    if lower == "driver" || lower == "d" || lower == "1w" {
        return "一号木"
    }
    // Hybrid / 小鸡腿.
    if s.contains("小鸡腿") || lower.contains("hybrid") || lower.contains("rescue") {
        if let n = firstDigit(s) { return "\(cnClubNumber[n] ?? n)号小鸡腿" }
        return "小鸡腿"
    }
    // Fairway wood: "Nw" / "N号木".
    if lower.hasSuffix("w"), lower.dropLast().allSatisfy(\.isNumber), let n = firstDigit(lower) {
        return "\(cnClubNumber[n] ?? n)号木"
    }
    if s.contains("号木"), let n = firstDigit(s) {
        return "\(cnClubNumber[n] ?? n)号木"
    }
    // Iron: "NI" / "N号铁".
    if lower.hasSuffix("i"), lower.dropLast().allSatisfy(\.isNumber), let n = firstDigit(lower) {
        return "\(cnClubNumber[n] ?? n)号铁"
    }
    if s.contains("号铁"), let n = firstDigit(s) {
        return "\(cnClubNumber[n] ?? n)号铁"
    }
    // Wedges by letter.
    switch lower {
    case "pw", "p", "pwedge", "p 杆", "p杆":
        return "P 杆"
    case "gw", "aw", "a", "ap", "gap", "a 杆", "a杆":
        return "A 杆"
    case "sw", "s", "sand", "s 杆", "s杆":
        return "S 杆"
    case "lw", "l", "lob", "l 杆", "l杆":
        return "L 杆"
    case "putter", "putt", "pt", "推杆":
        return "推杆"
    default:
        return s
    }
}

/// Driver/woods only make sense from the tee — never a 1-wood off the fairway (the player's note).
public func clubIsTeeOnly(_ zhName: String) -> Bool {
    zhName == "一号木"
}
