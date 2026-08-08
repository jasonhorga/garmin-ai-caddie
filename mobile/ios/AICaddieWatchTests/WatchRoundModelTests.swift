import CoreLocation
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
        shotType: String? = nil,
        globalId: Int? = nil,
        greenInRegulation: Bool? = nil,
        fairwayResult: String? = nil
    ) -> WatchRoundState {
        WatchRoundState(
            roundId: "r1", hole: n, par: par, distanceM: nil,
            teeLatitude: teeLatitude, teeLongitude: teeLongitude,
            selectedClub: nil,
            shotType: shotType,
            globalId: globalId,
            greenInRegulation: greenInRegulation,
            fairwayResult: fairwayResult,
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
        finisher: ((String, WatchRoundFinishMetadata) async throws -> Void)? = nil,
        config: WatchRoundConfig? = nil,
        autoShotEnabled: Bool = false,
        persistAutoShotEnabled: @escaping (Bool) -> Void = { _ in }
    ) -> WatchRoundModel {
        let model = WatchRoundModel(
            store: makeStore(),
            config: config,
            autoShotEnabled: autoShotEnabled,
            persistAutoShotEnabled: persistAutoShotEnabled,
            makeEventId: sequentialIds(),
            now: { "2026-06-20T00:00:00Z" },
            uploader: uploader,
            finisher: finisher
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

    func testCourseMapUpgradeKeepsRoundIdentityScoreAndDraft() {
        let partialMap = WatchHoleMap(
            w: 360,
            h: 560,
            you: [180, 520],
            pin: [180, 40],
            layup: [180, 260],
            apex: [180, 390],
            greenCtrl: [180, 150],
            route: [[180, 520, 0], [180, 40, 400]],
            greenOutline: [[170, 50], [190, 50], [180, 35]]
        )
        let current = WatchRoundState(
            roundId: "r1",
            hole: 1,
            par: 4,
            distanceM: 365,
            suggestedClub: "1W",
            selectedClub: "7I",
            globalId: 3881,
            holeMap: partialMap,
            geometryCoverage: "partial",
            hazards: [WatchHazard(kind: "water", label: "临时水域", startM: 120, endM: 150)],
            score: 5,
            putts: 2,
            penaltyCount: 1,
            caddieConfidence: "offline"
        )
        let model = seededModel(holes: [current])
        model.startScoringActiveHole()
        model.adjustDraftScore(1)

        let exactMap = WatchHoleMap(
            w: 678,
            h: 1060,
            you: [320, 980],
            pin: [350, 90],
            layup: [330, 520],
            apex: [325, 750],
            greenCtrl: [340, 300],
            route: [[320, 980, 0], [350, 90, 402]]
        )
        let exact = WatchRoundState(
            roundId: "r1",
            hole: 1,
            par: 4,
            distanceM: 368,
            suggestedClub: "1W",
            selectedClub: nil,
            globalId: 3881,
            holeMap: exactMap,
            geometryCoverage: "ready",
            score: 0,
            putts: 0,
            penaltyCount: 0,
            caddieConfidence: "offline"
        )

        model.applyCourseMapUpgrade([exact])

        XCTAssertEqual(model.round?.roundId, "r1")
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.activeHoleState?.geometryCoverage, "ready")
        XCTAssertEqual(model.activeHoleState?.holeMap?.w, 678)
        XCTAssertEqual(model.activeHoleState?.score, 5)
        XCTAssertEqual(model.activeHoleState?.putts, 2)
        XCTAssertEqual(model.activeHoleState?.penaltyCount, 1)
        XCTAssertEqual(model.activeHoleState?.selectedClub, "7I")
        XCTAssertTrue(
            model.activeHoleState?.hazards.isEmpty ?? false,
            "ready empty authority must clear partial ghost hazards"
        )
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.draftScore, 6)
    }

    func testCourseReleaseDowngradeClearsStalePreciseAuthorityUntilReplacementArrives() {
        let oldMap = WatchHoleMap(
            w: 678,
            h: 1060,
            you: [320, 980],
            pin: [350, 90],
            layup: [330, 520],
            apex: [325, 750],
            greenCtrl: [340, 300],
            route: [[320, 980, 0], [350, 90, 402]]
        )
        let current = WatchRoundState(
            roundId: "r-stale",
            hole: 1,
            par: 4,
            distanceM: 368,
            selectedClub: "7I",
            globalId: 3881,
            holeMap: oldMap,
            playsLikeDistanceM: 373,
            elevationDeltaM: 5,
            geometryCoverage: "ready",
            geometryRevision: "aaaaaaaaaaaaaaaa",
            hazards: [WatchHazard(kind: "water", label: "旧水域", startM: 120, endM: 150)],
            score: 5,
            putts: 2,
            penaltyCount: 1,
            caddieConfidence: "offline"
        )
        let model = seededModel(holes: [current])
        let refreshed = WatchRoundState(
            roundId: "r-stale",
            hole: 1,
            par: 4,
            distanceM: 368,
            globalId: 3881,
            holeMap: nil,
            geometryCoverage: "partial",
            geometryRevision: nil,
            hazards: [],
            score: 0,
            putts: 0,
            penaltyCount: 0,
            caddieConfidence: "offline"
        )

        model.applyCourseMapUpgrade([refreshed])

        XCTAssertEqual(model.activeHoleState?.geometryCoverage, "partial")
        XCTAssertNil(model.activeHoleState?.geometryRevision)
        XCTAssertNil(model.activeHoleState?.holeMap)
        XCTAssertNil(model.activeHoleState?.playsLikeDistanceM)
        XCTAssertTrue(model.activeHoleState?.hazards.isEmpty ?? false)
        XCTAssertEqual(model.activeHoleState?.selectedClub, "7I")
        XCTAssertEqual(model.activeHoleState?.score, 5)
        XCTAssertEqual(model.activeHoleState?.putts, 2)
        XCTAssertEqual(model.activeHoleState?.penaltyCount, 1)
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

    func testFinishOutcomesCountOnlyExplicitValidResultsOnScoredHoles() {
        let model = seededModel(holes: [
            hole(1, par: 4, score: 4, greenInRegulation: true, fairwayResult: "HIT"),
            hole(2, par: 5, score: 6, greenInRegulation: false, fairwayResult: "left"),
            hole(3, par: 3, score: 3, greenInRegulation: true),
            hole(4, par: 4, score: 5),
            hole(5, par: 4, score: 0, greenInRegulation: true, fairwayResult: "HIT"),
            hole(6, par: 4, score: 4, fairwayResult: "center"),
        ])

        XCTAssertEqual(model.fairwaySummary, WatchOutcomeSummary(hits: 1, recorded: 2))
        XCTAssertEqual(model.girSummary, WatchOutcomeSummary(hits: 2, recorded: 3))
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
        XCTAssertEqual(
            model.round?.pendingEvents.first(where: { $0.kind == .score })?.fairwayResult,
            "LEFT"
        )
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

    func testCurrentHoleShotListReusesRecordedClubAndLocationFacts() throws {
        let model = seededModel(holes: [hole(1), hole(2)])
        model.beginManualShot(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 4,
            capturedAt: "2026-07-26T08:00:00Z"
        )
        model.completePendingManualShot(clubName: "一号木")
        model.beginManualShot(
            latitude: 40.001,
            longitude: 116.0,
            horizontalAccuracyM: 4,
            capturedAt: "2026-07-26T08:05:00Z"
        )
        model.completePendingManualShot(clubName: nil)

        let shots = model.currentHoleShots

        XCTAssertEqual(shots.map(\.number), [1, 2])
        XCTAssertEqual(shots.map(\.clubName), ["一号木", nil])
        XCTAssertEqual(
            try XCTUnwrap(shots.first?.distanceToNextM),
            WatchGeoMath.metres(40.0, 116.0, 40.001, 116.0),
            accuracy: 0.01
        )
        XCTAssertNil(shots.last?.distanceToNextM)
        model.openCurrentHoleShots()
        XCTAssertEqual(model.screen, .currentHoleShots)
        XCTAssertEqual(model.activeHole, 1)
    }

    func testDistanceFromLatestShotUsesLastValidLocationOnActiveHole() throws {
        let store = makeStore()
        let events = [
            WatchInputEvent(
                eventId: "hole-1-old",
                roundId: "r1",
                hole: 1,
                kind: .location,
                value: "40.0,116.0,5.0",
                createdAt: "2026-07-26T08:00:00Z"
            ),
            WatchInputEvent(
                eventId: "hole-1-latest",
                roundId: "r1",
                hole: 1,
                kind: .location,
                value: "40.001,116.0,5.0",
                createdAt: "2026-07-26T08:05:00Z"
            ),
            WatchInputEvent(
                eventId: "other-hole",
                roundId: "r1",
                hole: 2,
                kind: .location,
                value: "41.0,116.0,5.0",
                createdAt: "2026-07-26T08:10:00Z"
            ),
            WatchInputEvent(
                eventId: "damaged-current-hole-value",
                roundId: "r1",
                hole: 1,
                kind: .location,
                value: "not-a-location",
                createdAt: "2026-07-26T08:15:00Z"
            ),
        ]
        try store.save(WatchRoundStore.PersistedRound(
            roundId: "r1",
            activeHole: 1,
            holeStates: [hole(1), hole(2)],
            pendingEvents: events
        ))
        let model = WatchRoundModel(store: store)

        let distance = try XCTUnwrap(model.distanceFromLatestShotM(
            latitude: 40.002,
            longitude: 116.0
        ))

        XCTAssertEqual(
            distance,
            WatchGeoMath.metres(40.001, 116.0, 40.002, 116.0),
            accuracy: 0.01
        )
    }

    func testDistanceFromLatestShotIsNilWithoutAValidCurrentHoleLocation() {
        let model = seededModel(holes: [hole(1)])

        XCTAssertNil(model.distanceFromLatestShotM(latitude: 40.0, longitude: 116.0))
        XCTAssertNil(model.distanceFromLatestShotM(latitude: .nan, longitude: 116.0))
    }

    func testRoundHomeDistancePrefersLiveWatchCenterYards() {
        let state = WatchRoundState(
            roundId: "r1",
            hole: 1,
            par: 4,
            distanceM: 365,
            selectedClub: nil,
            centerGreenM: 240,
            score: 0,
            putts: 0,
            penaltyCount: 0,
            caddieConfidence: "offline"
        )
        let model = seededModel(holes: [state])
        let view = WatchRoundContainerView(
            model: model,
            watchGreenYards: (front: 199, center: 211, back: 223)
        )

        XCTAssertEqual(view.distanceText, "211 码")
    }

    func testAutoShotIsOptInAndRejectedCandidateWritesNoShotEvent() {
        var savedPreferences: [Bool] = []
        let model = seededModel(
            holes: [hole(1)],
            persistAutoShotEnabled: { savedPreferences.append($0) }
        )

        XCTAssertFalse(model.proposeAutoShotCandidate(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        ))
        XCTAssertNil(model.pendingAutoShotCandidate)

        model.setAutoShotEnabled(true)
        XCTAssertEqual(savedPreferences, [true])
        XCTAssertTrue(model.proposeAutoShotCandidate(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        ))
        XCTAssertEqual(model.screen, .autoShotCandidate)
        XCTAssertNotNil(model.pendingAutoShotCandidate)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true)

        model.rejectAutoShotCandidate()

        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.pendingAutoShotCandidate)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true)
    }

    func testAcceptedAutoShotUsesExistingClubAndLocationEventPath() {
        let model = seededModel(holes: [hole(1)], autoShotEnabled: true)
        XCTAssertTrue(model.proposeAutoShotCandidate(
            latitude: 40.0454995,
            longitude: 116.5461531,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        ))

        model.acceptAutoShotCandidate()

        XCTAssertNil(model.pendingAutoShotCandidate)
        XCTAssertEqual(model.screen, .clubPrompt)
        XCTAssertEqual(model.pendingManualShot?.hole, 1)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true)

        model.completePendingManualShot(clubName: "一号木")

        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.club, .location])
        XCTAssertEqual(model.recordedShotCount, 1)
    }

    func testRejectedAutoShotCandidateRestoresOriginatingHoleMapAfterRelaunch() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("autoshot-map-reject-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            autoShotEnabled: true,
            persistAutoShotEnabled: { _ in }
        )
        first.seedRound([hole(1)])
        first.openHoleMap()
        XCTAssertTrue(first.proposeAutoShotCandidate(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        ))

        let restored = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            autoShotEnabled: true,
            persistAutoShotEnabled: { _ in }
        )
        restored.rejectAutoShotCandidate()

        XCTAssertEqual(restored.screen, .holeMap)
        XCTAssertNil(restored.pendingAutoShotCandidate)
        XCTAssertTrue(restored.round?.pendingEvents.isEmpty == true)
    }

    func testAcceptedAutoShotFromHoleMapReturnsThereAfterClubConfirmation() {
        let model = seededModel(holes: [hole(1)], autoShotEnabled: true)
        model.openHoleMap()
        XCTAssertTrue(model.proposeAutoShotCandidate(
            latitude: 40.0454995,
            longitude: 116.5461531,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        ))

        model.acceptAutoShotCandidate()
        XCTAssertEqual(model.screen, .clubPrompt)
        model.completePendingManualShot(clubName: nil)

        XCTAssertEqual(model.screen, .holeMap)
        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.location])
    }

    func testAutoShotCandidateRestoresWithoutBecomingARecordedShot() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("autoshot-restore-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            autoShotEnabled: true,
            persistAutoShotEnabled: { _ in }
        )
        first.seedRound([hole(1)])
        XCTAssertTrue(first.proposeAutoShotCandidate(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        ))

        let restored = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            autoShotEnabled: true,
            persistAutoShotEnabled: { _ in }
        )

        XCTAssertEqual(restored.screen, .autoShotCandidate)
        XCTAssertEqual(restored.pendingAutoShotCandidate?.capturedAt, "2026-07-26T12:00:00Z")
        XCTAssertTrue(restored.round?.pendingEvents.isEmpty == true)
    }

    func testAcceptedAutoShotAtNextTeeReusesPreviousHoleConfirmation() {
        let model = seededModel(
            holes: [
                hole(1, teeLatitude: 40.0, teeLongitude: 116.0),
                hole(2, teeLatitude: 40.001, teeLongitude: 116.0),
            ],
            autoShotEnabled: true
        )
        XCTAssertTrue(model.proposeAutoShotCandidate(
            latitude: 40.001,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        ))

        model.acceptAutoShotCandidate()

        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.pendingManualShot?.hole, 2)
        XCTAssertEqual(model.pendingManualShot?.candidateFromHole, 1)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true)
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

    func testCaddieSurfaceOpensOnlyWhenTheActiveHoleHasARecommendation() {
        let recommended = WatchRoundState(
            roundId: "r1", hole: 1, par: 5, distanceM: 480,
            suggestedClub: "3号木", selectedClub: nil,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let model = seededModel(holes: [recommended])

        model.openCaddie()
        XCTAssertEqual(model.screen, .caddie)
        model.backToMenu()
        XCTAssertEqual(model.screen, .menu)

        let factsOnly = seededModel(holes: [hole(1)])
        factsOnly.openCaddie()
        XCTAssertEqual(factsOnly.screen, .home)
    }

    func testHazardSurfaceOpensOnlyWhenTheActiveHoleHasHazards() {
        let withHazard = WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: 320,
            selectedClub: nil,
            hazards: [WatchHazard(kind: "bunker", label: "沙坑", startM: 180, sideM: 15)],
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let model = seededModel(holes: [withHazard])

        model.openHazards()
        XCTAssertEqual(model.screen, .hazards)
        model.backToMenu()
        XCTAssertEqual(model.screen, .menu)

        let noHazards = seededModel(holes: [hole(1)])
        noHazards.openHazards()
        XCTAssertEqual(noHazards.screen, .home)
    }

    func testRootCaddieLayerAppearsForACompleteCurrentLiveRecommendation() throws {
        let data = Data(
            #"""
            {
              "roundId": "r1",
              "hole": 1,
              "par": 4,
              "distanceM": 320,
              "suggestedClub": "3W",
              "decisionId": "decision-1",
              "holeMap": {
                "w": 1000,
                "h": 1000,
                "you": [500, 900],
                "pin": [500, 100],
                "layup": [500, 500],
                "apex": [500, 700],
                "greenCtrl": [500, 300],
                "route": [[500, 900, 0], [500, 500, 200], [500, 100, 400]]
              },
              "rootCaddieRecommendation": {
                "decisionId": "decision-1",
                "clubName": "3W",
                "aimCarryM": 205,
                "carryP10M": 188,
                "carryP90M": 220,
                "sampleSize": 24,
                "confidence": "high",
                "source": "live",
                "mode": "automatic",
                "generatedAt": "2026-06-20T00:00:00Z",
                "validUntil": "2026-06-20T00:00:12Z",
                "originLatitude": 40.0455,
                "originLongitude": 116.5462,
                "originAccuracyM": 5,
                "maximumMovementM": 25,
                "evidenceCount": 2
              },
              "score": 0,
              "putts": 0,
              "penaltyCount": 0,
              "caddieConfidence": "high"
            }
            """#.utf8
        )
        let recommendation = try JSONDecoder().decode(WatchRoundState.self, from: data)
        let model = seededModel(holes: [recommendation])

        XCTAssertTrue(model.rootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
            horizontalAccuracyM: 5,
            capturedAt: "2026-06-20T00:00:00Z"
        )))
        XCTAssertFalse(model.rootCaddieLayerAvailable(at: nil))
        XCTAssertFalse(model.rootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
            horizontalAccuracyM: 16,
            capturedAt: "2026-06-20T00:00:00Z"
        )))
        XCTAssertFalse(model.rootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
            horizontalAccuracyM: 5,
            capturedAt: "2026-06-19T23:59:44Z"
        )))
        XCTAssertFalse(model.rootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0458, longitude: 116.5462),
            horizontalAccuracyM: 5,
            capturedAt: "2026-06-20T00:00:00Z"
        )))
    }

    func testPreparedRootCaddieAppearsAtTeeAndExpiresAfterLeavingTee() {
        let state = WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: 400,
            teeLatitude: 40.0455, teeLongitude: 116.5462,
            suggestedClub: "1W", selectedClub: nil,
            holeMap: WatchHoleMap(
                w: 1000,
                h: 1000,
                you: [500, 900],
                pin: [500, 100],
                layup: [500, 500],
                apex: [500, 700],
                greenCtrl: [500, 300],
                route: [[500, 900, 0], [500, 500, 220], [500, 100, 400]]
            ),
            geometryCoverage: "ready",
            caddieOptions: [
                WatchCaddieOption(
                    optionId: "stock", label: "标准", clubName: "1W", carryM: 220,
                    plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 220)],
                    confidence: "offline"
                ),
            ],
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let model = seededModel(holes: [state])

        XCTAssertTrue(model.preparedRootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
            horizontalAccuracyM: 6,
            capturedAt: "2026-06-20T00:00:00Z"
        )))
        XCTAssertFalse(model.preparedRootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0461, longitude: 116.5462),
            horizontalAccuracyM: 6,
            capturedAt: "2026-06-20T00:00:00Z"
        )))

        let partial = state.applyingCourseMapUpgrade(WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: nil, selectedClub: nil,
            geometryCoverage: "partial",
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        ))
        let partialModel = seededModel(holes: [partial])
        XCTAssertFalse(partialModel.preparedRootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
            horizontalAccuracyM: 6,
            capturedAt: "2026-06-20T00:00:00Z"
        )))
    }

    func testPlaysLikeDeltaConvertsMetresToUserFacingYards() {
        let uphill = WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: 320,
            selectedClub: nil, elevationDeltaM: 7,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let model = seededModel(holes: [uphill])

        XCTAssertEqual(model.activePlaysLikeDeltaYards, 8)
    }

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

    func testFinishSummaryRequiresExplicitConfirmationBeforeUpload() {
        let model = seededModel(holes: [hole(1)])

        model.requestFinish()
        model.requestFinishConfirmation()
        XCTAssertEqual(model.screen, .finishConfirmation)

        model.cancelFinishConfirmation()
        XCTAssertEqual(model.screen, .finishing)
    }

    func testFinishCannotUploadUntilConfirmationScreenIsAccepted() async {
        var finishCalls = 0
        let model = seededModel(
            holes: [hole(1, score: 4)],
            finisher: { _, _ in finishCalls += 1 }
        )

        model.requestFinish()
        await model.confirmFinish()

        XCTAssertEqual(finishCalls, 0)
        XCTAssertNotNil(model.round)
        XCTAssertEqual(model.screen, .finishing)

        model.requestFinishConfirmation()
        await model.confirmFinish()

        XCTAssertEqual(finishCalls, 1)
        XCTAssertNil(model.round)
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
        var finishedRoundId: String?
        var finishMetadata: WatchRoundFinishMetadata?
        let model = seededModel(
            holes: [hole(1, par: 4, globalId: 12345), hole(2, par: 5, globalId: 12345)],
            uploader: { events, _ in received = events; return events.map(\.eventId) },
            finisher: { roundId, metadata in
                finishedRoundId = roundId
                finishMetadata = metadata
            }
        )
        model.startScoringActiveHole()
        model.adjustDraftScore(1)
        model.saveActiveHole()                          // 2 pending events
        XCTAssertEqual(model.pendingUploads, 2)
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()
        XCTAssertEqual(received.count, 2)               // uploader saw the queued events
        XCTAssertEqual(finishedRoundId, "r1")
        XCTAssertEqual(finishMetadata?.courseName, "北京丽宫 · 前九")
        XCTAssertEqual(finishMetadata?.holePars, [4, 5])
        XCTAssertEqual(finishMetadata?.holesCompleted, 1)
        XCTAssertEqual(finishMetadata?.courseGlobalId, 12345)
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
        model.requestFinish()
        model.requestFinishConfirmation()
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
        model.requestFinishConfirmation()

        await model.confirmFinish()

        XCTAssertNotNil(model.round)
        XCTAssertEqual(model.pendingUploads, pendingBefore)
        XCTAssertEqual(model.screen, .finishConfirmation)
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
        model.requestFinishConfirmation()

        await model.confirmFinish()

        XCTAssertNotNil(model.round)
        XCTAssertEqual(model.round?.pendingEvents.map(\.eventId), ["evt-2"])
        XCTAssertEqual(model.screen, .finishConfirmation)
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
