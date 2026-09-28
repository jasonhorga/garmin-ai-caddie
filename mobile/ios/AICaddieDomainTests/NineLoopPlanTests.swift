import XCTest
@testable import AICaddieDomain

/// The nine-loop state machine (README §8, IMPLEMENTATION_PLAN B4), including the prototype's own
/// `preRoundStateTest` cases from `pre-round.html`.
final class NineLoopPlanTests: XCTestCase {
    private let blackKnight = NineLoopCourse(
        id: "bk",
        loops: [
            NineLoop(id: "A", name: "A", par: 36, yards: 3190),
            NineLoop(id: "B", name: "B", par: 36, yards: 3201),
            NineLoop(id: "C", name: "C", par: 36, yards: 3211),
        ],
        usualPairs: ["B": "C", "A": "B", "C": "A"]
    )
    private let northLake = NineLoopCourse(
        id: "bh",
        loops: [NineLoop(id: "front", name: "前九", par: 36), NineLoop(id: "back", name: "后九", par: 36)],
        usualPairs: ["front": "back"]
    )
    private let tianma = NineLoopCourse(
        id: "tm",
        loops: [NineLoop(id: "E", name: "东"), NineLoop(id: "W", name: "西"), NineLoop(id: "S", name: "南")]
    )

    func testLoopNamesGetFieldOnlyForSingleCapitalLetters() {
        XCTAssertEqual(NineLoop.displayName("A"), "A 场")
        XCTAssertEqual(NineLoop.displayName("东"), "东")
        XCTAssertEqual(NineLoop.displayName("前九"), "前九")
        XCTAssertEqual(NineLoop.displayName("湖景场"), "湖景场")
        XCTAssertEqual(NineLoop.displayName("a"), "a")
        XCTAssertEqual(NineLoop.displayName("AB"), "AB")
    }

    func testStartPrefillsTheUsualPairingElseTheNextLoop() throws {
        let plan = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "B"))
        XCTAssertEqual(plan.second, .loop("C"))
        XCTAssertTrue(plan.secondIsUsualPairing)
        let noHistory = try XCTUnwrap(NineLoopPlan(course: tianma, first: "S"))
        XCTAssertEqual(noHistory.second, .loop("E"), "the next loop wraps around")
        XCTAssertFalse(noHistory.secondIsUsualPairing)
        let single = try XCTUnwrap(NineLoopPlan(course: NineLoopCourse(id: "one", loops: [NineLoop(id: "X", name: "X")])))
        XCTAssertEqual(single.second, .loop("X"), "a one-loop course plays the same loop again")
        XCTAssertNil(NineLoopPlan(course: NineLoopCourse(id: "none", loops: [])))
    }

    /// `pre-round.html` `window.preRoundStateTest`.
    func testPrototypeStateCases() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "C"))
        plan.chooseSecond(.loop("A"))
        plan.selectCourse(northLake)
        XCTAssertEqual(plan.first, "front", "switch course resets first")
        XCTAssertEqual(plan.second, .loop("back"), "switch course re-resolves second")

        plan.chooseSecond(.loop("back"))
        plan.normalize(with: NineLoopCourse(id: "bh", loops: [NineLoop(id: "front", name: "前九")]))
        XCTAssertEqual(plan.second, .loop("front"), "stale second is replaced")

        var bk = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "B"))
        bk.selectFirst("A")
        XCTAssertEqual(bk.second, .loop("B"), "changing first re-resolves second")
        bk.selectCourse(tianma)
        XCTAssertEqual(bk.second, .loop("W"), "no history: next loop")
        bk.chooseSecond(.stopAfterNine)
        bk.normalize(with: tianma)
        XCTAssertEqual(bk.second, .stopAfterNine, "stop-after-9 is kept")
    }

    func testTurnChoiceCanChangeUntilTheSecondLoopStartsThenLocks() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "B"))
        plan.beginFirstLoop()
        plan.selectFirst("A")
        XCTAssertEqual(plan.first, "B", "the first loop is fixed once play starts")
        plan.chooseSecond(.loop("A"))
        plan.reachTurn()
        XCTAssertEqual(plan.phase, .atTurn)
        XCTAssertEqual(plan.turnTitle, "B 场打完了")
        plan.chooseSecond(.loop("B"))
        XCTAssertEqual(plan.second, .loop("B"), "the same loop twice is allowed")
        XCTAssertEqual(plan.turnActionTitle, "接着打 B 场")
        plan.chooseSecond(.loop("Z"))
        XCTAssertEqual(plan.second, .loop("B"), "an unknown loop is ignored")
        plan.chooseSecond(.loop("C"))
        plan.beginSecondLoop()
        XCTAssertEqual(plan.phase, .secondLoop)
        XCTAssertFalse(plan.canChangeSecond)
        plan.chooseSecond(.loop("A"))
        XCTAssertEqual(plan.second, .loop("C"), "locked after the second loop's first hole")
        plan.normalize(with: NineLoopCourse(id: "bk", loops: [NineLoop(id: "A", name: "A")]))
        XCTAssertEqual(plan.second, .loop("C"), "a locked choice is never rewritten")
    }

    func testStoppingAfterNine() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "A"))
        plan.beginFirstLoop()
        plan.reachTurn()
        plan.chooseSecond(.stopAfterNine)
        XCTAssertEqual(plan.turnActionTitle, "结束 · 只打 9 洞")
        plan.beginSecondLoop()
        XCTAssertEqual(plan.phase, .finishedAfterNine)
        XCTAssertFalse(plan.canChangeSecond)

        var direct = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "A"))
        direct.reachTurn()
        direct.finishAfterNine()
        XCTAssertEqual(direct.second, .stopAfterNine)
        XCTAssertEqual(direct.phase, .finishedAfterNine)
    }

    func testTwoLoopEighteenHoleCourseUsesTheSameFlow() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: northLake))
        XCTAssertEqual(plan.first, "front")
        XCTAssertEqual(plan.second, .loop("back"))
        XCTAssertEqual(plan.startTitle(teeName: "蓝 T"), "从 前九 开始 · 蓝 T")
        plan.beginFirstLoop()
        plan.reachTurn()
        XCTAssertEqual(plan.turnTitle, "前九打完了")
        XCTAssertEqual(plan.turnActionTitle, "接着打 后九")
    }

    func testStartTitleUsesTheLoopNameRule() throws {
        let plan = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "B"))
        XCTAssertEqual(plan.startTitle(teeName: "蓝 T"), "从 B 场 开始 · 蓝 T")
        XCTAssertEqual(plan.startTitle(teeName: nil), "从 B 场 开始")
    }

    func testPlanRoundTripsThroughCodable() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: blackKnight, first: "B"))
        plan.beginFirstLoop()
        plan.chooseSecond(.stopAfterNine)
        let data = try JSONEncoder().encode(plan)
        XCTAssertEqual(try JSONDecoder().decode(NineLoopPlan.self, from: data), plan)
    }
}
