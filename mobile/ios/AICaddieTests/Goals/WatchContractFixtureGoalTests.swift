// size: medium
// goals: W-08, W-10
import Foundation
import XCTest
import AICaddieCore
@testable import AICaddie

/// The phone end of the watch↔phone contract: the phone reads the same shared fixtures the Watch
/// tests read (mobile/contracts/fixtures/watch), so the two ends cannot pass against different data.
final class WatchContractFixtureGoalTests: XCTestCase {
    override func setUp() {
        super.setUp()
        ensureC156TopoBundleStub()
    }

    // goals: W-10
    /// The round snapshot the phone sends carries exactly the fields of the shared contract fixture.
    func testPhoneRoundSnapshotMatchesSharedFixtureBothWays() throws {
        let fixture = try Self.fixtureData("round_state.fixture.json")

        let payload = try JSONDecoder().decode(WatchRoundStatePayload.self, from: fixture)
        XCTAssertEqual(payload.roundId, "round-fixture-1")
        XCTAssertEqual(payload.hole, 7)
        XCTAssertEqual(payload.availableClubs.map(\.clubName), ["Driver", "7I"])
        XCTAssertEqual(payload.caddieOptions.map(\.optionId), ["opt-stock"])
        XCTAssertEqual(payload.hazards.map(\.kind), ["water"])
        XCTAssertEqual(payload.phoneShotEventIds, ["phone-shot-1"])
        XCTAssertEqual(payload.snapshotRevision, 42)

        let encoded = try JSONEncoder().encode(payload)
        XCTAssertEqual(try Self.object(encoded), try Self.object(fixture))
    }

    // goals: W-08
    /// A Watch score record in the shared fixture shape is accepted, acknowledged and kept by the phone.
    func testPhoneAcceptsWatchScoreFixture() throws {
        let directory = Self.temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let bridge = WatchEventBridge(offlineStore: store)
        var reply: [String: Any]?

        bridge.handleWatchInputMessage(["event": try Self.object(Self.fixtureData("input_score.fixture.json"))]) {
            reply = $0
        }

        XCTAssertEqual(reply?["accepted"] as? Bool, true)
        XCTAssertEqual(reply?["acceptedEventIds"] as? [String], ["watch-evt-score-1"])
        let events = try store.loadEvents()
        XCTAssertEqual(events.map(\.eventId), ["watch-evt-score-1"])
        XCTAssertEqual(events.first?.roundId, "round-fixture-1")
        XCTAssertEqual(events.first?.hole, 7)
        XCTAssertEqual(events.first?.clientId, "apple-watch")
        XCTAssertEqual(events.first?.payload["strokes"], .number(5))
    }

    // goals: W-08
    /// A Watch manual-shot location in the shared fixture shape becomes the phone's shot location.
    func testPhoneAcceptsWatchLocationFixture() throws {
        let directory = Self.temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let bridge = WatchEventBridge(offlineStore: store)
        var reply: [String: Any]?

        bridge.handleWatchInputMessage(["event": try Self.object(Self.fixtureData("input_location.fixture.json"))]) {
            reply = $0
        }

        XCTAssertEqual(reply?["acceptedEventIds"] as? [String], ["watch-evt-location-1"])
        let event = try XCTUnwrap(try store.loadEvents().first)
        XCTAssertEqual(event.kind, .location)
        XCTAssertEqual(event.payload["latitude"], .number(39.9042))
        XCTAssertEqual(event.payload["longitude"], .number(116.4074))
        XCTAssertEqual(event.payload["horizontalAccuracyM"], .number(6.5))
        XCTAssertEqual(event.payload["source"], .string("apple_watch"))
    }

    private static func fixtureData(_ name: String) throws -> Data {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: nil))
        return try Data(contentsOf: url)
    }

    private static func object(_ data: Data) throws -> NSDictionary {
        try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? NSDictionary)
    }

    private static func temporaryDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    }
}
