import XCTest
@testable import AICaddieWatch

final class WatchHoleRootPresentationTests: XCTestCase {
    func testMissingWristFixShowsGPSAcquisitionBeforeMapOrPreparedDistances() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(
                hasQualifiedWristFix: false,
                hasGeometry: true,
                hasLiveCenterDistance: false
            ),
            .acquiringGPS
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
}
