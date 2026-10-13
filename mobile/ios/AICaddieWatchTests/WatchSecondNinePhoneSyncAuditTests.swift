import Foundation
import XCTest
@testable import AICaddieWatch

/// #424 review evidence only. Positive expectations describe the user's requested behaviour;
/// failures are findings for Claude, not fixes in this review branch.
@MainActor
final class WatchSecondNinePhoneSyncAuditTests: XCTestCase {
    private func states(_ key: String, roundId: String) -> [WatchRoundState] {
        (WatchCourseSelection.roundRows(loopKey: key) ?? []).map { row in
            WatchRoundState(roundId: roundId, hole: row.number, par: 4, distanceM: 350,
                selectedClub: nil, globalId: row.globalId, sourceLocalHole: row.sourceLocalHole,
                courseHoleNumber: row.courseHoleNumber, score: 0, putts: 0, penaltyCount: 0,
                caddieConfidence: "offline")
        }
    }

    private func seed(_ key: String, roundId: String) -> WatchRoundSeed {
        WatchRoundSeed(roundId: roundId, courseName: "审查球场", activeHole: 1,
            holes: states(key, roundId: roundId).map {
                WatchRoundSeedHole(hole: $0.hole, par: $0.par, distanceM: $0.distanceM,
                    globalId: $0.globalId, localHole: $0.sourceLocalHole,
                    courseHoleNumber: $0.courseHoleNumber)
            }, globalId: 31795, teeBox: "blue", loopKey: key)
    }

    private func model() -> WatchRoundModel {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("pr424-phone-sync-\(UUID().uuidString)")
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        let model = WatchRoundModel(store: WatchRoundStore(directoryURL: directory),
                                   autoShotEnabled: false, persistAutoShotEnabled: { _ in })
        model.applyRoundSeed(seed("31795:front", roundId: "sync-review"))
        model.resumeRound()
        model.selectHole(9)
        model.startScoringActiveHole()
        model.saveManualScore()
        return model
    }

    func testSameRoundPhoneReseedKeepsWatchAddedSecondNineEditable() {
        let model = model()
        let key = "31795:front+31795:back"
        XCTAssertTrue(model.applySecondLoop(Array(states(key, roundId: "sync-review").suffix(9)), loopKey: key))
        XCTAssertTrue(model.canChangeSecondNine)
        model.applyRoundSeed(seed("31795:front", roundId: "sync-review"))
        XCTAssertEqual(model.round?.loopKey, key)
        XCTAssertEqual(model.holeCount, 18)
        XCTAssertTrue(model.canChangeSecondNine, "A stale one-nine phone seed must retain the Watch's turn provenance.")
    }

    func testStalePairSeedCannotRestoreTheDroppedSecondNine() async {
        let model = model()
        let key = "31795:front+31795:back"
        XCTAssertTrue(model.applySecondLoop(Array(states(key, roundId: "sync-review").suffix(9)), loopKey: key))
        model.openChangeSecondNine()
        model.chooseTurnSecond(.stopAfterNine)
        await model.confirmTurn()
        XCTAssertEqual(model.holeCount, 9)
        XCTAssertEqual(model.round?.loopKey, "31795:front")
        model.applyRoundSeed(seed(key, roundId: "sync-review"))
        XCTAssertEqual(model.holeCount, 9, "A delayed phone pairing must not undo the explicit drop.")
        XCTAssertEqual(model.round?.loopKey, "31795:front")
    }
}
