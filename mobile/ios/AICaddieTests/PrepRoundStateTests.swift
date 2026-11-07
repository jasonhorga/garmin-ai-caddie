#if !SWIFT_PACKAGE
import CoreLocation
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

@MainActor
final class PrepRoundStateTests: XCTestCase {
    func testPrepEventIsDroppedWithoutOfflineRoundState() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c30-prep-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil)
        let package = try LiveRoundPackageFixture.package()
        model.enterPrepMode(with: package)

        let event = LiveRoundEventBuilder(roundId: package.roundId).makeLocationEvent(
            hole: package.holes[0].number,
            coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5,
            targetCoordinate: nil,
            targetKind: nil
        )
        model.handleEvent(event)

        XCTAssertNil(model.liveRoundState)
        XCTAssertTrue(try store.loadEvents().isEmpty)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
    }

    func testFirstStrokePersistsStartHoleAndRestoresIt() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c30-start-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        model.enterPrepMode(with: package, hole: 5)

        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 5))
        XCTAssertEqual(model.liveRoundState?.startHole, 5)
        XCTAssertEqual(model.liveRoundState?.activeHole, 5)

        let restored = try XCTUnwrap(store.restoreLiveRoundState(roundId: package.roundId, package: package))
        XCTAssertEqual(restored.startHole, 5)
        XCTAssertEqual(restored.activeHole, 5)
    }

    func testWholeCoursePrepHasAllHolesAndStartsAtTheFirstStrokeHole() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c99-whole-course-prep-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil)
        let package = try LiveRoundPackageFixture.wholeCourse(dataMode: "local")

        model.enterPrepMode(with: package)

        XCTAssertNil(model.liveRoundState)
        XCTAssertEqual(Set(model.prepPackage?.holes.map(\.number) ?? []), Set(1...18))
        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 10))
        XCTAssertEqual(model.liveRoundState?.activeHole, 10)
        XCTAssertEqual(model.liveRoundState?.startHole, 10)
    }

    func testUndoEmptyStartReturnsToPrepHole() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c30-undo-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        model.enterPrepMode(with: package, hole: 5)
        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 5))

        XCTAssertEqual(model.liveRoundState?.canUndoRoundStart, true)

        model.undoRoundStart()

        XCTAssertNil(model.liveRoundState)
        XCTAssertEqual(model.pendingLiveHole, 5)
        XCTAssertNotNil(model.prepPackage)
        XCTAssertEqual(model.prepTeeOptions, [package.course.teeBox])
        XCTAssertTrue(try store.loadEvents().isEmpty)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertFalse(try store.hasLiveRoundProgress())
    }

    // J5.9: once a stroke is durable, undo-start must never erase the round's records.
    func testFirstRecordedStrokePreventsUndoStart() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil)
        model.enterPrepMode(with: package, hole: 5)
        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 5))
        let event = LiveRoundEventBuilder(roundId: package.roundId).makeLocationEvent(
            hole: 5, coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5, targetCoordinate: nil, targetKind: nil
        )
        model.handleEvent(event)
        let events = try store.loadEvents()

        XCTAssertEqual(model.liveRoundState?.canUndoRoundStart, false)
        model.undoRoundStart()

        XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(try store.loadEvents(), events)
        XCTAssertNotNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertTrue(try store.hasLiveRoundProgress())
    }

    func testUndoStartRechecksDurableEventsAcrossAllHoles() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil)
        model.enterPrepMode(with: package, hole: 5)
        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 5))
        // A Watch/replay write can reach disk before the mounted phone page has refreshed.
        let before = try XCTUnwrap(model.liveRoundState)
        let event = LiveRoundEvent(
            eventId: "other-hole-location", roundId: package.roundId,
            timestamp: "2026-06-20T00:00:00Z", hole: 6, kind: .location,
            payload: ["latitude": .number(40), "longitude": .number(116)]
        )
        try store.appendEvent(event)
        XCTAssertEqual(model.liveRoundState?.canUndoRoundStart, true, "control: cached page is stale")
        let after = try store.restoreLiveRoundState(roundId: package.roundId, package: package)
        XCTAssertFalse(after.canUndoRoundStart)
        XCTAssertNotEqual(
            LiveHolePageRoundInput(before, hole: 5), LiveHolePageRoundInput(after, hole: 5),
            "J5.9: even a frozen adjacent page must hide undo when another hole records a stroke"
        )

        model.undoRoundStart()

        XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(try store.loadEvents().map(\.eventId), [event.eventId])
        XCTAssertNotNil(try store.loadRoundPackage(roundId: package.roundId))
    }

    func testRecoveredInProgressRoundRejectsUndoStartAndKeepsEvents() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        try store.saveRoundPackage(package)
        // Server replay into an empty install: no saveRoundStart/local progress file.
        _ = try store.applyReplayEvents([
            LiveRoundEvent(eventId: "recovered-first-stroke", roundId: package.roundId,
                           timestamp: "2026-06-20T00:00:00Z", hole: 5, kind: .score,
                           payload: ["strokes": .number(1)], startHole: 5),
        ])
        XCTAssertFalse(try store.hasLiveRoundProgress())
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil, garminSessionStore: nil)
        await model.bootstrap()
        XCTAssertEqual(model.liveRoundState?.startHole, 5)
        XCTAssertEqual(model.liveRoundState?.canUndoRoundStart, false)
        let events = try store.loadEvents()
        let hadProgress = try store.hasLiveRoundProgress()
        model.undoRoundStart()
        XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(try store.loadEvents(), events)
        XCTAssertNotNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertEqual(try store.hasLiveRoundProgress(), hadProgress)
    }

    func testPrepOpenAndHoleChangePassPriorityHoleThroughModel() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c30-priority-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let responseData = try JSONEncoder().encode(package)
        let lock = NSLock()
        var priorities: [Int] = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(CapturingURLProtocol.self)
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            if request.url?.path == "/api/v2/mobile/courses/\(package.course.globalId)/package" {
                let query = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
                if let value = query?.first(where: { $0.name == "priority_hole" })?.value.flatMap(Int.init) {
                    lock.lock()
                    priorities.append(value)
                    lock.unlock()
                }
                return (
                    HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!,
                    responseData
                )
            }
            return (
                HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 404, httpVersion: nil, headerFields: nil)!,
                Data()
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let baseURL = try XCTUnwrap(URL(string: "https://prep-priority-model.example.test"))
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: baseURL,
            watchBridge: nil,
            syncClient: SyncClient(baseURL: baseURL, session: session)
        )
        let course = MobileCourseOption(
            globalId: package.course.globalId,
            name: package.course.name,
            holes: 9,
            teeBox: package.course.teeBox
        )

        XCTAssertTrue(model.openPrepCourse(course, hole: 5))
        await model.waitForPrepOpenForTesting()
        XCTAssertNotNil(model.prepPackage)
        XCTAssertEqual(lock.withLock { priorities }, [5])

        model.prioritizePrepHole(6)
        model.prioritizePrepHole(6)
        await model.waitForPrepPriorityForTesting()
        XCTAssertEqual(lock.withLock { priorities }, [5, 6])
        model.closePrepMode()
        await model.cancelPrepCourseDownloadForTesting()
    }

    func testDownloadedPrepDoesNotRefreshPriorityOrReplaceLocalPackage() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c30-downloaded-priority-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let source = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let prepHoles = source.holes.map { hole in
            CoursePrepHole(
                hole: hole.number,
                par: hole.par,
                parSource: "courseview",
                blueYards: hole.yards ?? 0,
                routeLenM: 360,
                route: [[0, 0, 0], [0, 360, 360]],
                geometryCoverage: "ready",
                map: CoursePrepMap(
                    image: "data:image/png;base64,AQID",
                    overlay: CoursePrepOverlay(
                        w: 720,
                        h: 1120,
                        ppm: 1,
                        ln: 360,
                        route: [[360, 1000, 0], [360, 100, 360]]
                    )
                )
            )
        }
        let ready = source.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: source.course.globalId,
            holes: prepHoles,
            missingData: nil
        ))
        try store.saveCourseTemplate(ready)
        for hole in ready.holes {
            XCTAssertTrue(try store.saveCourseTopoImage(
                validOnePixelPNGData(),
                globalId: hole.sourceGlobalId,
                localHole: hole.sourceLocalHole
            ))
        }
        let course = MobileCourseOption(
            globalId: ready.course.globalId,
            name: ready.course.name,
            holes: ready.holes.count,
            teeBox: ready.course.teeBox
        )
        let packagePath = "/api/v2/mobile/courses/\(ready.course.globalId)/package"
        let lock = NSLock()
        var packageRequests = 0
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = testProtocolClasses(CapturingURLProtocol.self)
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            if url.path == packagePath {
                lock.withLock { packageRequests += 1 }
            }
            return (
                HTTPURLResponse(url: url, statusCode: 404, httpVersion: nil, headerFields: nil)!,
                Data()
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: URL(string: "https://downloaded-priority.example.test"),
            watchBridge: nil,
            syncClient: SyncClient(
                baseURL: URL(string: "https://downloaded-priority.example.test")!,
                session: session
            )
        )
        let key = PrepCourseDownloadRecord.key(globalId: course.globalId, teeBox: course.teeBox ?? "blue")
        XCTAssertTrue(model.downloadedCourseKeys.contains(key))
        XCTAssertTrue(model.openPrepCourse(course, hole: 5))
        await model.waitForPrepOpenForTesting()
        let openedRoundID = try XCTUnwrap(model.prepPackage?.roundId)
        model.prioritizePrepHole(6)
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(lock.withLock { packageRequests }, 0)
        XCTAssertEqual(model.prepPackage?.roundId, openedRoundID)
        model.closePrepMode()
        await model.cancelPrepCourseDownloadForTesting()
    }
}
#endif
