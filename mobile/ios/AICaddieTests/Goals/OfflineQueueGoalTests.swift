// size: medium
// goals: I-10, I-11
//
// I-10: every record lands locally first, queues while offline and uploads on reconnect with no
// duplicates and no loss. I-11: a round finished offline is sealed locally first and its finish
// completes automatically once the network is back.
// Entry points: LiveRoundAppModel (bootstrap, handleEvent, syncPendingEvents, finishActiveRound,
// syncOnForeground) over a temp-dir OfflineStore and a real SyncClient. Only the HTTP edge is
// faked (a scoped URLProtocol server that can be switched offline); retry sleeps are no-ops.

#if !SWIFT_PACKAGE
import CoreLocation
import Foundation
import XCTest
@testable import AICaddie

private let offlineQueueGoalBaseURL = "https://offline-queue-goal.example.test"
private let offlineQueueGoalTimestamp = "2026-07-29T05:00:00Z"

/// One events POST as the fake server saw it, including attempts made while it was offline.
private struct OfflineQueueGoalEventPost: Equatable {
    let key: String
    let ids: [String]
    let online: Bool
}

/// Requests the fake server answered successfully, in arrival order.
private enum OfflineQueueGoalEntry: Equatable {
    case events([String])
    case finish
}

/// Fake backend edge. Offline, every request fails with `notConnectedToInternet`. Online, the
/// events endpoint stores each event id once and acknowledges ids it already has as duplicates;
/// the finish endpoint records the finish. Faults (503 once, partial ACK once) are opt-in.
private final class OfflineQueueGoalServer: @unchecked Sendable {
    private let lock = NSLock()
    private let roundId: String
    private var online = false
    private var posts: [OfflineQueueGoalEventPost] = []
    private var entries: [OfflineQueueGoalEntry] = []
    private var stored: [String] = []
    private var onlineDeliveries: [String: Int] = [:]
    private var omitFromNextAck: String?
    private var failNextEventPost = false
    private var failNextFinish = false
    private var finishAttemptCount = 0
    private var finishSuccessCount = 0

    init(roundId: String) {
        self.roundId = roundId
    }

    private func locked<T>(_ body: () throws -> T) rethrows -> T {
        lock.lock()
        defer { lock.unlock() }
        return try body()
    }

    func setOnline(_ value: Bool) { locked { online = value } }
    func omitFromNextAcknowledgement(_ eventId: String) { locked { omitFromNextAck = eventId } }
    func failNextEventPostWith503() { locked { failNextEventPost = true } }
    func failNextFinishWith503() { locked { failNextFinish = true } }

    var eventPosts: [OfflineQueueGoalEventPost] { locked { posts } }
    var onlineEventPosts: [OfflineQueueGoalEventPost] { locked { posts.filter(\.online) } }
    var log: [OfflineQueueGoalEntry] { locked { entries } }
    var storedIds: [String] { locked { stored } }
    var deliveries: [String: Int] { locked { onlineDeliveries } }
    var finishAttempts: Int { locked { finishAttemptCount } }
    var finishSuccesses: Int { locked { finishSuccessCount } }

    func handle(_ request: URLRequest) throws -> (HTTPURLResponse, Data) {
        let url = try XCTUnwrap(request.url)
        if url.path == "/api/v2/mobile/rounds/\(roundId)/events", request.httpMethod == "POST" {
            let body = try CapturingURLProtocol.requestBodyData(from: request)
            let batch = try JSONDecoder().decode(EventBatch.self, from: body)
            let ids = batch.events.map(\.eventId)
            let key = request.value(forHTTPHeaderField: "Idempotency-Key") ?? ""
            enum Outcome { case offline, unavailable, ack(accepted: [String], duplicates: [String]) }
            let outcome: Outcome = locked {
                posts.append(OfflineQueueGoalEventPost(key: key, ids: ids, online: online))
                guard online else { return .offline }
                if failNextEventPost {
                    failNextEventPost = false
                    return .unavailable
                }
                var accepted: [String] = []
                var duplicates: [String] = []
                for id in ids {
                    onlineDeliveries[id, default: 0] += 1
                    if stored.contains(id) {
                        duplicates.append(id)
                    } else {
                        stored.append(id)
                        accepted.append(id)
                    }
                }
                if let omitted = omitFromNextAck {
                    omitFromNextAck = nil
                    accepted.removeAll { $0 == omitted }
                    duplicates.removeAll { $0 == omitted }
                }
                entries.append(.events(ids))
                return .ack(accepted: accepted, duplicates: duplicates)
            }
            switch outcome {
            case .offline:
                throw URLError(.notConnectedToInternet)
            case .unavailable:
                return try Self.reply(url, status: 503, body: Data(#"{"detail":"unavailable"}"#.utf8))
            case .ack(let accepted, let duplicates):
                let body = try JSONSerialization.data(withJSONObject: [
                    "accepted": accepted.count,
                    "duplicate": accepted.isEmpty && !duplicates.isEmpty,
                    "acceptedEventIds": accepted,
                    "duplicateEventIds": duplicates,
                    "serverSequence": storedIds.count,
                ] as [String: Any])
                return try Self.reply(url, status: 200, body: body)
            }
        }
        if url.path == "/api/v2/mobile/rounds/\(roundId)/finish" {
            enum Outcome { case offline, unavailable, finished }
            let outcome: Outcome = locked {
                guard online else { return .offline }
                finishAttemptCount += 1
                if failNextFinish {
                    failNextFinish = false
                    return .unavailable
                }
                finishSuccessCount += 1
                entries.append(.finish)
                return .finished
            }
            switch outcome {
            case .offline:
                throw URLError(.notConnectedToInternet)
            case .unavailable:
                return try Self.reply(url, status: 503, body: Data(#"{"detail":"unavailable"}"#.utf8))
            case .finished:
                return try Self.reply(url, status: 200, body: Data("{}".utf8))
            }
        }
        // Course options, home/remote packages, replay pulls: never needed by these promises.
        throw URLError(.notConnectedToInternet)
    }

    private static func reply(_ url: URL, status: Int, body: Data) throws -> (HTTPURLResponse, Data) {
        let response = try XCTUnwrap(HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil))
        return (response, body)
    }
}

/// A real model over a real SyncClient whose only network is the scoped fake server.
@MainActor
private final class OfflineQueueGoalApp {
    let scope: CapturingURLProtocolScope
    let session: URLSession
    let client: SyncClient
    let model: LiveRoundAppModel

    init(store: OfflineStore, server: OfflineQueueGoalServer, roundId: String) throws {
        let baseURL = try XCTUnwrap(URL(string: offlineQueueGoalBaseURL))
        let scope = CapturingURLProtocolScope(handler: { try server.handle($0) })
        let session = URLSession(configuration: scope.configuration())
        let client = SyncClient(baseURL: baseURL, session: session, retrySleep: { _ in })
        self.scope = scope
        self.session = session
        self.client = client
        self.model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: baseURL,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: roundId,
            syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [],
            networkPathObserver: nil
        )
    }

    func shutDown() async {
        await model.stopRoundBackgroundWorkForTesting()
        client.invalidateForTesting()
        session.invalidateAndCancel()
        withExtendedLifetime(scope) {}
    }
}

final class OfflineQueueGoalTests: XCTestCase {
    private var bagIsolation: GoalClubBagIsolation?

    override func setUp() async throws {
        try await super.setUp()
        bagIsolation = try await GoalClubBagIsolation()
    }

    override func tearDown() async throws {
        await bagIsolation?.restore()
        bagIsolation = nil
        try await super.tearDown()
    }

    private func makeStore() throws -> (OfflineStore, LiveRoundPackage, URL) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("offline-queue-goal-\(UUID().uuidString)", isDirectory: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        try store.saveRoundPackage(package)
        return (store, package, directory)
    }

    private func score(_ id: String, hole: Int, roundId: String) -> LiveRoundEvent {
        LiveRoundEvent(
            eventId: id, roundId: roundId, timestamp: offlineQueueGoalTimestamp,
            hole: hole, kind: .score, payload: ["strokes": .number(5), "fairway": .string("hit")]
        )
    }

    private func pendingIds(_ store: OfflineStore, _ roundId: String) throws -> [String] {
        try store.loadPendingEvents(roundId: roundId).map(\.eventId)
    }

    private func loggedIds(_ store: OfflineStore, _ roundId: String) throws -> [String] {
        try store.loadEvents()
            .filter { $0.roundId == roundId && $0.kind != .syncMarker }
            .map(\.eventId)
    }

    // MARK: - I-10

    // goals: I-10 [main]
    @MainActor
    func testQueueReplayNoDupNoLoss() async throws {
        let (store, package, _) = try makeStore()
        let roundId = package.roundId
        try store.appendEvent(score("queue-e1", hole: 1, roundId: roundId))
        let server = OfflineQueueGoalServer(roundId: roundId)
        let app = try OfflineQueueGoalApp(store: store, server: server, roundId: roundId)
        let model = app.model
        await model.bootstrap()

        // Offline: each record lands in the local log first and stays queued.
        model.handleEvent(score("queue-e2", hole: 2, roundId: roundId))
        model.handleEvent(score("queue-e3", hole: 3, roundId: roundId))
        XCTAssertEqual(try loggedIds(store, roundId), ["queue-e1", "queue-e2", "queue-e3"])
        await model.syncPendingEvents()
        XCTAssertEqual(server.storedIds, [], "nothing reaches the server while offline")
        XCTAssertEqual(try pendingIds(store, roundId), ["queue-e1", "queue-e2", "queue-e3"])
        XCTAssertEqual(model.pendingEventCount, 3)

        // Reconnect: the whole queue is replayed once.
        server.setOnline(true)
        await model.syncPendingEvents()
        XCTAssertEqual(Set(server.storedIds), ["queue-e1", "queue-e2", "queue-e3"], "no record is lost")
        XCTAssertEqual(server.storedIds.count, 3)
        XCTAssertEqual(server.deliveries, ["queue-e1": 1, "queue-e2": 1, "queue-e3": 1], "no record is sent twice")
        XCTAssertEqual(try pendingIds(store, roundId), [])
        XCTAssertEqual(model.pendingEventCount, 0)
        XCTAssertEqual(Set(server.eventPosts.map(\.key)).count, 1, "offline attempts and the replay share one idempotency key")
        XCTAssertEqual(try loggedIds(store, roundId), ["queue-e1", "queue-e2", "queue-e3"], "the local log keeps every record")

        // A later sync has nothing left to send.
        let postsBefore = server.eventPosts.count
        await model.syncPendingEvents()
        XCTAssertEqual(server.eventPosts.count, postsBefore, "an acknowledged queue is not uploaded again")
        XCTAssertEqual(server.deliveries, ["queue-e1": 1, "queue-e2": 1, "queue-e3": 1])
        await app.shutDown()
    }

    // goals: I-09
    /// A location and a score-only record use the production event builder and model entry point;
    /// both payloads survive a store close/reopen, including the score that has no GPS fields.
    @MainActor
    func testLiveEventsPersistAcrossRelaunchWithScoreOnlyPayload() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("offline-event-goal-\(UUID().uuidString)", isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        // Use the same scoped fake edge as the queue goals. The model's default client would
        // start package downloads and upload tasks against the host network while this test is
        // only proving the local persistence boundary.
        let server = OfflineQueueGoalServer(roundId: package.roundId)
        let app = try OfflineQueueGoalApp(store: store, server: server, roundId: package.roundId)
        addTeardownBlock {
            await app.shutDown()
            try? FileManager.default.removeItem(at: directory)
        }
        let model = app.model
        model.enterPrepMode(with: package, hole: package.holes[0].number)
        XCTAssertTrue(model.startRoundFromFirstStroke(startHole: package.holes[0].number))

        var ids = ["goal-location", "goal-score"]
        let builder = LiveRoundEventBuilder(
            roundId: package.roundId,
            idFactory: { ids.removeFirst() },
            now: { Date(timeIntervalSince1970: 1_900_000_000) }
        )
        let location = builder.makeLocationEvent(
            hole: package.holes[0].number,
            coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
            horizontalAccuracyM: 4
        )
        let score = builder.makeScoreEvent(hole: package.holes[0].number, strokes: 5)
        model.handleEvent(location)
        model.handleEvent(score)

        let before = try store.loadEvents().filter { $0.roundId == package.roundId }
        XCTAssertEqual(before.map(\.eventId), ["goal-location", "goal-score"])
        XCTAssertEqual(before.first?.payload["source"], .string("ios_gps"))
        XCTAssertEqual(before.first?.payload["latitude"], .number(40.0455))
        XCTAssertEqual(before.first?.payload["longitude"], .number(116.5462))
        XCTAssertEqual(before.first?.payload["horizontalAccuracyM"], .number(4))
        XCTAssertEqual(before.last?.payload["strokes"], .number(5))
        XCTAssertNil(before.last?.payload["latitude"], "score-only records stay free of synthetic GPS")

        let reopened = OfflineStore(directoryURL: directory)
        let after = try reopened.loadEvents().filter { $0.roundId == package.roundId }
        XCTAssertEqual(after.map(\.eventId), before.map(\.eventId))
        XCTAssertEqual(after.first?.payload["latitude"], .number(40.0455))
        XCTAssertEqual(after.first?.payload["longitude"], .number(116.5462))
        XCTAssertEqual(after.first?.payload["horizontalAccuracyM"], .number(4))
        XCTAssertEqual(after.first?.payload["source"], .string("ios_gps"))
        XCTAssertNil(after.last?.payload["latitude"])
        XCTAssertNil(after.last?.payload["longitude"])
        XCTAssertEqual(after.last?.payload["strokes"], .number(5))
    }

    // goals: I-10
    @MainActor
    func testPartialAcknowledgementKeepsQueueAndReplaysSameBatch() async throws {
        let (store, package, _) = try makeStore()
        let roundId = package.roundId
        let ids = ["partial-e1", "partial-e2", "partial-e3"]
        for (index, id) in ids.enumerated() {
            try store.appendEvent(score(id, hole: index + 1, roundId: roundId))
        }
        let server = OfflineQueueGoalServer(roundId: roundId)
        server.setOnline(true)
        server.omitFromNextAcknowledgement("partial-e3")
        let app = try OfflineQueueGoalApp(store: store, server: server, roundId: roundId)
        let model = app.model
        await model.bootstrap()

        await model.syncPendingEvents()
        XCTAssertEqual(try pendingIds(store, roundId), ids, "an incomplete ACK must not mark any record uploaded")
        let first = try XCTUnwrap(server.onlineEventPosts.first)
        XCTAssertEqual(first.ids, ids)

        await model.syncPendingEvents()
        let posts = server.onlineEventPosts
        XCTAssertEqual(posts.count, 2)
        let retry = try XCTUnwrap(posts.last)
        XCTAssertEqual(retry, first, "the replay resends the same batch under the same idempotency key")
        XCTAssertEqual(server.storedIds, ids, "each record is stored exactly once")
        XCTAssertEqual(try pendingIds(store, roundId), [])
        XCTAssertEqual(model.pendingEventCount, 0)

        await model.syncPendingEvents()
        XCTAssertEqual(server.onlineEventPosts.count, 2, "nothing is resent once fully acknowledged")
        await app.shutDown()
    }

    // goals: I-10
    @MainActor
    func testServerErrorRetriesSameBatchWithoutDuplicates() async throws {
        let (store, package, _) = try makeStore()
        let roundId = package.roundId
        let ids = ["retry-e1", "retry-e2", "retry-e3"]
        for (index, id) in ids.enumerated() {
            try store.appendEvent(score(id, hole: index + 1, roundId: roundId))
        }
        let server = OfflineQueueGoalServer(roundId: roundId)
        server.setOnline(true)
        server.failNextEventPostWith503()
        let app = try OfflineQueueGoalApp(store: store, server: server, roundId: roundId)
        let model = app.model
        await model.bootstrap()

        await model.syncPendingEvents()
        let posts = server.onlineEventPosts
        XCTAssertEqual(posts.count, 2, "a 503 is retried")
        XCTAssertEqual(posts.first, posts.last, "the retry carries the same key and the same records")
        XCTAssertEqual(server.storedIds, ids)
        XCTAssertEqual(server.deliveries, ["retry-e1": 1, "retry-e2": 1, "retry-e3": 1])
        XCTAssertEqual(try pendingIds(store, roundId), [])
        XCTAssertEqual(model.pendingEventCount, 0)
        await app.shutDown()
    }

    // goals: I-10
    @MainActor
    func testRecordAfterUploadIsQueuedAndSentAlone() async throws {
        let (store, package, _) = try makeStore()
        let roundId = package.roundId
        try store.appendEvent(score("tail-e1", hole: 1, roundId: roundId))
        let server = OfflineQueueGoalServer(roundId: roundId)
        server.setOnline(true)
        let app = try OfflineQueueGoalApp(store: store, server: server, roundId: roundId)
        let model = app.model
        await model.bootstrap()

        await model.syncPendingEvents()
        XCTAssertEqual(server.storedIds, ["tail-e1"])
        XCTAssertEqual(try pendingIds(store, roundId), [])

        model.handleEvent(score("tail-e2", hole: 2, roundId: roundId))
        XCTAssertEqual(model.pendingEventCount, 1, "the new record is queued locally first")
        XCTAssertEqual(try pendingIds(store, roundId), ["tail-e2"])
        await model.syncPendingEvents()

        let last = try XCTUnwrap(server.onlineEventPosts.last)
        XCTAssertEqual(last.ids, ["tail-e2"], "only the new record is uploaded")
        XCTAssertEqual(server.storedIds, ["tail-e1", "tail-e2"])
        XCTAssertEqual(server.deliveries, ["tail-e1": 1, "tail-e2": 1])
        XCTAssertEqual(try pendingIds(store, roundId), [])
        XCTAssertEqual(model.pendingEventCount, 0)
        await app.shutDown()
    }

    // MARK: - I-11

    /// Opens a resumable round with three recorded holes and seals it while offline.
    @MainActor
    private func sealOffline(
        prefix: String
    ) async throws -> (OfflineStore, String, URL, OfflineQueueGoalServer, OfflineQueueGoalApp, [String]) {
        let (store, package, directory) = try makeStore()
        let roundId = package.roundId
        let ids = (1...3).map { "\(prefix)-e\($0)" }
        for (index, id) in ids.enumerated() {
            try store.appendEvent(score(id, hole: index + 1, roundId: roundId))
        }
        let server = OfflineQueueGoalServer(roundId: roundId)
        let app = try OfflineQueueGoalApp(store: store, server: server, roundId: roundId)
        await app.model.bootstrap()
        let sealed = await app.model.finishActiveRound()
        XCTAssertTrue(sealed, "finishing offline seals the round locally")
        await app.model.waitForDeferredRoundFinishesForTesting()
        XCTAssertTrue(try store.isRoundPendingFinish(roundId))
        XCTAssertEqual(try pendingIds(store, roundId), ids, "the sealed round keeps every record queued")
        XCTAssertEqual(server.finishSuccesses, 0)
        return (store, roundId, directory, server, app, ids)
    }

    // goals: I-11 [main]
    @MainActor
    func testRoundFinishedOfflineIsSealedThenFinishesOnReconnect() async throws {
        let (store, roundId, _, server, app, ids) = try await sealOffline(prefix: "seal")
        let model = app.model

        server.setOnline(true)
        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()

        XCTAssertEqual(server.finishSuccesses, 1, "the finish completes on reconnect without a user action")
        XCTAssertFalse(try store.isRoundPendingFinish(roundId))
        XCTAssertEqual(server.storedIds, ids, "every record of the sealed round is uploaded")
        XCTAssertEqual(server.deliveries, ["seal-e1": 1, "seal-e2": 1, "seal-e3": 1])
        XCTAssertEqual(server.log, [.events(ids), .finish], "records are uploaded before the round is finished")
        let markers = try store.loadEvents().filter { $0.roundId == roundId && $0.kind == .syncMarker }
        XCTAssertEqual(markers.count, 1, "a completed upload records its acknowledgement locally")
        await app.shutDown()
    }

    // goals: I-11
    @MainActor
    func testSealedRoundSurvivesRelaunchAndFinishesOnce() async throws {
        let (_, roundId, directory, server, app, ids) = try await sealOffline(prefix: "relaunch")
        await app.shutDown()

        // The seal is durable: a fresh store over the same directory still owns the finish.
        let reopened = OfflineStore(directoryURL: directory)
        XCTAssertTrue(try reopened.isRoundPendingFinish(roundId))
        XCTAssertEqual(try pendingIds(reopened, roundId), ids)

        server.setOnline(true)
        let relaunched = try OfflineQueueGoalApp(store: reopened, server: server, roundId: roundId)
        await relaunched.model.bootstrap()
        await relaunched.model.waitForDeferredRoundFinishesForTesting()

        XCTAssertEqual(server.finishSuccesses, 1, "the relaunched app finishes the sealed round exactly once")
        XCTAssertFalse(try reopened.isRoundPendingFinish(roundId))
        XCTAssertEqual(server.storedIds, ids)
        XCTAssertEqual(server.deliveries, ["relaunch-e1": 1, "relaunch-e2": 1, "relaunch-e3": 1])
        await relaunched.shutDown()
    }

    // goals: I-11
    @MainActor
    func testFailedFinishStaysSealedAndCompletesOnNextForeground() async throws {
        let (store, roundId, _, server, app, ids) = try await sealOffline(prefix: "retry")
        let model = app.model

        server.setOnline(true)
        server.failNextFinishWith503()
        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(server.finishAttempts, 1)
        XCTAssertEqual(server.finishSuccesses, 0)
        XCTAssertTrue(try store.isRoundPendingFinish(roundId), "a failed finish keeps the round sealed")
        XCTAssertEqual(server.storedIds, ids)

        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(server.finishAttempts, 2)
        XCTAssertEqual(server.finishSuccesses, 1)
        XCTAssertFalse(try store.isRoundPendingFinish(roundId))
        XCTAssertEqual(server.onlineEventPosts.count, 1, "acknowledged records are not uploaded again for the retry")
        XCTAssertEqual(server.deliveries, ["retry-e1": 1, "retry-e2": 1, "retry-e3": 1])
        await app.shutDown()
    }

    // goals: I-11
    @MainActor
    func testRepeatedForegroundsFinishTheSealedRoundExactlyOnce() async throws {
        let (store, roundId, _, server, app, ids) = try await sealOffline(prefix: "repeat")
        let model = app.model

        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()
        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(server.finishSuccesses, 0)
        XCTAssertTrue(try store.isRoundPendingFinish(roundId), "still offline: the round stays sealed")
        XCTAssertEqual(try pendingIds(store, roundId), ids)

        server.setOnline(true)
        model.syncOnForeground()
        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()
        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()

        XCTAssertEqual(server.finishSuccesses, 1, "repeated foregrounds finish the round exactly once")
        XCTAssertFalse(try store.isRoundPendingFinish(roundId))
        XCTAssertEqual(server.storedIds, ids)
        XCTAssertEqual(server.deliveries, ["repeat-e1": 1, "repeat-e2": 1, "repeat-e3": 1])
        await app.shutDown()
    }
}
#endif
