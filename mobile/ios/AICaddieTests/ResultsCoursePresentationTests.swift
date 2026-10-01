@testable import AICaddie
import XCTest

/// B5b 球场详情 (README §9, `stats.html` 6).
final class ResultsCoursePresentationTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    private let courseJSON = #"""
    {"courseKey":"bk","courseName":"Black Knight","roundCount":5,"average18":86.9,"bestScore":82,
     "loopKeys":["gid:7:1-9","gid:7:10-18","gid:8:1-9"],"nineOnlyRounds":2,
     "rounds":[{"roundId":"r5","date":"2026-09-21T08:00:00","score":84,"holesCompleted":18,"frontLoopKey":"gid:7:10-18","backLoopKey":"gid:8:1-9"},
               {"roundId":"r4","date":"2026-08-02","score":44,"holesCompleted":9,"frontLoopKey":"gid:7:1-9"},
               {"roundId":"r3","date":"2026-07-01","score":82,"holesCompleted":18,"frontLoopKey":"gid:7:1-9","backLoopKey":"gid:7:10-18"},
               {"roundId":"r2","date":"2026-06-01","score":82,"holesCompleted":18},
               {"roundId":"r1","date":"2026-05-01","score":90,"holesCompleted":18}]}
    """#

    private let scoringJSON = #"""
    {"loops":[
      {"loopKey":"gid:7:1-9","label":"Black Knight A","holes":[
        {"hole":3,"par":4,"averageToPar":0.92,"samples":6},{"hole":5,"par":3,"averageToPar":1.4,"samples":1}]},
      {"loopKey":"gid:7:10-18","label":"Black Knight B","holes":[
        {"hole":12,"par":5,"averageToPar":0.92,"samples":9},{"hole":14,"par":4,"averageToPar":0.5,"samples":4},
        {"hole":18,"par":4,"averageToPar":null,"samples":4}]},
      {"loopKey":"gid:8:1-9","label":"C","holes":[{"hole":7,"par":4,"averageToPar":0.3,"samples":3}]},
      {"loopKey":"gid:99:1-9","label":"Elsewhere","holes":[{"hole":1,"par":4,"averageToPar":3.0,"samples":9}]}],
     "nineCombos":[
      {"frontKey":"gid:7:1-9","backKey":"gid:7:10-18","front":"Black Knight A","back":"Black Knight B","rounds":2,"average":86.0},
      {"frontKey":"gid:7:10-18","backKey":"gid:8:1-9","front":"Black Knight B","back":"C","rounds":6,"average":85.8},
      {"frontKey":"gid:8:1-9","backKey":"gid:7:1-9","front":"C","back":"Black Knight A","rounds":2,"average":84.5},
      {"frontKey":"gid:7:1-9","backKey":"gid:8:1-9","front":"Black Knight A","back":"C","rounds":1,"average":null},
      {"frontKey":"gid:99:1-9","backKey":"gid:7:1-9","front":"Elsewhere","back":"Black Knight A","rounds":9,"average":80}]}
    """#

    func testTheBackdropIsTheFirstGarminLoopsFirstHole() throws {
        let course = try decode(StatsCourse.self, courseJSON)
        XCTAssertEqual(ResultsCoursePresentation.backdrop(course), ResultsCoursePresentation.HoleRef(globalId: 7, localHole: 1))
        let back = try decode(StatsCourse.self, #"{"courseKey":"x","loopKeys":["course:x:1-9","gid:9:10-18"]}"#)
        XCTAssertEqual(ResultsCoursePresentation.backdrop(back), ResultsCoursePresentation.HoleRef(globalId: 9, localHole: 10))
        XCTAssertNil(ResultsCoursePresentation.backdrop(try decode(StatsCourse.self, #"{"courseKey":"x"}"#)))
    }

    func testTheHeaderAndDotsUseTheCoursesOwnRounds() throws {
        let course = try decode(StatsCourse.self, courseJSON)
        XCTAssertEqual(ResultsCoursePresentation.subtitle(course), "打过 5 次 · 最近 9 月 21 日")
        let dots = ResultsCoursePresentation.dots(course)
        XCTAssertEqual(dots.map(\.score), [90, 82, 82, 84], "18-hole rounds only, oldest first")
        XCTAssertEqual(dots.map(\.isBest), [false, false, true, false], "a tied best marks the newer round")
    }

    func testTheHardestHolesAreThisCoursesLoopsWithEnoughSamples() throws {
        let course = try decode(StatsCourse.self, courseJSON)
        let scoring = try decode(StatsScoring.self, scoringJSON)
        let holes = ResultsCoursePresentation.hardestHoles(course, loops: scoring.loops)
        XCTAssertEqual(holes.map(\.id), ["gid:7:10-18:12", "gid:7:1-9:3", "gid:7:10-18:14"],
                       "one-sample and missing-average holes and other courses' loops are left out; ties go to more samples")
        XCTAssertEqual(holes.map(\.overPar), ["+0.92", "+0.92", "+0.50"])
        XCTAssertEqual(holes.map(\.loopLabel), ["B", "A", "B"])
        XCTAssertEqual(holes[0].topo, ResultsCoursePresentation.HoleRef(globalId: 7, localHole: 12))
        XCTAssertEqual(holes[0].par, 5)
    }

    func testAHardHoleOpensEveryRoundThatPlayedItAtThatRoundsHoleNumber() throws {
        let course = try decode(StatsCourse.self, courseJSON)
        let holes = ResultsCoursePresentation.hardestHoles(course, loops: try decode(StatsScoring.self, scoringJSON).loops)
        let b12 = ResultsCoursePresentation.visits(course, hole: holes[0])
        XCTAssertEqual(b12.map(\.round.roundId), ["r5", "r3"])
        XCTAssertEqual(b12.map(\.displayHole), [3, 12], "B played first is holes 1–9, played second is 10–18")
        let a3 = ResultsCoursePresentation.visits(course, hole: holes[1])
        XCTAssertEqual(a3.map(\.round.roundId), ["r4", "r3"])
        XCTAssertEqual(a3.map(\.displayHole), [3, 3])
    }

    func testCombosAreThisCoursesMostPlayedWithTheRestCounted() throws {
        let course = try decode(StatsCourse.self, courseJSON)
        let scoring = try decode(StatsScoring.self, scoringJSON)
        let combos = ResultsCoursePresentation.combos(course, combos: scoring.nineCombos)
        XCTAssertEqual(combos.map(\.text), ["B → C · 6 次 · 85.8", "A → B · 2 次 · 86.0", "C → A · 2 次 · 84.5", "A → C · 1 次 · —"])
        XCTAssertEqual(ResultsCoursePresentation.allCombosLabel(course, count: combos.count), "全部 4 种组合 · 只打 9 洞 2 次")
        let noNines = try decode(StatsCourse.self, #"{"courseKey":"x"}"#)
        XCTAssertEqual(ResultsCoursePresentation.allCombosLabel(noNines, count: 6), "全部 6 种组合")
    }
}
