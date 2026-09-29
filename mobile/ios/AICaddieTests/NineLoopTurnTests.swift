import AICaddieDomain
import XCTest
@testable import AICaddie

/// B4 turn: the phone builds the shared NineLoopPlan from the venue's loops and the usual pairing.
final class NineLoopTurnTests: XCTestCase {
    private func loop(_ id: Int, _ label: String) -> MobileCourseOption {
        MobileCourseOption(globalId: id, name: "黑骑士 ~ \(label)", holes: 9, venueName: "黑骑士", segmentLabel: label, segmentHoles: 9)
    }

    private func card(_ id: String, front: Int, back: Int?) throws -> HistoryRoundCard {
        var json = #"{"id":"\#(id)","courseName":"黑骑士","globalId":\#(front)"#
        if let back { json += #","backGlobalId":\#(back)"# }
        json += "}"
        return try JSONDecoder().decode(HistoryRoundCard.self, from: Data(json.utf8))
    }

    func testRememberedPairingWinsOverHistoryAndHistoryUsesTheNewestRound() throws {
        let history = [try card("r2", front: 1, back: 3), try card("r1", front: 1, back: 2), try card("r0", front: 2, back: 1)]
        let pairs = NineLoopTurn.usualPairs(remembered: [2: 3], history: history, loopIds: [1, 2, 3])
        XCTAssertEqual(pairs["1"], "3", "newest history round")
        XCTAssertEqual(pairs["2"], "3", "the pairing chosen on this phone wins")
        let foreign = NineLoopTurn.usualPairs(remembered: [1: 99], history: [], loopIds: [1, 2])
        XCTAssertNil(foreign["1"], "a loop of another venue is never a pairing")
    }

    func testPlanAtTheTurnPreselectsTheUsualPairing() throws {
        let loops = [loop(1, "A"), loop(2, "B"), loop(3, "C")]
        let plan = try XCTUnwrap(NineLoopTurn.plan(front: loops[1], siblings: loops, remembered: [2: 1], history: []))
        XCTAssertEqual(plan.phase, .atTurn)
        XCTAssertEqual(plan.turnTitle, "B 场打完了")
        XCTAssertEqual(plan.second, .loop("1"))
        XCTAssertTrue(plan.secondIsUsualPairing)
        XCTAssertEqual(plan.turnActionTitle, "接着打 A 场")
    }

    func testWithoutSiblingsTheSameLoopIsOffered() throws {
        let only = loop(7, "A")
        let plan = try XCTUnwrap(NineLoopTurn.plan(front: only, siblings: [], remembered: [:], history: []))
        XCTAssertEqual(plan.course.loops.map(\.id), ["7"])
        XCTAssertEqual(plan.second, .loop("7"))
    }

    func testLoopsWithoutAFactualLabelAreNeverOfferedUnderASynthesizedName() throws {
        let unlabeledSibling = MobileCourseOption(globalId: 9, name: "黑骑士", holes: 9, venueName: "黑骑士", segmentHoles: 9)
        let loops = [loop(1, "A"), loop(2, "B"), unlabeledSibling]
        let plan = try XCTUnwrap(NineLoopTurn.plan(front: loops[0], siblings: loops, remembered: [:], history: []))
        XCTAssertEqual(plan.course.loops.map(\.id), ["1", "2"], "an unlabeled loop is not a choice")
        for name in plan.course.loops.map(\.displayName) + [plan.turnTitle, plan.turnActionTitle] {
            XCTAssertFalse(name.contains("洞组"), name)
        }

        // The loop just played keeps its factual course name when it has no loop label.
        let plain = MobileCourseOption(globalId: 5, name: "翠湖", holes: 9, venueName: "翠湖", segmentHoles: 9)
        let single = try XCTUnwrap(NineLoopTurn.plan(front: plain, siblings: [], remembered: [:], history: []))
        XCTAssertEqual(single.course.loops.map(\.id), ["5"])
        XCTAssertEqual(single.course.loops.first?.name, plain.localizedName)
        XCTAssertFalse(single.turnTitle.contains("洞组"))
    }

    func testTheSecondLoopStartsAtTheFirstHoleAfterTheFirstNine() {
        XCTAssertEqual(NineLoopTurn.firstHoleOfSecondLoop(Array(1...18)), 10)
        XCTAssertEqual(NineLoopTurn.firstHoleOfSecondLoop([12, 1, 10, 9]), 10)
        XCTAssertNil(NineLoopTurn.firstHoleOfSecondLoop(Array(1...9)))
    }

    func testPairingsRoundTripPerAccount() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        XCTAssertEqual(try store.loadNineLoopPairings(), [:])
        try store.rememberNineLoopPairing(front: 1, back: 3)
        try store.rememberNineLoopPairing(front: 1, back: 2)
        try store.rememberNineLoopPairing(front: 2, back: 2)
        XCTAssertEqual(try store.loadNineLoopPairings(), [1: 2, 2: 2])
        store.bindAccount(playerId: "player-b", migrateLegacyData: false)
        XCTAssertEqual(try store.loadNineLoopPairings(), [:])
    }
}
