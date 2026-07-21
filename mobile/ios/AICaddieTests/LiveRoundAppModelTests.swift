#if !SWIFT_PACKAGE
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

@MainActor
final class LiveRoundAppModelTests: XCTestCase {
    func testLaterConflictWithinReplayPageDoesNotAcknowledgeThatPage() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let existing = LiveRoundEvent(
            eventId: "conflict-later-in-page",
            roundId: package.roundId,
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        )
        try store.appendEvent(existing)
        try store.appendSyncMarker(
            roundId: package.roundId,
            timestamp: "2026-07-21T00:00:01Z"
        )

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let requestLock = NSLock()
        var requestedPaths: [String] = []
        let replayPayload = """
        {
          "schema": "ai-caddie-mobile-event-replay-v1",
          "roundId": "\(package.roundId)",
          "clientId": "ios-phone",
          "afterSequence": 0,
          "latestServerSequence": 2,
          "nextCursor": 2,
          "eventCount": 2,
          "hasMore": false,
          "events": [
            {
              "serverSequence": 1,
              "idempotencyKey": "remote-page",
              "event": {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "durable-prefix",
                "roundId": "\(package.roundId)",
                "clientId": "web",
                "timestamp": "2026-07-21T00:00:02Z",
                "hole": 1,
                "kind": "note",
                "payload": {"note": "prefix persisted before later conflict"}
              }
            },
            {
              "serverSequence": 2,
              "idempotencyKey": "remote-page",
              "event": {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "conflict-later-in-page",
                "roundId": "\(package.roundId)",
                "clientId": "apple-watch",
                "timestamp": "2026-07-21T00:00:00Z",
                "hole": 1,
                "kind": "score",
                "payload": {"strokes": 6}
              }
            }
          ]
        }
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            let status: Int
            let data: Data
            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/events/replay":
                status = 200
                data = replayPayload
            case "/api/v2/mobile/rounds/\(package.roundId)/events/ack":
                status = 200
                data = Data(
                    """
                    {"schema":"ai-caddie-mobile-event-ack-v1","roundId":"\(package.roundId)","clientId":"ios-phone","ackedServerSequence":2,"latestServerSequence":2,"pendingEventCount":0}
                    """.utf8
                )
            default:
                status = 500
                data = Data("{}".utf8)
            }
            return (
                HTTPURLResponse(
                    url: try XCTUnwrap(request.url),
                    statusCode: status,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!,
                data
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            clientId: "ios-phone",
            session: session
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: package.roundId,
            syncClient: client
        )

        await model.bootstrap()
        await model.syncPendingEvents()

        requestLock.lock()
        let paths = requestedPaths
        requestLock.unlock()
        XCTAssertTrue(paths.contains("/api/v2/mobile/rounds/\(package.roundId)/events/replay"))
        XCTAssertFalse(paths.contains("/api/v2/mobile/rounds/\(package.roundId)/events/ack"))
        let events = try store.loadEvents()
        XCTAssertTrue(events.contains { $0.eventId == "durable-prefix" })
        XCTAssertEqual(
            events.filter { $0.eventId == existing.eventId },
            [existing]
        )
    }

    private func localFixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let fixture = try String(contentsOf: url, encoding: .utf8)
            .replacingOccurrences(of: #""dataMode": "fixture""#, with: #""dataMode": "local""#)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: Data(fixture.utf8))
    }
}
#endif
