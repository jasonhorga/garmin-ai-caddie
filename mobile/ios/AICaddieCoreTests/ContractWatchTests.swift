// size: small
// goals: I-18, W-08
import AICaddieCore
import XCTest

/// I-18 / W-08: the Watch input payload and the phone's acknowledgement decode the same way on both
/// sides, including legacy single-event replies.
final class ContractWatchTests: XCTestCase {
    // goals: I-18
    func testInputEventEncodesSchemaAndRoundTrips() throws {
        let event = WatchInputEvent(
            eventId: "e1",
            roundId: "round-a",
            hole: 7,
            kind: .score,
            value: "5",
            createdAt: "2026-11-08T10:00:00Z",
            contextClub: "7I",
            strategyMode: "SAFE",
            distanceToPinM: 142.5,
            decisionId: "d-1",
            fairwayResult: "LEFT"
        )

        let data = try JSONEncoder().encode(event)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["schema"] as? String, "ai-caddie-watch-input-event-v1")
        XCTAssertEqual(object["kind"] as? String, "score")
        XCTAssertEqual(object["hole"] as? Int, 7)
        XCTAssertEqual(object["fairwayResult"] as? String, "LEFT")

        let decoded = try JSONDecoder().decode(WatchInputEvent.self, from: data)
        XCTAssertEqual(decoded, event)
    }

    // goals: I-18
    func testShotLocationValueRoundTripsAndRejectsImpossibleFixes() throws {
        let value = try XCTUnwrap(
            WatchShotLocationValue(latitude: 31.25, longitude: 121.5, horizontalAccuracyM: 4)
        )
        XCTAssertEqual(value.encodedValue, "31.25,121.5,4.0")
        XCTAssertEqual(WatchShotLocationValue(encodedValue: value.encodedValue), value)

        XCTAssertNil(WatchShotLocationValue(latitude: 91, longitude: 0, horizontalAccuracyM: 1))
        XCTAssertNil(WatchShotLocationValue(latitude: 0, longitude: 181, horizontalAccuracyM: 1))
        XCTAssertNil(WatchShotLocationValue(latitude: 0, longitude: 0, horizontalAccuracyM: -1))
        XCTAssertNil(WatchShotLocationValue(latitude: .nan, longitude: 0, horizontalAccuracyM: 1))
        XCTAssertNil(WatchShotLocationValue(encodedValue: "31.25,121.5"))
        XCTAssertNil(WatchShotLocationValue(encodedValue: "31.25,east,4"))
    }

    // goals: W-08
    func testLegacySingleEventAcknowledgement() {
        let accepted = WatchSyncAcknowledgement.decode(["accepted": true], fallbackEventId: "e1")
        XCTAssertEqual(accepted.acceptedEventIds, ["e1"])
        XCTAssertEqual(accepted.phoneSequence, 0)

        let refused = WatchSyncAcknowledgement.decode(["accepted": false, "eventId": "e2"], fallbackEventId: "e1")
        XCTAssertEqual(refused.acceptedEventIds, [])
        XCTAssertEqual(refused.resolvedEventIds, [])
    }

    // goals: W-08
    func testBatchAcknowledgementSeparatesAcknowledgedFromRejected() {
        let ack = WatchSyncAcknowledgement.decode(
            [
                "accepted": true,
                "acceptedEventIds": ["e1", "e2"],
                "duplicateEventIds": ["e3"],
                "rejectedEventIds": ["e4"],
                "watchAckSequence": 7.0,
            ],
            fallbackEventId: "e1"
        )

        XCTAssertEqual(ack.acknowledgedEventIds, ["e1", "e2", "e3"])
        XCTAssertEqual(ack.resolvedEventIds, ["e1", "e2", "e3", "e4"])
        XCTAssertEqual(ack.phoneSequence, 7)
    }

    // goals: W-08
    func testPhoneSequenceWinsOverLegacySequenceAndIgnoresNonFiniteValues() {
        let both = WatchSyncAcknowledgement.decode(
            ["phoneSequence": 9, "watchAckSequence": 3],
            fallbackEventId: "e1"
        )
        XCTAssertEqual(both.phoneSequence, 9)

        let infinite = WatchSyncAcknowledgement.decode(["phoneSequence": Double.infinity], fallbackEventId: "e1")
        XCTAssertEqual(infinite.phoneSequence, 0)
    }
}
