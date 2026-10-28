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

    func testProductSpec513OverlappingCorridorBoundaryNeedsDeeperEntry() {
        let longitudePerMetre = 1 / (111_320 * cos(40.002 * .pi / 180))
        let holes = [
            HoleLocatorGeometry(hole: 1, tee: coordinate(40, 116), green: coordinate(40.004, 116)),
            HoleLocatorGeometry(hole: 2, tee: coordinate(40, 116 + 60 * longitudePerMetre),
                                green: coordinate(40.004, 116 + 60 * longitudePerMetre)),
        ]
        let shallow = coordinate(40.002, 116 + 31 * longitudePerMetre)
        XCTAssertEqual(CurrentHoleLocator.locate(coordinate: shallow, horizontalAccuracyM: 5,
                                                holes: holes), .onHole(2))
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        for elapsed in [0.0, 6.0] {
            let now = Date(timeIntervalSince1970: 100 + elapsed)
            XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                fix: fix(shallow, at: now), holes: holes, now: now))
        }
        XCTAssertEqual(following.lastLocatedHole, 1)
    }

    func testProductSpec513OverlappingFairwayBoundaryNeedsDeeperEntry() {
        let longitudePerMetre = 1 / (111_320 * cos(40.002 * .pi / 180))
        func rectangle(_ left: Double, _ right: Double) -> [CLLocationCoordinate2D] {
            [coordinate(40.001, 116 + left * longitudePerMetre),
             coordinate(40.003, 116 + left * longitudePerMetre),
             coordinate(40.003, 116 + right * longitudePerMetre),
             coordinate(40.001, 116 + right * longitudePerMetre)]
        }
        let holes = [
            HoleLocatorGeometry(hole: 1, tee: nil, green: nil, fairway: [rectangle(-30, 30)]),
            HoleLocatorGeometry(hole: 2, tee: nil, green: nil, fairway: [rectangle(0, 80)]),
        ]
        let shallow = coordinate(40.002, 116 + 31 * longitudePerMetre)
        XCTAssertEqual(CurrentHoleLocator.locate(coordinate: shallow, horizontalAccuracyM: 5,
                                                holes: holes), .onHole(2))
        var following = PrepHoleFollowingState()
        _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
        for elapsed in [0.0, 6.0] {
            let now = Date(timeIntervalSince1970: 100 + elapsed)
            XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                fix: fix(shallow, at: now), holes: holes, now: now))
        }
        XCTAssertEqual(following.lastLocatedHole, 1)
    }

    func testProductSpec513FairwayAndTeeEntryDepthUseTheirOwnBoundaries() {
        let centre = coordinate(40.002, 116)
        let fairway = [coordinate(40.0015, 115.999), coordinate(40.0025, 115.999),
                       coordinate(40.0025, 116.001), coordinate(40.0015, 116.001)]
        let holes = [HoleLocatorGeometry(hole: 2, tee: coordinate(40, 116),
                                        green: coordinate(40.004, 116), fairway: [fairway])]
        XCTAssertGreaterThan(CurrentHoleLocator.entryDepthM(hole: 2, coordinate: centre, holes: holes), 50)
        let edge = coordinate(40.00151, 116)
        XCTAssertLessThan(CurrentHoleLocator.entryDepthM(hole: 2, coordinate: edge, holes: holes), 2)
        XCTAssertEqual(CurrentHoleLocator.entryDepthM(hole: 2, coordinate: coordinate(40, 116),
                                                     holes: holes), CurrentHoleLocator.teeRadiusM,
                       accuracy: 0.001)
    }

    func testProductSpec513DepthMustExceedAccuracyAndThirtyMetreAccuracyIsAllowed() {
        let longitudePerMetre = 1 / (111_320 * cos(40.002 * .pi / 180))
        // At 28 m from the centre the 22 m interior margin does not beat a 25 m uncertainty.
        let cases: [(Double, Double, Int?)] = [(28, 25, nil), (0, 30, 2)]
        for (offset, accuracy, expected) in cases {
            var following = PrepHoleFollowingState()
            _ = following.navigationTarget(currentLocatedHole: 1, displayedHole: 1)
            let now = Date(timeIntervalSince1970: 100)
            let point = coordinate(40.002, 116 + offset * longitudePerMetre)
            XCTAssertNil(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                fix: fix(point, at: now, accuracy: accuracy), holes: confirmationHoles, now: now))
            XCTAssertEqual(following.navigationTarget(currentLocatedHole: 2, displayedHole: 1,
                fix: fix(point, at: now.addingTimeInterval(5), accuracy: accuracy),
                holes: confirmationHoles, now: now.addingTimeInterval(5)), expected)
        }
    }

    /// Product spec 5.13: real transitions must still work between nearby, distinct tees.
    func testProductSpec513NearbyTeesConfirmThroughLocationEnvelope() {
        for separation in [20.0, 30.0] {
            for accuracy in [5.0, 15.0] {
                let holes = [
                    parallelHole(1, eastM: 0), parallelHole(2, eastM: separation),
                ]
                var following = PrepHoleFollowingState()
                let start = Date(timeIntervalSince1970: 100)
                XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: 0),
                                    time: start, accuracy: accuracy, displayedHole: 1, holes: holes))
                XCTAssertEqual(following.lastLocatedHole, 1)
                XCTAssertNil(follow(&following, at: localPoint(eastM: separation, northM: 0),
                                    time: start.addingTimeInterval(1), accuracy: accuracy,
                                    displayedHole: 1, holes: holes))
                XCTAssertEqual(follow(&following, at: localPoint(eastM: separation, northM: 0),
                                      time: start.addingTimeInterval(6), accuracy: accuracy,
                                      displayedHole: 1, holes: holes), 2,
                               "5.13: separation \(separation)m, accuracy \(accuracy)m must reach hole 2")
            }
        }
    }

    func testProductSpec513SharedTeeKeepsDisplayedLoopAndConfirmsPackageChoiceAfterFiveSeconds() {
        let holes = [parallelHole(1, eastM: 0), parallelHole(10, eastM: 0),
                     parallelHole(9, eastM: -120)]
        let start = Date(timeIntervalSince1970: 100)
        for displayed in [1, 10] {
            var following = PrepHoleFollowingState()
            for elapsed in [0.0, 6.0] {
                XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: 0),
                                    time: start.addingTimeInterval(elapsed),
                                    displayedHole: displayed, holes: holes))
            }
            XCTAssertEqual(following.lastLocatedHole, displayed,
                           "5.13: a shared 1/10 anchor must keep the displayed loop")
        }
        var following = PrepHoleFollowingState()
        _ = follow(&following, at: localPoint(eastM: -120, northM: 0), time: start,
                   displayedHole: 9, holes: holes)
        XCTAssertEqual(following.lastLocatedHole, 9)
        XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: 0),
                            time: start.addingTimeInterval(1), displayedHole: 9, holes: holes))
        // Movement within a shared start area does not bypass its 5 s time confirmation.
        XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: 12),
                            time: start.addingTimeInterval(2), displayedHole: 9, holes: holes))
        XCTAssertEqual(follow(&following, at: localPoint(eastM: 0, northM: 12),
                              time: start.addingTimeInterval(6), displayedHole: 9, holes: holes), 1)
    }

    func testProductSpec513NormalGreenToNextTeeRouteConfirmsThroughLocationEnvelope() {
        let holes = [
            HoleLocatorGeometry(hole: 5, tee: localPoint(eastM: 0, northM: -360),
                                green: localPoint(eastM: 0, northM: -60),
                                fairway: [localRectangle(left: -15, right: 15, bottom: -360, top: -55)]),
            parallelHole(6, eastM: 0),
        ]
        let start = Date(timeIntervalSince1970: 100)
        var following = PrepHoleFollowingState()
        XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: -60), time: start,
                            displayedHole: 5, holes: holes))
        XCTAssertEqual(following.lastLocatedHole, 5)
        XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: -35),
                            time: start.addingTimeInterval(1), displayedHole: 5, holes: holes))
        XCTAssertEqual(follow(&following, at: localPoint(eastM: 0, northM: 0),
                              time: start.addingTimeInterval(3), displayedHole: 5, holes: holes), 6)
    }

    func testProductSpec513CandidateAreaEdgesDoNotCancelARealTransition() {
        let holes = [parallelHole(1, eastM: -120), parallelHole(2, eastM: 0)]
        let start = Date(timeIntervalSince1970: 100)
        var following = PrepHoleFollowingState()
        _ = follow(&following, at: localPoint(eastM: -120, northM: 0), time: start,
                   displayedHole: 1, holes: holes)
        XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: 0),
                            time: start.addingTimeInterval(1), displayedHole: 1, holes: holes))
        // Beyond the new tee disc and just 1 m inside its fairway, still far from the old hole.
        XCTAssertEqual(follow(&following, at: localPoint(eastM: 14, northM: 80),
                              time: start.addingTimeInterval(2), displayedHole: 1, holes: holes), 2)
        // Moving from that fairway to the new hole's corridor keeps the same confirmed hole.
        XCTAssertNil(follow(&following, at: localPoint(eastM: 16, northM: 110),
                            time: start.addingTimeInterval(3), displayedHole: 2, holes: holes))
        XCTAssertEqual(following.lastLocatedHole, 2)
    }

    func testProductSpec513UnrelatedNearbyTeeDoesNotBlockLeavingDisplayedHole() {
        let holes = [parallelHole(1, eastM: -120), parallelHole(2, eastM: 0),
                     parallelHole(3, eastM: 12)]
        let start = Date(timeIntervalSince1970: 100)
        var following = PrepHoleFollowingState()
        _ = follow(&following, at: localPoint(eastM: -120, northM: 0), time: start,
                   displayedHole: 1, holes: holes)
        XCTAssertNil(follow(&following, at: localPoint(eastM: 0, northM: 0),
                            time: start.addingTimeInterval(1), displayedHole: 1, holes: holes))
        XCTAssertEqual(follow(&following, at: localPoint(eastM: 0, northM: 0),
                              time: start.addingTimeInterval(6), displayedHole: 1, holes: holes), 2)
    }

    private func follow(
        _ following: inout PrepHoleFollowingState, at point: CLLocationCoordinate2D, time: Date,
        accuracy: Double = 5, displayedHole: Int, holes: [HoleLocatorGeometry]
    ) -> Int? {
        let locatedHole = CurrentHoleLocator.locate(coordinate: point, horizontalAccuracyM: accuracy,
                                                   holes: holes, preferredHole: displayedHole).hole
        return following.navigationTarget(currentLocatedHole: locatedHole, displayedHole: displayedHole,
            fix: fix(point, at: time, accuracy: accuracy), holes: holes, now: time)
    }

    private func localPoint(eastM: Double, northM: Double) -> CLLocationCoordinate2D {
        coordinate(40 + northM / 111_320, 116 + eastM / (111_320 * cos(40 * .pi / 180)))
    }

    private func localRectangle(left: Double, right: Double, bottom: Double, top: Double)
        -> [CLLocationCoordinate2D] {
        [localPoint(eastM: left, northM: bottom), localPoint(eastM: right, northM: bottom),
         localPoint(eastM: right, northM: top), localPoint(eastM: left, northM: top)]
    }

    private func parallelHole(_ hole: Int, eastM: Double) -> HoleLocatorGeometry {
        HoleLocatorGeometry(hole: hole, tee: localPoint(eastM: eastM, northM: 0),
                            green: localPoint(eastM: eastM, northM: 400),
                            fairway: [localRectangle(left: eastM - 15, right: eastM + 15,
                                                     bottom: 0, top: 100)])
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
