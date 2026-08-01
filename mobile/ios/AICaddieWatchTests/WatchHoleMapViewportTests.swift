import XCTest
@testable import AICaddieWatch

final class WatchHoleMapViewportTests: XCTestCase {
    func testEdgeBackGestureAcceptsAHorizontalSwipeFromTheLeftEdge() {
        XCTAssertTrue(WatchEdgeBackGesture.shouldTrigger(
            startX: 20,
            translation: CGSize(width: 72, height: 8)
        ))
    }

    func testEdgeBackGestureRejectsSwipesThatStartAwayFromTheLeftEdge() {
        XCTAssertFalse(WatchEdgeBackGesture.shouldTrigger(
            startX: 48,
            translation: CGSize(width: 72, height: 8)
        ))
    }

    func testEdgeBackGestureRejectsMostlyVerticalMovement() {
        XCTAssertFalse(WatchEdgeBackGesture.shouldTrigger(
            startX: 20,
            translation: CGSize(width: 72, height: 64)
        ))
    }

    func testDistancePillMovesBelowMarkerWhenClockWouldCoverItsPreferredPosition() {
        let viewport = CGSize(width: 208, height: 248)
        let marker = CGPoint(x: 159.5, y: 40)
        let pillSize = CGSize(width: 68, height: 18)

        let center = WatchHoleMapViewport.distancePillCenter(
            marker: marker,
            pillSize: pillSize,
            viewportSize: viewport,
            preferredOffset: 20
        )

        let pillRect = CGRect(
            x: center.x - pillSize.width / 2,
            y: center.y - pillSize.height / 2,
            width: pillSize.width,
            height: pillSize.height
        )
        XCTAssertGreaterThan(center.y, marker.y)
        XCTAssertFalse(pillRect.intersects(WatchHoleMapViewport.systemTimeRect(in: viewport)))
    }

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

    func testHazardViewportReservesRoomForItsTopControls() {
        let viewportHeight = 319.0
        let playerAnchorFraction = 0.66
        let playerImageY = 923.0
        let hazardBackImageY = 426.2
        let scale = WatchHoleMapViewport.effectiveRestingScale(
            requestedScale: WatchHoleMapView.maximumCrownScale,
            viewportHeight: viewportHeight,
            playerAnchorFraction: playerAnchorFraction,
            playerImageY: playerImageY,
            pinImageY: hazardBackImageY,
            topClearance: 42
        )

        let edgeY = viewportHeight * playerAnchorFraction
            + (hazardBackImageY - playerImageY) * scale
        XCTAssertEqual(edgeY, 42, accuracy: 0.0001)
    }
}
