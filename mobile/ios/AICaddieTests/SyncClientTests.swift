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
}

private final class CapturingURLProtocol: URLProtocol {
    static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        guard let requestHandler = Self.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }

        do {
            let (response, data) = try requestHandler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
