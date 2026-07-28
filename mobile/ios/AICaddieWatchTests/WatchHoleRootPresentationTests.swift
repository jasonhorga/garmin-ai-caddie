import XCTest
@testable import AICaddieWatch

final class WatchHoleRootPresentationTests: XCTestCase {
    func testRealGeometryMakesTheMapTheCurrentHoleRoot() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(hasGeometry: true, hasCenterDistance: true),
            .map
        )
    }

    func testDistanceFactsProvideTheRootWhenGeometryIsUnavailable() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(hasGeometry: false, hasCenterDistance: true),
            .distances
        )
    }

    func testMissingMapAndDistanceFactsFallsBackToHonestScoring() {
        XCTAssertEqual(
            WatchHoleRootPresentation.resolve(hasGeometry: false, hasCenterDistance: false),
            .scoreOnly
        )
    }
}
