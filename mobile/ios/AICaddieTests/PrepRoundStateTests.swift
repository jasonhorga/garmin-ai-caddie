#if !SWIFT_PACKAGE
import CoreLocation
import Foundation
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
        XCTAssertTrue(try store.loadEvents().isEmpty)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertNil(try store.loadLiveRoundProgress())
    }
}
#endif
