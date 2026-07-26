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

    private func hole(
        _ n: Int,
        par: Int = 4,
        score: Int = 0,
        putts: Int = 0,
        penalty: Int = 0,
        teeLatitude: Double? = nil,
        teeLongitude: Double? = nil,
        shotType: String? = nil
    ) -> WatchRoundState {
        WatchRoundState(
            roundId: "r1", hole: n, par: par, distanceM: nil,
            teeLatitude: teeLatitude, teeLongitude: teeLongitude,
            selectedClub: nil,
            shotType: shotType,
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
        XCTAssertEqual(model.scoreFlowStep, .recommendation)
        XCTAssertEqual(model.draftScore, 5)   // defaults to par
        XCTAssertEqual(model.draftPutts, 2)   // sensible default
        XCTAssertEqual(model.draftPenalty, 0)
    }

    func testStartScoringUsesExistingValuesForScoredHole() {
        let model = seededModel(holes: [hole(1, par: 4, score: 6, putts: 3, penalty: 1)])
        model.startScoringActiveHole()
        XCTAssertEqual(model.scoreFlowStep, .score)
        XCTAssertEqual(model.draftScore, 6)
        XCTAssertEqual(model.draftPutts, 3)
        XCTAssertEqual(model.draftPenalty, 1)
    }

    func testNextUnscoredHoleRequestsConfirmationWithoutAdvancing() {
        let model = seededModel(holes: [hole(1), hole(2)])

        model.goToNextHole()

        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.scoreFlowStep, .recommendation)
    }

    func testAcceptRecommendedScorePersistsDefaultsAndAdvances() {
        let model = seededModel(holes: [hole(1, par: 4), hole(2)])
        model.goToNextHole()

        model.acceptRecommendedScore()

        let first = model.round?.holeStates.first { $0.hole == 1 }
        XCTAssertEqual(first?.score, 4)
        XCTAssertEqual(first?.putts, 2)
        XCTAssertEqual(first?.penaltyCount, 0)
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.pendingUploads, 2)
    }

    func testManualPar4ConfirmationFollowsScorePuttsFairwayPenalty() {
        let model = seededModel(holes: [hole(1, par: 4), hole(2)])
        model.startScoringActiveHole()

        model.startManualScoreEntry()
        XCTAssertEqual(model.scoreFlowStep, .score)
        model.adjustDraftScore(1)
        model.advanceScoreEntry()
        XCTAssertEqual(model.scoreFlowStep, .putts)
        model.advanceScoreEntry()
        XCTAssertEqual(model.scoreFlowStep, .fairway)
        model.selectDraftFairway(.left)
        XCTAssertEqual(model.scoreFlowStep, .penalty)
        model.adjustDraftPenalty(1)
        model.saveManualScore()

        let first = model.round?.holeStates.first { $0.hole == 1 }
        XCTAssertEqual(first?.score, 5)
        XCTAssertEqual(first?.putts, 2)
        XCTAssertEqual(first?.fairwayResult, "LEFT")
        XCTAssertEqual(first?.penaltyCount, 1)
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.screen, .home)
    }

    func testManualPar3ConfirmationSkipsFairway() {
        let model = seededModel(holes: [hole(1, par: 3), hole(2)])
        model.startScoringActiveHole()
        model.startManualScoreEntry()

        model.advanceScoreEntry()
        XCTAssertEqual(model.scoreFlowStep, .putts)
        model.advanceScoreEntry()

        XCTAssertEqual(model.scoreFlowStep, .penalty)
        XCTAssertNil(model.draftFairway)
    }

    func testManualShotRecordsClubThenLocationAndFeedsRecommendedScore() {
        let model = seededModel(holes: [hole(1, par: 4), hole(2)])

        model.beginManualShot(
            latitude: 40.0454995,
            longitude: 116.5461531,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T08:00:00Z"
        )
        XCTAssertEqual(model.screen, .clubPrompt)
        XCTAssertEqual(model.pendingManualShot?.hole, 1)

        model.completePendingManualShot(clubName: "一号木")

        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.pendingManualShot)
        XCTAssertEqual(model.recordedShotCount, 1)
        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.club, .location])
        XCTAssertEqual(model.round?.pendingEvents.first?.value, "一号木")
        XCTAssertEqual(model.round?.pendingEvents.first?.shotType, "tee")
        XCTAssertEqual(model.round?.pendingEvents.last?.value, "40.0454995,116.5461531,5.0")

        model.startScoringActiveHole()
        XCTAssertEqual(model.draftScore, 3)
        XCTAssertEqual(model.draftPutts, 2)
    }

    func testSkippingClubStillRecordsTheShotLocation() {
        let model = seededModel(holes: [hole(1)])
        model.beginManualShot(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 4,
            capturedAt: "2026-07-26T08:00:00Z"
        )

        model.completePendingManualShot(clubName: nil)

        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.location])
        XCTAssertEqual(model.recordedShotCount, 1)
    }

    func testPendingManualShotRestoresClubPromptAfterRelaunch() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("manual-shot-restore-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            makeEventId: sequentialIds(),
            now: { "2026-07-26T10:00:00Z" }
        )
        first.seedRound([hole(1)])
        first.beginManualShot(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T10:00:00Z"
        )

        let restored = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            makeEventId: sequentialIds(),
            now: { "2026-07-26T10:01:00Z" }
        )

        XCTAssertEqual(restored.screen, .clubPrompt)
        XCTAssertEqual(restored.pendingManualShot?.hole, 1)
        XCTAssertEqual(restored.pendingManualShot?.shotNumber, 1)
        XCTAssertEqual(restored.pendingUploads, 0)

        restored.completePendingManualShot(clubName: nil)
        XCTAssertNil(restored.pendingManualShot)
        XCTAssertEqual(restored.round?.pendingEvents.map(\.kind), [.location])
    }

    func testNextTeeCandidateAndScoreDraftRestoreAfterRelaunch() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("candidate-score-restore-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            makeEventId: sequentialIds(),
            now: { "2026-07-26T11:00:00Z" }
        )
        first.seedRound([
            hole(1, par: 4, teeLatitude: 40.0, teeLongitude: 116.0),
            hole(2, par: 5, teeLatitude: 40.001, teeLongitude: 116.0),
        ])
        first.beginManualShot(
            latitude: 40.001,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T11:00:00Z"
        )
        first.startManualScoreEntry()
        first.adjustDraftScore(1)
        first.advanceScoreEntry()
        first.adjustDraftPutts(1)

        let restored = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            makeEventId: sequentialIds(),
            now: { "2026-07-26T11:01:00Z" }
        )

        XCTAssertEqual(restored.screen, .scoring)
        XCTAssertEqual(restored.activeHole, 1)
        XCTAssertEqual(restored.scoringHole, 1)
        XCTAssertEqual(restored.scoreFlowStep, .putts)
        XCTAssertEqual(restored.draftScore, 5)
        XCTAssertEqual(restored.draftPutts, 3)
        XCTAssertEqual(restored.pendingManualShot?.hole, 2)
        XCTAssertEqual(restored.pendingManualShot?.candidateFromHole, 1)
        XCTAssertEqual(restored.pendingUploads, 0)

        restored.advanceScoreEntry()
        restored.selectDraftFairway(.hit)
        restored.saveManualScore()
        XCTAssertEqual(restored.activeHole, 2)
        XCTAssertEqual(restored.screen, .clubPrompt)

        restored.completePendingManualShot(clubName: nil)
        XCTAssertEqual(restored.round?.pendingEvents.map(\.kind), [.score, .putt, .location])
        XCTAssertEqual(restored.round?.pendingEvents.last?.hole, 2)
    }

    func testManualShotAtNextTeeWaitsForPreviousScoreThenBelongsToNextHole() {
        let model = seededModel(holes: [
            hole(1, par: 4, teeLatitude: 40.0, teeLongitude: 116.0),
            hole(2, par: 5, teeLatitude: 40.001, teeLongitude: 116.0),
        ])

        model.beginManualShot(
            latitude: 40.001,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T09:00:00Z"
        )

        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertEqual(model.pendingManualShot?.hole, 2)
        XCTAssertEqual(model.pendingManualShot?.candidateFromHole, 1)
        XCTAssertEqual(model.pendingUploads, 0)

        model.acceptRecommendedScore()

        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.screen, .clubPrompt)
        XCTAssertEqual(model.pendingManualShot?.hole, 2)
        XCTAssertNil(model.pendingManualShot?.candidateFromHole)

        model.completePendingManualShot(clubName: "一号木")

        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.score, .putt, .club, .location])
        XCTAssertEqual(model.round?.pendingEvents.suffix(2).map(\.hole), [2, 2])
        XCTAssertEqual(model.recordedShotCount, 1)
    }

    func testCancelPreviousScoreKeepsCandidateShotOnPreviousHole() {
        let model = seededModel(holes: [
            hole(1, teeLatitude: 40.0, teeLongitude: 116.0, shotType: "approach"),
            hole(2, teeLatitude: 40.001, teeLongitude: 116.0),
        ])
        model.beginManualShot(
            latitude: 40.001,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T09:00:00Z"
        )

        model.cancelScoring()

        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.screen, .clubPrompt)
        XCTAssertEqual(model.pendingManualShot?.hole, 1)
        XCTAssertNil(model.pendingManualShot?.candidateFromHole)
        model.completePendingManualShot(clubName: nil)
        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.location])
        XCTAssertEqual(model.round?.pendingEvents.first?.hole, 1)
        XCTAssertEqual(model.round?.pendingEvents.first?.shotType, "recovery")
        XCTAssertEqual(model.activeHoleState?.score, 0)
    }

    func testManualShotAtCurrentTeeDoesNotOpenPreviousScoreConfirmation() {
        let model = seededModel(holes: [
            hole(1, teeLatitude: 40.0, teeLongitude: 116.0),
            hole(2, teeLatitude: 40.0001, teeLongitude: 116.0),
        ])

        model.beginManualShot(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T09:00:00Z"
        )

        XCTAssertEqual(model.screen, .clubPrompt)
        XCTAssertEqual(model.pendingManualShot?.hole, 1)
        XCTAssertNil(model.pendingManualShot?.candidateFromHole)
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
        let model = seededModel(holes: [
            hole(1, score: 4, putts: 2),
            hole(2, score: 4, putts: 2),
            hole(3, score: 4, putts: 2),
        ])
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

    func testEditingHistoricalHoleDoesNotChangeActivePlayHole() {
        let model = seededModel(holes: [
            hole(1, score: 4, putts: 2),
            hole(2, score: 5, putts: 2),
            hole(3),
        ])
        model.selectHole(3)

        model.startEditingHole(1)
        XCTAssertEqual(model.activeHole, 3)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertEqual(model.scoreFlowStep, .score)
        model.adjustDraftScore(1)
        model.saveManualScore()

        XCTAssertEqual(model.round?.holeStates.first { $0.hole == 1 }?.score, 5)
        XCTAssertEqual(model.activeHole, 3)
        XCTAssertEqual(model.screen, .home)
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

    func testConfirmFinishWithoutConfigKeepsPendingRoundForLaterSync() async {
        let model = seededModel(holes: [hole(1, par: 4)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        let pendingBefore = model.pendingUploads
        model.requestFinish()

        await model.confirmFinish()

        XCTAssertNotNil(model.round)
        XCTAssertEqual(model.pendingUploads, pendingBefore)
        XCTAssertEqual(model.screen, .finishing)
        XCTAssertNotNil(model.uploadError)
    }

    func testConfirmFinishKeepsEventsMissingFromUploaderAcknowledgement() async {
        let model = seededModel(
            holes: [hole(1, par: 4)],
            uploader: { events, _ in [events[0].eventId] }
        )
        model.startScoringActiveHole()
        model.adjustDraftScore(1)
        model.saveActiveHole()
        XCTAssertEqual(model.pendingUploads, 2)
        model.requestFinish()

        await model.confirmFinish()

        XCTAssertNotNil(model.round)
        XCTAssertEqual(model.round?.pendingEvents.map(\.eventId), ["evt-2"])
        XCTAssertEqual(model.screen, .finishing)
        XCTAssertNotNil(model.uploadError)
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
