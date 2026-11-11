// size: medium
// goals: I-02, I-03, I-04

import AICaddieDomain
import Foundation
import XCTest
@testable import AICaddie

final class RoundStartGoalTests: XCTestCase {
    // goals: I-02 [main]
    /// Nearby owns the venue row; downloaded loops remain available for offline coverage.
    func testNearbyVenueAppearsOnceAndDownloadedCoverageKeepsItsOwnLoops() throws {
        let venue = "北京鸿华"
        let loops = zip([31776, 39546, 45979], ["A", "B", "C"]).map { id, label in
            MobileCourseOption(
                globalId: id, name: "\(venue) ~ \(label)", holes: 9,
                venueName: venue, segmentLabel: label, segmentHoles: 9
            )
        }
        let rows = StartRoundPresentation.mergedCourseRows(
            nearby: loops, downloaded: [loops[0]]
        )
        let row = try XCTUnwrap(rows.first)
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(row.venue, venue)
        XCTAssertEqual(row.source, .nearby)
        XCTAssertEqual(row.segments.map(\.globalId), [31776, 39546, 45979])
        XCTAssertEqual(row.holes, 27)

        let offlineRows = StartRoundPresentation.mergedCourseRows(
            nearby: [], downloaded: [loops[0]]
        )
        let offline = try XCTUnwrap(offlineRows.first)
        XCTAssertEqual(offline.segments.map(\.globalId), [31776])
        XCTAssertEqual(
            StartRoundView.holeCaption(for: offline, downloaded: [loops[0]], catalogue: loops, recent: nil),
            "已下载 9/27 洞"
        )
    }

    // goals: I-02
    @MainActor
    func testCourseTeeSelectionUsesCarriedRowsThenReportsRetryableFailure() async {
        var loading = false
        var failed = false
        var requested = 0
        let carried = [CourseTee(teeBox: "blue", name: "Blue", yards: 3200)]
        let immediate = await StartRoundView.courseTeeRows(
            globalId: 1, carried: [1: carried],
            setLoading: { loading = $0 }, setFailed: { failed = $0 },
            request: { _ in requested += 1; return nil }
        )
        XCTAssertEqual(immediate, carried)
        XCTAssertFalse(loading)
        XCTAssertFalse(failed)
        XCTAssertEqual(requested, 0)

        let fetched = await StartRoundView.courseTeeRows(
            globalId: 2, carried: [:],
            setLoading: { loading = $0 }, setFailed: { failed = $0 },
            request: { _ in [CourseTee(teeBox: "white", name: "White")] }
        )
        XCTAssertEqual(fetched?.map(\.teeBox), ["white"])
        XCTAssertFalse(loading)
        XCTAssertFalse(failed)

        let empty = await StartRoundView.courseTeeRows(
            globalId: 3, carried: [:],
            setLoading: { loading = $0 }, setFailed: { failed = $0 },
            request: { _ in [] }
        )
        XCTAssertNil(empty)
        XCTAssertTrue(failed)
    }

    // goals: I-03
    func testRoundStartFailureAndProgressKeepTheRetryReasonVisible() {
        XCTAssertEqual(RoundStartFailure.timedOut.presentationMessage, "服务器较慢，没能开始，点重试")
        XCTAssertEqual(RoundStartFailure.unavailable.presentationMessage, "网络不可用，没能开始，点重试")
        XCTAssertEqual(RoundStartFailure.reauthentication.presentationMessage, "需重新登录后才能开始")
        XCTAssertNil(RoundStartProgress.message(after: 7.9))
        XCTAssertEqual(RoundStartProgress.message(after: 8), "服务器在准备球场，稍等…")
        XCTAssertTrue(RoundStartProgress.message(after: 20)?.contains("秒") == true)
        XCTAssertNil(StartRoundPresentation.roundStartProgressText(isBusy: false, message: "旧错误"))
        XCTAssertEqual(StartRoundPresentation.roundStartProgressText(isBusy: true, message: nil), "正在准备球场…")
    }

    // goals: I-03 [main]
    /// Exercise the model's public start/retry/cancel path against a failing transport. The retry
    /// remains the same user-visible failure and cancellation clears the in-flight evidence.
    @MainActor
    func testRoundStartEntrypointsKeepFailureEvidenceAndCancelCleanly() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("round-start-goal-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let package = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let baseURL = try XCTUnwrap(URL(string: "https://round-start-goal.example.test"))
        var requests = 0
        let lock = NSLock()
        let scope = CapturingURLProtocolScope { request in
            lock.lock(); requests += 1; lock.unlock()
            let response = try XCTUnwrap(HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 503,
                httpVersion: nil, headerFields: ["Content-Type": "application/json"]
            ))
            return (response, Data(#"{"detail":"fixture unavailable"}"#.utf8))
        }
        let session = URLSession(configuration: scope.configuration())
        let client = SyncClient(baseURL: baseURL, session: session, retrySleep: { _ in })
        let model = LiveRoundAppModel(
            offlineStore: OfflineStore(directoryURL: directory), apiBaseURL: baseURL,
            watchBridge: nil, garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: nil,
            roundStartProgressSleep: { _ in }
        )
        defer {
            client.invalidateForTesting()
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }

        model.startCourseRound(
            roundId: package.roundId, teeBox: package.course.teeBox,
            loops: package.loopEntries
        )
        await model.activeRoundStartTaskForTesting?.value
        XCTAssertEqual(model.roundStartFailure, .timedOut)
        XCTAssertTrue(model.syncStatus.contains("重试"))

        await model.retryRoundStart()
        XCTAssertEqual(model.roundStartFailure, .timedOut)
        lock.lock(); let retryRequests = requests; lock.unlock()
        XCTAssertGreaterThanOrEqual(retryRequests, 2)

        model.cancelRoundStart()
        XCTAssertNil(model.roundStartFailure)
        XCTAssertNil(model.pendingLiveHole)
        XCTAssertFalse(model.isPreparingRound)
    }

    // goals: I-03
    func testRoundStartProgressCountdownNeverBecomesNegative() {
        XCTAssertEqual(RoundStartProgress.remainingSeconds(after: 0), 30)
        XCTAssertEqual(RoundStartProgress.remainingSeconds(after: 29.1), 1)
        XCTAssertEqual(RoundStartProgress.remainingSeconds(after: 31), 0)
    }

    // goals: I-03
    func testStaleSyncFailureIsHiddenWhileAStartIsInFlight() {
        XCTAssertEqual(
            StartRoundPresentation.staleSyncFailureMessage(
                syncStatus: "服务器较慢，旧任务", roundStartFailure: nil,
                failurePresentation: .hidden, isPreparing: false, isOpeningPrep: false
            ),
            "服务器较慢，旧任务"
        )
        XCTAssertNil(StartRoundPresentation.staleSyncFailureMessage(
            syncStatus: "服务器较慢，旧任务", roundStartFailure: nil,
            failurePresentation: .hidden, isPreparing: true, isOpeningPrep: false
        ))
        XCTAssertNil(StartRoundPresentation.staleSyncFailureMessage(
            syncStatus: "服务器较慢，旧任务", roundStartFailure: .timedOut,
            failurePresentation: .hidden, isPreparing: false, isOpeningPrep: false
        ))
    }

    // goals: I-03
    func testUnknownSyncStatusDoesNotInventAStartFailure() {
        XCTAssertNil(StartRoundPresentation.syncFailureMessage(from: "同步已完成"))
        XCTAssertEqual(StartRoundPresentation.syncFailureMessage(from: " 网络不可用，稍后再试"), "网络不可用，稍后再试")
    }

    private func course() -> NineLoopCourse {
        NineLoopCourse(
            id: "venue",
            loops: [NineLoop(id: "a", name: "A"), NineLoop(id: "b", name: "B"), NineLoop(id: "c", name: "C")],
            usualPairs: ["a": "b", "b": "c"]
        )
    }

    // goals: I-04
    func testNineLoopPlanOffersTheUsualSecondLoopAndLocksItAfterItsFirstHole() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: course(), first: "a"))
        XCTAssertEqual(plan.first, "a")
        XCTAssertEqual(plan.second, .loop("b"))
        XCTAssertTrue(plan.canChangeSecond)
        plan.beginFirstLoop()
        plan.reachTurn()
        plan.chooseSecond(.loop("c"))
        XCTAssertEqual(plan.second, .loop("c"))
        plan.beginSecondLoop()
        XCTAssertEqual(plan.phase, .secondLoop)
        XCTAssertFalse(plan.canChangeSecond)
        plan.chooseSecond(.loop("b"))
        XCTAssertEqual(plan.second, .loop("c"))
    }

    // goals: I-04
    func testChangingTheFirstLoopReResolvesTheSecondLoop() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: course(), first: "a"))
        plan.selectFirst("b")
        XCTAssertEqual(plan.first, "b")
        XCTAssertEqual(plan.second, .loop("c"))
        plan.selectFirst("missing")
        XCTAssertEqual(plan.first, "b")
    }

    // goals: I-04
    func testStopAfterNineFinishesWithoutEnteringASecondLoop() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: course()))
        plan.reachTurn()
        plan.chooseSecond(.stopAfterNine)
        plan.beginSecondLoop()
        XCTAssertEqual(plan.phase, .finishedAfterNine)
        XCTAssertEqual(plan.second, .stopAfterNine)
        XCTAssertEqual(plan.turnActionTitle, "结束 · 只打 9 洞")
    }

    // goals: I-04
    /// The turn planner resolves a factual second-nine candidate.
    func testTurnPlannerResolvesSecondNineCandidate() throws {
        let package = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let active = MobileCourseOption(
            globalId: package.course.globalId,
            name: "Fixture Links ~ A",
            holes: 9,
            venueName: package.course.name,
            segmentLabel: "A",
            segmentHoles: 9
        )
        let plan = try XCTUnwrap(
            NineLoopTurn.planAtEndOfFirstLoop(
                package: package,
                catalogue: [active],
                remembered: [:],
                history: []
            )
        )
        XCTAssertEqual(plan.phase, .atTurn)
        XCTAssertEqual(plan.first, NineLoopTurn.loopId(package.roundLoops[0].entry))
        XCTAssertEqual(plan.second, .loop(NineLoopTurn.loopId(package.roundLoops[0].entry)))
        XCTAssertEqual(plan.turnActionTitle, "接着打 A 场")
    }

    // goals: I-04 [main]
    /// Resume a scored nine, resolve the turn from installed loops and continue through the
    /// same model entry point the phone uses. Display hole ten maps to physical hole one.
    @MainActor
    func testRecordedNineContinuesIntoInstalledSecondLoopWithCorrectPhysicalHoles() async throws {
        ensureC156TopoBundleStub()
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("turn-goal-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let source = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let prep = try JSONDecoder().decode(
            CoursePrepResponse.self, from: offlinePrepResponseData(for: source)
        )
        let package = source.replacingCoursePrep(CoursePrepPackage(
            schema: prep.schema, globalId: prep.globalId, holes: prep.holes, missingData: nil
        ))
        try store.saveCourseTemplate(package)
        for hole in package.holes {
            _ = try store.saveCourseTopoImage(
                validOnePixelPNGData(), globalId: hole.sourceGlobalId,
                localHole: hole.sourceLocalHole, geometryRevision: hole.geometryRevision
            )
        }
        try store.saveRoundPackage(package)
        try store.appendEvent(LiveRoundEvent(
            eventId: "turn-score-nine", roundId: package.roundId,
            timestamp: "2026-07-29T05:00:00Z", hole: 9, kind: .score,
            payload: ["strokes": .number(4)]
        ))
        let bagIsolation = try GoalClubBagIsolation()
        let model = LiveRoundAppModel(
            offlineStore: store, apiBaseURL: URL(string: "https://round-start-goal.example.test"), watchBridge: nil,
            garminSessionStore: nil, networkPathObserver: nil
        )
        addTeardownBlock {
            await model.stopRoundBackgroundWorkForTesting()
            await bagIsolation.restore()
        }
        await model.bootstrap()
        XCTAssertEqual(model.package?.roundId, package.roundId)
        XCTAssertEqual(model.downloadedCourseOptions.map(\.globalId), [package.course.globalId])
        model.consumePendingLiveHole()
        model.setActiveHole(9)
        let active = try XCTUnwrap(model.package)
        let catalogue = NineLoopTurn.loopCatalogue(
            network: model.courseOptions, downloaded: model.downloadedCourseOptions
        )
        let plan = try XCTUnwrap(NineLoopTurn.planAtEndOfFirstLoop(
            package: active, catalogue: catalogue, remembered: [:], history: []
        ))
        XCTAssertEqual(plan.phase, .atTurn)
        let second = try XCTUnwrap(plan.secondLoop)
        let entry = try XCTUnwrap(NineLoopTurn.entry(second.id))
        await model.continueIntoSecondLoop(entry, roundId: package.roundId)
        XCTAssertEqual(model.package?.holes.map(\.number), Array(1...18))
        XCTAssertEqual(model.liveRoundState?.activeHole, 10)
        XCTAssertEqual(model.pendingLiveHole, 10)
        XCTAssertEqual(model.package?.holes.first { $0.number == 10 }?.sourceLocalHole, 1)
        XCTAssertEqual(model.package?.holes.first { $0.number == 10 }?.sourceGlobalId, entry.globalId)
        XCTAssertEqual(model.liveRoundState?.holeState(for: 9)?.score, 4)
        model.setActiveHole(18)
        XCTAssertEqual(model.package?.holes.first { $0.number == 18 }?.sourceLocalHole, 9)
        XCTAssertEqual(model.liveRoundState?.activeHole, 18)
        await model.stopRoundBackgroundWorkForTesting()
    }

    // goals: I-04
    func testInvalidSecondLoopAndLateTurnChangesAreIgnored() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: course()))
        plan.chooseSecond(.loop("missing"))
        XCTAssertEqual(plan.second, .loop("b"))
        plan.beginSecondLoop()
        plan.chooseSecond(.stopAfterNine)
        XCTAssertEqual(plan.second, .loop("b"))
    }

    // goals: I-04
    func testCourseRefreshKeepsStopChoiceButRepairsStaleLoopChoice() throws {
        var plan = try XCTUnwrap(NineLoopPlan(course: course()))
        plan.normalize(with: NineLoopCourse(id: "venue", loops: [NineLoop(id: "a", name: "A")]))
        XCTAssertEqual(plan.second, .loop("a"))
        plan.reachTurn()
        plan.chooseSecond(.stopAfterNine)
        plan.normalize(with: NineLoopCourse(id: "venue", loops: [NineLoop(id: "a", name: "A"), NineLoop(id: "d", name: "D")]))
        XCTAssertEqual(plan.second, .stopAfterNine)
    }
}
