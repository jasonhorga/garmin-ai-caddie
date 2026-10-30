#if !SWIFT_PACKAGE
import Combine
import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class C33EventTests: XCTestCase {
    /// Product spec 5.9: quarantine eligibility follows the wire code, independent of wording.
    func testProductSpec59EventInvalidCodeOverridesLegacyWording() {
        let cases: [(String, Bool)] = [
            (#"{"detail":{"code":"event_invalid","message":"记录内容不符合约定"}}"#, true),
            (#"{"detail":{"code":"event_invalid","message":"payload rejected"}}"#, true),
            (#"{"detail":{"code":"batch_invalid","message":"payload must be valid"}}"#, false),
            (#"{"detail":{"code":null,"message":"payload must be valid"}}"#, false),
            (#"{"detail":"club payload field strategyMode must be one of stock, attack"}"#, true),
            (#"{"detail":"roundId does not match path"}"#, false),
            (#"{"detail":[{"loc":["body","events",0,"payload"],"msg":"Invalid object"}]}"#, true),
        ]
        for (body, expected) in cases {
            XCTAssertEqual(LiveRoundAppModel.isSingleEventPayloadValidation422(body), expected, body)
        }
    }

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

    /// Product spec 5.9 / C145-1: a successful first upload preserves the append-only local order;
    /// hole grouping is reserved for the later rejection bisection path.
    func testProductSpec59InitialUploadPreservesEventLogOrder() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c145-order.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        var uploaded: [String] = []
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                uploaded = batch.events.map(\.eventId)
                proto.reply(200, try! JSONEncoder().encode(SyncResult(
                    accepted: batch.events.count, duplicate: false, acceptedEventIds: uploaded
                )))
                return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        for (index, hole) in [1, 2, 1, 3].enumerated() {
            try store.appendEvent(LiveRoundEvent(
                eventId: "order-\(index)", roundId: package.roundId,
                timestamp: "2026-01-01T00:00:0\(index)Z", hole: hole, kind: .club,
                payload: ["clubName": .string("7I")]
            ))
        }
        await model.syncPendingEvents()
        XCTAssertEqual(uploaded, ["order-0", "order-1", "order-2", "order-3"])
    }

    func testOne422IsQuarantinedAndOtherFourEventsUpload() async throws {
        try await assertOneInvalidEventIsQuarantined(
            responseBody: #"{"detail":[{"type":"enum","loc":["body","events",0,"payload","strategyMode"],"msg":"Input should be one of attack, protect_score, stock"}]}"#
        )
    }

    func testProductSpec59ChangedMessageWithEventInvalidCodeStillQuarantinesOnlyOneEvent() async throws {
        try await assertOneInvalidEventIsQuarantined(
            responseBody: #"{"detail":{"code":"event_invalid","message":"记录内容不符合约定"}}"#
        )
    }

    /// Product spec J5.9: a rejected score remains visible with the server's reason while siblings sync.
    func testProductSpec57ScoreInvariantCodeQuarantinesWithReasonAndShowsScorePrompt() async throws {
        try await assertOneInvalidEventIsQuarantined(
            responseBody: #"{"detail":{"code":"event_invalid","message":"hole 3: total 2 is less than putts 2 + penalties 0 + 1"}}"#,
            invalidKind: .score
        )
    }

    /// Product spec J5.9: putts and penalties are score facts and need the same actionable prompt.
    func testProductSpec57RejectedPuttShowsHolePrompt() async throws {
        try await assertOneInvalidEventIsQuarantined(
            responseBody: #"{"detail":{"code":"event_invalid","message":"hole 1: total 2 is less than putts 2 + penalties 0 + 1"}}"#,
            invalidKind: .putt
        )
    }

    func testProductSpec57RejectedPenaltyShowsHolePrompt() async throws {
        try await assertOneInvalidEventIsQuarantined(
            responseBody: #"{"detail":{"code":"event_invalid","message":"hole 1: total 2 is less than putts 2 + penalties 1 + 1"}}"#,
            invalidKind: .penalty
        )
    }

    /// Product spec J5.9: scoring facts for one hole are an atomic retry unit during bisection.
    func testProductSpec59SameHoleScoringEventsStayTogetherWhenAnotherEventIsRejected() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c137-hole-group.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            guard path.hasSuffix("/events") else { proto.reply(404); return }
            let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
            let ids = batch.events.map(\.eventId)
            var strokes = 5
            var putts = 2
            var penalties = 2
            for event in batch.events where event.hole == 1 {
                switch event.kind {
                case .score:
                    if case let .number(value)? = event.payload["strokes"] { strokes = Int(value) }
                case .putt:
                    if case let .number(value)? = event.payload["putts"] { putts = Int(value) }
                case .penalty:
                    if case let .number(value)? = event.payload["penalties"] { penalties = Int(value) }
                default:
                    break
                }
            }
            // Mirror require_possible_appended_scores: the server already stores 5/2/2, so a
            // singleton score=3 is rejected even though the complete 3/1/1 append is valid.
            let violatesInvariant = strokes < putts + penalties + 1
            if ids.contains("bad-club") || violatesInvariant {
                let message = violatesInvariant
                    ? "hole 1: total \(strokes) is less than putts \(putts) + penalties \(penalties) + 1"
                    : "invalid batch"
                let body = #"{"detail":{"code":"event_invalid","message":"\#(message)"}}"#
                proto.reply(422, Data(body.utf8))
            } else {
                proto.reply(200, try! JSONEncoder().encode(SyncResult(
                    accepted: ids.count, duplicate: false, acceptedEventIds: ids
                )))
            }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "score-1", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score, payload: ["strokes": .number(3)]))
        try store.appendEvent(LiveRoundEvent(eventId: "putt-1", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:01Z", hole: 1, kind: .putt, payload: ["putts": .number(1)]))
        try store.appendEvent(LiveRoundEvent(eventId: "penalty-1", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:02Z", hole: 1, kind: .penalty, payload: ["penalties": .number(1)]))
        try store.appendEvent(LiveRoundEvent(eventId: "bad-club", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:03Z", hole: 1, kind: .club, payload: ["clubName": .string("7I")]))
        await model.syncPendingEvents()
        XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)
        XCTAssertEqual(try store.loadEvents().filter { $0.kind == .syncMarker }.count, 1)
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).map { $0.event.eventId }, ["bad-club"])
    }

    /// Product spec J5.9: a later server rejection cannot erase an earlier local rejection.
    func testProductSpec59LaterRejectedScoreRemainsVisibleAfterEarlierScoreAccepted() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let syncClient = SyncClient(baseURL: URL(string: "https://c137-order.example.test")!, session: session)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            guard path.hasSuffix("/events") else { proto.reply(404); return }
            let ids = (try? JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request)))?.events.map(\.eventId) ?? []
            proto.reply(200, try! JSONEncoder().encode(SyncResult(
                accepted: ids.count, duplicate: false, acceptedEventIds: ids
            )))
        })
        defer {
            syncClient.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        // This test intentionally uses the model's client session; the same URLProtocol handler
        // serves the package and event calls.
        let model = c33Model(store, syncClient)
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "older-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score, payload: ["strokes": .number(5)]))
        try store.appendEvent(LiveRoundEvent(eventId: "newer-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:01Z", hole: 1, kind: .score, payload: ["strokes": .number(4)]))
        try store.quarantineEvent(
            LiveRoundEvent(eventId: "newer-score", roundId: package.roundId,
                timestamp: "2026-01-01T00:00:01Z", hole: 1, kind: .score,
                payload: ["strokes": .number(4)]),
            status: 422, reason: "later score rejected"
        )
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).map { $0.event.eventId }, ["newer-score"])
        XCTAssertEqual(model.syncStatus, "第 1 洞成绩被服务器拒绝（later score rejected）")
    }

    /// Product spec J5.9: a different scoring fact cannot silently replace a rejected score.
    func testProductSpec59DifferentScoringKindKeepsQuarantineAndFinishTargetsHole() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c137-same-kind.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                proto.reply(200, try! JSONEncoder().encode(SyncResult(
                    accepted: batch.events.count, duplicate: false, acceptedEventIds: batch.events.map(\.eventId)
                )))
                return
            }
            if path.hasSuffix("/finish") { proto.reply(200); return }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let rejected = LiveRoundEvent(eventId: "rejected-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 7, kind: .score,
            payload: ["strokes": .number(5)])
        try store.appendEvent(rejected)
        try store.quarantineEvent(rejected, status: 422, reason: "score fact rejected")
        try store.appendEvent(LiveRoundEvent(eventId: "accepted-putt", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 7, kind: .putt,
            payload: ["putts": .number(1)]))
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).map { $0.event.eventId }, ["rejected-score"])
        XCTAssertEqual(model.syncStatus, "第 7 洞成绩被服务器拒绝（score fact rejected）")
        XCTAssertFalse(model.syncStatus.contains("已同步"))
        let blockedFinish = await model.finishActiveRound()
        XCTAssertFalse(blockedFinish)
        XCTAssertEqual(model.liveRoundState?.activeHole, 7)
    }

    /// Product spec J5.9: the latest accepted same-kind fact is the one that may replace a rejection.
    func testProductSpec59LatestSameKindAcceptedEventClearsEarlierQuarantine() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c137-latest-kind.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                proto.reply(200, try! JSONEncoder().encode(SyncResult(
                    accepted: batch.events.count, duplicate: false, acceptedEventIds: batch.events.map(\.eventId)
                )))
                return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "older-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 4, kind: .score, payload: ["strokes": .number(5)]))
        let rejected = LiveRoundEvent(eventId: "rejected-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 4, kind: .score,
            payload: ["strokes": .number(6)])
        try store.appendEvent(rejected)
        try store.quarantineEvent(rejected, status: 422, reason: "old rejection")
        try store.appendEvent(LiveRoundEvent(eventId: "newer-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:02:00Z", hole: 4, kind: .score, payload: ["strokes": .number(4)]))
        await model.syncPendingEvents()
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
    }

    /// Product spec J5.9: repeated historical identities do not crash ordering cleanup.
    func testProductSpec59DuplicateHistoricalEventIdsDoNotCrashOrderingCleanup() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c137-duplicate-id.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                proto.reply(200, try! JSONEncoder().encode(SyncResult(
                    accepted: batch.events.count, duplicate: false, acceptedEventIds: batch.events.map(\.eventId)
                )))
                return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        for timestamp in ["2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"] {
            try store.appendEvent(LiveRoundEvent(eventId: "duplicate-history", roundId: package.roundId,
                timestamp: timestamp, hole: 2, kind: .club, payload: ["clubName": .string("7I")]))
        }
        try store.appendSyncMarker(roundId: package.roundId, timestamp: "2026-01-01T00:00:02Z")
        try store.appendEvent(LiveRoundEvent(eventId: "new-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:03Z", hole: 2, kind: .score, payload: ["strokes": .number(4)]))
        await model.syncPendingEvents()
        XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)
        XCTAssertEqual(model.syncStatus, "已同步")
    }

    /// Product spec J5.9: an offline re-entry waits for sync instead of asking for another re-entry.
    func testProductSpec59OfflineReplacementReportsWaitingForSync() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c137-offline-reentry.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path.hasSuffix("/package") == true {
                proto.reply(200, try! JSONEncoder().encode(package))
            } else {
                proto.reply(404)
            }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let rejected = LiveRoundEvent(eventId: "offline-rejected", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 6, kind: .score,
            payload: ["strokes": .number(99)])
        try store.appendEvent(rejected)
        try store.quarantineEvent(rejected, status: 422, reason: "score fact rejected")
        try store.appendEvent(LiveRoundEvent(eventId: "offline-replacement", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 6, kind: .score,
            payload: ["strokes": .number(4)]))
        let blockedFinish = await model.finishActiveRound()
        XCTAssertFalse(blockedFinish)
        XCTAssertTrue(model.finishErrorMessage?.contains("正在同步") == true ||
                      model.finishErrorMessage?.contains("等待联网") == true)
        XCTAssertFalse(model.finishErrorMessage?.contains("请重新录入") == true)
    }

    /// Product spec J5.9: an atomic rejected scoring group preserves the server reason for every fact.
    func testProductSpec59AtomicScoringQuarantinePreservesReasonForEveryEvent() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c137-group-reason.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        let reason = "hole 1: total 1 is less than putts 1 + penalties 1 + 1"
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"hole 1: total 1 is less than putts 1 + penalties 1 + 1"}}"#.utf8))
                return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "group-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score, payload: ["strokes": .number(1)]))
        try store.appendEvent(LiveRoundEvent(eventId: "group-putt", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:01Z", hole: 1, kind: .putt, payload: ["putts": .number(1)]))
        try store.appendEvent(LiveRoundEvent(eventId: "group-penalty", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:02Z", hole: 1, kind: .penalty, payload: ["penalties": .number(1)]))
        await model.syncPendingEvents()
        let quarantined = try store.loadQuarantinedEvents(roundId: package.roundId)
        XCTAssertEqual(quarantined.map { $0.event.eventId }, ["group-score", "group-putt", "group-penalty"])
        XCTAssertEqual(quarantined.map(\.reason), [reason, reason, reason])
    }

    private func assertOneInvalidEventIsQuarantined(
        responseBody: String, invalidKind: LiveRoundEventKind = .club
    ) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let host = "c33-events-\(UUID().uuidString.lowercased()).example.test"
        let client = SyncClient(baseURL: URL(string: "https://\(host)")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        let lock = NSLock()
        var accepted = Set<String>()
        var keysByRoster: [String: String] = [:]
        C33URLProtocol.onStart = { proto in
            guard proto.request.url?.host == host else { proto.reply(404); return }
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
                    proto.reply(422, Data(responseBody.utf8)); return
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
            let eventKind = invalidKind == .score || index == 3 ? invalidKind : .club
            try store.appendEvent(LiveRoundEvent(
                eventId: "e\(index)", roundId: package.roundId, timestamp: "2026-01-01T00:00:00Z",
                // Scores sit on distinct holes: an accepted score for the same hole would
                // legitimately supersede (un-quarantine) the rejected one.
                hole: eventKind == .score ? index : 1, kind: eventKind,
                payload: eventKind == .score
                    ? ["strokes": .number(2)]
                : (eventKind == .putt
                    ? ["putts": .number(index == 3 ? 2 : 1)]
                    : (eventKind == .penalty
                        ? ["penalties": .number(index == 3 ? 1 : 0)]
                        : ["clubName": .string("7I"), "strategyMode": .string(index == 3 ? "unknown-route" : "stock")]))
            ))
        }
        await model.syncPendingEvents()
        // C33: one bad event in five must leave four ACKed, one durable diagnostic, no poisoned tail.
        XCTAssertEqual(accepted, ["e1", "e2", "e4", "e5"])
        XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)
        let quarantined = try store.loadQuarantinedEvents(roundId: package.roundId)
        XCTAssertEqual(quarantined.map { $0.event.eventId }, ["e3"])
        XCTAssertEqual(quarantined.first?.status, 422)
        if invalidKind == .score {
            XCTAssertEqual(quarantined.first?.event.payload["strokes"], .number(2))
        } else if invalidKind == .club {
            XCTAssertEqual(quarantined.first?.event.payload["strategyMode"], .string("unknown-route"))
        }
        XCTAssertFalse(quarantined.first?.reason.isEmpty ?? true)
        if invalidKind == .score || invalidKind == .putt || invalidKind == .penalty {
            let label = invalidKind == .score ? "成绩" : (invalidKind == .putt ? "推杆" : "罚杆")
            let hole = invalidKind == .score ? 3 : 1
            let message = invalidKind == .penalty
                ? "hole 1: total 2 is less than putts 2 + penalties 1 + 1"
                : "hole \(hole): total 2 is less than putts 2 + penalties 0 + 1"
            XCTAssertTrue(quarantined.first?.reason.contains("hole \(hole): total 2") == true)
            XCTAssertEqual(model.syncStatus, "第 \(hole) 洞\(label)被服务器拒绝（\(message)）")
            XCTAssertEqual(model.localEventUploadStatus, "第 \(hole) 洞\(label)被服务器拒绝（\(message)）")
        }
        XCTAssertEqual(try OfflineStore(directoryURL: directory).loadQuarantinedEvents(roundId: package.roundId), quarantined)
        XCTAssertEqual(try store.loadEvents().filter { $0.kind != .syncMarker }.count, 5)
        XCTAssertEqual(model.pendingEventCount, 0)
        XCTAssertEqual(try store.loadEvents().filter { $0.kind == .syncMarker }.count, 1)
        await model.stopRoundBackgroundWorkForTesting()
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
                // Mirror the score invariant against the server's existing 5/2/2 facts. The
                // event id is deliberately unhelpful: rejection follows the actual score facts.
                var strokes = 5
                var putts = 2
                var penalties = 2
                for event in batch.events where event.hole == 1 {
                    switch event.kind {
                    case .score: if case let .number(value) = event.payload["strokes"] { strokes = Int(value) }
                    case .putt: if case let .number(value) = event.payload["putts"] { putts = Int(value) }
                    case .penalty: if case let .number(value) = event.payload["penalties"] { penalties = Int(value) }
                    default: break
                    }
                }
                if strokes < putts + penalties + 1 {
                    let reason = "hole 1: total \(strokes) is less than putts \(putts) + penalties \(penalties) + 1"
                    proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"\#(reason)"}}"#.utf8))
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
        try store.appendEvent(LiveRoundEvent(eventId: "accepted-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score,
            payload: ["strokes": .number(3)]))
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).count, 1)
        model.handleWatchRoundClosure(WatchRoundClosurePayload(
            roundId: package.roundId, disposition: .finished
        ))
        await model.waitForWatchRoundClosureReconciliationForTesting()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).count, 1)
        let blockedFinish = await model.finishActiveRound()
        XCTAssertFalse(blockedFinish)
        try store.appendEvent(LiveRoundEvent(eventId: "bad-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 1, kind: .score,
            payload: ["strokes": .number(5)]))
        await model.syncPendingEvents()
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
        let finished = await model.finishActiveRound()
        XCTAssertTrue(finished)
    }

    /// Product spec 5.9 / C145-5b: a Watch closure with no pending tail must keep the concrete
    /// rejected-hole prompt when local cleanup is blocked by quarantine.
    func testProductSpec59WatchClosureWithoutPendingPreservesRejectedHolePrompt() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c145-watch-direct.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path.hasSuffix("/package") == true {
                proto.reply(200, try! JSONEncoder().encode(package))
            } else { proto.reply(404) }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let rejected = LiveRoundEvent(eventId: "watch-direct-rejected", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 3, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejected)
        try store.appendSyncMarker(roundId: package.roundId, timestamp: "2026-01-01T00:00:01Z",
            result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
        try store.quarantineEvent(rejected, status: 422, reason: "bad score")
        model.handleWatchRoundClosure(WatchRoundClosurePayload(roundId: package.roundId, disposition: .finished))
        await model.waitForWatchRoundClosureReconciliationForTesting()
        XCTAssertTrue(model.finishErrorMessage?.contains("第 3 洞成绩被服务器拒绝") == true)
    }

    /// Product spec 5.9 / C145-5b: the reconciliation path also preserves the concrete prompt
    /// after it uploads a late local tail.
    func testProductSpec59WatchReconciliationPreservesRejectedHolePrompt() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c145-watch-reconcile.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                proto.reply(200, try! JSONEncoder().encode(SyncResult(
                    accepted: batch.events.count, duplicate: false, acceptedEventIds: batch.events.map(\.eventId)
                )))
                return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let rejected = LiveRoundEvent(eventId: "watch-reconcile-rejected", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 3, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejected)
        try store.appendSyncMarker(roundId: package.roundId, timestamp: "2026-01-01T00:00:01Z",
            result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
        try store.quarantineEvent(rejected, status: 422, reason: "bad score")
        try store.appendEvent(LiveRoundEvent(eventId: "watch-late-club", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:02Z", hole: 3, kind: .club,
            payload: ["clubName": .string("7I")]))
        model.handleWatchRoundClosure(WatchRoundClosurePayload(roundId: package.roundId, disposition: .finished))
        await model.waitForWatchRoundClosureReconciliationForTesting()
        XCTAssertTrue(model.finishErrorMessage?.contains("第 3 洞成绩被服务器拒绝") == true)
    }

    func testReplacementPuttClearsQuarantineAndAllowsFinish() async throws {
        try await assertReplacementScoringEventAllowsFinish(
            kind: .putt, payload: ["putts": .number(2)], replacement: ["putts": .number(1)]
        )
    }

    func testReplacementPenaltyClearsQuarantineAndAllowsFinish() async throws {
        try await assertReplacementScoringEventAllowsFinish(
            kind: .penalty, payload: ["penalties": .number(2)], replacement: ["penalties": .number(0)]
        )
    }

    /// Product spec 5.9 / C145-2: when two holes are rejected, target the one without a queued
    /// same-kind replacement so the finish prompt remains actionable.
    func testProductSpec59FinishTargetsRejectedHoleWithoutPendingReplacement() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c145-target.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path.hasSuffix("/package") == true {
                proto.reply(200, try! JSONEncoder().encode(package))
            } else { proto.reply(404) }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let rejectedThree = LiveRoundEvent(eventId: "rejected-3", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 3, kind: .score, payload: ["strokes": .number(3)])
        let rejectedSeven = LiveRoundEvent(eventId: "rejected-7", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:01Z", hole: 7, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejectedThree); try store.quarantineEvent(rejectedThree, status: 422, reason: "bad 3")
        try store.appendEvent(rejectedSeven); try store.quarantineEvent(rejectedSeven, status: 422, reason: "bad 7")
        try store.appendEvent(LiveRoundEvent(eventId: "replacement-3", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:02Z", hole: 3, kind: .score, payload: ["strokes": .number(5)]))
        let blocked = await model.finishActiveRound()
        XCTAssertFalse(blocked)
        XCTAssertEqual(model.liveRoundState?.activeHole, 7)
        XCTAssertTrue(model.finishErrorMessage?.contains("第 7 洞") == true)
    }

    /// Product spec 5.9 / C145-5: a rejected hole removed by a nine-hole edit is explained instead
    /// of passing an invalid cursor to setActiveHole.
    func testProductSpec59RemovedRejectedHoleShowsRecoveryInstruction() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c145-removed.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path.hasSuffix("/package") == true {
                proto.reply(200, try! JSONEncoder().encode(package))
            } else if proto.request.url?.path.hasSuffix("/events") == true {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                proto.reply(200, try! JSONEncoder().encode(SyncResult(accepted: batch.events.count,
                    duplicate: false, acceptedEventIds: batch.events.map(\.eventId))))
            } else if proto.request.url?.path.hasSuffix("/finish") == true {
                proto.reply(200)
            } else { proto.reply(404) }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let rejected = LiveRoundEvent(eventId: "rejected-10", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 10, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejected)
        try store.appendSyncMarker(roundId: package.roundId, timestamp: "2026-01-01T00:00:01Z",
            result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
        try store.quarantineEvent(rejected, status: 422, reason: "removed")
        let blocked = await model.finishActiveRound()
        XCTAssertFalse(blocked)
        XCTAssertTrue(model.finishErrorMessage?.contains("第 10 洞已从当前球局移除") == true)
        XCTAssertEqual(model.liveRoundState?.activeHole, 1)
        XCTAssertEqual(model.deferredFinishRecovery?.hole, 10)
        XCTAssertEqual(model.deferredFinishRecovery?.holeAvailable, false)
        XCTAssertTrue(model.syncStatus.contains("该洞成绩不会上传"))
        try store.appendEvent(LiveRoundEvent(eventId: "live-late-tail", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 1, kind: .club, payload: ["clubName": .string("7I")]))
        XCTAssertTrue(model.discardRemovedDeferredFinishRejection())
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertTrue(try store.loadPendingRoundFinishes().isEmpty)
        XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertNil(model.deferredFinishRecovery)
    }

    /// Product spec 5.9 / C145-3: an already queued replacement reports one network-aware state
    /// and starts the uploader; the old slash-joined copy is not a lasting UI state.
    func testProductSpec59BlockedFinishReportsWaitingForSyncWhenOffline() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c145-status.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            if proto.request.url?.path.hasSuffix("/package") == true {
                proto.reply(200, try! JSONEncoder().encode(package))
            } else { proto.reply(404) }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let rejected = LiveRoundEvent(eventId: "rejected-status", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejected); try store.quarantineEvent(rejected, status: 422, reason: "bad score")
        try store.appendEvent(LiveRoundEvent(eventId: "replacement-status", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:01Z", hole: 1, kind: .score, payload: ["strokes": .number(5)]))
        let blocked = await model.finishActiveRound()
        XCTAssertFalse(blocked)
        XCTAssertEqual(model.finishErrorMessage, "第 1 洞成绩被服务器拒绝（bad score），等待联网后再结束球局")
        XCTAssertFalse(model.finishErrorMessage?.contains("/") == true)
        XCTAssertEqual(model.syncStatus, "结束已暂停 · 第 1 洞成绩被服务器拒绝（bad score），等待联网后再结束球局")
        await model.waitForPendingReplacementSyncForTesting()
        XCTAssertTrue(model.syncStatus.contains("第 1 洞成绩被服务器拒绝"))
    }

    /// Product spec 5.9 / C145-3: an online blocked finish actively uploads its queued replacement;
    /// the test waits on the model's explicit sync hook instead of racing a Task scheduled by UI code.
    func testProductSpec59BlockedFinishUploadsPendingReplacementOnline() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let observer = C33NetworkObserver()
        let client = SyncClient(baseURL: URL(string: "https://c145-sync.example.test")!, session: session)
        let model = LiveRoundAppModel(
            offlineStore: store, apiBaseURL: client.baseURL, watchBridge: nil,
            garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: observer
        )
        let package = try c33Package()
        let lock = NSLock()
        var uploadedIDs: [String] = []
        let sent = expectation(description: "replacement upload held")
        let gate = FinishRequestGate()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                lock.lock(); uploadedIDs.append(contentsOf: batch.events.map(\.eventId)); lock.unlock()
                if gate.hold(proto, batch: batch) { sent.fulfill() }
                return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        model.setNetworkStateForTesting(SpeculativeNetworkState(
            isSatisfied: true, isExpensive: false, isConstrained: false
        ))
        let rejected = LiveRoundEvent(eventId: "online-rejected", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejected)
        try store.quarantineEvent(rejected, status: 422, reason: "bad score")
        try store.appendEvent(LiveRoundEvent(eventId: "online-replacement", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:01Z", hole: 1, kind: .score, payload: ["strokes": .number(5)]))
        let blocked = await model.finishActiveRound()
        XCTAssertFalse(blocked)
        await fulfillment(of: [sent], timeout: 10)
        XCTAssertTrue(model.syncStatus.contains("结束已暂停"))
        XCTAssertTrue(model.syncStatus.contains("第 1 洞成绩被服务器拒绝"))
        gate.accept()
        await model.waitForPendingReplacementSyncForTesting()
        lock.lock(); let uploaded = uploadedIDs; lock.unlock()
        XCTAssertTrue(uploaded.contains("online-replacement"))
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
    }

    /// Product spec 5.9 / C143-2: a deferred rejection from round A must coexist with an active
    /// round B. Recovery must refuse to switch the durable pointer or erase B's score draft.
    func testProductSpec59DeferredRecoveryDoesNotOverwriteAnotherLiveRound() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c143-two-rounds.example.test")!, session: session)
        let bridge = WatchEventBridge(offlineStore: store, autoActivate: false)
        let model = LiveRoundAppModel(offlineStore: store, apiBaseURL: client.baseURL,
            watchBridge: bridge, garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: nil)
        let packageA = try c33Package()
        let packageB = packageA.rebasedForOfflineStart(roundId: "c143-round-b")
        let lock = NSLock()
        var finishRequests = 0
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") {
                let requested = c33Query(proto.request, "round_id")
                proto.reply(200, try! JSONEncoder().encode(requested == packageB.roundId ? packageB : packageA))
                return
            }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                if batch.events.contains(where: { $0.hole == 3 }) {
                    proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"hole 3 rejected"}}"#.utf8))
                } else {
                    proto.reply(200, try! JSONEncoder().encode(SyncResult(
                        accepted: batch.events.count, duplicate: false,
                        acceptedEventIds: batch.events.map(\.eventId)
                    )))
                }
                return
            }
            if path.hasSuffix("/finish") {
                lock.lock(); finishRequests += 1; lock.unlock()
                proto.reply(200); return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }

        await model.prepareCourseRound(roundId: packageA.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "round-a-rejected", roundId: packageA.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 3, kind: .score, payload: ["strokes": .number(3)]))
        let sealed = await model.finishActiveRound()
        XCTAssertTrue(sealed)
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(model.deferredFinishRecovery?.roundId, packageA.roundId)

        // Seed B's durable pointer and draft before entering it. This models a player starting the
        // next round while A's deferred finish is still awaiting recovery.
        try store.saveRoundPackage(packageB)
        try store.saveRoundStart(roundId: packageB.roundId, startHole: 2)
        try store.saveLiveScoreDraft(roundId: packageB.roundId, draft: LiveScoreDraft(
            hole: 2, par: 4, phoneShotCount: 2
        ))
        await model.prepareCourseRound(roundId: packageB.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let beforePackage = try XCTUnwrap(try store.loadRoundPackage(roundId: packageB.roundId))
        let beforeDraft = try XCTUnwrap(try store.loadLiveScoreDraft(roundId: packageB.roundId))
        let beforeState = try XCTUnwrap(model.liveRoundState)
        XCTAssertEqual(beforeState.roundId, packageB.roundId)
        XCTAssertEqual(beforeState.activeHole, 2)

        let beforePointer = try XCTUnwrap(try store.loadCurrentRoundPackage())
        let beforeWatchContext = NSDictionary(dictionary: bridge.pendingApplicationContext())
        XCTAssertEqual((bridge.pendingApplicationContext()["roundSeed"] as? [String: Any])?["roundId"] as? String,
                       packageB.roundId)
        XCTAssertFalse(model.resumeDeferredFinishForEditing())
        XCTAssertEqual(try store.loadCurrentRoundPackage(), beforePointer)
        XCTAssertEqual(NSDictionary(dictionary: bridge.pendingApplicationContext()), beforeWatchContext)
        XCTAssertEqual(model.liveRoundState, beforeState)
        XCTAssertEqual(try store.loadRoundPackage(roundId: packageB.roundId), beforePackage)
        XCTAssertEqual(try store.loadLiveScoreDraft(roundId: packageB.roundId), beforeDraft)
        XCTAssertEqual(model.package?.roundId, packageB.roundId)
        XCTAssertTrue(model.syncStatus.contains("另一场进行中的球局"))
        // B never tried to finish: A's refused resume must not become B's finish-sheet error.
        XCTAssertNil(model.finishErrorMessage)
        lock.lock(); let finishes = finishRequests; lock.unlock()
        XCTAssertEqual(finishes, 0)
    }

    /// Product spec 5.9 / C145-5a: removing a rejected hole must leave a later Watch event in the
    /// append-only tail so the deferred finish can upload it before completing.
    func testProductSpec59DiscardRemovedRecoveryUploadsLatePendingEvent() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c145-discard-tail.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        let other = try XCTUnwrap(package.composingSecondLoop(
            RoundLoopEntry(globalId: 32850, half: "all"), from: package, roundId: "other-eighteen-hole-round"
        ))
        let lock = NSLock()
        var uploadedIDs: [String] = []
        var finishRequests = 0
        var holdLiveReplay = false
        let liveReplayStarted = expectation(description: "B follow-up replay held during A recovery")
        let liveReplayGate = FinishRequestGate()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") {
                let requested = c33Query(proto.request, "round_id")
                proto.reply(200, try! JSONEncoder().encode(requested == other.roundId ? other : package))
                return
            }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                lock.lock(); uploadedIDs.append(contentsOf: batch.events.map(\.eventId)); lock.unlock()
                if batch.events.contains(where: { $0.hole == 10 }) {
                    proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"hole 10 removed"}}"#.utf8))
                } else {
                    proto.reply(200, try! JSONEncoder().encode(SyncResult(
                        accepted: batch.events.count, duplicate: false,
                        acceptedEventIds: batch.events.map(\.eventId)
                    )))
                }
                return
            }
            if path.hasSuffix("/events/replay"), path.contains("/\(other.roundId)/") {
                lock.lock(); let shouldHold = holdLiveReplay; holdLiveReplay = false; lock.unlock()
                if shouldHold {
                    if liveReplayGate.hold(proto) { liveReplayStarted.fulfill() }
                    return
                }
            }
            if path.hasSuffix("/finish") {
                lock.lock(); finishRequests += 1; lock.unlock()
                proto.reply(200); return
            }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }

        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "removed-hole-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 10, kind: .score, payload: ["strokes": .number(3)]))
        let sealed = await model.finishActiveRound()
        XCTAssertTrue(sealed)
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(model.deferredFinishRecovery?.hole, 10)
        XCTAssertEqual(model.deferredFinishRecovery?.holeAvailable, false)
        // B has hole 10, while sealed A no longer does. Deferred status must consult A's table,
        // and discarding A must not replace B or reinterpret A's removed hole as playable.
        await model.prepareCourseRound(roundId: other.roundId, teeBox: "blue", loops: [
            .init(globalId: 32850, half: "all"), .init(globalId: 32850, half: "all")
        ])
        XCTAssertEqual(model.package?.roundId, other.roundId)
        XCTAssertTrue(model.package?.holes.contains(where: { $0.number == 10 }) == true)
        // The same pass may subsequently publish B's ordinary sync status. Observe the deferred
        // rejection status itself, rather than assuming the shared status line still belongs to A.
        var retryStatuses: [String] = []
        let statusSubscription = model.$syncStatus.sink { retryStatuses.append($0) }
        defer { statusSubscription.cancel() }
        lock.lock(); holdLiveReplay = true; lock.unlock()
        model.syncOnForeground()
        await fulfillment(of: [liveReplayStarted], timeout: 10)
        // The owner must remain visible while it awaits B's follow-up. Otherwise discard below
        // can see a nil handle, and the test's await can return before A's retry has even started.
        XCTAssertNotNil(model.deferredRoundFinishTaskForTesting())
        XCTAssertEqual(model.deferredFinishRecovery?.holeAvailable, false)
        let rejectionStatus = try XCTUnwrap(retryStatuses.last(where: { $0.contains("结束已暂停") }))
        XCTAssertTrue(rejectionStatus.contains("该洞成绩不会上传"))
        XCTAssertFalse(rejectionStatus.contains("请恢复该九洞"))

        try store.appendEvent(LiveRoundEvent(eventId: "late-watch-tail", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 1, kind: .club,
            payload: ["clubName": .string("7I")]))
        XCTAssertTrue(model.discardRemovedDeferredFinishRejection())
        liveReplayGate.reply(404, Data())
        await model.waitForDeferredRoundFinishesForTesting()
        lock.lock(); let uploaded = uploadedIDs; let finishes = finishRequests; lock.unlock()
        XCTAssertTrue(uploaded.contains("late-watch-tail"))
        XCTAssertEqual(finishes, 1)
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
        XCTAssertTrue(try store.loadPendingRoundFinishes().isEmpty)
        XCTAssertTrue(try store.loadPendingEvents(roundId: package.roundId).isEmpty)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertNil(model.deferredFinishRecovery)
        XCTAssertEqual(model.liveRoundState?.roundId, other.roundId)
        XCTAssertEqual(try store.loadCurrentRoundPackage()?.roundId, other.roundId)
    }

    private func assertReplacementScoringEventAllowsFinish(
        kind: LiveRoundEventKind, payload: [String: JSONValue], replacement: [String: JSONValue]
    ) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c137-replace.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                var strokes = 5
                var putts = 2
                var penalties = 2
                for event in batch.events where event.hole == 1 {
                    switch event.kind {
                    case .score: if case let .number(value) = event.payload["strokes"] { strokes = Int(value) }
                    case .putt: if case let .number(value) = event.payload["putts"] { putts = Int(value) }
                    case .penalty: if case let .number(value) = event.payload["penalties"] { penalties = Int(value) }
                    default: break
                    }
                }
                if strokes < putts + penalties + 1 {
                    proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"score fact rejected"}}"#.utf8))
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
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        let badPayload: [String: JSONValue]
        switch kind {
        case .score: badPayload = ["strokes": .number(3)]
        case .putt: badPayload = ["putts": .number(3)]
        case .penalty: badPayload = ["penalties": .number(3)]
        default: badPayload = payload
        }
        try store.appendEvent(LiveRoundEvent(eventId: "accepted-event", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: kind, payload: badPayload))
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).count, 1)
        let blocked = await model.finishActiveRound()
        XCTAssertFalse(blocked)
        try store.appendEvent(LiveRoundEvent(eventId: "bad-event", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 1, kind: kind, payload: replacement))
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
                var strokes = 5
                var putts = 2
                var penalties = 2
                let scoringHole = batch.events.first?.hole ?? 1
                for event in batch.events where event.hole == scoringHole {
                    switch event.kind {
                    case .score: if case let .number(value) = event.payload["strokes"] { strokes = Int(value) }
                    case .putt: if case let .number(value) = event.payload["putts"] { putts = Int(value) }
                    case .penalty: if case let .number(value) = event.payload["penalties"] { penalties = Int(value) }
                    default: break
                    }
                }
                if strokes < putts + penalties + 1 {
                    let reason = "hole \(scoringHole): total \(strokes) is less than putts \(putts) + penalties \(penalties) + 1"
                    proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"\#(reason)"}}"#.utf8))
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
        try store.appendEvent(LiveRoundEvent(eventId: "accepted-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 3, kind: .score,
            payload: ["strokes": .number(3)]))
        try store.appendEvent(LiveRoundEvent(eventId: "later-other-hole", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:01Z", hole: 4, kind: .club,
            payload: ["clubName": .string("7I")]))
        let sealed = await model.finishActiveRound()
        XCTAssertTrue(sealed)
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).map { $0.event.eventId }, ["accepted-score"])
        XCTAssertEqual(model.deferredFinishRecovery?.hole, 3)
        XCTAssertTrue(model.deferredFinishRecovery?.prompt.contains("第 3 洞成绩被服务器拒绝") == true)
        finishLock.lock(); let blockedFinishes = finishRequests; finishLock.unlock()
        // The server round must stay open until the rejected hole is re-entered.
        XCTAssertEqual(blockedFinishes, 0)
        XCTAssertEqual(try store.loadPendingRoundFinishes().map(\.roundId), [package.roundId])

        XCTAssertTrue(model.resumeDeferredFinishForEditing())
        XCTAssertEqual(model.liveRoundState?.activeHole, 3)
        XCTAssertEqual(model.pendingLiveHole, 3)
        XCTAssertNil(model.deferredFinishRecovery)
        XCTAssertTrue(try store.loadPendingRoundFinishes().isEmpty)

        try store.appendEvent(LiveRoundEvent(eventId: "bad-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:01:00Z", hole: 3, kind: .score,
            payload: ["strokes": .number(5)]))
        await model.syncPendingEvents()
        let resealed = await model.finishActiveRound()
        XCTAssertTrue(resealed)
        await model.waitForDeferredRoundFinishesForTesting()
        finishLock.lock(); let finishes = finishRequests; finishLock.unlock()
        XCTAssertEqual(finishes, 1)
        XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
        XCTAssertTrue(try store.loadPendingRoundFinishes().isEmpty)
        XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
        XCTAssertNil(model.deferredFinishRecovery)
    }

    /// Product spec 5.9 / C143-4: transport failure alone keeps the sealed round retryable and
    /// hidden; after transport recovers, a real server rejection creates the recovery entry.
    func testProductSpec59DeferredFinishRecoveryRequiresServerRejection() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c143-recovery.example.test")!, session: session)
        let model = c33Model(store, client)
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        let lock = NSLock()
        var recoveredTransport = false
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, packageData); return }
            if path.hasSuffix("/events") {
                lock.lock(); let recovered = recoveredTransport; lock.unlock()
                if !recovered { proto.reply(500); return }
                proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"hole 3: total 3 is less than putts 2 + penalties 2 + 1"}}"#.utf8))
                return
            }
            if path.hasSuffix("/finish") { proto.reply(200); return }
            proto.reply(404)
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "transport-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 3, kind: .score,
            payload: ["strokes": .number(3)]))
        let sealed = await model.finishActiveRound()
        XCTAssertTrue(sealed)
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertNil(model.deferredFinishRecovery)
        XCTAssertTrue(try store.loadPendingRoundFinishes().contains { $0.roundId == package.roundId })

        lock.lock(); recoveredTransport = true; lock.unlock()
        model.syncOnForeground()
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(model.deferredFinishRecovery?.hole, 3)
        XCTAssertTrue(model.deferredFinishRecovery?.prompt.contains("第 3 洞成绩被服务器拒绝") == true)
    }

    /// Product spec 5.9: a successful retry removes the rejection card at completion, without
    /// first reopening/discarding the card (those actions would hide a missing success cleanup).
    func testProductSpec59DeferredFinishSuccessClearsRecoveryCard() async throws {
        try await withDeferredRecovery { model, store, package, _ in
            // The accepted re-entry resolves the quarantine inside the retry pass itself.
            try store.appendEvent(LiveRoundEvent(eventId: "fixed-score", roundId: package.roundId,
                timestamp: "2026-01-01T00:01:00Z", hole: 3, kind: .score,
                payload: ["strokes": .number(5)]))
            XCTAssertNotNil(model.deferredFinishRecovery)
            model.syncOnForeground()
            await model.waitForDeferredRoundFinishesForTesting()
            XCTAssertNil(model.deferredFinishRecovery)
            XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
            XCTAssertTrue(try store.loadPendingRoundFinishes().isEmpty)
        }
    }

    /// Product spec 5.9: a failed resume preflight leaves the deferred uploader (including other
    /// sealed rounds) alive. The request is released explicitly, never by a sleep or timeout.
    func testProductSpec59RemovedHoleResumeLeavesDeferredTaskRunning() async throws {
        try await withDeferredRecovery(hole: 10) { model, store, package, _ in
            let other = package.rebasedForOfflineStart(roundId: "other-sealed-round")
            try store.sealRoundForDeferredFinish(package: other, metadata: MobileRoundFinishMetadata(
                courseName: other.course.venueDisplayName, holePars: other.holes.map(\.par),
                holesCompleted: 0, courseGlobalId: other.course.globalId))
            try store.appendEvent(LiveRoundEvent(eventId: "held-tail", roundId: package.roundId,
                timestamp: "2026-01-01T00:01:00Z", hole: 1, kind: .club,
                payload: ["clubName": .string("7I")]))
            let sent = self.expectation(description: "deferred tail in flight")
            let gate = FinishRequestGate()
            C33URLProtocol.setHandlers(onStart: { proto in
                let path = proto.request.url?.path ?? ""
                if path.hasSuffix("/events") {
                    let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                    if batch.events.contains(where: { $0.eventId == "held-tail" }) {
                        if gate.hold(proto, batch: batch) { sent.fulfill() }
                        return
                    }
                }
                if path.hasSuffix("/finish") { proto.reply(200) } else { proto.reply(404) }
            })
            model.syncOnForeground()
            let task = try XCTUnwrap(model.deferredRoundFinishTaskForTesting())
            await self.fulfillment(of: [sent], timeout: 10)
            XCTAssertFalse(model.resumeDeferredFinishForEditing())
            XCTAssertFalse(task.isCancelled, "a false preflight must not cancel another round's uploader")
            if !task.isCancelled { gate.accept() }
            await task.value
            XCTAssertFalse(try store.loadPendingRoundFinishes().contains { $0.roundId == other.roundId })
            XCTAssertTrue(try store.isRoundPendingFinish(package.roundId))
        }
    }

    /// Product spec 5.9: resuming during an upload cancels the old pass; its late catch must not
    /// overwrite the edit instruction or discard a round that is now being edited.
    func testProductSpec59ResumeCancelsStaleFinishAndKeepsEditStatus() async throws {
        try await withDeferredRecovery { model, store, package, _ in
            try store.appendEvent(LiveRoundEvent(eventId: "held-tail", roundId: package.roundId,
                timestamp: "2026-01-01T00:01:00Z", hole: 4, kind: .club,
                payload: ["clubName": .string("7I")]))
            let sent = self.expectation(description: "old deferred upload held")
            let gate = FinishRequestGate()
            C33URLProtocol.setHandlers(onStart: { proto in
                if proto.request.url?.path.hasSuffix("/events") == true {
                    let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                    if gate.hold(proto, batch: batch) { sent.fulfill() }
                } else { proto.reply(404) }
            })
            model.syncOnForeground()
            let oldTask = try XCTUnwrap(model.deferredRoundFinishTaskForTesting())
            await self.fulfillment(of: [sent], timeout: 10)
            XCTAssertTrue(model.resumeDeferredFinishForEditing())
            XCTAssertTrue(oldTask.isCancelled)
            // If cancellation is removed by a mutant, release the network request as well so the
            // test fails its assertions instead of hanging while waiting for the stale task.
            if !oldTask.isCancelled { gate.accept() }
            await oldTask.value
            XCTAssertEqual(model.syncStatus, "已恢复本场 · 请重录第 3 洞")
            XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
            XCTAssertEqual(model.liveRoundState?.activeHole, 3)
            XCTAssertNotNil(try store.loadRoundPackage(roundId: package.roundId))
            XCTAssertFalse(try store.isRoundPendingFinish(package.roundId))
        }
    }

    /// Product spec 5.9: a Watch start awaiting its course package already owns the next round;
    /// recovery must preserve both its pending identity and the seed/pointer.
    func testProductSpec59DeferredRecoveryDoesNotOverwritePendingWatchRound() async throws {
        try await withDeferredRecovery { model, store, package, bridge in
            let other = package.rebasedForOfflineStart(roundId: "pending-watch-round")
            // A cold Watch course fetch must really suspend; the prior round cached its template.
            try store.invalidateCourseTemplate(for: package)
            let seed = bridge.makeWatchRoundSeedPayload(package: other, activeHole: 2)
            bridge.sendRoundSeedToWatch(seed)
            let beforeWatch = NSDictionary(dictionary: bridge.pendingApplicationContext())
            let beforePointer = try store.loadCurrentRoundPackage()
            let sent = self.expectation(description: "Watch package in flight")
            let gate = FinishRequestGate()
            C33URLProtocol.setHandlers(onStart: { proto in
                if proto.request.url?.path.hasSuffix("/package") == true {
                    if gate.hold(proto) { sent.fulfill() }
                } else { proto.reply(404) }
            })
            let start = WatchRoundStartPayload(roundId: other.roundId,
                courseName: other.course.venueDisplayName, teeBox: "blue", loopKey: other.loopKey,
                globalId: other.course.globalId, activeHole: 2, holes: seed.holes)
            let watchTask = Task { @MainActor in await model.handleWatchRoundStart(start) }
            await self.fulfillment(of: [sent], timeout: 10)
            XCTAssertEqual(model.pendingWatchRoundStart?.roundId, other.roundId)
            XCTAssertFalse(model.resumeDeferredFinishForEditing())
            XCTAssertEqual(model.pendingWatchRoundStart, start)
            XCTAssertEqual(try store.loadCurrentRoundPackage(), beforePointer)
            XCTAssertEqual(NSDictionary(dictionary: bridge.pendingApplicationContext()), beforeWatch)
            XCTAssertTrue(try store.isRoundPendingFinish(package.roundId))
            XCTAssertTrue(model.syncStatus.contains("另一场进行中的球局"))
            XCTAssertNil(model.finishErrorMessage)
            gate.reply(200, try JSONEncoder().encode(other))
            await watchTask.value
        }
    }

    /// J5.9: abandoning the live round removes its recovery too, so the Hub can start again.
    func testProductSpec59AbandoningLiveRoundClearsRemovedHoleRecovery() async throws {
        try await withLiveRemovedRejection { model, store, package in
            model.discardActiveRound()
            XCTAssertNil(model.liveRoundState)
            XCTAssertNil(model.liveFinishRecovery)
            XCTAssertNil(model.deferredFinishRecovery, "an abandoned round must not leave a Hub recovery")
            XCTAssertNil(model.sealedFinishRecovery)
            XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
            XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
            let home = self.recoveryHome(model)
            XCTAssertTrue(home.showsNewRoundPlayCard, "abandon must restore the Hub start entry")
            XCTAssertNil(home.deferredFinishRecovery)
            XCTAssertNil(home.liveFinishRecovery)
            XCTAssertNil(home.removedFinishRejectionAction)
        }
    }

    /// J5.9: nine holes plus a second nine restores round hole 10. A stale discard cannot delete it.
    func testProductSpec59RestoringSecondLoopPreservesRejectedScore() async throws {
        try await withLiveRemovedRejection { model, store, package in
            let action = try XCTUnwrap(self.recoveryHome(model).removedFinishRejectionAction)
            await model.setSecondLoop(RoundLoopEntry(globalId: 32850, half: "all"), roundId: package.roundId)
            XCTAssertEqual(model.package?.holes.count, 18)
            XCTAssertTrue(model.package?.holes.contains { $0.number == 10 } == true)
            XCTAssertNil(model.liveFinishRecovery, "a restored hole must no longer offer removed-hole discard")
            let blocked = await model.finishActiveRound()
            XCTAssertFalse(blocked)
            XCTAssertTrue(model.finishErrorMessage?.contains("请重新录入") == true)
            XCTAssertNil(self.recoveryHome(model).removedFinishRejectionAction,
                         "the finish sheet must show the re-entry instruction rather than the removed-hole card")
            XCTAssertFalse(action.discard(action.recovery.roundId, action.recovery.hole))
            XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).map(\.event.eventId),
                           ["live-rejected-10"])
            XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
            XCTAssertFalse(try store.isRoundPendingFinish(package.roundId))
        }
    }

    /// J5.9: recovery is additional Hub information; it never removes the route back to a live game.
    func testProductSpec59HubKeepsLiveEntryAlongsideRemovedHoleRecovery() async throws {
        try await withLiveRemovedRejection { model, _, package in
            let home = self.recoveryHome(model)
            XCTAssertTrue(home.showsInProgressPlayCard, "the live HubRoute.hole card must still render")
            let action = try XCTUnwrap(home.removedFinishRejectionAction)
            XCTAssertEqual(action.recovery.roundId, package.roundId)
            XCTAssertEqual(action.recovery.hole, 10)
            XCTAssertFalse(action.recovery.holeAvailable)
        }
    }

    /// J5.9: the same model-bound action supplied to the live finish sheet can discard and seal.
    func testProductSpec59LiveFinishRecoveryActionSealsOnlyItsRound() async throws {
        try await withLiveRemovedRejection { model, store, package in
            let action = try XCTUnwrap(self.recoveryHome(model).removedFinishRejectionAction)
            XCTAssertTrue(action.discard(action.recovery.roundId, action.recovery.hole))
            XCTAssertNil(model.liveRoundState)
            XCTAssertNil(model.liveFinishRecovery, "sealing must remove the live-only affordance immediately")
            await model.waitForDeferredRoundFinishesForTesting()
            XCTAssertTrue(try store.loadPendingRoundFinishes().isEmpty)
            XCTAssertNil(try store.loadRoundPackage(roundId: package.roundId))
            XCTAssertNil(model.deferredFinishRecovery)
        }
    }

    /// J5.9: discard is tied to the displayed round and hole, not whichever recovery is current.
    func testProductSpec59StaleDiscardIdentityLeavesRejectedFactsUntouched() async throws {
        try await withLiveRemovedRejection { model, store, package in
            XCTAssertFalse(model.discardRemovedDeferredFinishRejection(roundId: "other-round", hole: 10))
            XCTAssertFalse(model.discardRemovedDeferredFinishRejection(roundId: package.roundId, hole: 11))
            XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).map(\.event.eventId),
                           ["live-rejected-10"])
            XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
        }
    }

    /// J5.9: ordinary score sync must preserve an unresolved finish's actionable status.
    func testProductSpec59OrdinarySyncPreservesPausedFinishInstruction() async throws {
        try await withLiveRemovedRejection { model, _, _ in
            await model.syncPendingEvents()
            XCTAssertTrue(model.syncStatus.hasPrefix("结束已暂停 · "))
            XCTAssertTrue(model.syncStatus.contains("第 10 洞"))
            XCTAssertTrue(model.syncStatus.contains("该洞成绩不会上传"))
        }
    }

    /// J5.9: a sealed A and a live B own separate recovery facts, including after A's retry/B sync.
    func testProductSpec59SealedAndLiveRecoveriesRemainIndependent() async throws {
        try await withDeferredRecovery(hole: 10) { model, store, packageA, _ in
            let packageB = packageA.rebasedForOfflineStart(roundId: "live-recovery-b")
            C33URLProtocol.setHandlers(onStart: { proto in
                if proto.request.url?.path.hasSuffix("/package") == true {
                    proto.reply(200, try! JSONEncoder().encode(packageB))
                } else { proto.reply(404) }
            })
            try store.saveRoundPackage(packageB)
            try store.saveRoundStart(roundId: packageB.roundId, startHole: 1)
            await model.prepareCourseRound(roundId: packageB.roundId, teeBox: "blue", loops: packageB.loopEntries)
            await model.stopRoundBackgroundWorkForTesting()
            let rejected = LiveRoundEvent(eventId: "b-rejected-11", roundId: packageB.roundId,
                timestamp: "2026-01-01T00:02:00Z", hole: 11, kind: .score, payload: ["strokes": .number(3)])
            try store.appendEvent(rejected)
            try store.appendSyncMarker(roundId: packageB.roundId, timestamp: "2026-01-01T00:02:01Z",
                result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
            try store.quarantineEvent(rejected, status: 422, reason: "removed B hole")
            let blocked = await model.finishActiveRound()
            XCTAssertFalse(blocked)
            XCTAssertEqual(model.liveFinishRecovery?.roundId, packageB.roundId)
            XCTAssertEqual(model.sealedFinishRecovery?.roundId, packageA.roundId)
            model.syncOnForeground()
            await model.waitForDeferredRoundFinishesForTesting()
            XCTAssertEqual(model.liveFinishRecovery?.hole, 11)
            XCTAssertEqual(model.sealedFinishRecovery?.hole, 10)
            XCTAssertTrue(model.syncStatus.hasPrefix("结束已暂停 · "))
            XCTAssertTrue(model.syncStatus.contains("第 11 洞"), "B follow-up must preserve B's rejected-hole instruction")
            // A now has an unacknowledged tail. Its failing HTTP upload overwrites syncStatus
            // before B's follow-up; B's durable quarantine/finish error must still take priority.
            try store.appendEvent(LiveRoundEvent(eventId: "a-late-tail", roundId: packageA.roundId,
                timestamp: "2026-01-01T00:03:00Z", hole: 1, kind: .club,
                payload: ["clubName": .string("7I")]))
            model.syncOnForeground()
            await model.waitForDeferredRoundFinishesForTesting()
            XCTAssertTrue(model.syncStatus.hasPrefix("结束已暂停 · "))
            XCTAssertTrue(model.syncStatus.contains("第 11 洞"), "A transport failure must not shorten B's paused finish")
            XCTAssertEqual(try store.loadPendingEvents(roundId: packageA.roundId).map(\.eventId), ["a-late-tail"])
            let home = self.recoveryHome(model)
            XCTAssertTrue(home.showsInProgressPlayCard)
            XCTAssertEqual(home.removedFinishRejectionAction?.recovery.roundId, packageB.roundId)
            model.discardActiveRound()
            XCTAssertNil(model.liveFinishRecovery)
            XCTAssertEqual(model.sealedFinishRecovery?.roundId, packageA.roundId)
            XCTAssertTrue(try store.isRoundPendingFinish(packageA.roundId))
            XCTAssertEqual(try store.loadQuarantinedEvents(roundId: packageA.roundId).count, 1)
        }
    }

    /// J5.9 (N1): the Hub offers the live removed-hole discard only after this round's finish
    /// attempt. The finish sheet does not wait for it, and the next round starts unmarked.
    func testProductSpec59HubLiveRecoveryWaitsForThisRoundsFinishAttempt() async throws {
        try await withTwoLiveRounds { model, store, first, second in
            try await self.startRoundWithRemovedRejection(model, store, first)
            XCTAssertEqual(model.liveFinishRecovery?.hole, 10)
            var home = self.recoveryHome(model)
            XCTAssertNil(home.hubLiveFinishRecovery, "no finish attempt yet: the Hub must not offer to end the round")
            XCTAssertNotNil(home.removedFinishRejectionAction, "the finish sheet still explains the removed hole")
            XCTAssertTrue(home.showsInProgressPlayCard)

            let blocked = await model.finishActiveRound()
            XCTAssertFalse(blocked)
            home = self.recoveryHome(model)
            XCTAssertEqual(home.hubLiveFinishRecovery?.roundId, first.roundId)
            XCTAssertEqual(home.hubLiveFinishRecovery?.hole, 10)

            model.discardActiveRound()
            try await self.startRoundWithRemovedRejection(model, store, second)
            XCTAssertEqual(model.liveFinishRecovery?.roundId, second.roundId)
            home = self.recoveryHome(model)
            XCTAssertNil(home.hubLiveFinishRecovery, "the previous round's finish attempt must not mark this round")
            XCTAssertNotNil(home.removedFinishRejectionAction)
        }
    }

    /// J5.9 (N2): a paused finish belongs to its round. Abandoning it into the cached Hub and
    /// starting the next round must not label that round's ordinary rejection「结束已暂停」.
    func testProductSpec59NextRoundDoesNotInheritPausedFinish() async throws {
        try await withTwoLiveRounds { model, store, first, second in
            try await self.startRoundWithRemovedRejection(model, store, first)
            let blocked = await model.finishActiveRound()
            XCTAssertFalse(blocked)
            XCTAssertNotNil(model.finishErrorMessage)
            XCTAssertTrue(model.syncStatus.hasPrefix("结束已暂停 · "))
            // A cached Hub package sends abandon through activateHomePackage.
            try store.saveHomePackage(first.rebasedForOfflineStart(roundId: "finish-attempt-home"))
            XCTAssertNotNil(try store.loadHomePackage())
            model.discardActiveRound()
            XCTAssertNil(model.liveRoundState)
            XCTAssertNil(model.finishErrorMessage, "the abandoned round's finish error must not reach the next round")

            await model.prepareCourseRound(roundId: second.roundId, teeBox: "blue", loops: second.loopEntries)
            await model.stopRoundBackgroundWorkForTesting()
            XCTAssertEqual(model.liveRoundState?.roundId, second.roundId)
            // Hole 3 is still in play: an ordinary rejection, and this round was never finished.
            let rejected = LiveRoundEvent(eventId: "next-round-rejected-3", roundId: second.roundId,
                timestamp: "2026-01-01T00:05:00Z", hole: 3, kind: .score, payload: ["strokes": .number(3)])
            try store.appendEvent(rejected)
            try store.appendSyncMarker(roundId: second.roundId, timestamp: "2026-01-01T00:05:01Z",
                result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
            try store.quarantineEvent(rejected, status: 422, reason: "bad score")
            await model.syncPendingEvents()
            XCTAssertNil(model.finishErrorMessage)
            XCTAssertFalse(model.syncStatus.hasPrefix("结束已暂停"), model.syncStatus)
            XCTAssertTrue(model.syncStatus.contains("第 3 洞"), model.syncStatus)
        }
    }

    /// J5.9 (N2): restoring the second loop recomputes the paused finish text at once. Hole 10 is
    /// playable again, so the sheet asks for a re-entry instead of saying it will not upload.
    func testProductSpec59RestoredLoopRecomputesPausedFinishMessage() async throws {
        try await withLiveRemovedRejection { model, _, package in
            XCTAssertTrue(model.finishErrorMessage?.contains("第 10 洞已从当前球局移除") == true)
            await model.setSecondLoop(RoundLoopEntry(globalId: 32850, half: "all"), roundId: package.roundId)
            XCTAssertEqual(model.package?.holes.count, 18)
            let message = model.finishErrorMessage ?? "nil"
            XCTAssertFalse(message.contains("已从当前球局移除"), message)
            XCTAssertTrue(message.contains("第 10 洞"), message)
            XCTAssertTrue(message.contains("请重新录入"), message)
        }
    }

    /// J5.9 (N3): a delayed Watch start for the sealed round is the same round as its recovery
    /// card. The Hub shows that one card, not a pending Watch card beside it.
    func testProductSpec59PendingWatchStartForSealedRoundShowsOneCard() async throws {
        try await withDeferredRecovery { model, _, package, bridge in
            let seed = bridge.makeWatchRoundSeedPayload(package: package, activeHole: 3)
            let start = WatchRoundStartPayload(roundId: package.roundId,
                courseName: package.course.venueDisplayName, teeBox: "blue", loopKey: package.loopKey,
                globalId: package.course.globalId, activeHole: 3, holes: seed.holes)
            XCTAssertEqual(model.sealedFinishRecovery?.roundId, package.roundId)
            // Render a pending delivery already present in a Hub snapshot. The model now
            // acknowledges newly arriving sealed starts before any package fetch can suspend.
            let home = self.recoveryHome(model, pendingWatchRoundStart: start)
            XCTAssertFalse(home.showsPendingWatchPlayCard, "the sealed recovery card already stands for this round")
            XCTAssertFalse(home.showsNewRoundPlayCard)
            XCTAssertEqual(home.deferredFinishRecovery?.roundId, package.roundId)
        }
    }

    /// J5.9: a sealed A may write a paused status immediately before the live B follow-up.
    /// B has never tried to finish; its ordinary hole-3 rejection cannot inherit A's prefix.
    func testProductSpec59SealedStatusDoesNotMarkUnfinishedLiveRound() async throws {
        try await withDeferredRecovery { model, store, first, _ in
            let second = first.rebasedForOfflineStart(roundId: "ordinary-live-round")
            C33URLProtocol.setHandlers(onStart: { proto in
                if proto.request.url?.path.hasSuffix("/package") == true {
                    proto.reply(200, try! JSONEncoder().encode(second))
                } else { proto.reply(404) }
            })
            await model.prepareCourseRound(roundId: second.roundId, teeBox: "blue", loops: second.loopEntries)
            await model.stopRoundBackgroundWorkForTesting()
            XCTAssertEqual(model.liveRoundState?.roundId, second.roundId)
            XCTAssertNil(model.finishAttemptRoundId)
            let rejected = LiveRoundEvent(eventId: "ordinary-rejected-3", roundId: second.roundId,
                timestamp: "2026-01-01T00:05:00Z", hole: 3, kind: .score, payload: ["strokes": .number(3)])
            try store.appendEvent(rejected)
            try store.appendSyncMarker(roundId: second.roundId, timestamp: "2026-01-01T00:05:01Z",
                result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
            try store.quarantineEvent(rejected, status: 422, reason: "ordinary score")

            var statuses: [String] = []
            let subscription = model.$syncStatus.dropFirst().sink { statuses.append($0) }
            defer { subscription.cancel() }
            model.syncOnForeground()
            await model.waitForDeferredRoundFinishesForTesting()
            XCTAssertTrue(statuses.contains(where: { $0.hasPrefix("结束已暂停 · ") }),
                "sealed A must write its prefix before B's follow-up")
            XCTAssertEqual(model.sealedFinishRecovery?.roundId, first.roundId)
            XCTAssertFalse(model.syncStatus.hasPrefix("结束已暂停"), model.syncStatus)
            XCTAssertTrue(model.syncStatus.contains("第 3 洞"), model.syncStatus)
            XCTAssertNil(model.finishErrorMessage)
        }
    }

    /// J5.9 / J6.1: a Watch finish is this live round's finish attempt too. Hole 10 was
    /// removed by the nine-hole edit, so the Hub exposes it and a later sync stays paused.
    func testProductSpec59WatchFinishExposesRemovedHoleRecoveryAndKeepsPausedStatus() async throws {
        try await withTwoLiveRounds { model, store, first, _ in
            try await self.startRoundWithRemovedRejection(model, store, first)
            XCTAssertNil(self.recoveryHome(model).hubLiveFinishRecovery)
            model.handleWatchRoundClosure(WatchRoundClosurePayload(roundId: first.roundId, disposition: .finished))
            await model.waitForWatchRoundClosureReconciliationForTesting()
            XCTAssertEqual(self.recoveryHome(model).hubLiveFinishRecovery?.hole, 10)
            XCTAssertEqual(model.finishAttemptRoundId, first.roundId)
            await model.syncPendingEvents()
            XCTAssertTrue(model.syncStatus.hasPrefix("结束已暂停 · "), model.syncStatus)
            XCTAssertTrue(model.syncStatus.contains("第 10 洞"), model.syncStatus)
        }
    }

    /// J5.9: changing the playable table without a finish attempt must not open a finish error.
    func testProductSpec59LoopEditsWithoutFinishAttemptKeepFinishErrorNil() async throws {
        try await withTwoLiveRounds { model, store, first, _ in
            try await self.startRoundWithRemovedRejection(model, store, first)
            XCTAssertNil(model.finishAttemptRoundId)
            XCTAssertNil(model.finishErrorMessage, "dropping the second nine is not a finish attempt")
            await model.setSecondLoop(RoundLoopEntry(globalId: 32850, half: "all"), roundId: first.roundId)
            XCTAssertEqual(model.package?.holes.count, 18)
            XCTAssertNil(model.finishErrorMessage, "restoring it is not a finish attempt either")
        }
    }

    /// J5.9: with two removed rejections, a pending replacement for 10 makes 11 actionable.
    /// Merely changing the live cursor must refresh the card, with no package/quarantine write.
    func testProductSpec59LiveCursorRefreshesPreferredRemovedRejectionAfterPendingAppend() async throws {
        try await withTwoLiveRounds { model, store, first, _ in
            try await self.startRoundWithRemovedRejection(model, store, first)
            let other = LiveRoundEvent(eventId: "rejected-11", roundId: first.roundId,
                timestamp: "2026-01-01T00:01:00Z", hole: 11, kind: .score, payload: ["strokes": .number(3)])
            try store.appendEvent(other)
            try store.appendSyncMarker(roundId: first.roundId, timestamp: "2026-01-01T00:01:01Z",
                result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [other.eventId]))
            try store.quarantineEvent(other, status: 422, reason: "second removed score")
            XCTAssertEqual(try store.loadQuarantinedEvents(roundId: first.roundId).count, 2)
            XCTAssertEqual(model.liveFinishRecovery?.hole, 10)
            let holes = model.package?.holes.map(\.number)
            try store.appendEvent(LiveRoundEvent(eventId: "replacement-10", roundId: first.roundId,
                timestamp: "2026-01-01T00:02:00Z", hole: 10, kind: .score, payload: ["strokes": .number(5)]))
            XCTAssertEqual(model.liveFinishRecovery?.hole, 10, "append alone does not publish a live snapshot")
            model.setActiveHole(2)
            XCTAssertEqual(model.liveRoundState?.activeHole, 2)
            XCTAssertEqual(model.package?.holes.map(\.number), holes)
            XCTAssertEqual(model.liveFinishRecovery?.hole, 11, "11 still needs input; 10 already has a pending replacement")
        }
    }

    /// J5.9: accepting a same-hole replacement resolves the paused finish error immediately,
    /// without another Save & End tap. The player's live round remains open.
    func testProductSpec59AcceptedReentryClearsLiveFinishErrorWithoutAnotherFinish() async throws {
        try await withTwoLiveRounds { model, store, first, _ in
            await model.prepareCourseRound(roundId: first.roundId, teeBox: "blue", loops: first.loopEntries)
            await model.stopRoundBackgroundWorkForTesting()
            let rejected = LiveRoundEvent(eventId: "live-rejected-3", roundId: first.roundId,
                timestamp: "2026-01-01T00:00:00Z", hole: 3, kind: .score, payload: ["strokes": .number(3)])
            try store.appendEvent(rejected)
            try store.appendSyncMarker(roundId: first.roundId, timestamp: "2026-01-01T00:00:01Z",
                result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
            try store.quarantineEvent(rejected, status: 422, reason: "bad score")
            let blocked = await model.finishActiveRound()
            XCTAssertFalse(blocked)
            XCTAssertNotNil(model.finishErrorMessage)
            try store.appendEvent(LiveRoundEvent(eventId: "live-reentry-3", roundId: first.roundId,
                timestamp: "2026-01-01T00:01:00Z", hole: 3, kind: .score, payload: ["strokes": .number(5)]))
            let stillBlocked = await model.finishActiveRound()
            XCTAssertFalse(stillBlocked)
            XCTAssertTrue(model.finishErrorMessage?.contains("等待联网后再结束球局") == true)
            await model.waitForPendingReplacementSyncForTesting()
            XCTAssertTrue(try store.loadQuarantinedEvents(roundId: first.roundId).isEmpty)
            XCTAssertTrue(try store.loadPendingEvents(roundId: first.roundId).isEmpty)
            XCTAssertNil(model.finishErrorMessage, "the accepted re-entry resolved the rejection")
            XCTAssertEqual(model.liveRoundState?.roundId, first.roundId)
        }
    }

    /// J5.9: unreadable durable rejection facts are not evidence of resolution. A refresh
    /// triggered by another round keeps this sealed snapshot until a successful empty read.
    func testProductSpec59SealedRecoverySurvivesQuarantineReadFailure() async throws {
        try await withDeferredRecovery { model, store, package, _ in
            let snapshot = try XCTUnwrap(model.sealedFinishRecovery)
            let quarantineDirectory = store.storageScope.accountDirectory.appendingPathComponent("event_quarantine")
            let files = try FileManager.default.contentsOfDirectory(at: quarantineDirectory, includingPropertiesForKeys: nil)
            XCTAssertEqual(files.count, 1)
            let file = try XCTUnwrap(files.first)
            let original = try Data(contentsOf: file)
            defer { try? original.write(to: file, options: [.atomic]) }
            try Data("unreadable quarantine".utf8).write(to: file, options: [.atomic])
            XCTAssertThrowsError(try store.loadQuarantinedEvents(roundId: package.roundId))
            try store.removeQuarantinedEvents(roundId: "unrelated-round")
            XCTAssertEqual(model.sealedFinishRecovery, snapshot, "a failed read must retain the last known rejection")
            try original.write(to: file, options: [.atomic])
            try store.removeQuarantinedEvents(roundId: package.roundId)
            XCTAssertNil(model.sealedFinishRecovery, "a successful empty read still clears the card")
        }
    }

    /// J6.1 / J5.9: a delayed or repeated Watch start cannot reopen the sealed outbox round.
    func testProductSpec61LateWatchStartDoesNotReactivatePendingFinish() async throws {
        try await withDeferredRecovery { model, store, package, bridge in
            XCTAssertNil(model.liveRoundState)
            XCTAssertTrue(try store.isRoundPendingFinish(package.roundId))
            let snapshot = model.sealedFinishRecovery
            let events = try store.loadEvents()
            let seed = bridge.makeWatchRoundSeedPayload(package: package, activeHole: 3)
            let start = WatchRoundStartPayload(roundId: package.roundId,
                courseName: package.course.venueDisplayName, teeBox: "blue", loopKey: package.loopKey,
                globalId: package.course.globalId, activeHole: 3, holes: seed.holes)
            // The fixture's fresh-round handoff published hole 1 before Save & End sealed it.
            // A rejected late start must clear that stale navigation intent as well.
            XCTAssertEqual(model.pendingLiveHole, package.holes.first?.number)
            for _ in 0..<2 {
                bridge.sendRoundSeedToWatch(seed)
                await model.handleWatchRoundStart(start)
                XCTAssertNil(model.liveRoundState, "a pending finish must never become a live round")
                XCTAssertNil(model.pendingWatchRoundStart)
                XCTAssertNil(model.pendingLiveHole)
                XCTAssertFalse(self.recoveryHome(model).showsInProgressPlayCard)
                XCTAssertEqual(model.sealedFinishRecovery, snapshot)
                XCTAssertTrue(try store.isRoundPendingFinish(package.roundId))
                XCTAssertEqual(try store.loadEvents(), events)
                XCTAssertNil(bridge.pendingApplicationContext()["roundSeed"], "the finished reply retracts the stale seed")
            }
            await model.stopRoundBackgroundWorkForTesting()
        }
    }

    /// J6.1 / J5.9: the finish ledger can change while a Watch package fetch is suspended.
    /// The late response must recheck the durable seal before writing an active pointer.
    func testProductSpec61WatchStartSealedDuringFetchStaysInactive() async throws {
        try await withTwoLiveRounds { model, store, first, _ in
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            let bridge = WatchEventBridge(offlineStore: OfflineStore(directoryURL: directory), autoActivate: false)
            let seed = bridge.makeWatchRoundSeedPayload(package: first, activeHole: 3)
            let start = WatchRoundStartPayload(roundId: first.roundId,
                courseName: first.course.venueDisplayName, teeBox: "blue", loopKey: first.loopKey,
                globalId: first.course.globalId, activeHole: 3, holes: seed.holes)
            let sent = self.expectation(description: "Watch package in flight before seal")
            let gate = FinishRequestGate()
            C33URLProtocol.setHandlers(onStart: { proto in
                if proto.request.url?.path.hasSuffix("/package") == true {
                    if gate.hold(proto) { sent.fulfill() }
                } else { proto.reply(404) }
            })
            let watchTask = Task { @MainActor in await model.handleWatchRoundStart(start) }
            await self.fulfillment(of: [sent], timeout: 10)
            XCTAssertEqual(model.pendingWatchRoundStart?.roundId, first.roundId)
            // Another local finish transaction commits while the earlier delivery awaits its fetch.
            try store.sealRoundForDeferredFinish(package: first, metadata: MobileRoundFinishMetadata(
                courseName: first.course.venueDisplayName, holePars: first.holes.map(\.par),
                holesCompleted: 0, courseGlobalId: first.course.globalId
            ))
            gate.reply(200, try JSONEncoder().encode(first))
            await watchTask.value
            XCTAssertNil(model.liveRoundState)
            XCTAssertNil(model.pendingWatchRoundStart)
            XCTAssertNil(model.pendingLiveHole)
            XCTAssertTrue(try store.isRoundPendingFinish(first.roundId))
            XCTAssertNil(try store.loadCurrentRoundPackage(), "no active pointer may be written after the seal")
        }
    }

    /// J5.9 (N4): the live recovery is a published fact, not a disk read in every body evaluation.
    /// A write to the quarantine alone, with no other published change, still updates the UI.
    func testProductSpec59QuarantineWriteAloneRepublishesLiveRecovery() async throws {
        try await withTwoLiveRounds { model, store, first, _ in
            await model.prepareCourseRound(roundId: first.roundId, teeBox: "blue", loops: first.loopEntries)
            await model.stopRoundBackgroundWorkForTesting()
            let rejected = LiveRoundEvent(eventId: "late-rejected-10", roundId: first.roundId,
                timestamp: "2026-01-01T00:00:00Z", hole: 10, kind: .score, payload: ["strokes": .number(3)])
            try store.appendEvent(rejected)
            try store.appendSyncMarker(roundId: first.roundId, timestamp: "2026-01-01T00:00:01Z",
                result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
            await model.setSecondLoop(nil, roundId: first.roundId)
            XCTAssertEqual(model.package?.holes.count, 9)
            XCTAssertNil(model.liveFinishRecovery)

            var changes = 0
            let subscription = model.objectWillChange.sink { _ in changes += 1 }
            defer { subscription.cancel() }
            try store.quarantineEvent(rejected, status: 422, reason: "late removed hole")
            XCTAssertGreaterThan(changes, 0, "a quarantine-only write must republish the recovery")
            XCTAssertEqual(model.liveFinishRecovery?.hole, 10)
            let afterQuarantine = changes
            try store.removeQuarantinedEvents(roundId: first.roundId)
            XCTAssertGreaterThan(changes, afterQuarantine, "clearing the quarantine must republish too")
            XCTAssertNil(model.liveFinishRecovery)
        }
    }

    /// J5.9 (N5): once a sealed round's re-entry is accepted, its recovery card goes with the
    /// quarantine, even though the finish request itself then fails without a network.
    func testProductSpec59SealedRecoveryClearsWhenReentryAcceptedButFinishFails() async throws {
        try await withDeferredRecovery { model, store, package, _ in
            let lock = NSLock()
            var finishRequests = 0
            C33URLProtocol.setHandlers(onStart: { proto in
                let path = proto.request.url?.path ?? ""
                if path.hasSuffix("/events") {
                    let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                    proto.reply(200, try! JSONEncoder().encode(SyncResult(accepted: batch.events.count,
                        duplicate: false, acceptedEventIds: batch.events.map(\.eventId))))
                    return
                }
                if path.hasSuffix("/finish") {
                    lock.lock(); finishRequests += 1; lock.unlock()
                    proto.reply(503); return
                }
                proto.reply(404)
            })
            try store.appendEvent(LiveRoundEvent(eventId: "accepted-reentry", roundId: package.roundId,
                timestamp: "2026-01-01T00:01:00Z", hole: 3, kind: .score,
                payload: ["strokes": .number(5)]))
            XCTAssertEqual(model.sealedFinishRecovery?.hole, 3)
            model.syncOnForeground()
            await model.waitForDeferredRoundFinishesForTesting()
            lock.lock(); let finishes = finishRequests; lock.unlock()
            XCTAssertEqual(finishes, 1, "the finish request itself must have been tried and failed")
            XCTAssertTrue(try store.loadQuarantinedEvents(roundId: package.roundId).isEmpty)
            XCTAssertTrue(try store.isRoundPendingFinish(package.roundId))
            XCTAssertNil(model.sealedFinishRecovery, "a resolved rejection must not keep its card until a later pass")
            XCTAssertNil(self.recoveryHome(model).deferredFinishRecovery)
        }
    }

    /// An 18-hole round whose hole-10 score was rejected, then cut to nine holes. No finish yet.
    private func startRoundWithRemovedRejection(
        _ model: LiveRoundAppModel, _ store: OfflineStore, _ package: LiveRoundPackage
    ) async throws {
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: package.loopEntries)
        await model.stopRoundBackgroundWorkForTesting()
        XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(model.package?.holes.count, 18)
        let rejected = LiveRoundEvent(eventId: "\(package.roundId)-rejected-10", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 10, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejected)
        try store.appendSyncMarker(roundId: package.roundId, timestamp: "2026-01-01T00:00:01Z",
            result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
        try store.quarantineEvent(rejected, status: 422, reason: "removed live hole")
        await model.setSecondLoop(nil, roundId: package.roundId)
        XCTAssertEqual(model.package?.holes.count, 9)
    }

    /// Two 18-hole rounds on one model; /package answers each round id with its own table.
    private func withTwoLiveRounds(
        _ body: (LiveRoundAppModel, OfflineStore, LiveRoundPackage, LiveRoundPackage) async throws -> Void
    ) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://finish-attempt.example.test")!, session: session)
        let model = c33Model(store, client)
        let nine = try c33Package()
        let first = try XCTUnwrap(nine.composingSecondLoop(
            RoundLoopEntry(globalId: 32850, half: "all"), from: nine, roundId: "finish-attempt-a"
        ))
        let second = try XCTUnwrap(nine.composingSecondLoop(
            RoundLoopEntry(globalId: 32850, half: "all"), from: nine, roundId: "finish-attempt-b"
        ))
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") {
                let requested = c33Query(proto.request, "round_id")
                proto.reply(200, try! JSONEncoder().encode(requested == second.roundId ? second : first))
                return
            }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                proto.reply(200, try! JSONEncoder().encode(SyncResult(accepted: batch.events.count,
                    duplicate: false, acceptedEventIds: batch.events.map(\.eventId))))
            } else if path.hasSuffix("/finish") { proto.reply(200) } else { proto.reply(404) }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        try await body(model, store, first, second)
        await model.stopRoundBackgroundWorkForTesting()
        await model.waitForDeferredRoundFinishesForTesting()
    }

    private func recoveryHome(
        _ model: LiveRoundAppModel, pendingWatchRoundStart: WatchRoundStartPayload? = nil
    ) -> RoundHomeView {
        RoundHomeView(
            package: model.package, offlineStore: model.offlineStore, sessionStore: nil,
            liveRoundState: model.liveRoundState,
            pendingWatchRoundStart: pendingWatchRoundStart ?? model.pendingWatchRoundStart,
            finishErrorMessage: model.finishErrorMessage,
            deferredFinishRecovery: model.sealedFinishRecovery,
            liveFinishRecovery: model.liveFinishRecovery,
            finishAttemptRoundId: model.finishAttemptRoundId,
            onDiscardRemovedDeferredFinish: { roundId, hole in
                model.discardRemovedDeferredFinishRejection(roundId: roundId, hole: hole)
            }
        )
    }

    private func withLiveRemovedRejection(
        _ body: (LiveRoundAppModel, OfflineStore, LiveRoundPackage) async throws -> Void
    ) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://live-recovery.example.test")!, session: session)
        let model = c33Model(store, client)
        let nine = try c33Package()
        let eighteen = try XCTUnwrap(nine.composingSecondLoop(
            RoundLoopEntry(globalId: 32850, half: "all"), from: nine, roundId: "live-recovery-round"
        ))
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(eighteen)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                proto.reply(200, try! JSONEncoder().encode(SyncResult(accepted: batch.events.count,
                    duplicate: false, acceptedEventIds: batch.events.map(\.eventId))))
            } else if path.hasSuffix("/finish") { proto.reply(200) } else { proto.reply(404) }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: eighteen.roundId, teeBox: "blue", loops: eighteen.loopEntries)
        await model.stopRoundBackgroundWorkForTesting()
        XCTAssertEqual(model.package?.holes.count, 18)
        let rejected = LiveRoundEvent(eventId: "live-rejected-10", roundId: eighteen.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 10, kind: .score, payload: ["strokes": .number(3)])
        try store.appendEvent(rejected)
        try store.appendSyncMarker(roundId: eighteen.roundId, timestamp: "2026-01-01T00:00:01Z",
            result: SyncResult(accepted: 1, duplicate: false, acceptedEventIds: [rejected.eventId]))
        try store.quarantineEvent(rejected, status: 422, reason: "removed live hole")
        await model.setSecondLoop(nil, roundId: eighteen.roundId)
        XCTAssertEqual(model.package?.holes.count, 9)
        let blocked = await model.finishActiveRound()
        XCTAssertFalse(blocked)
        XCTAssertEqual(model.liveFinishRecovery?.hole, 10)
        try await body(model, store, eighteen)
        await model.stopRoundBackgroundWorkForTesting()
        await model.waitForDeferredRoundFinishesForTesting()
    }

    private func withDeferredRecovery(
        hole: Int = 3,
        _ body: (LiveRoundAppModel, OfflineStore, LiveRoundPackage, WatchEventBridge) async throws -> Void
    ) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://finish-followups.example.test")!, session: session)
        let bridge = WatchEventBridge(offlineStore: store, autoActivate: false)
        let model = LiveRoundAppModel(offlineStore: store, apiBaseURL: client.baseURL,
            watchBridge: bridge, garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: nil)
        let package = try c33Package()
        C33URLProtocol.setHandlers(onStart: { proto in
            let path = proto.request.url?.path ?? ""
            if path.hasSuffix("/package") { proto.reply(200, try! JSONEncoder().encode(package)); return }
            if path.hasSuffix("/events") {
                let batch = try! JSONDecoder().decode(EventBatch.self, from: c33RequestBody(proto.request))
                if batch.events.contains(where: { $0.eventId == "rejected-score" }) {
                    proto.reply(422, Data(#"{"detail":{"code":"event_invalid","message":"bad score"}}"#.utf8))
                } else {
                    proto.reply(200, try! JSONEncoder().encode(SyncResult(accepted: batch.events.count,
                        duplicate: false, acceptedEventIds: batch.events.map(\.eventId))))
                }
                return
            }
            if path.hasSuffix("/finish") { proto.reply(200) } else { proto.reply(404) }
        })
        defer {
            client.invalidateForTesting(); session.invalidateAndCancel(); C33URLProtocol.setHandlers(onStart: nil)
            try? FileManager.default.removeItem(at: directory)
        }
        await model.prepareCourseRound(roundId: package.roundId, teeBox: "blue", loops: [.init(globalId: 32850, half: "all")])
        try store.appendEvent(LiveRoundEvent(eventId: "rejected-score", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: hole, kind: .score,
            payload: ["strokes": .number(3)]))
        let sealed = await model.finishActiveRound()
        XCTAssertTrue(sealed)
        await model.waitForDeferredRoundFinishesForTesting()
        XCTAssertEqual(model.deferredFinishRecovery?.hole, hole)
        try await body(model, store, package, bridge)
    }

    /// URLProtocol callbacks run off the main actor. A held response owns no blocking semaphore
    /// and can always be explicitly released before awaiting the model's task.
    private final class FinishRequestGate {
        private let lock = NSLock()
        private var request: C33URLProtocol?
        private var batch: EventBatch?
        private var claimed = false

        func hold(_ request: C33URLProtocol, batch: EventBatch? = nil) -> Bool {
            lock.lock(); defer { lock.unlock() }
            guard !claimed else { request.reply(404); return false }
            claimed = true
            self.request = request
            self.batch = batch
            return true
        }

        func accept() {
            lock.lock(); let batch = self.batch; lock.unlock()
            guard let batch else { return }
            reply(200, try! JSONEncoder().encode(SyncResult(accepted: batch.events.count,
                duplicate: false, acceptedEventIds: batch.events.map(\.eventId))))
        }

        func reply(_ status: Int, _ data: Data) {
            lock.lock(); let request = self.request; self.request = nil; lock.unlock()
            request?.reply(status, data)
        }
    }

}
#endif
