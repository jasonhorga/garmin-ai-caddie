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

    func testTouchTargetUsesTwoStraightLineRangesCalibratedByLivePinDistance() throws {
        let distances = try XCTUnwrap(WatchTouchTargetDistanceLayout.resolve(
            playerImagePoint: WatchHoleMapSample.lastShotPx,
            targetImagePoint: WatchHoleMapSample.youPx,
            pinImagePoint: WatchHoleMapSample.pinPx,
            centerGreenYards: 567
        ))

        XCTAssertEqual(distances.playerToTargetYards, 232)
        XCTAssertEqual(distances.targetToPinYards, 346)
        // This dogleg target sits off the direct player→pin chord. S70-style straight segments can
        // therefore add up to slightly more than the 567-yard direct green distance.
        XCTAssertGreaterThan(
            distances.playerToTargetYards + distances.targetToPinYards,
            567
        )
    }

    func testTouchTargetUsesMovedPinButKeepsCanonicalCalibration() throws {
        let distances = try XCTUnwrap(WatchTouchTargetDistanceLayout.resolve(
            playerImagePoint: CGPoint(x: 0, y: 10),
            targetImagePoint: CGPoint(x: 0, y: 5),
            pinImagePoint: CGPoint(x: 3, y: 0),
            canonicalPinImagePoint: CGPoint(x: 0, y: 0),
            centerGreenYards: 10
        ))

        XCTAssertEqual(distances.playerToTargetYards, 5)
        XCTAssertEqual(distances.targetToPinYards, 6)
    }

    func testReviewTouchTargetIsARealIntermediateLieAndEndsAtMovedFlag() throws {
        let player = CGPoint(x: 469.7174, y: 339.6333)
        let target = CGPoint(x: 458, y: 318)
        let movedPin = CGPoint(x: 447, y: 270)
        let distances = try XCTUnwrap(WatchTouchTargetDistanceLayout.resolve(
            playerImagePoint: player,
            targetImagePoint: target,
            pinImagePoint: movedPin,
            canonicalPinImagePoint: WatchHoleMapSample.pinPx,
            centerGreenYards: 53
        ))

        XCTAssertEqual(distances.playerToTargetYards, 19)
        XCTAssertEqual(distances.targetToPinYards, 37)
        XCTAssertGreaterThan(distances.playerToTargetYards, 0)
        XCTAssertGreaterThan(distances.targetToPinYards, 0)
    }

    func testTouchTargetRejectsMissingOrDegenerateDistanceAuthority() {
        XCTAssertNil(WatchTouchTargetDistanceLayout.resolve(
            playerImagePoint: .zero,
            targetImagePoint: CGPoint(x: 0, y: 50),
            pinImagePoint: CGPoint(x: 0, y: 100),
            centerGreenYards: nil
        ))
        XCTAssertNil(WatchTouchTargetDistanceLayout.resolve(
            playerImagePoint: .zero,
            targetImagePoint: CGPoint(x: 0, y: 50),
            pinImagePoint: .zero,
            centerGreenYards: 100
        ))
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
        XCTAssertEqual(all.map(\.remainingYards), [100, 150, 200])
        XCTAssertEqual(all[0].imagePoint.y, 91.44, accuracy: 0.01)

        let late = WatchHoleMapReferenceLayout.remainingMarkers(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 150)
        )
        XCTAssertEqual(late.map(\.remainingYards), [100, 150])
    }

    func testRemainingMarkersMeasureBackFromTheRealPinInsteadOfAnExtendedRouteTail() throws {
        let route = [
            [0.0, 500.0, 0.0],
            [0.0, 100.0, 400.0], // actual pin
            [0.0, 0.0, 500.0],   // provider route tail beyond the pin
        ]

        let markers = WatchHoleMapReferenceLayout.remainingMarkers(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 500),
            pinImagePoint: CGPoint(x: 0, y: 100)
        )

        XCTAssertEqual(markers.map(\.remainingYards), [100, 150, 200])
        XCTAssertEqual(try XCTUnwrap(markers.first).imagePoint.y, 191.44, accuracy: 0.01)
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

    func testMovedGreenFlagUpdatesPinDistanceAndFourBoundaryClearances() throws {
        let outline = [
            CGPoint(x: 0, y: 0), CGPoint(x: 10, y: 0),
            CGPoint(x: 10, y: 10), CGPoint(x: 0, y: 10),
        ]
        let metrics = try XCTUnwrap(WatchGreenPreviewLayout.pinMetrics(
            playerImagePoint: CGPoint(x: 5, y: 15),
            canonicalPinImagePoint: CGPoint(x: 5, y: 5),
            selectedPinImagePoint: CGPoint(x: 7, y: 4),
            greenOutline: outline,
            centerGreenYards: 10
        ))

        XCTAssertEqual(metrics.playerToPinYards, 11)
        XCTAssertEqual(metrics.edge(.top)?.yards, 4)
        XCTAssertEqual(metrics.edge(.right)?.yards, 3)
        XCTAssertEqual(metrics.edge(.bottom)?.yards, 6)
        XCTAssertEqual(metrics.edge(.left)?.yards, 7)
    }

    func testGreenViewportAndPinMetricsShareTheSampledBoundaryRotationCentre() throws {
        let base = WatchHoleMapSample.geometry
        let geometry = WatchHoleMapGeometry(
            image: base.image,
            imageSize: base.imageSize,
            youPx: WatchHoleMapSample.lastShotPx,
            pinPx: base.pinPx,
            layupPx: base.layupPx,
            apexPx: base.apexPx,
            greenCtrlPx: base.greenCtrlPx,
            greenOutlinePx: [
                CGPoint(x: 410, y: 257), CGPoint(x: 452, y: 252),
                CGPoint(x: 470, y: 281), CGPoint(x: 447, y: 306),
                CGPoint(x: 408, y: 296), CGPoint(x: 397, y: 274),
            ]
        )
        let boundary = try XCTUnwrap(
            WatchGreenPreviewLayout.boundaryGeometry(geometry.greenOutlinePx)
        )
        let viewport = WatchGreenPreviewLayout.viewport(
            geometry: geometry,
            size: CGSize(width: 198, height: 242),
            rotationDegrees: 35
        )
        let renderedCentre = viewport.canvasPoint(boundary.center)

        XCTAssertEqual(renderedCentre.x, viewport.rotationCenterCanvas.x, accuracy: 0.0001)
        XCTAssertEqual(renderedCentre.y, viewport.rotationCenterCanvas.y, accuracy: 0.0001)
    }

    func testShortRightClearanceLabelMovesAwayFromFlagAndStaysVisible() {
        let safeRect = CGRect(x: 0, y: 0, width: 198, height: 242)
        let flag = CGPoint(x: 120, y: 120)
        let label = WatchGreenPreviewLayout.edgeLabelPoint(
            direction: .right,
            edgeCanvasPoint: CGPoint(x: 110, y: 120),
            flagCanvasPoint: flag,
            safeRect: safeRect
        )

        XCTAssertGreaterThanOrEqual(label.x, safeRect.minX + 11)
        XCTAssertLessThanOrEqual(label.x, safeRect.maxX - 11)
        XCTAssertGreaterThanOrEqual(label.y, safeRect.minY + 31)
        XCTAssertLessThanOrEqual(label.y, safeRect.maxY - 31)
        XCTAssertGreaterThanOrEqual(hypot(label.x - flag.x, label.y - flag.y), 14)
    }

    func testRotatingGreenChangesScreenAxisClearancesWithoutChangingFlagRange() throws {
        let outline = [
            CGPoint(x: 0, y: 0), CGPoint(x: 20, y: 0),
            CGPoint(x: 20, y: 10), CGPoint(x: 0, y: 10),
        ]
        let unrotated = try XCTUnwrap(WatchGreenPreviewLayout.pinMetrics(
            playerImagePoint: CGPoint(x: 10, y: 15),
            canonicalPinImagePoint: CGPoint(x: 10, y: 5),
            selectedPinImagePoint: CGPoint(x: 10, y: 5),
            greenOutline: outline,
            centerGreenYards: 10,
            rotationDegrees: 0
        ))
        let quarterTurn = try XCTUnwrap(WatchGreenPreviewLayout.pinMetrics(
            playerImagePoint: CGPoint(x: 10, y: 15),
            canonicalPinImagePoint: CGPoint(x: 10, y: 5),
            selectedPinImagePoint: CGPoint(x: 10, y: 5),
            greenOutline: outline,
            centerGreenYards: 10,
            rotationDegrees: 90
        ))

        XCTAssertEqual(unrotated.playerToPinYards, quarterTurn.playerToPinYards)
        XCTAssertEqual(unrotated.edge(.top)?.yards, 5)
        XCTAssertEqual(unrotated.edge(.right)?.yards, 10)
        XCTAssertEqual(quarterTurn.edge(.top)?.yards, 10)
        XCTAssertEqual(quarterTurn.edge(.right)?.yards, 5)
    }

    func testGreenFlagMetricsRejectMissingLiveDistanceAuthority() {
        XCTAssertNil(WatchGreenPreviewLayout.pinMetrics(
            playerImagePoint: CGPoint(x: 5, y: 15),
            canonicalPinImagePoint: CGPoint(x: 5, y: 5),
            selectedPinImagePoint: CGPoint(x: 5, y: 5),
            greenOutline: [CGPoint(x: 0, y: 0), CGPoint(x: 10, y: 0), CGPoint(x: 5, y: 10)],
            centerGreenYards: nil
        ))
    }

    func testGreenPreviewDefaultCropFillsTheDedicatedFlagInstrument() throws {
        let base = WatchHoleMapSample.geometry
        let geometry = WatchHoleMapGeometry(
            image: base.image,
            imageSize: base.imageSize,
            youPx: WatchHoleMapSample.lastShotPx,
            pinPx: base.pinPx,
            layupPx: base.layupPx,
            apexPx: base.apexPx,
            greenCtrlPx: base.greenCtrlPx,
            greenOutlinePx: [
                CGPoint(x: 410, y: 257), CGPoint(x: 452, y: 252),
                CGPoint(x: 470, y: 281), CGPoint(x: 447, y: 306),
                CGPoint(x: 408, y: 296), CGPoint(x: 397, y: 274),
            ]
        )
        let size = CGSize(width: 198, height: 242)
        let viewport = WatchGreenPreviewLayout.viewport(geometry: geometry, size: size)
        let outline = geometry.greenOutlinePx.map(viewport.canvasPoint)
        let adjacentBunker = viewport.canvasPoint(CGPoint(x: 498, y: 317))
        let minX = try XCTUnwrap(outline.map(\.x).min())
        let maxX = try XCTUnwrap(outline.map(\.x).max())
        let safeRect = WatchDisplayGeometry.contentRect(in: size)

        XCTAssertTrue(outline.allSatisfy { safeRect.contains($0) })
        XCTAssertGreaterThan(maxX - minX, safeRect.width * 0.55)
        XCTAssertTrue(safeRect.contains(adjacentBunker))
    }

    func testGreenPreviewMaximumCrownKeepsTopoUnderTheWholeDisplay() {
        let base = WatchHoleMapSample.geometry
        let geometry = WatchHoleMapGeometry(
            image: base.image,
            imageSize: base.imageSize,
            youPx: WatchHoleMapSample.lastShotPx,
            pinPx: base.pinPx,
            layupPx: base.layupPx,
            apexPx: base.apexPx,
            greenCtrlPx: base.greenCtrlPx,
            greenOutlinePx: [
                CGPoint(x: 410, y: 257), CGPoint(x: 452, y: 252),
                CGPoint(x: 470, y: 281), CGPoint(x: 447, y: 306),
                CGPoint(x: 408, y: 296), CGPoint(x: 397, y: 274),
            ]
        )
        let size = CGSize(width: 198, height: 242)
        let viewport = WatchGreenPreviewLayout.viewport(
            geometry: geometry,
            size: size,
            zoom: 2
        )
        let imageRect = CGRect(
            x: viewport.imageOrigin.x,
            y: viewport.imageOrigin.y,
            width: geometry.imageSize.width * viewport.scale,
            height: geometry.imageSize.height * viewport.scale
        )

        XCTAssertTrue(imageRect.contains(CGPoint(x: 0, y: 0)))
        XCTAssertTrue(imageRect.contains(CGPoint(x: size.width - 0.01, y: size.height - 0.01)))
    }

    func testGreenPreviewRotationKeepsRealTopoUnderEveryWatchCorner() {
        let base = WatchHoleMapSample.geometry
        let geometry = WatchHoleMapGeometry(
            image: base.image,
            imageSize: base.imageSize,
            youPx: WatchHoleMapSample.lastShotPx,
            pinPx: base.pinPx,
            layupPx: base.layupPx,
            apexPx: base.apexPx,
            greenCtrlPx: base.greenCtrlPx,
            greenOutlinePx: [
                CGPoint(x: 410, y: 257), CGPoint(x: 452, y: 252),
                CGPoint(x: 470, y: 281), CGPoint(x: 447, y: 306),
                CGPoint(x: 408, y: 296), CGPoint(x: 397, y: 274),
            ]
        )
        let sizes = [
            CGSize(width: 176, height: 215),
            CGSize(width: 184, height: 224),
            CGSize(width: 198, height: 242),
        ]
        for size in sizes {
            for degrees in stride(from: -180.0, through: 180.0, by: 30.0) {
                let viewport = WatchGreenPreviewLayout.viewport(
                    geometry: geometry,
                    size: size,
                    zoom: 1,
                    rotationDegrees: degrees
                )
                for corner in [
                    CGPoint(x: 0, y: 0), CGPoint(x: size.width, y: 0),
                    CGPoint(x: size.width, y: size.height), CGPoint(x: 0, y: size.height),
                ] {
                    let imagePoint = viewport.imagePoint(corner)
                    XCTAssertGreaterThanOrEqual(imagePoint.x, -0.01, "\(size), \(degrees)°")
                    XCTAssertLessThanOrEqual(imagePoint.x, geometry.imageSize.width + 0.01, "\(size), \(degrees)°")
                    XCTAssertGreaterThanOrEqual(imagePoint.y, -0.01, "\(size), \(degrees)°")
                    XCTAssertLessThanOrEqual(imagePoint.y, geometry.imageSize.height + 0.01, "\(size), \(degrees)°")
                }
            }
        }
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

    func testTouchTargetRestingScaleKeepsPlayerAndFlagVisibleThenZoomsContinuously() {
        let resting = WatchHoleMapViewport.touchTargetScale(
            crownScale: WatchHoleMapView.restingCrownScale,
            minimumCrownScale: WatchHoleMapView.restingCrownScale,
            maximumCrownScale: WatchHoleMapView.maximumCrownScale,
            viewportHeight: 242,
            playerAnchorFraction: 0.66,
            playerImageY: 981,
            pinImageY: 279
        )
        let middle = WatchHoleMapViewport.touchTargetScale(
            crownScale: 0.44,
            minimumCrownScale: WatchHoleMapView.restingCrownScale,
            maximumCrownScale: WatchHoleMapView.maximumCrownScale,
            viewportHeight: 242,
            playerAnchorFraction: 0.66,
            playerImageY: 981,
            pinImageY: 279
        )
        let maximum = WatchHoleMapViewport.touchTargetScale(
            crownScale: WatchHoleMapView.maximumCrownScale,
            minimumCrownScale: WatchHoleMapView.restingCrownScale,
            maximumCrownScale: WatchHoleMapView.maximumCrownScale,
            viewportHeight: 242,
            playerAnchorFraction: 0.66,
            playerImageY: 981,
            pinImageY: 279
        )

        let pinY = 242.0 * 0.66 + (279.0 - 981.0) * resting
        XCTAssertGreaterThanOrEqual(pinY, WatchHoleMapViewport.flagTopClearance)
        XCTAssertLessThan(resting, middle)
        XCTAssertLessThan(middle, maximum)
        XCTAssertEqual(maximum, WatchHoleMapView.maximumCrownScale, accuracy: 0.0001)
    }

}
