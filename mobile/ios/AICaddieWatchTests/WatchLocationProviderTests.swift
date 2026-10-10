import CoreLocation
import XCTest
@testable import AICaddieWatch

final class WatchLocationProviderTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    override func tearDown() {
        unsetenv("UITEST_LOCATION_AUTHORIZATION")
        super.tearDown()
    }

    /// Field report 2026-10-10: standing still under a 3 m distance filter produced no callbacks, the
    /// fix aged past the 15 s rangefinder window and F/M/B showed 999 "等待定位". Every fix is delivered.
    func testDeliversEveryFixSoAStandingPlayerKeepsALiveRange() {
        let manager = CLLocationManager()
        _ = WatchLocationProvider(manager: manager)
        XCTAssertEqual(manager.distanceFilter, kCLDistanceFilterNone)
        XCTAssertEqual(manager.desiredAccuracy, kCLLocationAccuracyBest)
    }

    /// Battery report 2026-10-10: every published fix or heading redraws the round UI. A standing
    /// player's 1 Hz fixes are republished only on a 2 m move, a 3 m accuracy change, or every 5 s
    /// (inside the 15 s rangefinder and 10 s swing-speed windows).
    func testUnchangedFixesAreRepublishedOnlyOftenEnoughToStayLive() {
        let previous = WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5,
            capturedAt: ISO8601DateFormatter().string(from: now)
        )
        let publishedAt = now
        XCTAssertTrue(WatchLocationProvider.shouldPublish(previous: nil, previousPublishedAt: nil, next: location(), now: now))
        XCTAssertFalse(WatchLocationProvider.shouldPublish(
            previous: previous, previousPublishedAt: publishedAt, next: location(), now: now.addingTimeInterval(1)
        ), "same spot, same accuracy, 1 s later")
        XCTAssertTrue(WatchLocationProvider.shouldPublish(
            previous: previous, previousPublishedAt: publishedAt,
            next: location(latitude: 40.00003), now: now.addingTimeInterval(1)
        ), "a 3 m step")
        XCTAssertTrue(WatchLocationProvider.shouldPublish(
            previous: previous, previousPublishedAt: publishedAt, next: location(accuracy: 12), now: now.addingTimeInterval(1)
        ), "accuracy changed")
        let riding = WatchLocationFix(
            coordinate: previous.coordinate, horizontalAccuracyM: 5,
            capturedAt: previous.capturedAt, speedMps: 4, speedAccuracyMps: 1
        )
        XCTAssertTrue(WatchLocationProvider.shouldPublish(
            previous: riding, previousPublishedAt: publishedAt, next: location(speed: 0.5, speedAccuracy: 1), now: now.addingTimeInterval(1)
        ), "the cart stopped: the swing riding gate must see it")
        XCTAssertTrue(WatchLocationProvider.shouldPublish(
            previous: riding, previousPublishedAt: publishedAt, next: location(speed: 4, speedAccuracy: 3),
            now: now.addingTimeInterval(1)
        ), "speed turned too uncertain for the riding gate")
        XCTAssertTrue(WatchLocationProvider.shouldPublish(
            previous: previous, previousPublishedAt: publishedAt, next: location(),
            now: now.addingTimeInterval(WatchLocationProvider.stationaryRepublishSeconds)
        ), "standing still: republished before the 15 s window lapses")
        XCTAssertLessThan(
            WatchLocationProvider.stationaryRepublishSeconds + 2,
            WatchLocationProvider.maximumLiveRangefinderAgeSeconds
        )
        XCTAssertLessThan(
            WatchLocationProvider.stationaryRepublishSeconds + 2,
            WatchSwingCollectionSession.maximumSpeedAgeS,
            "1 s fix cadence + 1 s ISO8601 truncation"
        )
    }

    func testHeadingRunsOnlyWhileAPageThatShowsItIsOpen() {
        let provider = WatchLocationProvider(manager: CLLocationManager())
        XCTAssertFalse(provider.wantsHeadingUpdates, "off for the round by default")
        provider.setHeadingUpdates(true)
        XCTAssertTrue(provider.wantsHeadingUpdates)
        provider.setHeadingUpdates(false)
        XCTAssertFalse(provider.wantsHeadingUpdates)
        XCTAssertNil(provider.latestHeading, "a stale arrow never outlives the page")
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
        age: TimeInterval = 0,
        speed: Double = -1,
        speedAccuracy: Double = -1
    ) -> CLLocation {
        CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            altitude: 0,
            horizontalAccuracy: accuracy,
            verticalAccuracy: 5,
            course: -1,
            courseAccuracy: -1,
            speed: speed,
            speedAccuracy: speedAccuracy,
            timestamp: now.addingTimeInterval(-age)
        )
    }
}
