#if !SWIFT_PACKAGE
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

@MainActor
final class LiveRoundAppModelTests: XCTestCase {
    func testResponseLostEventRetryStaysExactAfterLaterMediaUploadSuccess() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let attachment = try store.savePendingMedia(
            data: Data("image".utf8),
            eventId: "photo-event",
            roundId: package.roundId,
            hole: 1,
            targetId: "\(package.roundId):1",
            assetLocalId: "photo.jpg",
            mediaKind: "photo",
            fileName: "photo.jpg",
            capturedAt: "2026-07-21T00:00:00Z"
        )
        let event = LiveRoundEventBuilder(
            roundId: package.roundId,
            idFactory: { "photo-event" },
            now: { Date(timeIntervalSince1970: 1_774_051_200) }
        ).makePhotoEvent(
            hole: 1,
            assetLocalId: attachment.assetLocalId,
            fileURL: attachment.fileURL,
            note: nil,
            mediaId: nil
        )
        try store.appendEvent(event)
        let logURL = directory.appendingPathComponent("events.jsonl")

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let stateLock = NSLock()
        var cycle = 1
        var mediaMaySucceed = false
        var eventPostMaySucceed = false
        var capturedEventPosts: [(cycle: Int, body: Data, key: String, log: Data)] = []
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            stateLock.lock()
            let currentCycle = cycle
            let shouldSucceedMedia = mediaMaySucceed
            let shouldSucceedEventPost = eventPostMaySucceed
            stateLock.unlock()

            switch path {
            case "/api/v2/media":
                guard shouldSucceedMedia else {
                    throw URLError(.networkConnectionLost)
                }
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {
                          "schema": "ai-caddie-media-create-v1",
                          "media": {
                            "id": "uploaded-media-1",
                            "createdAt": "2026-07-21T00:00:01Z",
                            "targetType": "hole",
                            "targetId": "\(package.roundId):1",
                            "mediaKind": "photo",
                            "localPath": "private/media/uploaded-media-1.jpg",
                            "capturedAt": "2026-07-21T00:00:00Z",
                            "privacyState": "private_local",
                            "source": "ios"
                          }
                        }
                        """.utf8
                    )
                )
            case "/api/v2/media/uploaded-media-1/analyze":
                throw URLError(.cannotParseResponse)
            case "/api/v2/mobile/rounds/\(package.roundId)/events":
                let captured = (
                    cycle: currentCycle,
                    body: try XCTUnwrap(request.httpBody),
                    key: try XCTUnwrap(request.value(forHTTPHeaderField: "Idempotency-Key")),
                    log: try Data(contentsOf: logURL)
                )
                stateLock.lock()
                capturedEventPosts.append(captured)
                stateLock.unlock()
                guard shouldSucceedEventPost else {
                    throw URLError(.networkConnectionLost)
                }
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {"accepted":1,"duplicate":false,"acceptedEventIds":["photo-event"],"duplicateEventIds":[],"serverSequence":1}
                        """.utf8
                    )
                )
            case "/api/v2/mobile/rounds/\(package.roundId)/events/replay":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {"schema":"ai-caddie-mobile-event-replay-v1","roundId":"\(package.roundId)","clientId":"ios-phone","afterSequence":0,"latestServerSequence":0,"nextCursor":0,"eventCount":0,"hasMore":false,"events":[]}
                        """.utf8
                    )
                )
            default:
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 500,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data("{}".utf8)
                )
            }
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let baseURL = try XCTUnwrap(URL(string: "https://example.test"))
        let syncClient = SyncClient(baseURL: baseURL, clientId: "ios-phone", session: session)
        let mediaClient = MediaUploadClient(baseURL: baseURL, session: session)
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: package.roundId,
            syncClient: syncClient,
            mediaUploadClient: mediaClient
        )

        await model.bootstrap()
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadPendingMedia(roundId: package.roundId).map(\.id), [attachment.id])

        stateLock.lock()
        cycle = 2
        mediaMaySucceed = true
        eventPostMaySucceed = true
        stateLock.unlock()
        await model.syncPendingEvents()

        stateLock.lock()
        let firstCyclePosts = capturedEventPosts.filter { $0.cycle == 1 }
        let secondCyclePosts = capturedEventPosts.filter { $0.cycle == 2 }
        stateLock.unlock()
        let firstPost = try XCTUnwrap(firstCyclePosts.first)
        let retryPost = try XCTUnwrap(secondCyclePosts.first)
        XCTAssertEqual(
            try JSONDecoder().decode(EventBatch.self, from: retryPost.body),
            try JSONDecoder().decode(EventBatch.self, from: firstPost.body)
        )
        XCTAssertEqual(retryPost.key, firstPost.key)
        XCTAssertEqual(retryPost.log, firstPost.log)
        XCTAssertEqual(firstCyclePosts.count, 3)
        XCTAssertEqual(secondCyclePosts.count, 1)
        XCTAssertTrue(try store.loadPendingMedia(roundId: package.roundId).isEmpty)
    }

    func testTornEOFReplayReopensDurablyBeforeHTTPAck() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let existing = LiveRoundEvent(
            eventId: "existing-before-torn-tail",
            roundId: package.roundId,
            clientId: "ios-phone",
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
        let logURL = directory.appendingPathComponent("events.jsonl")
        let handle = try FileHandle(forWritingTo: logURL)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data(#"{"eventId":"torn""#.utf8))
        try handle.close()

        let replayed = LiveRoundEvent(
            eventId: "durable-before-http-ack",
            roundId: package.roundId,
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:02Z",
            hole: 1,
            kind: .note,
            payload: ["note": .string("replayed after repair")]
        )
        let replayBody = try JSONEncoder().encode(
            EventReplayResponse(
                schema: "ai-caddie-mobile-event-replay-v1",
                roundId: package.roundId,
                clientId: "ios-phone",
                afterSequence: 0,
                latestServerSequence: 7,
                nextCursor: 7,
                eventCount: 1,
                hasMore: false,
                events: [
                    EventReplayItem(
                        serverSequence: 7,
                        idempotencyKey: "remote-page",
                        event: replayed
                    )
                ]
            )
        )
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let requestLock = NSLock()
        var requestedPaths: [String] = []
        var ackBody: Data?
        var durableEventsObservedAtAck: [LiveRoundEvent]?
        var durableLogObservedAtAck: Data?
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/events/replay":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    replayBody
                )
            case "/api/v2/mobile/rounds/\(package.roundId)/events/ack":
                let reopened = OfflineStore(directoryURL: directory)
                let durableEvents = try reopened.loadEvents()
                let durableLog = try Data(contentsOf: logURL)
                guard durableEvents.contains(replayed),
                      durableLog.last == 0x0A,
                      !String(decoding: durableLog, as: UTF8.self).contains(#"{"eventId":"torn""#)
                else {
                    throw URLError(.cannotParseResponse)
                }
                requestLock.lock()
                ackBody = request.httpBody
                durableEventsObservedAtAck = durableEvents
                durableLogObservedAtAck = durableLog
                requestLock.unlock()
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data(
                        """
                        {"schema":"ai-caddie-mobile-event-ack-v1","roundId":"\(package.roundId)","clientId":"ios-phone","ackedServerSequence":7,"latestServerSequence":7,"pendingEventCount":0}
                        """.utf8
                    )
                )
            default:
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 500,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    Data("{}".utf8)
                )
            }
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
        let capturedAckBody = ackBody
        let eventsAtAck = durableEventsObservedAtAck
        let logAtAck = durableLogObservedAtAck
        requestLock.unlock()
        let replayPath = "/api/v2/mobile/rounds/\(package.roundId)/events/replay"
        let ackPath = "/api/v2/mobile/rounds/\(package.roundId)/events/ack"
        let replayIndex = try XCTUnwrap(paths.firstIndex(of: replayPath))
        let ackIndex = try XCTUnwrap(paths.firstIndex(of: ackPath))
        XCTAssertLessThan(replayIndex, ackIndex)
        XCTAssertEqual(
            try JSONDecoder().decode(
                EventCursorAckRequest.self,
                from: try XCTUnwrap(capturedAckBody)
            ),
            EventCursorAckRequest(clientId: "ios-phone", serverSequence: 7)
        )
        let unwrappedEventsAtAck = try XCTUnwrap(eventsAtAck)
        XCTAssertTrue(unwrappedEventsAtAck.contains(replayed))
        let durableLog = try XCTUnwrap(logAtAck)
        XCTAssertEqual(durableLog.last, 0x0A)
        XCTAssertFalse(String(decoding: durableLog, as: UTF8.self).contains(#"{"eventId":"torn""#))
        XCTAssertEqual(try OfflineStore(directoryURL: directory).loadEvents(), unwrappedEventsAtAck)
    }

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
