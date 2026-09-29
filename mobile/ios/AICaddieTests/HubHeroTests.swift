import XCTest
@testable import AICaddie

/// README §8 home main card: which state it shows, the course it offers, the in-progress to-par
/// and the last-round symbol strip.
final class HubHeroTests: XCTestCase {
    private let blackKnightB = MobileCourseOption(
        globalId: 31795,
        name: "北京天竺黑骑士球员俱乐部 ~ B",
        holes: 9,
        teeBox: "blue",
        venueName: "北京天竺黑骑士球员俱乐部",
        segmentLabel: "B",
        segmentHoles: 9,
        tees: ["Gold", "Blue", "White"]
    )

    func testHeroStatePrefersTheActiveRoundThenWatchThenTheCourseHereThenSearch() {
        let here = HubCourseSuggestion(globalId: 1, courseName: "x", startTitle: "开始", teeBox: nil)
        let last = HubCourseSuggestion(globalId: 2, courseName: "y", startTitle: "开始", teeBox: nil)
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: true, hasPendingWatchRound: true, nearby: here, replay: last),
            .inProgress
        )
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: true, nearby: here, replay: last),
            .pendingWatch
        )
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, nearby: here, replay: last),
            .nearby(here)
        )
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, nearby: nil, replay: last),
            .search(replay: last),
            "no course here: search plus a separate 再打上次那个"
        )
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, nearby: nil, replay: nil),
            .search(replay: nil)
        )
    }

    private func loop(_ id: Int, _ venue: String, _ label: String, lat: Double, lon: Double) -> MobileCourseOption {
        MobileCourseOption(
            globalId: id,
            name: "\(venue) ~ \(label)",
            holes: 9,
            teeBox: "blue",
            venueName: venue,
            segmentLabel: label,
            segmentHoles: 9,
            latitude: lat,
            longitude: lon
        )
    }

    private func card(_ id: String, globalId: Int, teeBox: String?) throws -> HistoryRoundCard {
        var json = #"{"id":"\#(id)","courseName":"x","globalId":\#(globalId)"#
        if let teeBox { json += #","teeBox":"\#(teeBox)""# }
        json += "}"
        return try JSONDecoder().decode(HistoryRoundCard.self, from: Data(json.utf8))
    }

    func testTheCurrentVenueIsTheNearestCourseWithinTheOnCourseRadius() throws {
        let knightA = loop(31794, "黑骑士", "A", lat: 40.10, lon: 116.50)
        let knightB = loop(31795, "黑骑士", "B", lat: 40.101, lon: 116.501)
        let palace = loop(31793, "丽宫", "A", lat: 40.02, lon: 116.40)
        let here = try XCTUnwrap(
            HubNearby.currentVenue(options: [palace, knightB, knightA], latitude: 40.1002, longitude: 116.5002)
        )
        XCTAssertEqual(here.map(\.globalId), [31794, 31795], "that venue's loops, in loop order")
        XCTAssertNil(
            HubNearby.currentVenue(options: [palace, knightA], latitude: 40.30, longitude: 116.90),
            "20+ km away is not \"at a course\""
        )
        let unlocated = MobileCourseOption(globalId: 9, name: "x", holes: 9, venueName: "x", segmentHoles: 9)
        XCTAssertNil(HubNearby.currentVenue(options: [unlocated], latitude: 40.1, longitude: 116.5))
    }

    func testOneTapStartPreparesThatLoopAndTeeAsAFreshRound() throws {
        let knightB = loop(31795, "黑骑士", "B", lat: 40.101, lon: 116.501)
        let played = try card("x-last", globalId: 31795, teeBox: "white")
        let here = try XCTUnwrap(HubCourseSuggestion.forVenue([knightB], history: [played], recent: nil))
        XCTAssertEqual(
            here.startRequest(roundId: "live-31795-new"),
            HubCourseSuggestion.StartRequest(globalId: 31795, roundId: "live-31795-new", teeBox: "white", nine: "all")
        )
        let fresh = try XCTUnwrap(HubCourseSuggestion.forVenue([knightB], history: [], recent: nil))
        XCTAssertEqual(fresh.startRequest(roundId: "r").teeBox, "unknown", "no known tee → the course default")
    }

    func testNoCourseHereKeepsTheLastCourseAsASeparateReplay() throws {
        let recent = MobileCourseOption(
            globalId: 31795, name: "北京天竺黑骑士球员俱乐部 ~ B", holes: 9, teeBox: "white",
            venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "B", segmentHoles: 9
        )
        let replay = HubCourseSuggestion.make(history: [], recent: recent, catalogue: [], downloaded: [])
        let state = HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, nearby: nil, replay: replay)
        guard case .search(let offered) = state else { return XCTFail("no course here → search") }
        XCTAssertEqual(offered?.globalId, 31795)
        XCTAssertEqual(offered?.startTitle, "从 B 场 开始 · 白 T")
    }

    func testNearXAfterLastPlayingYOffersXsOwnLastLoopAndTee() throws {
        let knightA = loop(31794, "黑骑士", "A", lat: 40.10, lon: 116.50)
        let knightB = loop(31795, "黑骑士", "B", lat: 40.101, lon: 116.501)
        // The newest round was elsewhere (Y); the newest round at 黑骑士 started on B with the white tee.
        let history = [
            try card("y-newest", globalId: 31793, teeBox: "blue"),
            try card("x-last", globalId: 31795, teeBox: "white"),
            try card("x-older", globalId: 31794, teeBox: "red"),
        ]
        let recentY = loop(31793, "丽宫", "A", lat: 40.02, lon: 116.40)
        let here = try XCTUnwrap(HubCourseSuggestion.forVenue([knightA, knightB], history: history, recent: recentY))
        XCTAssertEqual(here.globalId, 31795)
        XCTAssertEqual(here.teeBox, "white")
        XCTAssertEqual(here.startTitle, "从 B 场 开始 · 白 T")
        XCTAssertEqual(here.nine, "all")

        // Never played here: the venue's first loop with the course default tee.
        let fresh = try XCTUnwrap(HubCourseSuggestion.forVenue([knightA, knightB], history: [], recent: recentY))
        XCTAssertEqual(fresh.globalId, 31794)
        XCTAssertNil(fresh.teeBox)
        XCTAssertEqual(fresh.startTitle, "从 A 场 开始")
    }

    func testRecentCourseOffersItsFirstLoopAndLastTee() throws {
        // A composite round stored the played 18 holes; the catalogue still owns the loop structure.
        let recent = MobileCourseOption(
            globalId: 31795,
            name: "北京天竺黑骑士球员俱乐部 ~ B",
            holes: 18,
            teeBox: "white",
            venueName: "北京天竺黑骑士球员俱乐部",
            segmentLabel: "B",
            segmentHoles: 18,
            tees: ["white"]
        )
        let suggestion = try XCTUnwrap(
            HubCourseSuggestion.make(history: [], recent: recent, catalogue: [blackKnightB], downloaded: [])
        )
        XCTAssertEqual(suggestion.globalId, 31795)
        XCTAssertEqual(suggestion.courseName, "北京天竺黑骑士球员俱乐部")
        XCTAssertEqual(suggestion.startTitle, "从 B 场 开始 · 白 T")
        XCTAssertEqual(suggestion.teeBox, "white")
    }

    func testReplayIsTheNewestPlayedCourseNotTheMostPlayedHomePackage() throws {
        // No app-started record; the newest archived round is X. The most-played home package (Y)
        // is not an input at all, so it can never be offered as 上次.
        let knightA = loop(31794, "北京天竺黑骑士球员俱乐部", "A", lat: 40.1, lon: 116.5)
        let played = try card("x", globalId: 31795, teeBox: "white")
        let replay = try XCTUnwrap(
            HubCourseSuggestion.make(history: [played], recent: nil, catalogue: [knightA, blackKnightB], downloaded: [])
        )
        XCTAssertEqual(replay.globalId, 31795)
        XCTAssertEqual(replay.startTitle, "从 B 场 开始 · 白 T")
        XCTAssertEqual(replay.startRequest(roundId: "r").teeBox, "white")
        XCTAssertNil(
            HubCourseSuggestion.make(history: [], recent: nil, catalogue: [knightA, blackKnightB], downloaded: []),
            "no played course and no app-started record → no 再打上次那个"
        )
    }

    func testANewerSyncedRoundWinsOverAnOlderAppStartedCourse() throws {
        let knightA = loop(31794, "北京天竺黑骑士球员俱乐部", "A", lat: 40.1, lon: 116.5)
        let olderAppStart = MobileCourseOption(
            globalId: 31794, name: "北京天竺黑骑士球员俱乐部 ~ A", holes: 9, teeBox: "gold",
            venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "A", segmentHoles: 9
        )
        let newerGarmin = try card("g", globalId: 31795, teeBox: "blue")
        let replay = try XCTUnwrap(
            HubCourseSuggestion.make(
                history: [newerGarmin], recent: olderAppStart, catalogue: [knightA, blackKnightB], downloaded: []
            )
        )
        XCTAssertEqual(replay.globalId, 31795)
        XCTAssertEqual(replay.teeBox, "blue")
        // The newest played course cannot be resolved to a start → no replay, never the older one.
        XCTAssertNil(
            HubCourseSuggestion.make(history: [newerGarmin], recent: olderAppStart, catalogue: [knightA], downloaded: [])
        )
        // A round without a course id is not a usable fact; the app-started course is used.
        let unmatched = try JSONDecoder().decode(HistoryRoundCard.self, from: Data(#"{"id":"u","courseName":"?"}"#.utf8))
        let fallback = try XCTUnwrap(
            HubCourseSuggestion.make(history: [unmatched], recent: olderAppStart, catalogue: [knightA], downloaded: [])
        )
        XCTAssertEqual(fallback.globalId, 31794)
        XCTAssertEqual(fallback.teeBox, "gold")
    }

    func testUnknownTeeIsNotWrittenIntoTheHeroTitle() throws {
        let recent = MobileCourseOption(
            globalId: 41825,
            name: "北京北湖九号国际高尔夫俱乐部",
            holes: 18,
            teeBox: "unknown",
            venueName: "北京北湖九号国际高尔夫俱乐部",
            segmentHoles: 18
        )
        let suggestion = try XCTUnwrap(
            HubCourseSuggestion.make(history: [], recent: recent, catalogue: [], downloaded: [])
        )
        XCTAssertEqual(suggestion.startTitle, "开始 18 洞")
        XCTAssertNil(suggestion.teeBox)
    }

    func testInProgressToParSumsRecordedHolesAndIsOmittedWhenUnknown() {
        let facts: [Int: (par: Int, score: Int)] = [1: (4, 5), 2: (3, 3), 3: (5, 4), 4: (4, 6)]
        XCTAssertEqual(HubHeroState.toPar(scoredHoles: [1, 2, 3, 4]) { facts[$0] }, 2)
        XCTAssertEqual(HubHeroState.toPar(scoredHoles: [2]) { facts[$0] }, 0)
        XCTAssertNil(HubHeroState.toPar(scoredHoles: []) { facts[$0] })
        XCTAssertNil(HubHeroState.toPar(scoredHoles: [1, 9]) { facts[$0] }, "a hole without facts is never guessed")
    }

    func testLastRoundStripComesOnlyFromTheSameNewestRound() throws {
        let json = """
        {"id":"round-a","courseName":"Fixture Links","scoreStrip":[
        {"hole":1,"score":5,"par":4,"toPar":1},{"hole":2,"score":3,"par":3,"toPar":0}]}
        """
        let card = try JSONDecoder().decode(HistoryRoundCard.self, from: Data(json.utf8))
        XCTAssertEqual(HubHeroState.lastRoundStrip(lastRoundId: "round-a", newest: card).map(\.hole), [1, 2])
        XCTAssertTrue(HubHeroState.lastRoundStrip(lastRoundId: "round-b", newest: card).isEmpty)
        XCTAssertTrue(HubHeroState.lastRoundStrip(lastRoundId: "round-a", newest: nil).isEmpty)
    }

    func testInProgressToParCopy() {
        XCTAssertEqual(HubInProgressCard.toParText(0), "E")
        XCTAssertEqual(HubInProgressCard.toParText(2), "+2")
        XCTAssertEqual(HubInProgressCard.toParText(-1), "-1")
    }
}
