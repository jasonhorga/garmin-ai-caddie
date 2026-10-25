#if !SWIFT_PACKAGE
import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class C33EventTests: XCTestCase {
    func testEveryRouteTokenProducesOnlyServerStrategyEnumsOrOmission() throws {
        // Server _LIVE_EVENT_PAYLOAD_ENUMS is the authority, not another client mapper.
        let allowed: Set<String> = ["protect_score", "stock", "attack"]
        let aliases = ["conservative layup", "safe", "safe line", "safe route", "conservative", "protect",
            "protect score", "lay back", "layup", "lay up", "stock line", "stock", "stock route",
            "standard", "standard line", "neutral", "recommended", "recommended line", "aggressive line",
            "attack", "attack line", "aggressive", "go for it", "go for it line", "unknown-route",
            "driver-3w", "route:7I", "", "   ", "未知方案"]
        // An unknown route is not a stock shot: the optional field is omitted, never coerced.
        let unknownRoutes = ["unknown-route", "driver-3w", "route:7I", "", "   ", "未知方案"]
        let unknownInputs = Set(unknownRoutes + unknownRoutes.map {
            $0.uppercased().replacingOccurrences(of: " ", with: "_")
        })
        let bridgeDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let bridge = WatchEventBridge(offlineStore: OfflineStore(directoryURL: bridgeDirectory))
        defer { try? FileManager.default.removeItem(at: bridgeDirectory) }
        let builder = LiveRoundEventBuilder(roundId: "c33-round", idFactory: { "builder-event" })
        for route in aliases + aliases.map({ $0.uppercased().replacingOccurrences(of: " ", with: "_") }) {
            let event = try bridge.mapWatchInputEvent(WatchInputEvent(
                eventId: UUID().uuidString, roundId: "c33-round", hole: 1, kind: .club,
                value: "7I", createdAt: "2026-01-01T00:00:00Z", strategyMode: route
            ))
            if let value = event.payload["strategyMode"] {
                guard case let .string(mode) = value else { return XCTFail("strategyMode must be string") }
                XCTAssertTrue(allowed.contains(mode), "route=\(route), payload=\(mode)")
            }
            let built = builder.makeClubEvent(hole: 1, clubName: "7I", strategyMode: route)
            if let value = built.payload["strategyMode"] {
                guard case let .string(mode) = value else { return XCTFail("strategyMode must be string") }
                XCTAssertTrue(allowed.contains(mode), "builder route=\(route), payload=\(mode)")
            }
            if unknownInputs.contains(route) {
                XCTAssertNil(event.payload["strategyMode"], "unknown route=\(route)")
                XCTAssertNil(built.payload["strategyMode"], "builder unknown route=\(route)")
            }
        }
    }

    func testIdempotencyKeyBindsBodyAndIsStableAcrossTransportRetry() async throws {
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-key.example.test")!, session: session)
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        var keys: [String: [String]] = [:]
        let keysLock = NSLock()
        C33URLProtocol.onStart = { proto in
            if proto.request.url!.path.hasSuffix("/package") { proto.reply(200, packageData); return }
            guard proto.request.httpMethod == "POST", proto.request.url!.path.hasSuffix("/events") else {
                proto.reply(404); return
            }
            do {
                let batch = try JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                guard let value = batch.events[0].payload["strategyMode"], case let .string(mode) = value else {
                    XCTFail("missing strategy"); proto.reply(422); return
                }
                keysLock.lock()
                keys[mode, default: []].append(proto.request.value(forHTTPHeaderField: "Idempotency-Key") ?? "")
                let first = keys[mode]!.count == 1
                keysLock.unlock()
                if first { proto.reply(503); return }
                proto.reply(200, try JSONEncoder().encode(SyncResult(accepted: 1, duplicate: false, acceptedEventIds: ["e1"])))
            } catch { XCTFail("\(error)"); proto.reply(500) }
        }
        URLProtocol.registerClass(C33URLProtocol.self)
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.onStart = nil
            URLProtocol.unregisterClass(C33URLProtocol.self)
        }
        for mode in ["stock", "attack"] {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            let store = OfflineStore(directoryURL: directory)
            let model = c33Model(store, client)
            await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
            try store.appendEvent(LiveRoundEvent(
                eventId: "e1", roundId: package.roundId, timestamp: "2026-01-01T00:00:00Z",
                hole: 1, kind: .club, payload: ["clubName": .string("7I"), "strategyMode": .string(mode)]
            ))
            await model.syncPendingEvents()
            XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)
            XCTAssertEqual(try store.loadEvents().filter { $0.kind == .syncMarker }.count, 1)
        }
        // Same immutable body retries with the same key; a changed body cannot reuse that key.
        XCTAssertEqual(keys["stock"]?.count, 2)
        XCTAssertEqual(keys["attack"]?.count, 2)
        XCTAssertEqual(keys["stock"]?.first, keys["stock"]?.last)
        XCTAssertEqual(keys["attack"]?.first, keys["attack"]?.last)
        XCTAssertNotEqual(keys["stock"]?.first, keys["attack"]?.first)
    }

    func testOne422IsQuarantinedAndOtherFourEventsUpload() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-events.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        let lock = NSLock()
        var accepted = Set<String>()
        var keysByRoster: [String: String] = [:]
        C33URLProtocol.onStart = { proto in
            if proto.request.url!.path.hasSuffix("/package") { proto.reply(200, packageData); return }
            guard proto.request.httpMethod == "POST", proto.request.url!.path.hasSuffix("/events") else {
                proto.reply(404); return
            }
            do {
                let batch = try JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                let ids = batch.events.map(\.eventId)
                let roster = ids.joined(separator: ",")
                lock.lock()
                if let previous = keysByRoster[roster] { XCTAssertEqual(previous, proto.request.value(forHTTPHeaderField: "Idempotency-Key")) }
                keysByRoster[roster] = proto.request.value(forHTTPHeaderField: "Idempotency-Key")
                if !ids.contains("e3") { accepted.formUnion(ids) }
                lock.unlock()
                if ids.contains("e3") {
                    proto.reply(422, Data(#"{"detail":[{"type":"enum","loc":["body","events",0,"payload","strategyMode"],"msg":"Input should be one of attack, protect_score, stock"}]}"#.utf8)); return
                }
                proto.reply(200, try JSONEncoder().encode(SyncResult(accepted: ids.count, duplicate: false, acceptedEventIds: ids)))
            } catch { XCTFail("\(error)"); proto.reply(500) }
        }
        URLProtocol.registerClass(C33URLProtocol.self)
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.onStart = nil
            URLProtocol.unregisterClass(C33URLProtocol.self)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        for index in 1...5 {
            try store.appendEvent(LiveRoundEvent(
                eventId: "e\(index)", roundId: package.roundId, timestamp: "2026-01-01T00:00:00Z",
                hole: 1, kind: .club, payload: ["clubName": .string("7I"), "strategyMode": .string(index == 3 ? "unknown-route" : "stock")]
            ))
        }
        await model.syncPendingEvents()
        // C33: one bad event in five must leave four ACKed, one durable diagnostic, no poisoned tail.
        XCTAssertEqual(accepted, ["e1", "e2", "e4", "e5"])
        XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)
        let quarantined = try store.loadQuarantinedEvents(roundId: package.roundId)
        XCTAssertEqual(quarantined.map { $0.event.eventId }, ["e3"])
        XCTAssertEqual(quarantined.first?.status, 422)
        XCTAssertEqual(quarantined.first?.event.payload["strategyMode"], .string("unknown-route"))
        XCTAssertFalse(quarantined.first?.reason.isEmpty ?? true)
        XCTAssertEqual(try OfflineStore(directoryURL: directory).loadQuarantinedEvents(roundId: package.roundId), quarantined)
        XCTAssertEqual(try store.loadEvents().filter { $0.kind != .syncMarker }.count, 5)
        XCTAssertEqual(model.pendingEventCount, 0)
        XCTAssertEqual(try store.loadEvents().filter { $0.kind == .syncMarker }.count, 1)
    }

    func testStoreOrIdempotency422KeepsWholeBatchRetryable() async throws {
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        // Neither a store/idempotency failure nor a pydantic error outside the event payload is a
        // payload reject. FastAPI echoes the failing event as `input`, so the raw text of the list
        // still says "payload"; only the structured `loc` tells the two apart.
        let bodies = [
            #"{"detail":"idempotency_key_body_mismatch"}"#,
            #"{"detail":[{"type":"missing","loc":["body","events",0,"timestamp"],"msg":"Field required","input":{"eventId":"bad-store","hole":1,"kind":"club","payload":{"clubName":"7I","strategyMode":"stock"}}}]}"#,
        ]
        for body in bodies {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            let store = OfflineStore(directoryURL: directory)
            let session = C33URLProtocol.session()
            let client = SyncClient(baseURL: URL(string: "https://c33-store-error.example.test")!, session: session)
            let model = c33Model(store, client)
            C33URLProtocol.setHandlers(onStart: { proto in
                if proto.request.url!.path.hasSuffix("/package") {
                    proto.reply(200, packageData); return
                }
                proto.reply(422, Data(body.utf8))
            })
            defer {
                client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
                try? FileManager.default.removeItem(at: directory)
            }
            await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
            try store.appendEvent(LiveRoundEvent(eventId: "bad-store", roundId: package.roundId,
                timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .club,
                payload: ["clubName": .string("7I"), "strategyMode": .string("stock")]))
            await model.syncPendingEvents()
            XCTAssertEqual(try store.loadPendingEvents(roundId: package.roundId).map(\.eventId), ["bad-store"], body)
            XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty, body)
            XCTAssertEqual(try store.loadEvents().filter { $0.kind == .syncMarker }.count, 0, body)
        }
    }

    func testDiscardActiveRoundRemovesItsQuarantineDiagnostics() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-discard.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.onStart = { proto in
            if proto.request.url!.path.hasSuffix("/package") {
                proto.reply(200, try! JSONEncoder().encode(package))
            } else { proto.reply(404) }
        }
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.onStart = nil
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let event = LiveRoundEvent(eventId: "q1", roundId: package.roundId, timestamp: "2026-01-01T00:00:00Z",
            hole: 1, kind: .club, payload: ["clubName": .string("7I")])
        try store.quarantineEvent(event, status: 422, reason: "payload")
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).count, 1)
        model.discardActiveRound()
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
    }

    func testReplacementScoreClearsQuarantineAndAllowsFinish() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-score-replacement.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") {
                proto.reply(200, try! JSONEncoder().encode(package)); return
            }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                if batch.events.contains(where: { $0.eventId == "bad-score" }) {
                    proto.reply(422, Data(#"{"detail":[{"type":"enum","loc":["body","events",0,"payload","strokes"],"msg":"invalid score"}]}"#.utf8))
                } else {
                    proto.reply(200, try! JSONEncoder().encode(SyncResult(
                        accepted: batch.events.count, duplicate: false,
                        acceptedEventIds: batch.events.map(\.eventId)
                    )))
                }
                return
            }
            if path.hasSuffix("/finish") { proto.reply(200); return }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "bad-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score,
            payload: ["strokes": .number(99)]))
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).count, 1)
        model.handleWatchRoundClosure(WatchRoundClosurePayload(
            roundId: package.roundId, disposition: .finished
        ))
        await model.waitForWatchRoundClosureReconciliationForTesting()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).count, 1)
        let blockedFinish = await model.finishActiveRound()
        XCTAssertFalse(blockedFinish)
        try store.appendEvent(LiveRoundEvent(eventId: "replacement-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 1, kind: .score,
            payload: ["strokes": .number(4)]))
        await model.syncPendingEvents()
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
        let finished = await model.finishActiveRound()
        XCTAssertTrue(finished)
    }

    func testDeferredFinishNeverReachesServerWhileAScoreIsQuarantined() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let host = "c33-deferred-finish.example.test"
        let client = SyncClient(baseURL: URL(string: "https://\(host)")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        let finishLock = NSLock()
        var finishRequests = 0
        C33URLProtocol.setHandlers(onStart: { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, packageData); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                if batch.events.contains(where: { $0.eventId == "bad-score" }) {
                    proto.reply(422, Data(#"{"detail":[{"type":"enum","loc":["body","events",0,"payload","strokes"],"msg":"invalid score"}]}"#.utf8))
                } else {
                    proto.reply(200, try! JSONEncoder().encode(SyncResult(
                        accepted: batch.events.count, duplicate: false,
                        acceptedEventIds: batch.events.map(\.eventId)
                    )))
                }
                return
            }
            if path.hasSuffix("/finish") {
                finishLock.lock(); finishRequests += 1; finishLock.unlock()
                proto.reply(200); return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        // Save & End while the score is still queued: sealing succeeds, and the upload, its 422
        // and the server finish all happen later in the deferred finish pass.
        try store.appendEvent(LiveRoundEvent(eventId: "bad-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score,
            payload: ["strokes": .number(99)]))
        let sealed = await model.finishActiveRound()
        XCTAssertTrue(sealed)
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).map { $0.event.eventId }, ["bad-score"])
        finishLock.lock(); let blockedFinishes = finishRequests; finishLock.unlock()
        // The server round must stay open until the rejected hole is re-entered.
        XCTAssertEqual(blockedFinishes, 0)
        XCTAssertEqual(try store.loadPendingRoundFinishes().map(\.roundId), [package.roundId])

        try store.appendEvent(LiveRoundEvent(eventId: "replacement-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 1, kind: .score,
            payload: ["strokes": .number(4)]))
        await model.syncPendingEvents()
        await model.waitForDeferredRoundFinishesForTesting()
        finishLock.lock(); let finishes = finishRequests; finishLock.unlock()
        XCTAssertEqual(finishes, 1)
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
        XCTAssertTrue(try store.loadPendingRoundFinishes().isEmpty)
    }
}
#endif
