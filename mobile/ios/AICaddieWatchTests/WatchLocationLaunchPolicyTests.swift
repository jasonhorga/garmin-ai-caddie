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
}
