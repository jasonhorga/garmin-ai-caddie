import XCTest
@testable import AICaddieWatch

final class WatchHoleMapViewportTests: XCTestCase {
    func testCompactRuntimeViewportFitsTheFlagWithoutChangingPlayerAnchor() {
        let scale = WatchHoleMapViewport.effectiveRestingScale(
            requestedScale: WatchHoleMapView.restingCrownScale,
            viewportHeight: 195,
            playerAnchorFraction: 0.72,
            playerImageY: 702,
            pinImageY: 279
        )

        let playerY = 195.0 * 0.72
        let pinY = playerY + (279.0 - 702.0) * scale
        XCTAssertGreaterThanOrEqual(pinY, WatchHoleMapViewport.flagTopClearance)
        XCTAssertLessThan(scale, WatchHoleMapView.restingCrownScale)
    }

    func testApprovedSnapshotViewportKeepsTheExistingRestingScale() {
        let scale = WatchHoleMapViewport.effectiveRestingScale(
            requestedScale: WatchHoleMapView.restingCrownScale,
            viewportHeight: 242,
            playerAnchorFraction: 0.72,
            playerImageY: 702,
            pinImageY: 279
        )

        XCTAssertEqual(scale, WatchHoleMapView.restingCrownScale, accuracy: 0.0001)
    }
}
