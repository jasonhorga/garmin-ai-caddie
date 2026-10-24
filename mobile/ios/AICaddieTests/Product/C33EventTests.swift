#if !SWIFT_PACKAGE
import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class C33EventTests: XCTestCase {
    func testEveryRouteTokenProducesOnlyServerStrategyEnumsOrOmission() {
        // Server _LIVE_EVENT_PAYLOAD_ENUMS is the authority, not another client mapper.
        let allowed: Set<String> = ["protect_score", "stock", "attack"]
        let aliases = ["conservative layup", "safe", "safe line", "safe route", "conservative", "protect",
            "protect score", "lay back", "layup", "lay up", "stock line", "stock", "stock route",
            "standard", "standard line", "neutral", "recommended", "recommended line", "aggressive line",
            "attack", "attack line", "aggressive", "go for it", "go for it line", "unknown-route",
            "driver-3w", "route:7I", "", "   ", "未知方案"]
        let builder = LiveRoundEventBuilder(roundId: "c33-round")
        for route in aliases + aliases.map({ $0.uppercased().replacingOccurrences(of: " ", with: "_") }) {
            let event = builder.makeClubEvent(
                hole: 1, clubName: "7I", strategyMode: caddieSelectionToken(forRouteId: route)
            )
            if let value = event.payload["strategyMode"] {
                guard case let .string(mode) = value else { return XCTFail("strategyMode must be string") }
                XCTAssertTrue(allowed.contains(mode), "route=\(route), payload=\(mode)")
            }
        }
    }

    func testIdempotencyKeyBindsBodyAndIsStableAcrossTransportRetry() async throws {
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://c33-key.example.test")!, session: session)
        let package = try c33Package()
        let packageData = try JSONEncoder().encode(package)
        var keys: [String: [String]] = [:]
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
                keys[mode, default: []].append(proto.request.value(forHTTPHeaderField: "Idempotency-Key") ?? "")
                if keys[mode]!.count == 1 { proto.reply(503); return }
                proto.reply(200, try JSONEncoder().encode(SyncResult(accepted: 1, duplicate: false, acceptedEventIds: ["e1"])))
            } catch { XCTFail("\(error)"); proto.reply(500) }
        }
        URLProtocol.registerClass(C33URLProtocol.self)
        defer {
            session.invalidateAndCancel(); C33URLProtocol.onStart = nil
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
                if ids.contains("e3") { proto.reply(422, Data(#"{"detail":"invalid strategyMode"}"#.utf8)); return }
                proto.reply(200, try JSONEncoder().encode(SyncResult(accepted: ids.count, duplicate: false, acceptedEventIds: ids)))
            } catch { XCTFail("\(error)"); proto.reply(500) }
        }
        URLProtocol.registerClass(C33URLProtocol.self)
        defer {
            session.invalidateAndCancel(); C33URLProtocol.onStart = nil
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
    }
}
#endif
