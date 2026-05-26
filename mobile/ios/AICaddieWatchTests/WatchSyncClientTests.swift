import XCTest
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif
@testable import AICaddieWatch

final class WatchSyncClientTests: XCTestCase {
    func testQueueInputEventSerializesPendingEvents() throws {
        let queueURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("queued_events.json")
        let client = WatchSyncClient(queueURL: queueURL)
        let event = WatchInputEvent(
            eventId: "event-1",
            roundId: "round-1",
            hole: 3,
            kind: .club,
            value: "8I",
            createdAt: "2026-05-25T00:00:00Z"
        )

        try client.queueInputEvent(event)

        XCTAssertEqual(try client.loadQueuedEvents(), [event])
    }

    func testReceiveStatePersistsLastRoundStateForOfflineRelaunch() throws {
        let directoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let queueURL = directoryURL.appendingPathComponent("queued_events.json")
        let stateURL = directoryURL.appendingPathComponent("current_state.json")
        let state = WatchRoundState(
            roundId: "round-1",
            hole: 7,
            par: 4,
            distanceM: 142,
            suggestedClub: "8I",
            selectedClub: "8I",
            score: 4,
            putts: 2,
            penaltyCount: 0,
            caddieConfidence: "medium"
        )
        let client = WatchSyncClient(queueURL: queueURL, stateURL: stateURL)

        client.receiveState(state)
        let relaunched = WatchSyncClient(queueURL: queueURL, stateURL: stateURL)

        XCTAssertEqual(relaunched.currentState, state)
    }

    #if canImport(WatchConnectivity)
    func testDidReceiveUserInfoPersistsRoundStateLikeInteractiveMessage() throws {
        let directoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let queueURL = directoryURL.appendingPathComponent("queued_events.json")
        let stateURL = directoryURL.appendingPathComponent("current_state.json")
        let state = WatchRoundState(
            roundId: "round-1",
            hole: 7,
            par: 4,
            distanceM: 142,
            suggestedClub: "8I",
            selectedClub: "8I",
            score: 4,
            putts: 2,
            penaltyCount: 0,
            caddieConfidence: "medium"
        )
        let client = WatchSyncClient(queueURL: queueURL, stateURL: stateURL)

        client.session(WCSession.default, didReceiveUserInfo: ["state": try Self.jsonObject(from: state)])

        XCTAssertEqual(client.currentState, state)
        XCTAssertEqual(try client.loadPersistedState(), state)
    }
    #endif

    private static func jsonObject<T: Encodable>(from value: T) throws -> Any {
        let data = try JSONEncoder().encode(value)
        return try JSONSerialization.jsonObject(with: data)
    }
}
