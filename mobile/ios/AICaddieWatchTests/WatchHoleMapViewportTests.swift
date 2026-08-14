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

    func testDistancePillStaysOutOfTheMaskedHoleRootDataColumn() {
        // SwiftUI lays out the 41 mm Watch in logical points; its screenshot is 352x430 pixels.
        // Testing with screenshot pixels would falsely allow a label twice as wide as the product.
        let viewport = CGSize(width: 176, height: 215)
        let dataColumnMaxX = viewport.width * 0.38
        let text = WatchHoleMapViewport.hazardDistanceText(
            kind: "沙",
            toYards: 999,
            overYards: 999,
            fullMap: false
        )
        let pillSize = WatchHoleMapViewport.distancePillSize(for: text)

        XCTAssertEqual(text, "沙 到999 过999")
        XCTAssertLessThanOrEqual(
            pillSize.width,
            viewport.width - dataColumnMaxX - 8,
            "the longest useful compact hazard label must fit the 41 mm split-map panel"
        )

        let center = WatchHoleMapViewport.distancePillCenter(
            marker: CGPoint(x: 85, y: 120),
            pillSize: pillSize,
            viewportSize: viewport,
            preferredOffset: 24,
            contentMinX: dataColumnMaxX
        )
        let pillRect = CGRect(
            x: center.x - pillSize.width / 2,
            y: center.y - pillSize.height / 2,
            width: pillSize.width,
            height: pillSize.height
        )

        XCTAssertGreaterThanOrEqual(pillRect.minX, dataColumnMaxX + 4)
        XCTAssertLessThanOrEqual(pillRect.maxX, viewport.width - 4)
    }

    func testFullMapHazardLabelRetainsExplicitNearAndFarGrammar() {
        XCTAssertEqual(
            WatchHoleMapViewport.hazardDistanceText(
                kind: "水",
                toYards: 37,
                overYards: 54,
                fullMap: true
            ),
            "水 · 到 37 / 过 54"
        )
    }

    func testDistancePillConnectorBindsTheCalloutToItsMarker() {
        let connector = WatchHoleMapViewport.distancePillConnector(
            marker: CGPoint(x: 100, y: 100),
            pillCenter: CGPoint(x: 100, y: 80),
            pillSize: CGSize(width: 68, height: 18)
        )

        XCTAssertEqual(connector?.start, CGPoint(x: 100, y: 89))
        XCTAssertEqual(connector?.end, CGPoint(x: 100, y: 100))
    }

    func testFreeMeasurementOwnsTheVisibleRouteInsteadOfLeavingASecondCaddieTarget() {
        let measured = CGPoint(x: 470, y: 470)

        XCTAssertEqual(
            WatchHoleMapRouteOverlay.resolve(
                measuredPoint: measured,
                showCaddieRecommendation: true,
                hasCurrentShot: false,
                showPreparedPlan: true
            ),
            .measurement(measured)
        )
    }

    func testRootHazardOverlayUsesOnlyTheNearestUpcomingMeasuredObstacle() throws {
        let route = [[0.0, 200.0, 0.0], [0.0, 100.0, 100.0], [0.0, 0.0, 200.0]]
        let passed = WatchHazard(kind: "bunker", label: "已过沙坑", startM: 10, endM: 20,
                                 frontPx: [0, 190], backPx: [0, 180])
        let nearest = WatchHazard(kind: "water", label: "前方水障碍", startM: 80, endM: 110,
                                  frontPx: [0, 120], backPx: [0, 90])
        let farther = WatchHazard(kind: "bunker", label: "果岭沙坑", startM: 150, endM: 170,
                                  frontPx: [0, 50], backPx: [0, 30])

        let selected = try XCTUnwrap(WatchHoleMapView.nearestUpcomingHazard(
            [farther, passed, nearest],
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 150)
        ))

        XCTAssertEqual(selected.id, nearest.id)
    }

    func testEighteenHoleRingStartsAtThreeAndEndsAtTwelve() {
        let centers = (0 ..< 18).map {
            WatchHoleMapView.scoringRingCenterFraction(index: $0, count: 18)
        }

        XCTAssertEqual(centers[0], 0.25, accuracy: 0.0001)
        XCTAssertEqual(centers[17], 1.0, accuracy: 0.0001)
        XCTAssertTrue(centers.allSatisfy { $0 >= 0.25 && $0 <= 1.0 })
        XCTAssertTrue(zip(centers, centers.dropFirst()).allSatisfy { pair in
            pair.0 < pair.1
        })
    }

    func testNineHoleRingUsesTheSameClockClearSweep() {
        let centers = (0 ..< 9).map {
            WatchHoleMapView.scoringRingCenterFraction(index: $0, count: 9)
        }

        XCTAssertEqual(centers[0], 0.25, accuracy: 0.0001)
        XCTAssertEqual(centers[8], 1.0, accuracy: 0.0001)
    }

    func testEighteenHoleRingKeepsEverySegmentSeparatedAcrossTheClockwiseSweep() {
        let centers = (0 ..< 18).map {
            WatchHoleMapView.scoringRingCenterFraction(index: $0, count: 18)
        }
        let separations = zip(centers, centers.dropFirst()).map { next, following in
            following - next
        }

        XCTAssertGreaterThanOrEqual(separations.min() ?? 0, 0.03)
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
