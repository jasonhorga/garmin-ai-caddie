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
}
