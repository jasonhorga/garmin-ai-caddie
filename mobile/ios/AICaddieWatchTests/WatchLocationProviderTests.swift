import CoreLocation
import XCTest
@testable import AICaddieWatch

final class WatchLocationProviderTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    override func tearDown() {
        unsetenv("UITEST_LOCATION_AUTHORIZATION")
        super.tearDown()
    }

    func testRejectsInvalidNegativeAccuracyAndCachedSamples() {
        XCTAssertFalse(WatchLocationProvider.isUsable(location(latitude: 91), now: now))
        XCTAssertFalse(WatchLocationProvider.isUsable(location(longitude: 181), now: now))
        XCTAssertFalse(WatchLocationProvider.isUsable(location(accuracy: -1), now: now))
        XCTAssertFalse(WatchLocationProvider.isUsable(location(age: 301), now: now))
        XCTAssertFalse(WatchLocationProvider.isUsable(location(age: -301), now: now))
    }

    func testUsesNewestUsableWristFixInsteadOfBlindlyTakingLast() throws {
        let oldValid = location(latitude: 40.0, longitude: 116.0, age: 300)
        let newestValid = location(latitude: 40.2, longitude: 116.2, age: 1)
        let invalidLast = location(latitude: 42.0, longitude: 118.0, accuracy: -1)

        let selected = try XCTUnwrap(WatchLocationProvider.latestUsableLocation(
            in: [oldValid, newestValid, invalidLast],
            now: now
        ))
        XCTAssertEqual(selected.coordinate.latitude, 40.2)
        XCTAssertEqual(selected.coordinate.longitude, 116.2)
    }

    func testSimulatedDenialSurvivesARealManagerAuthorizationCallback() {
        setenv("UITEST_LOCATION_AUTHORIZATION", "denied", 1)
        let provider = WatchLocationProvider()

        XCTAssertEqual(provider.authorizationStatus, .denied)
        provider.locationManagerDidChangeAuthorization(CLLocationManager())
        XCTAssertEqual(provider.authorizationStatus, .denied)
        XCTAssertNil(provider.latestFix)
    }

    func testLiveRangefinderFixRequiresFreshAccuratePresentTimeGPS() {
        XCTAssertTrue(WatchLocationProvider.isLiveRangefinderFix(fix(age: 0), now: now))
        XCTAssertTrue(WatchLocationProvider.isLiveRangefinderFix(fix(age: 15), now: now))
        XCTAssertFalse(WatchLocationProvider.isLiveRangefinderFix(fix(age: 16), now: now))
        XCTAssertFalse(WatchLocationProvider.isLiveRangefinderFix(fix(age: -1), now: now))
        XCTAssertFalse(WatchLocationProvider.isLiveRangefinderFix(fix(accuracy: 15.1), now: now))
        XCTAssertFalse(WatchLocationProvider.isLiveRangefinderFix(fix(latitude: 91), now: now))
        XCTAssertFalse(WatchLocationProvider.isLiveRangefinderFix(
            WatchLocationFix(
                coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
                horizontalAccuracyM: 5,
                capturedAt: "not-a-date"
            ),
            now: now
        ))
    }

    private func fix(
        latitude: Double = 40,
        longitude: Double = 116,
        accuracy: Double = 5,
        age: TimeInterval = 0
    ) -> WatchLocationFix {
        WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            horizontalAccuracyM: accuracy,
            capturedAt: ISO8601DateFormatter().string(from: now.addingTimeInterval(-age))
        )
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
