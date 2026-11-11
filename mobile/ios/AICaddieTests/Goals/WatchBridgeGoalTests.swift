// size: medium
// goals: I-17, I-18
import WatchConnectivity
import XCTest
import AICaddieCore
@testable import AICaddie

/// I-17: the phone hands the Watch its config, session token and current-hole data, and a
/// disconnected Watch never keeps showing advice made before the latest shot.
/// I-18: Watch score / start / finish inputs reach the phone, are stored locally and uploaded.
final class WatchBridgeGoalTests: XCTestCase {
    private var directories: [URL] = []

    override func setUp() {
        super.setUp()
        ensureC156TopoBundleStub()
    }

    override func tearDown() {
        for directory in directories {
            try? FileManager.default.removeItem(at: directory)
        }
        directories = []
        super.tearDown()
    }

    // MARK: - I-17 phone -> Watch

    // goals: I-17 [main]
    func testDisconnectedWatchQueuesEveryHoleSnapshotAndTheLatestOneRetiresOlderAdvice() throws {
        let session = GoalWatchSession(activated: true, reachable: false)
        let bridge = WatchEventBridge(offlineStore: makeStore(), autoActivate: false, session: session)
        let package = try LiveRoundPackageFixture.package()
        let hole = try XCTUnwrap(package.holes.first)

        let teeAdvice = bridge.makeWatchRoundStatePayload(
            package: package, hole: hole, score: 0, putts: 0, penaltyCount: 0,
            selectedClub: nil, decision: nil,
            caddieOptions: [GoalWatchFixture.option(club: "D", origin: [])],
            phoneShotEventIds: []
        )
        try bridge.sendStateToWatch(teeAdvice)
        let afterShot = bridge.makeWatchRoundStatePayload(
            package: package, hole: hole, score: 1, putts: 0, penaltyCount: 0,
            selectedClub: "7I", decision: nil,
            caddieOptions: [GoalWatchFixture.option(club: "7I", origin: ["shot-1"])],
            phoneShotEventIds: ["shot-1"]
        )
        try bridge.sendStateToWatch(afterShot)

        // An unreachable Watch gets durable, ordered deliveries instead of dropped live messages.
        XCTAssertTrue(session.sentMessages.isEmpty)
        XCTAssertEqual(session.queuedUserInfo.count, 2)
        let delivered = try session.queuedUserInfo.map { try GoalWatchFixture.state(from: $0) }
        XCTAssertEqual(delivered.map(\.roundId), [package.roundId, package.roundId])
        XCTAssertEqual(delivered.map(\.hole), [hole.number, hole.number])
        XCTAssertEqual(delivered.map(\.par), [hole.par, hole.par])
        let first = try XCTUnwrap(delivered.first?.snapshotRevision)
        let latest = try XCTUnwrap(delivered.last?.snapshotRevision)
        XCTAssertGreaterThan(latest, first, "the Watch keeps the newest snapshot by revision")
        // The tee advice was made before shot-1; the latest snapshot names the phone's shots so the
        // Watch can recognise the older plan as stale and replace it.
        XCTAssertEqual(delivered.first?.phoneShotEventIds, [])
        XCTAssertEqual(delivered.last?.phoneShotEventIds, ["shot-1"])
        XCTAssertEqual(delivered.last?.caddieOptions.map(\.originShotEventIds), [["shot-1"]])
        XCTAssertNotEqual(
            delivered.first?.caddieOptions.first?.originShotEventIds,
            delivered.last?.phoneShotEventIds
        )
    }

    // goals: I-17
    func testReachableWatchGetsCurrentHoleStateAsALiveMessage() throws {
        let session = GoalWatchSession(activated: true, reachable: true)
        let bridge = WatchEventBridge(offlineStore: makeStore(), autoActivate: false, session: session)
        let package = try LiveRoundPackageFixture.package()
        let hole = try XCTUnwrap(package.holes.first { $0.number == 3 })

        try bridge.sendStateToWatch(bridge.makeWatchRoundStatePayload(
            package: package, hole: hole, score: 2, putts: 1, penaltyCount: 0,
            selectedClub: "PW", decision: nil
        ))

        XCTAssertTrue(session.queuedUserInfo.isEmpty)
        XCTAssertEqual(session.sentMessages.count, 1)
        let state = try GoalWatchFixture.state(from: try XCTUnwrap(session.sentMessages.first))
        XCTAssertEqual(state.roundId, package.roundId)
        XCTAssertEqual(state.hole, 3)
        XCTAssertEqual(state.par, hole.par)
        XCTAssertEqual(state.score, 2)
        XCTAssertEqual(state.putts, 1)
        XCTAssertEqual(state.selectedClub, "PW")
    }

    // goals: I-17
    func testConfigSessionAndRoundSeedWaitForActivationThenArriveInOneContext() throws {
        let session = GoalWatchSession(activated: false, reachable: false)
        let bridge = WatchEventBridge(offlineStore: makeStore(), autoActivate: false, session: session)
        let package = try LiveRoundPackageFixture.package()
        let expiry = Date(timeIntervalSince1970: 1_800_000_000)

        bridge.sendConfigToWatch(
            apiBaseURL: "https://watch-goal.example.test", adminToken: nil,
            sessionToken: "member-session", sessionTokenExpiresAt: expiry
        )
        bridge.sendRoundSeedToWatch(bridge.makeWatchRoundSeedPayload(package: package, activeHole: 4))
        XCTAssertTrue(session.publishedContexts.isEmpty, "nothing is published before activation")

        bridge.activateSession()
        bridge.session(WCSession.default, activationDidCompleteWith: .activated, error: nil)

        XCTAssertEqual(session.publishedContexts.count, 1)
        let context = try XCTUnwrap(session.publishedContexts.last)
        XCTAssertEqual(context["configStatus"] as? String, "available")
        let config = try XCTUnwrap(context["config"] as? [String: Any])
        XCTAssertEqual(config["apiBaseURL"] as? String, "https://watch-goal.example.test")
        XCTAssertEqual(config["sessionToken"] as? String, "member-session")
        XCTAssertEqual(
            config["sessionTokenExpiresAt"] as? String,
            ISO8601DateFormatter().string(from: expiry)
        )
        let seed = try XCTUnwrap(context["roundSeed"] as? [String: Any])
        XCTAssertEqual(seed["roundId"] as? String, package.roundId)
        XCTAssertEqual(seed["activeHole"] as? Int, 4)
        XCTAssertEqual(seed["loopKey"] as? String, package.loopKey)
        XCTAssertEqual((seed["holes"] as? [[String: Any]])?.count, package.holes.count)

        // A Watch that missed the push can ask for the same snapshot.
        var reply: [String: Any]?
        bridge.handleWatchInputMessage(["requestConfiguration": true]) { reply = $0 }
        XCTAssertEqual(NSDictionary(dictionary: try XCTUnwrap(reply)), NSDictionary(dictionary: context))
    }

    // goals: I-17
    func testSignOutRepublishesConfigWithoutTheSessionToken() throws {
        let session = GoalWatchSession(activated: true, reachable: true)
        let bridge = WatchEventBridge(offlineStore: makeStore(), autoActivate: false, session: session)

        bridge.sendConfigToWatch(
            apiBaseURL: "https://watch-goal.example.test", adminToken: nil,
            sessionToken: "member-session", sessionTokenExpiresAt: nil
        )
        bridge.sendConfigToWatch(
            apiBaseURL: "https://watch-goal.example.test", adminToken: nil,
            sessionToken: nil, sessionTokenExpiresAt: nil
        )

        XCTAssertEqual(session.publishedContexts.count, 2)
        let latest = try XCTUnwrap(session.publishedContexts.last)
        XCTAssertEqual(latest["configStatus"] as? String, "available")
        let config = try XCTUnwrap(latest["config"] as? [String: Any])
        XCTAssertEqual(config["apiBaseURL"] as? String, "https://watch-goal.example.test")
        XCTAssertNil(config["sessionToken"], "a signed-out phone must clear the Watch's Bearer")
        XCTAssertNil(config["sessionTokenExpiresAt"])
    }

    // goals: I-17
    func testFinishedRoundRetractsOnlyItsOwnSeedAndKeepsTheConfig() throws {
        let session = GoalWatchSession(activated: true, reachable: false)
        let bridge = WatchEventBridge(offlineStore: makeStore(), autoActivate: false, session: session)
        let package = try LiveRoundPackageFixture.package()
        bridge.sendConfigToWatch(apiBaseURL: "https://watch-goal.example.test", adminToken: nil)
        bridge.sendRoundSeedToWatch(bridge.makeWatchRoundSeedPayload(package: package, activeHole: 1))

        bridge.handleWatchRoundClosure(try GoalWatchFixture.object(WatchRoundClosurePayload(
            roundId: "another-round", disposition: .finished, closedAt: "2026-11-10T08:00:00Z"
        )))
        XCTAssertEqual(
            (session.publishedContexts.last?["roundSeed"] as? [String: Any])?["roundId"] as? String,
            package.roundId,
            "a closure for a different round keeps the live seed"
        )

        bridge.handleWatchRoundClosure(try GoalWatchFixture.object(WatchRoundClosurePayload(
            roundId: package.roundId, disposition: .finished, closedAt: "2026-11-10T08:00:00Z"
        )))
        let latest = try XCTUnwrap(session.publishedContexts.last)
        XCTAssertNil(latest["roundSeed"], "the finished round's seed is retracted")
        XCTAssertEqual(latest["configStatus"] as? String, "available")
        XCTAssertNotNil(latest["config"])
    }

    // MARK: - I-18 Watch -> phone

    // goals: I-18
    func testWatchScoreIsAcknowledgedAndStoredAsAPendingWatchEvent() throws {
        let store = makeStore()
        let bridge = WatchEventBridge(offlineStore: store, autoActivate: false, session: nil)
        let event = WatchInputEvent(
            eventId: "watch-score-7", roundId: "watch-round", hole: 7, kind: .score,
            value: "5", createdAt: "2026-11-10T08:07:00Z", fairwayResult: "left"
        )

        let reply = try GoalWatchFixture.deliver(event, to: bridge)

        XCTAssertEqual(reply["accepted"] as? Bool, true)
        XCTAssertEqual(reply["acceptedEventIds"] as? [String], [event.eventId])
        XCTAssertEqual(reply["duplicateEventIds"] as? [String], [])
        let pending = try store.loadPendingEvents(roundId: "watch-round")
        XCTAssertEqual(pending.count, 1)
        let stored = try XCTUnwrap(pending.first)
        XCTAssertEqual(stored.eventId, event.eventId)
        XCTAssertEqual(stored.hole, 7)
        XCTAssertEqual(stored.kind, .score)
        XCTAssertEqual(stored.clientId, "apple-watch")
        XCTAssertEqual(stored.timestamp, event.createdAt)
        XCTAssertEqual(stored.payload["strokes"], .number(5))
        XCTAssertEqual(stored.payload["fairway"], .string("left"))
        XCTAssertEqual(stored.payload["source"], .string("apple_watch"))
    }

    // goals: I-18
    func testWatchScoreBelowOneIsRejectedAndNothingIsStored() throws {
        let store = makeStore()
        let bridge = WatchEventBridge(offlineStore: store, autoActivate: false, session: nil)

        let rejected = try GoalWatchFixture.deliver(WatchInputEvent(
            eventId: "watch-score-zero", roundId: "watch-round", hole: 2, kind: .score,
            value: "0", createdAt: "2026-11-10T08:02:00Z"
        ), to: bridge)
        XCTAssertEqual(rejected["accepted"] as? Bool, false)
        XCTAssertEqual(rejected["reason"] as? String, "invalid_numeric_input")
        XCTAssertEqual(rejected["rejectedEventIds"] as? [String], ["watch-score-zero"])
        XCTAssertTrue(try store.loadPendingEvents(roundId: "watch-round").isEmpty)

        let accepted = try GoalWatchFixture.deliver(WatchInputEvent(
            eventId: "watch-score-one", roundId: "watch-round", hole: 2, kind: .score,
            value: "1", createdAt: "2026-11-10T08:02:30Z"
        ), to: bridge)
        XCTAssertEqual(accepted["accepted"] as? Bool, true)
        XCTAssertEqual(try store.loadPendingEvents(roundId: "watch-round").map(\.eventId), ["watch-score-one"])
    }

    // goals: I-18
    func testRedeliveredWatchEventIsReportedAsDuplicateAndStoredOnce() throws {
        let store = makeStore()
        let bridge = WatchEventBridge(offlineStore: store, autoActivate: false, session: nil)
        let event = WatchInputEvent(
            eventId: "watch-putt-4", roundId: "watch-round", hole: 4, kind: .putt,
            value: "2", createdAt: "2026-11-10T08:04:00Z"
        )

        _ = try GoalWatchFixture.deliver(event, to: bridge)
        let again = try GoalWatchFixture.deliver(event, to: bridge)

        XCTAssertEqual(again["accepted"] as? Bool, true)
        XCTAssertEqual(again["acceptedEventIds"] as? [String], [])
        XCTAssertEqual(again["duplicateEventIds"] as? [String], [event.eventId])
        let pending = try store.loadPendingEvents(roundId: "watch-round")
        XCTAssertEqual(pending.map(\.eventId), [event.eventId])
        XCTAssertEqual(pending.first?.payload["putts"], .number(2))
    }

    // goals: I-18
    func testWatchStartAndFinishMessagesReachThePhoneCallbacks() throws {
        let bridge = WatchEventBridge(offlineStore: makeStore(), autoActivate: false, session: nil)
        let package = try LiveRoundPackageFixture.package()
        let seed = bridge.makeWatchRoundSeedPayload(package: package, activeHole: 2)
        var starts: [WatchRoundStartPayload] = []
        var closures: [WatchRoundClosurePayload] = []
        bridge.onRoundStarted = { starts.append($0) }
        bridge.onRoundClosure = { closures.append($0) }
        let start = WatchRoundStartPayload(
            roundId: package.roundId, courseName: package.course.venueDisplayName, teeBox: "blue",
            loopKey: package.loopKey, globalId: package.course.globalId, activeHole: 2, holes: seed.holes
        )
        let emptyStart = WatchRoundStartPayload(
            roundId: "empty-round", courseName: "Empty", teeBox: "blue",
            loopKey: package.loopKey, activeHole: 1, holes: []
        )
        let finish = WatchRoundClosurePayload(
            roundId: package.roundId, disposition: .finished, closedAt: "2026-11-10T10:00:00Z"
        )

        bridge.handleWatchRoundStart(try GoalWatchFixture.object(emptyStart))
        bridge.handleWatchRoundStart(try GoalWatchFixture.object(start))
        bridge.handleWatchRoundClosure(try GoalWatchFixture.object(finish))

        XCTAssertEqual(starts.map(\.roundId), [package.roundId], "a start without holes never reaches the phone")
        XCTAssertEqual(starts.first?.activeHole, 2)
        XCTAssertEqual(starts.first?.loopKey, package.loopKey)
        XCTAssertEqual(starts.first?.globalId, package.course.globalId)
        XCTAssertEqual(starts.first?.holes.map(\.hole), seed.holes.map(\.hole))
        XCTAssertEqual(closures, [finish])
    }

    // goals: I-18 [main]
    @MainActor
    func testWatchStartedRoundUploadsWatchScoreAndFinishesOnThePhone() async throws {
        let topo = C33TopoPrefetchScope()
        let store = makeStore()
        let watch = GoalWatchSession(activated: true, reachable: false)
        let bridge = WatchEventBridge(offlineStore: store, autoActivate: false, session: watch)
        let package = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        let packageData = try JSONEncoder().encode(package)
        let uploaded = GoalUploadLog()
        let uploadMatch = C33FirstMatch()
        let watchScoreUploaded = expectation(description: "Watch score reaches the backend")
        let scope = CapturingURLProtocolScope { request in
            let url = try XCTUnwrap(request.url)
            let path = url.path
            var status = 404
            var body = Data("{}".utf8)
            if path.hasSuffix("/package") {
                status = 200
                body = packageData
            } else if path.hasSuffix("/events") {
                let batch = try JSONDecoder().decode(
                    EventBatch.self, from: CapturingURLProtocol.requestBodyData(from: request)
                )
                uploaded.append(batch.events)
                if batch.events.contains(where: { $0.eventId == "watch-score-7" }), uploadMatch.claim() {
                    watchScoreUploaded.fulfill()
                }
                status = 200
                body = try JSONEncoder().encode(SyncResult(
                    accepted: batch.events.count, duplicate: false,
                    acceptedEventIds: batch.events.map(\.eventId), serverSequence: 1
                ))
            } else if path.hasSuffix("/events/replay") {
                status = 200
                body = Data("""
                    {"schema":"ai-caddie-mobile-event-replay-v1","roundId":"\(package.roundId)",\
                    "clientId":"ios-phone","afterSequence":0,"latestServerSequence":0,\
                    "nextCursor":0,"eventCount":0,"hasMore":false,"events":[]}
                    """.utf8)
            } else if path.hasSuffix("/events/ack") {
                status = 200
                body = Data("""
                    {"schema":"ai-caddie-mobile-event-ack-v1","roundId":"\(package.roundId)",\
                    "clientId":"ios-phone","ackedServerSequence":1,"latestServerSequence":1,\
                    "pendingEventCount":0}
                    """.utf8)
            }
            return (
                HTTPURLResponse(url: url, statusCode: status, httpVersion: nil,
                                headerFields: ["Content-Type": "application/json"])!,
                body
            )
        }
        let urlSession = URLSession(configuration: scope.configuration())
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://watch-goal.example.test")),
            clientId: "ios-phone", session: urlSession, retrySleep: { _ in }
        )
        let model = LiveRoundAppModel(
            offlineStore: store, apiBaseURL: client.baseURL, watchBridge: bridge,
            garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: nil
        )

        // Start: the Watch's round becomes the phone's live round and the Watch gets its seed.
        let seed = bridge.makeWatchRoundSeedPayload(package: package, activeHole: 1)
        await model.handleWatchRoundStart(WatchRoundStartPayload(
            roundId: package.roundId, courseName: package.course.venueDisplayName, teeBox: "blue",
            loopKey: package.loopKey, globalId: package.course.globalId, activeHole: 1, holes: seed.holes
        ))
        XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(
            (watch.publishedContexts.last?["roundSeed"] as? [String: Any])?["roundId"] as? String,
            package.roundId
        )

        // Score: stored on the phone, acknowledged to the Watch, then uploaded.
        let watchReply = expectation(description: "Watch receives the phone acknowledgement")
        let replyBox = GoalReplyBox()
        let score = WatchInputEvent(
            eventId: "watch-score-7", roundId: package.roundId, hole: 7, kind: .score,
            value: "5", createdAt: "2026-11-10T09:07:00Z"
        )
        bridge.handleWatchInputMessage(["event": try GoalWatchFixture.object(score)]) { reply in
            replyBox.set(reply)
            watchReply.fulfill()
        }
        await fulfillment(of: [watchReply, watchScoreUploaded], timeout: 10)
        let reply = try XCTUnwrap(replyBox.value)
        XCTAssertEqual(reply["acceptedEventIds"] as? [String], [score.eventId])
        XCTAssertTrue(try store.containsEvent(eventId: score.eventId))
        let sent = try XCTUnwrap(uploaded.events.first { $0.eventId == score.eventId })
        XCTAssertEqual(sent.roundId, package.roundId)
        XCTAssertEqual(sent.hole, 7)
        XCTAssertEqual(sent.kind, .score)
        XCTAssertEqual(sent.clientId, "apple-watch")
        XCTAssertEqual(sent.payload["strokes"], .number(5))
        XCTAssertEqual(sent.payload["source"], .string("apple_watch"))

        // Finish: the Watch's finish closes the phone's round once nothing is left to upload.
        model.handleWatchRoundClosure(WatchRoundClosurePayload(
            roundId: package.roundId, disposition: .finished, closedAt: "2026-11-10T10:00:00Z"
        ))
        await model.waitForWatchRoundClosureReconciliationForTesting()
        XCTAssertNil(model.liveRoundState)
        XCTAssertNil(try store.loadCurrentRoundPackage())
        XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)

        await topo.stop()
        client.invalidateForTesting()
        urlSession.invalidateAndCancel()
        withExtendedLifetime(scope) {}
    }

    // MARK: - helpers

    private func makeStore() -> OfflineStore {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        directories.append(directory)
        return OfflineStore(directoryURL: directory)
    }
}

/// A WatchConnectivity stand-in recording what the phone sends and how.
private final class GoalWatchSession: WatchSessioning {
    var isSessionActivated: Bool
    var isCounterpartReachable: Bool
    var receivedContext: [String: Any] = [:]
    var sentContext: [String: Any] = [:]
    private(set) var sentMessages: [[String: Any]] = []
    private(set) var queuedUserInfo: [[String: Any]] = []
    private(set) var publishedContexts: [[String: Any]] = []

    init(activated: Bool, reachable: Bool) {
        isSessionActivated = activated
        isCounterpartReachable = reachable
    }

    func activateSession() { isSessionActivated = true }

    func send(
        _ message: [String: Any],
        onReply: (([String: Any]) -> Void)?,
        onError: ((Error) -> Void)?
    ) {
        sentMessages.append(message)
    }

    func queueUserInfo(_ userInfo: [String: Any]) { queuedUserInfo.append(userInfo) }

    func replaceContext(_ context: [String: Any]) throws {
        publishedContexts.append(context)
        sentContext = context
    }
}

private enum GoalWatchFixture {
    static func option(club: String, origin: [String]) -> WatchCaddieOption {
        WatchCaddieOption(optionId: "plan-\(club)", label: club, clubName: club, originShotEventIds: origin)
    }

    static func state(from envelope: [String: Any]) throws -> WatchRoundStatePayload {
        let object = try XCTUnwrap(envelope["state"])
        return try JSONDecoder().decode(
            WatchRoundStatePayload.self, from: JSONSerialization.data(withJSONObject: object)
        )
    }

    static func object<T: Encodable>(_ value: T) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any])
    }

    /// Delivers through the bridge path without a model, which replies before returning.
    static func deliver(_ event: WatchInputEvent, to bridge: WatchEventBridge) throws -> [String: Any] {
        var reply: [String: Any]?
        bridge.handleWatchInputMessage(["event": try object(event)]) { reply = $0 }
        return try XCTUnwrap(reply)
    }
}

private final class GoalUploadLog {
    private let lock = NSLock()
    private var stored: [LiveRoundEvent] = []

    func append(_ events: [LiveRoundEvent]) {
        lock.lock(); stored += events; lock.unlock()
    }

    var events: [LiveRoundEvent] {
        lock.lock(); defer { lock.unlock() }
        return stored
    }
}

private final class GoalReplyBox {
    private let lock = NSLock()
    private var stored: [String: Any]?

    func set(_ reply: [String: Any]) {
        lock.lock(); stored = reply; lock.unlock()
    }

    var value: [String: Any]? {
        lock.lock(); defer { lock.unlock() }
        return stored
    }
}
