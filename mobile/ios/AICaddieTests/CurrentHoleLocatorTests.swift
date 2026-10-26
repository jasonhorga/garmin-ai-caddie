import CoreLocation
import XCTest
@testable import AICaddie

final class CurrentHoleLocatorTests: XCTestCase {
    func testTeeFixSelectsTheNearestHole() {
        let holes = [
            HoleLocatorGeometry(hole: 5, tee: coordinate(40, 116), green: coordinate(40.001, 116)),
            HoleLocatorGeometry(hole: 6, tee: coordinate(40.01, 116), green: coordinate(40.011, 116)),
        ]
        XCTAssertEqual(CurrentHoleLocator.locate(
            coordinate: coordinate(40.00001, 116), horizontalAccuracyM: 5, holes: holes
        ), .onHole(5))
    }

    func testPracticeAreaFarFromHoleAnchorsDoesNotStartRound() {
        let holes = [
            HoleLocatorGeometry(hole: 5, tee: coordinate(40, 116), green: coordinate(40.001, 116)),
        ]
        XCTAssertEqual(CurrentHoleLocator.locate(
            coordinate: coordinate(40.005, 116), horizontalAccuracyM: 5, holes: holes
        ), .atCourse)
        XCTAssertEqual(CurrentHoleLocator.locate(
            coordinate: coordinate(40.03, 116), horizontalAccuracyM: 5, holes: holes
        ), .awayFromCourse)
    }

    func testCorridorTieUsesPackageOrder() {
        let holes = [
            HoleLocatorGeometry(hole: 5, tee: coordinate(40, 115.9995), green: coordinate(40.001, 115.99975)),
            HoleLocatorGeometry(hole: 6, tee: coordinate(40, 116.0005), green: coordinate(40.001, 116.00025)),
        ]
        let result = CurrentHoleLocator.locate(
            coordinate: coordinate(40.0005, 116), horizontalAccuracyM: 5, holes: holes
        )
        XCTAssertEqual(result, .onHole(5))

        let reversed = CurrentHoleLocator.locate(
            coordinate: coordinate(40.0005, 116), horizontalAccuracyM: 5, holes: Array(holes.reversed())
        )
        XCTAssertEqual(reversed, .onHole(6))
    }

    func testFairwayOutlineSelectsHoleAwayFromStraightCorridor() {
        let fairway = [
            coordinate(40.002, 116.000), coordinate(40.002, 116.002),
            coordinate(40.003, 116.002), coordinate(40.003, 116.000),
        ]
        let holes = [
            HoleLocatorGeometry(
                hole: 5,
                tee: coordinate(40, 116),
                green: coordinate(40.001, 116),
                fairway: [fairway]
            ),
        ]
        XCTAssertEqual(CurrentHoleLocator.locate(
            coordinate: coordinate(40.0025, 116.001), horizontalAccuracyM: 5, holes: holes
        ), .onHole(5))
    }

    func testPrepHoleFollowingKeepsManualHoleWhenLocationStaysOnHoleOne() {
        var following = PrepHoleFollowingState()

        XCTAssertNil(following.navigationTarget(currentLocatedHole: 1, displayedHole: 1))
        // The player manually previews hole 2 while the GPS fix remains in hole 1.
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 1, displayedHole: 2))
        XCTAssertEqual(following.lastLocatedHole, 1)
    }

    func testPrepHoleFollowingFollowsHoleThreeAfterManualHoleTwo() {
        var following = PrepHoleFollowingState()

        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 1, displayedHole: 2))
        XCTAssertEqual(
            following.navigationTarget(currentLocatedHole: 3, displayedHole: 2),
            3
        )
    }

    private func coordinate(_ latitude: Double, _ longitude: Double) -> CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}
