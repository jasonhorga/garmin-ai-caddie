import XCTest
@testable import AICaddieWatch

final class WatchHoleMapViewportTests: XCTestCase {
    func testCriticalContentGuideFitsEverySupportedRoundedWatchFace() {
        let faces = [
            CGSize(width: 176, height: 215), // 41 mm
            CGSize(width: 198, height: 242), // 45 mm
            CGSize(width: 205, height: 251), // Ultra 49 mm
        ]

        for size in faces {
            XCTAssertGreaterThan(size.height, size.width, "Watch display must be tested as a portrait rectangle")
            let rect = WatchDisplayGeometry.contentRect(in: size)
            XCTAssertGreaterThanOrEqual(rect.minX, WatchDisplayGeometry.minimumContentInset)
            XCTAssertGreaterThanOrEqual(rect.minY, WatchDisplayGeometry.minimumContentInset)
            for point in [
                CGPoint(x: rect.minX, y: rect.minY),
                CGPoint(x: rect.maxX, y: rect.minY),
                CGPoint(x: rect.minX, y: rect.maxY),
                CGPoint(x: rect.maxX, y: rect.maxY),
            ] {
                XCTAssertTrue(
                    WatchDisplayGeometry.contains(point, in: size),
                    "safe guide corner \(point) must remain visible on \(size)"
                )
            }
        }
    }

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

    func testFixedRemainingMarkersComeFromRouteMetresRatherThanScreenPercentages() {
        let route = [
            [0.0, 400.0, 0.0],
            [0.0, 0.0, 400.0],
        ]

        let all = WatchHoleMapReferenceLayout.remainingMarkers(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 400)
        )
        XCTAssertEqual(all.map(\.remainingYards), [100, 150, 200, 250])
        XCTAssertEqual(all[0].imagePoint.y, 91.44, accuracy: 0.01)

        let late = WatchHoleMapReferenceLayout.remainingMarkers(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 150)
        )
        XCTAssertEqual(late.map(\.remainingYards), [100, 150])
    }

    func testDriverArcRequiresARealInBoundsBagDistance() throws {
        let route = [
            [0.0, 400.0, 0.0],
            [0.0, 0.0, 400.0],
        ]
        let target = try XCTUnwrap(WatchHoleMapReferenceLayout.driverTarget(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 400),
            driverDistanceM: 200
        ))
        XCTAssertEqual(target.y, 200, accuracy: 0.001)
        XCTAssertNil(WatchHoleMapReferenceLayout.driverTarget(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 400),
            driverDistanceM: 450
        ))
        XCTAssertNil(WatchHoleMapReferenceLayout.driverTarget(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 400),
            driverDistanceM: nil
        ))
    }

    func testGreenPreviewOnlyAcceptsPointsInsideTheRealOutline() {
        let outline = [
            CGPoint(x: 0, y: 0),
            CGPoint(x: 10, y: 0),
            CGPoint(x: 10, y: 10),
            CGPoint(x: 0, y: 10),
        ]
        XCTAssertTrue(WatchGreenPreviewLayout.contains(CGPoint(x: 5, y: 5), polygon: outline))
        XCTAssertFalse(WatchGreenPreviewLayout.contains(CGPoint(x: 15, y: 5), polygon: outline))
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

    func testScoringRingStrokeFitsInsideEveryRoundedHardwareMask() {
        for size in [
            CGSize(width: 176, height: 215),
            CGSize(width: 198, height: 242),
            CGSize(width: 205, height: 251),
        ] {
            let inset: CGFloat = 6
            let center = CGPoint(x: size.width / 2, y: size.height / 2)
            let halfW = size.width / 2 - inset
            let halfH = size.height / 2 - inset
            let corner = max(0, WatchDisplayGeometry.cornerRadius(for: size) - inset)
            let flatW = max(0, halfW - corner)
            let flatH = max(0, halfH - corner)
            let perimeter = 4 * flatW + 4 * flatH + 2 * CGFloat.pi * corner

            for sample in 0...120 {
                let (point, _) = WatchHoleMapView.perimeterPointTangent(
                    s: perimeter * CGFloat(sample) / 120,
                    center: center,
                    halfW: halfW,
                    halfH: halfH,
                    corner: corner
                )
                // The widest current-hole stroke is 5.5 pt, so a 3 pt disc around its centreline
                // must remain inside the physical mask.
                for angle in stride(
                    from: CGFloat.zero,
                    to: 2 * CGFloat.pi,
                    by: CGFloat.pi / 4
                ) {
                    let strokePoint = CGPoint(
                        x: point.x + cos(angle) * 3,
                        y: point.y + sin(angle) * 3
                    )
                    XCTAssertTrue(
                        WatchDisplayGeometry.contains(strokePoint, in: size, tolerance: 0.01),
                        "ring stroke at \(strokePoint) must remain visible on \(size)"
                    )
                }
            }
        }
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

}
