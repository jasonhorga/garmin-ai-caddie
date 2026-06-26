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

        XCTAssertEqual(client.queuedEventCount, 1)
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

        XCTAssertEqual(client.queuedEventCount, 1)
        XCTAssertEqual(try client.loadQueuedEvents(), [second])

        try client.markEventsAcknowledged(["event-2"])

        XCTAssertEqual(client.queuedEventCount, 0)
        XCTAssertEqual(try client.loadQueuedEvents(), [])
    }

    func testAcknowledgementDecoderSupportsAcceptedDuplicateAndLegacyReplies() throws {
        let batch = WatchSyncAcknowledgement.decode(
            [
                "accepted": true,
                "eventId": "legacy-event",
                "acceptedEventIds": ["event-1", "event-2"],
                "duplicateEventIds": ["event-0"],
                "phoneSequence": 42,
            ],
            fallbackEventId: "fallback-event"
        )

        XCTAssertEqual(batch.acceptedEventIds, ["event-1", "event-2"])
        XCTAssertEqual(batch.duplicateEventIds, ["event-0"])
        XCTAssertEqual(batch.rejectedEventIds, [])
        XCTAssertEqual(batch.acknowledgedEventIds, ["event-1", "event-2", "event-0"])
        XCTAssertEqual(batch.resolvedEventIds, ["event-1", "event-2", "event-0"])
        XCTAssertEqual(batch.phoneSequence, 42)

        let legacy = WatchSyncAcknowledgement.decode(["accepted": true, "eventId": "legacy-event"], fallbackEventId: "fallback-event")

        XCTAssertEqual(legacy.acceptedEventIds, ["legacy-event"])
        XCTAssertEqual(legacy.duplicateEventIds, [])
        XCTAssertEqual(legacy.acknowledgedEventIds, ["legacy-event"])

        let rejected = WatchSyncAcknowledgement.decode(
            [
                "accepted": false,
                "eventId": "rejected-event",
                "rejectedEventIds": ["rejected-event"],
                "reason": "missing_club_context",
            ],
            fallbackEventId: "fallback-event"
        )

        XCTAssertEqual(rejected.acceptedEventIds, [])
        XCTAssertEqual(rejected.duplicateEventIds, [])
        XCTAssertEqual(rejected.rejectedEventIds, ["rejected-event"])
        XCTAssertEqual(rejected.acknowledgedEventIds, [])
        XCTAssertEqual(rejected.resolvedEventIds, ["rejected-event"])
    }

    func testRejectedAcknowledgementIdsCanBeRemovedFromQueue() throws {
        let queueURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("queued_events.json")
        let client = WatchSyncClient(queueURL: queueURL)
        let event = WatchInputEvent(
            eventId: "bad-event",
            roundId: "round-1",
            hole: 3,
            kind: .distance,
            value: "155",
            createdAt: "2026-05-25T00:00:00Z"
        )
        let acknowledgement = WatchSyncAcknowledgement.decode(
            ["accepted": false, "eventId": "bad-event", "rejectedEventIds": ["bad-event"]],
            fallbackEventId: "fallback-event"
        )

        try client.queueInputEvent(event)
        try client.markEventsAcknowledged(acknowledgement.resolvedEventIds)

        XCTAssertEqual(try client.loadQueuedEvents(), [])
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

    func testReceiveStateMergesUnacknowledgedWatchEditsOverAStalePhoneSnapshot() throws {
        // P1-12: the watch edits score on-wrist (queued, not yet acked); a phone snapshot that predates
        // that edit must NOT clobber it — the still-queued edit is re-applied on top of the snapshot.
        let directoryURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let queueURL = directoryURL.appendingPathComponent("queued_events.json")
        let stateURL = directoryURL.appendingPathComponent("current_state.json")
        let baseline = WatchRoundState(
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
        client.receiveState(baseline)

        // The golfer taps score=6 on the watch (queued, awaiting the phone's ack).
        try client.queueInputEvent(
            WatchInputEvent(
                eventId: "watch-score",
                roundId: "round-1",
                hole: 7,
                kind: .score,
                value: "6",
                createdAt: "2026-05-25T00:00:00Z"
            )
        )
        XCTAssertEqual(client.currentState?.score, 6)

        // The phone re-pushes its snapshot, which still shows the old score (it hasn't acked yet).
        client.receiveState(baseline)

        // The watch edit survives the dirty-merge instead of being reverted to 4.
        XCTAssertEqual(client.currentState?.score, 6)
        XCTAssertEqual(try client.loadPersistedState()?.score, 6)
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

    private func tempQueueURL() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("queued_events.json")
    }

    func testApplyApplicationContextParsesBackendConfig() throws {
        let client = WatchSyncClient(queueURL: tempQueueURL())
        client.applyApplicationContext([
            "config": ["apiBaseURL": "https://caddie.example.com", "adminToken": "tok-123"],
        ])
        XCTAssertEqual(client.config?.baseURL.absoluteString, "https://caddie.example.com")
        XCTAssertEqual(client.config?.adminToken, "tok-123")
    }

    func testApplyApplicationContextAcceptsConfigWithoutToken() throws {
        let client = WatchSyncClient(queueURL: tempQueueURL())
        client.applyApplicationContext(["config": ["apiBaseURL": "https://caddie.example.com"]])
        XCTAssertEqual(client.config?.baseURL.absoluteString, "https://caddie.example.com")
        XCTAssertNil(client.config?.adminToken)
    }

    func testApplyApplicationContextIgnoresInvalidPayload() throws {
        let client = WatchSyncClient(queueURL: tempQueueURL())
        client.applyApplicationContext(["unrelated": 1])
        XCTAssertNil(client.config)
        client.applyApplicationContext(["config": ["apiBaseURL": ""]])  // URL(string: "") is nil
        XCTAssertNil(client.config)
    }

    private static func jsonObject<T: Encodable>(from value: T) throws -> Any {
        let data = try JSONEncoder().encode(value)
        return try JSONSerialization.jsonObject(with: data)
    }
}
