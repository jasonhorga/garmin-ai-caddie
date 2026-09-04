import XCTest
import CoreLocation
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

    func testSelectedCourseWithoutFirstMapPayloadUsesMapPreparingRoot() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: false,
                hasGeometry: false,
                hasLiveCenterDistance: false,
                courseDataPending: true
            ),
            .mapPreparing
        )
    }

    func testMapPreparingWinsOverAStaticDistanceFallback() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: false,
                hasGeometry: false,
                hasLiveCenterDistance: true,
                courseDataPending: true
            ),
            .mapPreparing
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

    func testMissingWristFixWithoutGeometryDoesNotPromoteAStaticDistanceToTheRoot() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: false,
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

    func testBridgedGreenRangeMustContainAllThreeEdges() {
        XCTAssertFalse(
            WatchRoundContainerView.hasCompleteGreenRange(nil)
        )
        XCTAssertFalse(
            WatchRoundContainerView.hasCompleteGreenRange((front: 100, center: nil, back: 120))
        )
        XCTAssertTrue(
            WatchRoundContainerView.hasCompleteGreenRange((front: 100, center: 110, back: 120))
        )
    }

    func testRangeQualificationRequiresAFreshWristFixEvenWithACompleteBridgeFact() {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let expired = WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5,
            capturedAt: ISO8601DateFormatter().string(from: now.addingTimeInterval(-16))
        )

        XCTAssertFalse(
            WatchRoundContainerView.rangeFixIsQualified(
                shotLocation: expired,
                watchGreenYards: nil,
                now: now
            )
        )
        XCTAssertFalse(
            WatchRoundContainerView.rangeFixIsQualified(
                shotLocation: expired,
                watchGreenYards: (front: 100, center: 110, back: 120),
                now: now
            )
        )
    }

    func testRangeQualificationRejectsMissingWristFixEvenWithACompleteBridgeFact() {
        XCTAssertFalse(
            WatchRoundContainerView.rangeFixIsQualified(
                shotLocation: nil,
                watchGreenYards: (front: 100, center: 110, back: 120)
            )
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
