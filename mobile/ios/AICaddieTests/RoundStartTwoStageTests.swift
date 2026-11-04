#if !SWIFT_PACKAGE
import Combine
import Foundation
import XCTest
import UIKit
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

    override func tearDown() async throws {
        for fixture in fixtures {
            await fixture.tearDown()
        }
        fixtures.removeAll()
        C33URLProtocol.setHandlers(onStart: nil)
        try await super.tearDown()
    }

    /// J4.2: establish the foreground gate before enqueueing the durable whole-course download.
    func testPrepStartDoesNotCreateAndImmediatelyCancelADownloadWorker() throws {
        C33URLProtocol.setHandlers(onStart: { $0.reply(404) })
        let fixture = makeModel(host: "prep-start-order.example.test")
        let model = fixture.model
        let course = MobileCourseOption(globalId: c85CourseId, name: "Fixture Links", holes: 9, teeBox: "blue")
        XCTAssertTrue(model.openPrepCourse(course))
        // Synchronous before any actor yield: a worker created then cancelled is still a bug,
        // even if its URL request never reached the transport.
        XCTAssertEqual(model.prepWorkerStartsForTesting, 0)
        XCTAssertEqual(model.prepWorkerCancellationsForTesting, 0)
        XCTAssertEqual(model.prepCourseDownloads.first { !$0.isIntentPrefetch }?.phase, .queued)
        XCTAssertEqual(try fixture.store.loadPrepCourseDownloads().filter { !$0.isIntentPrefetch }.count, 1)
    }

    /// J4.2: an explicit repeated request attaches to the held task and immediately changes copy.
    func testActiveOfflineDownloadRequestShowsFeedbackWithoutRestarting() async throws {
        let host = "prep-active-feedback.example.test"
        let held = C85HeldRequests()
        let sent = expectation(description: "whole-course download is active")
        let once = C33FirstMatch()
        let requests = C85RequestLog()
        C33URLProtocol.setHandlers(onStart: { proto in
            requests.append(proto.request)
            held.hold(proto)
            if once.claim() { sent.fulfill() }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        let course = MobileCourseOption(globalId: c85CourseId, name: "Fixture Links", holes: 9, teeBox: "blue")
        model.downloadPrepCourse(course)
        await fulfillment(of: [sent], timeout: eventWait)
        model.downloadPrepCourse(course)
        let row = try XCTUnwrap(model.prepCourseDownloads.first)
        XCTAssertEqual(StartRoundPresentation.offlineStatusText(row), "正在下载，已在进行")
        XCTAssertNil(StartRoundPresentation.offlineActionTitle(row))
        XCTAssertEqual(model.prepWorkerStartsForTesting, 1)
        XCTAssertEqual(model.prepWorkerCancellationsForTesting, 0)
        XCTAssertEqual(requests.all.count, 1)
        XCTAssertEqual(row.downloadedHoles, 0)
    }

    func testMapOnlyPackageRequestCarriesTheWatchContract() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(CapturingURLProtocol.self)
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
        let bitmap = try garminTestBitmap()
        model.garminRasterDownloader = { url in
            downloads.urls.append(url)
            GarminRasterImageStore.cacheForTesting(bitmap, for: url)
            return true
        }
        // The package's own URLs, version query included (C88 adds `?v=`); never rebuilt locally.
        func raster(_ hole: Int) -> URL {
            URL(string: "https://\(host)/api/v2/courses/\(c85CourseId)/holes/\(hole)/garmin-raster.jpg?v=c85-r1")!
        }

        defer { (1...9).map(raster).forEach { GarminRasterImageStore.removeDiskEntryForTesting($0) } }
        (1...9).map(raster).forEach { GarminRasterImageStore.removeDiskEntryForTesting($0) }
        await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: roundPackage.loopEntries)
        XCTAssertEqual(model.pendingLiveHole, 1)
        await model.waitForGarminRasterDownloadForTesting()
        XCTAssertEqual(downloads.urls, (1...9).map(raster), "every hole, in play order from the first tee")

        // J4.5: the player moves to hole 6; the next pass must skip all nine durable images.
        downloads.urls.removeAll()
        model.setActiveHole(6)
        await model.waitForGarminRasterDownloadForTesting()
        XCTAssertEqual(downloads.urls, [], "J4.5 moving holes must not redownload cached Garmin bitmaps")
        await model.waitForOfflineCourseDownloadForTesting()
    }

    /// J4.5: a held package cannot stop a personal template whose Garmin bitmaps are already local.
    /// The injected clock advances the production deadline by exactly 30 seconds without a sleep.
    func testJ45HeldPackageEntersOnDiskGarminFromLocalTemplate() async throws {
        let host = "garmin-local-\(UUID().uuidString).example.test"
        let roundId = "garmin-local-round"
        let template = try package(
            roundId: "garmin-local-template", mapOnly: false,
            garminRasterVersion: "local-v1", standalone: true, offlineState: "ready"
        )
        let expectedURLs = (1...9).map {
            URL(string: "https://\(host)/api/v2/courses/\(c85CourseId)/holes/\($0)/garmin-raster.jpg?v=local-v1")!
        }
        let imageData = try garminTestBitmap()
        for url in expectedURLs { GarminRasterImageStore.cacheForTesting(imageData, for: url) }
        defer { expectedURLs.forEach { GarminRasterImageStore.removeDiskEntryForTesting($0) } }
        let held = C85HeldRequests()
        let requestGate = C90RequestGate()
        let clock = C367StartClock()
        let requests = C85RequestLog()
        C33URLProtocol.setHandlers(onStart: { proto in
            requests.append(proto.request)
            held.hold(proto) // Never answer the package, including after the deadline.
            Task { await requestGate.release() }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held, roundStartNow: { clock.now })
        fixture.client.roundStartDeadlineSleep = { nanoseconds in
            await requestGate.wait()
            clock.advance(by: Double(nanoseconds) / 1_000_000_000)
        }
        try fixture.store.saveCourseTemplate(template)
        let downloads = C85DownloadLog()
        fixture.model.garminRasterDownloader = { url in downloads.urls.append(url); return false }
        await fixture.model.prepareCourseRound(
            roundId: roundId, teeBox: "blue", loops: template.loopEntries
        )
        XCTAssertEqual(clock.elapsed, 30, accuracy: 1, "J4.5 the held package uses the 30-second fallback")
        XCTAssertEqual(requests.all.filter { $0.url?.path.hasSuffix("/package") == true }.count, 1)
        XCTAssertEqual(fixture.model.pendingLiveHole, 1, "J4.5 enter from the local Garmin template")
        let entered = try XCTUnwrap(fixture.model.package)
        XCTAssertEqual(entered.holes.first?.garminRaster?.imageUrl,
                       "/api/v2/courses/31795/holes/1/garmin-raster.jpg?v=local-v1",
                       "J4.5 projected entry keeps the template's exact Garmin URL")
        XCTAssertEqual(LiveRoundAppModel.garminRasterURLsInPlayOrder(
            entered, activeHole: 1, baseURL: fixture.client.baseURL
        ), expectedURLs, "J4.5 entry enumerates every cached physical hole")
        await fixture.model.waitForGarminRasterDownloadForTesting()
        XCTAssertTrue(downloads.urls.isEmpty, "J4.5 already-on-disk rasters never invoke the downloader")
        let imageStore = GarminRasterImageStore(sleep: { _ in throw CancellationError() })
        await imageStore.load(expectedURLs[0])
        XCTAssertNotNil(imageStore.image, "J4.5 bitmap is decoded from the disk cache")
        let view = CurrentHoleView(package: entered, hole: try XCTUnwrap(entered.holes.first),
                                   caddieBaseURL: fixture.client.baseURL, offlineStore: fixture.store)
        XCTAssertEqual(view.liveMapDisplayStateForTesting(), .garminRaster,
                       "J4.5 local template entry displays Garmin while the package never answers")
        fixture.model.setActiveHole(2)
        await fixture.model.waitForGarminRasterDownloadForTesting()
        XCTAssertTrue(downloads.urls.isEmpty, "J4.5 a later entry pass skips the same disk images")
    }

    /// J4.5: the saved template's image task is independent of the prep queue's next held package.
    func testJ45SavedTemplateRastersDoNotWaitForAnotherCoursePackage() async throws {
        let host = "template-lane-\(UUID().uuidString).example.test"
        let template = try package(roundId: "template-lane", mapOnly: false,
                                   garminRasterVersion: "saved-v1", standalone: true, offlineState: "ready")
        let data = try JSONEncoder().encode(template)
        let held = C85HeldRequests()
        let nextSent = expectation(description: "another course package never answers")
        let once = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path == "/api/v2/mobile/courses/31796/package" {
                held.hold(proto)
                if once.claim() { nextSent.fulfill() }
            } else if proto.request.url?.path == "/api/v2/mobile/courses/31795/package" {
                proto.reply(200, data)
            } else { proto.reply(404) }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held)
        let firstImage = expectation(description: "saved template begins its independent raster lane")
        let gate = C90RequestGate()
        let downloads = C85DownloadLog()
        fixture.model.garminRasterDownloader = { url in
            downloads.urls.append(url)
            if downloads.urls.count == 1 { firstImage.fulfill(); await gate.wait() }
            return true
        }
        fixture.model.downloadPrepCourse(.init(globalId: c85CourseId, name: "Saved", holes: 9, teeBox: "blue"))
        await fulfillment(of: [firstImage], timeout: eventWait)
        XCTAssertNotNil(try fixture.store.loadCourseTemplate(globalId: c85CourseId, teeBox: "blue"))
        fixture.model.downloadPrepCourse(.init(globalId: 31796, name: "Held", holes: 9, teeBox: "blue"))
        await fulfillment(of: [nextSent], timeout: eventWait)
        await gate.release()
        await fixture.model.waitForGarminRasterDownloadForTesting()
        let expected = (1...9).map {
            URL(string: "https://\(host)/api/v2/courses/31795/holes/\($0)/garmin-raster.jpg?v=saved-v1")!
        }
        XCTAssertEqual(downloads.urls, expected,
                       "J4.5 all saved-template Garmin images finish while the next package stays held")
    }

    /// J4.5: Start may pause prep but cannot cancel a Garmin image or discard another queued template.
    func testJ45GarminQueueSurvivesStartAndRetainsNextTemplate() async throws {
        let host = "serial-lane-\(UUID().uuidString).example.test"
        C33URLProtocol.setHandlers(onStart: { $0.reply(404) })
        let fixture = makeModel(host: host)
        let first = try package(roundId: "serial-blue", mapOnly: false,
                                garminRasterVersion: "blue-v1", standalone: true, offlineState: "ready")
        let next = try package(roundId: "serial-white", mapOnly: false,
                               garminRasterVersion: "white-v1", standalone: true, offlineState: "ready")
            .replacingCourseTeeBox("white")
        try fixture.store.saveCourseTemplate(first)
        try fixture.store.saveCourseTemplate(next)
        let started = expectation(description: "first Garmin held")
        let gate = C90RequestGate()
        let downloads = C85DownloadLog()
        var running = 0
        var maximumRunning = 0
        fixture.model.garminRasterDownloader = { url in
            running += 1
            maximumRunning = max(maximumRunning, running)
            downloads.urls.append(url)
            if downloads.urls.count == 1 { started.fulfill(); await gate.wait() }
            running -= 1
            return true
        }
        let course = MobileCourseOption(globalId: c85CourseId, name: "Serial", holes: 9, teeBox: "blue")
        fixture.model.prefetchIntendedCourses([course], teeBox: "blue")
        await fulfillment(of: [started], timeout: eventWait)
        let token = fixture.model.beginRoundPreparationForTesting()
        fixture.model.prefetchIntendedCourses([course], teeBox: "white")
        XCTAssertTrue(fixture.model.isPreparingRound)
        await gate.release()
        await fixture.model.waitForGarminRasterDownloadForTesting()
        let expected = ["blue-v1", "white-v1"].flatMap { version in
            (1...9).map { URL(string: "https://\(host)/api/v2/courses/31795/holes/\($0)/garmin-raster.jpg?v=\(version)")! }
        }
        XCTAssertEqual(downloads.urls, expected, "J4.5 Start preserves both Garmin passes without dropping URLs")
        XCTAssertEqual(maximumRunning, 1, "J4.5 only one Garmin downloader runs at a time")
        fixture.model.finishRoundPreparationForTesting(token)
    }

    /// J4.5/C158: genuinely saved speculative templates do not spend traffic on Garmin rasters.
    func testJ45SpeculativeTemplateDoesNotDownloadGarmin() async throws {
        let host = "speculative-raster.example.test"
        let template = try package(roundId: "speculative-raster", mapOnly: false,
                                   garminRasterVersion: "spec-v1", standalone: true, offlineState: "ready")
        let body = try JSONEncoder().encode(template)
        let packageSent = expectation(description: "speculative package fetched")
        let once = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path.hasSuffix("/package") == true {
                if once.claim() { packageSent.fulfill() }
                proto.reply(200, body)
            } else { proto.reply(404) }
        })
        let course = MobileCourseOption(globalId: c85CourseId, name: "Guess", holes: 9, teeBox: "blue")
        let fixture = makeModel(host: host, prepDownloadRecords: [
            PrepCourseDownloadRecord(course: course, teeBox: "blue", isSpeculative: true)
        ])
        let downloads = C85DownloadLog()
        fixture.model.garminRasterDownloader = { url in downloads.urls.append(url); return true }
        fixture.model.publishOfflineStorageUsageForTesting(.init(topoBytes: 0, templateBytes: 0))
        fixture.model.setNetworkStateForTesting(.init(isSatisfied: true, isExpensive: false, isConstrained: false))
        await fulfillment(of: [packageSent], timeout: eventWait)
        await fixture.model.waitForPrepCourseDownloadForTesting()
        await fixture.model.waitForGarminRasterDownloadForTesting()
        XCTAssertNotNil(try fixture.store.loadCourseTemplate(globalId: c85CourseId, teeBox: "blue"),
                        "J4.5 the speculative template was actually saved")
        XCTAssertTrue(downloads.urls.isEmpty, "J4.5 speculative templates must not fetch Garmin images")
    }

    private func garminTestBitmap() throws -> Data {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 2, height: 2)).image { context in
            UIColor.green.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 2, height: 2))
        }
        return try XCTUnwrap(image.pngData())
    }

    /// J4.5: an offline projection keeps the physical hole's Garmin descriptor so a local start
    /// can display the cached fallback while the remote package is unavailable.
    func testJ45OfflineProjectionRetainsGarminDescriptor() throws {
        let template = try package(
            roundId: "c369-template",
            mapOnly: false,
            garminRasterVersion: "c369-r1"
        )
        let projected = try XCTUnwrap(LiveRoundPackage.projecting(
            [RoundLoopEntry(globalId: c85CourseId, half: "front")],
            templates: [c85CourseId: template],
            roundId: "c369-offline"
        ))
        XCTAssertEqual(
            projected.holes.first?.garminRaster?.imageUrl,
            template.holes.first?.garminRaster?.imageUrl,
            "J4.5 offline projection preserves the Garmin URL for the physical hole"
        )
    }

    /// J4.2: overlapping course lookups retain each course's own failure cause.
    func testJ42ConcurrentTeeFailuresRemainScopedToTheirCourse() async {
        let held = C85HeldRequests()
        let firstSent = expectation(description: "first course tees held")
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path == "/api/v2/courses/31795/tees" {
                held.hold(proto)
                firstSent.fulfill()
            } else {
                proto.client?.urlProtocol(proto, didFailWithError: URLError(.timedOut))
            }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: "tee-failures.example.test", held: held)
        let first = Task { await fixture.model.loadCourseTees(globalId: 31795) }
        await fulfillment(of: [firstSent], timeout: eventWait)
        let secondRows = await fixture.model.loadCourseTees(globalId: 31796)
        XCTAssertTrue(secondRows.isEmpty)
        held.releaseAll(400)
        let firstRows = await first.value
        XCTAssertTrue(firstRows.isEmpty)
        XCTAssertEqual(fixture.model.courseTeesFailures[31795], .unavailable)
        XCTAssertEqual(fixture.model.courseTeesFailures[31796], .timedOut,
                       "a later failure from another course cannot replace this course's timeout")
    }

    /// J4.2/W2: 25 seconds spent on an intent leaves exactly five of the single 30-second
    /// foreground budget. The fallback transport never answers; only its deadline can end Start.
    func testJ42IntentFailureAndHeldFallbackShareThirtySecondDeadline() async throws {
        let clock = C367StartClock()
        let held = C85HeldRequests()
        let intentSent = expectation(description: "intent held")
        let fallbackSent = expectation(description: "fallback held forever")
        let fallbackGate = C90RequestGate()
        let once = C33FirstMatch()
        let requests = C85RequestLog()
        C33URLProtocol.setHandlers(onStart: { proto in
            requests.append(proto.request)
            held.hold(proto)
            if once.claim() { intentSent.fulfill() } else { fallbackSent.fulfill(); Task { await fallbackGate.release() } }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: "start-budget.example.test", held: held, roundStartNow: { clock.now })
        fixture.client.roundStartDeadlineSleep = { nanoseconds in
            await fallbackGate.wait()
            clock.advance(by: Double(nanoseconds) / 1_000_000_000)
        }
        let model = fixture.model
        let course = MobileCourseOption(globalId: c85CourseId, name: "Intent nine", holes: 9, teeBox: "blue")
        model.prefetchIntendedCourses([course], teeBox: "blue")
        await fulfillment(of: [intentSent], timeout: eventWait)
        model.roundStartIntentWaitDidBeginForTesting = {
            clock.advance(by: 25)
            // A permanent intent error at controlled t=25; no transport retry.
            held.releaseAll(400)
        }
        await model.prepareCourseRound(
            roundId: "shared-deadline", teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "front")]
        )
        await fulfillment(of: [fallbackSent], timeout: eventWait)
        XCTAssertEqual(requests.all.count, 2)
        XCTAssertEqual(model.roundStartFailure, .timedOut)
        // J4.2 promises 30 s from Start, tolerance at most 1 s (not 25 + another 30).
        XCTAssertEqual(clock.elapsed, 30, accuracy: 1, "J4.2: intent and fallback share the tap-time deadline")
        XCTAssertNil(model.pendingLiveHole)
    }

    /// J4.2/W2 (default 开始 → 备战 path): the same single 30-second budget as a loop start.
    /// The fallback transport never answers; only its deadline can end Start.
    func testJ42PrepStartIntentFailureAndHeldFallbackShareThirtySecondDeadline() async throws {
        let clock = C367StartClock()
        let held = C85HeldRequests()
        let intentSent = expectation(description: "intent held")
        let fallbackSent = expectation(description: "fallback held forever")
        fallbackSent.assertForOverFulfill = false
        let fallbackGate = C90RequestGate()
        let once = C33FirstMatch()
        let requests = C85RequestLog()
        C33URLProtocol.setHandlers(onStart: { proto in
            requests.append(proto.request)
            held.hold(proto)
            if once.claim() { intentSent.fulfill() } else { fallbackSent.fulfill(); Task { await fallbackGate.release() } }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: "prep-start-budget.example.test", held: held, roundStartNow: { clock.now })
        fixture.client.roundStartDeadlineSleep = { nanoseconds in
            await fallbackGate.wait()
            clock.advance(by: Double(nanoseconds) / 1_000_000_000)
        }
        let model = fixture.model
        let course = MobileCourseOption(globalId: c85CourseId, name: "Intent nine", holes: 9, teeBox: "blue")
        model.prefetchIntendedCourses([course], teeBox: "blue")
        await fulfillment(of: [intentSent], timeout: eventWait)
        model.roundStartIntentWaitDidBeginForTesting = {
            clock.advance(by: 25)
            // A permanent intent error at controlled t=25; no transport retry.
            held.releaseAll(400)
        }
        XCTAssertTrue(model.openPrepCourse(course))
        await model.activeRoundStartTaskForTesting?.value
        await fulfillment(of: [fallbackSent], timeout: eventWait)
        // Intent + fallback; once Start fails the durable prep download may add its own request.
        XCTAssertGreaterThanOrEqual(requests.all.count, 2)
        XCTAssertEqual(model.roundStartFailure, .timedOut)
        // J4.2 promises 30 s from Start, tolerance at most 1 s (not 25 + another 30).
        XCTAssertEqual(clock.elapsed, 30, accuracy: 1, "J4.2: intent and fallback share the tap-time deadline")
        XCTAssertNil(model.pendingLiveHole)
    }

    func testCompletedCourseIntentIsReusedByStart() async throws {
        let host = "c85-intent-complete.example.test"
        let roundId = "c85-intent-complete"
        let intentId = c85CourseId
        let mapPackage = try package(roundId: roundId, mapOnly: true, garminRasterVersion: "c85-r1", eighteenHoles: true)
        let mapData = try JSONEncoder().encode(mapPackage)
        let requests = C85RequestLog()
        let intentSent = expectation(description: "intent package sent")
        let intentSentOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path.hasSuffix("/package") == true else { proto.reply(404); return }
            requests.append(proto.request)
            if c33Query(proto.request, "map_only") == "true" {
                if intentSentOnce.claim() { intentSent.fulfill() }
                proto.reply(200, mapData)
            } else {
                proto.reply(404)
            }
        })
        let fixture = makeModel(host: host)
        let model = fixture.model
        let intent = MobileCourseOption(globalId: intentId, name: "Intent eighteen", holes: 18, teeBox: "blue")
        let rasterURLs = C85DownloadLog()
        model.garminRasterDownloader = { url in
            rasterURLs.urls.append(url)
            return true
        }

        model.prefetchIntendedCourses([intent], teeBox: "blue", startHole: 10)
        await fulfillment(of: [intentSent], timeout: eventWait)
        await model.waitForPrepCourseDownloadForTesting()
        await model.waitForGarminRasterDownloadForTesting()
        let expectedRasters = [10, 11, 12, 13, 14, 15, 16, 17, 18, 1, 2, 3, 4, 5, 6, 7, 8, 9].map { hole in
            URL(string: "https://\(host)/api/v2/courses/\(c85CourseId)/holes/\(hole)/garmin-raster.jpg?v=c85-r1")!
        }
        XCTAssertEqual(rasterURLs.urls, expectedRasters, "J4.5 intent prefetch warms every hole in play order")
        XCTAssertNil(model.pendingLiveHole, "J4.5 all Garmin requests precede Start")
        await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)

        let mapRequests = requests.all.filter { c33Query($0, "map_only") == "true" }
        XCTAssertEqual(mapRequests.count, 1, "Start reuses the completed intent package")
        XCTAssertEqual(model.pendingLiveHole, 1)
    }

    func testInFlightCourseIntentIsAwaitedByStartWithoutDuplicate() async throws {
        let host = "c85-intent-flight.example.test"
        let roundId = "c85-intent-flight"
        let intentId = c85CourseId
        let mapPackage = try package(roundId: roundId, mapOnly: true)
        let mapData = try JSONEncoder().encode(mapPackage)
        let held = C85HeldRequests()
        let requests = C85RequestLog()
        let intentSent = expectation(description: "intent package sent")
        let intentSentOnce = C33FirstMatch()
        let intentStopped = expectation(description: "in-flight intent remains active until release")
        intentStopped.isInverted = true
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path.hasSuffix("/package") == true else { proto.reply(404); return }
            requests.append(proto.request)
            held.hold(proto)
            if intentSentOnce.claim() { intentSent.fulfill() }
        }, onStop: { request in
            held.forget(request)
            if request.url?.path.hasSuffix("/package") == true { intentStopped.fulfill() }
        })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        let intent = MobileCourseOption(globalId: intentId, name: "Intent nine", holes: 9, teeBox: "blue")

        model.prefetchIntendedCourses([intent], teeBox: "blue")
        await fulfillment(of: [intentSent], timeout: eventWait)
        let start = Task {
            await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)
        }
        try await Task.sleep(nanoseconds: 50_000_000)
        let mapRequestsBeforeRelease = requests.all.filter { c33Query($0, "map_only") == "true" }
        XCTAssertEqual(mapRequestsBeforeRelease.count, 1, "Start waits for the in-flight intent instead of sending another map package")
        await fulfillment(of: [intentStopped], timeout: 0.1)
        held.releaseAll(200, mapData)
        await start.value

        let mapRequests = requests.all.filter { c33Query($0, "map_only") == "true" }
        XCTAssertEqual(mapRequests.count, 1)
        XCTAssertEqual(model.pendingLiveHole, 1)
    }

    func testInFlightCourseIntentTimesOutWithinTheForegroundBudget() async throws {
        let host = "c85-intent-timeout.example.test"
        let roundId = "c85-intent-timeout"
        let intentId = c85CourseId
        let mapPackage = try package(roundId: roundId, mapOnly: true)
        let held = C85HeldRequests()
        let requests = C85RequestLog()
        let intentSent = expectation(description: "intent package sent")
        let intentSentOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path.hasSuffix("/package") == true else { proto.reply(404); return }
            requests.append(proto.request)
            if requests.all.filter({ c33Query($0, "map_only") == "true" }).count == 1 {
                held.hold(proto)
                if intentSentOnce.claim() { intentSent.fulfill() }
            } else {
                // If the budget mutant keeps waiting, let teardown finish the retry ladder
                // after the bounded test wait instead of leaving a URLSession task alive.
                proto.reply(503)
            }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held, roundStartIntentWaitNanoseconds: 50_000_000)
        let model = fixture.model
        let intent = MobileCourseOption(globalId: intentId, name: "Intent nine", holes: 9, teeBox: "blue")

        model.prefetchIntendedCourses([intent], teeBox: "blue")
        await fulfillment(of: [intentSent], timeout: eventWait)
        let startFinished = expectation(description: "foreground start finishes within its intent budget")
        let startFinishedFlag = C85Counter()
        let start = Task {
            await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)
            startFinishedFlag.set(1)
            startFinished.fulfill()
        }
        await fulfillment(of: [startFinished], timeout: 2)
        if startFinishedFlag.value == 0 {
            // The wait-budget mutant leaves the first request held. Release it and answer
            // retries so this mutant produces a bounded test failure instead of hanging the job.
            held.releaseAll(503)
            await start.value
            return
        }
        XCTAssertEqual(model.roundStartFailure, .timedOut)
        XCTAssertNil(model.pendingLiveHole)
        XCTAssertEqual(
            requests.all.filter { c33Query($0, "map_only") == "true" }.count,
            1,
            "timeout ends only the foreground wait and does not issue a duplicate map request"
        )
    }

    /// J4.2: closing a Start that awaits shared intent ends its waiter before the producer answers.
    func testClosingPrepCancelsTheIntentWaitBeforeTheProducerReturns() async throws {
        let host = "intent-close.example.test"
        let held = C85HeldRequests()
        let requests = C85RequestLog()
        let intentSent = expectation(description: "shared intent producer is held")
        let sentOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path.hasSuffix("/package") == true else { proto.reply(404); return }
            requests.append(proto.request)
            held.hold(proto)
            if sentOnce.claim() { intentSent.fulfill() }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        let course = MobileCourseOption(globalId: c85CourseId, name: "Intent nine", holes: 9, teeBox: "blue")
        model.prefetchIntendedCourses([course], teeBox: "blue")
        await fulfillment(of: [intentSent], timeout: eventWait)
        let waiterEntered = expectation(description: "Start is awaiting the held producer")
        model.roundStartIntentWaitDidBeginForTesting = { waiterEntered.fulfill() }
        XCTAssertTrue(model.openPrepCourse(course))
        let oldStart = try XCTUnwrap(model.activeRoundStartTaskForTesting)
        await fulfillment(of: [waiterEntered], timeout: eventWait)
        model.roundStartIntentWaitDidBeginForTesting = nil

        let oldStartReturned = expectation(description: "cancelled Start returns while intent remains held")
        let returned = C85Counter()
        let observer = Task {
            await oldStart.value
            returned.set(1)
            oldStartReturned.fulfill()
        }
        model.closePrepMode()
        await fulfillment(of: [oldStartReturned], timeout: 2)
        XCTAssertEqual(returned.value, 1, "onCancel must finish the old waiter without the 30-second timer")
        XCTAssertEqual(requests.all.count, 1, "cancelling a waiter does not issue another package request")
        XCTAssertFalse(model.isOpeningPrepCourse)
        // Always release after the bounded assertion, including on the onCancel-noop mutant.
        // The held producer may retry a 503; subsequent requests must answer immediately.
        C33URLProtocol.setHandlers(onStart: { $0.reply(503) }, onStop: { held.forget($0) })
        held.releaseAll(503)
        await observer.value
    }

    func testOtherCourseIntentIsPausedWhenStartTakesTheNetwork() async throws {
        let host = "c85-intent-other.example.test"
        let roundId = "c85-intent-other"
        let otherCourseId = 31796
        let mapPackage = try package(roundId: roundId, mapOnly: true)
        let mapData = try JSONEncoder().encode(mapPackage)
        let held = C85HeldRequests()
        let requests = C85RequestLog()
        let intentStarted = expectation(description: "other course intent started")
        let intentStopped = expectation(description: "other course intent stopped")
        let startSent = expectation(description: "foreground start sent")
        let intentStartedOnce = C33FirstMatch()
        let intentStoppedOnce = C33FirstMatch()
        let startSentOnce = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  (proto.request.url?.path == "/api/v2/mobile/courses/\(otherCourseId)/package"
                    || proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package") else {
                proto.reply(404); return
            }
            requests.append(proto.request)
            let roundID = c33Query(proto.request, "round_id") ?? ""
            if roundID == "prep-library-\(otherCourseId)" {
                held.hold(proto)
                if intentStartedOnce.claim() { intentStarted.fulfill() }
                return
            }
            guard c33Query(proto.request, "map_only") == "true" else {
                proto.reply(404); return
            }
            if startSentOnce.claim() { startSent.fulfill() }
            proto.reply(200, mapData)
        }, onStop: { request in
            held.forget(request)
            let roundID = c33Query(request, "round_id") ?? ""
            if roundID == "prep-library-\(otherCourseId)", intentStoppedOnce.claim() {
                intentStopped.fulfill()
            }
        })
        let fixture = makeModel(host: host, held: held)
        let model = fixture.model
        let other = MobileCourseOption(globalId: otherCourseId, name: "Other", holes: 9, teeBox: "blue")

        model.prefetchIntendedCourses([other], teeBox: "blue")
        await fulfillment(of: [intentStarted], timeout: eventWait)
        await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: mapPackage.loopEntries)
        await fulfillment(of: [intentStopped, startSent], timeout: eventWait)

        let intentRequests = requests.all.filter { c33Query($0, "round_id") == "prep-library-\(otherCourseId)" }
        XCTAssertEqual(intentRequests.count, 1)
        XCTAssertEqual(model.pendingLiveHole, 1)
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

    /// J4.2 / C365-A1: cancelling a foreground start must drop a package that answers after the
    /// cancel tap. The held URLProtocol deliberately still replies after URLSession cancellation so
    /// this catches a missing preparation-generation invalidation, rather than only transport stop.
    func testC365CancelDropsLateCoursePackageAndDoesNotNavigate() async throws {
        let host = "c365-cancel.example.test"
        let roundId = "c365-cancel"
        let map = try package(roundId: roundId, mapOnly: true)
        let data = try JSONEncoder().encode(map)
        let held = C85HeldRequests()
        let sent = expectation(description: "foreground package held")
        let afterFetch = expectation(description: "package answered before cancellation boundary")
        let releaseAfterFetch = C90RequestGate()
        let requests = C85RequestLog()
        let once = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            requests.append(proto.request)
            held.hold(proto)
            if once.claim() { sent.fulfill() }
        })
        let fixture = makeModel(host: host, held: held, roundStartTimeoutInterval: 2)
        let model = fixture.model
        model.roundStartAfterFetchForTesting = {
            afterFetch.fulfill()
            await releaseAfterFetch.wait()
        }
        model.startCourseRound(
            roundId: roundId, teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )
        let start = try XCTUnwrap(model.activeRoundStartTaskForTesting)
        await fulfillment(of: [sent], timeout: eventWait)

        held.releaseAll(200, data)
        await fulfillment(of: [afterFetch], timeout: eventWait)
        model.cancelRoundStart()
        await releaseAfterFetch.release()
        await start.value

        XCTAssertNil(model.pendingLiveHole, "a late package must not publish a hole after cancel")
        XCTAssertNil(model.liveRoundState, "cancelled start must not activate a round")
        XCTAssertFalse(model.isPreparingRound)
        XCTAssertEqual(requests.all.count, 1, "cancel must not issue a replacement start request")
    }

    /// J4.2 / C365-A2: returning from setup to the course list uses the same cancellation boundary as
    /// the explicit button. This model call is the callback wired by StartRoundView's 返回 action.
    func testC365ReturningToCourseListDropsLateCoursePackage() async throws {
        let host = "c365-return.example.test"
        let roundId = "c365-return"
        let map = try package(roundId: roundId, mapOnly: true)
        let data = try JSONEncoder().encode(map)
        let held = C85HeldRequests()
        let sent = expectation(description: "foreground package held")
        let afterFetch = expectation(description: "package answered before return boundary")
        let releaseAfterFetch = C90RequestGate()
        let once = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            held.hold(proto)
            if once.claim() { sent.fulfill() }
        })
        let fixture = makeModel(host: host, held: held, roundStartTimeoutInterval: 2)
        let model = fixture.model
        model.roundStartAfterFetchForTesting = {
            afterFetch.fulfill()
            await releaseAfterFetch.wait()
        }
        model.startCourseRound(
            roundId: roundId, teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )
        let start = try XCTUnwrap(model.activeRoundStartTaskForTesting)
        await fulfillment(of: [sent], timeout: eventWait)

        // StartRoundView invokes this callback before changing page to .course.
        held.releaseAll(200, data)
        await fulfillment(of: [afterFetch], timeout: eventWait)
        model.cancelRoundStart()
        await releaseAfterFetch.release()
        await start.value

        XCTAssertNil(model.pendingLiveHole)
        XCTAssertNil(model.liveRoundState)
        XCTAssertFalse(model.isPreparingRound)
    }

    /// C365-N6: the first half-second of a new Start belongs to the tap transition, so a second
    /// tap cannot immediately cancel the operation it just created.
    func testC365ImmediateSecondCancelIsIgnoredDuringStartTransition() async throws {
        let host = "c365-double-tap.example.test"
        let held = C85HeldRequests()
        let sent = expectation(description: "start request held")
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            held.hold(proto)
            sent.fulfill()
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held, roundStartTimeoutInterval: 2)
        let model = fixture.model
        model.startCourseRound(
            roundId: "c365-double-tap", teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )
        let deadline = ProcessInfo.processInfo.systemUptime + 1
        while !model.isPreparingRound {
            guard ProcessInfo.processInfo.systemUptime < deadline else { throw NSError(domain: "C365", code: 1) }
            await Task.yield()
        }
        await fulfillment(of: [sent], timeout: eventWait)
        model.cancelRoundStartIfReady()
        XCTAssertTrue(model.isPreparingRound, "the transition guard must ignore an immediate second tap")
        held.releaseAll(200)
    }

    /// J4.2 / C365-N1: a setup exit uses the immediate cancellation callback, so returning right
    /// after Start (inside the 0.5 s primary-button window) still drops the operation.
    func testC365ImmediateSetupExitCancelsStartDuringTransition() async throws {
        let host = "c365-immediate-exit.example.test"
        let held = C85HeldRequests()
        let sent = expectation(description: "start request held")
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            held.hold(proto)
            sent.fulfill()
        }, onStop: { held.forget($0) })
        let fixture = makeModel(host: host, held: held, roundStartTimeoutInterval: 2)
        let model = fixture.model
        model.startCourseRound(
            roundId: "c365-immediate-exit", teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )
        let deadline = ProcessInfo.processInfo.systemUptime + 1
        while !model.isPreparingRound {
            guard ProcessInfo.processInfo.systemUptime < deadline else { throw NSError(domain: "C365", code: 2) }
            await Task.yield()
        }
        await fulfillment(of: [sent], timeout: eventWait)
        model.cancelRoundStart()
        XCTAssertFalse(model.isPreparingRound)
        XCTAssertNil(model.pendingLiveHole)
        XCTAssertNil(model.liveRoundState)
        held.releaseAll(200)
    }

    /// J4.2 / C365-A1': a single-course prep start must drop a package answered after cancellation.
    func testC365PrepCancelDropsLateCoursePackageAndDoesNotNavigate() async throws {
        let host = "c365-prep-cancel.example.test"
        let roundId = "c365-prep-cancel"
        let map = try package(roundId: roundId, mapOnly: true, standalone: true, offlineState: "ready")
        let data = try JSONEncoder().encode(map)
        let held = C85HeldRequests()
        let sent = expectation(description: "prep map package held")
        let afterFetch = expectation(description: "prep package answered before cancellation boundary")
        let releaseAfterFetch = C90RequestGate()
        let requests = C85RequestLog()
        let once = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            if proto.request.url?.path.hasSuffix("/package") == true {
                requests.append(proto.request)
                held.hold(proto)
                if once.claim() { sent.fulfill() }
            } else {
                proto.reply(404)
            }
        })
        let fixture = makeModel(host: host, held: held, roundStartTimeoutInterval: 2)
        let model = fixture.model
        model.roundStartAfterFetchForTesting = {
            afterFetch.fulfill()
            await releaseAfterFetch.wait()
        }
        let course = MobileCourseOption(globalId: c85CourseId, name: "Prep fixture", holes: 9, teeBox: "blue")
        XCTAssertTrue(model.openPrepCourse(course))
        let start = try XCTUnwrap(model.activeRoundStartTaskForTesting)
        await fulfillment(of: [sent], timeout: eventWait)

        held.releaseAll(200, data)
        await fulfillment(of: [afterFetch], timeout: eventWait)
        model.cancelRoundStart()
        await releaseAfterFetch.release()
        await start.value

        XCTAssertNil(model.prepPackage, "a cancelled prep start must not publish a prep package")
        XCTAssertNil(model.pendingLiveHole, "a cancelled prep start must not navigate to a hole")
        XCTAssertNil(model.liveRoundState)
        XCTAssertNil(model.roundStartFailure, "cancel must not become a network failure")
        XCTAssertFalse(model.syncStatus.contains("网络不可用"))
        XCTAssertEqual(requests.all.count, 1)
    }

    /// J4.2 / C365-A3: a timed-out package with only an incomplete template stays on Start and offers
    /// an explicit simplified entry. It may enter only after that affordance is chosen.
    func testC365IncompleteTemplateDoesNotSilentlyEnterAndSimplifiedStartIsExplicit() async throws {
        let host = "c365-incomplete.example.test"
        let roundId = "c365-incomplete"
        let incomplete = try package(
            roundId: roundId, mapOnly: true, standalone: true, offlineState: "ready"
        )
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            // The short injected foreground timeout ends this request; no package response is
            // delivered before the fallback decision.
        })
        let fixture = makeModel(host: host, roundStartTimeoutInterval: 0.05)
        try fixture.store.saveCourseTemplate(incomplete)
        let model = fixture.model
        await model.prepareCourseRound(
            roundId: roundId, teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )

        XCTAssertNil(model.pendingLiveHole, "an incomplete template cannot silently open hole 1")
        XCTAssertTrue(model.canStartSimplifiedRound)
        await model.startSimplifiedRound()
        XCTAssertEqual(model.pendingLiveHole, 1, "the explicit simplified action may enter the hole")
    }

    /// J4.2 / C365-A4: an already cached complete round keeps the existing offline start behavior.
    func testC365CompleteCachedRoundStillEntersAfterPackageTimeout() async throws {
        let host = "c365-complete-cache.example.test"
        let roundId = "c365-complete-cache"
        let cached = try package(roundId: roundId, mapOnly: false, standalone: true, offlineState: "ready")
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            // The package timeout drives the cached fallback.
        })
        let fixture = makeModel(host: host, roundStartTimeoutInterval: 0.05)
        try fixture.store.saveRoundPackage(cached)
        let model = fixture.model
        await model.prepareCourseRound(
            roundId: roundId, teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )

        XCTAssertEqual(model.pendingLiveHole, 1, "a complete cached package remains offline usable")
        XCTAssertFalse(model.canStartSimplifiedRound)
    }

    /// J4.2 / C365-N3: an intent timeout reuses a complete cached round without a second request.
    func testC365IntentTimeoutFallsBackToCompleteCachedRoundWithoutDuplicateRequest() async throws {
        let host = "c365-intent-fallback.example.test"
        let roundId = "c365-intent-fallback"
        let cached = try package(roundId: roundId, mapOnly: false, standalone: true, offlineState: "ready")
        let held = C85HeldRequests()
        let requests = C85RequestLog()
        let intentSent = expectation(description: "intent producer held")
        let once = C33FirstMatch()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path.hasSuffix("/package") == true else { proto.reply(404); return }
            requests.append(proto.request)
            held.hold(proto)
            if once.claim() { intentSent.fulfill() }
        }, onStop: { held.forget($0) })
        let fixture = makeModel(
            host: host, held: held, roundStartIntentWaitNanoseconds: 50_000_000,
            roundStartTimeoutInterval: 2
        )
        let model = fixture.model
        let course = MobileCourseOption(globalId: c85CourseId, name: "Intent fixture", holes: 9, teeBox: "blue")
        model.prefetchIntendedCourses([course], teeBox: "blue")
        await fulfillment(of: [intentSent], timeout: eventWait)
        try fixture.store.saveRoundPackage(cached)

        await model.prepareCourseRound(
            roundId: roundId, teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )

        XCTAssertEqual(model.pendingLiveHole, 1)
        XCTAssertFalse(model.canStartSimplifiedRound)
        XCTAssertEqual(requests.all.count, 1, "intent timeout must not issue a duplicate package request")
        held.releaseAll(503)
    }

    /// J4.2 / C365-N4: cancelling a visible failure clears the stale failure copy as well.
    func testC365CancelAfterFailureClearsFailureCopy() async throws {
        let host = "c365-cancel-failure.example.test"
        let fixture = makeModel(host: host, roundStartTimeoutInterval: 0.05)
        let model = fixture.model
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
        })
        await model.prepareCourseRound(
            roundId: "c365-cancel-failure", teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )
        XCTAssertNotNil(model.roundStartFailure)
        model.cancelRoundStart()
        XCTAssertNil(model.roundStartFailure)
        XCTAssertFalse(model.syncStatus.contains("点重试"))
    }

    /// J4.2 / C365-N8: a degraded cached package is never an implicit offline entry.
    func testC365DegradedCachedRoundDoesNotSilentlyEnter() async throws {
        let host = "c365-degraded-cache.example.test"
        let roundId = "c365-degraded-cache"
        let cached = try package(roundId: roundId, mapOnly: false, standalone: true, offlineState: "degraded")
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
        })
        let fixture = makeModel(host: host, roundStartTimeoutInterval: 0.05)
        try fixture.store.saveRoundPackage(cached)
        let model = fixture.model
        await model.prepareCourseRound(
            roundId: roundId, teeBox: "blue",
            loops: [RoundLoopEntry(globalId: c85CourseId, half: "all")]
        )
        XCTAssertNil(model.pendingLiveHole)
        XCTAssertNil(model.liveRoundState)
        XCTAssertNotNil(model.roundStartFailure)
        // The explicit 简化开局 escape hatch may still be offered; only silent entry is forbidden.
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
        let topoResponses = C85Counter()
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
                topoResponses.increment()
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
        XCTAssertGreaterThan(topoResponses.value, 0, "injected topo must reach this test’s handler")
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

    /// J4.2: the deferred personal package follows the playing hole even when starting on 10.
    func testPersonalEnrichmentRequestCarriesCurrentTenthHole() async throws {
        let host = "j4-personal-tenth.example.test"
        let roundId = "j4-personal-tenth"
        let template = try package(roundId: roundId, mapOnly: true)
        let map = try XCTUnwrap(LiveRoundPackage.projecting(
            [.init(globalId: c85CourseId, half: "front"), .init(globalId: c85CourseId, half: "front")],
            templates: [c85CourseId: template], roundId: roundId
        ))
        let fullSent = expectation(description: "personal package for playing hole 10")
        let once = C33FirstMatch()
        let log = C85RequestLog()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host,
                  proto.request.url?.path == "/api/v2/mobile/courses/\(c85CourseId)/package",
                  c33Query(proto.request, "map_only") != "true" else { proto.reply(404); return }
            log.append(proto.request)
            if once.claim() { fullSent.fulfill() }
            proto.reply(503)
        })
        let fixture = makeModel(host: host)
        fixture.model.enterPrepMode(with: map, hole: 10)
        XCTAssertTrue(fixture.model.startRoundFromFirstStroke(startHole: 10))
        await fulfillment(of: [fullSent], timeout: eventWait)
        XCTAssertEqual(fixture.model.liveRoundState?.activeHole, 10)
        XCTAssertEqual(log.all.first.flatMap { c33Query($0, "priority_hole") }, "10",
                       "J4.2 enrichment must warm the playing hole, not default hole 1")
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
        configuration.protocolClasses = testProtocolClasses(C33URLProtocol.self)
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

    private func makeModel(
        host: String,
        held: C85HeldRequests? = nil,
        roundStartIntentWaitNanoseconds: UInt64 = LiveRoundAppModel.defaultRoundStartIntentWaitNanoseconds,
        roundStartTimeoutInterval: TimeInterval = 30,
        roundStartNow: @escaping () -> Date = { Date() },
        prepDownloadRecords: [PrepCourseDownloadRecord] = []
    ) -> ModelFixture {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c85-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        if !prepDownloadRecords.isEmpty { try! store.savePrepCourseDownloads(prepDownloadRecords) }
        // No per-host connection cap: a held request must not serialize the next one.
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(C33URLProtocol.self)
        let session = URLSession(configuration: configuration)
        let client = SyncClient(
            baseURL: URL(string: "https://\(host)")!,
            session: session,
            retrySleep: { _ in },
            roundStartTimeoutInterval: roundStartTimeoutInterval
        )
        let model = LiveRoundAppModel(
            offlineStore: store, apiBaseURL: client.baseURL, watchBridge: nil,
            garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [],
            roundStartIntentWaitNanoseconds: roundStartIntentWaitNanoseconds,
            networkPathObserver: nil, roundStartNow: roundStartNow
        )
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
        standalone: Bool = false,
        offlineState: String? = nil,
        eighteenHoles: Bool = false
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
        if let offlineState, var status = root["offlinePackageStatus"] as? [String: Any] {
            status["state"] = offlineState
            root["offlinePackageStatus"] = status
        }
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
        if eighteenHoles {
            var holes = try XCTUnwrap(root["holes"] as? [[String: Any]])
            let back = holes.map { source -> [String: Any] in
                var row = source
                let number = (source["number"] as! Int) + 9
                row["number"] = number
                row["sourceLocalHole"] = number
                row["courseHoleNumber"] = number
                if let version = garminRasterVersion {
                    row["garminRaster"] = [
                        "imageUrl": "/api/v2/courses/\(c85CourseId)/holes/\(number)/garmin-raster.jpg?v=\(version)",
                        "metadataUrl": "/api/v2/courses/\(c85CourseId)/holes/\(number)/garmin-raster",
                    ]
                }
                return row
            }
            holes += back
            root["holes"] = holes
            root["roundLoops"] = [
                ["globalId": c85CourseId, "half": "front", "roundStartHole": 1, "sourceStartHole": 1, "holeCount": 9],
                ["globalId": c85CourseId, "half": "back", "roundStartHole": 10, "sourceStartHole": 10, "holeCount": 9],
            ]
            root["loopKey"] = "\(c85CourseId):front+\(c85CourseId):back"
        }
        let decoded = try JSONDecoder().decode(
            LiveRoundPackage.self,
            from: JSONSerialization.data(withJSONObject: root)
        ).validatedRoundIdentity()
        XCTAssertEqual(decoded.holes.map(\.number), Array(1...(eighteenHoles ? 18 : 9)))
        if !mapOnly {
            XCTAssertFalse(decoded.clubProfiles.isEmpty)
            XCTAssertEqual(Set(decoded.caddieContextSeeds.map(\.hole)), Set(1...9))
        }
        return decoded
    }
}

private final class C367StartClock: @unchecked Sendable {
    private let lock = NSLock()
    private var seconds: TimeInterval = 0
    var elapsed: TimeInterval { lock.lock(); defer { lock.unlock() }; return seconds }
    var now: Date { Date(timeIntervalSince1970: 1_900_000_000 + elapsed) }
    func advance(by seconds: TimeInterval) { lock.lock(); self.seconds += seconds; lock.unlock() }
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
