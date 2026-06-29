import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class AppleAuthClientTests: XCTestCase {
    private func mockSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        return URLSession(configuration: configuration)
    }

    override func tearDown() {
        SessionStore.shared.signOut()  // never leak a live session into another test
        CapturingURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testSignInHitsAppleEndpointAndDecodesSession() async throws {
        let session = mockSession()
        let payload = """
        {"token":"sess-abc","expiresAt":"2026-07-01T00:00:00Z","userId":"u1","playerId":"p_1234"}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/auth/apple")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertNil(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"))
            let response = HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }
        let client = AppleAuthClient(baseURL: try XCTUnwrap(URL(string: "https://example.test")), session: session)

        let result = try await client.signIn(identityToken: "apple.jwt", displayName: "Boss")

        XCTAssertEqual(result.token, "sess-abc")
        XCTAssertEqual(result.playerId, "p_1234")
    }

    func testRefreshSendsBearerToken() async throws {
        let session = mockSession()
        let payload = """
        {"token":"sess-renewed","expiresAt":"2026-07-02T00:00:00Z"}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/auth/apple/refresh")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer sess-old")
            let response = HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }
        let client = AppleAuthClient(baseURL: try XCTUnwrap(URL(string: "https://example.test")), session: session)

        let result = try await client.refresh(token: "sess-old")

        XCTAssertEqual(result.token, "sess-renewed")
    }

    func testApplyAuthUsesBearerWhenLiveSession() {
        SessionStore.shared.save(AppSession(token: "live-1", playerId: "me"))
        var request = URLRequest(url: URL(string: "https://x.test/api")!)
        applyAICaddieAuth(to: &request, adminToken: "admin-secret")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer live-1")
        XCTAssertNil(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"))
    }

    func testApplyAuthFallsBackToAdminWhenNoSession() {
        SessionStore.shared.signOut()
        var request = URLRequest(url: URL(string: "https://x.test/api")!)
        applyAICaddieAuth(to: &request, adminToken: "admin-secret")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
    }

    func testSyncClientUsesLiveBearerOverAdminToken() async throws {
        SessionStore.shared.save(AppSession(token: "sess-xyz", playerId: "me"))
        let session = mockSession()
        let payload = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":0,"clubs":[],"holes":[]}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer sess-xyz")
            XCTAssertNil(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"))
            let response = HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }
        // Built with an admin token, but a live session must override it.
        let client = SyncClient(baseURL: try XCTUnwrap(URL(string: "https://example.test")),
                                adminToken: "admin-secret", session: session)
        _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
    }

    func testAppleSignOutClearsLocalSessionEvenIfServerFails() async throws {
        SessionStore.shared.save(AppSession(token: "sess-bye", playerId: "me"))
        XCTAssertNotNil(SessionStore.shared.currentSession)
        let session = mockSession()
        CapturingURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 500, httpVersion: nil,
                                           headerFields: nil)!
            return (response, Data())
        }
        let client = AppleAuthClient(baseURL: try XCTUnwrap(URL(string: "https://example.test")), session: session)

        await client.signOut(token: "sess-bye")

        XCTAssertNil(SessionStore.shared.currentSession)
        XCTAssertNil(SessionStore.shared.liveToken)
    }
}
