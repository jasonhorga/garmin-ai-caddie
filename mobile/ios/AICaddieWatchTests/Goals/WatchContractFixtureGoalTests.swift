// size: medium
// goals: W-08, W-10
import Foundation
import XCTest
import AICaddieCore
@testable import AICaddieWatch

/// The Watch end reads the same contract fixtures that the iPhone target receives as resources.
/// This keeps the two sides of the WatchConnectivity contract on one canonical payload shape.
final class WatchContractFixtureGoalTests: XCTestCase {
    // goals: W-10
    /// The Watch decodes the shared round snapshot and input event fixtures without a target-local copy.
    func testWatchDecodesSharedRoundAndInputFixtures() throws {
        let round = try JSONDecoder().decode(WatchRoundState.self, from: Self.fixture("round_state.fixture.json"))
        XCTAssertEqual(round.roundId, "round-fixture-1")
        XCTAssertEqual(round.hole, 7)
        XCTAssertEqual(round.availableClubNames, ["Driver", "7I"])
        XCTAssertEqual(round.snapshotRevision, 42)

        let score = try JSONDecoder().decode(WatchInputEvent.self, from: Self.fixture("input_score.fixture.json"))
        XCTAssertEqual(score.eventId, "watch-evt-score-1")
        XCTAssertEqual(score.kind, .score)
        XCTAssertEqual(score.value, "5")

        let location = try JSONDecoder().decode(WatchInputEvent.self, from: Self.fixture("input_location.fixture.json"))
        XCTAssertEqual(location.eventId, "watch-evt-location-1")
        XCTAssertEqual(location.kind, .location)
        XCTAssertEqual(WatchShotLocationValue(encodedValue: location.value)?.horizontalAccuracyM, 6.5)
    }

    // goals: W-08
    /// Watch-produced score and shot-location messages use the exact shared shape consumed by the phone.
    func testWatchEncodesInputEventsMatchingSharedFixtures() throws {
        let events = [
            ("input_score.fixture.json", WatchInputEvent(
                eventId: "watch-evt-score-1", roundId: "round-fixture-1", hole: 7,
                kind: .score, value: "5", createdAt: "2026-11-08T10:00:00Z"
            )),
            ("input_location.fixture.json", WatchInputEvent(
                eventId: "watch-evt-location-1", roundId: "round-fixture-1", hole: 7,
                kind: .location, value: "39.9042,116.4074,6.5", createdAt: "2026-11-08T10:01:00Z",
                contextClub: "Driver", shotType: "tee"
            )),
        ]
        for (name, event) in events {
            let actual = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(event)) as? NSDictionary)
            let expected = try XCTUnwrap(JSONSerialization.jsonObject(with: Self.fixture(name)) as? NSDictionary)
            XCTAssertEqual(actual, expected, name)
        }
    }

    private static func fixture(_ name: String) throws -> Data {
        let bundle = Bundle(for: Self.self)
        let url = try XCTUnwrap(bundle.url(forResource: name, withExtension: nil))
        return try Data(contentsOf: url)
    }
}
