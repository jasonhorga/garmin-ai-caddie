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

    func testAcknowledgedQueueRemovalKeepsUnconfirmedEvents() throws {
        let queueURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("queued_events.json")
        let client = WatchSyncClient(queueURL: queueURL)
        let first = WatchInputEvent(
            eventId: "event-1",
            roundId: "round-1",
            hole: 3,
            kind: .score,
            value: "4",
            createdAt: "2026-05-25T00:00:00Z"
        )
        let second = WatchInputEvent(
            eventId: "event-2",
            roundId: "round-1",
            hole: 3,
            kind: .club,
            value: "8I",
            createdAt: "2026-05-25T00:01:00Z"
        )
        let third = WatchInputEvent(
            eventId: "event-3",
            roundId: "round-1",
            hole: 3,
            kind: .putt,
            value: "2",
            createdAt: "2026-05-25T00:02:00Z"
        )

        try client.queueInputEvent(first)
        try client.queueInputEvent(second)
        try client.queueInputEvent(third)

        try client.markEventsAcknowledged(["event-1", "event-3"])

        XCTAssertEqual(try client.loadQueuedEvents(), [second])

        try client.markEventsAcknowledged(["event-2"])

        XCTAssertEqual(try client.loadQueuedEvents(), [])
    }

    func testAcknowledgementDecoderSupportsAcceptedDuplicateAndLegacyReplies() throws {
        let batch = WatchSyncAcknowledgement.decode(
            [
                "accepted": true,
                "eventId": "legacy-event",
                "acceptedEventIds": ["event-1", "event-2"],
                "duplicateEventIds": ["event-0"],
                "serverSequence": 42,
            ],
            fallbackEventId: "fallback-event"
        )

        XCTAssertEqual(batch.acceptedEventIds, ["event-1", "event-2"])
        XCTAssertEqual(batch.duplicateEventIds, ["event-0"])
        XCTAssertEqual(batch.acknowledgedEventIds, ["event-1", "event-2", "event-0"])
        XCTAssertEqual(batch.serverSequence, 42)

        let legacy = WatchSyncAcknowledgement.decode(["accepted": true, "eventId": "legacy-event"], fallbackEventId: "fallback-event")

        XCTAssertEqual(legacy.acceptedEventIds, ["legacy-event"])
        XCTAssertEqual(legacy.duplicateEventIds, [])
        XCTAssertEqual(legacy.acknowledgedEventIds, ["legacy-event"])

        let rejected = WatchSyncAcknowledgement.decode(["accepted": false, "eventId": "rejected-event"], fallbackEventId: "fallback-event")

        XCTAssertEqual(rejected.acceptedEventIds, [])
        XCTAssertEqual(rejected.duplicateEventIds, [])
        XCTAssertEqual(rejected.acknowledgedEventIds, [])
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

    func testQueuedQuickInputUpdatesPersistedCurrentState() throws {
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

        try client.queueInputEvent(
            WatchInputEvent(
                eventId: "event-1",
                roundId: "round-1",
                hole: 7,
                kind: .club,
                value: "7I",
                createdAt: "2026-05-25T00:00:00Z"
            )
        )

        XCTAssertEqual(client.currentState?.selectedClub, "7I")
        XCTAssertEqual(try client.loadPersistedState()?.selectedClub, "7I")
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
