#if !SWIFT_PACKAGE
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
                if batch.events.contains(where: { $0.eventId == "bad-event" }) {
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
        try store.appendEvent(LiveRoundEvent(eventId: "bad-event", roundId: package.roundId,
            timestamp: "2026-01-01T00:00:00Z", hole: 1, kind: kind, payload: payload))
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadQuarantinedEvents(roundId: package.roundId).count, 1)
        let blocked = await model.finishActiveRound()
        XCTAssertFalse(blocked)
        try store.appendEvent(LiveRoundEvent(eventId: "replacement-event", roundId: package.roundId,
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
