import XCTest
@testable import AICaddieWatch

final class WatchHazardMapLayoutTests: XCTestCase {
    private let route = [
        [100.0, 700.0, 0.0],
        [500.0, 400.0, 200.0],
        [600.0, 100.0, 400.0],
    ]

    func testInterpolatesHazardEdgeOnTheDownloadedRoute() throws {
        let point = try XCTUnwrap(WatchHazardMapLayout.imagePoint(on: route, atMetres: 300))

        XCTAssertEqual(point.x, 550, accuracy: 0.0001)
        XCTAssertEqual(point.y, 250, accuracy: 0.0001)
    }

    func testProjectsThePlayerOntoTheRouteBeforeShowingRemainingCarry() throws {
        let progress = try XCTUnwrap(WatchHazardMapLayout.playerProgressMetres(
            on: route,
            playerImagePoint: CGPoint(x: 300, y: 550)
        ))

        XCTAssertEqual(progress, 100, accuracy: 0.0001)
        XCTAssertEqual(WatchHazardMapLayout.remainingYards(to: 180, after: progress), 87)
        XCTAssertNil(WatchHazardMapLayout.remainingYards(to: 90, after: progress))
    }

    func testBunkerLateralGapNeverBecomesAFakeClearDistance() {
        let measured = WatchHazard(
            kind: "bunker", label: "沙坑", startM: 170, endM: 190,
            frontDistanceM: 168, backDistanceM: 184,
            frontPx: [440, 445], backPx: [470, 420]
        )
        let current = WatchHazard(
            kind: "bunker", label: "沙坑", startM: 180, sideM: 15
        )
        let oldCache = WatchHazard(
            kind: "bunker", label: "沙坑", startM: 180, endM: 15
        )

        XCTAssertEqual(WatchHazardMapLayout.alongRouteEndMetres(for: measured), 190)
        XCTAssertNil(WatchHazardMapLayout.bunkerSideMetres(for: measured))
        XCTAssertEqual(WatchHazardMapLayout.alongRouteEndMetres(for: current), 180)
        XCTAssertEqual(WatchHazardMapLayout.bunkerSideMetres(for: current), 15)
        XCTAssertEqual(WatchHazardMapLayout.alongRouteEndMetres(for: oldCache), 180)
        XCTAssertEqual(WatchHazardMapLayout.bunkerSideMetres(for: oldCache), 15)
    }

    func testDistanceToRealHazardBoundaryUsesMapScaleInsteadOfRouteProgress() throws {
        let straightRoute = [
            [100.0, 700.0, 0.0],
            [100.0, 500.0, 200.0],
        ]
        let player = CGPoint(x: 100, y: 700)
        let sideBunkerFront = CGPoint(x: 120, y: 610)

        let yards = try XCTUnwrap(WatchHazardMapLayout.distanceYards(
            from: player, to: sideBunkerFront, on: straightRoute
        ))

        XCTAssertEqual(yards, 101) // sqrt(20² + 90²) metres, then metres → yards
    }

    func testTopClampedFrontAndBackPillsOccupySeparateLanes() {
        let lanes = WatchHazardMapLayout.separatedPillCenterYs(
            frontPreferredY: 44,
            backPreferredY: 40,
            minimumY: 42,
            maximumY: 306,
            minimumSpacing: 26
        )

        XCTAssertEqual(lanes.back, 42, accuracy: 0.0001)
        XCTAssertEqual(lanes.front, 68, accuracy: 0.0001)
        XCTAssertGreaterThanOrEqual(lanes.front - lanes.back, 26)
    }

    func testHazardPillUsesApprovedCompactMapGeometry() {
        let size = WatchHazardMapLayout.distancePillSize(for: "过 149")

        XCTAssertEqual(size.width, 60, accuracy: 0.0001)
        XCTAssertEqual(size.height, 18, accuracy: 0.0001)
        XCTAssertEqual(WatchHazardMapLayout.markerDiameter, 8, accuracy: 0.0001)
        XCTAssertEqual(WatchHazardMapLayout.markerToPillCenterOffset, 14, accuracy: 0.0001)
    }

    func testTopHazardBoundaryMarkerStaysClearOfTheApprovedPillLane() {
        let pill = WatchHazardMapLayout.distancePillSize(for: "过 149")
        let requiredCenterSpacing = pill.height * 0.5
            + WatchHazardMapLayout.markerDiameter * 0.5
            + 1

        XCTAssertEqual(WatchHazardMapLayout.topPillLaneCenterY, 42, accuracy: 0.0001)
        XCTAssertEqual(WatchHazardMapLayout.topBoundaryClearance, 56, accuracy: 0.0001)
        XCTAssertGreaterThanOrEqual(
            WatchHazardMapLayout.topBoundaryClearance
                - WatchHazardMapLayout.topPillLaneCenterY,
            requiredCenterSpacing
        )
    }

    func testTopSummaryLeavesTheRealWatchSystemTimeLaneClear() {
        let viewportWidth: CGFloat = 198
        let summaryRightEdge = WatchHazardMapLayout.topSummaryLeadingInset
            + WatchHazardMapLayout.topSummaryWidth(viewportWidth: viewportWidth)

        XCTAssertEqual(summaryRightEdge, 142, accuracy: 0.0001)
        XCTAssertGreaterThanOrEqual(
            viewportWidth - summaryRightEdge,
            WatchHazardMapLayout.systemTimeTrailingClearance
        )
    }

    func testHazardPillStaysCenteredOnItsBoundaryMarker() {
        XCTAssertEqual(
            WatchHazardMapLayout.distancePillCenterX(
                markerX: 84,
                pillWidth: 60,
                viewportWidth: 198
            ),
            84,
            accuracy: 0.0001
        )
        XCTAssertEqual(
            WatchHazardMapLayout.distancePillCenterX(
                markerX: 20,
                pillWidth: 60,
                viewportWidth: 198
            ),
            40,
            accuracy: 0.0001
        )
    }

    func testHazardPillClampsInsideEveryRoundedFaceGuide() {
        for size in [
            CGSize(width: 176, height: 215),
            CGSize(width: 198, height: 242),
            CGSize(width: 205, height: 251),
        ] {
            let pillWidth: CGFloat = 60
            let safeRect = WatchDisplayGeometry.contentRect(in: size)
            for markerX in [CGFloat.zero, size.width] {
                let centerX = WatchHazardMapLayout.distancePillCenterX(
                    markerX: markerX,
                    pillWidth: pillWidth,
                    viewportWidth: size.width
                )
                XCTAssertGreaterThanOrEqual(centerX - pillWidth / 2, safeRect.minX)
                XCTAssertLessThanOrEqual(centerX + pillWidth / 2, safeRect.maxX)
            }
        }
    }
}
