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

    func testPreferredDisplayedHoleWinsWhenTeeAnchorsOverlap() {
        let sharedTee = coordinate(40, 116)
        let holes = [
            HoleLocatorGeometry(hole: 1, tee: sharedTee, green: coordinate(40.001, 116)),
            HoleLocatorGeometry(hole: 10, tee: sharedTee, green: coordinate(40.001, 116.001)),
        ]

        XCTAssertEqual(CurrentHoleLocator.locate(
            coordinate: sharedTee,
            horizontalAccuracyM: 5,
            holes: holes,
            preferredHole: 10
        ), .onHole(10))
    }

    func testClearlyNearerTeeBeatsTheDisplayedHole() {
        // Standing on hole 10's tee (0 m) while the screen still shows hole 1, whose tee is ~33 m away.
        let holes = [
            HoleLocatorGeometry(hole: 1, tee: coordinate(40.0003, 116), green: coordinate(40.004, 116)),
            HoleLocatorGeometry(hole: 10, tee: coordinate(40, 116), green: coordinate(40, 116.004)),
        ]

        XCTAssertEqual(CurrentHoleLocator.locate(
            coordinate: coordinate(40, 116),
            horizontalAccuracyM: 5,
            holes: holes,
            preferredHole: 1
        ), .onHole(10))
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
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 3, displayedHole: 2,
                                              sampledAt: Date(timeIntervalSince1970: 100)))
        XCTAssertEqual(following.navigationTarget(currentLocatedHole: 3, displayedHole: 2,
                                                sampledAt: Date(timeIntervalSince1970: 105)), 3)
    }

    func testPrepHoleFollowingRejectsRapidStationaryDriftThenConfirmsAfterWaiting() {
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        let first = Date(timeIntervalSince1970: 100)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                              sampledAt: first, coordinate: coordinate(40, 116)))
        // About 4.4 m in 1 s: plausible noise with LocationProvider's 3 m distance filter.
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                              sampledAt: first.addingTimeInterval(1),
                                              coordinate: coordinate(40.00004, 116)))
        XCTAssertEqual(following.lastLocatedHole, 1)
        XCTAssertEqual(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                                sampledAt: first.addingTimeInterval(5),
                                                coordinate: coordinate(40.00004, 116)), 2)
    }

    func testPrepHoleFollowingConfirmsRealMovementWithoutWaiting() {
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        let first = Date(timeIntervalSince1970: 100)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                              sampledAt: first, coordinate: coordinate(40, 116)))
        // About 13.3 m exceeds the 10 m drift allowance even before the 5 s interval.
        XCTAssertEqual(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                                sampledAt: first.addingTimeInterval(3),
                                                coordinate: coordinate(40.00012, 116)), 2)
        XCTAssertEqual(following.lastLocatedHole, 2)
        // A manual preview still wins after the hole has been confirmed.
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 3))
    }

    func testPrepHoleFollowingReplayAndMissingFixCannotConfirmPendingHole() {
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        let first = Date(timeIntervalSince1970: 100)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1, sampledAt: first))
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1, sampledAt: first))
        XCTAssertEqual(following.lastLocatedHole, 1)
        // Loss of the fix breaks the confirmation window, including the first sample's age.
        XCTAssertNil(following.navigationTarget(currentLocatedHole: nil, displayedHole: 1,
                                              sampledAt: first.addingTimeInterval(4)))
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                              sampledAt: first.addingTimeInterval(5)))
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                              sampledAt: first.addingTimeInterval(6)))
        XCTAssertEqual(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                                                sampledAt: first.addingTimeInterval(10)), 2)
    }

    func testPrepHoleFollowingIgnoresOneFixOfBoundaryJitter() {
        var following = PrepHoleFollowingState()

        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 2))
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 1, displayedHole: 2))
        XCTAssertEqual(following.lastLocatedHole, 1)
    }

    func testPrepHoleFollowingResetClearsConfirmedAndPendingHole() {
        var following = PrepHoleFollowingState()

        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        following.reset()

        XCTAssertNil(following.lastLocatedHole)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1))
    }

    func testPrepHoleFollowingUnknownLocationDoesNotOverwriteLastHole() {
        var following = PrepHoleFollowingState()

        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: nil, displayedHole: 2))
        XCTAssertEqual(following.lastLocatedHole, 1)
    }

    /// Product spec 5.13: GPS drift must not turn a hole preview into a different playing hole.
    func testProductSpec513ShallowBoundaryDriftDoesNotConfirmAfterFiveSeconds() {
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        let start = Date(timeIntervalSince1970: 100)
        // A straight corridor is 50 m wide on each side; 48 m from its centre is only 2 m inside.
        let point = coordinate(40.002, 116 + 48 / (111_320 * cos(40.002 * .pi / 180)))
        XCTAssertEqual(CurrentHoleLocator.locate(coordinate: point, horizontalAccuracyM: 5,
                                                holes: confirmationHoles), .onHole(2))
        for elapsed in [0.0, 6.0, 12.0] {
            let now = start.addingTimeInterval(elapsed)
            XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                fix: fix(point, at: now, accuracy: 5), holes: confirmationHoles, now: now))
        }
        XCTAssertEqual(following.lastLocatedHole, 1)
    }

    func testProductSpec513PoorAccuracyNeverConfirmsHoleChange() {
        for accuracy in [-1.0, 31.0, Double.nan, Double.infinity] {
            var following = PrepHoleFollowingState()
            _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
            for elapsed in [0.0, 6.0] {
                let now = Date(timeIntervalSince1970: 100 + elapsed)
                XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                    fix: fix(coordinate(40.002, 116), at: now, accuracy: accuracy),
                    holes: confirmationHoles, now: now))
            }
            XCTAssertEqual(following.lastLocatedHole, 1)
        }
    }

    func testProductSpec513CachedFirstFixDoesNotStartConfirmationClock() {
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        let now = Date(timeIntervalSince1970: 100)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(coordinate(40.001, 116), at: now.addingTimeInterval(-31)),
            holes: confirmationHoles, now: now))
        // Even displacement from the cached fix must not count as real observed movement.
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(coordinate(40.002, 116), at: now), holes: confirmationHoles, now: now))
        XCTAssertEqual(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(coordinate(40.002, 116), at: now.addingTimeInterval(5)),
            holes: confirmationHoles, now: now.addingTimeInterval(5)), 2)
    }

    func testProductSpec513FractionalSecondsDoNotRoundFourSecondsUpToFive() throws {
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        let first = Date(timeIntervalSince1970: 100.9)
        let point = coordinate(40.002, 116)
        XCTAssertEqual(try XCTUnwrap(PrepHoleFollowingState.sampleDate(fix(point, at: first).capturedAt))
            .timeIntervalSince1970, 100.9, accuracy: 0.001)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(point, at: first), holes: confirmationHoles, now: first))
        let second = Date(timeIntervalSince1970: 105.1) // 4.2 s, even though integer seconds differ by 5.
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(point, at: second), holes: confirmationHoles, now: second))
        XCTAssertEqual(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(point, at: first.addingTimeInterval(5)), holes: confirmationHoles,
            now: first.addingTimeInterval(5)), 2)
    }

    func testProductSpec513SameTimestampDifferentCoordinatesAreNotReplay() {
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        let now = Date(timeIntervalSince1970: 100)
        XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(coordinate(40.001, 116), at: now), holes: confirmationHoles, now: now))
        XCTAssertEqual(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
            fix: fix(coordinate(40.002, 116), at: now), holes: confirmationHoles, now: now), 2)
    }

    private var confirmationHoles: [HoleLocatorGeometry] {
        [HoleLocatorGeometry(hole: 2, tee: coordinate(40, 116), green: coordinate(40.004, 116))]
    }

    private func fix(_ point: CLLocationCoordinate2D, at date: Date, accuracy: Double = 5) -> LocationFix {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return LocationFix(coordinate: point, horizontalAccuracyM: accuracy, altitudeM: nil,
                           capturedAt: formatter.string(from: date))
    }

    private func coordinate(_ latitude: Double, _ longitude: Double) -> CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}
