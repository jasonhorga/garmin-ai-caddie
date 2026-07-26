import XCTest
@testable import AICaddieWatch

final class WatchLocationLaunchPolicyTests: XCTestCase {
    func testScreenshotLaunchDoesNotStartLocationServices() {
        let arguments = ["AI Caddie", "-uitest-screen", "score-next-tee-candidate"]

        XCTAssertFalse(WatchLocationLaunchPolicy.shouldStartLocationServices(arguments: arguments))
    }
}
