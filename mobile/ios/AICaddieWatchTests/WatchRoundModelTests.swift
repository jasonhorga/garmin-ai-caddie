import XCTest
@testable import AICaddieWatch

@MainActor
final class WatchRoundModelTests: XCTestCase {
    // MARK: helpers

    private func makeStore() -> WatchRoundStore {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("wmodel-\(UUID().uuidString)", isDirectory: true)
        return WatchRoundStore(directoryURL: dir)
    }

    private func hole(_ n: Int, par: Int = 4, score: Int = 0, putts: Int = 0, penalty: Int = 0) -> WatchRoundState {
        WatchRoundState(
            roundId: "r1", hole: n, par: par, distanceM: nil, selectedClub: nil,
            score: score, putts: putts, penaltyCount: penalty, caddieConfidence: "offline"
        )
    }

    /// Deterministic monotonically-increasing event ids so pending-event assertions are stable.
    private func sequentialIds() -> () -> String {
        var counter = 0
        return { counter += 1; return "evt-\(counter)" }
    }

    private func seededModel(
        holes: [WatchRoundState],
        uploader: (([WatchInputEvent], String) async throws -> [String])? = nil,
        config: WatchRoundConfig? = nil
    ) -> WatchRoundModel {
        let model = WatchRoundModel(
            store: makeStore(),
            config: config,
            makeEventId: sequentialIds(),
            now: { "2026-06-20T00:00:00Z" },
            uploader: uploader
        )
        model.seedRound(holes, courseName: "北京丽宫 · 前九")
        return model
    }

    // MARK: seeding + derived

    func testApplyRoundSeedStartsAndRestoresARealCourse() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("real-round-\(UUID().uuidString)", isDirectory: true)
        let store = WatchRoundStore(directoryURL: directory)
        let model = WatchRoundModel(store: store)
        let seed = WatchRoundSeed(
            roundId: "real-round-1",
            courseName: "北京丽宫",
            activeHole: 2,
            holes: [
                WatchRoundSeedHole(hole: 1, par: 4, distanceM: 365),
                WatchRoundSeedHole(hole: 2, par: 3, distanceM: 148),
                WatchRoundSeedHole(hole: 3, par: 5, distanceM: 472),
            ]
        )

        model.applyRoundSeed(seed)

        XCTAssertEqual(model.courseName, "北京丽宫")
        XCTAssertEqual(model.holeCount, 3)
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.activeHoleState?.par, 3)
        XCTAssertEqual(model.activeHoleState?.distanceM, 148)

        let relaunched = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory)
        )
        XCTAssertEqual(relaunched.courseName, "北京丽宫")
        XCTAssertEqual(relaunched.holeCount, 3)
        XCTAssertEqual(relaunched.activeHole, 2)
    }

    func testReceivePhoneStateUpdatesOneHoleWithoutDroppingTheRound() {
        let model = seededModel(holes: [hole(1), hole(2), hole(3)])
        let liveState = WatchRoundState(
            roundId: "r1",
            hole: 2,
            par: 4,
            distanceM: 137,
            suggestedClub: "8I",
            selectedClub: "8I",
            score: 0,
            putts: 0,
            penaltyCount: 0,
            caddieConfidence: "medium"
        )

        model.receivePhoneState(liveState)

        XCTAssertEqual(model.courseName, "北京丽宫 · 前九")
        XCTAssertEqual(model.holeCount, 3)
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.activeHoleState?.distanceM, 137)
        XCTAssertEqual(model.activeHoleState?.suggestedClub, "8I")
    }

    func testSeedRoundSetsActiveHoleAndCourse() {
        let model = seededModel(holes: [hole(1), hole(2), hole(3)])
        XCTAssertEqual(model.holeCount, 3)
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.courseName, "北京丽宫 · 前九")
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.toPar)        // nothing scored yet
        XCTAssertEqual(model.scoredHoles, 0)
    }

    // MARK: scoring draft

    func testStartScoringDefaultsToParForUnscoredHole() {
        let model = seededModel(holes: [hole(1, par: 5)])
        model.startScoringActiveHole()
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.draftScore, 5)   // defaults to par
        XCTAssertEqual(model.draftPutts, 2)   // sensible default
        XCTAssertEqual(model.draftPenalty, 0)
    }

    func testStartScoringUsesExistingValuesForScoredHole() {
        let model = seededModel(holes: [hole(1, par: 4, score: 6, putts: 3, penalty: 1)])
        model.startScoringActiveHole()
        XCTAssertEqual(model.draftScore, 6)
        XCTAssertEqual(model.draftPutts, 3)
        XCTAssertEqual(model.draftPenalty, 1)
    }

    func testAdjustDraftClampsAtLowerBounds() {
        let model = seededModel(holes: [hole(1)])
        model.startScoringActiveHole()
        model.draftScore = 1; model.adjustDraftScore(-5)
        XCTAssertEqual(model.draftScore, 1)   // never below 1
        model.draftPutts = 0; model.adjustDraftPutts(-3)
        XCTAssertEqual(model.draftPutts, 0)
        model.draftPenalty = 0; model.adjustDraftPenalty(-1)
        XCTAssertEqual(model.draftPenalty, 0)
        model.adjustDraftScore(2)
        XCTAssertEqual(model.draftScore, 3)
    }

    // MARK: save → events + advance

    func testSaveActiveHoleEmitsOnlyChangedFieldsAndAdvances() {
        let model = seededModel(holes: [hole(1, par: 4), hole(2, par: 4), hole(3, par: 4)])
        model.startScoringActiveHole()      // draft 4 / 2 / 0
        model.adjustDraftScore(1)           // -> 5
        model.saveActiveHole()
        // score (5≠0) + putt (2≠0) changed; penalty (0==0) unchanged -> 2 events
        XCTAssertEqual(model.pendingUploads, 2)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.activeHole, 2)             // advanced
        let h1 = model.round?.holeStates.first { $0.hole == 1 }
        XCTAssertEqual(h1?.score, 5)
        XCTAssertEqual(h1?.putts, 2)
        XCTAssertEqual(model.scoredHoles, 1)
        XCTAssertEqual(model.toPar, 1)                  // 5 - 4
    }

    func testDerivedTotalsAcrossTwoHoles() {
        let model = seededModel(holes: [hole(1, par: 4), hole(2, par: 3), hole(3, par: 4)])
        model.startScoringActiveHole()      // hole 1: draft 4/2/0
        model.adjustDraftScore(1)           // 5
        model.saveActiveHole()              // hole1 = 5, advance to 2
        model.startScoringActiveHole()      // hole 2 par 3: draft 3/2/0
        model.saveActiveHole()              // hole2 = 3, advance to 3
        XCTAssertEqual(model.scoredHoles, 2)
        XCTAssertEqual(model.totalStrokes, 8)          // 5 + 3
        XCTAssertEqual(model.totalPutts, 4)            // 2 + 2
        XCTAssertEqual(model.toPar, 1)                 // (5-4) + (3-3)
        XCTAssertEqual(model.activeHole, 3)
    }

    // MARK: navigation

    func testNavigationClampsAtBothEnds() {
        let model = seededModel(holes: [hole(1), hole(2), hole(3)])
        model.goToPreviousHole()
        XCTAssertEqual(model.activeHole, 1)            // already first, clamps
        model.goToNextHole(); model.goToNextHole(); model.goToNextHole()
        XCTAssertEqual(model.activeHole, 3)            // clamps at last
        model.goToPreviousHole()
        XCTAssertEqual(model.activeHole, 2)
    }

    // MARK: finish

    func testRequestFinishAndKeepPlayingToggleScreen() {
        let model = seededModel(holes: [hole(1)])
        model.requestFinish()
        XCTAssertEqual(model.screen, .finishing)
        model.keepPlaying()
        XCTAssertEqual(model.screen, .home)
    }

    func testCancelScoringDiscardsDraftAndReturnsHome() {
        let model = seededModel(holes: [hole(1, par: 4)])
        model.startScoringActiveHole()
        model.adjustDraftScore(2)        // draft changed but not saved
        model.cancelScoring()
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.pendingUploads, 0)   // nothing recorded
        XCTAssertEqual(model.scoredHoles, 0)      // hole still unscored
    }

    func testConfirmFinishUploadsPendingThenClearsRound() async {
        var received: [WatchInputEvent] = []
        let model = seededModel(
            holes: [hole(1, par: 4)],
            uploader: { events, _ in received = events; return events.map(\.eventId) }
        )
        model.startScoringActiveHole()
        model.adjustDraftScore(1)
        model.saveActiveHole()                          // 2 pending events
        XCTAssertEqual(model.pendingUploads, 2)
        await model.confirmFinish()
        XCTAssertEqual(received.count, 2)               // uploader saw the queued events
        XCTAssertNil(model.round)                       // round cleared after successful upload
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.uploadError)
        XCTAssertFalse(model.isUploading)
    }

    func testConfirmFinishKeepsRoundAndSetsErrorOnUploadFailure() async {
        struct Boom: Error {}
        let model = seededModel(
            holes: [hole(1, par: 4)],
            uploader: { _, _ in throw Boom() }
        )
        model.startScoringActiveHole()
        model.saveActiveHole()
        let pendingBefore = model.pendingUploads
        await model.confirmFinish()
        XCTAssertNotNil(model.round)                    // round retained (offline-safe)
        XCTAssertEqual(model.pendingUploads, pendingBefore)
        XCTAssertNotNil(model.uploadError)
        XCTAssertFalse(model.isUploading)
    }

    func testConfirmFinishWithoutConfigFinishesLocally() async {
        // a local practice round with no backend configured just finishes cleanly (no scary error)
        let model = seededModel(holes: [hole(1, par: 4)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        await model.confirmFinish()
        XCTAssertNil(model.uploadError)
        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)
    }

    // MARK: practice round

    func testStartPracticeRoundSeedsBlankHoles() {
        let model = WatchRoundModel(
            store: makeStore(),
            makeEventId: sequentialIds(),
            now: { "2026-06-21T00:00:00Z" }
        )
        model.startPracticeRound(holeCount: 9, par: 4)
        XCTAssertEqual(model.holeCount, 9)
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.scoredHoles, 0)
        XCTAssertEqual(model.courseName, "练习记分")
        XCTAssertTrue(model.round?.roundId.hasPrefix("watch-") ?? false)
        XCTAssertEqual(model.activeHoleState?.par, 4)
    }
}
