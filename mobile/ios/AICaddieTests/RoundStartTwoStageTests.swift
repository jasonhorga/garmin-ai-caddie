#if !SWIFT_PACKAGE
import Combine
import Foundation
import XCTest
@testable import AICaddie

/// The fixture's course (front nine of 31795). File-level so the URLProtocol handlers can read it.
private let c85CourseId = 31795

/// C85 (build 96, 北京沙河): Start waited 10–20 s for the complete personal package before the hole
/// screen, and later holes showed a spinner because no Garmin raster was cached ahead of them.
///
/// The start now enters on the map-only package (`map_only=true`, the Watch's #426 contract) and
/// fills the personal package in later; the whole course's Garmin rasters download in play order;
/// and a course-intent prefetch never runs beside the start.
///
/// Each test owns its host. Held requests stand in for the 20 s cold full package (docs/operations/
/// 2026-10-14-nearby-map-startup.md: 24 s cold, 4.7 s warm, map package 0.3–0.6 s): they are only
/// answered when the test says so, so a start that waits for them never enters within the wait.
@MainActor
final class RoundStartTwoStageTests: XCTestCase {
    /// Far below the 30 s start budget and far above a CI simulator stall.
    private let eventWait: TimeInterval = 10
    /// Every model a test made, torn down after the test in `tearDown` — also when it threw early.
    private var fixtures: [ModelFixture] = []

    override func setUp() {
        super.setUp()
        URLProtocol.registerClass(C33URLProtocol.self)
    }

    override func tearDown() async throws {
        for fixture in fixtures {
            await fixture.tearDown()
        }
        fixtures.removeAll()
        C33URLProtocol.setHandlers(onStart: nil)
        URLProtocol.unregisterClass(C33URLProtocol.self)
        try await super.tearDown()
    }

    func testMapOnlyPackageRequestCarriesTheWatchContract() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let responseData = try JSONEncoder().encode(try package(roundId: "c85-map-query", mapOnly: true))
        let log = C85RequestLog()
        CapturingURLProtocol.requestHandler = { request in
            log.append(request)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(baseURL: try XCTUnwrap(URL(string: "https://c85-query.example.test")), session: session)
        let loops = [RoundLoopEntry(globalId: c85CourseId, half: "front")]

        _ = try await client.fetchCoursePackage(
            globalId: c85CourseId, roundId: "c85-map-query", teeBox: "blue", loops: loops,
            backgroundGeometry: true, mapOnly: true
        )
        _ = try await client.fetchCoursePackage(
            globalId: c85CourseId, roundId: "c85-map-query", teeBox: "blue", loops: loops,
            backgroundGeometry: true
        )

        let requests = log.all
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests.first.flatMap { c33Query($0, "map_only") }, "true")
        XCTAssertEqual(requests.first.flatMap { c33Query($0, "background_geometry") }, "true")
        XCTAssertNil(requests.last.flatMap { c33Query($0, "map_only") }, "the ordinary package is unchanged")
    }

    func testPersonalRequestWaitsForInitialHoleLoadAndRecentHistoryWaitsForMerge() async throws {
        let host = "c91-gate.example.test"
        let roundId = "c91-gate"
        let map = try package(roundId: roundId, mapOnly: true)
        let full = try package(roundId: roundId, mapOnly: false)
        let mapData = try JSONEncoder().encode(map)
        let fullData = try JSONEncoder().encode(full)
        let held = C85HeldRequests()
        let sentBeforeReady = expectation(description: "personal package sent before initial hole load")
        sentBeforeReady.isInverted = true
        let sentAfterReady = expectation(description: "personal package sent after initial hole load")
        let ready = C85Counter()
        let earlyOnce = C33FirstMatch(), afterOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package" else {
                proto.reply(404); return
            }
            if c33Query(proto.request, "map_only") == "true" { proto.reply(200, mapData); return }
            guard c33Query(proto.request, "round_id") == roundId else { proto.reply(404); return }
            held.hold(proto)
            if ready.value == 0 {
                if earlyOnce.claim() { sentBeforeReady.fulfill() }
            } else if afterOnce.claim() { sentAfterReady.fulfill() }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        // The shared fixture documents three previous rounds, latest round-a on May 20.
        let previous = MobileCourseOption(globalId: c85CourseId, name: "Fixture Links", roundCount: 3,
                                          latestRoundId: "round-a", latestRoundDate: "2026-05-20T08:00:00", holes: 9, teeBox: "blue")
        try fixture.store.saveRecentCourseSelection(previous)
        await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: map.loopEntries)
        // Even the asset pipeline's fallback release cannot substitute for the initial-load signal.
        let generation = try XCTUnwrap(model.freshEntryReleaseGenerationForTesting)
        model.releaseFreshEntryForTesting(generation: generation)
        await fulfillment(of: [sentBeforeReady], timeout: 0.2)
        XCTAssertEqual(try fixture.store.loadRecentCourseSelection()?.roundCount, 3)
        XCTAssertEqual(try fixture.store.loadRecentCourseSelection()?.latestRoundId, "round-a")
        ready.set(1)
        model.liveHoleInitialLoadDidFinish()
        await fulfillment(of: [sentAfterReady], timeout: eventWait)
        held.releaseAll(200, fullData)
        await model.waitForRoundEnrichmentForTesting()
        XCTAssertEqual(model.recentCourseOption?.roundCount, 3)
        XCTAssertEqual(model.recentCourseOption?.latestRoundId, "round-a")
        XCTAssertEqual(try fixture.store.loadRecentCourseSelection()?.roundCount, 3)
        XCTAssertEqual(try fixture.store.loadRecentCourseSelection()?.latestRoundDate, "2026-05-20T08:00:00")
    }

    func testLatePersonalPackageCannotRecreateADiscardedRoundOrReplaceANewRound() async throws {
        let host = "c91-stale.example.test"
        let oldMap = try package(roundId: "c91-old", mapOnly: true, standalone: true)
        let oldFull = try package(roundId: "c91-old", mapOnly: false, standalone: true)
        let newMap = try package(roundId: "c91-new", mapOnly: true, standalone: true)
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host, c33Query(proto.request, "map_only") == "true" else {
                proto.reply(404); return
            }
            let snapshot = c33Query(proto.request, "round_id") == "c91-old" ? oldMap : newMap
            proto.reply(200, try! JSONEncoder().encode(snapshot))
        })
        let fixture = makeModel(host: host)
        let model = fixture.model
        await model.prepareCourseRound(roundId: oldMap.roundId, teeBox: "blue", loops: oldMap.loopEntries)
        model.discardActiveRound()
        XCTAssertFalse(model.mergeRoundEnrichmentForTesting(oldFull))
        XCTAssertNil(model.liveRoundState)
        XCTAssertNil(try fixture.store.loadCurrentRoundPackage())
        await model.prepareCourseRound(roundId: newMap.roundId, teeBox: "blue", loops: newMap.loopEntries)
        XCTAssertFalse(model.mergeRoundEnrichmentForTesting(oldFull))
        XCTAssertEqual(model.package?.roundId, "c91-new")
        XCTAssertEqual(try fixture.store.loadCurrentRoundPackage()?.roundId, "c91-new")
        XCTAssertEqual(model.package?.clubProfiles, [])
        let template = try XCTUnwrap(fixture.store.loadCourseTemplate(globalId: c85CourseId, teeBox: "blue"))
        XCTAssertEqual(template.roundId, "c91-new")
        XCTAssertEqual(template.clubProfiles, [])
    }

    func testStartEntersOnTheMapPackageAndMergesTheFullPackageIntoTheSameRound() async throws {
        let host = "c85-two-stage.example.test"
        let roundId = "c85-two-stage"
        let mapPackage = try package(roundId: roundId, mapOnly: true)
        let fullPackage = try package(roundId: roundId, mapOnly: false)
        let mapData = try JSONEncoder().encode(mapPackage)
        let fullData = try JSONEncoder().encode(fullPackage)
        let held = C85HeldRequests()
        let log = C85RequestLog()
        let fullSent = expectation(description: "full package requested")
        let fullSentOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package" else {
                proto.reply(404); return
            }
            log.append(proto.request)
            if c33Query(proto.request, "map_only") == "true" {
                proto.reply(200, mapData)
                return
            }
            // The complete package is the slow one: held until the player is already on the course.
            held.hold(proto)
            if fullSentOnce.claim() { fullSent.fulfill() }
        }, onStop: { request in
            guard request.url?.host == host else { return }
            held.forget(request)
        })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        let entered = expectation(description: "hole 1 entered")
        let subscription = model.$pendingLiveHole.compactMap { $0 }.first().sink { _ in entered.fulfill() }
        defer { subscription.cancel() }

        let start = Task {
            await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)
        }
        defer { start.cancel() }
        // Behaviour, not the clock: the full package is never answered here, so hole 1 can only be
        // entered within the wait if the start does not wait for it.
        await fulfillment(of: [entered], timeout: eventWait)
        await start.value
        model.liveHoleInitialLoadDidFinish()
        await fulfillment(of: [fullSent], timeout: eventWait)
        XCTAssertEqual(model.pendingLiveHole, 1)
        XCTAssertFalse(model.isPreparingRound, "the spinner ends with the map package")
        XCTAssertEqual(model.package?.roundId, roundId)
        XCTAssertEqual(model.package?.clubProfiles, [], "hole 1 opens on the map package")

        // The player scores hole 1 and walks to hole 2 while the personal package is still building.
        model.handleEvent(LiveRoundEvent(
            eventId: "c85-hole-1-score",
            roundId: roundId,
            clientId: "ios-phone",
            timestamp: "2026-10-26T08:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(5)]
        ))
        model.setActiveHole(2)

        held.releaseAll(200, fullData)
        await model.waitForRoundEnrichmentForTesting()

        let merged = try XCTUnwrap(model.package)
        XCTAssertEqual(merged.roundId, roundId, "the personal package never changes the round")
        XCTAssertEqual(model.liveRoundState?.roundId, roundId)
        XCTAssertEqual(merged.clubProfiles, fullPackage.clubProfiles, "clubs arrive with the full package")
        XCTAssertEqual(Set(merged.caddieContextSeeds.map(\.hole)), Set(1...9), "caddie seeds arrive too")
        XCTAssertEqual(model.liveRoundState?.activeHole, 2, "the merge does not move the player")
        XCTAssertEqual(model.liveRoundState?.holeState(for: 1)?.score, 5, "a recorded score survives the merge")
        XCTAssertEqual(
            try fixture.store.loadRoundPackage(roundId: roundId)?.clubProfiles,
            fullPackage.clubProfiles,
            "the merged package is what a relaunch resumes"
        )
        let requests = log.all
        XCTAssertEqual(requests.first.flatMap { c33Query($0, "map_only") }, "true", "the start asks for the map first")
        let background = requests.filter { c33Query($0, "map_only") == nil }
        XCTAssertEqual(background.count, 1)
        XCTAssertEqual(background.first.flatMap { c33Query($0, "round_id") }, roundId)
        await model.waitForOfflineCourseDownloadForTesting()
    }

    func testAFailedFullPackageIsRetriedWhileScoringKeepsWorking() async throws {
        let host = "c85-retry.example.test"
        let roundId = "c85-retry"
        let mapPackage = try package(roundId: roundId, mapOnly: true)
        let fullPackage = try package(roundId: roundId, mapOnly: false)
        let mapData = try JSONEncoder().encode(mapPackage)
        let fullData = try JSONEncoder().encode(fullPackage)
        let failures = C85Counter()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package" else {
                proto.reply(404); return
            }
            if c33Query(proto.request, "map_only") == "true" {
                proto.reply(200, mapData)
            } else if failures.increment() <= 2 {
                proto.reply(503)
            } else {
                proto.reply(200, fullData)
            }
        })
        let fixture = makeModel(host: host)
        let model = fixture.model
        model.roundEnrichmentRetryDelaysNanoseconds = [0, 0, 0, 0]

        await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)
        XCTAssertEqual(model.pendingLiveHole, 1, "a failing personal package does not hold up the start")
        XCTAssertNil(model.roundStartFailure)
        model.handleEvent(LiveRoundEvent(
            eventId: "c85-retry-score",
            roundId: roundId,
            clientId: "ios-phone",
            timestamp: "2026-10-26T08:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        ))
        model.liveHoleInitialLoadDidFinish()
        await model.waitForRoundEnrichmentForTesting()

        XCTAssertGreaterThan(failures.value, 2, "the failed package was asked for again")
        XCTAssertEqual(model.package?.roundId, roundId)
        XCTAssertEqual(model.package?.clubProfiles, fullPackage.clubProfiles)
        XCTAssertEqual(model.liveRoundState?.holeState(for: 1)?.score, 4)
        await model.waitForOfflineCourseDownloadForTesting()
    }

    func testEntryDownloadsEveryGarminRasterInPlayOrderFromTheHoleBeingPlayed() async throws {
        let host = "c85-raster.example.test"
        let roundId = "c85-raster"
        let roundPackage = try package(roundId: roundId, mapOnly: false, garminRasterVersion: "c85-r1")
        let data = try JSONEncoder().encode(roundPackage)
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package" else {
                proto.reply(404); return
            }
            proto.reply(200, data)
        })
        let fixture = makeModel(host: host)
        let model = fixture.model
        let downloads = C85DownloadLog()
        model.garminRasterDownloader = { url in
            downloads.urls.append(url)
            return true
        }
        // The package's own URLs, version query included (C88 adds `?v=`); never rebuilt locally.
        func raster(_ hole: Int) -> URL {
            URL(string: "https://\(host)/api/v2/courses/\(c85CourseId)/holes/\(hole)/garmin-raster.jpg?v=c85-r1")!
        }

        await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: roundPackage.loopEntries)
        XCTAssertEqual(model.pendingLiveHole, 1)
        await model.waitForGarminRasterDownloadForTesting()
        XCTAssertEqual(downloads.urls, (1...9).map(raster), "every hole, in play order from the first tee")

        // The player is on hole 6 when the course pass runs again: it starts there and wraps.
        downloads.urls.removeAll()
        model.setActiveHole(6)
        await model.waitForGarminRasterDownloadForTesting()
        XCTAssertEqual(downloads.urls, [6, 7, 8, 9, 1, 2, 3, 4, 5].map(raster))
        await model.waitForOfflineCourseDownloadForTesting()
    }

    func testACourseIntentDoesNotRunBesideTheStart() async throws {
        let host = "c85-intent.example.test"
        let roundId = "c85-intent"
        let intentId = 31796
        let mapPackage = try package(roundId: roundId, mapOnly: false)
        let mapData = try JSONEncoder().encode(mapPackage)
        let held = C85HeldRequests()
        let phase = C85Counter()
        let intentSent = expectation(description: "intent package sent")
        let intentStopped = expectation(description: "intent package cancelled by the start")
        let startSent = expectation(description: "start package sent")
        let resentDuringStart = expectation(description: "intent sent again while the start runs")
        resentDuringStart.isInverted = true
        let resentAfterEntry = expectation(description: "intent sent again before the fresh entry is released")
        resentAfterEntry.isInverted = true
        let intentSentOnce = C33FirstMatch(), intentStoppedOnce = C33FirstMatch(), startSentOnce = C33FirstMatch()
        let resentDuringStartOnce = C33FirstMatch(), resentAfterEntryOnce = C33FirstMatch()
        let intentPath = "/api/v2/mobile/courses/\(intentId)/package"
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            switch proto.request.url?.path {
            case intentPath:
                held.hold(proto)
                switch phase.value {
                case 0: if intentSentOnce.claim() { intentSent.fulfill() }
                case 1: if resentDuringStartOnce.claim() { resentDuringStart.fulfill() }
                default: if resentAfterEntryOnce.claim() { resentAfterEntry.fulfill() }
                }
            case "/api/v2/mobile/courses/\(c85CourseId)/package":
                held.hold(proto)
                if startSentOnce.claim() { startSent.fulfill() }
            default:
                proto.reply(404)
            }
        }, onStop: { request in
            guard request.url?.host == host else { return }
            held.forget(request)
            guard request.url?.path == intentPath else { return }
            if intentStoppedOnce.claim() { intentStopped.fulfill() }
        })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        let intent = MobileCourseOption(globalId: intentId, name: "Intent nine", holes: 9, teeBox: "blue")

        // 1.5 s after the Tee is chosen, the venue's other nine starts installing.
        model.prefetchIntendedCourses([intent], teeBox: "blue")
        await fulfillment(of: [intentSent], timeout: eventWait)

        // 开球: the intent request is cancelled and the start is sent.
        phase.set(1)
        let start = Task {
            await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)
        }
        defer { start.cancel() }
        await fulfillment(of: [intentStopped, startSent], timeout: eventWait)

        // The home's 在这个球场 card announces the same intent while the start is still in flight: it
        // must wait instead of building a whole-course package beside the start.
        model.prefetchIntendedCourses([intent], teeBox: "blue")
        await fulfillment(of: [resentDuringStart], timeout: 2)

        phase.set(2)
        held.releaseStartPackage(path: "/api/v2/mobile/courses/\(c85CourseId)/package", data: mapData)
        await start.value
        XCTAssertEqual(model.pendingLiveHole, 1)
        // Hole 1 still has priority until its first load settles (or the fallback fires).
        await fulfillment(of: [resentAfterEntry], timeout: 2)
        await model.cancelPrepCourseDownloadForTesting()
    }

    /// Teardown guard (fixture run 40308301959): once the test hook has returned, nothing the round
    /// started in the background sends another request — the session is invalidated right after.
    func testAStoppedModelSendsNoFurtherRequest() async throws {
        // C85: pin cancellation between request construction and URLSession transport. This makes
        // the stop boundary deterministic instead of relying on the scheduler to expose it.
        let host = "c85-stop.example.test"
        let roundId = "c85-stop"
        let mapPackage = try package(roundId: roundId, mapOnly: true, garminRasterVersion: "c85-stop")
        let mapData = try JSONEncoder().encode(mapPackage)
        let held = C85HeldRequests()
        let requests = C85Counter()
        let installStatusRequests = C85Counter()
        let stopped = C85Counter()
        let latePaths = C85RequestLog()
        let fullSent = expectation(description: "full package requested")
        let lateRequest = expectation(description: "a request after the stop")
        lateRequest.isInverted = true
        let installStatusGateEntered = expectation(description: "install status gate entered")
        let installStatusGate = C90RequestGate()
        let installStatusGateOnce = C33FirstMatch()
        let fullSentOnce = C33FirstMatch(), lateRequestOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            // The client's requests. The hole screen's image stores (first-hole topo warm-up) go
            // through the shared session, which is never invalidated, and ask for `Accept: image/*`.
            let isInstallStatus = proto.request.url?.path == "/api/v2/courses/\(c85CourseId)/install/status"
            if isInstallStatus {
                installStatusRequests.increment()
            }
            if proto.request.value(forHTTPHeaderField: "Accept")?.hasPrefix("image/") != true {
                requests.increment()
                if isInstallStatus, stopped.value > 0 {
                    latePaths.append(proto.request)
                    if lateRequestOnce.claim() { lateRequest.fulfill() }
                }
            }
            guard proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package" else {
                proto.reply(404); return
            }
            if c33Query(proto.request, "map_only") == "true" {
                proto.reply(200, mapData)
                return
            }
            held.hold(proto)
            if fullSentOnce.claim() { fullSent.fulfill() }
        }, onStop: { request in
            guard request.url?.host == host else { return }
            held.forget(request)
        })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        fixture.client.requestDataGateForTesting = { request in
            guard request.url?.path == "/api/v2/courses/\(c85CourseId)/install/status",
                  installStatusGateOnce.claim() else { return }
            installStatusGateEntered.fulfill()
            await installStatusGate.wait()
        }
        // A personal package still alive after the stop would retry a failure at once.
        model.roundEnrichmentRetryDelaysNanoseconds = [0, 0, 0, 0]
        let rasterStarted = expectation(description: "raster pass running")
        let rasterStartedOnce = C33FirstMatch()
        let rasterCalls = C85Counter()
        model.garminRasterDownloader = { _ in
            rasterCalls.increment()
            if rasterStartedOnce.claim() { rasterStarted.fulfill() }
            // A raster that never arrives: only cancelling the pass ends it.
            try? await Task.sleep(nanoseconds: 600_000_000_000)
            return false
        }

        let start = Task {
            await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)
        }
        defer { start.cancel() }
        await fulfillment(of: [rasterStarted], timeout: eventWait)
        await start.value
        XCTAssertEqual(model.pendingLiveHole, 1)
        model.liveHoleInitialLoadDidFinish()
        await fulfillment(of: [fullSent], timeout: eventWait)
        await fulfillment(of: [installStatusGateEntered], timeout: eventWait)

        let stopping = Task { await model.stopRoundBackgroundWorkForTesting() }
        stopped.set(1)
        await Task.yield()
        await installStatusGate.release()
        await stopping.value
        await waitForNoRunningTasks(fixture.session)
        let requestsAtStop = requests.value
        let installStatusAtStop = installStatusRequests.value
        // Push everything that could start work again: the held personal package fails now (a live
        // retry loop would ask again at once) and the live view repeats its initial-load callback
        // (it must not restart personal enrichment or either asset pass after the stop).
        held.releaseAll(503)
        model.liveHoleInitialLoadDidFinish()
        await fulfillment(of: [lateRequest], timeout: 2)

        let paths = latePaths.all.compactMap { request -> String? in
            guard let url = request.url else { return nil }
            return url.path + (url.query.map { "?\($0)" } ?? "")
        }
        XCTAssertEqual(requests.value, requestsAtStop, "no request after the stop; paths=\(paths)")
        XCTAssertEqual(installStatusRequests.value, installStatusAtStop, "no install/status start after the stop")
        XCTAssertEqual(rasterCalls.value, 1, "the raster pass ended at the stop")
        XCTAssertEqual(model.package?.clubProfiles, [], "the personal package was never merged")
    }

    /// J5.2/J4.2: a quarantine-blocked Save & End keeps the live round's background ownership.
    func testQuarantineBlockedFinishKeepsRoundBackgroundWorkAlive() async throws {
        let (fixture, package, _) = try await startRoundWithHeldBackgroundWork(
            host: "c90-quarantine-finish.example.test", roundId: "c90-quarantine-finish"
        )
        try fixture.store.quarantineEvent(
            LiveRoundEvent(
                eventId: "c90-quarantine-score", roundId: package.roundId,
                timestamp: "2026-10-28T00:00:00Z", hole: 1, kind: .score,
                payload: ["strokes": .number(5)]
            ),
            status: 422,
            reason: "score rejected"
        )
        let result = await fixture.model.finishActiveRound()
        XCTAssertFalse(result)
        XCTAssertEqual(fixture.model.offlineCourseDownloadRoundIdForTesting, package.roundId)
    }

    /// J5.2/J4.2: a Watch-finished round blocked by quarantine remains resumable on the phone.
    func testQuarantineBlockedWatchFinishKeepsRoundBackgroundWorkAlive() async throws {
        let (fixture, package, _) = try await startRoundWithHeldBackgroundWork(
            host: "c90-quarantine-watch.example.test", roundId: "c90-quarantine-watch"
        )
        try fixture.store.quarantineEvent(
            LiveRoundEvent(
                eventId: "c90-watch-quarantine-score", roundId: package.roundId,
                timestamp: "2026-10-28T00:00:00Z", hole: 1, kind: .score,
                payload: ["strokes": .number(5)]
            ),
            status: 422,
            reason: "score rejected"
        )
        fixture.model.handleWatchRoundClosure(
            WatchRoundClosurePayload(roundId: package.roundId, disposition: .finished)
        )
        await fixture.model.waitForWatchRoundClosureReconciliationForTesting()
        XCTAssertEqual(fixture.model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(fixture.model.offlineCourseDownloadRoundIdForTesting, package.roundId)
    }

    /// J5.2/J4.2: an event-log failure in explicit discard leaves the active round and downloads intact.
    func testDiscardFailureKeepsRoundBackgroundWorkAlive() async throws {
        let (fixture, package, _) = try await startRoundWithHeldBackgroundWork(
            host: "c90-discard-failure.example.test", roundId: "c90-discard-failure"
        )
        try Data("{broken}\n".utf8).write(
            to: fixture.directory.appendingPathComponent("events.jsonl"), options: [.atomic]
        )
        fixture.model.discardActiveRound()
        XCTAssertEqual(fixture.model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(fixture.model.offlineCourseDownloadRoundIdForTesting, package.roundId)
    }

    /// J4.2: ending a round must leave another player-requested prep download running in place.
    func testDiscardLeavesAnotherPrepCourseDownloadRunning() async throws {
        let host = "c90-prep-survives-discard.example.test"
        let roundId = "c90-prep-survives-discard"
        let roundPackage = try package(roundId: roundId, mapOnly: false)
        let roundData = try JSONEncoder().encode(roundPackage)
        let targetHeld = C85HeldRequests()
        let targetStarted = expectation(description: "another prep course request started")
        let targetRetried = expectation(description: "another prep course request retried after release")
        let targetOnce = C33FirstMatch()
        let targetRequests = C85Counter()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            let path = proto.request.url?.path ?? ""
            if path == "/api/v2/mobile/courses/\(c85CourseId)/package" {
                proto.reply(200, roundData)
            } else if path == "/api/v2/mobile/courses/31800/package" {
                targetHeld.hold(proto)
                let count = targetRequests.increment()
                if targetOnce.claim() { targetStarted.fulfill() }
                if count == 2 { targetRetried.fulfill() }
            } else {
                proto.reply(503)
            }
        }, onStop: { request in
            guard request.url?.host == host else { return }
            targetHeld.forget(request)
        })
        let fixture = makeModel(host: host, held: targetHeld)
        let model = fixture.model
        await model.prepareCourseRound(
            roundId: roundId, teeBox: "blue", loops: roundPackage.loopEntries
        )
        model.liveHoleInitialLoadDidFinish()
        model.downloadPrepCourse(
            MobileCourseOption(globalId: 31800, name: "Second course", holes: 18, teeBox: "blue")
        )
        await fulfillment(of: [targetStarted], timeout: eventWait)
        model.discardActiveRound()
        let target = try XCTUnwrap(model.prepCourseDownloads.first { $0.course.globalId == 31800 })
        XCTAssertNotEqual(target.phase, .queued, "discard must not requeue the shared prep job")
        XCTAssertEqual(model.activePrepCourseDownloadIDForTesting, target.id)
        targetHeld.releaseAll(503)
        await fulfillment(of: [targetRetried], timeout: eventWait)
    }

    /// J4.2: Save & End keeps the current course's whole-course download alive until its request ends.
    func testFinishKeepsWholeCourseDownloadRunning() async throws {
        // OfflineStore intentionally skips fixture-mode packages and partial physical courses.
        // Model a complete nine-hole course so this test can observe the installer's durable write.
        let roundPackage = try package(
            roundId: "c90-finish-offline", mapOnly: false,
            garminRasterVersion: "c90-r6", standalone: true
        )
        let prepData = try offlinePrepResponseData(for: roundPackage)
        let installData = installStatusResponseData(for: roundPackage)
        do {
            // These are the same DTOs/JSONDecoder calls used by SyncClient's response readers.
            let prep = try JSONDecoder().decode(CoursePrepResponse.self, from: prepData)
            let install = try JSONDecoder().decode(CourseInstallStatus.self, from: installData)
            XCTAssertEqual(prep.holes.count, roundPackage.holes.count)
            XCTAssertEqual(install.holes.count, roundPackage.holes.count)
        } catch {
            XCTFail("whole-course fixture failed product response decoding: \(error)")
            throw error
        }
        let (fixture, package, held) = try await startRoundWithHeldBackgroundWork(
            host: "c90-finish-offline.example.test", roundId: "c90-finish-offline",
            roundPackage: roundPackage
        )
        XCTAssertNil(package.coursePrep, "ready prep must come from the released download")
        XCTAssertNil(try fixture.store.loadCourseTemplate(globalId: c85CourseId, teeBox: "blue")?.coursePrep)
        let result = await fixture.model.finishActiveRound()
        XCTAssertTrue(result)
        XCTAssertEqual(fixture.model.offlineCourseDownloadRoundIdForTesting, package.roundId)
        let responses = C90ResponseLog()
        let diagnostics = {
            "ownership=\(String(describing: fixture.model.offlineCourseDownloadRoundIdForTesting)) "
                + "interrupted=\(String(describing: fixture.model.interruptedOfflineCourseDownloadRoundIdForTesting)) "
                + "dataMode=\(package.dataMode) loopKey=\(package.loopKey) "
                + "syncStatus=\(fixture.model.syncStatus) requests=\(responses.all)"
        }
        held.releaseAllAndReplyFuture { request in
            let response: (status: Int, data: Data)
            let usedDefault: Bool
            switch request.url?.path {
            case "/api/v2/courses/\(c85CourseId)/install/status":
                response = (200, installData)
                usedDefault = false
            case "/api/v2/courses/\(c85CourseId)/prep":
                response = (200, prepData)
                usedDefault = false
            case let path where path?.hasSuffix("/topo.png") == true:
                response = (200, validOnePixelPNGData())
                usedDefault = false
            default:
                response = (404, Data())
                usedDefault = true
            }
            responses.append(request, status: response.status, usedDefault: usedDefault)
            return response
        }
        do {
            try await waitForOfflineCourseDownloadWithin(fixture.model)
        } catch {
            XCTFail("whole-course download exceeded its 3-second wait: \(error); \(diagnostics())")
            throw error
        }
        XCTAssertNil(fixture.model.offlineCourseDownloadRoundIdForTesting)
        guard let template = try fixture.store.loadCourseTemplate(globalId: c85CourseId, teeBox: "blue") else {
            XCTFail("missing whole-course template (globalId=\(c85CourseId), teeBox=blue); \(diagnostics())")
            return
        }
        XCTAssertEqual(template.coursePrep?.holes.count, package.holes.count)
        XCTAssertTrue(template.coursePrep?.holes.allSatisfy {
            $0.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame
        } ?? false)
    }

    /// J4.2: a seal failure keeps the live round and its background downloads resumable.
    func testSealFailureKeepsRoundBackgroundWorkAlive() async throws {
        let rasterGate = C90RequestGate()
        let (fixture, package, _) = try await startRoundWithHeldBackgroundWork(
            host: "c90-seal-failure.example.test", roundId: "c90-seal-failure", rasterGate: rasterGate
        )
        // sealRoundForDeferredFinish writes packages/<round>.json before the current pointer,
        // home package, or either pending-finish ledger. Replacing that first destination with a
        // directory makes the first write fail deterministically, before seal changes any state.
        let roundPackageURL = fixture.directory
            .appendingPathComponent("packages", isDirectory: true)
            .appendingPathComponent("c90-seal-failure.json")
        try FileManager.default.removeItem(at: roundPackageURL)
        try FileManager.default.createDirectory(at: roundPackageURL, withIntermediateDirectories: true)
        let result = await fixture.model.finishActiveRound()
        XCTAssertFalse(result)
        XCTAssertEqual(fixture.model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(fixture.model.offlineCourseDownloadRoundIdForTesting, package.roundId)
        XCTAssertEqual(try fixture.store.loadCurrentRoundPackage()?.roundId, package.roundId)
        XCTAssertTrue(fixture.model.garminRasterDownloadTaskRunningForTesting)
        await rasterGate.release()
    }

    /// A first stroke starts a deferred map-only round even when the hole screen has not called
    /// `liveHoleInitialLoadDidFinish` yet. The player's first action must release the personal
    /// package fetch; waiting for a later view callback leaves the round without clubs/history.
    func testFirstStrokeReleasesDeferredPersonalPackage() async throws {
        let host = "c102-first-stroke.example.test"
        let roundId = "c102-first-stroke"
        let mapPackage = try package(roundId: roundId, mapOnly: true)
        let fullPackage = try package(roundId: roundId, mapOnly: false)
        let fullData = try JSONEncoder().encode(fullPackage)
        let fullSent = expectation(description: "personal package requested after first stroke")
        let fullSentOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            guard proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package",
                  c33Query(proto.request, "map_only") != "true" else {
                proto.reply(404)
                return
            }
            if fullSentOnce.claim() { fullSent.fulfill() }
            proto.reply(200, fullData)
        })
        let fixture = makeModel(host: host)
        let model = fixture.model
        model.enterPrepMode(with: mapPackage, hole: 1)

        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 1))
        await fulfillment(of: [fullSent], timeout: eventWait)
        await model.waitForRoundEnrichmentForTesting()
        XCTAssertFalse(model.package?.clubProfiles.isEmpty ?? true)
    }

    /// The fallback behind the hook: once a test has invalidated the client, a request fails with
    /// `CancellationError` instead of creating a task in the invalidated session (NSGenericException).
    func testAnInvalidatedClientRefusesRequestsBeforeTheSession() async throws {
        let host = "c85-invalidated.example.test"
        let requests = C85Counter()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.host == host { requests.increment() }
            proto.reply(404)
        })
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [C33URLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://\(host)")),
            session: session,
            retrySleep: { _ in }
        )
        client.invalidateForTesting()
        session.invalidateAndCancel()
        let loops = [RoundLoopEntry(globalId: c85CourseId, half: "front")]

        for foregroundStart in [false, true] {
            do {
                _ = try await client.fetchCoursePackage(
                    globalId: c85CourseId, roundId: "c85-invalidated", teeBox: "blue", loops: loops,
                    backgroundGeometry: true, foregroundStart: foregroundStart
                )
                XCTFail("an invalidated client answered (foregroundStart=\(foregroundStart))")
            } catch {
                XCTAssertTrue(error is CancellationError, "foregroundStart=\(foregroundStart): \(error)")
            }
        }
        XCTAssertEqual(requests.value, 0)
    }

    // MARK: - Helpers

    /// URLSession can deliver a request to URLProtocol after the model's cancellation hook returns.
    /// Drain running tasks before taking the stop counter snapshot so that delivery belongs to the
    /// pre-stop side of this test's boundary, rather than becoming a false late request.
    private func waitForNoRunningTasks(_ session: URLSession) async {
        let deadline = ProcessInfo.processInfo.systemUptime + 2
        while ProcessInfo.processInfo.systemUptime < deadline {
            let tasks: [URLSessionTask] = await withCheckedContinuation { continuation in
                session.getAllTasks { continuation.resume(returning: $0) }
            }
            if tasks.allSatisfy({ $0.state != .running && $0.state != .canceling }) { return }
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
    }

    private func startRoundWithHeldBackgroundWork(
        host: String,
        roundId: String,
        rasterGate: C90RequestGate? = nil,
        roundPackage: LiveRoundPackage? = nil
    ) async throws -> (fixture: ModelFixture, package: LiveRoundPackage, held: C85HeldRequests) {
        let package = try roundPackage ?? package(roundId: roundId, mapOnly: false, garminRasterVersion: "c90-r6")
        let data = try JSONEncoder().encode(package)
        let held = C85HeldRequests()
        let prepPath = "/api/v2/courses/\(c85CourseId)/prep"
        let prepData = try offlinePrepResponseData(for: package)
        let requestStarted = expectation(description: "round background request started")
        let requestOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            if proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package" {
                proto.reply(200, data)
            } else {
                if proto.request.url?.path == prepPath {
                    held.holdOrReplyAfterRelease(proto, status: 200, data: prepData)
                } else if proto.request.value(forHTTPHeaderField: "Accept")?.hasPrefix("image/") == true {
                    held.holdOrReplyAfterRelease(proto, status: 404)
                } else {
                    held.holdOrReplyAfterRelease(proto, status: 404)
                }
                if requestOnce.claim() { requestStarted.fulfill() }
            }
        }, onStop: { request in
            guard request.url?.host == host else { return }
            held.forget(request)
        })
        let fixture = makeModel(host: host, held: held)
        let rasterStarted = rasterGate.map { _ in expectation(description: "raster task held") }
        let rasterStartedOnce = C33FirstMatch()
        if let rasterGate {
            fixture.model.garminRasterDownloader = { _ in
                if rasterStartedOnce.claim() { rasterStarted?.fulfill() }
                await rasterGate.wait()
                return false
            }
        }
        await fixture.model.prepareCourseRound(
            roundId: roundId, teeBox: "blue", loops: package.loopEntries
        )
        fixture.model.liveHoleInitialLoadDidFinish()
        await fulfillment(of: [requestStarted], timeout: eventWait)
        if let rasterStarted {
            // The task handle must be live before finishActiveRound is called; otherwise a
            // cancellation mutant can hide behind URLProtocol's asynchronous stop callback.
            await fulfillment(of: [rasterStarted], timeout: eventWait)
        }
        return (fixture, package, held)
    }

    private func installStatusResponseData(for package: LiveRoundPackage) -> Data {
        let rows = package.holes.map { hole in
            """
            {"globalId":\(hole.sourceGlobalId),"localHole":\(hole.sourceLocalHole),"displayHole":\(hole.number),
             "geometry":"ready","geometryRevision":"c90-r9","topo":"ready",
             "topoRevision":"c90-r9","error":null}
            """
        }.joined(separator: ",")
        return Data("""
        {"schema":"ai-caddie-course-install-v1","jobId":"c90-r9",
         "globalId":\(package.course.globalId),"teeBox":"\(package.course.teeBox)","loopKey":"\(package.loopKey)",
         "phase":"ready","stage":"ready","totalHoles":\(package.holes.count),
         "geometryReady":\(package.holes.count),"topoReady":\(package.holes.count),
         "updatedAt":null,"error":null,"holes":[\(rows)]}
        """.utf8)
    }

    private func waitForOfflineCourseDownloadWithin(
        _ model: LiveRoundAppModel,
        timeout: TimeInterval = 3
    ) async throws {
        enum Timeout: Error { case exceeded }
        // A task-group race still joins its losing child: awaiting an unstructured model task's
        // value ignores that child's cancellation. Poll the completion marker with a real deadline.
        let deadline = ProcessInfo.processInfo.systemUptime + timeout
        while model.offlineCourseDownloadRoundIdForTesting != nil {
            guard ProcessInfo.processInfo.systemUptime < deadline else { throw Timeout.exceeded }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
    }

    private struct ModelFixture {
        let model: LiveRoundAppModel
        let store: OfflineStore
        let client: SyncClient
        let session: URLSession
        let directory: URL
        let held: C85HeldRequests?

        /// In this order (fixture run 40308301959 crashed the test process with "Task created in a
        /// session that has been invalidated"): stop the model's background work and wait for it;
        /// only then answer what is still held — answered earlier, a failure would be retried — and
        /// invalidate the sessions last.
        func tearDown() async {
            await model.stopRoundBackgroundWorkForTesting()
            held?.releaseAll(404)
            client.invalidateForTesting()
            session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
    }

    private func makeModel(host: String, held: C85HeldRequests? = nil) -> ModelFixture {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c85-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        // No per-host connection cap: a held request must not serialize the next one.
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [C33URLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = SyncClient(
            baseURL: URL(string: "https://\(host)")!,
            session: session,
            retrySleep: { _ in }
        )
        let model = c33Model(store, client)
        let fixture = ModelFixture(
            model: model, store: store, client: client, session: session, directory: directory, held: held
        )
        fixtures.append(fixture)
        return fixture
    }

    /// The shared front-nine fixture as the server would answer this round. `mapOnly` is the #426
    /// map package: same holes and route facts, personal enrichment deferred (no clubs, no seeds,
    /// `playerStatsWindow: deferred`, as `mobile_live.py` emits for `map_only=true`).
    private func package(
        roundId: String,
        mapOnly: Bool,
        garminRasterVersion: String? = nil,
        standalone: Bool = false
    ) throws -> LiveRoundPackage {
        var root = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: LiveRoundPackageFixture.url)) as? [String: Any]
        )
        root["roundId"] = roundId
        if standalone {
            root["dataMode"] = "local"
            root["roundLoops"] = [["globalId": c85CourseId, "half": "all", "roundStartHole": 1,
                                   "sourceStartHole": 1, "holeCount": 9]]
            root["loopKey"] = "\(c85CourseId):all"
        }
        var coverage = try XCTUnwrap(root["sourceCoverage"] as? [String: Any])
        coverage["requestedRoundId"] = roundId
        if standalone { coverage["dataMode"] = "local" }
        if mapOnly {
            coverage["playerStatsWindow"] = "deferred"
            root["clubProfiles"] = [] as [Any]
            root["caddieContextSeeds"] = [] as [Any]
            // #426's map-only answer has no personal history projection.
            root["recentHistory"] = ["course": ["courseKey": "fixture-links", "roundCount": 0,
                                               "recentScores": [Int](), "roundIds": [String]()] as [String: Any],
                                   "rounds": [[String: Any]](), "holes": [[String: Any]]()] as [String: Any]
        }
        root["sourceCoverage"] = coverage
        if let garminRasterVersion {
            var holes = try XCTUnwrap(root["holes"] as? [[String: Any]])
            for index in holes.indices {
                let local = try XCTUnwrap(holes[index]["sourceLocalHole"] as? Int)
                let base = "/api/v2/courses/\(c85CourseId)/holes/\(local)"
                holes[index]["garminRaster"] = [
                    "imageUrl": "\(base)/garmin-raster.jpg?v=\(garminRasterVersion)",
                    "metadataUrl": "\(base)/garmin-raster",
                ]
            }
            root["holes"] = holes
        }
        let decoded = try JSONDecoder().decode(
            LiveRoundPackage.self,
            from: JSONSerialization.data(withJSONObject: root)
        ).validatedRoundIdentity()
        XCTAssertEqual(decoded.holes.map(\.number), Array(1...9))
        if !mapOnly {
            XCTAssertFalse(decoded.clubProfiles.isEmpty)
            XCTAssertEqual(Set(decoded.caddieContextSeeds.map(\.hole)), Set(1...9))
        }
        return decoded
    }
}

private final class C85RequestLog {
    private let lock = NSLock()
    private var requests: [URLRequest] = []

    func append(_ request: URLRequest) {
        lock.lock(); requests.append(request); lock.unlock()
    }

    var all: [URLRequest] {
        lock.lock(); defer { lock.unlock() }
        return requests
    }
}

/// Responder evidence survives URLProtocol callbacks on different queues, including fallback 404s.
private final class C90ResponseLog {
    private let lock = NSLock()
    private var entries: [String] = []

    func append(_ request: URLRequest, status: Int, usedDefault: Bool) {
        let url = request.url
        let pathAndQuery = (url?.path ?? "<missing URL>") + (url?.query.map { "?\($0)" } ?? "")
        let entry = "\(request.httpMethod ?? "GET") \(pathAndQuery) -> \(status)\(usedDefault ? " (default)" : "")"
        lock.lock(); entries.append(entry); lock.unlock()
    }

    var all: [String] {
        lock.lock(); defer { lock.unlock() }
        return entries
    }
}

private final class C85Counter {
    private let lock = NSLock()
    private var count = 0

    @discardableResult
    func increment() -> Int {
        lock.lock(); defer { lock.unlock() }
        count += 1
        return count
    }

    func set(_ value: Int) {
        lock.lock(); count = value; lock.unlock()
    }

    var value: Int {
        lock.lock(); defer { lock.unlock() }
        return count
    }
}

/// Requests left unanswered until the test releases them.
private final class C85HeldRequests {
    private let lock = NSLock()
    private var held: [C33URLProtocol] = []
    private var replyFuture = false
    private var futureResponder: ((URLRequest) -> (status: Int, data: Data))?

    func hold(_ proto: C33URLProtocol) {
        lock.lock(); held.append(proto); lock.unlock()
    }

    func holdOrReplyAfterRelease(
        _ proto: C33URLProtocol,
        status: Int,
        data: Data = Data()
    ) {
        lock.lock()
        let released = replyFuture
        let responder = futureResponder
        if !released { held.append(proto) }
        lock.unlock()
        if released {
            let response = responder?(proto.request) ?? (status: status, data: data)
            proto.reply(response.status, response.data)
        }
    }

    /// A request URLSession stopped (cancelled) is never answered afterwards.
    func forget(_ request: URLRequest) {
        lock.lock()
        held.removeAll { $0.request.url == request.url }
        lock.unlock()
    }

    func releaseAll(_ status: Int, _ data: Data = Data()) {
        lock.lock()
        let released = held
        held.removeAll()
        lock.unlock()
        released.forEach { $0.reply(status, data) }
    }

    func releaseAllAndReplyFuture(
        _ status: Int,
        _ data: Data = Data(),
        onlyPath: String? = nil
    ) {
        lock.lock()
        replyFuture = true
        futureResponder = nil
        let released = held
        held.removeAll()
        lock.unlock()
        released.forEach { proto in
            if onlyPath == nil || proto.request.url?.path == onlyPath {
                proto.reply(status, data)
            } else {
                proto.reply(404)
            }
        }
    }

    func releaseAllAndReplyFuture(
        _ responder: @escaping (URLRequest) -> (status: Int, data: Data)
    ) {
        lock.lock()
        replyFuture = true
        futureResponder = responder
        let released = held
        held.removeAll()
        lock.unlock()
        released.forEach { proto in
            let response = responder(proto.request)
            proto.reply(response.status, response.data)
        }
    }

    /// Answers only the start's held package; any other held request stays held.
    func releaseStartPackage(path: String, data: Data) {
        lock.lock()
        let released = held.filter { $0.request.url?.path == path }
        held.removeAll { $0.request.url?.path == path }
        lock.unlock()
        released.forEach { $0.reply(200, data) }
    }
}

private final class C85DownloadLog {
    var urls: [URL] = []
}

private actor C90RequestGate {
    private var waiter: CheckedContinuation<Void, Never>?
    private var released = false

    func wait() async {
        if released { return }
        await withCheckedContinuation { continuation in
            if released {
                continuation.resume()
                return
            }
            waiter = continuation
        }
    }

    func release() {
        released = true
        waiter?.resume()
        waiter = nil
    }
}
#endif
