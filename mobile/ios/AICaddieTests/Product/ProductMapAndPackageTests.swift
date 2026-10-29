import CoreLocation
import Foundation
#if !SWIFT_PACKAGE
import SwiftUI
import UIKit
#endif
import XCTest
@testable import AICaddie
import AICaddieDomain

#if !SWIFT_PACKAGE
private final class C136Counter {
    private let lock = NSLock()
    private var storage = 0

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func increment() {
        lock.lock()
        storage += 1
        lock.unlock()
    }
}

private actor C136Gate {
    private var continuations: [CheckedContinuation<Void, Never>] = []
    private var released = false

    func wait() async {
        if released { return }
        await withCheckedContinuation { continuations.append($0) }
    }

    func release() {
        released = true
        let pending = continuations
        continuations.removeAll()
        pending.forEach { $0.resume() }
    }
}
#endif

@MainActor
final class ProductMapAndPackageTests: XCTestCase {
#if !SWIFT_PACKAGE
    private let productEventWait: TimeInterval = 10

    override func tearDown() {
        C33URLProtocol.setHandlers(onStart: nil)
        super.tearDown()
    }

    private func c136Package(
        garmin: Bool = false,
        pendingHole: Int? = nil,
        includePrep: Bool = true
    ) throws -> LiveRoundPackage {
        var root = try XCTUnwrap(
            JSONSerialization.jsonObject(
                with: JSONEncoder().encode(try c33Package())
            ) as? [String: Any]
        )
        var holes = try XCTUnwrap(root["holes"] as? [[String: Any]])
        for index in holes.indices {
            let number = (holes[index]["number"] as? Int) ?? (index + 1)
            if garmin {
                holes[index]["garminRaster"] = [
                    "imageUrl": "/api/v2/courses/32850/holes/\(number)/garmin-raster.jpg?v=c136",
                    "metadataUrl": "/api/v2/courses/32850/holes/\(number)/garmin-raster.json?v=c136",
                ]
            }
            if number == pendingHole {
                holes[index]["geometryCoverage"] = "partial"
                holes[index]["geometryState"] = "pending"
                holes[index]["retryAfterEpoch"] = 0.0
            }
        }
        root["holes"] = holes
        if !includePrep,
           var coursePrep = root["coursePrep"] as? [String: Any],
           var prepHoles = coursePrep["holes"] as? [[String: Any]] {
            prepHoles.removeAll { ($0["hole"] as? Int) == pendingHole }
            coursePrep["holes"] = prepHoles
            root["coursePrep"] = coursePrep
        }
        return try ProductSharedVectors.decode(root)
    }

    private func c136Model(host: String, package: LiveRoundPackage) -> (
        model: LiveRoundAppModel, client: SyncClient, session: URLSession, directory: URL
    ) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c136-\(UUID().uuidString)", isDirectory: true)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [C33URLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = SyncClient(baseURL: URL(string: "https://\(host)")!, session: session)
        let model = c33Model(OfflineStore(directoryURL: directory), client)
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            guard proto.request.url?.path == "/api/v2/mobile/courses/\(package.course.globalId)/package" else {
                proto.reply(404)
                return
            }
            proto.reply(200, (try? JSONEncoder().encode(package)) ?? Data())
        })
        return (model, client, session, directory)
    }

    private func hostCurrentHole(_ view: CurrentHoleView) -> (
        controller: UIHostingController<CurrentHoleView>, window: UIWindow
    ) {
        let controller = UIHostingController(rootView: view)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 844))
        window.rootViewController = controller
        window.makeKeyAndVisible()
        return (controller, window)
    }

    /// C136/J4: disabling Garmin is an end-to-end gate. The model receives a package carrying
    /// raster URLs, but its real preload pass must issue zero raster URL requests.
    func test_j4_5_garmin_disabled_model_sends_no_raster_request() async throws {
        let package = try c136Package(garmin: true)
        let host = "c136-garmin-off.example.test"
        let fixture = c136Model(host: host, package: package)
        let rasterRequests = C136Counter()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            if proto.request.url?.path.contains("/garmin-raster") == true {
                rasterRequests.increment()
            }
            if proto.request.url?.path == "/api/v2/mobile/courses/\(package.course.globalId)/package" {
                proto.reply(200, (try? JSONEncoder().encode(package)) ?? Data())
            } else {
                proto.reply(200)
            }
        })
        fixture.model.garminRasterPreloadingEnabled = { false }
        fixture.model.garminRasterDownloader = { url in
            let request = URLRequest(url: url)
            _ = try? await fixture.session.data(for: request)
            return true
        }
        defer {
            fixture.client.invalidateForTesting()
            fixture.session.invalidateAndCancel()
            try? FileManager.default.removeItem(at: fixture.directory)
        }

        await fixture.model.prepareCourseRound(
            roundId: package.roundId, teeBox: package.course.teeBox, loops: package.loopEntries
        )
        await fixture.model.waitForGarminRasterDownloadForTesting()
        XCTAssertEqual(rasterRequests.value, 0, "disabled Garmin must not reach /garmin-raster")
        XCTAssertEqual(fixture.model.pendingLiveHole, package.holes.first?.number)
        await fixture.model.stopRoundBackgroundWorkForTesting()
    }

    /// C136/J4.5: the selected hole's Garmin guards cover both the direct descriptor request and
    /// its recovery loop. With the persisted switch off neither path may issue a request.
    func test_j4_5_garmin_disabled_hole_view_sends_no_raster_request() async throws {
        let package = try c136Package(garmin: true)
        let hole = try XCTUnwrap(package.holes.first)
        let host = "c136-garmin-hole-off.example.test"
        let requests = C136Counter()
        let session = C33URLProtocol.session()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path.contains("garmin-raster") == true { requests.increment() }
            proto.reply(200)
        })
        let defaults = UserDefaults.standard
        let previous = defaults.object(forKey: LiveGarminRasterPolicy.preferenceKey)
        defaults.set(false, forKey: LiveGarminRasterPolicy.preferenceKey)
        defer {
            if let previous { defaults.set(previous, forKey: LiveGarminRasterPolicy.preferenceKey) }
            else { defaults.removeObject(forKey: LiveGarminRasterPolicy.preferenceKey) }
            session.invalidateAndCancel()
        }
        let view = CurrentHoleView(
            package: package, hole: hole,
            caddieBaseURL: URL(string: "https://\(host)")!,
            networkSession: session
        )
        await view.loadGarminRasterForTesting()
        await view.recoverGarminDescriptorForTesting()
        XCTAssertEqual(requests.value, 0, "disabled Garmin must gate both hole raster paths")
    }

    /// C136/J4: a slow/failed raster pass is independent of the playable first hole. The test holds
    /// the actual downloader, calls the same initial-load callback used by CurrentHoleView, and
    /// proves the model can publish and persist the active hole before releasing the raster.
    func test_j4_5_slow_failed_garmin_does_not_block_first_hole_or_scoring() async throws {
        let package = try c136Package(garmin: true)
        let host = "c136-garmin-slow.example.test"
        let fixture = c136Model(host: host, package: package)
        let started = expectation(description: "raster preload started")
        let gate = C136Gate()
        let startLock = NSLock()
        var didSignalStart = false
        fixture.model.garminRasterPreloadingEnabled = { true }
        fixture.model.garminRasterDownloader = { _ in
            startLock.lock()
            let shouldSignal = !didSignalStart
            didSignalStart = true
            startLock.unlock()
            if shouldSignal { started.fulfill() }
            await gate.wait()
            return false
        }
        defer {
            fixture.client.invalidateForTesting()
            fixture.session.invalidateAndCancel()
            try? FileManager.default.removeItem(at: fixture.directory)
        }

        await fixture.model.prepareCourseRound(
            roundId: package.roundId, teeBox: package.course.teeBox, loops: package.loopEntries
        )
        await fulfillment(of: [started], timeout: productEventWait)
        XCTAssertEqual(fixture.model.pendingLiveHole, 1, "first hole publishes while raster is held")
        fixture.model.setActiveHole(1)
        XCTAssertEqual(fixture.model.liveRoundState?.activeHole, 1, "scoring cursor is usable")
        await gate.release()
        await fixture.model.waitForGarminRasterDownloadForTesting()
        XCTAssertEqual(fixture.model.pendingLiveHole, 1)
        await fixture.model.stopRoundBackgroundWorkForTesting()
    }

    /// C136/J4: geometry refresh after moving to a pending hole is map-only. The initial full
    /// package is counted separately, then switching holes must add only `map_only=true` traffic.
    func test_j4_2_switching_holes_uses_map_only_without_full_package() async throws {
        let pending = try c136Package(pendingHole: 2)
        let ready = try c136Package()
        let host = "c136-map-only.example.test"
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c136-\(UUID().uuidString)", isDirectory: true)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [C33URLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = SyncClient(baseURL: URL(string: "https://\(host)")!, session: session)
        let model = c33Model(OfflineStore(directoryURL: directory), client)
        let fullRequests = C136Counter(), mapOnlyRequests = C136Counter()
        let roundPackageRequests = C136Counter()
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else {
                proto.reply(404); return
            }
            if proto.request.url?.path.contains("/mobile/rounds/") == true {
                roundPackageRequests.increment()
                proto.reply(404)
                return
            }
            guard proto.request.url?.path == "/api/v2/mobile/courses/\(pending.course.globalId)/package" else {
                proto.reply(404)
                return
            }
            if c33Query(proto.request, "map_only") == "true" {
                mapOnlyRequests.increment()
                proto.reply(200, (try? JSONEncoder().encode(ready)) ?? Data())
            } else {
                fullRequests.increment()
                proto.reply(200, (try? JSONEncoder().encode(pending)) ?? Data())
            }
        })
        defer {
            client.invalidateForTesting()
            session.invalidateAndCancel()
            try? FileManager.default.removeItem(at: directory)
        }

        await model.prepareCourseRound(
            roundId: pending.roundId, teeBox: pending.course.teeBox, loops: pending.loopEntries
        )
        let fullBaseline = fullRequests.value
        let roundBaseline = roundPackageRequests.value
        let mapBaseline = mapOnlyRequests.value
        model.setActiveHole(2)
        let deadline = ProcessInfo.processInfo.systemUptime + productEventWait
        while mapOnlyRequests.value - mapBaseline < 1, ProcessInfo.processInfo.systemUptime < deadline {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertEqual(fullRequests.value - fullBaseline, 0, "J4.2 hole change adds no full personal package")
        XCTAssertEqual(roundPackageRequests.value - roundBaseline, 0, "J4.2 hole change adds no round package")
        XCTAssertGreaterThanOrEqual(mapOnlyRequests.value - mapBaseline, 1)
        XCTAssertEqual(model.liveRoundState?.activeHole, 2, "local map and cursor are immediate")
        await model.stopRoundBackgroundWorkForTesting()
    }

    /// C136/J4.5: the real hole loader keeps the partial route and F/M/B facts visible while
    /// `/prep` is in flight. The task is intentionally held after the view has started it.
    func test_j4_5_real_hole_loader_keeps_surface_visible_during_prep() async throws {
        let package = try c136Package(pendingHole: 1)
        let hole = try XCTUnwrap(package.holes.first)
        let host = "c136-hole-loader.example.test"
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [C33URLProtocol.self]
        let session = URLSession(configuration: configuration)
        let started = expectation(description: "hole prep started")
        let startedOnce = C33FirstMatch()
        let prepRequests = C136Counter()
        let gate = C136Gate()
        let defaults = UserDefaults.standard
        let previousGarmin = defaults.object(forKey: LiveGarminRasterPolicy.preferenceKey)
        defaults.set(false, forKey: LiveGarminRasterPolicy.preferenceKey)
        defer {
            if let previousGarmin { defaults.set(previousGarmin, forKey: LiveGarminRasterPolicy.preferenceKey) }
            else { defaults.removeObject(forKey: LiveGarminRasterPolicy.preferenceKey) }
            session.invalidateAndCancel()
        }
        let prepPackage = try XCTUnwrap(try c33Package().coursePrep)
        let prepHoles = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(prepPackage.holes)) as? [[String: Any]]
        )
        let prepData = try JSONSerialization.data(withJSONObject: [
            "schema": prepPackage.schema, "globalId": prepPackage.globalId,
            "holeCount": prepHoles.count, "clubs": [], "holes": prepHoles
        ])
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            if proto.request.url?.path.hasSuffix("/prep") == true {
                prepRequests.increment()
                if startedOnce.claim() { started.fulfill() }
                Task {
                    await gate.wait()
                    proto.reply(200, prepData)
                }
            } else {
                proto.reply(404)
            }
        })
        let view = CurrentHoleView(
            package: package, hole: hole,
            caddieBaseURL: URL(string: "https://\(host)")!,
            networkSession: session,
            caddieClient: CaddieDecisionClient(
                baseURL: URL(string: "https://\(host)")!, session: session
            ),
            isSelected: true
        )
        let hosted = hostCurrentHole(view)
        let controller = hosted.controller
        defer { hosted.window.isHidden = true; hosted.window.rootViewController = nil }
        controller.rootView.clearHolePrepForTesting()
        defer {
            Task { await gate.release() }
        }
        await fulfillment(of: [started], timeout: productEventWait)
        let secondAttempt = Task { @MainActor in await controller.rootView.retryHoleMapForTesting() }
        _ = await secondAttempt.value
        XCTAssertFalse(controller.rootView.mapPreparingSurfaceFailedForTesting(),
                       "a retry joining an in-flight prep cannot mark the map as failed")
        XCTAssertEqual(controller.rootView.liveMapDisplayStateForTesting(), .factual,
                       "partial route remains actionable while prep is held")
        let visible = controller.rootView.displayedGreenRangeYardsForTesting()
        XCTAssertNotNil(visible.middle, "numeric middle remains visible during prep")
        XCTAssertEqual(prepRequests.value, 1, "one hole starts one prep request")
        await gate.release()
    }

    /// C136/J4: a held prep request cannot replace the factual route/numeric first frame with the
    /// full-screen waiting page. The fetch is the real live prep publication seam and is released
    /// only after the visible state has been asserted.
    func test_j4_5_hanging_prep_keeps_route_and_numeric_surface_visible() async throws {
        let gate = C136Gate()
        let started = expectation(description: "prep request held")
        let task = Task { @MainActor in
            await LiveHolePrepPublication.run(
                fetch: {
                    started.fulfill()
                    await gate.wait()
                    return nil
                },
                publish: { _ in true },
                pushWatch: {}
            )
        }
        await fulfillment(of: [started], timeout: productEventWait)
        let state = LiveMapDisplayState.resolveLive(.init(
            coverage: "partial", preciseTopoImageReady: false, garminRaster: nil,
            garminImageReady: false, garminImageFailed: true, hasCachedPreciseTopo: false,
            hasRoute: true
        ))
        XCTAssertEqual(state, .factual, "route facts draw while /prep is held")
        XCTAssertEqual(
            HoleMapWaitingPage(holeNumber: 2, par: 4, yards: 241).subtitle,
            "241 码 · 图到了自动出来"
        )
        await gate.release()
        _ = await task.value
    }

    /// C136/J4: both successful and terminally failed prep requests clear the pending state. This
    /// drives the production probe and then resolves the same map state used by CurrentHoleView.
    func test_j4_5_map_spinner_stops_after_prep_success_or_failure() async throws {
        let partial = try ProductInputs.prep(coverage: "partial")
        let ready = try ProductInputs.prep(coverage: "ready")
        let success = await LiveHolePrepProbe.run(
            fetch: { ready }, publishInterim: { _ in }, wait: { _ in }
        )
        XCTAssertEqual(LiveMapDisplayState.resolve(prep: partial, pending: true), .factualPending)
        XCTAssertEqual(
            LiveMapDisplayState.resolve(prep: success, pending: false), .precise,
            "successful prep ends the spinner and promotes the map"
        )

        var failedInput = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(partial)) as? [String: Any]
        )
        failedInput["missingData"] = [["label": "hazards", "state": "failed"]]
        let failed: CoursePrepHole = try ProductSharedVectors.decode(failedInput)
        let terminal = await LiveHolePrepProbe.run(
            fetch: { failed }, publishInterim: { _ in }, wait: { _ in }
        )
        XCTAssertNil(terminal)
        XCTAssertEqual(
            LiveMapDisplayState.resolve(prep: failed, pending: false), .factual,
            "terminal failure ends the spinner while retaining route facts"
        )
        XCTAssertFalse(
            CurrentHoleView.mapPreparingSurfaceFailed(
                holeMapLoadFailed: false, preciseMapTimedOut: false, hasPrep: false, hasRoute: false
            ),
            "J4.5 an in-flight prep keeps the route surface actionable"
        )
        XCTAssertTrue(
            CurrentHoleView.mapPreparingSurfaceFailed(
                holeMapLoadFailed: false, preciseMapTimedOut: true, hasPrep: false, hasRoute: false
            ),
            "J4.5 a terminal timeout stops the waiting spinner"
        )
    }
#endif

    func test_j4_5_garmin_disabled_gate_has_no_raster_request_or_surface() {
        XCTAssertFalse(LiveGarminRasterPolicy.shouldFetch(enabled: false, requestStarted: false))
        XCTAssertNil(LiveGarminRasterPolicy.displayedRaster(
            enabled: false,
            raster: GarminRasterResponse(available: true, imageUrl: "/raster.jpg", mode: "H")
        ))
    }

    func test_j4_2_cached_package_lifecycle_and_revision_adoption() throws {
        // Prepared at midnight; stale at +24 h; expires at +48 h. Boundary instants are inclusive.
        let status: OfflinePackageStatus = try ProductSharedVectors.decode([
            "state": "ready", "preparedAt": "2026-10-01T00:00:00Z", "expiresAt": "2026-10-03T00:00:00Z",
            "cachePolicy": ["staleAfterHours": 24, "expiresAfterHours": 48],
        ])
        for (date, expected) in [
            ("2026-10-01T23:59:59Z", OfflinePackageCacheState.ready),
            ("2026-10-02T00:00:00Z", .stale), ("2026-10-03T00:00:00Z", .expired),
        ] {
            XCTAssertEqual(status.cacheState(now: try XCTUnwrap(ISO8601DateFormatter().date(from: date))), expected, date)
        }
        let job = PrepCourseDownloadRecord(course: ProductInputs.course(81001, venue: "Example", holes: 18),
            phase: .downloading, preparedHoles: 18, downloadedHoles: 7, totalHoles: 18,
            requiredGeometryRevisions: ["81001:8": "synthetic-r2"])
        let precise = try ProductInputs.prep()
        let partial = try ProductInputs.prep(coverage: "partial")
        XCTAssertTrue(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: partial, incoming: precise), "new map replaces route")
        XCTAssertFalse(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: precise, incoming: partial), "late partial cannot erase complete map")
        var input = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(partial)) as? [String: Any])
        input["geometryRevision"] = "synthetic-r2"
        let replacement: CoursePrepHole = try ProductSharedVectors.decode(input)
        XCTAssertTrue(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: precise, incoming: replacement, authoritativeRevision: "synthetic-r2"))
        XCTAssertFalse(CoursePrepHoleAdoptionPolicy.shouldAdopt(current: replacement, incoming: precise, authoritativeRevision: "synthetic-r2"))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        try store.savePrepCourseDownloads([job])
        let resumed = try XCTUnwrap(OfflineStore(directoryURL: directory).loadPrepCourseDownloads().first)
        XCTAssertEqual(resumed.phase, .downloading, "restart resumes unfinished job")
        XCTAssertEqual(resumed.downloadedHoles, 7, "seven finished maps retained")
        XCTAssertEqual(resumed.requiredGeometryRevisions, ["81001:8": "synthetic-r2"])
        var packageInput = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(ProductInputs.package())) as? [String: Any])
        packageInput["coursePrep"] = ["schema": "ai-caddie-course-prep-v1", "globalId": 81001,
            "holes": [try JSONSerialization.jsonObject(with: JSONEncoder().encode(precise))]]
        let package: LiveRoundPackage = try ProductSharedVectors.decode(packageInput)
        XCTAssertFalse(package.hasCompleteOfflineCoursePrep, "one prepared map is a partial package")
        var completeInput = packageInput
        let firstPrep = try XCTUnwrap((packageInput["coursePrep"] as? [String: Any])?["holes"] as? [[String: Any]]).first!
        completeInput["coursePrep"] = ["schema": "ai-caddie-course-prep-v1", "globalId": 81001,
            "holes": (1...18).map { number -> [String: Any] in var row = firstPrep; row["hole"] = number; return row }]
        let complete: LiveRoundPackage = try ProductSharedVectors.decode(completeInput)
        XCTAssertTrue(complete.hasCompleteOfflineCoursePrep, "all eighteen precise routes installed")
        try store.saveRoundPackage(package)
        // No client/network exists on the read path: a fresh store can recover the installed facts.
        let restored = try XCTUnwrap(OfflineStore(directoryURL: directory).loadRoundPackage(roundId: package.roundId))
        XCTAssertEqual(restored.holes.map(\.sourceLocalHole), Array(1...18), "unreachable server and restart")
        input = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(package)) as? [String: Any])
        XCTAssertEqual(restored.coursePrep?.holes.first?.map?.overlay.w, 300, "installed overlay survives no server")
        let files = try FileManager.default.subpathsOfDirectory(atPath: directory.path)
            .filter { $0.hasPrefix("packages/") && $0.hasSuffix(".json") }
        XCTAssertEqual(files.count, 1)
        let cached = directory.appendingPathComponent(try XCTUnwrap(files.first))
        try Data("{bad".utf8).write(to: cached)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId), "corrupt cache rejected")
        XCTAssertFalse(FileManager.default.fileExists(atPath: cached.path), "invalid package evicted for reacquisition")
        try store.saveRoundPackage(package)
        XCTAssertNotNil(try store.loadRoundPackage(roundId: package.roundId), "fresh package installs after corruption")
        for (name, key) in [("negative-id", "-1:front"), ("unknown-half", "81001:side"), ("three-loops", "81001:front+81001:back+81001:front")] {
            XCTAssertNil(RoundLoopEntry.entries(loopKey: key), name)
        }
        input["schema"] = "ai-caddie-live-round-package-v1"
        let old: LiveRoundPackage = try ProductSharedVectors.decode(input)
        XCTAssertThrowsError(try OfflineStore(directoryURL: directory).saveRoundPackage(old), "old package must be reacquired")
    }

    func test_j4_5_map_degradation_and_upgrade_preserve_physical_points() throws {
        let ready = try ProductInputs.prep()
        let partial = try ProductInputs.prep(coverage: "partial")
        let empty = try ProductInputs.prep(coverage: "missing", route: false)
        let rows: [(String, CoursePrepHole?, Bool, LiveMapDisplayState)] = [
            ("precise", ready, false, .precise), ("route-downloading", partial, true, .factualPending),
            ("offline-route", partial, false, .factual), ("no-route", empty, true, .waiting),
            ("no-hole", nil, false, .waiting),
        ]
        for (id, prep, pending, expected) in rows {
            XCTAssertEqual(LiveMapDisplayState.resolve(prep: prep, pending: pending), expected, id)
        }
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: ready, hasLocalTopo: true, isStale: false, downloadActive: false), .precise)
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: ready, hasLocalTopo: true, isStale: true, downloadActive: true), .factualPending)
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: partial, hasLocalTopo: false, isStale: false, downloadActive: false), .factual)
        XCTAssertEqual(LiveMapDisplayState.resolvePrep(prep: empty, hasLocalTopo: false, isStale: false, downloadActive: true), .waiting)
        let old = try XCTUnwrap(ready.map?.overlay)
        let new = try XCTUnwrap(ProductInputs.prep(scale: 2).map?.overlay)
        // Same physical station/lateral offset in a map with twice the pixels/metre.
        for (id, point, expected) in [
            ("target", CGPoint(x: 110, y: 200), CGPoint(x: 220, y: 400)),
            ("flag", CGPoint(x: 100, y: 50), CGPoint(x: 200, y: 100)),
        ] {
            let transferred = try XCTUnwrap(LiveMapCarryOver.transfer(point, from: old, to: new), id)
            XCTAssertEqual(transferred.x, expected.x, accuracy: 0.001, id)
            XCTAssertEqual(transferred.y, expected.y, accuracy: 0.001, id)
        }
        var session = PrepHoleMapSession()
        session.select(hole: 1)
        session.selectPlan(2, planCount: 3)
        session.viewport = HoleMapViewportState(zoomScale: 2.5, offset: CGSize(width: 35, height: -20))
        for state in ["route", "topo-arrived", "revision-replaced"] {
            session.adopt(holeNumbers: [1, 2], planCount: 3)
            XCTAssertEqual(session.holeNumber, 1, state)
            XCTAssertEqual(session.selectedPlanIndex, 2, state)
            XCTAssertEqual(session.viewport.zoomScale, 2.5, state)
            XCTAssertEqual(session.viewport.offset, CGSize(width: 35, height: -20), state)
        }
        func hazard(_ id: String, _ station: Double, kind: String = "water") -> LiveHazardDisplayItem {
            LiveHazardDisplayItem(id: id, kind: kind, label: "Example obstacle", frontYards: 110, backYards: 132,
                frontPx: [100, 250], backPx: [100, 230], outlinePx: [], frontRouteM: station, backRouteM: station + 20)
        }
        let before = [hazard("old", 100)]
        for (name, after, selected) in [
            ("same-physical-new-id", [hazard("new", 105)], Optional("new")),
            ("different-obstacle", [hazard("old", 130)], nil),
            ("different-kind", [hazard("old", 100, kind: "bunker")], nil),
        ] {
            XCTAssertEqual(LiveMapCarryOver.hazardSelection(current: "old", previous: before, next: after), selected, name)
        }
    }

    func test_j4_2_map_only_merge_preserves_player_package_facts() throws {
        let current = try ProductInputs.package()
        var input = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(current)) as? [String: Any]
        )
        input["coursePrep"] = [
            "schema": "ai-caddie-course-prep-v1",
            "globalId": current.course.globalId,
            "holes": [try JSONSerialization.jsonObject(with: JSONEncoder().encode(ProductInputs.prep()))]
        ]
        let mapOnly = try ProductSharedVectors.decode(input, as: LiveRoundPackage.self)
        let merged = current.mergingMapFacts(from: mapOnly)
        XCTAssertEqual(merged.clubProfiles, current.clubProfiles, "map-only cannot replace the bag")
        XCTAssertEqual(merged.caddieContextSeeds, current.caddieContextSeeds, "map-only cannot replace caddie seeds")
        XCTAssertEqual(merged.eventCursor, current.eventCursor, "map-only cannot replace event authority")
        XCTAssertEqual(merged.coursePrep?.holes.first?.resolvedMapOverlay, mapOnly.coursePrep?.holes.first?.resolvedMapOverlay)
    }

    func test_j4_2_map_only_merge_rejects_mismatched_loop_identity() throws {
        let current = try ProductInputs.package()
        let incoming = current.replacingCoursePrep(nil).replacingCourseDisplayName("other")
        let mismatched = LiveRoundPackage(
            schema: incoming.schema, roundId: incoming.roundId, dataMode: incoming.dataMode,
            sourceCoverage: incoming.sourceCoverage, missingData: incoming.missingData,
            playerProfile: incoming.playerProfile, course: incoming.course, holes: incoming.holes,
            roundLoops: incoming.roundLoops, loopKey: "different-loop", venueLoops: incoming.venueLoops,
            coursePrep: incoming.coursePrep, geometryCoverage: incoming.geometryCoverage,
            readinessChecks: incoming.readinessChecks, caddieContextSeeds: incoming.caddieContextSeeds,
            weatherSnapshot: incoming.weatherSnapshot, clubProfiles: incoming.clubProfiles,
            caddieDecisionEndpoint: incoming.caddieDecisionEndpoint,
            offlinePackageStatus: incoming.offlinePackageStatus, eventCursor: incoming.eventCursor,
            recentHistory: incoming.recentHistory, cachedCaddieRules: incoming.cachedCaddieRules,
            generatedAt: incoming.generatedAt, readinessState: incoming.readinessState,
            enrichmentState: incoming.enrichmentState
        )
        XCTAssertFalse(current.mapFactsCompatible(with: mismatched))
        XCTAssertEqual(current.mergingMapFacts(from: mismatched), current)
    }

    func test_j5_4_green_edges_and_live_position_ranges() throws {
        // At 1 px/m the rectangular green is 20m wide x 40m deep. The centred flag
        // is 20m from front/back and 10m from either side -> 22/22/11/11 yards.
        let rectangle: [[Double]] = [[0, 0], [20, 0], [20, 40], [0, 40]]
        // A centred notch removes the upper middle. Flag at (5,20), image-up axis:
        // first forward intersection y=10, not the distant top lobe y=0.
        let concave: [[Double]] = [[0, 0], [4, 0], [4, 10], [6, 10], [6, 0], [10, 0], [10, 40], [0, 40]]
        for (id, outline, flag, expected) in [
            ("rectangle", rectangle, [10.0, 20.0], [22, 22, 11, 11]),
            ("concave-notch", concave, [5.0, 20.0], [22, 11, 5, 5]),
            ("on-edge", rectangle, [0.0, 20.0], [22, 22, 0, 22]),
        ] {
            let edges = try XCTUnwrap(GreenEdgeDistances.resolve(flagPx: flag, outlinePx: outline,
                referencePx: nil, pixelsPerMetre: 1), id)
            XCTAssertEqual([edges.front.yards, edges.back.yards, edges.left.yards, edges.right.yards], expected, id)
        }
        // Great-circle distances on the equator: .001 degrees = 111.1949m = 121.604 yd.
        // After moving north by .001 degrees every F/M/B distance falls by 122 yards.
        let positions: [(String, Double, [Int])] = [
            ("tee", 0, [243, 365, 486]), ("after-tee", 0.001, [122, 243, 365]),
        ]
        for (id, latitude, expected) in positions {
            let actual = [0.002, 0.003, 0.004].map { GeoDistance.yards(from: latitude, 0, to: $0, 0) }
            XCTAssertEqual(actual, expected.map(Optional.some), id)
        }
        let clamped = try XCTUnwrap(LivePolygonGeometry.nearestPoint(CGPoint(x: 30, y: 20), on: rectangle.map { CGPoint(x: $0[0], y: $0[1]) }))
        XCTAssertEqual(clamped, CGPoint(x: 20, y: 20), "flag dragged beyond right edge attaches to boundary")
        XCTAssertNil(GeoDistance.yards(from: 0, 0, to: nil, nil))
        XCTAssertNil(GreenEdgeDistances.resolve(flagPx: [10, 20], outlinePx: [], referencePx: nil, pixelsPerMetre: 1))
    }

    /// C136: the selected Tee is the single distance origin for the static card and the caddie
    /// before the first stroke. The test drives the prep/package request path.
    func test_j5_4_selected_tee_static_golden_and_atomic_live_fallback() throws {
        var prepInput = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(try ProductInputs.prep())) as? [String: Any]
        )
        prepInput["greenDistances"] = [
            "available": true, "frontM": 236.0, "middleM": 241.0, "backM": 246.0,
            "frontRouteM": 236.0, "backRouteM": 246.0,
        ]
        let prep: CoursePrepHole = try ProductSharedVectors.decode(prepInput)
        let package = try ProductInputs.package()
        let hole = try XCTUnwrap(package.holes.first)
        let staticRange = LiveGreenRangeYards(
            front: CoursePrepRoute.yards(fromMetres: try XCTUnwrap(prep.greenDistances?.frontM)),
            middle: CoursePrepRoute.yards(fromMetres: try XCTUnwrap(prep.greenDistances?.middleM)),
            back: CoursePrepRoute.yards(fromMetres: try XCTUnwrap(prep.greenDistances?.backM))
        )
        let firstFrame = LiveCaddieInput.firstFrameTee(greenDistances: prep.greenDistances, holeYards: hole.yards)
        XCTAssertEqual(firstFrame.distanceToPinM, prep.greenDistances?.middleM)
        XCTAssertEqual(
            CurrentHoleView.planningDistanceForCaddie(
                recordedShotCount: 0, hasLeftSelectedTee: true, manualM: nil,
                liveMiddleM: 999, staticMiddleM: prep.greenDistances?.middleM, holeYards: hole.yards
            ),
            prep.greenDistances?.middleM,
            "J5.4 opening planning uses the selected-Tee static middle"
        )
        XCTAssertEqual(
            CurrentHoleView.planningDistanceForCaddie(
                recordedShotCount: 1, hasLeftSelectedTee: false, manualM: 214,
                liveMiddleM: 999, staticMiddleM: prep.greenDistances?.middleM, holeYards: hole.yards
            ),
            214,
            "J5.4 Touch Target distance wins after the first stroke"
        )
        XCTAssertEqual(
            CurrentHoleView.planningDistanceForCaddie(
                recordedShotCount: 1, hasLeftSelectedTee: false, manualM: 188,
                liveMiddleM: 999, staticMiddleM: prep.greenDistances?.middleM, holeYards: hole.yards
            ),
            188,
            "J5.4 a dragged flag updates planning distance"
        )
        XCTAssertEqual(
            CurrentHoleView.planningDistanceForCaddie(
                recordedShotCount: 0, hasLeftSelectedTee: true, manualM: nil,
                liveMiddleM: 205, staticMiddleM: prep.greenDistances?.middleM, holeYards: hole.yards
            ),
            205,
            "J5.4 an unrecorded GPS fix beyond the selected Tee uses live distance"
        )
        let livePackage = try c136Package()
        let liveHole = try XCTUnwrap(livePackage.holes.first)
        let livePrep = try XCTUnwrap(livePackage.coursePrep?.holes.first)
        let liveMiddle = try XCTUnwrap(livePrep.greenDistances?.middleM)
        let openingProvider = LocationProvider()
        let openingView = CurrentHoleView(
            package: livePackage, hole: liveHole, locationProvider: openingProvider
        )
        let openingHost = hostCurrentHole(openingView)
        defer { openingHost.window.isHidden = true; openingHost.window.rootViewController = nil }
        let openingRange = openingHost.controller.rootView.displayedGreenRangeYardsForTesting()
        XCTAssertEqual(openingRange.middle, CoursePrepRoute.yards(fromMetres: liveMiddle),
                       "J5.4 the rendered opening ladder uses the selected tee")
        XCTAssertEqual(openingHost.controller.rootView.caddiePlanningDistanceForTesting(), liveMiddle,
                       "J5.4 the caddie request uses the same opening tee middle")
        let tee = CLLocationCoordinate2D(
            latitude: try XCTUnwrap(liveHole.teeLatitude), longitude: try XCTUnwrap(liveHole.teeLongitude)
        )
        let moved = CLLocationCoordinate2D(latitude: try XCTUnwrap(liveHole.teeLatitude) + 0.001,
                                           longitude: try XCTUnwrap(liveHole.teeLongitude))
        openingHost.controller.rootView.setPlanningCoordinateForTesting(moved)
        XCTAssertEqual(try XCTUnwrap(openingHost.controller.rootView.caddiePlanningDistanceForTesting()),
                       GeoDistance.haversineMetres(moved.latitude, moved.longitude,
                                                   try XCTUnwrap(livePrep.greenDistances?.middleLat),
                                                   try XCTUnwrap(livePrep.greenDistances?.middleLon)), accuracy: 0.01,
                       "J5.4 GPS beyond the tee threshold drives the opening plan")

        // J5.4/r7 drives the same hosted view state through clubhouse, tee and fairway positions.
        let clubhouse = CLLocationCoordinate2D(
            latitude: tee.latitude + 0.001,
            longitude: tee.longitude + 0.002
        )
        let fairway = CLLocationCoordinate2D(
            // The second projected route point in c33-32850-hole1 is about 130 m from the tee.
            latitude: 39.16544454946022,
            longitude: 116.99388744815977
        )
        let clubhouseProvider = LocationProvider()
        let clubhouseHost = hostCurrentHole(CurrentHoleView(
            package: livePackage, hole: liveHole, locationProvider: clubhouseProvider
        ))
        defer { clubhouseHost.window.isHidden = true; clubhouseHost.window.rootViewController = nil }
        clubhouseHost.controller.rootView.setPlanningCoordinateForTesting(clubhouse)
        XCTAssertEqual(
            clubhouseHost.controller.rootView.caddiePlanningDistanceForTesting(), liveMiddle,
            "clubhouse/off-hole opening state keeps the selected-Tee static middle"
        )
        XCTAssertNil(
            clubhouseHost.controller.rootView.caddieCoordinateForTesting(),
            "clubhouse/off-hole opening state must omit the request coordinate"
        )

        let teeProvider = LocationProvider()
        let teeHost = hostCurrentHole(CurrentHoleView(
            package: livePackage, hole: liveHole, locationProvider: teeProvider
        ))
        defer { teeHost.window.isHidden = true; teeHost.window.rootViewController = nil }
        teeHost.controller.rootView.setPlanningCoordinateForTesting(tee)
        XCTAssertEqual(
            teeHost.controller.rootView.caddiePlanningDistanceForTesting(), liveMiddle,
            "standing on the selected Tee keeps the static middle"
        )
        XCTAssertNotNil(
            teeHost.controller.rootView.caddieCoordinateForTesting(),
            "standing on the selected Tee still sends the on-hole coordinate"
        )

        let fairwayProvider = LocationProvider()
        let fairwayHost = hostCurrentHole(CurrentHoleView(
            package: livePackage, hole: liveHole, locationProvider: fairwayProvider
        ))
        defer { fairwayHost.window.isHidden = true; fairwayHost.window.rootViewController = nil }
        fairwayHost.controller.rootView.setPlanningCoordinateForTesting(fairway)
        XCTAssertEqual(
            try XCTUnwrap(fairwayHost.controller.rootView.caddiePlanningDistanceForTesting()),
            GeoDistance.haversineMetres(
                fairway.latitude, fairway.longitude,
                try XCTUnwrap(livePrep.greenDistances?.middleLat),
                try XCTUnwrap(livePrep.greenDistances?.middleLon)
            ), accuracy: 0.01,
            "on-hole fairway GPS beyond the Tee threshold drives live planning"
        )
        XCTAssertNotNil(
            fairwayHost.controller.rootView.caddieCoordinateForTesting(),
            "on-hole fairway opening state must send the request coordinate"
        )

        let target = CLLocationCoordinate2D(latitude: moved.latitude + 0.0003, longitude: moved.longitude)
        let targetDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: targetDirectory) }
        let targetStore = OfflineStore(directoryURL: targetDirectory)
        try targetStore.appendEvent(LiveRoundEventBuilder(roundId: livePackage.roundId).makeLocationEvent(
            hole: liveHole.number, coordinate: moved, horizontalAccuracyM: 5,
            targetCoordinate: target, targetKind: "target"
        ))
        let targetState = try targetStore.restoreLiveRoundState(
            roundId: livePackage.roundId, package: livePackage
        )
        let targetHost = hostCurrentHole(CurrentHoleView(
            package: livePackage, hole: liveHole, offlineStore: targetStore, liveRoundState: targetState
        ))
        defer { targetHost.window.isHidden = true; targetHost.window.rootViewController = nil }
        XCTAssertEqual(try XCTUnwrap(targetHost.controller.rootView.caddiePlanningDistanceForTesting()),
                       GeoDistance.haversineMetres(tee.latitude, tee.longitude, target.latitude, target.longitude), accuracy: 0.01,
                       "J5.4 Touch Target remains the post-shot planning source")
        let pin = CLLocationCoordinate2D(latitude: moved.latitude + 0.0005, longitude: moved.longitude)
        let pinDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: pinDirectory) }
        let pinStore = OfflineStore(directoryURL: pinDirectory)
        try pinStore.appendEvent(LiveRoundEventBuilder(roundId: livePackage.roundId).makeLocationEvent(
            hole: liveHole.number, coordinate: moved, horizontalAccuracyM: 5,
            targetCoordinate: pin, targetKind: "pin"
        ))
        let pinState = try pinStore.restoreLiveRoundState(
            roundId: livePackage.roundId, package: livePackage
        )
        let pinHost = hostCurrentHole(CurrentHoleView(
            package: livePackage, hole: liveHole, offlineStore: pinStore, liveRoundState: pinState
        ))
        defer { pinHost.window.isHidden = true; pinHost.window.rootViewController = nil }
        XCTAssertEqual(try XCTUnwrap(pinHost.controller.rootView.caddiePlanningDistanceForTesting()),
                       GeoDistance.haversineMetres(tee.latitude, tee.longitude, pin.latitude, pin.longitude), accuracy: 0.01,
                       "J5.4 dragging the flag updates the post-shot planning source")

        XCTAssertEqual(
            LiveGreenRangePresentation.resolve(
                live: LiveGreenRangeYards(front: 220, middle: nil, back: 437),
                staticFallback: staticRange
            ),
            staticRange,
            "one missing live edge keeps the complete static group"
        )
    }

    func test_j5_5_saved_gps_and_accuracy_or_unknown_score_position() throws {
        for (id, accuracy) in [("accurate", 5.0), ("poor", 120.0)] {
            let event = LiveRoundEventBuilder(roundId: "synthetic", idFactory: { id }).makeLocationEvent(
                hole: 1, coordinate: CLLocationCoordinate2D(latitude: 0.001, longitude: 0.002), horizontalAccuracyM: accuracy)
            XCTAssertEqual(event.payload["latitude"], .number(0.001), id)
            XCTAssertEqual(event.payload["longitude"], .number(0.002), id)
            XCTAssertEqual(event.payload["horizontalAccuracyM"], .number(accuracy), id)
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            let store = OfflineStore(directoryURL: directory)
            try store.appendEvent(event)
            try store.appendEvent(LiveRoundEventBuilder(roundId: "synthetic").makeScoreEvent(hole: 1, strokes: 4))
            let restored = try XCTUnwrap(store.restoreLiveRoundState(roundId: "synthetic", package: ProductInputs.package()).holeState(for: 1))
            XCTAssertEqual(restored.score, 4, id + " score remains saveable")
            XCTAssertEqual(restored.horizontalAccuracyM, accuracy, id + " precision remains visible to the view")
            if accuracy == 5 {
                XCTAssertEqual(restored.latitude, 0.001, id)
                XCTAssertEqual(restored.longitude, 0.002, id)
            } else {
                XCTAssertNil(restored.latitude, id + " location must be unknown")
                XCTAssertNil(restored.longitude, id + " location must be unknown")
            }
        }
        // Scoring without a location still writes the same three score facts, and no invented GPS.
        for phoneShots in [0, 2] {
            let draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: phoneShots)
            let events = LiveScoreSubmission.events(roundId: "synthetic", draft: draft, note: "", timestamp: "2026-10-23T00:00:00Z")
            XCTAssertEqual(events.map(\.kind), [.score, .putt, .penalty], "no GPS, shots=\(phoneShots)")
            XCTAssertTrue(events.allSatisfy { $0.payload["latitude"] == nil && $0.payload["longitude"] == nil })
        }
    }

    func test_j5_5_poor_followup_location_keeps_previous_good_coordinates() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        var eventIndex = 0
        let builder = LiveRoundEventBuilder(roundId: "synthetic", idFactory: {
            eventIndex += 1
            return "location-\(eventIndex)"
        })
        try store.appendEvent(builder.makeLocationEvent(
            hole: 1,
            coordinate: CLLocationCoordinate2D(latitude: 0.001, longitude: 0.002),
            horizontalAccuracyM: 5
        ))
        try store.appendEvent(builder.makeLocationEvent(
            hole: 1,
            coordinate: CLLocationCoordinate2D(latitude: 0.009, longitude: 0.009),
            horizontalAccuracyM: 120
        ))

        let state = try XCTUnwrap(
            store.restoreLiveRoundState(roundId: "synthetic", package: ProductInputs.package())
                .holeState(for: 1)
        )
        XCTAssertEqual(state.latitude, 0.001)
        XCTAssertEqual(state.longitude, 0.002)
        XCTAssertEqual(state.horizontalAccuracyM, 5)
    }

    func test_j8_3_optional_sections_old_and_future_data_decode_without_losing_facts() throws {
        let rows: [(String, [String: Any], Int?, Bool)] = [
            ("old", ["hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 328, "route_len_m": 300, "steps": [], "cautions": [], "hazards": [:]], nil, false),
            ("new-unknown-fields", ["hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 328, "route_len_m": 300, "steps": [], "cautions": [], "hazards": [:], "teeYards": 300, "future": ["new": true]], 300, false),
            ("unknown-outline", ["hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 328, "route_len_m": 300, "steps": [], "cautions": [], "hazards": [:], "fairwayOutline": ["version": 999, "polygons": []]], nil, false),
        ]
        for (id, input, tee, hasOutline) in rows {
            let prep: CoursePrepHole = try ProductSharedVectors.decode(input)
            XCTAssertEqual(prep.hole, 1, id)
            XCTAssertEqual(prep.par, 4, id)
            XCTAssertEqual(prep.teeYards, tee, id)
            XCTAssertEqual(prep.fairwayOutline != nil, hasOutline, id)
            XCTAssertNil(prep.greenDistances, id)
        }
        // A broken optional analytics section must not erase the valid score summary.
        let stats: MobileStats = try ProductSharedVectors.decode([
            "summary": ["totalRounds": 3, "average18": 82], "scoring": "future-shape", "future": true,
        ])
        XCTAssertEqual(stats.summary?.totalRounds, 3)
        XCTAssertEqual(stats.summary?.average18, 82)
        XCTAssertNil(stats.scoring)
    }
}
