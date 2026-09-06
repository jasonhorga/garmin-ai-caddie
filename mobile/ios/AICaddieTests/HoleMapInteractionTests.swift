import SwiftUI
import XCTest
@testable import AICaddie

final class HoleMapInteractionTests: XCTestCase {
    func testNearbyClubDistancesInterpolateToDifferentLandingPixels() throws {
        let overlay = CoursePrepOverlay(
            w: 200,
            h: 1_000,
            ppm: 1,
            ln: 200,
            route: [
                [20, 900, 0],
                [100, 500, 100],
                [180, 100, 200],
            ]
        )

        let sixIron = try XCTUnwrap(HoleImageMapView.landingOverlayPoint(overlay, targetMetres: 137))
        let fiveIron = try XCTUnwrap(HoleImageMapView.landingOverlayPoint(overlay, targetMetres: 146))

        XCTAssertEqual(sixIron[0], 129.6, accuracy: 0.001)
        XCTAssertEqual(sixIron[1], 352, accuracy: 0.001)
        XCTAssertEqual(fiveIron[0], 136.8, accuracy: 0.001)
        XCTAssertEqual(fiveIron[1], 316, accuracy: 0.001)
        XCTAssertNotEqual(sixIron[0], fiveIron[0])
        XCTAssertNotEqual(sixIron[1], fiveIron[1])
    }

    func testLandingInterpolationRejectsRoutesWithoutMeasuredPixels() {
        let overlay = CoursePrepOverlay(
            w: 200,
            h: 1_000,
            ppm: 1,
            ln: 200,
            route: [[20, 900], []]
        )

        XCTAssertNil(HoleImageMapView.landingOverlayPoint(overlay, targetMetres: 146))
    }

    func testRecommendationBuildsTwoDirectFlightArcsThroughLanding() {
        let tee = CGPoint(x: 100, y: 500)
        let landing = CGPoint(x: 145, y: 290)
        let pin = CGPoint(x: 120, y: 70)

        let arcs = HoleImageMapView.flightArcs(tee: tee, landing: landing, pin: pin)

        XCTAssertEqual(arcs.count, 2)
        XCTAssertEqual(arcs[0].start, tee)
        XCTAssertEqual(arcs[0].end, landing)
        XCTAssertEqual(arcs[1].start, landing)
        XCTAssertEqual(arcs[1].end, pin)
        XCTAssertNotEqual(arcs[0].control, CGPoint(x: 122.5, y: 395))
        XCTAssertNotEqual(arcs[1].control, CGPoint(x: 132.5, y: 180))
    }

    func testHorizontalHoleSwipeChangesOnlyToAnAdjacentHole() {
        let holes = [1, 2, 3]

        XCTAssertEqual(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: -90, height: 8)
            ),
            3
        )
        XCTAssertEqual(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: 90, height: -8)
            ),
            1
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: 45, height: 2)
            )
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: -90, height: 120)
            )
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: -90, height: 2),
                enabled: false
            )
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 3,
                holes: holes,
                translation: CGSize(width: -90, height: 2)
            )
        )
    }

    func testMediaCaptureCardRemainsFeatureFlaggedOffInLivePlay() {
        XCTAssertFalse(CurrentHoleView.showsMediaCaptureCard)
    }
}
