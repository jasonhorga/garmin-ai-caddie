import XCTest
@testable import AICaddie

final class PhoneRoundIdleTrackerTests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_800_000_000)
    private let course: [(latitude: Double, longitude: Double)] = [(40.0, 116.0)]

    private func minutes(_ value: Double) -> Date {
        start.addingTimeInterval(value * 60)
    }

    func testLeavingKnownCourseFinishesAfterTenMinutes() {
        var tracker = PhoneRoundIdleTracker()
        XCTAssertEqual(tracker.evaluate(latitude: 40, longitude: 116, at: start,
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .none)
        XCTAssertEqual(tracker.evaluate(latitude: 40.03, longitude: 116, at: minutes(9),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .none)
        XCTAssertEqual(tracker.evaluate(latitude: 40.04, longitude: 116, at: minutes(19),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .finishLeftCourse)
    }

    func testStationaryRoundOnlyPausesAfterFortyFiveMinutes() {
        var tracker = PhoneRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40, longitude: 116, at: start,
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: true, allHolesScored: false)
        XCTAssertEqual(tracker.evaluate(latitude: 40.0001, longitude: 116, at: minutes(44),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .none)
        XCTAssertEqual(tracker.evaluate(latitude: 40.0001, longitude: 116, at: minutes(45),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .pauseStationary)
    }

    func testCompletedRoundFinishesAfterTwentyMinutes() {
        var tracker = PhoneRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40, longitude: 116, at: start,
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: true, allHolesScored: true)
        XCTAssertEqual(tracker.evaluate(latitude: 40, longitude: 116, at: minutes(19),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: true), .none)
        XCTAssertEqual(tracker.evaluate(latitude: 40, longitude: 116, at: minutes(20),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: true), .finishAfterCompletedRound)
    }

    func testWrongCourseOnlyPromptsAndNeverFinishes() {
        var tracker = PhoneRoundIdleTracker()
        XCTAssertEqual(tracker.evaluate(latitude: 40.03, longitude: 116, at: start,
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .none)
        XCTAssertEqual(tracker.evaluate(latitude: 40.04, longitude: 116, at: minutes(10),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .wrongCourse)
    }

    func testNoStrokeNeverCreatesAnAutomaticAction() {
        var tracker = PhoneRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40, longitude: 116, at: start,
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: false, allHolesScored: true)
        XCTAssertEqual(tracker.evaluate(latitude: 40, longitude: 116, at: minutes(60),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: false, allHolesScored: true), .none)
    }

    /// Design round-flow §4: a round with no recorded stroke is not saved, pushed or prompted
    /// when the player leaves; only a course the player never reached is a wrong-course prompt.
    func testLeavingWithoutAStrokeStaysSilent() {
        var tracker = PhoneRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40, longitude: 116, at: start,
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: false, allHolesScored: false)
        XCTAssertEqual(tracker.evaluate(latitude: 40.04, longitude: 116, at: minutes(1),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: false, allHolesScored: false), .none)
        XCTAssertEqual(tracker.evaluate(latitude: 40.04, longitude: 116, at: minutes(12),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: false, allHolesScored: false), .none)
    }

    func testGPSGapResetsTheOffCourseClock() {
        var tracker = PhoneRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40, longitude: 116, at: start,
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: true, allHolesScored: false)
        _ = tracker.evaluate(latitude: 40.04, longitude: 116, at: minutes(1),
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: true, allHolesScored: false)
        _ = tracker.evaluate(latitude: nil, longitude: nil, at: minutes(5),
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: true, allHolesScored: false)
        XCTAssertEqual(tracker.evaluate(latitude: 40.04, longitude: 116, at: minutes(11),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: false), .none)
    }

    func testWrongCourseWithLaterGPSGapNeverAutoFinishesCompletedRound() {
        var tracker = PhoneRoundIdleTracker()
        _ = tracker.evaluate(latitude: 40.04, longitude: 116, at: start,
                             coursePoints: course, lastActivityAt: start,
                             hasRecordedStroke: true, allHolesScored: true)
        XCTAssertEqual(tracker.evaluate(latitude: nil, longitude: nil, at: minutes(21),
                                        coursePoints: course, lastActivityAt: start,
                                        hasRecordedStroke: true, allHolesScored: true), .none)
    }
}
