#if !SWIFT_PACKAGE
import CoreLocation
import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class PrepRoundStateTests: XCTestCase {
    func testPrepEventIsDroppedWithoutOfflineRoundState() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("c30-prep-(UUID().uuidString)", isDirectory: true)
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
}
#endif
