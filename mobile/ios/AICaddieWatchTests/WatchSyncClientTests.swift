import XCTest
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif
@testable import AICaddieWatch

final class WatchSyncClientTests: XCTestCase {
    func testHoleImageTransferRejectsMissingOrStaleRendererVersion() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let imageStore = WatchHoleImageStore(directoryURL: directory)
        let client = WatchSyncClient(
            queueURL: directory.appendingPathComponent("queued_events.json"),
            holeImageStore: imageStore
        )
        let imageURL = directory.appendingPathComponent("received.img")
        let image = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        try image.write(to: imageURL, options: .atomic)

        XCTAssertFalse(client.receiveHoleImage(
            fileURL: imageURL,
            metadata: ["globalId": 31833, "hole": 1]
        ))
        XCTAssertFalse(client.receiveHoleImage(
            fileURL: imageURL,
            metadata: ["globalId": 31833, "hole": 1, "styleVersion": "topo-v7"]
        ))
        XCTAssertFalse(imageStore.hasImage(globalId: 31833, hole: 1))
    }

    func testHoleImageTransferAcceptsCurrentRendererVersion() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let imageStore = WatchHoleImageStore(directoryURL: directory)
        let client = WatchSyncClient(
            queueURL: directory.appendingPathComponent("queued_events.json"),
            holeImageStore: imageStore
        )
        let imageURL = directory.appendingPathComponent("received.img")
        let image = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        try image.write(to: imageURL, options: .atomic)

        XCTAssertTrue(client.receiveHoleImage(
            fileURL: imageURL,
            metadata: [
                "globalId": 31833,
                "hole": 1,
                "styleVersion": WatchBackendClient.topoStyleVersion,
                "geometryRevision": "aaaaaaaaaaaaaaaa",
            ]
        ))
        XCTAssertNil(imageStore.data(globalId: 31833, hole: 1))
        XCTAssertEqual(imageStore.data(
            globalId: 31833,
            hole: 1,
            geometryRevision: "aaaaaaaaaaaaaaaa"
        ), image)
    }

    func testGreenDetailTransferRequiresCurrentFocusedAssetVersion() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let imageStore = WatchHoleImageStore(directoryURL: directory)
        let client = WatchSyncClient(
            queueURL: directory.appendingPathComponent("queued_events.json"),
            holeImageStore: imageStore
        )
        let imageURL = directory.appendingPathComponent("received-green.img")
        let image = try XCTUnwrap(WatchHoleMapSample.greenDetailImage?.pngData())
        try image.write(to: imageURL, options: .atomic)

        let base: [String: Any] = [
            "globalId": 31833,
            "hole": 1,
            "styleVersion": WatchBackendClient.topoStyleVersion,
            "assetKind": "green-detail",
        ]
        XCTAssertFalse(client.receiveHoleImage(fileURL: imageURL, metadata: base))
        XCTAssertFalse(client.receiveHoleImage(
            fileURL: imageURL,
            metadata: base.merging(["assetStyleVersion": "green-v1"]) { _, new in new }
        ))
        XCTAssertTrue(client.receiveHoleImage(
            fileURL: imageURL,
            metadata: base.merging([
                "assetStyleVersion": WatchBackendClient.greenDetailStyleVersion,
            ]) { _, new in new }
        ))
        XCTAssertEqual(
            imageStore.data(globalId: 31833, hole: 1, detail: true),
            image
        )
    }

    func testReceiveRoundSeedPublishesRealRoundForTheAppModel() throws {
        let client = WatchSyncClient(queueURL: tempQueueURL())
        let seed = WatchRoundSeed(
            roundId: "round-real-1",
            courseName: "北京丽宫",
            activeHole: 2,
            holes: [
                WatchRoundSeedHole(hole: 1, par: 4, distanceM: 365),
                WatchRoundSeedHole(hole: 2, par: 3, distanceM: 148),
            ]
        )

        client.receiveRoundSeed(seed)

        XCTAssertEqual(client.roundSeed, seed)
    }

    func testRoundStartCreatesItsParentDirectoryBeforePersistingOfflineRelay() throws {
        let parent = FileManager.default.temporaryDirectory
            .appendingPathComponent("watch-sync-start-\(UUID().uuidString)", isDirectory: true)
        let queueURL = parent.appendingPathComponent("queued_events.json")
        let client = WatchSyncClient(queueURL: queueURL)
        let start = WatchRoundStart(
            roundId: "watch-start-1",
            courseName: "远方球场",
            teeBox: "Blue",
            activeHole: 1,
            holes: [WatchRoundSeedHole(hole: 1, par: 4, distanceM: nil)]
        )

        // The parent is intentionally absent. This is the first-launch/offline path where a
        // best-effort `try? data.write` used to lose the only durable round-start fact.
        XCTAssertFalse(FileManager.default.fileExists(atPath: parent.path))
        client.sendRoundStart(start)

        let pendingURL = parent.appendingPathComponent("pending_round_start.json")
        let persisted = try JSONDecoder().decode(
            WatchRoundStart.self,
            from: Data(contentsOf: pendingURL)
        )
        XCTAssertEqual(persisted, start)
    }

    func testConfigOnlyApplicationContextRetractsAnOldRoundSeed() {
        let client = WatchSyncClient(queueURL: tempQueueURL())
        client.receiveRoundSeed(WatchRoundSeed(
            roundId: "old-round",
            courseName: "Old course",
            activeHole: 1,
            holes: [WatchRoundSeedHole(hole: 1, par: 4, distanceM: 350)]
        ))

        client.applyApplicationContext([
            "config": ["apiBaseURL": "https://caddie.example.com"],
        ])

        XCTAssertNil(client.roundSeed)
    }

    func testForgetRoundClearsOnlyMatchingStateAndQueuedEvents() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let queueURL = directory.appendingPathComponent("queued_events.json")
        let stateURL = directory.appendingPathComponent("current_state.json")
        let client = WatchSyncClient(queueURL: queueURL, stateURL: stateURL)
        client.receiveState(WatchRoundState(
            roundId: "old-round", hole: 1, par: 4, distanceM: 350,
            selectedClub: nil, score: 0, putts: 0, penaltyCount: 0,
            caddieConfidence: "offline"
        ))
        try client.queueInputEvent(WatchInputEvent(
            eventId: "old-event", roundId: "old-round", hole: 1,
            kind: .score, value: "4", createdAt: "2026-08-09T00:00:00Z"
        ))
        try client.queueInputEvent(WatchInputEvent(
            eventId: "new-event", roundId: "new-round", hole: 1,
            kind: .score, value: "4", createdAt: "2026-08-09T00:01:00Z"
        ))

        try client.forgetRound(roundId: "old-round", discardQueuedEvents: true)

        XCTAssertNil(client.currentState)
        XCTAssertNil(try client.loadPersistedState())
        XCTAssertEqual(try client.loadQueuedEvents().map(\.eventId), ["new-event"])
    }

    func testForgetRoundFromDelegateQueueSynchronizesPublishedIdentity() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let client = WatchSyncClient(
            queueURL: directory.appendingPathComponent("queued_events.json"),
            stateURL: directory.appendingPathComponent("current_state.json")
        )
        client.receiveState(WatchRoundState(
            roundId: "old-round", hole: 1, par: 4, distanceM: 350,
            selectedClub: nil, score: 0, putts: 0, penaltyCount: 0,
            caddieConfidence: "offline"
        ))

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            DispatchQueue.global().async {
                do {
                    try client.forgetRound(roundId: "old-round", discardQueuedEvents: false)
                    continuation.resume()
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }

        XCTAssertNil(client.currentState)
        XCTAssertNil(try client.loadPersistedState())
    }

    func testPhoneRoundClosureClearsMatchingLegacyStateAndPublishesDisposition() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let client = WatchSyncClient(
            queueURL: directory.appendingPathComponent("queued_events.json"),
            stateURL: directory.appendingPathComponent("current_state.json")
        )
        client.receiveState(WatchRoundState(
            roundId: "done-round", hole: 1, par: 4, distanceM: 350,
            selectedClub: nil, score: 4, putts: 2, penaltyCount: 0,
            caddieConfidence: "offline"
        ))
        let closure = WatchRoundClosure(
            roundId: "done-round",
            disposition: .finished,
            closedAt: "2026-08-09T00:00:00Z"
        )

        client.receiveRoundClosure(closure)

        XCTAssertNil(client.currentState)
        XCTAssertEqual(client.phoneRoundClosure, closure)
    }

    func testPhoneFinishPreservesLegacyQueueUntilExplicitAbandon() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let client = WatchSyncClient(
            queueURL: directory.appendingPathComponent("queued_events.json"),
            stateURL: directory.appendingPathComponent("current_state.json")
        )
        let wristEvent = WatchInputEvent(
            eventId: "wrist-event",
            roundId: "done-round",
            hole: 1,
            kind: .score,
            value: "4",
            createdAt: "2026-08-09T00:00:00Z"
        )
        let newerEvent = WatchInputEvent(
            eventId: "newer-event",
            roundId: "new-round",
            hole: 1,
            kind: .score,
            value: "5",
            createdAt: "2026-08-09T00:01:00Z"
        )
        try client.queueInputEvent(wristEvent)
        try client.queueInputEvent(newerEvent)

        client.receiveRoundClosure(WatchRoundClosure(
            roundId: "done-round",
            disposition: .finished,
            closedAt: "2026-08-09T00:02:00Z"
        ))

        XCTAssertEqual(try client.loadQueuedEvents(), [wristEvent, newerEvent])

        client.receiveRoundClosure(WatchRoundClosure(
            roundId: "done-round",
            disposition: .abandoned,
            closedAt: "2026-08-09T00:03:00Z"
        ))

        XCTAssertEqual(try client.loadQueuedEvents(), [newerEvent])
    }

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

    func testConcurrentLegacyQueueAppendsDoNotLoseEvents() throws {
        let queueURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("queued_events.json")
        let client = WatchSyncClient(queueURL: queueURL)
        let events = (0..<32).map { index in
            WatchInputEvent(
                eventId: "event-\(index)",
                roundId: "round-1",
                hole: 1,
                kind: .score,
                value: "4",
                createdAt: "2026-08-09T08:00:00Z"
            )
        }
        let errorLock = NSLock()
        var failures: [Error] = []

        DispatchQueue.concurrentPerform(iterations: events.count) { index in
            do {
                try client.queueInputEvent(events[index])
            } catch {
                errorLock.lock()
                failures.append(error)
                errorLock.unlock()
            }
        }

        XCTAssertTrue(failures.isEmpty)
        XCTAssertEqual(
            Set(try client.loadQueuedEvents().map(\.eventId)),
            Set(events.map(\.eventId))
        )
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
        // round-13 watch-auth: a signed-out phone pushes config WITHOUT a session token, so the watch
        // clears its Bearer (latest-wins application context).
        XCTAssertNil(client.config?.sessionToken)
        XCTAssertNil(client.config?.sessionTokenExpiresAt)
    }

    func testApplyApplicationContextParsesSessionTokenAndExpiry() throws {
        // round-13 watch-auth: the phone forwards its live Apple session token (Bearer) + expiry so the
        // watch's standalone WatchBackendClient authenticates as the signed-in member/owner.
        let client = WatchSyncClient(queueURL: tempQueueURL())
        let expiry = "2026-12-31T00:00:00Z"
        client.applyApplicationContext([
            "config": [
                "apiBaseURL": "https://caddie.example.com",
                "sessionToken": "session-jwt",
                "sessionTokenExpiresAt": expiry,
            ],
        ])
        XCTAssertEqual(client.config?.sessionToken, "session-jwt")
        XCTAssertEqual(client.config?.sessionTokenExpiresAt, ISO8601DateFormatter().date(from: expiry))
    }

    func testValidConfigPersistsAcrossWatchProcessRelaunch() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let queueURL = directory.appendingPathComponent("queued_events.json")
        let first = WatchSyncClient(queueURL: queueURL)
        first.applyApplicationContext([
            "configStatus": "available",
            "config": [
                "apiBaseURL": "https://caddie.example.com",
                "sessionToken": "persisted-watch-token",
            ],
        ])

        let relaunched = WatchSyncClient(queueURL: queueURL)

        XCTAssertEqual(relaunched.config?.baseURL.absoluteString, "https://caddie.example.com")
        XCTAssertEqual(relaunched.config?.sessionToken, "persisted-watch-token")
    }

    func testExplicitUnavailableConfigClearsPersistedCredential() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let queueURL = directory.appendingPathComponent("queued_events.json")
        let client = WatchSyncClient(queueURL: queueURL)
        client.applyApplicationContext([
            "config": [
                "apiBaseURL": "https://caddie.example.com",
                "sessionToken": "old-token",
            ],
        ])

        client.applyApplicationContext(["configStatus": "unavailable"])

        XCTAssertNil(client.config)
        XCTAssertNil(WatchSyncClient(queueURL: queueURL).config)
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
