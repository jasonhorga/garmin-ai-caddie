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
        var mediaUploadAttempts = 0
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
                mediaUploadAttempts += 1
                if mediaUploadAttempts <= 3 {
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
        XCTAssertEqual(firstCyclePosts.count, 3)
        XCTAssertEqual(secondCyclePosts.count, 1)
        XCTAssertTrue(try store.loadPendingMedia(roundId: package.roundId).isEmpty)
        mediaStateLock.lock()
        let finalMediaUploadAttempts = mediaUploadAttempts
        mediaStateLock.unlock()
        XCTAssertEqual(finalMediaUploadAttempts, 4)
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
