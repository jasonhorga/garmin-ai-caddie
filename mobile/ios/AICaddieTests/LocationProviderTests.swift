import CoreLocation
import XCTest
@testable import AICaddie

final class LocationProviderTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    func testRejectsInvalidInaccurateAndStaleSamples() {
        XCTAssertFalse(LocationProvider.isUsable(location(latitude: 91), now: now))
        XCTAssertFalse(LocationProvider.isUsable(location(longitude: 181), now: now))
        XCTAssertFalse(LocationProvider.isUsable(location(accuracy: -1), now: now))
        XCTAssertFalse(LocationProvider.isUsable(location(age: 301), now: now))
        XCTAssertFalse(LocationProvider.isUsable(location(age: -301), now: now))
    }

    func testAcceptsFreshBoundarySamplesAndSkipsAnInvalidLastValue() throws {
        let first = location(latitude: 40.0, longitude: 116.0, age: 300)
        let newestValid = location(latitude: 40.1, longitude: 116.1, age: 2)
        let staleLast = location(latitude: 39.0, longitude: 115.0, age: 600)

        XCTAssertTrue(LocationProvider.isUsable(first, now: now))
        let selected = try XCTUnwrap(LocationProvider.latestUsableLocation(
            in: [first, newestValid, staleLast],
            now: now
        ))
        XCTAssertEqual(selected.coordinate.latitude, 40.1)
        XCTAssertEqual(selected.coordinate.longitude, 116.1)
    }

    private func location(
        latitude: Double = 40,
        longitude: Double = 116,
        accuracy: Double = 5,
        age: TimeInterval = 0
    ) -> CLLocation {
        CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            altitude: 0,
            horizontalAccuracy: accuracy,
            verticalAccuracy: 5,
            timestamp: now.addingTimeInterval(-age)
        )
    }
}
