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
}
