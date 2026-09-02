import CoreLocation
import XCTest
@testable import AICaddie

final class LocationProviderTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    override func tearDown() {
        unsetenv("UITEST_LOCATION_AUTHORIZATION")
        unsetenv("UITEST_GPS_LAT")
        unsetenv("UITEST_GPS_LON")
        super.tearDown()
    }

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

    func testSimulatedDenialSurvivesARealManagerAuthorizationCallback() {
        setenv("UITEST_LOCATION_AUTHORIZATION", "denied", 1)
        let provider = LocationProvider()

        XCTAssertEqual(provider.authorizationStatus, .denied)
        provider.locationManagerDidChangeAuthorization(CLLocationManager())
        XCTAssertEqual(provider.authorizationStatus, .denied)
        XCTAssertNil(provider.latestFix)
    }

    func testInjectedFixMovesImmediatelyForAMultiHoleJourney() throws {
        setenv("UITEST_GPS_LAT", "40.0454995", 1)
        setenv("UITEST_GPS_LON", "116.5461531", 1)
        let provider = LocationProvider()
        provider.startUpdatingLocation()

        let moved = try XCTUnwrap(provider.moveSimulatedFixForUITest(
            latitude: 40.0474938219,
            longitude: 116.5442115447
        ))
        let latest = try XCTUnwrap(provider.latestFix)

        XCTAssertEqual(moved.coordinate.latitude, 40.0474938219, accuracy: 0.0000001)
        XCTAssertEqual(moved.coordinate.longitude, 116.5442115447, accuracy: 0.0000001)
        XCTAssertEqual(latest.coordinate.latitude, moved.coordinate.latitude, accuracy: 0.0000001)
        XCTAssertEqual(latest.coordinate.longitude, moved.coordinate.longitude, accuracy: 0.0000001)
    }

    func testUITestMovementNeverCreatesAFixWithoutInjectedGPS() {
        setenv("UITEST_LOCATION_AUTHORIZATION", "authorized", 1)
        let provider = LocationProvider()

        XCTAssertNil(provider.moveSimulatedFixForUITest(latitude: 40.0, longitude: 116.0))
        XCTAssertNil(provider.latestFix)
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
