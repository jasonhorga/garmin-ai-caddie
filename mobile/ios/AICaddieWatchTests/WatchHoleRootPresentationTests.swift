import XCTest
@testable import AICaddieWatch

final class WatchHoleRootPresentationTests: XCTestCase {
    func testMissingWristFixKeepsTheMapUsableDuringColdStart() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: false,
                hasGeometry: true,
                hasLiveCenterDistance: false
            ),
            .map
        )
    }

    func testRealGeometryMakesTheMapTheCurrentHoleRoot() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: true,
                hasGeometry: true,
                hasLiveCenterDistance: true
            ),
            .map
        )
    }

    func testVectorGeometryRemainsVisibleWhileGreenDistancesUpgrade() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: true,
                hasGeometry: true,
                hasLiveCenterDistance: false
            ),
            .map
        )
    }

    func testDistanceFactsProvideTheRootWhenGeometryIsUnavailable() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: true,
                hasGeometry: false,
                hasLiveCenterDistance: true
            ),
            .distances
        )
    }

    func testMissingMapAndDistanceFactsFallsBackToHonestScoring() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: true,
                hasGeometry: false,
                hasLiveCenterDistance: false
            ),
            .scoreOnly
        )
    }

    func testMissingGreenEdgeDistanceStaysUnknownInsteadOfBecomingZero() {
        XCTAssertNil(WatchRoundContainerView.effectiveGreenYards(live: nil, fallbackMetres: nil))
        XCTAssertEqual(
            WatchRoundContainerView.effectiveGreenYards(live: nil, fallbackMetres: 100),
            109
        )
        XCTAssertEqual(
            WatchRoundContainerView.effectiveGreenYards(live: 123, fallbackMetres: nil),
            123
        )
    }

    func testContainerDoesNotUseStaticCenterRangeWithoutQualifiedWristFix() {
        XCTAssertNil(
            WatchRoundContainerView.canonicalCenterYards(
                live: nil,
                fallbackMetres: 100,
                hasQualifiedRangeFix: false
            )
        )
        XCTAssertEqual(
            WatchRoundContainerView.canonicalCenterYards(
                live: nil,
                fallbackMetres: 100,
                hasQualifiedRangeFix: true
            ),
            109
        )
        XCTAssertEqual(
            WatchRoundContainerView.canonicalCenterYards(
                live: 123,
                fallbackMetres: 100,
                hasQualifiedRangeFix: true
            ),
            123
        )
    }

    func testRangeDependentInstrumentsExposeExplicitUnavailableState() {
        let green = WatchGreenPreviewView(
            geometry: WatchHoleMapSample.geometry,
            centerGreenYards: nil,
            rangeUnavailable: true
        )
        XCTAssertTrue(green.rangeUnavailable)

        let hazard = WatchHazardMapView(
            geometry: WatchHoleMapSample.geometry,
            route: [[120, 900, 0], [430, 120, 372]],
            hazards: [],
            centerGreenYards: nil,
            rangeUnavailable: true
        )
        XCTAssertTrue(hazard.rangeUnavailable)
    }
}
