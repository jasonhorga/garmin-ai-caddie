// size: small
// goals: I-08, I-09

import AICaddieCore
import AICaddieDomain
import XCTest

final class ScoreInvariantGoalTests: XCTestCase {
    // goals: I-08 [main]
    func testScoreAlwaysCoversPuttsAndPenaltyAndSelectionsRemainConsistent() {
        var values = HoleScoreValues(score: 2, putts: 2, penalty: 1)
        XCTAssertEqual(values.score, 4)
        values.selectPutts(4)
        XCTAssertEqual(values.score, 6)
        values.selectPenalty(3)
        XCTAssertEqual(values.score, 8)
        values.selectScore(3)
        XCTAssertEqual(values.score, 3)
        XCTAssertLessThanOrEqual(values.putts + values.penalty + 1, values.score)
    }

    // goals: I-08
    func testRaisingPuttsRaisesOnlyTheNecessaryTotal() {
        var values = HoleScoreValues(score: 4, putts: 1, penalty: 0)
        XCTAssertTrue(values.selectPutts(5))
        XCTAssertEqual(values.score, 6)
        XCTAssertFalse(values.selectPutts(5))
    }

    // goals: I-08
    func testRaisingPenaltyRaisesOnlyTheNecessaryTotal() {
        var values = HoleScoreValues(score: 4, putts: 1, penalty: 0)
        XCTAssertTrue(values.selectPenalty(4))
        XCTAssertEqual(values.score, 6)
        XCTAssertFalse(values.selectPenalty(4))
    }

    // goals: I-08
    func testLoweringScoreGivesWayToPuttsThenPenalty() {
        var values = HoleScoreValues(score: 8, putts: 4, penalty: 2)
        XCTAssertTrue(values.selectScore(3))
        XCTAssertEqual(values.score, 3)
        XCTAssertEqual(values.putts, 0)
        XCTAssertEqual(values.penalty, 2)
    }

    // goals: I-08
    func testWheelValuesAreClampedAndIdempotent() {
        var values = HoleScoreValues(score: 1, putts: -2, penalty: 99)
        XCTAssertEqual(values.putts, 0)
        XCTAssertEqual(values.penalty, 4)
        XCTAssertEqual(values.score, 5)
        XCTAssertFalse(values.selectPenalty(99))
    }

    // goals: I-09 [main]
    func testLocationAndScoreEventsRemainSaveableTogetherOrIndependently() throws {
        let location = WatchShotLocationValue(latitude: 31.2, longitude: 121.4, horizontalAccuracyM: 4.5)
        let locationEvent = WatchInputEvent(
            eventId: "location-1", roundId: "round-1", hole: 1, kind: .location,
            value: try XCTUnwrap(location).encodedValue, createdAt: "2026-11-10T00:00:00Z"
        )
        let scoreEvent = WatchInputEvent(
            eventId: "score-1", roundId: "round-1", hole: 1, kind: .score,
            value: "5", createdAt: "2026-11-10T00:00:01Z"
        )
        var locationQueue = WatchInputQueue()
        XCTAssertTrue(locationQueue.enqueue(locationEvent))
        let restoredLocation = try JSONDecoder().decode(
            [WatchInputEvent].self,
            from: JSONEncoder().encode(locationQueue.events)
        )
        XCTAssertEqual(restoredLocation, [locationEvent])
        XCTAssertEqual(
            WatchShotLocationValue(encodedValue: restoredLocation[0].value),
            location,
            "a saved GPS location survives the event persistence boundary"
        )

        var scoreOnlyQueue = WatchInputQueue()
        XCTAssertTrue(scoreOnlyQueue.enqueue(scoreEvent), "a score remains saveable when no GPS event is present")
        let restoredScore = try JSONDecoder().decode(
            [WatchInputEvent].self,
            from: JSONEncoder().encode(scoreOnlyQueue.events)
        )
        XCTAssertEqual(restoredScore, [scoreEvent])
        XCTAssertEqual(restoredScore[0].kind, .score)
        XCTAssertEqual(restoredScore[0].value, "5")
    }

    // goals: I-09
    func testInvalidLocationValuesAreRejected() {
        XCTAssertNil(WatchShotLocationValue(latitude: 91, longitude: 0, horizontalAccuracyM: 1))
        XCTAssertNil(WatchShotLocationValue(latitude: 0, longitude: 181, horizontalAccuracyM: 1))
        XCTAssertNil(WatchShotLocationValue(latitude: 0, longitude: 0, horizontalAccuracyM: -1))
        XCTAssertNil(WatchShotLocationValue(encodedValue: "nan,0,1"))
        XCTAssertNil(WatchShotLocationValue(encodedValue: "0,0"))
    }
}
