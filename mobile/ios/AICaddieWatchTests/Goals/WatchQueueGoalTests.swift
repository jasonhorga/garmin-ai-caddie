// size: medium
// goals: W-08, W-09
import Foundation
import XCTest
import AICaddieDomain
import AICaddieCore
@testable import AICaddieWatch

@MainActor
final class WatchQueueGoalTests: XCTestCase {
    private final class Session: NSObject, WatchSessioning {
        var isSessionActivated = true
        var isCounterpartReachable = true
        var receivedContext: [String: Any] = [:]
        var sentContext: [String: Any] = [:]
        var messages: [[String: Any]] = []
        var reply: [String: Any] = [:]
        var deferReplies = false
        var replyCallbacks: [(([String: Any]) -> Void)?] = []

        func activateSession() {}
        func send(_ message: [String: Any], onReply: (([String: Any]) -> Void)?, onError: ((Error) -> Void)?) {
            messages.append(message)
            replyCallbacks.append(onReply)
            if !deferReplies { onReply?(reply) }
        }
        func queueUserInfo(_ userInfo: [String: Any]) {}
        func replaceContext(_ context: [String: Any]) throws { sentContext = context }
    }
    private func client(_ directory: URL, session: WatchSessioning? = nil) -> WatchSyncClient {
        WatchSyncClient(
            queueURL: directory.appendingPathComponent("events.json"),
            holeImageStore: WatchHoleImageStore(directoryURL: directory.appendingPathComponent("images")),
            courseStore: WatchCourseStore(directoryURL: directory.appendingPathComponent("courses")),
            session: session
        )
    }

    private func hole() -> WatchRoundState {
        WatchRoundState(roundId: "r1", hole: 1, par: 4, distanceM: nil, selectedClub: nil,
                        score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline")
    }

    private func queueEvent(_ id: String, kind: WatchInputKind = .score) -> WatchInputEvent {
        WatchInputEvent(
            eventId: id, roundId: "r1", hole: 1, kind: kind,
            value: kind == .score ? "4" : "40.0,116.0,5.0",
            createdAt: "2026-06-20T00:00:00Z"
        )
    }

    // goals: W-08
    /// Queue contents survive a new client instance and acknowledgement removes only the IDs
    /// confirmed by the receiver.
    func testQueuedEventsSurviveRelaunchAndAckOnlyConfirmedIds() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let first = client(directory)
        try first.queueInputEvent(queueEvent("event-1"))
        try first.queueInputEvent(queueEvent("event-2", kind: .location))

        let relaunched = client(directory)
        XCTAssertEqual(try relaunched.loadQueuedEvents().map(\.eventId), ["event-1", "event-2"])
        try relaunched.markEventsAcknowledged(["event-2"])
        XCTAssertEqual(try relaunched.loadQueuedEvents().map(\.eventId), ["event-1"])
    }

    // goals: W-08
    /// An acknowledgement for an unknown ID cannot erase a pending event; a later acknowledgement
    /// clears the same queue entry exactly once.
    func testUnknownAcknowledgementKeepsPendingEventUntilItIsConfirmed() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let client = client(directory)
        try client.queueInputEvent(queueEvent("event-1"))
        try client.markEventsAcknowledged(["missing-event"])
        XCTAssertEqual(try client.loadQueuedEvents().map(\.eventId), ["event-1"])
        try client.markEventsAcknowledged(["event-1"])
        XCTAssertTrue(try client.loadQueuedEvents().isEmpty)
    }

    // goals: W-08 [main]
    /// The real flush path sends each durable event and removes it only from the acknowledgement callback.
    func testFlushQueueSendsAndDeletesOnlyAcknowledgedEvents() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let session = Session()
        session.reply = ["acceptedEventIds": ["event-1"]]
        let client = client(directory, session: session)
        try client.queueInputEvent(queueEvent("event-1"))
        try client.queueInputEvent(queueEvent("event-2", kind: .location))

        try client.flushQueue()

        XCTAssertEqual(session.messages.compactMap { ($0["event"] as? [String: Any])?["eventId"] as? String }, ["event-1", "event-2"])
        XCTAssertEqual(try client.loadQueuedEvents().map(\.eventId), ["event-2"])
    }

    // goals: W-08
    /// Killing the sender with outstanding replies keeps the same IDs for replay; duplicate and
    /// partial acknowledgements resolve only those IDs, even if an old reply arrives later.
    func testLostReplyReplaysSameIdsAfterRelaunchWithoutDroppingNewEvents() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let outstanding = Session()
        outstanding.deferReplies = true
        var first: WatchSyncClient? = client(directory, session: outstanding)
        try first?.queueInputEvent(queueEvent("event-1"))
        try first?.queueInputEvent(queueEvent("event-2"))
        try first?.flushQueue()
        XCTAssertEqual(outstanding.messages.count, 2)
        XCTAssertEqual(try first?.loadQueuedEvents().count, 2)
        first = nil

        let replay = Session()
        replay.deferReplies = true
        let restored = client(directory, session: replay)
        try restored.flushQueue()
        XCTAssertEqual(replay.messages.compactMap { ($0["event"] as? [String: Any])?["eventId"] as? String }, ["event-1", "event-2"])
        replay.replyCallbacks[0]?(["duplicateEventIds": ["event-1"]])
        replay.replyCallbacks[1]?(["accepted": false])
        XCTAssertEqual(try restored.loadQueuedEvents().map(\.eventId), ["event-2"])
        try restored.queueInputEvent(queueEvent("event-3"))
        outstanding.replyCallbacks[0]?(["acceptedEventIds": ["event-1"]])
        XCTAssertEqual(try restored.loadQueuedEvents().map(\.eventId), ["event-2", "event-3"])
        replay.replyCallbacks[1]?(["acceptedEventIds": ["event-2"]])
        replay.replyCallbacks[1]?(["duplicateEventIds": ["event-2"]])
        XCTAssertEqual(try restored.loadQueuedEvents().map(\.eventId), ["event-3"])
    }

    // goals: W-08, W-09
    /// The direct-backend wire path retains all IDs after 503, only removes accepted IDs after a
    /// partial ack, and finishes only when replay receives a duplicate ack for the remaining facts.
    func testDirectBackendFailurePartialAckAndDuplicateReplay() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchRoundStore(directoryURL: directory)
        var batches: [[String]] = []
        var finishCalls = 0
        let backend = WatchBackendClient(baseURL: URL(string: "https://caddie.example")!, dataLoader: { request in
            let body = try XCTUnwrap(request.httpBody)
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            let events = try XCTUnwrap(object["events"] as? [[String: Any]])
            let ids = events.compactMap { $0["eventId"] as? String }
            batches.append(ids)
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/r1/events")
            let payload: [String: Any]
            let status: Int
            switch batches.count {
            case 1: status = 503; payload = [:]
            case 2: status = 200; payload = ["acceptedEventIds": [try XCTUnwrap(ids.first)]]
            default: status = 200; payload = ["duplicateEventIds": ids]
            }
            return (try JSONSerialization.data(withJSONObject: payload),
                    HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
        }, retrySleep: { _ in })
        func makeModel() -> WatchRoundModel {
            WatchRoundModel(store: store, uploader: { events, roundId in
                let result = try await backend.postEvents(events, roundId: roundId, idempotencyKey: "fixture-batch")
                return result.acknowledgedEventIds
            }, finisher: { _, _ in finishCalls += 1 })
        }
        let model = makeModel()
        model.seedRound([hole()])
        model.startScoringActiveHole()
        model.setDraftScore(5)
        model.setDraftPutts(2)
        model.saveActiveHole()
        let originalIds = store.pendingEvents().map(\.eventId)
        XCTAssertGreaterThan(originalIds.count, 1)
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()
        XCTAssertEqual(store.loadDeferredFinishes().first?.round.pendingEvents.map(\.eventId), originalIds)
        XCTAssertEqual(finishCalls, 0)
        let relaunched = makeModel()
        await relaunched.retryDeferredFinishes()
        let remaining = try XCTUnwrap(store.loadDeferredFinishes().first).round.pendingEvents.map(\.eventId)
        XCTAssertEqual(remaining, Array(originalIds.dropFirst()))
        XCTAssertEqual(finishCalls, 0)
        await relaunched.retryDeferredFinishes()
        XCTAssertEqual(batches, [originalIds, originalIds, remaining])
        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
        XCTAssertEqual(finishCalls, 1)
    }

    // goals: W-09 [main]
    /// A failed finish is deferred durably, then retried after connectivity returns; abandon closes
    /// the local round without creating a deferred upload.
    func testFinishDefersAndRetriesAfterNetworkRecovery() async throws {
        struct Offline: Error {}
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchRoundStore(directoryURL: directory)
        var online = false
        var finishCalls = 0
        let model = WatchRoundModel(
            store: store,
            uploader: { events, _ in
                guard online else { throw Offline() }
                return events.map(\.eventId)
            },
            finisher: { _, _ in
                guard online else { throw Offline() }
                finishCalls += 1
            }
        )
        model.seedRound([hole()])
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()
        XCTAssertNil(model.round)
        XCTAssertEqual(store.loadDeferredFinishes().count, 1)

        online = true
        await model.retryDeferredFinishes()
        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
        XCTAssertEqual(finishCalls, 1)

        let second = WatchRoundModel(store: WatchRoundStore(directoryURL: directory.appendingPathComponent("abandon")))
        second.seedRound([hole()])
        second.requestAbandon()
        second.confirmAbandon()
        XCTAssertNil(second.round)
        XCTAssertEqual(second.lastRoundClosure?.disposition, .abandoned)
    }

    // goals: W-09
    /// A reachable finish uploads its queued facts before closing and leaves no retry archive.
    func testReachableFinishClosesOnlyAfterAcknowledgedUpload() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchRoundStore(directoryURL: directory)
        var uploaded: [String] = []
        var finished = false
        let model = WatchRoundModel(
            store: store,
            uploader: { events, _ in
                uploaded = events.map(\.eventId)
                return uploaded
            },
            finisher: { _, _ in finished = true }
        )
        model.seedRound([hole()])
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()

        XCTAssertFalse(uploaded.isEmpty)
        XCTAssertTrue(finished)
        XCTAssertNil(model.round)
        XCTAssertEqual(model.lastRoundClosure?.disposition, .finished)
        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
    }

    // goals: W-09
    /// A retry that still cannot reach the backend retains the exact archive and never revives the
    /// finished screen or asks the backend to finish it.
    func testFailedRetryRetainsDeferredRoundWithoutRevivingUi() async throws {
        struct Offline: Error {}
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchRoundStore(directoryURL: directory)
        var finishCalls = 0
        let model = WatchRoundModel(
            store: store,
            uploader: { _, _ in throw Offline() },
            finisher: { _, _ in finishCalls += 1 }
        )
        model.seedRound([hole()])
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()
        let archived = try XCTUnwrap(store.loadDeferredFinishes().first)

        await model.retryDeferredFinishes()

        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(store.loadDeferredFinishes().first?.round.roundId, archived.round.roundId)
        XCTAssertEqual(finishCalls, 0)
    }

    // goals: W-09
    /// Abandon is a terminal local decision: it removes a deferred finish archive and records the
    /// tombstone so an old round cannot return on a later seed.
    func testAbandonDiscardsDeferredFinishAndTombstonesRound() async throws {
        struct Offline: Error {}
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchRoundStore(directoryURL: directory)
        let model = WatchRoundModel(store: store, uploader: { _, _ in throw Offline() })
        model.seedRound([hole()])
        model.startScoringActiveHole()
        model.saveActiveHole()
        model.requestFinish()
        model.requestFinishConfirmation()
        await model.confirmFinish()
        XCTAssertEqual(store.loadDeferredFinishes().count, 1)

        model.applyPhoneRoundClosure(WatchRoundClosure(
            roundId: "r1", disposition: .abandoned, closedAt: "2026-06-20T00:01:00Z"
        ))

        XCTAssertTrue(store.loadDeferredFinishes().isEmpty)
        XCTAssertTrue(store.isClosed(roundId: "r1"))
        XCTAssertNil(model.round)
    }
}
