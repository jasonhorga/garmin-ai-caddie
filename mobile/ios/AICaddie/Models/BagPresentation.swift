import Foundation

/// B5c 球包 (README §9, `stats.html` 3): one distance ladder that replaces 成绩 → 球杆 and 球杆设置.
/// Each club in the bag is a p10–p90 bar (80% of its shots) with the median, long to short, and the
/// gap to the next club; a gap under 8 or over 20 yards is flagged (overlap or hole in the bag). A
/// typed distance (the one the caddie uses) replaces the history median and is drawn as a dot.
/// Pure, so ordering, gaps and the axis are testable.
enum BagPresentation {
    static let narrowGap = 8
    static let wideGap = 20

    struct Row: Equatable, Identifiable {
        var id: String { name }
        let name: String
        /// Shot-history figures in yards; nil without samples.
        let p10: Int?
        let historyMedian: Int?
        let p90: Int?
        let samples: Int
        /// The typed distance the caddie uses, when set.
        let manual: Int?

        var median: Int? { manual ?? historyMedian }
        var isManual: Bool { manual != nil }
        var hasRange: Bool { p10 != nil && p90 != nil }
    }

    struct Gap: Equatable {
        let yards: Int
        var isFlagged: Bool { yards < narrowGap || yards > wideGap }
        var text: String { "差 \(yards) 码" }
    }

    /// The bag's clubs (catalog names; the putter is not on a distance ladder), long to short by the
    /// distance in use; clubs without any distance last, in catalog order.
    static func rows(bag: Set<String>, profiles: [ClubProfile], manual: [String: Int]) -> [Row] {
        let built = ClubCatalog.all.map(\.zhName).filter { bag.contains($0) && $0 != "推杆" }.map { name -> Row in
            let profile = strongestProfile(for: name, in: profiles)
            func yards(_ metres: Double?) -> Int? {
                guard let metres, metres.isFinite, metres > 0 else { return nil }
                return CoursePrepRoute.yards(fromMetres: metres)
            }
            return Row(
                name: name,
                p10: yards(profile?.p10M),
                historyMedian: yards(profile?.medianM),
                p90: yards(profile?.p90M),
                samples: profile?.sampleSize ?? 0,
                manual: manual[name].flatMap { $0 > 0 ? $0 : nil }
            )
        }
        let measured = built.enumerated().filter { $0.element.median != nil }
            .sorted { ($0.element.median ?? 0, -$0.offset) > ($1.element.median ?? 0, -$1.offset) }
            .map(\.element)
        return measured + built.filter { $0.median == nil }
    }

    /// Legacy aliases of one physical club ("Aw"/"GW", "7I"/"7 Iron") can all be in the package. The
    /// caddie keeps the one with the most shots, so does the ladder: most samples wins, the earlier
    /// row on a tie.
    static func strongestProfile(for name: String, in profiles: [ClubProfile]) -> ClubProfile? {
        profiles.reduce(nil as ClubProfile?) { best, profile in
            guard profile.sampleSize > 0,
                  zhClubName(profile.clubName.trimmingCharacters(in: .whitespaces)) == name else { return best }
            guard let best else { return profile }
            return profile.sampleSize > best.sampleSize ? profile : best
        }
    }

    /// The gap from `above` down to `below`, when both have a distance.
    static func gap(_ above: Row, _ below: Row) -> Gap? {
        guard let a = above.median, let b = below.median else { return nil }
        return Gap(yards: a - b)
    }

    /// The shared yardage axis: every bar, median and typed distance, padded to whole tens.
    static func axis(_ rows: [Row]) -> ClosedRange<Int>? {
        let values = rows.flatMap { [$0.p10, $0.p90, $0.median].compactMap { $0 } }
        guard let low = values.min(), let high = values.max() else { return nil }
        let start = max(0, (low - 10) / 10 * 10)
        let end = ((high + 19) / 10) * 10
        return start...max(end, start + 10)
    }

    /// Axis labels every 50 yards inside the axis.
    static func ticks(_ axis: ClosedRange<Int>) -> [Int] {
        stride(from: (axis.lowerBound + 49) / 50 * 50, through: axis.upperBound, by: 50).map { $0 }
    }

    static func summary(_ rows: [Row]) -> String {
        "\(rows.count) 支 · 条是 80% 的击球落在的范围，白线是中位数"
    }

    /// The editor's history line: "历史 86 杆 · 中位 231 码 · 80% 在 205–248 码", parts left out
    /// when unknown; "还没有击球记录" without samples.
    static func historyText(_ row: Row) -> String {
        guard row.samples > 0 else { return "还没有击球记录" }
        var parts = ["历史 \(row.samples) 杆"]
        if let median = row.historyMedian { parts.append("中位 \(median) 码") }
        if let p10 = row.p10, let p90 = row.p90 { parts.append("80% 在 \(p10)–\(p90) 码") }
        return parts.joined(separator: " · ")
    }

    /// Catalog clubs that can still be added ("＋ 球杆"), in catalog order. The putter has no row on
    /// a distance ladder, so it is not offered here either (adding it would be invisible and could not
    /// be undone from this screen); the Garmin bag keeps whichever putter the player carries.
    static func addable(bag: Set<String>) -> [CatalogClub] {
        ClubCatalog.all.filter { !bag.contains($0.zhName) && $0.category != .putter }
    }
}
