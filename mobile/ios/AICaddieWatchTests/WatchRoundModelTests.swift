import CoreLocation
import Foundation
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
        sourceLocalHole: Int? = nil,
        courseHoleNumber: Int? = nil,
        greenInRegulation: Bool? = nil,
        fairwayResult: String? = nil
    ) -> WatchRoundState {
        // A course hole carries its full physical identity (front-nine / nine-hole-loop row by
        // default); a score-only hole carries none.
        WatchRoundState(
            roundId: "r1", hole: n, par: par, distanceM: nil,
            teeLatitude: teeLatitude, teeLongitude: teeLongitude,
            selectedClub: nil,
            shotType: shotType,
            globalId: globalId,
            sourceLocalHole: sourceLocalHole ?? (globalId == nil ? nil : n),
            courseHoleNumber: courseHoleNumber ?? (globalId == nil ? nil : n),
            greenInRegulation: greenInRegulation,
            fairwayResult: fairwayResult,
            score: score, putts: putts, penaltyCount: penalty, caddieConfidence: "offline"
        )
    }

    /// A course round holds its complete table: every round position of `loopKey` with its
    /// physical identity. `holes` supply the facts for the positions a test cares about; the rest
    /// are blank par-4 holes. All snapshots take `roundId`.
    private func courseHoles(
        _ loopKey: String,
        roundId: String = "r1",
        _ holes: [WatchRoundState] = []
    ) -> [WatchRoundState] {
        let given = Dictionary(holes.map { ($0.hole, $0) }, uniquingKeysWith: { first, _ in first })
        return (WatchCourseSelection.roundRows(loopKey: loopKey) ?? []).map { row in
            let base = given[row.number] ?? WatchRoundState(
                roundId: roundId, hole: row.number, par: 4, distanceM: nil, selectedClub: nil,
                globalId: row.globalId,
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
            )
            return base.replacingRoundId(
                roundId,
                hole: row.number,
                sourceLocalHole: row.sourceLocalHole,
                courseHoleNumber: row.courseHoleNumber
            )
        }
    }

    /// A phone seed carries the package's complete table.
    private func courseSeedHoles(_ loopKey: String, _ holes: [WatchRoundSeedHole]) -> [WatchRoundSeedHole] {
        let given = Dictionary(holes.map { ($0.hole, $0) }, uniquingKeysWith: { first, _ in first })
        return (WatchCourseSelection.roundRows(loopKey: loopKey) ?? []).map { row in
            let hole = given[row.number]
            return WatchRoundSeedHole(
                hole: row.number,
                par: hole?.par ?? 4,
                distanceM: hole?.distanceM,
                teeLatitude: hole?.teeLatitude,
                teeLongitude: hole?.teeLongitude,
                globalId: row.globalId,
                localHole: row.sourceLocalHole,
                courseHoleNumber: row.courseHoleNumber
            )
        }
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
        // Course fixtures seed under their whole-course key with full physical identity; score-only
        // fixtures stay a practice round (no loop key).
        let courseId = holes.compactMap(\.globalId).first
        let loopKey = courseId.map { "\($0):front+\($0):back" }
        let seeded = loopKey.map { courseHoles($0, roundId: holes.first?.roundId ?? "r1", holes) } ?? holes
        model.seedRound(
            seeded,
            activeHole: holes.first?.hole,
            courseName: "北京丽宫 · 前九",
            loopKey: loopKey
        )
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
            holes: courseSeedHoles("31795:all", [
                WatchRoundSeedHole(hole: 1, par: 4, distanceM: 365, globalId: 31795, localHole: 1, courseHoleNumber: 1),
                WatchRoundSeedHole(hole: 2, par: 3, distanceM: 148, globalId: 31795, localHole: 2, courseHoleNumber: 2),
                WatchRoundSeedHole(hole: 3, par: 5, distanceM: 472, globalId: 31795, localHole: 3, courseHoleNumber: 3),
            ]),
            loopKey: "31795:all"
        )

        model.applyRoundSeed(seed)

        XCTAssertEqual(model.courseName, "北京丽宫")
        XCTAssertEqual(model.holeCount, 9, "a course round holds its whole loop")
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.activeHoleState?.par, 3)
        XCTAssertEqual(model.activeHoleState?.distanceM, 148)
        XCTAssertEqual(model.activeHoleState?.globalId, 31795)
        XCTAssertEqual(model.round?.loopKey, "31795:all", "the phone seed's loop key is round state")
        XCTAssertEqual(model.screen, .resume)
        XCTAssertFalse(model.hasRecordedProgress)
        XCTAssertFalse(model.canSaveAndEndFromResume)
        model.requestSaveAndEndFromResume()
        XCTAssertEqual(model.screen, .resume, "an empty new round cannot create an unfinishable archive")

        let relaunched = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory)
        )
        XCTAssertEqual(relaunched.courseName, "北京丽宫")
        XCTAssertEqual(relaunched.holeCount, 9)
        XCTAssertEqual(relaunched.activeHole, 2)
        XCTAssertEqual(relaunched.round?.loopKey, "31795:all")
        XCTAssertEqual(relaunched.screen, .resume)
    }

    func testPersistedRoundLoopKeySurvivesStoreSaveAndLoad() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("loop-key-round-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchRoundStore(directoryURL: directory)
        try store.save(WatchRoundStore.PersistedRound(
            roundId: "r-back-front",
            activeHole: 10,
            holeStates: courseHoles("41825:back+41825:front", roundId: "r-back-front"),
            courseGlobalId: 41825,
            teeBox: "Blue",
            loopKey: "41825:back+41825:front"
        ))

        let loaded = try XCTUnwrap(WatchRoundStore(directoryURL: directory).load())
        XCTAssertEqual(loaded.loopKey, "41825:back+41825:front")
        XCTAssertEqual(loaded.teeBox, "Blue")
        XCTAssertEqual(loaded.courseGlobalId, 41825)

        // A Watch-started round seeds its loop key through the model and restores it on relaunch.
        let seededDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("loop-key-seed-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: seededDirectory) }
        let first = WatchRoundModel(store: WatchRoundStore(directoryURL: seededDirectory))
        first.seedRound(
            courseHoles("41825:front+41825:front"),
            activeHole: 1,
            courseName: "测试球场",
            courseGlobalId: 41825,
            teeBox: "Blue",
            loopKey: "41825:front+41825:front"
        )
        let relaunched = WatchRoundModel(store: WatchRoundStore(directoryURL: seededDirectory))
        XCTAssertEqual(relaunched.round?.loopKey, "41825:front+41825:front")
        XCTAssertEqual(relaunched.round?.teeBox, "Blue")
    }

    func testGreenPlacementPersistsPerHoleAcrossRelaunchAndSeedRefresh() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("green-placement-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        first.seedRound(
            courseHoles("31669:front+31669:back"),
            activeHole: 1,
            loopKey: "31669:front+31669:back"
        )

        first.saveGreenPlacement(
            hole: 1,
            globalId: 31669,
            normalizedPinX: 0.42,
            normalizedPinY: 0.31,
            rotationDegrees: 450
        )

        let relaunched = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        let restored = try XCTUnwrap(relaunched.greenPlacement(forHole: 1, globalId: 31669))
        XCTAssertEqual(restored.normalizedPinX, 0.42, accuracy: 0.000_001)
        XCTAssertEqual(restored.normalizedPinY, 0.31, accuracy: 0.000_001)
        XCTAssertEqual(restored.rotationDegrees, 90, accuracy: 0.000_001)
        XCTAssertNil(relaunched.greenPlacement(forHole: 2, globalId: 31669))
        XCTAssertNil(relaunched.greenPlacement(forHole: 1, globalId: 99999))

        relaunched.applyRoundSeed(WatchRoundSeed(
            roundId: "r1",
            courseName: "刷新后的同一球局",
            activeHole: 1,
            holes: courseSeedHoles("31669:front+31669:back", [
                WatchRoundSeedHole(hole: 1, par: 4, distanceM: 360, globalId: 31669, localHole: 1, courseHoleNumber: 1),
                WatchRoundSeedHole(hole: 2, par: 4, distanceM: 350, globalId: 31669, localHole: 2, courseHoleNumber: 2),
            ]),
            loopKey: "31669:front+31669:back"
        ))
        XCTAssertEqual(
            relaunched.greenPlacement(forHole: 1, globalId: 31669)?.rotationDegrees,
            90
        )
    }

    func testGreenPlacementIsClearedWithTerminalRoundClosure() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("green-placement-close-\(UUID().uuidString)", isDirectory: true)
        let model = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        model.seedRound(courseHoles("31669:front+31669:back"), activeHole: 1, loopKey: "31669:front+31669:back")
        model.saveGreenPlacement(
            hole: 1,
            globalId: 31669,
            normalizedPinX: 0.5,
            normalizedPinY: 0.5,
            rotationDegrees: 12
        )

        model.requestAbandon()
        model.confirmAbandon()

        XCTAssertNil(model.round)
        XCTAssertNil(WatchRoundStore(directoryURL: directory).load())
    }

    func testDeferredFinishDoesNotArchiveRoundScopedGreenPlacement() throws {
        let store = makeStore()
        let round = WatchRoundStore.PersistedRound(
            roundId: "r1",
            greenPlacements: [
                WatchGreenPlacement(
                    hole: 1,
                    globalId: 31669,
                    normalizedPinX: 0.5,
                    normalizedPinY: 0.5,
                    rotationDegrees: 12
                ),
            ]
        )

        _ = try store.deferFinish(round, savedAt: "2026-08-17T00:00:00Z")

        XCTAssertNil(store.loadDeferredFinishes().first?.round.greenPlacements)
    }

    func testLegacyPersistedRoundWithoutGreenPlacementsStillDecodes() throws {
        let data = try XCTUnwrap(
            """
            {"roundId":"legacy","activeHole":1,"holeStates":[],"pendingEvents":[]}
            """.data(using: .utf8)
        )

        let decoded = try JSONDecoder().decode(WatchRoundStore.PersistedRound.self, from: data)

        XCTAssertEqual(decoded.roundId, "legacy")
        XCTAssertNil(decoded.greenPlacements)
    }

    func testRestoredScoreDraftWaitsAtResumeGateUntilPlayerContinues() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("resume-round-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        first.seedRound([hole(1)])
        first.startScoringActiveHole()
        first.adjustDraftScore(1)

        let relaunched = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))

        XCTAssertEqual(relaunched.screen, .resume)
        XCTAssertEqual(relaunched.round?.scoreDraft?.score, 5)
        relaunched.applyRoundSeed(WatchRoundSeed(
            roundId: "r1",
            courseName: "北京丽宫",
            activeHole: 1,
            holes: courseSeedHoles("31795:all", [WatchRoundSeedHole(hole: 1, par: 4, distanceM: 350, globalId: 31795, localHole: 1, courseHoleNumber: 1)]),
            loopKey: "31795:all"
        ))
        XCTAssertEqual(relaunched.screen, .resume)
        relaunched.resumeRound()
        XCTAssertEqual(relaunched.screen, .scoring)
        XCTAssertEqual(relaunched.draftScore, 5)
    }

    func testDifferentPhoneSeedCannotOverwriteAnActiveWatchRound() {
        let model = seededModel(holes: [hole(1)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        let pending = model.round?.pendingEvents

        model.applyRoundSeed(WatchRoundSeed(
            roundId: "stale-or-new-phone-round",
            courseName: "Other course",
            activeHole: 1,
            holes: courseSeedHoles("31795:all", [WatchRoundSeedHole(hole: 1, par: 3, distanceM: 120, globalId: 31795, localHole: 1, courseHoleNumber: 1)]),
            loopKey: "31795:all"
        ))

        XCTAssertEqual(model.round?.roundId, "r1")
        XCTAssertEqual(model.round?.pendingEvents, pending)
        XCTAssertEqual(model.courseName, "北京丽宫 · 前九")
        XCTAssertEqual(model.pendingPhoneRoundCourseName, "Other course")
        XCTAssertEqual(model.screen, .resume)
    }

    func testDifferentPhoneSeedReplacesAnEmptyStandaloneRound() {
        let model = seededModel(holes: [hole(1)])

        model.applyRoundSeed(WatchRoundSeed(
            roundId: "phone-round",
            courseName: "Phone course",
            activeHole: 1,
            holes: courseSeedHoles("31795:all", [WatchRoundSeedHole(hole: 1, par: 3, distanceM: 120, globalId: 31795, localHole: 1, courseHoleNumber: 1)]),
            loopKey: "31795:all"
        ))

        XCTAssertEqual(model.round?.roundId, "phone-round")
        XCTAssertEqual(model.courseName, "Phone course")
        XCTAssertEqual(model.lastRoundClosure?.roundId, "r1")
        XCTAssertEqual(model.lastRoundClosure?.disposition, .abandoned)
        XCTAssertNil(model.pendingPhoneRoundCourseName)
        XCTAssertEqual(model.screen, .resume)
    }

    func testAbandoningAConflictingWatchRoundActivatesThePendingPhoneRound() {
        let model = seededModel(holes: [hole(1)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.applyRoundSeed(WatchRoundSeed(
            roundId: "phone-round",
            courseName: "Phone course",
            activeHole: 1,
            holes: courseSeedHoles("31795:all", [WatchRoundSeedHole(hole: 1, par: 3, distanceM: 120, globalId: 31795, localHole: 1, courseHoleNumber: 1)]),
            loopKey: "31795:all"
        ))

        model.requestAbandon()
        model.confirmAbandon()

        XCTAssertEqual(model.round?.roundId, "phone-round")
        XCTAssertEqual(model.courseName, "Phone course")
        XCTAssertNil(model.pendingPhoneRoundCourseName)
        XCTAssertEqual(model.screen, .resume)
    }

    func testMatchingPhoneSeedRefreshesFactsWithoutMovingTheWatchCursorOrScreen() {
        let model = seededModel(holes: [hole(1), hole(2)])
        model.selectHole(2)
        model.openMenu()

        model.applyRoundSeed(WatchRoundSeed(
            roundId: "r1",
            courseName: "北京丽宫 · 后九",
            activeHole: 1,
            holes: courseSeedHoles("31795:all", [
                WatchRoundSeedHole(hole: 1, par: 4, distanceM: 350, globalId: 31795, localHole: 1, courseHoleNumber: 1),
                WatchRoundSeedHole(hole: 2, par: 4, distanceM: 365, globalId: 31795, localHole: 2, courseHoleNumber: 2),
            ]),
            loopKey: "31795:all"
        ))

        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.screen, .menu)
        XCTAssertEqual(model.courseName, "北京丽宫 · 后九")
        XCTAssertEqual(model.round?.holeStates.first { $0.hole == 2 }?.globalId, 31795)
    }

    func testPhoneReseedDropsScoreDraftForAHoleThatNoLongerExists() {
        // A ten-hole score-only round; the phone's nine-hole course table has no hole 10.
        let model = seededModel(holes: (1...10).map { hole($0) })
        model.selectHole(10)
        model.startScoringActiveHole()
        model.adjustDraftScore(1)
        XCTAssertEqual(model.round?.scoreDraft?.hole, 10)

        model.applyRoundSeed(WatchRoundSeed(
            roundId: "r1",
            courseName: "Back nine",
            activeHole: 2,
            holes: courseSeedHoles("31795:all", [WatchRoundSeedHole(hole: 2, par: 4, distanceM: 350, globalId: 31795, localHole: 2, courseHoleNumber: 2)]),
            loopKey: "31795:all"
        ))

        XCTAssertNil(model.round?.scoreDraft)
        XCTAssertNil(model.scoringHole)
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.screen, .home)
    }

    func testPhoneReseedDropsVisibleManualShotForAHoleThatNoLongerExists() {
        let model = seededModel(holes: (1...10).map { hole($0) })
        model.selectHole(10)
        model.beginManualShot(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-08-09T08:00:00Z"
        )
        XCTAssertEqual(model.pendingManualShot?.hole, 10)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNotNil(model.undoableShotText)

        model.applyRoundSeed(WatchRoundSeed(
            roundId: "r1",
            courseName: "Back nine",
            activeHole: 2,
            holes: courseSeedHoles("31795:all", [WatchRoundSeedHole(hole: 2, par: 4, distanceM: 350, globalId: 31795, localHole: 2, courseHoleNumber: 2)]),
            loopKey: "31795:all"
        ))

        XCTAssertNil(model.round?.pendingManualShot)
        XCTAssertNil(model.pendingManualShot)
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.screen, .home)
    }

    func testInvalidPersistedActiveHoleFallsBackToFirstRealHole() throws {
        let store = makeStore()
        try store.save(WatchRoundStore.PersistedRound(
            roundId: "r1",
            activeHole: 99,
            holeStates: [hole(2), hole(3)]
        ))

        let model = WatchRoundModel(store: store)

        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.activeHoleState?.hole, 2)
    }

    func testDelayedPhoneClosureCannotStopOrDeleteANewerWatchRound() {
        let model = seededModel(holes: [hole(1)])

        model.applyPhoneRoundClosure(WatchRoundClosure(
            roundId: "older-round",
            disposition: .finished,
            closedAt: "2026-08-09T00:00:00Z"
        ))

        XCTAssertEqual(model.round?.roundId, "r1")
        XCTAssertEqual(model.screen, .home)
    }

    /// B7 step 1 (Codex review on #368): running the whole collection path (session, router, store,
    /// uploader) through a phone Finish leaves the round, its events and the score byte-for-byte as
    /// they are without collection, and hands the closed round's candidates to the uploader.
    func testSwingCandidateCollectionNeverChangesTheRoundOrItsEvents() async throws {
        func scriptedRound(collecting: Bool) async throws -> (round: Data, deferred: Data, uploaded: [String]) {
            let store = makeStore()
            let model = WatchRoundModel(
                store: store,
                makeEventId: sequentialIds(),
                now: { "2026-08-09T00:00:00Z" }
            )
            model.seedRound([hole(1)])
            model.startScoringActiveHole()
            model.saveActiveHole()
            let candidates = WatchSwingCandidateStore(directoryURL: FileManager.default.temporaryDirectory
                .appendingPathComponent("swing-e2e-\(UUID().uuidString)", isDirectory: true))
            var router = WatchSwingCandidateRouter()
            let start = Date(timeIntervalSince1970: 1_790_000_000)
            router.roundChanged(to: model.round?.roundId, at: start)
            router.holeChanged(to: model.activeHole, at: start)
            var lateObservation: WatchSwingObservation?
            if collecting {
                var session = WatchSwingCollectionSession()
                _ = session.detection(at: 2.0, autoShotWanted: false)
                session.accelerationBatch(stride(from: 1.95, to: 2.05, by: 0.001).map {
                    WatchAutoShotAccelerationSample(timestamp: $0, x: 0, y: 0, z: abs($0 - 2.0) < 0.003 ? 5 : 1)
                })
                var t = 0.0
                var rotation: [WatchAutoShotRotationSample] = []
                while t < 3.1 {
                    let swinging = t >= 1.5 && t < 2.5
                    rotation.append(WatchAutoShotRotationSample(timestamp: t, rotationAlongGravity: swinging ? 9 : 0.05))
                    t += 0.01
                }
                // The swing ends 30 s into the round, but its batches are delivered only after the
                // phone closed the round (uptime 3.1 at delivery = 90 s into the round).
                for batchStart in stride(from: 0, to: rotation.count, by: 25) {
                    let batch = Array(rotation[batchStart..<min(batchStart + 25, rotation.count)])
                    if let observation = session.rotationBatch(
                        batch, now: start.addingTimeInterval(90), uptime: 3.1 + 60
                    ) {
                        lateObservation = observation
                    }
                }
                XCTAssertNotNil(lateObservation)
            }
            model.applyPhoneRoundClosure(WatchRoundClosure(
                roundId: "r1",
                disposition: .finished,
                closedAt: "2026-08-09T01:00:00Z"
            ))
            XCTAssertEqual(model.activeHole, 0, "no round: the model's active hole is not a valid hole")
            XCTAssertEqual(router.roundChanged(to: model.round?.roundId, at: start.addingTimeInterval(60)), "r1")
            router.holeChanged(to: model.activeHole, at: start.addingTimeInterval(60))
            if let observation = lateObservation {
                // Production path: the router, not the model, gives the round and hole.
                let assignment = try XCTUnwrap(router.assignment(forMotionAt: observation.observedAt))
                XCTAssertEqual(assignment, .init(roundId: "r1", hole: 1))
                candidates.append(WatchSwingCandidateRecord(
                    capturedAt: "2026-08-09T00:00:01Z", hole: assignment.hole,
                    features: observation.features, horizontalAccuracyM: 5,
                    speedMps: observation.speedMps, proposedShot: observation.proposedShot
                ), roundId: assignment.roundId)
            }
            var uploaded: [String] = []
            var uploadedHoles: [Int] = []
            _ = await WatchSwingCandidateUploader(store: candidates).uploadClosedRounds(
                activeRoundId: router.activeRoundId
            ) { roundId, records in
                uploaded.append(roundId)
                uploadedHoles += records.map(\.hole)
            }
            if collecting {
                XCTAssertEqual(uploadedHoles, [1], "the late candidate uploads with the closed round's hole")
            }
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let deferred = try XCTUnwrap(store.loadDeferredFinishes().first)
            return (try encoder.encode(model.round), try encoder.encode(deferred.round), uploaded)
        }

        let without = try await scriptedRound(collecting: false)
        let with = try await scriptedRound(collecting: true)
        XCTAssertEqual(with.round, without.round)
        XCTAssertEqual(with.deferred, without.deferred, "the archived events and score are unchanged")
        XCTAssertEqual(without.uploaded, [])
        XCTAssertEqual(with.uploaded, ["r1"], "the phone-closed round hands its candidates to the uploader")
    }

    func testPhoneFinishArchivesPendingEventsFromTheVisibleWatchRound() throws {
        let store = makeStore()
        let model = WatchRoundModel(
            store: store,
            makeEventId: sequentialIds(),
            now: { "2026-08-09T00:00:00Z" }
        )
        model.seedRound([hole(1)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        let pending = try XCTUnwrap(model.round?.pendingEvents)
        XCTAssertFalse(pending.isEmpty)

        model.applyPhoneRoundClosure(WatchRoundClosure(
            roundId: "r1",
            disposition: .finished,
            closedAt: "2026-08-09T01:00:00Z"
        ))

        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)
        let deferred = try XCTUnwrap(store.loadDeferredFinishes().first)
        XCTAssertEqual(deferred.round.roundId, "r1")
        XCTAssertEqual(deferred.round.pendingEvents, pending)
        XCTAssertEqual(store.closure(roundId: "r1")?.disposition, .savedLocally)
        XCTAssertNil(model.lastRoundClosure, "phone closures must not echo back to the phone")
    }

    func testPhoneStateCannotCreateALegacyOneHoleRound() {
        let model = WatchRoundModel(store: makeStore())

        model.receivePhoneState(hole(1))

        XCTAssertNil(model.round)
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
        XCTAssertEqual(model.activeHole, 1)
        let updatedHole = model.round?.holeStates.first { $0.hole == 2 }
        XCTAssertEqual(updatedHole?.distanceM, 137)
        XCTAssertEqual(updatedHole?.suggestedClub, "8I")
        XCTAssertEqual(updatedHole?.selectedClub, "8I")
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
            selectedClub: nil,
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
        XCTAssertEqual(model.screen, .home)
        XCTAssertNotNil(model.undoableShotText)
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

    // MARK: caddie plan lifecycle (Codex review on #367)

    private func liveDecisionState(
        _ decisionId: String,
        _ plan: [WatchCaddiePlanStep],
        originShotEventIds: [String]?,
        phoneShots: [String]? = nil,
        revision: Int64? = nil,
        roundId: String = "r1",
        globalId: Int? = nil,
        shotType: String? = nil
    ) -> WatchRoundState {
        WatchRoundState(
            roundId: roundId, hole: 1, par: 4, distanceM: 400,
            selectedClub: nil,
            shotType: shotType,
            decisionId: decisionId,
            globalId: globalId,
            sourceLocalHole: globalId == nil ? nil : 1,
            courseHoleNumber: globalId == nil ? nil : 1,
            caddieOptions: [
                WatchCaddieOption(
                    optionId: "stock", label: "一号木", clubName: plan.first?.clubName,
                    carryM: plan.first?.carryM, carryP10M: 205, carryP90M: 235, sampleSize: 20,
                    plan: plan, confidence: "high", routeOffsetBasis: .shot,
                    originShotEventIds: originShotEventIds
                ),
            ],
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high",
            phoneShotEventIds: phoneShots, snapshotRevision: revision
        )
    }

    private func recordShot(_ model: WatchRoundModel, club: String) {
        model.beginManualShot(
            latitude: 40.0454995, longitude: 116.5461531, horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T08:00:00Z"
        )
        model.completePendingManualShot(clubName: club)
    }

    private func lastLocationEventId(_ model: WatchRoundModel) -> String? {
        model.round?.pendingEvents.last { $0.kind == .location }?.eventId
    }

    func testALiveDecisionArrivingAfterTheWatchShotIsNotReplayed() throws {
        let model = seededModel(holes: [hole(1), hole(2)])
        let plan = [
            WatchCaddiePlanStep(clubName: "1W", carryM: 220, routeOffsetM: 220),
            WatchCaddiePlanStep(clubName: "8I", carryM: 140, routeOffsetM: 360),
        ]
        // The phone requested d1 before any shot; the Watch records the tee shot before d1 first
        // reaches it.
        recordShot(model, club: "一号木")
        let teeShot = try XCTUnwrap(lastLocationEventId(model))
        model.receivePhoneState(liveDecisionState("d1", plan, originShotEventIds: []))
        XCTAssertEqual(model.activeHoleState?.caddieOptions.first?.originShotEventIds, [], "the producer's origin, not arrival")
        var current = try XCTUnwrap(model.currentCaddieOptions(progressM: 215).first)
        XCTAssertEqual(current.plan?.map(\.clubName), ["8I"], "the Driver leg is not replayed")
        XCTAssertEqual(current.clubName, "8I")
        XCTAssertNil(current.plan?.first?.routeOffsetM, "placed by its carry from the player")
        XCTAssertNil(current.carryP10M, "the Driver's dispersion no longer describes the next shot")

        // The same decision re-sent in a later snapshot: still the remaining plan.
        model.receivePhoneState(liveDecisionState("d1", plan, originShotEventIds: []))
        current = try XCTUnwrap(model.currentCaddieOptions(progressM: 215).first)
        XCTAssertEqual(current.plan?.map(\.clubName), ["8I"])

        // A decision the phone made after that Watch shot (it names it) is drawn as made.
        model.receivePhoneState(liveDecisionState(
            "d2", [WatchCaddiePlanStep(clubName: "9I", carryM: 130, routeOffsetM: 130)], originShotEventIds: [teeShot]
        ))
        current = try XCTUnwrap(model.currentCaddieOptions(progressM: 215).first)
        XCTAssertEqual(current.plan?.map(\.clubName), ["9I"])
        XCTAssertEqual(current.plan?.first?.routeOffsetM, 130)
    }

    func testAPhoneShotThenAWatchShotDoesNotReplayTheSecondShotsPlan() throws {
        // Shot 1 is recorded on the iPhone (the Watch never sees it). The phone's decision for shot
        // 2 names that phone shot as its origin. Shot 2 is then recorded on the Watch.
        let store = makeStore()
        let model = WatchRoundModel(store: store, makeEventId: sequentialIds(), now: { "2026-06-20T00:00:00Z" })
        model.seedRound([hole(1), hole(2)], activeHole: 1)
        let plan = [
            WatchCaddiePlanStep(clubName: "5I", carryM: 160, routeOffsetM: 160),
            WatchCaddiePlanStep(clubName: "PW", carryM: 100, routeOffsetM: 260),
        ]
        model.receivePhoneState(liveDecisionState("d2", plan, originShotEventIds: ["phone-shot-1"]))
        XCTAssertEqual(model.currentCaddieOptions(progressM: 220).first?.plan?.map(\.clubName), ["5I", "PW"],
                       "the Watch has not played since the plan was made")

        recordShot(model, club: "五号铁")
        XCTAssertEqual(model.currentCaddieOptions(progressM: 380).first?.plan?.map(\.clubName), ["PW"],
                       "the Watch shot is played after the plan: 5I is not replayed")

        // The same after a relaunch from disk.
        let restored = WatchRoundModel(store: store)
        XCTAssertEqual(restored.currentCaddieOptions(progressM: 380).first?.plan?.map(\.clubName), ["PW"])
    }

    private let teePlan = [
        WatchCaddiePlanStep(clubName: "1W", carryM: 220, routeOffsetM: 220, expectedRemainingM: 180),
        WatchCaddiePlanStep(clubName: "8I", carryM: 140, routeOffsetM: 360, expectedRemainingM: 40),
    ]

    func testAShotRecordedOnlyOnThePhoneRetiresTheOlderDecision() throws {
        let store = makeStore()
        let model = WatchRoundModel(store: store, makeEventId: sequentialIds(), now: { "2026-06-20T00:00:00Z" })
        model.seedRound([hole(1), hole(2)], activeHole: 1)
        model.receivePhoneState(liveDecisionState("d0", teePlan, originShotEventIds: [], phoneShots: [], revision: 100))
        XCTAssertEqual(model.currentCaddieOptions(progressM: 0).first?.plan?.first?.clubName, "1W")

        // The tee shot is recorded on the iPhone only; its next snapshot still carries d0 (the new
        // decision has not come back) but names the phone's current shots.
        model.receivePhoneState(liveDecisionState("d0", teePlan, originShotEventIds: [], phoneShots: ["p1"], revision: 101))
        XCTAssertEqual(model.currentCaddieOptions(progressM: 215).first?.plan?.map(\.clubName), ["8I"], "no Driver replay")

        // Relaunch from disk: still retired.
        let restored = WatchRoundModel(store: store)
        XCTAssertEqual(restored.currentCaddieOptions(progressM: 215).first?.plan?.map(\.clubName), ["8I"])
    }

    func testAnOlderSnapshotArrivingLastNeverRollsBackTheNewerDecision() throws {
        let store = makeStore()
        let model = WatchRoundModel(store: store, makeEventId: sequentialIds(), now: { "2026-06-20T00:00:00Z" })
        model.seedRound([hole(1), hole(2)], activeHole: 1)
        let d1 = [WatchCaddiePlanStep(clubName: "7I", carryM: 150, routeOffsetM: 150, expectedRemainingM: 30)]
        // d1 (made after the phone shot p1) arrives first; the older d0 snapshot, queued earlier
        // through transferUserInfo, arrives last.
        model.receivePhoneState(liveDecisionState("d1", d1, originShotEventIds: ["p1"], phoneShots: ["p1"], revision: 201))
        model.receivePhoneState(liveDecisionState("d0", teePlan, originShotEventIds: [], phoneShots: [], revision: 200))
        func assertD1(_ model: WatchRoundModel, _ message: String) {
            XCTAssertEqual(model.activeHoleState?.decisionId, "d1", message)
            let current = model.currentCaddieOptions(progressM: 220).first
            XCTAssertEqual(current?.clubName, "7I", message)
            XCTAssertEqual(current?.plan?.map(\.routeOffsetM), [150], message)
        }
        assertD1(model, "the newer decision, club and route stay")
        // A duplicate of the applied revision is ignored too.
        model.receivePhoneState(liveDecisionState("d0", teePlan, originShotEventIds: [], phoneShots: [], revision: 201))
        assertD1(model, "a same-revision snapshot does not replace it")
        assertD1(WatchRoundModel(store: store), "after a relaunch")
    }

    func testASameRoundSeedKeepsThePhoneShotsSoAPlayedPlanStaysRetired() throws {
        let store = makeStore()
        let model = WatchRoundModel(store: store, makeEventId: sequentialIds(), now: { "2026-06-20T00:00:00Z" })
        let seed = WatchRoundSeed(
            roundId: "seed-round",
            courseName: "北京丽宫",
            activeHole: 1,
            holes: courseSeedHoles("31795:all", [
                WatchRoundSeedHole(hole: 1, par: 4, distanceM: 365, globalId: 31795, localHole: 1, courseHoleNumber: 1),
            ]),
            globalId: 31795,
            loopKey: "31795:all"
        )
        model.applyRoundSeed(seed)
        XCTAssertNotNil(model.round)
        model.receivePhoneState(liveDecisionState(
            "d0", teePlan, originShotEventIds: [], phoneShots: ["p1"], revision: 300,
            roundId: "seed-round", globalId: 31795
        ))
        XCTAssertEqual(model.currentCaddieOptions(progressM: 215).first?.plan?.map(\.clubName), ["8I"])

        // The phone re-sends the same round's seed (activation, an added half, a refresh).
        model.applyRoundSeed(seed)
        XCTAssertEqual(model.round?.phoneShots?.first?.eventIds, ["p1"], "round-owned, kept")
        XCTAssertEqual(model.currentCaddieOptions(progressM: 215).first?.plan?.map(\.clubName), ["8I"], "no Driver revival")
        XCTAssertEqual(
            WatchRoundModel(store: store).currentCaddieOptions(progressM: 215).first?.plan?.map(\.clubName), ["8I"],
            "after a relaunch"
        )
    }

    func testAPhoneShotCountsForTheWatchShotNumberTypeScoreAndTeeOrigin() throws {
        let store = makeStore()
        let model = WatchRoundModel(store: store, makeEventId: sequentialIds(), now: { "2026-06-20T00:00:00Z" })
        model.seedRound([hole(1, par: 4), hole(2)], activeHole: 1)
        // The tee shot p1 was recorded on the iPhone; the Watch's own queue is empty. The phone's
        // snapshot still carries the older tee decision (shotType "tee") while it fetches the next.
        model.receivePhoneState(liveDecisionState(
            "d0", teePlan, originShotEventIds: [], phoneShots: ["p1"], revision: 400, shotType: "tee"
        ))
        XCTAssertEqual(model.round?.pendingEvents.count, 0)
        XCTAssertEqual(model.recordedShotCount, 1, "the phone's shot is a hole fact on the Watch")

        // The next Watch shot is the second shot and not a tee shot (the tee origin is off: the
        // 方案 page measures from the tee only while recordedShotCount == 0).
        model.beginManualShot(
            latitude: 40.0454995, longitude: 116.5461531, horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T08:00:00Z"
        )
        XCTAssertEqual(model.pendingManualShot?.shotNumber, 2)
        XCTAssertNotEqual(model.pendingManualShot?.shotType, "tee")
        model.completePendingManualShot(clubName: "七号铁")
        XCTAssertEqual(model.recordedShotCount, 2)
        XCTAssertNotEqual(model.round?.pendingEvents.first { $0.kind == .club }?.shotType, "tee")

        // The score recommendation includes the phone's shot (2 shots + 2 putts).
        model.startScoringActiveHole()
        XCTAssertEqual(model.draftScore, 4)

        let restored = WatchRoundModel(store: store)
        XCTAssertEqual(restored.recordedShotCount, 2, "after a relaunch")
        XCTAssertEqual(
            restored.round?.pendingEvents.filter { $0.kind == .club }.map(\.shotType), ["approach"],
            "the persisted shot is not written as a tee shot"
        )
        // A legitimate later phase from the decision is kept.
        XCTAssertEqual(WatchRoundModel.shotType(shotNumber: 2, decisionShotType: "recovery"), "recovery")
        XCTAssertEqual(WatchRoundModel.shotType(shotNumber: 1, decisionShotType: "approach"), "tee")
    }

    func testTheClubTagNoteDescribesTheNextShotOfTheCurrentSelectedPlan() {
        let stock = WatchCaddieOption(
            optionId: "stock", label: "标准",
            plan: [
                WatchCaddiePlanStep(clubName: "1W", carryM: 220, routeOffsetM: 220, expectedRemainingM: 140),
                WatchCaddiePlanStep(clubName: "8I", carryM: 128, routeOffsetM: 348, expectedRemainingM: 12),
            ],
            routeOffsetBasis: .tee, originShotEventIds: []
        )
        let safe = WatchCaddieOption(
            optionId: "safe", label: "稳妥",
            plan: [
                WatchCaddiePlanStep(clubName: "3W", carryM: 190, routeOffsetM: 190, expectedRemainingM: 170),
                WatchCaddiePlanStep(clubName: "7I", carryM: 130, routeOffsetM: 320, expectedRemainingM: 40),
                WatchCaddiePlanStep(clubName: "SW", carryM: 40, routeOffsetM: 360, expectedRemainingM: 0),
            ],
            routeOffsetBasis: .tee, originShotEventIds: []
        )
        func note(_ metres: Double) -> String { "留\(WatchUnits.yards(metres))码" }
        // Before the tee shot: the Driver's own leave, not the plan's last.
        XCTAssertEqual(WatchRoundContainerView.planNote(stock, stateRemainingM: 0), note(140))
        // Switching plan switches the note to that plan's next shot.
        XCTAssertEqual(WatchRoundContainerView.planNote(safe, stateRemainingM: 0), note(170))
        // After the tee shot: single-step and multi-step remaining plans.
        let stockAfter = stock.remaining(fromProgressM: 220, watchShotEventIds: ["evt-2"])
        XCTAssertEqual(stockAfter.clubName, "8I")
        XCTAssertEqual(WatchRoundContainerView.planNote(stockAfter, stateRemainingM: 0), note(12))
        let safeAfter = safe.remaining(fromProgressM: 190, watchShotEventIds: ["evt-2"])
        XCTAssertEqual(safeAfter.plan?.map(\.clubName), ["7I", "SW"])
        XCTAssertEqual(WatchRoundContainerView.planNote(safeAfter, stateRemainingM: 0), note(40))
        // Only a hole without plans uses the decision's own remaining.
        XCTAssertEqual(WatchRoundContainerView.planNote(nil, stateRemainingM: 0), "攻果岭")
    }

    func testARestoredLegacyLivePlanWithoutAnOriginFailsClosedAfterAShot() throws {
        let store = makeStore()
        let plan = [
            WatchCaddiePlanStep(clubName: "1W", carryM: 220, routeOffsetM: 220),
            WatchCaddiePlanStep(clubName: "8I", carryM: 140, routeOffsetM: 360),
        ]
        let first = WatchRoundModel(store: store, makeEventId: sequentialIds(), now: { "2026-06-20T00:00:00Z" })
        first.seedRound([liveDecisionState("d1", plan, originShotEventIds: nil), hole(2)], activeHole: 1)
        XCTAssertEqual(first.currentCaddieOptions(progressM: 0).first?.plan?.first?.clubName, "1W",
                       "before any shot an unstamped plan is still the tee plan")
        XCTAssertTrue(first.caddieDetailAvailable)
        recordShot(first, club: "一号木")

        // Relaunch from disk: the legacy live plan does not say which shots it was made after.
        let restored = WatchRoundModel(store: store)
        XCTAssertEqual(restored.recordedShotCount, 1)
        XCTAssertTrue(restored.currentCaddieOptions(progressM: 215).isEmpty, "no replayed Driver leg")
        XCTAssertFalse(restored.caddieDetailAvailable, "the menu cannot open the stale decision either")
        // Its same-id resend without an origin stays closed too.
        restored.receivePhoneState(liveDecisionState("d1", plan, originShotEventIds: nil))
        XCTAssertTrue(restored.currentCaddieOptions(progressM: 215).isEmpty)
        XCTAssertFalse(restored.caddieDetailAvailable)
    }

    func testAPreparedPlanAdvancesForEveryConsumerAfterTheTeeShot() throws {
        let options = WatchCourseTemplateBuilder.preparedCaddieOptions(
            clubs: [
                WatchClubOption(clubName: "1W", medianM: 220, source: "course-prep"),
                WatchClubOption(clubName: "3W", medianM: 190, source: "course-prep"),
                WatchClubOption(clubName: "5I", medianM: 160, source: "course-prep"),
                WatchClubOption(clubName: "8I", medianM: 125, source: "course-prep"),
            ],
            suggestedClub: "1W",
            routeDistanceM: 518.8,
            landingM: nil
        )
        let state = WatchRoundState(
            roundId: "r1", hole: 1, par: 5, distanceM: 518.8,
            selectedClub: nil,
            caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let model = seededModel(holes: [state, hole(2)])
        let atTee = try XCTUnwrap(model.currentCaddieOptions(progressM: 0).first { $0.optionId == "stock" })
        XCTAssertEqual(atTee.clubName, "1W")
        XCTAssertEqual(WatchCaddieOptionsView.clubChain(atTee, compact: true), "D›3W›8i")

        recordShot(model, club: "一号木")
        let current = model.currentCaddieOptions(progressM: 220)
        let stock = try XCTUnwrap(current.first { $0.optionId == "stock" })
        // The club tag, the 球童 detail's chain and the legs all start from the next shot.
        XCTAssertEqual(stock.clubName, "3W")
        XCTAssertEqual(stock.label, "标准", "a prepared plan keeps its tier name")
        XCTAssertEqual(WatchCaddieOptionsView.clubChain(stock, compact: true), "3W›8i")
        XCTAssertEqual(
            stock.plan?.compactMap(\.routeOffsetM).map { ($0 * 10).rounded() / 10 }, [190, 298.8],
            "original 410 / 518.8 m stations, from the player at 220 m"
        )
        let screen = WatchCaddieScreen(state: try XCTUnwrap(model.activeHoleState), options: current)
        XCTAssertEqual(screen.options.first { $0.optionId == "stock" }?.clubName, "3W")
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

    // MARK: live distance from the last shot (owner feedback 2026-10-10; Codex on #414)

    private func phoneSnapshot(
        hole: Int,
        lastShot: (latitude: Double, longitude: Double, at: String)?,
        shotIds: [String],
        revision: Int64
    ) -> WatchRoundState {
        WatchRoundState(
            roundId: "r1", hole: hole, par: 4, distanceM: nil, selectedClub: nil,
            lastShotLatitude: lastShot?.latitude, lastShotLongitude: lastShot?.longitude,
            lastShotCapturedAt: lastShot?.at,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline",
            phoneShotEventIds: shotIds, snapshotRevision: revision
        )
    }

    private func markWatchShot(_ model: WatchRoundModel, latitude: Double, at: String) {
        model.beginManualShot(latitude: latitude, longitude: 116.0, horizontalAccuracyM: 5, capturedAt: at)
        model.completePendingManualShot(clubName: nil)
    }

    private func liveShotModel(store: WatchRoundStore) -> WatchRoundModel {
        WatchRoundModel(store: store, makeEventId: sequentialIds(), now: { "2026-07-26T08:00:00Z" })
    }

    /// A Watch mark made while disconnected is older than the phone's newest shot, whose snapshot
    /// arrives before the mark is relayed: the phone shot is the origin, and still is after relaunch.
    func testAnOlderUndeliveredWatchMarkDoesNotBeatTheNewerPhoneShot() throws {
        let store = makeStore()
        let model = liveShotModel(store: store)
        model.seedRound([hole(1), hole(2)], activeHole: 1, courseName: "练习", loopKey: nil)
        markWatchShot(model, latitude: 40.0, at: "2026-07-26T10:00:00Z")
        model.receivePhoneState(phoneSnapshot(
            hole: 1, lastShot: (40.001, 116.0, "2026-07-26T10:05:00Z"), shotIds: ["phone-second"], revision: 1
        ))
        let expected = WatchGeoMath.metres(40.001, 116.0, 40.002, 116.0)

        let live = try XCTUnwrap(model.distanceFromLatestShotM(latitude: 40.002, longitude: 116.0))
        XCTAssertEqual(live, expected, accuracy: 0.01)

        let relaunched = liveShotModel(store: store)
        let resumed = try XCTUnwrap(relaunched.distanceFromLatestShotM(latitude: 40.002, longitude: 116.0))
        XCTAssertEqual(resumed, expected, accuracy: 0.01, "same origin after relaunch")
    }

    func testANewerWatchMarkBeatsThePhonesLastShot() throws {
        let model = liveShotModel(store: makeStore())
        model.seedRound([hole(1), hole(2)], activeHole: 1, courseName: "练习", loopKey: nil)
        model.receivePhoneState(phoneSnapshot(
            hole: 1, lastShot: (40.0, 116.0, "2026-07-26T10:00:00Z"), shotIds: ["phone-tee"], revision: 1
        ))
        markWatchShot(model, latitude: 40.001, at: "2026-07-26T10:05:00.500Z")

        let live = try XCTUnwrap(model.distanceFromLatestShotM(latitude: 40.002, longitude: 116.0))
        XCTAssertEqual(live, WatchGeoMath.metres(40.001, 116.0, 40.002, 116.0), accuracy: 0.01)
    }

    func testAnotherHolesShotsNeverBecomeTheOrigin() {
        let model = liveShotModel(store: makeStore())
        model.seedRound([hole(1), hole(2)], activeHole: 1, courseName: "练习", loopKey: nil)
        model.receivePhoneState(phoneSnapshot(
            hole: 2, lastShot: (41.0, 116.0, "2026-07-26T11:00:00Z"), shotIds: ["phone-h2"], revision: 1
        ))

        XCTAssertNil(model.distanceFromLatestShotM(latitude: 40.002, longitude: 116.0),
                     "hole 1 has no shot; hole 2's never leaks in")
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
            watchGreenYards: (front: 199, center: 211, back: 223),
            shotLocation: WatchLocationFix(
                coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
                horizontalAccuracyM: 5,
                capturedAt: ISO8601DateFormatter().string(from: Date())
            )
        )

        XCTAssertEqual(view.distanceText, "211 码")
    }

    func testRoundHomeDistanceUses999OnlyWithoutLocationOrLiveRange() {
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
        let view = WatchRoundContainerView(model: model)

        XCTAssertEqual(view.distanceText, "999 码 · 等待定位")
    }

    func testAutoShotIsOptInAndAnUndoneShotWritesNoEvent() {
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
        // README §3: no per-shot confirmation page — the shot waits in the bottom undo strip.
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.pendingAutoShotCandidate)
        XCTAssertEqual(model.undoableShotText, "第 1 杆")
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true)

        model.undoPendingManualShot()

        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.undoableShotText)
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

        XCTAssertNil(model.pendingAutoShotCandidate)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNotNil(model.undoableShotText)
        XCTAssertEqual(model.pendingManualShot?.hole, 1)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true)

        model.completePendingManualShot(clubName: "一号木")

        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.club, .location])
        XCTAssertEqual(model.recordedShotCount, 1)
    }

    func testADetectedShotSurvivesARelaunchAsTheSameUndoableShot() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("autoshot-map-restore-\(UUID().uuidString)", isDirectory: true)
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
        XCTAssertEqual(first.screen, .holeMap, "no confirmation page over the map")

        let restored = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            autoShotEnabled: true,
            persistAutoShotEnabled: { _ in }
        )

        XCTAssertNil(restored.pendingAutoShotCandidate)
        XCTAssertEqual(restored.pendingManualShot?.hole, 1)
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

        XCTAssertEqual(model.screen, .holeMap, "B6: no club prompt; the shot waits in its undo window")
        XCTAssertEqual(model.undoableShotText, "第 1 杆")
        model.completePendingManualShot(clubName: nil)

        XCTAssertEqual(model.screen, .holeMap)
        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.location])
    }

    func testAutoShotRestoresWithoutBecomingARecordedShotOrAPage() {
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

        XCTAssertEqual(restored.screen, .resume)
        XCTAssertNil(restored.pendingAutoShotCandidate)
        XCTAssertTrue(restored.round?.pendingEvents.isEmpty == true)

        restored.resumeRound()
        XCTAssertNotEqual(restored.screen, .autoShotCandidate)
        XCTAssertEqual(restored.undoableShotText, "第 1 杆")
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

    // MARK: B6 洞结束

    func testWalkingOffTheGreenTowardTheNextTeeOpensScoringOnce() {
        // Hole 1's green at (40.0, 116.0); hole 2's tee ~120 m east of it.
        let east120 = 116.0 + 120 / (111_195.0 * cos(40.0 * .pi / 180))
        let east45 = 116.0 + 45 / (111_195.0 * cos(40.0 * .pi / 180))
        let first = WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: nil,
            teeLatitude: 39.997, teeLongitude: 116.0, selectedClub: nil,
            centerGreenLat: 40.0, centerGreenLon: 116.0,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let model = seededModel(holes: [first, hole(2, teeLatitude: 40.0, teeLongitude: east120)])
        XCTAssertFalse(model.observeLocation(latitude: 39.9995, longitude: 116.0, horizontalAccuracyM: 5),
                       "approaching the green")
        XCTAssertFalse(model.observeLocation(latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 4), "on the green")
        XCTAssertEqual(model.screen, .home)
        XCTAssertTrue(model.observeLocation(latitude: 40.0, longitude: east45, horizontalAccuracyM: 5))
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertFalse(model.observeLocation(latitude: 40.0, longitude: east120, horizontalAccuracyM: 5),
                       "the hole ends once")
    }

    func testAHoleEndReportedWhileTheMenuIsOpenIsNotLost() {
        let east120 = 116.0 + 120 / (111_195.0 * cos(40.0 * .pi / 180))
        let east45 = 116.0 + 45 / (111_195.0 * cos(40.0 * .pi / 180))
        let east60 = 116.0 + 60 / (111_195.0 * cos(40.0 * .pi / 180))
        let first = WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: nil,
            teeLatitude: 39.997, teeLongitude: 116.0, selectedClub: nil,
            centerGreenLat: 40.0, centerGreenLon: 116.0,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let model = seededModel(holes: [first, hole(2, teeLatitude: 40.0, teeLongitude: east120)])
        XCTAssertFalse(model.observeLocation(latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 4), "on the green")
        model.openMenu()
        // The detector fires exactly once, while the menu is up: nothing opens over the menu…
        XCTAssertFalse(model.observeLocation(latitude: 40.0, longitude: east45, horizontalAccuracyM: 5))
        XCTAssertEqual(model.screen, .menu)
        XCTAssertEqual(model.pendingHoleEnd, 1)
        // …and the next fix after the menu closes opens 本洞成绩 instead of losing the trigger.
        model.backToHome()
        XCTAssertTrue(model.observeLocation(latitude: 40.0, longitude: east60, horizontalAccuracyM: 5))
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertNil(model.pendingHoleEnd)
        XCTAssertFalse(model.observeLocation(latitude: 40.0, longitude: east120, horizontalAccuracyM: 5), "still once")
    }

    func testAHoleWithoutGreenCoordinatesHasNoGPSHoleEnd() {
        let model = seededModel(holes: [hole(1), hole(2)])
        XCTAssertFalse(model.observeLocation(latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 4))
        XCTAssertEqual(model.screen, .home, "no green coordinates: no GPS hole end")
    }

    func testPendingManualShotRestoresItsUndoWindowAfterRelaunch() {
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

        XCTAssertEqual(restored.screen, .resume)
        XCTAssertEqual(restored.pendingManualShot?.hole, 1)
        XCTAssertEqual(restored.pendingManualShot?.shotNumber, 1)
        XCTAssertEqual(restored.pendingUploads, 0)
        XCTAssertFalse(restored.canSaveAndEndFromResume)
        restored.requestSaveAndEndFromResume()
        XCTAssertEqual(restored.screen, .resume)

        restored.resumeRound()
        XCTAssertEqual(restored.screen, .home)
        XCTAssertNotNil(restored.undoableShotText)
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

        XCTAssertEqual(restored.screen, .resume)
        XCTAssertFalse(restored.canSaveAndEndFromResume)
        restored.resumeRound()
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
        XCTAssertEqual(restored.screen, .home)
        XCTAssertNotNil(restored.undoableShotText)

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
        XCTAssertEqual(model.screen, .home)
        XCTAssertNotNil(model.undoableShotText)
        XCTAssertEqual(model.pendingManualShot?.hole, 2)
        XCTAssertNil(model.pendingManualShot?.candidateFromHole)

        model.completePendingManualShot(clubName: "一号木")

        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.score, .putt, .club, .location])
        XCTAssertEqual(model.round?.pendingEvents.suffix(2).map(\.hole), [2, 2])
        XCTAssertEqual(model.recordedShotCount, 1)
    }

    func testNextTeeProvisionalShotIsAcceptedAndCompletedOnlyOnce() {
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

        // The GPS fact is provisional: it must not end hole 1 or enter the event queue yet.
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertEqual(model.pendingManualShot?.hole, 2)
        XCTAssertEqual(model.pendingManualShot?.candidateFromHole, 1)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true)

        // A double tap on the recommended score is still one score decision.
        model.acceptRecommendedScore()
        model.acceptRecommendedScore()
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.pendingManualShot?.hole, 2)
        XCTAssertNil(model.pendingManualShot?.candidateFromHole)
        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.score, .putt])

        // Completing the staged shot twice cannot duplicate the same GPS location event.
        model.completePendingManualShot(clubName: "一号木")
        model.completePendingManualShot(clubName: "7I")

        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.score, .putt, .club, .location])
        XCTAssertEqual(model.round?.pendingEvents.filter { $0.kind == .location }.count, 1)
        XCTAssertEqual(model.round?.pendingEvents.last?.hole, 2)
        XCTAssertEqual(model.recordedShotCount, 1)
        XCTAssertNil(model.pendingManualShot)
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
        XCTAssertEqual(model.screen, .home)
        XCTAssertNotNil(model.undoableShotText)
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

        XCTAssertEqual(model.screen, .home)
        XCTAssertNotNil(model.undoableShotText)
        XCTAssertEqual(model.pendingManualShot?.hole, 1)
        XCTAssertNil(model.pendingManualShot?.candidateFromHole)
    }

    // MARK: B6 测到挥杆 (no 刚才用哪支杆？)

    func testADetectedShotCanBeUndoneBeforeItIsRecorded() {
        let model = seededModel(holes: [hole(1), hole(2)])
        model.beginManualShot(latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 5,
                              capturedAt: "2026-07-26T09:00:00Z")
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.undoableShotText, "第 1 杆")
        model.undoPendingManualShot()
        XCTAssertNil(model.pendingManualShot)
        XCTAssertNil(model.undoableShotText)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty == true, "an undone shot writes nothing")
        XCTAssertEqual(model.recordedShotCount, 0)
    }

    func testTheNextShotEndsThePreviousShotsUndoWindow() {
        let model = seededModel(holes: [hole(1), hole(2)])
        model.beginManualShot(latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 5,
                              capturedAt: "2026-07-26T09:00:00Z")
        model.beginManualShot(latitude: 40.0015, longitude: 116.0, horizontalAccuracyM: 5,
                              capturedAt: "2026-07-26T09:03:00Z")
        XCTAssertEqual(model.round?.pendingEvents.map(\.kind), [.location], "the first shot is recorded")
        XCTAssertEqual(model.undoableShotText, "第 2 杆")
    }

    func testTheNextTeeShotSavesAnOpenScoreDraft() {
        let model = seededModel(holes: [
            hole(1, par: 4, teeLatitude: 40.0, teeLongitude: 116.0),
            hole(2, par: 5, teeLatitude: 40.001, teeLongitude: 116.0),
        ])
        model.startScoringActiveHole()  // as the hole-end trigger does
        model.draftScore = 6
        model.draftPutts = 2
        model.beginManualShot(latitude: 40.001, longitude: 116.0, horizontalAccuracyM: 5,
                              capturedAt: "2026-07-26T09:30:00Z")
        XCTAssertEqual(model.activeHole, 2, "the unconfirmed hole is saved and play moves on")
        XCTAssertEqual(model.allHoleStates.first?.score, 6)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.pendingManualShot?.hole, 2)
        XCTAssertNil(model.pendingManualShot?.candidateFromHole)
        XCTAssertEqual(model.undoableShotText, "第 1 杆")
    }

    func testOneScreenScoreRaisesTheTotalAndWrapsTheWheels() {
        let model = seededModel(holes: [hole(1, par: 4), hole(2)])
        model.startScoringActiveHole()
        model.setDraftScore(3)
        model.setDraftPutts(3)
        XCTAssertEqual(model.draftScore, 4, "total ≥ putts + penalties + 1")
        model.setDraftPenalty(-1)
        XCTAssertEqual(model.draftPenalty, 4, "0 sits under 4")
        XCTAssertEqual(model.draftScore, 8)
        model.setDraftPutts(6)
        XCTAssertEqual(model.draftPutts, 0, "5 rolls over to 0")
        XCTAssertEqual(model.draftScore, 8, "lowering putts never lowers the total")
        model.setDraftFairway(.left)
        model.setDraftFairway(.left)
        XCTAssertNil(model.draftFairway, "tapping the chosen cell clears it")
        model.saveManualScore()
        XCTAssertEqual(model.allHoleStates.first?.score, 8)
        XCTAssertEqual(model.activeHole, 2)
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

    func testMapDetailAndGreenPreviewHaveExplicitShallowNavigationStates() {
        let model = seededModel(holes: [hole(1)])

        model.openHoleMap()
        XCTAssertEqual(model.screen, .holeMap)
        model.backToHome()
        XCTAssertEqual(model.screen, .home)

        model.openViewGreen()
        XCTAssertEqual(model.screen, .viewGreen)
        model.backToMenu()
        XCTAssertEqual(model.screen, .menu)
    }

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
        XCTAssertFalse(model.playerAtActiveTee(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.04585, longitude: 116.5462),
            horizontalAccuracyM: 6,
            capturedAt: "2026-06-20T00:00:00Z"
        )))
        XCTAssertFalse(model.preparedRootCaddieLayerAvailable(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0461, longitude: 116.5462),
            horizontalAccuracyM: 6,
            capturedAt: "2026-06-20T00:00:00Z"
        )))

        let partial = state.applyingCourseMapUpgrade(WatchRoundState(
            roundId: "r1", hole: 1, par: 4, distanceM: nil,
            teeLatitude: 40.0455, teeLongitude: 116.5462,
            selectedClub: nil,
            geometryCoverage: "partial",
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        ))
        let partialModel = seededModel(holes: [partial])
        XCTAssertTrue(partialModel.playerAtActiveTee(at: WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
            horizontalAccuracyM: 6,
            capturedAt: "2026-06-20T00:00:00Z"
        )))
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

    func testPlaysLikeDistanceKeepsStateInMetresBeforeDisplayConversion() throws {
        let playsLikeMetres = try XCTUnwrap(
            WatchUnits.playsLikeMetres(distanceMetres: 369.4176, elevationDeltaMetres: 5)
        )
        XCTAssertEqual(
            playsLikeMetres,
            374.4176,
            accuracy: 0.0001
        )
        XCTAssertNil(WatchUnits.playsLikeMetres(distanceMetres: nil, elevationDeltaMetres: 5))
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

    func testFinishScorecardEditsReturnToEndRoundWithoutMovingLiveHole() {
        let model = seededModel(holes: [
            hole(1, score: 4, putts: 2),
            hole(2, score: 5, putts: 2),
            hole(3),
        ])
        model.selectHole(3)
        model.requestFinish()

        model.openScorecardFromFinish()
        XCTAssertEqual(model.screen, .scorecard)
        model.startEditingHole(1)
        model.adjustDraftScore(1)
        model.saveManualScore()

        XCTAssertEqual(model.round?.holeStates.first { $0.hole == 1 }?.score, 5)
        XCTAssertEqual(model.activeHole, 3)
        XCTAssertEqual(model.screen, .scorecard)
        model.closeScorecard()
        XCTAssertEqual(model.screen, .finishing)
    }

    func testFinishSummaryRequiresExplicitConfirmationBeforeUpload() {
        let model = seededModel(holes: [hole(1, score: 4)])

        model.requestFinish()
        model.requestFinishConfirmation()
        XCTAssertEqual(model.screen, .finishConfirmation)

        model.cancelFinishConfirmation()
        XCTAssertEqual(model.screen, .finishing)
    }

    func testEmptyRoundFinishRoutesToTwoStepAbandonInsteadOfCreatingADeferredZombie() {
        let model = seededModel(holes: [hole(1)])

        model.requestFinish()
        model.requestFinishConfirmation()

        XCTAssertEqual(model.screen, .abandonConfirmation)
        model.cancelAbandon()
        XCTAssertEqual(model.screen, .finishing)
    }

    func testLocationOnlyRoundCannotSaveAndEndFromResume() throws {
        let store = makeStore()
        let location = WatchInputEvent(
            eventId: "tee-origin-only",
            roundId: "r1",
            hole: 1,
            kind: .location,
            value: "40.0,116.0,5.0",
            createdAt: "2026-08-09T08:00:00Z"
        )
        try store.save(WatchRoundStore.PersistedRound(
            roundId: "r1",
            activeHole: 1,
            holeStates: [hole(1)],
            pendingEvents: [location]
        ))
        let model = WatchRoundModel(store: store)

        XCTAssertEqual(model.screen, .resume)
        XCTAssertTrue(model.hasRecordedProgress)
        XCTAssertFalse(model.canSaveAndEndFromResume)
        model.requestSaveAndEndFromResume()
        XCTAssertEqual(model.screen, .resume)
    }

    func testCancelSaveAndEndFromResumeReturnsToResumeWithDraftIntact() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("resume-finish-cancel-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        first.seedRound([hole(1)])
        first.startScoringActiveHole()
        first.adjustDraftScore(1)

        let restored = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        XCTAssertEqual(restored.screen, .resume)

        restored.requestSaveAndEndFromResume()
        XCTAssertEqual(restored.screen, .finishConfirmation)
        restored.cancelFinishConfirmation()

        XCTAssertEqual(restored.screen, .resume)
        XCTAssertEqual(restored.round?.scoreDraft?.score, 5)
        restored.resumeRound()
        XCTAssertEqual(restored.screen, .scoring)
        XCTAssertEqual(restored.draftScore, 5)
    }

    func testConfirmSaveAndEndMaterializesRestoredDraftBeforeFinishing() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("resume-finish-draft-\(UUID().uuidString)", isDirectory: true)
        let first = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        first.seedRound([hole(1)])
        first.startScoringActiveHole()
        first.adjustDraftScore(1)

        var uploaded: [WatchInputEvent] = []
        var finishMetadata: WatchRoundFinishMetadata?
        let restored = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            makeEventId: sequentialIds(),
            now: { "2026-08-09T08:00:00Z" },
            uploader: { events, _ in
                uploaded = events
                return events.map(\.eventId)
            },
            finisher: { _, metadata in finishMetadata = metadata }
        )

        restored.requestSaveAndEndFromResume()
        XCTAssertEqual(restored.screen, .finishConfirmation)
        await restored.confirmFinish()

        XCTAssertEqual(uploaded.map(\.kind), [.score, .putt])
        XCTAssertEqual(uploaded.first?.value, "5")
        XCTAssertEqual(finishMetadata?.holesCompleted, 1)
        XCTAssertNil(restored.round)
        XCTAssertEqual(restored.lastRoundClosure?.disposition, .finished)
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
        XCTAssertEqual(finishMetadata?.holePars, [4, 5] + Array(repeating: 4, count: 16))
        XCTAssertEqual(finishMetadata?.holesCompleted, 1)
        XCTAssertEqual(finishMetadata?.courseGlobalId, 12345)
        XCTAssertNil(model.round)                       // round cleared after successful upload
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.uploadError)
        XCTAssertFalse(model.isUploading)
    }

    func testConfirmFinishNetworkFailureSavesForLaterAndLeavesRoundUI() async {
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
        XCTAssertNil(model.round)
        XCTAssertEqual(model.lastRoundClosure?.disposition, .savedLocally)
        XCTAssertEqual(model.lastRoundClosure?.roundId, "r1")
        XCTAssertEqual(pendingBefore, 2)
        XCTAssertNil(model.uploadError)
        XCTAssertFalse(model.isUploading)
    }

    func testConfirmFinishWithoutConfigArchivesRoundAndReturnsHome() async {
        let model = seededModel(holes: [hole(1, par: 4)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        let pendingBefore = model.pendingUploads
        model.requestFinish()
        model.requestFinishConfirmation()

        await model.confirmFinish()

        XCTAssertNil(model.round)
        XCTAssertEqual(pendingBefore, 2)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.lastRoundClosure?.disposition, .savedLocally)
        XCTAssertNil(model.uploadError)
    }

    func testConfirmFinishKeepsEventsMissingFromUploaderAcknowledgement() async {
        let store = makeStore()
        let model = WatchRoundModel(
            store: store,
            makeEventId: sequentialIds(),
            now: { "2026-08-09T08:00:00Z" },
            uploader: { events, _ in [events[0].eventId] }
        )
        model.seedRound([hole(1, par: 4)], courseName: "北京丽宫 · 前九")
        model.startScoringActiveHole()
        model.adjustDraftScore(1)
        model.saveActiveHole()
        XCTAssertEqual(model.pendingUploads, 2)
        let missingEventId = model.round?.pendingEvents.last?.eventId
        model.requestFinish()
        model.requestFinishConfirmation()

        await model.confirmFinish()

        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.lastRoundClosure?.disposition, .savedLocally)
        XCTAssertNil(model.uploadError)
        XCTAssertEqual(
            store.loadDeferredFinishes().first?.round.pendingEvents.map(\.eventId),
            missingEventId.map { [$0] }
        )
    }

    func testAbandonWorksOfflineAndTombstoneRejectsTheOldSeed() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("abandon-round-\(UUID().uuidString)", isDirectory: true)
        let store = WatchRoundStore(directoryURL: directory)
        let model = WatchRoundModel(store: store)
        let seed = WatchRoundSeed(
            roundId: "ghost-round",
            courseName: "Old course",
            activeHole: 1,
            holes: courseSeedHoles("31795:all", [WatchRoundSeedHole(hole: 1, par: 4, distanceM: 350, globalId: 31795, localHole: 1, courseHoleNumber: 1)]),
            loopKey: "31795:all"
        )
        model.applyRoundSeed(seed)

        model.requestAbandon()
        model.confirmAbandon()

        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.lastRoundClosure?.disposition, .abandoned)
        XCTAssertTrue(store.isClosed(roundId: "ghost-round"))

        model.applyRoundSeed(seed)
        XCTAssertNil(model.round)
        let relaunched = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        XCTAssertNil(relaunched.round)
    }

    func testDeferredFinishRetriesWithoutRevivingRoundUI() async throws {
        struct Offline: Error {}
        let store = makeStore()
        var online = false
        var finishCalls = 0
        let model = WatchRoundModel(
            store: store,
            makeEventId: sequentialIds(),
            now: { "2026-08-09T00:00:00Z" },
            uploader: { events, _ in
                guard online else { throw Offline() }
                return events.map(\.eventId)
            },
            finisher: { _, _ in
                guard online else { throw Offline() }
                finishCalls += 1
            }
        )
        model.seedRound([hole(1)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.requestFinish()
        model.requestFinishConfirmation()

        await model.confirmFinish()
        XCTAssertNil(model.round)
        XCTAssertEqual(store.loadDeferredFinishes().count, 1)

        online = true
        await model.retryDeferredFinishes()

        XCTAssertNil(model.round)
        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
        XCTAssertEqual(finishCalls, 1)
        XCTAssertEqual(model.lastRoundClosure?.disposition, .finished)
    }

    func testRetryUploadsLegacyLocationOnlyDeferredFinishBeforeRemovingIt() async throws {
        let store = makeStore()
        let location = WatchInputEvent(
            eventId: "legacy-location-only",
            roundId: "r1",
            hole: 1,
            kind: .location,
            value: "40.0,116.0,5.0",
            createdAt: "2026-08-09T08:00:00Z"
        )
        let legacy = WatchRoundStore.PersistedRound(
            roundId: "r1",
            activeHole: 1,
            holeStates: [hole(1)],
            pendingEvents: [location]
        )
        _ = try store.deferFinish(legacy, savedAt: "2026-08-09T08:01:00Z")
        var uploadedEventIds: [String] = []
        var finishCalls = 0
        let model = WatchRoundModel(
            store: store,
            uploader: { events, _ in
                uploadedEventIds = events.map(\.eventId)
                return uploadedEventIds
            },
            finisher: { _, _ in finishCalls += 1 }
        )

        await model.retryDeferredFinishes()

        XCTAssertEqual(uploadedEventIds, [location.eventId])
        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
        XCTAssertEqual(finishCalls, 0)
    }

    func testPhoneFinishUploadsLocationOnlyWatchQueueBeforeCleanup() async throws {
        let store = makeStore()
        var uploadedEventIds: [String] = []
        var finishCalls = 0
        let model = WatchRoundModel(
            store: store,
            makeEventId: sequentialIds(),
            uploader: { events, _ in
                uploadedEventIds = events.map(\.eventId)
                return uploadedEventIds
            },
            finisher: { _, _ in finishCalls += 1 }
        )
        model.seedRound([hole(1)])
        model.beginManualShot(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-08-09T08:00:00Z"
        )
        model.completePendingManualShot(clubName: nil)
        let locationEventId = try XCTUnwrap(
            model.round?.pendingEvents.first { $0.kind == .location }?.eventId
        )

        model.applyPhoneRoundClosure(WatchRoundClosure(
            roundId: "r1",
            disposition: .finished,
            closedAt: "2026-08-09T08:01:00Z"
        ))
        XCTAssertNil(model.round)
        XCTAssertEqual(
            store.loadDeferredFinishes().first?.round.pendingEvents.map(\.eventId),
            [locationEventId]
        )

        await model.retryDeferredFinishes()

        XCTAssertEqual(uploadedEventIds, [locationEventId])
        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
        XCTAssertEqual(finishCalls, 0)
    }

    func testRetryRetainsLegacyLocationOnlyDeferredFinishUntilAcknowledged() async throws {
        let store = makeStore()
        let location = WatchInputEvent(
            eventId: "legacy-location-only",
            roundId: "r1",
            hole: 1,
            kind: .location,
            value: "40.0,116.0,5.0",
            createdAt: "2026-08-09T08:00:00Z"
        )
        let legacy = WatchRoundStore.PersistedRound(
            roundId: "r1",
            activeHole: 1,
            holeStates: [hole(1)],
            pendingEvents: [location]
        )
        _ = try store.deferFinish(legacy, savedAt: "2026-08-09T08:01:00Z")
        let model = WatchRoundModel(
            store: store,
            uploader: { _, _ in [] },
            finisher: { _, _ in XCTFail("location-only archive must not call Finish") }
        )

        await model.retryDeferredFinishes()

        XCTAssertEqual(
            store.loadDeferredFinishes().first?.round.pendingEvents.map(\.eventId),
            [location.eventId]
        )
    }

    func testPhoneFinishPreservesDeferredWatchEventsButPhoneAbandonDiscardsThem() async {
        let store = makeStore()
        let model = WatchRoundModel(store: store)
        model.seedRound([hole(1)])
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()
        XCTAssertEqual(store.loadDeferredFinishes().count, 1)

        model.applyPhoneRoundClosure(WatchRoundClosure(
            roundId: "r1",
            disposition: .finished,
            closedAt: "2026-08-09T01:00:00Z"
        ))
        XCTAssertEqual(store.loadDeferredFinishes().count, 1)

        model.applyPhoneRoundClosure(WatchRoundClosure(
            roundId: "r1",
            disposition: .abandoned,
            closedAt: "2026-08-09T01:01:00Z"
        ))
        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
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
