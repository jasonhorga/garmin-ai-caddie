import Foundation

/// The course the home main card offers to start (README §8): the last explicitly started course
/// (its first loop and tee), else the home package's course when the catalogue knows it.
struct HubCourseSuggestion: Equatable {
    let globalId: Int
    let courseName: String
    /// "从 B 场 开始 · 蓝 T".
    let startTitle: String
    /// The tee to preselect on 开始一场; nil when unknown.
    let teeBox: String?

    static func make(
        recent: MobileCourseOption?,
        homeCourse: Course?,
        catalogue: [MobileCourseOption],
        downloaded: [MobileCourseOption]
    ) -> HubCourseSuggestion? {
        if let recent,
           recent.globalId > 0,
           !recent.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            // Current catalogue facts (loop structure) win over the stored row; the tee stays the
            // one the player last started with.
            let option = StartRoundView.reconciledCourseOption(
                provider: recent,
                catalogue: catalogue.first { $0.globalId == recent.globalId },
                downloaded: downloaded.first { $0.globalId == recent.globalId }
            )
            return suggestion(for: option, teeBox: recent.teeBox)
        }
        // The home package is only offered when 开始一场 can resolve the same global id.
        if let homeCourse, homeCourse.globalId > 0,
           let option = catalogue.first(where: { $0.globalId == homeCourse.globalId })
            ?? downloaded.first(where: { $0.globalId == homeCourse.globalId }) {
            return suggestion(for: option, teeBox: homeCourse.teeBox)
        }
        return nil
    }

    private static func suggestion(for option: MobileCourseOption, teeBox: String?) -> HubCourseSuggestion {
        let tee = teeBox.flatMap { raw -> String? in
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, trimmed.caseInsensitiveCompare("unknown") != .orderedSame else { return nil }
            return trimmed
        }
        return HubCourseSuggestion(
            globalId: option.globalId,
            courseName: option.venueDisplayName,
            startTitle: StartRoundPresentation.startActionTitle(
                selected: option,
                loops: [option],
                teeBox: tee ?? ""
            ),
            teeBox: tee
        )
    }
}

/// Which main card the home shows (README §8, `pre-round.html` screen 1).
enum HubHeroState: Equatable {
    /// A round is in progress → "继续第 N 洞".
    case inProgress
    /// A Watch-started round is still being fetched; no new-round entry.
    case pendingWatch
    /// A known course → "从 B 场 开始 · 蓝 T" + 开始 + 换球场或组合.
    case suggestion(HubCourseSuggestion)
    /// No course known → "今天去哪打？" + search.
    case search

    static func resolve(
        hasActiveRound: Bool,
        hasPendingWatchRound: Bool,
        suggestion: HubCourseSuggestion?
    ) -> HubHeroState {
        if hasActiveRound { return .inProgress }
        if hasPendingWatchRound { return .pendingWatch }
        if let suggestion { return .suggestion(suggestion) }
        return .search
    }

    /// The round's score to par over the holes that have a recorded score; nil when nothing is
    /// recorded or any recorded hole has no known par/score (never a guessed number).
    static func toPar(
        scoredHoles: Set<Int>,
        parAndScore: (Int) -> (par: Int, score: Int)?
    ) -> Int? {
        guard !scoredHoles.isEmpty else { return nil }
        var total = 0
        for hole in scoredHoles {
            guard let entry = parAndScore(hole), entry.par > 0, entry.score > 0 else { return nil }
            total += entry.score - entry.par
        }
        return total
    }

    /// The 18-hole symbol strip for the last-round card: only when the newest archived round is
    /// that same round (`RecentRoundSummary` carries no per-hole scores).
    static func lastRoundStrip(lastRoundId: String, newest: HistoryRoundCard?) -> [HistoryScoreCell] {
        guard let newest, newest.id == lastRoundId else { return [] }
        return Array(newest.scoreStrip.prefix(18))
    }
}
