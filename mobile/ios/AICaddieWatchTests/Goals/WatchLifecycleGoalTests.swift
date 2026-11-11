// size: medium
// goals: W-11, W-12, W-13
import Foundation
import XCTest
import WatchConnectivity
import AICaddieDomain
import AICaddieCore
@testable import AICaddieWatch

@MainActor
final class WatchLifecycleGoalTests: XCTestCase {
    // goals: W-11 [main]
    /// AutoShot is opt-in: it stages the same undoable shot as manual entry, leaves the queue
    /// untouched until the undo window completes, and then records the location event.
    func testAutoShotIsOptInAndUndoableBeforeRecording() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        var persisted: [Bool] = []
        let model = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory), autoShotEnabled: false,
            persistAutoShotEnabled: { persisted.append($0) }, makeEventId: { "event-1" }
        )
        model.startPracticeRound()
        XCTAssertFalse(model.proposeAutoShotCandidate(latitude: 40, longitude: 116, horizontalAccuracyM: 5, capturedAt: "2026-06-20T00:00:00Z"))
        XCTAssertTrue(model.round?.pendingEvents.isEmpty ?? false)
        model.setAutoShotEnabled(true)
        XCTAssertEqual(persisted, [true])
        XCTAssertTrue(model.proposeAutoShotCandidate(latitude: 40, longitude: 116, horizontalAccuracyM: 5, capturedAt: "2026-06-20T00:00:00Z"))
        XCTAssertNil(model.pendingAutoShotCandidate)
        XCTAssertNotNil(model.pendingManualShot)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty ?? false)
        model.undoPendingManualShot()
        XCTAssertNil(model.pendingManualShot)
        XCTAssertTrue(model.round?.pendingEvents.isEmpty ?? false)

        XCTAssertTrue(model.proposeAutoShotCandidate(latitude: 40, longitude: 116, horizontalAccuracyM: 5, capturedAt: "2026-06-20T00:00:01Z"))
        model.completePendingManualShot(clubName: nil)
        XCTAssertEqual(model.round?.pendingEvents.filter { $0.kind == .location }.count, 1)
    }

    // goals: W-12 [main]
    /// Location preheat is allowed before a round, active play keeps it alive, and deterministic UI
    /// launches avoid location/workout side effects.
    func testLocationLaunchPolicyCoversPreheatRoundAndScreenshotModes() {
        XCTAssertTrue(WatchLocationLaunchPolicy.shouldStartLocationServices(hasActiveRound: false, gpsPreheatEnabled: true, arguments: ["AI Caddie"]))
        XCTAssertTrue(WatchLocationLaunchPolicy.shouldStartLocationServices(hasActiveRound: true, gpsPreheatEnabled: false, arguments: ["AI Caddie"]))
        XCTAssertFalse(WatchLocationLaunchPolicy.shouldStartLocationServices(hasActiveRound: true, gpsPreheatEnabled: true, arguments: ["AI Caddie", "-uitest-screen", "hole-map"]))
        XCTAssertTrue(WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(hasActiveRound: true, arguments: ["AI Caddie"], environment: [:]))
        XCTAssertFalse(WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(hasActiveRound: true, arguments: ["AI Caddie", "-uitest-screen", "hole-map"], environment: [:]))
    }

    // goals: W-13
    /// The current renderer version is accepted, while a stale version is rejected and cannot replace
    /// the cached image.
    func testHoleImageVersionRejectsStaleReplacement() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let image = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        let file = directory.appendingPathComponent("hole.img")
        try image.write(to: file)
        let imageStore = WatchHoleImageStore(directoryURL: directory)
        let client = WatchSyncClient(queueURL: directory.appendingPathComponent("queue.json"), holeImageStore: imageStore,
                                     courseStore: WatchCourseStore(directoryURL: directory.appendingPathComponent("courses")), session: nil)
        let current: [String: Any] = ["globalId": 31833, "hole": 1, "styleVersion": WatchBackendClient.topoStyleVersion, "geometryRevision": "r1"]
        XCTAssertTrue(client.receiveHoleImage(fileURL: file, metadata: current))
        let before = imageStore.data(globalId: 31833, hole: 1, geometryRevision: "r1")
        XCTAssertFalse(client.receiveHoleImage(
            fileURL: file,
            metadata: ["globalId": 31833, "hole": 1, "styleVersion": "topo-v-old", "geometryRevision": "r2"]
        ))
        XCTAssertEqual(imageStore.data(globalId: 31833, hole: 1, geometryRevision: "r1"), before)
    }

    private func map(width: Int) -> WatchHoleMap {
        WatchHoleMap(w: width, h: 100, you: [10, 90], pin: [90, 10], layup: [50, 50],
                     apex: [50, 50], greenCtrl: [70, 30], route: [[10, 90, 0], [90, 10, 350]])
    }

    // goals: W-13 [main]
    /// A complete downloaded course starts without phone configuration after a failed catalogue
    /// refresh; a second launch rebases the template onto a fresh round identity.
    func testCachedCourseStillStartsOfflineAfterRefreshFailure() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchCourseStore(directoryURL: directory.appendingPathComponent("courses"))
        let images = WatchHoleImageStore(directoryURL: directory.appendingPathComponent("images"))
        let option = WatchCourseOption(globalId: 81001, name: "Fixture Course", holes: 9, teeBox: "Blue")
        let states = (1...9).map { hole in
            WatchRoundState(roundId: "template-only", hole: hole, par: 4, distanceM: 350,
                            selectedClub: nil, globalId: 81001, sourceLocalHole: hole, courseHoleNumber: hole,
                            holeMap: map(width: 100), geometryCoverage: "ready",
                            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline")
        }
        try store.save(WatchCourseTemplate(option: option, courseName: option.name, teeBox: "Blue",
                                           holeStates: states, cachedAt: "2026-06-20T00:00:00Z"))
        let image = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        for hole in 1...9 { try images.store(data: image, globalId: 81001, hole: hole) }
        var requests = 0
        let backend = WatchBackendClient(baseURL: URL(string: "https://caddie.example")!, dataLoader: { _ in
            requests += 1
            throw URLError(.notConnectedToInternet)
        }, retrySleep: { _ in })
        var nextId = 0
        let library = WatchCourseLibrary(store: store, imageStore: images, makeRoundId: {
            nextId += 1
            return "offline-\(nextId)"
        }, clientFactory: { _ in backend })
        await library.refresh(config: WatchRoundConfig(baseURL: URL(string: "https://caddie.example")!, adminToken: nil))
        XCTAssertGreaterThan(requests, 0)
        XCTAssertNotNil(library.errorMessage)
        XCTAssertEqual(library.courses, [option])
        XCTAssertEqual(library.cachedCourseIds, [81001])
        let firstResult = await library.startCourse(option, config: nil)
        let first = try XCTUnwrap(firstResult)
        let secondResult = await library.startCourse(option, config: nil)
        let second = try XCTUnwrap(secondResult)
        XCTAssertEqual(first.roundId, "offline-1")
        XCTAssertEqual(second.roundId, "offline-2")
        XCTAssertEqual(first.holeStates.map(\.hole), Array(1...9))
        XCTAssertTrue(first.holeStates.allSatisfy { $0.roundId == "offline-1" && $0.holeMap != nil })
        XCTAssertTrue(second.holeStates.allSatisfy { $0.roundId == "offline-2" })
        XCTAssertEqual(requests, 1, "offline starts must not attempt a network download")
    }

    // goals: W-13
    /// Installing precise geometry during play preserves both saved score facts and the open draft;
    /// a late partial geometry response cannot downgrade the installed map.
    func testMapUpgradePreservesRoundScoresDraftAndDoesNotRegress() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchRoundStore(directoryURL: directory)
        var nextId = 0
        let model = WatchRoundModel(store: store, makeEventId: { nextId += 1; return "score-\(nextId)" })
        func state(hole: Int = 1, width: Int, coverage: String) -> WatchRoundState {
            WatchRoundState(roundId: "playing", hole: hole, par: 4, distanceM: 350,
                            selectedClub: nil, globalId: 81001, sourceLocalHole: hole, courseHoleNumber: hole,
                            holeMap: map(width: width),
                            geometryCoverage: coverage, score: 0, putts: 0, penaltyCount: 0,
                            caddieConfidence: "offline")
        }
        model.seedRound((1...9).map { state(hole: $0, width: 100, coverage: "partial") }, loopKey: "81001:front")
        XCTAssertEqual(model.round?.roundId, "playing")
        model.startScoringActiveHole()
        model.setDraftScore(5)
        model.saveActiveHole()
        let facts = store.pendingEvents()
        XCTAssertFalse(facts.isEmpty)
        model.selectHole(1)
        model.startScoringActiveHole()
        model.setDraftScore(6)
        model.applyCourseMapUpgrade([state(width: 200, coverage: "ready")])
        model.applyCourseMapUpgrade([state(width: 100, coverage: "partial")])
        XCTAssertEqual(model.round?.roundId, "playing")
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.activeHoleState?.holeMap?.w, 200)
        XCTAssertEqual(model.activeHoleState?.geometryCoverage, "ready")
        XCTAssertEqual(model.activeHoleState?.score, 5)
        XCTAssertEqual(model.draftScore, 6)
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(store.pendingEvents(), facts)
        let restored = WatchRoundModel(store: WatchRoundStore(directoryURL: directory))
        XCTAssertEqual(restored.round?.roundId, "playing")
        XCTAssertEqual(restored.activeHoleState?.score, 5)
        restored.resumeRound()
        XCTAssertEqual(restored.draftScore, 6)
    }

}
