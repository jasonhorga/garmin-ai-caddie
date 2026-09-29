import Foundation

/// The course the home main card offers to start (README §8): the course here, or the last course
/// played (its first loop and tee).
struct HubCourseSuggestion: Equatable {
    let globalId: Int
    let courseName: String
    /// "从 B 场 开始 · 蓝 T".
    let startTitle: String
    /// The tee to start with / preselect on 开始一场; nil when unknown (the course default).
    let teeBox: String?
    /// The loop's `nine` for a one-tap start (a nine-hole loop, or a whole course, is "all").
    var nine: String = "all"

    /// "再打上次那个": the course the player last played. The newest archived round with a course
    /// id decides (a newly synced Garmin round is 上次), then the last course this app started.
    /// The most-played / home package is never labelled 上次; when the newest played course cannot
    /// be resolved to a start, no replay is offered rather than an older one.
    static func make(
        history: [HistoryRoundCard],
        recent: MobileCourseOption?,
        catalogue: [MobileCourseOption],
        downloaded: [MobileCourseOption]
    ) -> HubCourseSuggestion? {
        if let played = history.first(where: { ($0.globalId ?? 0) > 0 }),
           let playedId = played.globalId {
            let known = catalogue.first { $0.globalId == playedId }
                ?? downloaded.first { $0.globalId == playedId }
            let stored = recent.flatMap { $0.globalId == playedId ? $0 : nil }
            guard let provider = stored ?? known else { return nil }
            let option = StartRoundView.reconciledCourseOption(
                provider: provider,
                catalogue: catalogue.first { $0.globalId == playedId },
                downloaded: downloaded.first { $0.globalId == playedId }
            )
            return suggestion(for: option, teeBox: knownTee(played.teeBox) ?? knownTee(stored?.teeBox))
        }
        guard let recent,
              recent.globalId > 0,
              !recent.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        // Current catalogue facts (loop structure) win over the stored row; the tee stays the
        // one the player last started with.
        let option = StartRoundView.reconciledCourseOption(
            provider: recent,
            catalogue: catalogue.first { $0.globalId == recent.globalId },
            downloaded: downloaded.first { $0.globalId == recent.globalId }
        )
        return suggestion(for: option, teeBox: recent.teeBox)
    }

    /// The one-tap start ("开始" / "再打上次那个"): prepare exactly this loop and tee as a fresh
    /// round. No tee known → the course default (`unknown`), never a guessed colour.
    struct StartRequest: Equatable {
        let globalId: Int
        let roundId: String
        let teeBox: String
        let nine: String
    }

    func startRequest(roundId: String) -> StartRequest {
        StartRequest(globalId: globalId, roundId: roundId, teeBox: teeBox ?? "unknown", nine: nine)
    }

    /// The course the player is at (README §8 "在球场附近"): that venue's own last first loop and
    /// tee — the newest archived round on one of its loops, else the recent course when it is one
    /// of them, else the venue's first loop with the course default tee.
    static func forVenue(
        _ loops: [MobileCourseOption],
        history: [HistoryRoundCard],
        recent: MobileCourseOption?
    ) -> HubCourseSuggestion? {
        guard let first = loops.first else { return nil }
        let ids = Set(loops.map(\.globalId))
        if let played = history.first(where: { $0.globalId.map(ids.contains) ?? false }),
           let loopId = played.globalId,
           let loop = loops.first(where: { $0.globalId == loopId }) {
            let sameLoopRecent = recent.flatMap { $0.globalId == loopId ? $0.teeBox : nil }
            return suggestion(for: loop, teeBox: knownTee(played.teeBox) ?? knownTee(sameLoopRecent))
        }
        if let recent, let loop = loops.first(where: { $0.globalId == recent.globalId }) {
            return suggestion(for: loop, teeBox: recent.teeBox)
        }
        return suggestion(for: first, teeBox: nil)
    }

    /// A usable tee name; blank and "unknown" are no tee (each source is normalised before one
    /// source is preferred over another).
    static func knownTee(_ raw: String?) -> String? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty,
              trimmed.caseInsensitiveCompare("unknown") != .orderedSame else { return nil }
        return trimmed
    }

    private static func suggestion(for option: MobileCourseOption, teeBox: String?) -> HubCourseSuggestion {
        let tee = knownTee(teeBox)
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

/// The venue the player is standing at: the nearest provider-nearby course within an on-course
/// radius, with all of that venue's loops in loop order. Uses the same nearby authority as
/// 开始一场 (`model.nearbyCourses`); nothing here guesses a venue without a fix.
enum HubNearby {
    /// Within this distance of a loop's tee anchor the player is at that venue.
    static let onCourseMetres: Double = 3_000

    static func currentVenue(
        options: [MobileCourseOption],
        latitude: Double,
        longitude: Double,
        withinMetres: Double = onCourseMetres
    ) -> [MobileCourseOption]? {
        var nearest: (option: MobileCourseOption, metres: Double)?
        for option in options {
            guard let lat = option.latitude, let lon = option.longitude else { continue }
            let metres = StartRoundView.haversineMetres(latitude, longitude, lat, lon)
            if nearest == nil || metres < nearest!.metres {
                nearest = (option, metres)
            }
        }
        guard let nearest, nearest.metres <= withinMetres else { return nil }
        let venue = nearest.option.venueDisplayName
        var seen = Set<Int>()
        return options
            .filter { $0.venueDisplayName == venue && seen.insert($0.globalId).inserted }
            .sorted { ($0.resolvedSegmentLabel ?? "~~") < ($1.resolvedSegmentLabel ?? "~~") }
    }
}

extension HubNearby {
    /// Provider-nearby matches as startable loops, reconciled with catalogue/download facts
    /// (the same rows 开始一场 shows). A match without a factual hole count is dropped.
    static func options(
        from matches: [MobileCourseSearchMatch],
        catalogue: [MobileCourseOption],
        downloaded: [MobileCourseOption]
    ) -> [MobileCourseOption] {
        matches.compactMap { match -> MobileCourseOption? in
            guard let provider = match.courseOption else { return nil }
            return StartRoundView.reconciledCourseOption(
                provider: provider,
                catalogue: catalogue.first { $0.globalId == match.globalId },
                downloaded: downloaded.first { $0.globalId == match.globalId }
            )
        }
    }
}

/// Which main card the home shows (README §8, `pre-round.html` screen 1).
enum HubHeroState: Equatable {
    /// A round is in progress → "继续第 N 洞".
    case inProgress
    /// A Watch-started round is still being fetched; no new-round entry.
    case pendingWatch
    /// At a course → that course with its last first loop + tee, "开始" starts it directly.
    case nearby(HubCourseSuggestion)
    /// Not at a course → "今天去哪打？" + search, and a separate one-tap "再打上次那个" when a
    /// last course is known.
    case search(replay: HubCourseSuggestion?)

    /// The home's full resolution from its inputs: the fix and provider-nearby rows decide the
    /// course here; history and the app-started course decide the replay.
    static func resolve(
        hasActiveRound: Bool,
        hasPendingWatchRound: Bool,
        fix: (latitude: Double, longitude: Double)?,
        nearbyOptions: [MobileCourseOption],
        history: [HistoryRoundCard],
        recent: MobileCourseOption?,
        catalogue: [MobileCourseOption],
        downloaded: [MobileCourseOption]
    ) -> HubHeroState {
        var nearby: HubCourseSuggestion?
        if let fix,
           let loops = HubNearby.currentVenue(options: nearbyOptions, latitude: fix.latitude, longitude: fix.longitude) {
            nearby = HubCourseSuggestion.forVenue(loops, history: history, recent: recent)
        }
        return resolve(
            hasActiveRound: hasActiveRound,
            hasPendingWatchRound: hasPendingWatchRound,
            nearby: nearby,
            replay: HubCourseSuggestion.make(history: history, recent: recent, catalogue: catalogue, downloaded: downloaded)
        )
    }

    static func resolve(
        hasActiveRound: Bool,
        hasPendingWatchRound: Bool,
        nearby: HubCourseSuggestion?,
        replay: HubCourseSuggestion?
    ) -> HubHeroState {
        if hasActiveRound { return .inProgress }
        if hasPendingWatchRound { return .pendingWatch }
        if let nearby { return .nearby(nearby) }
        return .search(replay: replay)
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
