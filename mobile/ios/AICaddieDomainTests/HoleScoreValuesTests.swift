import XCTest
@testable import AICaddieDomain

/// The score rule the phone and the Watch share (README §3).
final class HoleScoreValuesTests: XCTestCase {
    func testTheTotalNeverDropsBelowOneFullShot() {
        let values = HoleScoreValues(score: 2, putts: 3, penalty: 1)
        XCTAssertEqual(values.score, 5)
        XCTAssertEqual(values.minimumScore, 5)
    }

    func testRaisingPuttsOrPenaltyLiftsTheTotalOnlyWhenItMust() {
        var values = HoleScoreValues(score: 6, putts: 2, penalty: 0)
        XCTAssertTrue(values.selectPutts(3))
        XCTAssertEqual(values.score, 6, "room left: the chosen total stays")
        XCTAssertTrue(values.selectPutts(5))
        XCTAssertEqual(values.score, 6)
        XCTAssertTrue(values.selectPenalty(1))
        XCTAssertEqual(values.score, 7, "5 putts + 1 penalty needs at least 7")
    }

    func testLoweringPuttsOrPenaltyNeverLowersTheTotal() {
        var values = HoleScoreValues(score: 5, putts: 2, penalty: 1)
        XCTAssertTrue(values.selectPutts(1))
        XCTAssertTrue(values.selectPenalty(0))
        XCTAssertEqual(values.score, 5)
    }

    func testALowerTotalGivesWayPuttsFirstThenPenalty() {
        var values = HoleScoreValues(score: 6, putts: 3, penalty: 2)
        XCTAssertTrue(values.selectScore(4))
        XCTAssertEqual(values.putts, 1)
        XCTAssertEqual(values.penalty, 2)
        XCTAssertTrue(values.selectScore(2))
        XCTAssertEqual(values.putts, 0)
        XCTAssertEqual(values.penalty, 1)
        XCTAssertTrue(values.selectScore(0))
        XCTAssertEqual(values.score, 1)
        XCTAssertEqual(values.penalty, 0)
    }

    func testLimitsAndNoChangeReports() {
        var values = HoleScoreValues(score: 30, putts: 12, penalty: -1)
        XCTAssertEqual(values.putts, HoleScoreValues.maximumPutts)
        XCTAssertEqual(values.penalty, 0)
        XCTAssertEqual(values.score, 30, "no cap on the total")
        XCTAssertFalse(values.selectPutts(10), "already at the maximum")
        XCTAssertFalse(values.selectPenalty(-1))
        XCTAssertFalse(values.selectScore(30))
    }
}
