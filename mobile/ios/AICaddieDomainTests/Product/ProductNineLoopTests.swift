import XCTest
@testable import AICaddieDomain

final class ProductNineLoopTests: XCTestCase {
    func test_j5_1_first_loop_turn_defaults_and_lock() throws {
        // Expected pairings are explicit: history B->A beats sequential B->C;
        // absent history A->B, C->A wraps, and a single loop repeats itself.
        let rows: [(String, [String], [String: String], String, String)] = [
            ("18-front", ["front", "back"], [:], "front", "back"),
            ("18-back", ["front", "back"], [:], "back", "front"),
            ("27-history", ["A", "B", "C"], ["B": "A"], "B", "A"),
            ("27-next", ["A", "B", "C"], [:], "A", "B"),
            ("27-wrap", ["A", "B", "C"], [:], "C", "A"),
            ("9-repeat", ["A"], [:], "A", "A"),
        ]
        for (id, loops, history, first, expected) in rows {
            let course = NineLoopCourse(id: id, loops: loops.map { NineLoop(id: $0, name: $0) }, usualPairs: history)
            var plan = try XCTUnwrap(NineLoopPlan(course: course, first: first), id)
            XCTAssertEqual(plan.second, .loop(expected), id)
            plan.beginFirstLoop()
            plan.selectFirst("invalid")
            XCTAssertEqual(plan.first, first, id)
            plan.reachTurn()
            XCTAssertEqual(plan.phase, .atTurn, id)
            XCTAssertTrue(plan.canChangeSecond, id)
            plan.chooseSecond(.loop(first))
            XCTAssertEqual(plan.second, .loop(first), id + " same loop allowed")
            var stopped = plan
            stopped.finishAfterNine()
            XCTAssertEqual(stopped.phase, .finishedAfterNine, id)
            XCTAssertEqual(stopped.second, .stopAfterNine, id)
            plan.beginSecondLoop()
            XCTAssertFalse(plan.canChangeSecond, id)
            plan.chooseSecond(.stopAfterNine)
            XCTAssertEqual(plan.second, .loop(first), id + " recorded second half is fixed")
            // Restarting from persisted state retains the locked choice.
            let restored = try JSONDecoder().decode(NineLoopPlan.self, from: JSONEncoder().encode(plan))
            XCTAssertEqual(restored.phase, .secondLoop, id)
            XCTAssertEqual(restored.second, .loop(first), id)
        }
        let course = NineLoopCourse(id: "reset", loops: [NineLoop(id: "A", name: "A"), NineLoop(id: "B", name: "B"), NineLoop(id: "C", name: "C")])
        var plan = try XCTUnwrap(NineLoopPlan(course: course, first: "A"))
        plan.chooseSecond(.loop("A"))
        plan.selectFirst("B")
        XCTAssertEqual(plan.second, .loop("C"), "changing first resolves its own default")
        plan.selectCourse(NineLoopCourse(id: "other", loops: [NineLoop(id: "X", name: "X")]))
        XCTAssertEqual(plan.first, "X")
        XCTAssertEqual(plan.second, .loop("X"))
    }
}
