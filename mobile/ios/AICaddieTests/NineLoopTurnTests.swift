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

    func testTheLiveCatalogueAddsInstalledLoopsTheNetworkDidNotList() {
        let networkA = loop(1, "A")
        let installedA = loop(1, "A")
        let installedB = loop(2, "B")
        XCTAssertEqual(NineLoopTurn.loopCatalogue(network: [], downloaded: [installedA, installedB]).map(\.globalId), [1, 2])
        XCTAssertEqual(NineLoopTurn.loopCatalogue(network: [networkA], downloaded: [installedA, installedB]).map(\.globalId), [1, 2])
        let other = MobileCourseOption(globalId: 9, name: "北湖 ~ A", holes: 9, venueName: "北湖", segmentLabel: "A", segmentHoles: 9)
        XCTAssertEqual(
            NineLoopTurn.siblings(of: installedB, in: [installedB, other, installedA, installedA]).map(\.globalId), [1, 2],
            "same venue only, one row per loop, in loop order"
        )
    }

    func testACoarseSameIdNetworkRowNeverMasksTheInstalledLoop() {
        let coarse = MobileCourseOption(globalId: 1, name: "黑骑士", holes: 18, venueName: "黑骑士", segmentHoles: 18)
        let installedA = loop(1, "A")
        let installedB = loop(2, "B")
        let merged = NineLoopTurn.loopCatalogue(network: [coarse], downloaded: [installedA, installedB])
        XCTAssertEqual(merged.map(\.globalId), [1, 2])
        XCTAssertEqual(merged[0].resolvedHoles, 9, "the installed nine-hole A wins over a coarse 18-hole row")
        XCTAssertEqual(merged[0].resolvedSegmentLabel, "A")

        // The network row stays authoritative when it is the same factual loop.
        let networkA = MobileCourseOption(globalId: 1, name: "黑骑士 ~ A", holes: 9, venueName: "黑骑士 (网络)", segmentLabel: "A", segmentHoles: 9)
        let kept = NineLoopTurn.loopCatalogue(network: [networkA], downloaded: [installedA])
        XCTAssertEqual(kept.first?.venueName, "黑骑士 (网络)")

        // An unlabeled network nine-hole row is also coarser than an installed labeled loop.
        let unlabeled = MobileCourseOption(globalId: 1, name: "黑骑士", holes: 9, venueName: "黑骑士", segmentHoles: 9)
        XCTAssertEqual(NineLoopTurn.loopCatalogue(network: [unlabeled], downloaded: [installedA]).first?.resolvedSegmentLabel, "A")
    }

    func testTheTurnSheetFreezesEveryControlWhileTheLoopIsBeingAdded() {
        XCTAssertTrue(LiveRoundTurnSheet.acceptsInput(isPreparing: false))
        XCTAssertFalse(
            LiveRoundTurnSheet.acceptsInput(isPreparing: true),
            "稍后, loop tiles, 只打 9 洞 and the CTA must not act while a continuation is in flight"
        )
    }

    func testAnEighteenHoleCourseUsesItsHalvesAsTheTwoLoops() throws {
        let front = try XCTUnwrap(NineLoopTurn.halvesPlan(globalId: 31793, startedOn: "front"))
        XCTAssertEqual(front.phase, .atTurn)
        XCTAssertEqual(front.turnTitle, "前九打完了")
        XCTAssertEqual(front.second, .loop("31793:back"), "the usual second loop is the other half")
        XCTAssertEqual(front.turnActionTitle, "接着打 后九")
        XCTAssertEqual(NineLoopTurn.turnChoices(front).map(\.name), ["前九", "后九"], "前九 can be played again")

        let back = try XCTUnwrap(NineLoopTurn.halvesPlan(globalId: 31793, startedOn: "back"))
        XCTAssertEqual(back.turnTitle, "后九打完了")
        XCTAssertEqual(back.second, .loop("31793:front"))
        XCTAssertEqual(
            NineLoopTurn.turnChoices(back).map(\.name), ["前九"],
            "a 后九 start already uses holes 10–18, so 后九 cannot be added again"
        )

        XCTAssertNil(NineLoopTurn.halvesPlan(globalId: 31793, startedOn: "all"))
        XCTAssertEqual(NineLoopTurn.half(ofLoopId: "31793:back"), "back")
        XCTAssertNil(NineLoopTurn.half(ofLoopId: "31793"))
        XCTAssertNil(NineLoopTurn.half(ofLoopId: "x:front"))
        XCTAssertEqual(NineLoopTurn.firstHoleOfOtherHalf(startedOn: "front"), 10)
        XCTAssertEqual(NineLoopTurn.firstHoleOfOtherHalf(startedOn: "back"), 1)
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
