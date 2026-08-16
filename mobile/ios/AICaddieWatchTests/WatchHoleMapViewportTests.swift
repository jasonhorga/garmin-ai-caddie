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
        XCTAssertLessThanOrEqual(
            pillRect.maxX,
            WatchDisplayGeometry.contentRect(in: viewport).maxX
        )
    }

    func testMapPillsStayInsideRoundedFaceGuideAtEveryViewportEdge() {
        for viewport in [
            CGSize(width: 176, height: 215),
            CGSize(width: 198, height: 242),
            CGSize(width: 205, height: 251),
        ] {
            let safeRect = WatchDisplayGeometry.contentRect(in: viewport)
            let pillSize = CGSize(width: 68, height: 18)
            for marker in [CGPoint.zero, CGPoint(x: viewport.width, y: viewport.height)] {
                let center = WatchHoleMapViewport.distancePillCenter(
                    marker: marker,
                    pillSize: pillSize,
                    viewportSize: viewport,
                    preferredOffset: 20
                )
                let rect = CGRect(
                    x: center.x - pillSize.width / 2,
                    y: center.y - pillSize.height / 2,
                    width: pillSize.width,
                    height: pillSize.height
                )
                XCTAssertGreaterThanOrEqual(rect.minX, safeRect.minX)
                XCTAssertLessThanOrEqual(rect.maxX, safeRect.maxX)
                XCTAssertGreaterThanOrEqual(rect.minY, safeRect.minY)
                XCTAssertLessThanOrEqual(rect.maxY, safeRect.maxY)
            }
        }
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

    func testCompactReferenceLabelsUseSeparateLanesOutsideTheClockAndDataColumn() throws {
        let viewport = CGSize(width: 176, height: 215)
        let contentMinX = viewport.width * 0.38
        let clusteredMarkers = [
            CGPoint(x: 103, y: 48),
            CGPoint(x: 106, y: 51),
            CGPoint(x: 110, y: 57),
            CGPoint(x: 108, y: 67),
            CGPoint(x: 111, y: 78),
        ]
        let sizes = [
            CGSize(width: 34, height: 11),
            CGSize(width: 23, height: 11),
            CGSize(width: 23, height: 11),
            CGSize(width: 23, height: 11),
            CGSize(width: 23, height: 11),
        ]
        var occupied: [CGRect] = []

        for (marker, size) in zip(clusteredMarkers, sizes) {
            let placement = try XCTUnwrap(WatchHoleMapReferenceLayout.labelPlacement(
                marker: marker,
                pillSize: size,
                viewportSize: viewport,
                contentMinX: contentMinX,
                occupiedRects: occupied
            ))
            XCTAssertGreaterThanOrEqual(placement.rect.minX, contentMinX)
            XCTAssertFalse(placement.rect.intersects(WatchHoleMapViewport.systemTimeRect(in: viewport)))
            XCTAssertTrue(occupied.allSatisfy { !$0.intersects(placement.rect) })
            occupied.append(placement.rect)
        }
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
