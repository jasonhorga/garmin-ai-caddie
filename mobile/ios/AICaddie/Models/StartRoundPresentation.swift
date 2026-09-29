import AICaddieDomain
import Foundation

/// One physical venue in 开始一场's single course list (README §8): nearby first, then the explicit
/// search pick, the recent course and downloaded packages. `source` is the first source that
/// listed the venue; later sources never merge their loops into it, so each venue's loops keep one
/// authority.
struct StartCourseListRow: Equatable, Identifiable {
    enum Source: String, Equatable {
        case nearby
        case search
        case recent
        case downloaded
    }

    let venue: String
    let segments: [MobileCourseOption]
    let source: Source

    var id: Int { segments.first?.globalId ?? 0 }

    /// Holes the venue offers across its listed loops (A/B/C = 27, one 18-hole course = 18).
    var holes: Int { segments.reduce(0) { $0 + $1.resolvedHoles } }
}

/// Pure copy and list rules for 开始一场 and the home hero, kept out of the views so they are
/// unit-testable without a SwiftUI host.
enum StartRoundPresentation {
    /// Merge every course source into one list without duplicate venues. Order: nearby (already
    /// distance-sorted by the caller), then search, recent, downloaded.
    static func mergedCourseRows(
        nearby: [MobileCourseOption],
        search: [MobileCourseOption] = [],
        recent: [MobileCourseOption] = [],
        downloaded: [MobileCourseOption] = []
    ) -> [StartCourseListRow] {
        var rows: [StartCourseListRow] = []
        var seenVenues = Set<String>()
        var seenIds = Set<Int>()
        let sources: [(StartCourseListRow.Source, [MobileCourseOption])] = [
            (.nearby, nearby),
            (.search, search),
            (.recent, recent),
            (.downloaded, downloaded),
        ]
        for (source, options) in sources {
            var groups: [(key: String, venue: String, segments: [MobileCourseOption])] = []
            for option in options {
                let venue = option.venueDisplayName
                let key = venueKey(venue)
                guard !seenVenues.contains(key), !seenIds.contains(option.globalId) else { continue }
                if let index = groups.firstIndex(where: { $0.key == key }) {
                    if !groups[index].segments.contains(where: { $0.globalId == option.globalId }) {
                        groups[index].segments.append(option)
                    }
                } else {
                    groups.append((key: key, venue: venue, segments: [option]))
                }
            }
            for group in groups {
                seenVenues.insert(group.key)
                for segment in group.segments {
                    seenIds.insert(segment.globalId)
                }
                rows.append(
                    StartCourseListRow(
                        venue: group.venue,
                        segments: group.segments.sorted { segmentSortKey($0) < segmentSortKey($1) },
                        source: source
                    )
                )
            }
        }
        return rows
    }

    /// Nearest first; rows without coordinates keep their provider order after every located row.
    static func sortedByDistance(
        _ options: [MobileCourseOption],
        latitude: Double,
        longitude: Double
    ) -> [MobileCourseOption] {
        options.enumerated()
            .map { entry -> (offset: Int, option: MobileCourseOption, distance: Double) in
                let distance: Double
                if let lat = entry.element.latitude, let lon = entry.element.longitude {
                    distance = StartRoundView.haversineMetres(latitude, longitude, lat, lon)
                } else {
                    distance = .greatestFiniteMagnitude
                }
                return (offset: entry.offset, option: entry.element, distance: distance)
            }
            .sorted { lhs, rhs in
                lhs.distance == rhs.distance ? lhs.offset < rhs.offset : lhs.distance < rhs.distance
            }
            .map { $0.option }
    }

    /// "1.2 公里" below 10 km, "23 公里" beyond (`pre-round.html`).
    static func distanceText(metres: Double) -> String? {
        guard metres.isFinite, metres >= 0 else { return nil }
        let km = metres / 1_000
        let tenths = (km * 10).rounded() / 10
        if tenths < 10 {
            return String(format: "%.1f 公里", tenths)
        }
        return "\(Int(km.rounded())) 公里"
    }

    /// "蓝 T" etc. `unknown` is the server's course default. Empty → nil (no tee chosen yet).
    static func teeShortLabel(_ teeBox: String) -> String? {
        let trimmed = teeBox.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        switch trimmed.lowercased() {
        case "unknown": return "球场默认 T"
        case "blue": return "蓝 T"
        case "white": return "白 T"
        case "red": return "红 T"
        case "gold": return "金 T"
        case "black", "championship", "tips": return "黑 T"
        case "green": return "绿 T"
        case "yellow": return "黄 T"
        case "silver": return "银 T"
        case "back": return "后 T"
        case "middle": return "中 T"
        case "forward": return "前 T"
        default: return trimmed
        }
    }

    /// A loop tile's name: the course's own loop name ("A 场", "东"); a whole course is "18 洞".
    static func loopTileTitle(_ segment: MobileCourseOption) -> String {
        guard segment.resolvedHoles == 9 else { return "\(segment.resolvedHoles) 洞" }
        return NineLoopTurn.firstLoop(segment).displayName
    }

    /// The primary action: "从 B 场 开始 · 蓝 T" for a nine-hole loop and "从 前九 开始 · 蓝 T" for
    /// the chosen half of an 18-hole course (the shared `NineLoopPlan` copy), "开始" before a course
    /// is chosen.
    static func startActionTitle(
        selected: MobileCourseOption?,
        loops: [MobileCourseOption],
        teeBox: String,
        half: String = "front"
    ) -> String {
        let tee = teeShortLabel(teeBox)
        guard let selected else { return "开始" }
        if selected.resolvedHoles == 18,
           let plan = NineLoopPlan(
               course: NineLoopCourse(id: String(selected.globalId), loops: NineLoopTurn.halfLoops(globalId: selected.globalId)),
               first: "\(selected.globalId):\(half == "back" ? "back" : "front")"
           ) {
            return plan.startTitle(teeName: tee)
        }
        if selected.resolvedHoles == 9 {
            let nineLoops = loops.contains(where: { $0.globalId == selected.globalId })
                ? loops
                : [selected] + loops
            let course = NineLoopCourse(
                id: selected.venueDisplayName,
                loops: nineLoops.map(NineLoopTurn.firstLoop)
            )
            if let plan = NineLoopPlan(course: course, first: String(selected.globalId)) {
                return plan.startTitle(teeName: tee)
            }
        }
        let base = "开始 \(selected.resolvedHoles) 洞"
        guard let tee else { return base }
        return "\(base) · \(tee)"
    }

    private static func venueKey(_ venue: String) -> String {
        venue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private static func segmentSortKey(_ segment: MobileCourseOption) -> String {
        segment.resolvedSegmentLabel ?? "~~"
    }
}
