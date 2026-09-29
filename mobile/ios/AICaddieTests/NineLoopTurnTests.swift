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
        let pairs = NineLoopTurn.usualPairs(
            remembered: ["2:all": "3:all"],
            history: history,
            loopIds: ["1:all", "2:all", "3:all"]
        )
        XCTAssertEqual(pairs["1:all"], "3:all", "newest history round")
        XCTAssertEqual(pairs["2:all"], "3:all", "the pairing chosen on this phone wins")
        let foreign = NineLoopTurn.usualPairs(remembered: ["1:all": "99:all"], history: [], loopIds: ["1:all", "2:all"])
        XCTAssertNil(foreign["1:all"], "a loop of another venue is never a pairing")
    }

    func testPlanAtTheTurnPreselectsTheUsualPairing() throws {
        let loops = [loop(1, "A"), loop(2, "B"), loop(3, "C")]
        let plan = try XCTUnwrap(NineLoopTurn.plan(front: loops[1], siblings: loops, remembered: ["2:all": "1:all"], history: []))
        XCTAssertEqual(plan.phase, .atTurn)
        XCTAssertEqual(plan.turnTitle, "B 场打完了")
        XCTAssertEqual(plan.second, .loop("1:all"))
        XCTAssertTrue(plan.secondIsUsualPairing)
        XCTAssertEqual(plan.turnActionTitle, "接着打 A 场")
    }

    func testWithoutSiblingsTheSameLoopIsOffered() throws {
        let only = loop(7, "A")
        let plan = try XCTUnwrap(NineLoopTurn.plan(front: only, siblings: [], remembered: [:], history: []))
        XCTAssertEqual(plan.course.loops.map(\.id), ["7:all"])
        XCTAssertEqual(plan.second, .loop("7:all"))
    }

    func testLoopsWithoutAFactualLabelAreNeverOfferedUnderASynthesizedName() throws {
        let unlabeledSibling = MobileCourseOption(globalId: 9, name: "黑骑士", holes: 9, venueName: "黑骑士", segmentHoles: 9)
        let loops = [loop(1, "A"), loop(2, "B"), unlabeledSibling]
        let plan = try XCTUnwrap(NineLoopTurn.plan(front: loops[0], siblings: loops, remembered: [:], history: []))
        XCTAssertEqual(plan.course.loops.map(\.id), ["1:all", "2:all"], "an unlabeled loop is not a choice")
        for name in plan.course.loops.map(\.displayName) + [plan.turnTitle, plan.turnActionTitle] {
            XCTAssertFalse(name.contains("洞组"), name)
        }

        // The loop just played keeps its factual course name when it has no loop label.
        let plain = MobileCourseOption(globalId: 5, name: "翠湖", holes: 9, venueName: "翠湖", segmentHoles: 9)
        let single = try XCTUnwrap(NineLoopTurn.plan(front: plain, siblings: [], remembered: [:], history: []))
        XCTAssertEqual(single.course.loops.map(\.id), ["5:all"])
        XCTAssertEqual(single.course.loops.first?.name, plain.localizedName)
        XCTAssertFalse(single.turnTitle.contains("洞组"))
    }

    func testLoopIdsAreRequestEntries() {
        XCTAssertEqual(NineLoopTurn.loopId(RoundLoopEntry(globalId: 31795, half: "all")), "31795:all")
        XCTAssertEqual(NineLoopTurn.loopId(RoundLoopEntry(globalId: 41825, half: "back")), "41825:back")
        XCTAssertEqual(NineLoopTurn.entry("41825:front"), RoundLoopEntry(globalId: 41825, half: "front"))
        XCTAssertNil(NineLoopTurn.entry("41825:front+41825:back"), "a loop id is exactly one entry")
        XCTAssertNil(NineLoopTurn.entry("41825"))
        XCTAssertEqual(NineLoopTurn.firstLoop(loop(31795, "B")).id, "31795:all")
    }

    func testTheSecondLoopStartsOnRoundHoleTen() throws {
        let pair = try halfRoundPackage(loops: [
            RoundLoopEntry(globalId: 41825, half: "back"),
            RoundLoopEntry(globalId: 41825, half: "front"),
        ])
        XCTAssertEqual(pair.secondLoop?.roundStartHole, 10)
        XCTAssertEqual(pair.secondLoop?.half, "front")
        XCTAssertNil(try halfRoundPackage(loops: [RoundLoopEntry(globalId: 41825, half: "back")]).secondLoop)
    }

    func testAnEighteenHoleHalfRoundTurnsOntoTheHalvesOfTheSameCourse() throws {
        let package = try halfRoundPackage(loops: [RoundLoopEntry(globalId: 41825, half: "back")])
        let plan = try XCTUnwrap(NineLoopTurn.planAtEndOfFirstLoop(
            package: package,
            catalogue: [],
            remembered: [:],
            history: []
        ))
        XCTAssertEqual(plan.phase, .atTurn)
        XCTAssertEqual(plan.course.loops.map(\.name), ["前九", "后九"])
        XCTAssertEqual(plan.course.loops.map(\.id), ["41825:front", "41825:back"])
        XCTAssertEqual(plan.first, "41825:back")
        XCTAssertEqual(plan.second, .loop("41825:front"), "the other half is preselected")
        XCTAssertEqual(plan.turnTitle, "后九打完了")
        XCTAssertEqual(plan.turnActionTitle, "接着打 前九")

        var sameHalf = plan
        sameHalf.chooseSecond(.loop("41825:back"))
        XCTAssertEqual(sameHalf.second, .loop("41825:back"), "the same half may be played again")
        XCTAssertEqual(sameHalf.turnActionTitle, "接着打 后九")
        sameHalf.chooseSecond(.stopAfterNine)
        XCTAssertEqual(sameHalf.turnActionTitle, "结束 · 只打 9 洞")

        let remembered = try XCTUnwrap(NineLoopTurn.planAtEndOfFirstLoop(
            package: package,
            catalogue: [],
            remembered: ["41825:back": "41825:back", "31795:all": "31796:all"],
            history: []
        ))
        XCTAssertEqual(remembered.second, .loop("41825:back"), "the remembered same-half pairing wins")
        XCTAssertTrue(remembered.secondIsUsualPairing)
    }

    func testAFrontHalfRoundDefaultsToTheBackHalfAndAPairedRoundHasNoTurnPlan() throws {
        let front = try halfRoundPackage(loops: [RoundLoopEntry(globalId: 41825, half: "front")])
        let plan = try XCTUnwrap(NineLoopTurn.planAtEndOfFirstLoop(package: front, catalogue: [], remembered: [:], history: []))
        XCTAssertEqual(plan.first, "41825:front")
        XCTAssertEqual(plan.second, .loop("41825:back"))
        XCTAssertEqual(plan.turnTitle, "前九打完了")

        let paired = try halfRoundPackage(loops: [
            RoundLoopEntry(globalId: 41825, half: "front"),
            RoundLoopEntry(globalId: 41825, half: "front"),
        ])
        XCTAssertNil(NineLoopTurn.planAtEndOfFirstLoop(package: paired, catalogue: [], remembered: [:], history: []))
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

    func testPairingsRoundTripPerAccount() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        XCTAssertEqual(try store.loadNineLoopPairings(), [:])
        try store.rememberNineLoopPairing(first: "1:all", second: "3:all")
        try store.rememberNineLoopPairing(first: "1:all", second: "2:all")
        try store.rememberNineLoopPairing(first: "2:all", second: "2:all")
        try store.rememberNineLoopPairing(first: "41825:back", second: "41825:front")
        try store.rememberNineLoopPairing(first: "41825:back+41825:front", second: "41825:front")
        try store.rememberNineLoopPairing(first: "1", second: "2:all")
        XCTAssertEqual(
            try store.loadNineLoopPairings(),
            ["1:all": "2:all", "2:all": "2:all", "41825:back": "41825:front"],
            "only single loop ids are remembered"
        )
        store.bindAccount(playerId: "player-b", migrateLegacyData: false)
        XCTAssertEqual(try store.loadNineLoopPairings(), [:])
    }

    /// A round on the halves of the 18-hole course 41825 in the given play order, projected from a
    /// whole-course table built on the shared fixture package.
    private func halfRoundPackage(loops: [RoundLoopEntry]) throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let source = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: url))
        let table = RoundLoopEntry.table(loops)
        let holes = table.flatMap { loop in
            (0..<loop.holeCount).map { index in
                Hole(
                    number: loop.roundStartHole + index,
                    par: 4,
                    yards: 400,
                    geometryCoverage: .ready,
                    sourceGlobalId: loop.globalId,
                    sourceLocalHole: loop.sourceStartHole + index,
                    courseHoleNumber: loop.sourceStartHole + index
                )
            }
        }
        return LiveRoundPackage(
            roundId: "half-round",
            dataMode: source.dataMode,
            sourceCoverage: source.sourceCoverage,
            missingData: [],
            playerProfile: source.playerProfile,
            course: Course(globalId: 41825, name: "北湖", teeBox: "blue"),
            holes: holes,
            roundLoops: table,
            loopKey: RoundLoopEntry.loopKey(loops),
            geometryCoverage: GeometryCoverage(state: .ready, readyHoles: holes.count, totalHoles: holes.count),
            readinessChecks: [],
            caddieContextSeeds: [],
            weatherSnapshot: source.weatherSnapshot,
            clubProfiles: source.clubProfiles,
            caddieDecisionEndpoint: source.caddieDecisionEndpoint,
            offlinePackageStatus: source.offlinePackageStatus,
            eventCursor: source.eventCursor,
            recentHistory: source.recentHistory,
            cachedCaddieRules: source.cachedCaddieRules,
            generatedAt: source.generatedAt
        )
    }
}
