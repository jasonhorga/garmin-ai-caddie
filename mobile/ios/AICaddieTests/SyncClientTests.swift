import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

final class SyncClientTests: XCTestCase {
    func testEventBatchEncodesRoundIdAndEvents() throws {
        let event = LiveRoundEvent(
            eventId: "event-1",
            roundId: "round-1",
            timestamp: "2026-05-25T00:00:00Z",
            hole: 1,
            kind: .club,
            payload: ["clubName": .string("8I")]
        )

        let data = try JSONEncoder().encode(EventBatch(roundId: "round-1", events: [event]))
        let decoded = try JSONDecoder().decode(EventBatch.self, from: data)

        XCTAssertEqual(decoded.roundId, "round-1")
        XCTAssertEqual(decoded.events.first?.kind, .club)
    }

    func testSyncResultDecodesAcknowledgementMetadata() throws {
        let payload = """
        {
          "accepted": 2,
          "duplicate": false,
          "acceptedEventIds": ["event-1", "event-2"],
          "duplicateEventIds": ["event-0"],
          "serverSequence": 42
        }
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(SyncResult.self, from: payload)

        XCTAssertEqual(result.accepted, 2)
        XCTAssertFalse(result.duplicate)
        XCTAssertEqual(result.acceptedEventIds, ["event-1", "event-2"])
        XCTAssertEqual(result.duplicateEventIds, ["event-0"])
        XCTAssertEqual(result.serverSequence, 42)
    }

    func testSyncResultDecodesLegacyAcknowledgementWithoutMetadata() throws {
        let payload = """
        {
          "accepted": 1,
          "duplicate": true
        }
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(SyncResult.self, from: payload)

        XCTAssertEqual(result.accepted, 1)
        XCTAssertTrue(result.duplicate)
        XCTAssertEqual(result.acceptedEventIds, [])
        XCTAssertEqual(result.duplicateEventIds, [])
        XCTAssertEqual(result.serverSequence, 0)
    }

    func testFetchRoundPackageAttachesAdminTokenHeader() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/live-round-1/package")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            session: session
        )

        let package = try await client.fetchRoundPackage(roundId: "live-round-1")

        XCTAssertEqual(package.roundId, "live-round-1")
    }

    func testFetchRoundPackageSendsCapturedAtQuery() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let responseData = try Data(contentsOf: fixtureURL)
        let capturedAt = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-05-25T09:15:00Z"))
        CapturingURLProtocol.requestHandler = { request in
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "captured_at" }?.value, "2026-05-25T09:15:00Z")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, responseData)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        let package = try await client.fetchRoundPackage(roundId: "live-round-1", capturedAt: capturedAt)

        XCTAssertEqual(package.roundId, "live-round-1")
    }

    func testFetchCoursePrepRenderFalseSendsQueryItem() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":0,"clubs":[],"holes":[]}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/courses/31870/prep")
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "render" }?.value, "false")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        let response = try await client.fetchCoursePrep(globalId: 31870, render: false)

        XCTAssertEqual(response.globalId, 31870)
    }

    func testFetchEventReplayUsesClientCursorQuery() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = """
        {
          "schema": "ai-caddie-mobile-event-replay-v1",
          "roundId": "live-round-1",
          "clientId": "ios-test",
          "afterSequence": 1,
          "latestServerSequence": 2,
          "nextCursor": 2,
          "eventCount": 1,
          "hasMore": false,
          "events": [
            {
              "serverSequence": 2,
              "idempotencyKey": "batch-2",
              "event": {
                "schema": "ai-caddie-live-round-event-v1",
                "eventId": "club-1",
                "roundId": "live-round-1",
                "timestamp": "2026-05-25T00:00:00Z",
                "hole": 1,
                "kind": "club",
                "payload": {"clubName": "8I"}
              }
            }
          ]
        }
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/live-round-1/events/replay")
            let queryItems = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(queryItems?.first { $0.name == "client_id" }?.value, "ios-test")
            XCTAssertEqual(queryItems?.first { $0.name == "after_sequence" }?.value, "1")
            XCTAssertEqual(queryItems?.first { $0.name == "limit" }?.value, "25")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            clientId: "ios-test",
            session: session
        )

        let replay = try await client.fetchEventReplay(roundId: "live-round-1", afterSequence: 1, limit: 25)

        XCTAssertEqual(replay.clientId, "ios-test")
        XCTAssertEqual(replay.events.first?.serverSequence, 2)
        XCTAssertEqual(replay.events.first?.event.eventId, "club-1")
    }

    func testAckEventCursorPostsClientSequence() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let payload = """
        {
          "schema": "ai-caddie-mobile-event-ack-v1",
          "roundId": "live-round-1",
          "clientId": "ios-test",
          "ackedServerSequence": 2,
          "latestServerSequence": 2,
          "pendingEventCount": 0
        }
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/mobile/rounds/live-round-1/events/ack")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            let body = try Self.requestBodyData(from: request)
            let decoded = try JSONDecoder().decode(EventCursorAckRequest.self, from: body)
            XCTAssertEqual(decoded.clientId, "ios-test")
            XCTAssertEqual(decoded.serverSequence, 2)
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            adminToken: "admin-secret",
            clientId: "ios-test",
            session: session
        )

        let ack = try await client.ackEventCursor(roundId: "live-round-1", serverSequence: 2)

        XCTAssertEqual(ack.ackedServerSequence, 2)
        XCTAssertEqual(ack.pendingEventCount, 0)
    }

    func testNonSuccessResponseThrowsTypedErrorWithStatusAndBody() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: 500,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data(#"{"detail":"boom"}"#.utf8))
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session
        )

        do {
            _ = try await client.postEventBatch([], roundId: "round-1", idempotencyKey: "key-1")
            XCTFail("expected SyncClientError for a 500 response")
        } catch let error as SyncClientError {
            XCTAssertEqual(error, .http(status: 500, body: #"{"detail":"boom"}"#))
        }
    }

    private static func requestBodyData(from request: URLRequest) throws -> Data {
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
}

// CapturingURLProtocol moved to TestURLProtocol.swift (shared with AppleAuthClientTests).
