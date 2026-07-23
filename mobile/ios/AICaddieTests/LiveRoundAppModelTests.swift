#if !SWIFT_PACKAGE
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Network
import XCTest
@testable import AICaddie

private enum LiveRoundAppModelTestFailure: Error {
    case directorySync
    case loopbackServerStart(String)
    case loopbackServerTimeout
}

private final class LoopbackHTTPServer: @unchecked Sendable {
    private struct Request {
        let path: String
        let body: Data
    }

    private let listener: NWListener
    private let queue = DispatchQueue(label: "ai-caddie-tests.loopback-http")
    private let handler: (String, Data) -> (Int, Data)
    private let startupSemaphore = DispatchSemaphore(value: 0)
    private let startupLock = NSLock()
    private var startupFailure: Error?

    init(handler: @escaping (String, Data) -> (Int, Data)) throws {
        self.handler = handler
        self.listener = try NWListener(using: .tcp, on: .any)
        listener.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                startupSemaphore.signal()
            case .failed(let error):
                startupLock.lock()
                startupFailure = LiveRoundAppModelTestFailure.loopbackServerStart(
                    String(describing: error)
                )
                startupLock.unlock()
                startupSemaphore.signal()
            default:
                break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in
            self?.accept(connection)
        }
        listener.start(queue: queue)
        guard startupSemaphore.wait(timeout: .now() + 5) == .success else {
            listener.cancel()
            throw LiveRoundAppModelTestFailure.loopbackServerTimeout
        }
        startupLock.lock()
        let failure = startupFailure
        startupLock.unlock()
        if let failure {
            listener.cancel()
            throw failure
        }
        guard listener.port != nil else {
            listener.cancel()
            throw LiveRoundAppModelTestFailure.loopbackServerStart("missing bound port")
        }
    }

    var baseURL: URL {
        guard let port = listener.port,
              let url = URL(string: "http://127.0.0.1:\(port.rawValue)")
        else {
            preconditionFailure("loopback listener lost its bound port")
        }
        return url
    }

    func stop() {
        listener.cancel()
    }

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        receive(on: connection, accumulated: Data())
    }

    private func receive(on connection: NWConnection, accumulated: Data) {
        connection.receive(
            minimumIncompleteLength: 1,
            maximumLength: 64 * 1024
        ) { [weak self] data, _, isComplete, error in
            guard let self else {
                connection.cancel()
                return
            }
            var received = accumulated
            if let data {
                received.append(data)
            }
            if let request = parseRequest(received) {
                let response = handler(request.path, request.body)
                send(status: response.0, body: response.1, on: connection)
                return
            }
            if isComplete || error != nil || received.count > 1_048_576 {
                connection.cancel()
                return
            }
            receive(on: connection, accumulated: received)
        }
    }

    private func parseRequest(_ data: Data) -> Request? {
        let separator = Data("\r\n\r\n".utf8)
        guard let headerRange = data.range(of: separator),
              let header = String(data: data[..<headerRange.lowerBound], encoding: .utf8)
        else {
            return nil
        }
        let lines = header.components(separatedBy: "\r\n")
        guard let requestLine = lines.first else { return nil }
        let requestParts = requestLine.split(separator: " ", omittingEmptySubsequences: true)
        guard requestParts.count >= 2 else { return nil }
        let contentLength = lines.dropFirst().compactMap { line -> Int? in
            let fields = line.split(separator: ":", maxSplits: 1).map(String.init)
            guard fields.count == 2,
                  fields[0].trimmingCharacters(in: .whitespacesAndNewlines)
                    .caseInsensitiveCompare("Content-Length") == .orderedSame
            else {
                return nil
            }
            return Int(fields[1].trimmingCharacters(in: .whitespacesAndNewlines))
        }.first ?? 0
        let bodyStart = headerRange.upperBound
        let bodyEnd = bodyStart + contentLength
        guard data.count >= bodyEnd else { return nil }
        return Request(
            path: String(requestParts[1]),
            body: data.subdata(in: bodyStart..<bodyEnd)
        )
    }

    private func send(status: Int, body: Data, on connection: NWConnection) {
        let reason: String
        switch status {
        case 200: reason = "OK"
        case 404: reason = "Not Found"
        default: reason = "Service Unavailable"
        }
        var response = Data(
            """
            HTTP/1.1 \(status) \(reason)\r
            Content-Type: application/json\r
            Content-Length: \(body.count)\r
            Connection: close\r
            \r

            """.utf8
        )
        response.append(body)
        connection.send(content: response, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
}

private func capturedRequestBodyData(from request: URLRequest) throws -> Data {
    if let body = request.httpBody {
        return body
    }
    guard let stream = request.httpBodyStream else {
        throw URLError(.zeroByteResource)
    }
    stream.open()
    defer { stream.close() }
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 1024)
    while stream.hasBytesAvailable {
        let readCount = stream.read(&buffer, maxLength: buffer.count)
        if readCount < 0 {
            throw stream.streamError ?? URLError(.cannotDecodeContentData)
        }
        if readCount == 0 {
            break
        }
        data.append(buffer, count: readCount)
    }
    return data
}

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

        let mediaStateLock = NSLock()
        var mediaUploadMaySucceed = false
        let mediaSuccessBody = Data(
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
        let mediaServer = try LoopbackHTTPServer { path, _ in
            mediaStateLock.lock()
            defer { mediaStateLock.unlock() }
            switch path {
            case "/api/v2/media":
                if !mediaUploadMaySucceed {
                    return (503, Data("{}".utf8))
                }
                return (200, mediaSuccessBody)
            case "/api/v2/media/uploaded-media-1/analyze":
                return (503, Data("{}".utf8))
            default:
                return (404, Data("{}".utf8))
            }
        }
        defer { mediaServer.stop() }

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let stateLock = NSLock()
        var cycle = 1
        var eventPostMaySucceed = false
        var capturedEventPosts: [(cycle: Int, body: Data, key: String, log: Data)] = []
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            stateLock.lock()
            let currentCycle = cycle
            let shouldSucceedEventPost = eventPostMaySucceed
            stateLock.unlock()

            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/events":
                let captured = (
                    cycle: currentCycle,
                    body: try capturedRequestBodyData(from: request),
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
        let syncClient = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            clientId: "ios-phone",
            session: session
        )
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: mediaServer.baseURL,
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: package.roundId,
            syncClient: syncClient
        )

        await model.bootstrap()
        await model.syncPendingEvents()
        XCTAssertEqual(try store.loadPendingMedia(roundId: package.roundId).map(\.id), [attachment.id])

        mediaStateLock.lock()
        mediaUploadMaySucceed = true
        mediaStateLock.unlock()
        stateLock.lock()
        cycle = 2
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
                ackBody = try capturedRequestBodyData(from: request)
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

    func testExactReplayDirectoryBarrierFaultNeverSendsHTTPAck() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let barrierLock = NSLock()
        var barrierShouldFail = false
        var barrierOperations: [String] = []
        let store = OfflineStore(
            directoryURL: directory,
            syncEventLogFile: { url in
                barrierLock.lock()
                barrierOperations.append("file:\(url.lastPathComponent)")
                barrierLock.unlock()
            },
            syncEventLogDirectory: { url in
                barrierLock.lock()
                barrierOperations.append("directory:\(url.lastPathComponent)")
                let mustFail = barrierShouldFail
                    && url.standardizedFileURL.resolvingSymlinksInPath()
                        == directory.standardizedFileURL.resolvingSymlinksInPath()
                barrierLock.unlock()
                if mustFail {
                    throw LiveRoundAppModelTestFailure.directorySync
                }
            }
        )
        let package = try localFixturePackage()
        try store.saveRoundPackage(package)
        let replayed = LiveRoundEvent(
            eventId: "visible-but-directory-barrier-uncertain",
            roundId: package.roundId,
            clientId: "apple-watch",
            timestamp: "2026-07-21T00:00:02Z",
            hole: 1,
            kind: .syncMarker,
            payload: [
                "status": .string("synced"),
                "serverSequence": .number(0),
            ]
        )
        let logURL = directory.appendingPathComponent("events.jsonl")
        let packageBody = try JSONEncoder().encode(package)
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
        var ackObservedEvents: [LiveRoundEvent]?
        var ackObservedLog: Data?
        var ackObservedBarriers: [String]?
        CapturingURLProtocol.requestHandler = { request in
            let path = request.url?.path ?? ""
            requestLock.lock()
            requestedPaths.append(path)
            requestLock.unlock()
            switch path {
            case "/api/v2/mobile/rounds/\(package.roundId)/package":
                return (
                    HTTPURLResponse(
                        url: try XCTUnwrap(request.url),
                        statusCode: 200,
                        httpVersion: nil,
                        headerFields: ["Content-Type": "application/json"]
                    )!,
                    packageBody
                )
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
                barrierLock.lock()
                let barriers = barrierOperations
                barrierLock.unlock()
                let reopened = OfflineStore(directoryURL: directory)
                let durableEvents = try reopened.loadEvents()
                let durableLog = try Data(contentsOf: logURL)
                requestLock.lock()
                ackBody = try capturedRequestBodyData(from: request)
                ackObservedEvents = durableEvents
                ackObservedLog = durableLog
                ackObservedBarriers = barriers
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
        requestLock.lock()
        requestedPaths.removeAll()
        requestLock.unlock()
        barrierLock.lock()
        barrierOperations.removeAll()
        barrierShouldFail = true
        barrierLock.unlock()

        await model.syncPendingEvents()

        requestLock.lock()
        let failedAttemptPaths = requestedPaths
        requestLock.unlock()
        barrierLock.lock()
        let failedAttemptBarriers = barrierOperations
        barrierLock.unlock()
        let physicallyVisibleEvents = try OfflineStore(directoryURL: directory).loadEvents()
        let physicallyVisibleLog = try Data(contentsOf: logURL)
        XCTAssertEqual(physicallyVisibleEvents, [replayed])
        XCTAssertEqual(physicallyVisibleLog.last, 0x0A)
        XCTAssertEqual(physicallyVisibleLog.split(separator: 0x0A).count, 1)

        barrierLock.lock()
        barrierShouldFail = false
        barrierOperations.removeAll()
        barrierLock.unlock()
        XCTAssertTrue(
            failedAttemptPaths.contains(
                "/api/v2/mobile/rounds/\(package.roundId)/events/replay"
            )
        )
        XCTAssertFalse(
            failedAttemptPaths.contains(
                "/api/v2/mobile/rounds/\(package.roundId)/events/ack"
            )
        )
        XCTAssertEqual(
            Array(failedAttemptBarriers.suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )

        requestLock.lock()
        requestedPaths.removeAll()
        requestLock.unlock()
        await model.syncPendingEvents()

        requestLock.lock()
        let successfulAttemptPaths = requestedPaths
        let capturedAckBody = ackBody
        let durableEventsAtAck = ackObservedEvents
        let durableLogAtAck = ackObservedLog
        let barriersAtAck = ackObservedBarriers
        requestLock.unlock()
        let replayPath = "/api/v2/mobile/rounds/\(package.roundId)/events/replay"
        let ackPath = "/api/v2/mobile/rounds/\(package.roundId)/events/ack"
        let replayIndex = try XCTUnwrap(successfulAttemptPaths.firstIndex(of: replayPath))
        let ackIndex = try XCTUnwrap(successfulAttemptPaths.firstIndex(of: ackPath))
        XCTAssertLessThan(replayIndex, ackIndex)
        XCTAssertEqual(successfulAttemptPaths.filter { $0 == ackPath }.count, 1)
        XCTAssertEqual(
            try JSONDecoder().decode(
                EventCursorAckRequest.self,
                from: try XCTUnwrap(capturedAckBody)
            ),
            EventCursorAckRequest(clientId: "ios-phone", serverSequence: 7)
        )
        XCTAssertEqual(try XCTUnwrap(durableEventsAtAck), [replayed])
        let durableLog = try XCTUnwrap(durableLogAtAck)
        XCTAssertEqual(durableLog.last, 0x0A)
        XCTAssertEqual(durableLog.split(separator: 0x0A).count, 1)
        XCTAssertEqual(
            Array(try XCTUnwrap(barriersAtAck).suffix(2)),
            ["file:events.jsonl", "directory:\(directory.lastPathComponent)"]
        )
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
