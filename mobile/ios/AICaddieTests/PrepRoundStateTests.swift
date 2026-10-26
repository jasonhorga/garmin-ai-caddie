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

    func testUndoFirstStrokeClearsLocalRoundAndReturnsToPrepHole() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c30-undo-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let model = LiveRoundAppModel(offlineStore: store, watchBridge: nil)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        model.enterPrepMode(with: package, hole: 5)
        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 5))

        model.undoRoundStart()

        XCTAssertNil(model.liveRoundState)
        XCTAssertEqual(model.pendingLiveHole, 5)
        XCTAssertNotNil(model.prepPackage)
        XCTAssertEqual(model.prepTeeOptions, [package.course.teeBox])
        XCTAssertTrue(try store.loadEvents().isEmpty)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertNil(try store.loadLiveRoundProgress())
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
        configuration.protocolClasses = [CapturingURLProtocol.self]
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
        for _ in 0..<100 where model.prepPackage == nil {
            try await Task.sleep(nanoseconds: 1_000_000)
        }
        XCTAssertNotNil(model.prepPackage)
        XCTAssertEqual(lock.withLock { priorities }, [5])

        model.prioritizePrepHole(6)
        model.prioritizePrepHole(6)
        for _ in 0..<100 where lock.withLock({ priorities.count }) < 2 {
            try await Task.sleep(nanoseconds: 1_000_000)
        }
        XCTAssertEqual(lock.withLock { priorities }, [5, 6])
    }
}
#endif
