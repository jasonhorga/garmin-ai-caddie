import XCTest
@testable import AICaddieWatch

/// Owner battery report 2026-10-12: a round left open kept the workout session and GPS running.
final class WatchRoundIdleTrackerTests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_800_000_000)
    private let course: [(latitude: Double, longitude: Double)] = [(40.0, 116.0), (40.004, 116.0)]

    private func minutes(_ value: Double) -> Date { start.addingTimeInterval(value * 60) }

    func testLeavingTheCourseSetsTheRoundAsideAfterTenMinutes() {
        var tracker = WatchRoundIdleTracker()
        // ~2.2 km north of the last green, moving (driving away).
        XCTAssertNil(tracker.evaluate(latitude: 40.024, longitude: 116.0, at: start,
                                      holePoints: course, lastActivityAt: start, allHolesScored: false))
        XCTAssertNil(tracker.evaluate(latitude: 40.03, longitude: 116.0, at: minutes(9),
                                      holePoints: course, lastActivityAt: start, allHolesScored: false))
        XCTAssertEqual(tracker.evaluate(latitude: 40.04, longitude: 116.0, at: minutes(10),
                                        holePoints: course, lastActivityAt: start, allHolesScored: false),
                       .leftCourse)
    }

    func testInputKeepsARoundInPlayAwayFromTheMappedCourse() {
        var tracker = WatchRoundIdleTracker()
        // Wrong course chosen: the player is 2.2 km from every mapped hole but still scoring.
        _ = tracker.evaluate(latitude: 40.024, longitude: 116.0, at: start,
                             holePoints: course, lastActivityAt: start, allHolesScored: false)
        XCTAssertNil(tracker.evaluate(latitude: 40.024, longitude: 116.0, at: minutes(12),
                                      holePoints: course, lastActivityAt: minutes(8), allHolesScored: false))
        XCTAssertEqual(tracker.evaluate(latitude: 40.024, longitude: 116.0, at: minutes(18),
                                        holePoints: course, lastActivityAt: minutes(8), allHolesScored: false),
                       .leftCourse)
    }

    func testWithoutAnyFixOnlyInputKeepsARoundInPlay() {
        var tracker = WatchRoundIdleTracker()
        XCTAssertNil(tracker.evaluate(latitude: nil, longitude: nil, at: start,
                                      holePoints: course, lastActivityAt: start, allHolesScored: false))
        XCTAssertNil(tracker.evaluate(latitude: nil, longitude: nil, at: minutes(44),
                                      holePoints: course, lastActivityAt: start, allHolesScored: false))
        XCTAssertEqual(tracker.evaluate(latitude: nil, longitude: nil, at: minutes(45),
                                        holePoints: course, lastActivityAt: start, allHolesScored: false),
                       .stationary)
    }

    func testAScoreEnteredOnThePhoneCountsAsInput() {
        var tracker = WatchRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40.004, longitude: 116.0, at: start, holePoints: course,
                             lastActivityAt: start, scoredHoles: 17, allHolesScored: false)
        // The last hole arrives from the phone at minute 30; the watch recorded nothing since the start.
        XCTAssertNil(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: minutes(30), holePoints: course,
                                      lastActivityAt: start, scoredHoles: 18, allHolesScored: true))
        XCTAssertNil(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: minutes(49), holePoints: course,
                                      lastActivityAt: start, scoredHoles: 18, allHolesScored: true))
        XCTAssertEqual(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: minutes(50), holePoints: course,
                                        lastActivityAt: start, scoredHoles: 18, allHolesScored: true),
                       .finished)
    }

    func testComingBackOnTheCourseRestartsTheAwayClock() {
        var tracker = WatchRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40.024, longitude: 116.0, at: start,
                             holePoints: course, lastActivityAt: start, allHolesScored: false)
        _ = tracker.evaluate(latitude: 40.002, longitude: 116.0, at: minutes(6),
                             holePoints: course, lastActivityAt: start, allHolesScored: false)
        XCTAssertNil(tracker.evaluate(latitude: 40.024, longitude: 116.0, at: minutes(12),
                                      holePoints: course, lastActivityAt: start, allHolesScored: false),
                     "the away clock starts again after a return")
    }

    func testStandingStillWithNoInputForFortyFiveMinutesSetsItAside() {
        var tracker = WatchRoundIdleTracker()
        XCTAssertNil(tracker.evaluate(latitude: 40.001, longitude: 116.0, at: start,
                                      holePoints: course, lastActivityAt: start, allHolesScored: false))
        XCTAssertNil(tracker.evaluate(latitude: 40.0011, longitude: 116.0, at: minutes(44),
                                      holePoints: course, lastActivityAt: start, allHolesScored: false))
        XCTAssertEqual(tracker.evaluate(latitude: 40.0011, longitude: 116.0, at: minutes(45),
                                        holePoints: course, lastActivityAt: start, allHolesScored: false),
                       .stationary)
    }

    func testMovingOrRecordingKeepsARoundInPlay() {
        var tracker = WatchRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40.001, longitude: 116.0, at: start,
                             holePoints: course, lastActivityAt: start, allHolesScored: false)
        XCTAssertNil(tracker.evaluate(latitude: 40.0011, longitude: 116.0, at: minutes(50),
                                      holePoints: course, lastActivityAt: minutes(40), allHolesScored: false),
                     "a score recorded ten minutes ago")
        XCTAssertNil(tracker.evaluate(latitude: 40.003, longitude: 116.0, at: minutes(95),
                                      holePoints: course, lastActivityAt: minutes(40), allHolesScored: false),
                     "walked 200 m to the next tee")
    }

    func testResumingAFinishedRoundGetsTheFullGraceAgain() {
        var tracker = WatchRoundIdleTracker()
        // Resumed at minute 30 of an all-scored round whose last input was at minute 0.
        XCTAssertNil(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: minutes(30),
                                      holePoints: course, lastActivityAt: start, allHolesScored: true))
        XCTAssertNil(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: minutes(49),
                                      holePoints: course, lastActivityAt: start, allHolesScored: true))
        XCTAssertEqual(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: minutes(50),
                                        holePoints: course, lastActivityAt: start, allHolesScored: true),
                       .finished)
    }

    func testCoarseIndoorFixesDoNotCountAsMoving() {
        var tracker = WatchRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40.001, longitude: 116.0, horizontalAccuracyM: 8, at: start,
                             holePoints: course, lastActivityAt: start, allHolesScored: false)
        // A 65 m jump at 60 m accuracy is noise, not a walk.
        XCTAssertNil(tracker.evaluate(latitude: 40.0016, longitude: 116.0, horizontalAccuracyM: 60, at: minutes(30),
                                      holePoints: course, lastActivityAt: start, allHolesScored: false))
        XCTAssertEqual(tracker.evaluate(latitude: 40.0016, longitude: 116.0, horizontalAccuracyM: 60, at: minutes(45),
                                        holePoints: course, lastActivityAt: start, allHolesScored: false),
                       .stationary)
    }

    func testAFinishedRoundIsSetAsideTwentyMinutesAfterTheLastInput() {
        var tracker = WatchRoundIdleTracker()
        XCTAssertNil(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: start,
                                      holePoints: course, lastActivityAt: start, allHolesScored: true))
        XCTAssertNil(tracker.evaluate(latitude: 40.004, longitude: 116.0, at: minutes(19),
                                      holePoints: course, lastActivityAt: start, allHolesScored: true))
        XCTAssertEqual(tracker.evaluate(latitude: 40.0045, longitude: 116.0, at: minutes(20),
                                        holePoints: course, lastActivityAt: start, allHolesScored: true),
                       .finished)
    }
}
