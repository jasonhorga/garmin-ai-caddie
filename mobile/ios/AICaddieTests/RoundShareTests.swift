import Foundation
import XCTest
@testable import AICaddie

final class RoundShareTests: XCTestCase {
    private let baseURL = URL(string: "https://api.example.test")!

    override func tearDown() {
        CapturingURLProtocol.requestHandler = nil
        SessionStore.shared.signOut()
        super.tearDown()
    }

    func testProductSpec95CreateShareUsesRoundPathAndSameAuthAsCorrections() async throws {
        var requests: [URLRequest] = []
        CapturingURLProtocol.requestHandler = { request in
            requests.append(request)
            let payload = #"{"schema":"ai-caddie-round-share-v1","url":"/api/v2/share/token","pageUrl":"/s/token","expiresAt":"2026-11-27T00:00:00Z","shareId":"share-1"}"#
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 201, httpVersion: nil, headerFields: nil
            )!
            return (response, Data(payload.utf8))
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let client = SyncClient(
            baseURL: baseURL, adminToken: "admin-secret", session: URLSession(configuration: configuration)
        )

        let share = try await client.createRoundShare(roundRef: "round-1")

        let request = try XCTUnwrap(requests.first)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/api/v2/history/rounds/round-1/share")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), nil)
        XCTAssertEqual(share.pageUrl, "/s/token")
        XCTAssertEqual(share.absolutePageURL(baseURL: baseURL)?.absoluteString, "https://api.example.test/s/token")
    }

    func testProductSpec95RevokeShareUsesDeleteAndTheSameAuthHeader() async throws {
        var captured: URLRequest?
        CapturingURLProtocol.requestHandler = { request in
            captured = request
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (response, Data(#"{"revoked":1}"#.utf8))
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let client = SyncClient(
            baseURL: baseURL, adminToken: "admin-secret", session: URLSession(configuration: configuration)
        )

        let result = try await client.revokeRoundShare(roundRef: "round-1")

        XCTAssertEqual(result.revoked, 1)
        XCTAssertEqual(captured?.httpMethod, "DELETE")
        XCTAssertEqual(captured?.url?.path, "/api/v2/history/rounds/round-1/share")
        XCTAssertEqual(captured?.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
    }

    func testProductSpec95InvalidOrFailedShareFallsBackToPlainText() {
        let fallback = "球场 · 10月28日\n72 杆（+0）"
        XCTAssertEqual(
            RoundSharePresentation.resolve(fallbackText: fallback, share: nil, baseURL: baseURL),
            .plainText(fallback)
        )
        let malicious = RoundShare(
            schema: "ai-caddie-round-share-v1", url: "/api/v2/share/t", pageUrl: "https://evil.test/s/t",
            expiresAt: "2026-11-27T00:00:00Z", shareId: "s1"
        )
        XCTAssertEqual(
            RoundSharePresentation.resolve(fallbackText: fallback, share: malicious, baseURL: baseURL),
            .plainText(fallback)
        )
    }

    func testProductSpec95ShareRequestUsesFiveSecondTimeoutAndTimeoutFallsBack() async throws {
        var timeout: TimeInterval?
        CapturingURLProtocol.requestHandler = { request in
            timeout = request.timeoutInterval
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 503, httpVersion: nil, headerFields: nil
            )!
            return (response, Data(#"{"detail":"offline"}"#.utf8))
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let client = SyncClient(
            baseURL: baseURL, adminToken: "admin-secret", session: URLSession(configuration: configuration)
        )
        let fallback = "本场复盘"

        do {
            _ = try await client.createRoundShare(roundRef: "round-1")
            XCTFail("a failed share request must throw so the view can use plain text")
        } catch {
            XCTAssertEqual(try XCTUnwrap(timeout), 5, accuracy: 0.001)
            XCTAssertEqual(
                RoundSharePresentation.resolve(fallbackText: fallback, share: nil, baseURL: baseURL),
                .plainText(fallback)
            )
        }
    }

    func testProductSpec95DuplicateShareTapIsIgnoredWhileRequestIsInFlight() {
        var gate = RoundShareRequestGate()
        XCTAssertTrue(gate.begin())
        XCTAssertFalse(gate.begin(), "the second tap must not create a second share token")
        XCTAssertTrue(gate.isInFlight)
        gate.finish()
        XCTAssertTrue(gate.begin(), "a later tap may retry after the first request completes")
    }
}
