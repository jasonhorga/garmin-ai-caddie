import AICaddieDomain
import XCTest
@testable import AICaddieWatch

@MainActor
final class WatchC16fTurnTests: XCTestCase {
    private func directory() -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("c16f-turn-\(UUID().uuidString)")
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    // Hand identity: front physical 1...9, back physical 10...18; round slots always 1...N.
    private func states(roundID: String, physical: [Int], score: Int = 0) -> [WatchRoundState] {
        physical.enumerated().map { index, hole in
            WatchRoundState(roundId: roundID, hole: index + 1, par: 4, distanceM: nil,
                            selectedClub: nil, globalId: 81001, sourceLocalHole: hole,
                            courseHoleNumber: hole, score: score, putts: 0,
                            penaltyCount: 0, caddieConfidence: "offline")
        }
    }

    func test_5_1_watch_turn_defaults_prioritize_local_then_history_then_next() throws {
        let rows: [(String, Bool, String?, String)] = [
            ("next in course order", false, nil, "81001:back"),
            ("history repeats front", true, nil, "81001:front"),
            ("local choice overrides history", true, "81001:front", "81001:front"),
        ]
        for (label, hasHistory, localChoice, expected) in rows {
            let store = WatchRoundStore(directoryURL: directory())
            if hasHistory {
                // A completed, locally retained earlier round is the history input.
                // No product resolver is used to construct either its rows or the expected second.
                let priorSecond = localChoice == nil ? "front" : "back"
                let priorPhysical = Array(1...9) + (localChoice == nil ? Array(1...9) : Array(10...18))
                let prior = WatchRoundStore.PersistedRound(
                    roundId: "previous", activeHole: 18,
                    holeStates: states(roundID: "previous", physical: priorPhysical, score: 4),
                    courseName: "Example", courseGlobalId: 81001, teeBox: "blue",
                    loopKey: "81001:front+81001:\(priorSecond)"
                )
                _ = try store.deferFinish(prior, savedAt: "2026-10-22T12:00:00Z")
                XCTAssertEqual(store.loadDeferredFinishes().count, 1, label)
            }
            let model = WatchRoundModel(store: store, autoShotEnabled: false)
            model.seedRound(states(roundID: "current", physical: Array(1...9), score: 4), activeHole: 9,
                            courseName: "Example", courseGlobalId: 81001, teeBox: "blue", loopKey: "81001:front")
            model.openTurn()
            XCTAssertEqual(model.screen, .turn, label)
            if let localChoice {
                model.chooseTurnSecond(.loop(localChoice))
                model.leaveTurn()
                model.openTurn() // The local choice survives revisiting the turn.
            }
            let check = { XCTAssertEqual(model.turnPlan?.second, .loop(expected), label) }
            if hasHistory && localChoice == nil {
                XCTExpectFailure("5.1: Watch turn creation ignores retained round history", failingBlock: check)
            } else {
                check()
            }
        }
    }

    func test_5_1_watch_remembers_local_second_nine_for_the_next_round() async throws {
        let store = WatchRoundStore(directoryURL: directory())
        let previous = WatchRoundModel(store: store, autoShotEnabled: false)
        previous.seedRound(states(roundID: "local-previous", physical: Array(1...9), score: 4), activeHole: 9,
                           courseName: "Example", loopKey: "81001:front")
        let second = Array(states(roundID: "local-previous", physical: Array(1...9) + Array(1...9)).dropFirst(9))
        previous.secondLoopLoader = { _ in .ready(loopKey: "81001:front+81001:front", holeStates: second) }
        previous.openTurn()
        previous.chooseTurnSecond(.loop("81001:front"))
        await previous.confirmTurn()
        XCTAssertEqual(previous.round?.loopKey, "81001:front+81001:front")
        // Finish that locally chosen pair and retain it through the real offline finish store.
        var completed = try XCTUnwrap(previous.round)
        completed.holeStates = states(roundID: "local-previous", physical: Array(1...9) + Array(1...9), score: 4)
        completed.activeHole = 18
        _ = try store.deferFinish(completed, savedAt: "2026-10-22T12:00:00Z")
        let next = WatchRoundModel(store: store, autoShotEnabled: false)
        next.seedRound(states(roundID: "local-next", physical: Array(1...9), score: 4), activeHole: 9,
                       courseName: "Example", loopKey: "81001:front")
        next.openTurn()
        // Hand golden: last locally selected front->front beats sequential front->back.
        XCTExpectFailure("5.1: Watch does not remember a local second-nine preference across rounds") {
            XCTAssertEqual(next.turnPlan?.second, .loop("81001:front"))
        }
    }

    func test_5_1_watch_shared_turn_re_resolves_defaults_when_first_or_course_changes() throws {
        // Ordered loops A,B,C; history pairs A->C. A local A->A choice must not leak
        // into a B start (default C) or a new course D,E (default E).
        let course = NineLoopCourse(id: "abc", loops: [
            NineLoop(id: "A", name: "A"), NineLoop(id: "B", name: "B"), NineLoop(id: "C", name: "C"),
        ], usualPairs: ["A": "C"])
        var plan = try XCTUnwrap(NineLoopPlan(course: course, first: "A"))
        XCTAssertEqual(plan.second, .loop("C"), "history beats sequential B")
        plan.chooseSecond(.loop("A"))
        XCTAssertEqual(plan.second, .loop("A"), "local beats history C")
        plan.selectFirst("B")
        XCTAssertEqual(plan.second, .loop("C"), "new first uses sequential C")
        plan.selectCourse(NineLoopCourse(id: "de", loops: [NineLoop(id: "D", name: "D"), NineLoop(id: "E", name: "E")]))
        XCTAssertEqual(plan.first, "D")
        XCTAssertEqual(plan.second, .loop("E"), "new course uses sequential E")
    }

    func test_5_1_watch_any_record_on_tenth_hole_locks_second_nine() throws {
        let rows: [(String, WatchInputKind?, String)] = [
            ("no record", nil, ""), ("total", .score, "5"), ("putts", .putt, "2"),
            ("penalty", .penalty, "1"), ("club", .club, "6I"),
            ("shot", .location, "40,116,4"), ("distance", .distance, "150"),
        ]
        for (label, kind, value) in rows {
            let store = WatchRoundStore(directoryURL: directory())
            let model = WatchRoundModel(store: store, autoShotEnabled: false)
            model.seedRound(states(roundID: "lock", physical: Array(1...9), score: 4), activeHole: 9,
                            courseName: "Example", loopKey: "81001:front")
            let second = Array(states(roundID: "lock", physical: Array(1...9) + Array(10...18)).dropFirst(9))
            XCTAssertTrue(model.applySecondLoop(second, loopKey: "81001:front+81001:back"), label)
            XCTAssertTrue(model.canChangeSecondNine, label)
            if let kind {
                _ = try store.record(WatchInputEvent(eventId: "tenth-\(label)", roundId: "lock", hole: 10,
                                                    kind: kind, value: value, createdAt: "2026-10-23T12:00:00Z"))
            }
            let reopened = WatchRoundModel(store: store, autoShotEnabled: false)
            XCTAssertEqual(reopened.canChangeSecondNine, kind == nil, label)
            reopened.openChangeSecondNine()
            XCTAssertEqual(reopened.isChangingSecondNine, kind == nil, label)
            if kind != nil {
                XCTAssertFalse(reopened.applySecondLoop(second, loopKey: "81001:front+81001:back", replacingSecondNine: true), label)
            }
        }
    }
}
