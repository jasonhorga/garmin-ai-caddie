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

    @MainActor
    func testProductSpec95AbsolutePageURLsFallBackToPlainText() {
        let fallback = "球场 · 10月28日\n72 杆（+0）"
        for pageURL in ["https://evil.test/s/token", "//evil.test/s/token"] {
            let share = RoundShare(
                schema: "ai-caddie-round-share-v1", url: "/api/v2/share/token", pageUrl: pageURL,
                expiresAt: "2026-11-27T00:00:00Z", shareId: "share-1"
            )
            XCTAssertEqual(
                RoundSharePresentation.resolve(fallbackText: fallback, share: share, baseURL: baseURL),
                .plainText(fallback)
            )
        }
    }

    @MainActor
    func testProductSpec95ShareFlow201UsesAbsolutePageURL() async throws {
        let payload = #"{"schema":"ai-caddie-round-share-v1","url":"/api/v2/share/token","pageUrl":"/s/token","expiresAt":"2026-11-27T00:00:00Z","shareId":"share-1"}"#
        CapturingURLProtocol.requestHandler = { request in
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
        let fallback = "球场 · 10月28日\n72 杆（+0）"
        let flow = RoundShareFlow(
            create: { try await client.createRoundShare(roundRef: $0) },
            fallbackText: fallback,
            baseURL: baseURL
        )

        let presentation = await flow.share(roundRef: "round-1")

        XCTAssertEqual(
            presentation,
            .activityText(fallback + "\nhttps://api.example.test/s/token")
        )
    }

    @MainActor
    func testProductSpec95ShareFlowRebuildsWhenAdminTokenChanges() async throws {
        let payload = #"{"schema":"ai-caddie-round-share-v1","url":"/api/v2/share/token","pageUrl":"/s/token","expiresAt":"2026-11-27T00:00:00Z","shareId":"share-1"}"#
        var requests: [URLRequest] = []
        let lock = NSLock()
        CapturingURLProtocol.requestHandler = { request in
            lock.lock()
            requests.append(request)
            lock.unlock()
            let response = HTTPURLResponse(
                url: try XCTUnwrap(request.url), statusCode: 201, httpVersion: nil, headerFields: nil
            )!
            return (response, Data(payload.utf8))
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let fallback = "本场复盘"
        func makeFlow(adminToken: String) -> RoundShareFlow {
            let client = SyncClient(baseURL: baseURL, adminToken: adminToken, session: session)
            return RoundShareFlow(
                create: { try await client.createRoundShare(roundRef: $0) },
                fallbackText: fallback,
                baseURL: baseURL,
                adminToken: adminToken
            )
        }

        var flow = makeFlow(adminToken: "token-a")
        _ = await flow.share(roundRef: "round-1")
        if !RoundShareFlow.canReuse(flow, baseURL: baseURL, adminToken: "token-b") {
            flow = makeFlow(adminToken: "token-b")
        }
        _ = await flow.share(roundRef: "round-1")

        lock.lock()
        let captured = requests
        lock.unlock()
        XCTAssertEqual(captured.count, 2)
        let firstRequest = try XCTUnwrap(captured.first)
        let secondRequest = try XCTUnwrap(captured.dropFirst().first)
        XCTAssertEqual(firstRequest.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "token-a")
        XCTAssertEqual(secondRequest.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "token-b")
    }

    @MainActor
    func testProductSpec95ShareFlow503AndTimeoutFallBackToPlainText() async throws {
        let fallback = "本场复盘"
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
        let failedFlow = RoundShareFlow(
            create: { try await client.createRoundShare(roundRef: $0) },
            fallbackText: fallback,
            baseURL: baseURL
        )

        let failedPresentation = await failedFlow.share(roundRef: "round-1")

        XCTAssertEqual(failedPresentation, .plainText(fallback))
        XCTAssertEqual(try XCTUnwrap(timeout), 5, accuracy: 0.001)

        let timedOutFlow = RoundShareFlow(
            create: { _ in throw URLError(.timedOut) },
            fallbackText: fallback,
            baseURL: baseURL
        )
        let timedOutPresentation = await timedOutFlow.share(roundRef: "round-1")
        XCTAssertEqual(timedOutPresentation, .plainText(fallback))
    }

    @MainActor
    func testProductSpec95ShareFlowDuplicateTapsMakeOneRequest() async throws {
        let entered = expectation(description: "the first share request entered the protocol")
        entered.assertForOverFulfill = false
        let release = DispatchSemaphore(value: 0)
        let lock = NSLock()
        var requestCount = 0
        let payload = #"{"schema":"ai-caddie-round-share-v1","url":"/api/v2/share/token","pageUrl":"/s/token","expiresAt":"2026-11-27T00:00:00Z","shareId":"share-1"}"#
        CapturingURLProtocol.requestHandler = { request in
            lock.lock()
            requestCount += 1
            let shouldHold = requestCount == 1
            lock.unlock()
            entered.fulfill()
            if shouldHold {
                _ = release.wait(timeout: .now() + 5)
            }
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
        let fallback = "本场复盘"
        let flow = RoundShareFlow(
            create: { try await client.createRoundShare(roundRef: $0) },
            fallbackText: fallback,
            baseURL: baseURL
        )
        let first = Task { @MainActor in
            await flow.share(roundRef: "round-1")
        }

        await fulfillment(of: [entered], timeout: 5)
        let second = await flow.share(roundRef: "round-1")
        XCTAssertNil(second)
        release.signal()
        let firstPresentation = await first.value

        let third = await flow.share(roundRef: "round-1")
        XCTAssertNotNil(third, "the in-flight gate must reset after the first request completes")

        lock.lock()
        let count = requestCount
        lock.unlock()
        XCTAssertEqual(count, 2)
        XCTAssertEqual(
            firstPresentation,
            .activityText(fallback + "\nhttps://api.example.test/s/token")
        )
    }
}
