import XCTest
@testable import AICaddieWatch

final class WatchLocationLaunchPolicyTests: XCTestCase {
    func testGPSPreheatStartsLocationBeforeARound() {
        XCTAssertTrue(
            WatchLocationLaunchPolicy.shouldStartLocationServices(
                hasActiveRound: false,
                gpsPreheatEnabled: true,
                arguments: ["AI Caddie"]
            )
        )
    }

    func testDisablingGPSPreheatStopsIdleLocation() {
        XCTAssertFalse(
            WatchLocationLaunchPolicy.shouldStartLocationServices(
                hasActiveRound: false,
                gpsPreheatEnabled: false,
                arguments: ["AI Caddie"]
            )
        )
    }

    func testActiveRoundKeepsLocationOnWhenPreheatIsDisabled() {
        XCTAssertTrue(
            WatchLocationLaunchPolicy.shouldStartLocationServices(
                hasActiveRound: true,
                gpsPreheatEnabled: false,
                arguments: ["AI Caddie"]
            )
        )
    }

    func testScreenshotLaunchDoesNotStartLocationServices() {
        let arguments = ["AI Caddie", "-uitest-screen", "score-next-tee-candidate"]

        XCTAssertFalse(
            WatchLocationLaunchPolicy.shouldStartLocationServices(
                hasActiveRound: true,
                gpsPreheatEnabled: true,
                arguments: arguments
            )
        )
    }

    func testActiveRoundKeepsWorkoutSessionWithoutAutoShotDependency() {
        XCTAssertTrue(
            WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(
                hasActiveRound: true,
                arguments: ["AI Caddie"],
                environment: [:]
            )
        )
        XCTAssertFalse(
            WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(
                hasActiveRound: false,
                arguments: ["AI Caddie"],
                environment: [:]
            )
        )
    }

    func testDeterministicWatchEvidenceDoesNotOpenHealthAuthorization() {
        XCTAssertFalse(
            WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(
                hasActiveRound: true,
                arguments: ["AI Caddie", "-uitest-screen", "hole-map"],
                environment: [:]
            )
        )
        XCTAssertFalse(
            WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(
                hasActiveRound: true,
                arguments: ["AI Caddie"],
                environment: ["UITEST_GPS_LAT": "40", "UITEST_GPS_LON": "116"]
            )
        )
    }
}
