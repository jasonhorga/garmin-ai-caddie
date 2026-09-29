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

    func testHeroStatePrefersTheActiveRoundThenWatchThenACourseThenSearch() {
        let suggestion = HubCourseSuggestion(globalId: 1, courseName: "x", startTitle: "开始", teeBox: nil)
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: true, hasPendingWatchRound: true, suggestion: suggestion),
            .inProgress
        )
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: true, suggestion: suggestion),
            .pendingWatch
        )
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, suggestion: suggestion),
            .suggestion(suggestion)
        )
        XCTAssertEqual(
            HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, suggestion: nil),
            .search
        )
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
            HubCourseSuggestion.make(recent: recent, homeCourse: nil, catalogue: [blackKnightB], downloaded: [])
        )
        XCTAssertEqual(suggestion.globalId, 31795)
        XCTAssertEqual(suggestion.courseName, "北京天竺黑骑士球员俱乐部")
        XCTAssertEqual(suggestion.startTitle, "从 B 场 开始 · 白 T")
        XCTAssertEqual(suggestion.teeBox, "white")
    }

    func testHomePackageCourseIsOfferedOnlyWhenTheCatalogueKnowsIt() throws {
        let home = Course(globalId: 31795, name: "Fixture Links", teeBox: "blue")
        let suggestion = try XCTUnwrap(
            HubCourseSuggestion.make(recent: nil, homeCourse: home, catalogue: [blackKnightB], downloaded: [])
        )
        XCTAssertEqual(suggestion.startTitle, "从 B 场 开始 · 蓝 T")
        XCTAssertNil(HubCourseSuggestion.make(recent: nil, homeCourse: home, catalogue: [], downloaded: []))
        XCTAssertNil(
            HubCourseSuggestion.make(
                recent: nil,
                homeCourse: Course(globalId: 0, name: "", teeBox: "unknown"),
                catalogue: [blackKnightB],
                downloaded: []
            )
        )
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
            HubCourseSuggestion.make(recent: recent, homeCourse: nil, catalogue: [], downloaded: [])
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
