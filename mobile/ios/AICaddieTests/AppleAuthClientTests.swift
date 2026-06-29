import Foundation
import XCTest
@testable import AICaddie

final class AppleAuthClientTests: XCTestCase {
    private func mockSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        return URLSession(configuration: configuration)
    }

    func testSignInHitsAppleEndpointAndDecodesSession() async throws {
        let session = mockSession()
        let payload = """
        {"token":"sess-abc","expiresAt":"2026-07-01T00:00:00Z","userId":"u1","playerId":"p_1234"}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/api/v2/auth/apple")
            XCTAssertEqual(request.httpMethod, "POST")
            // The auth exchange must NEVER send the admin token.
            XCTAssertNil(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"))
            let response = HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
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
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = AppleAuthClient(baseURL: try XCTUnwrap(URL(string: "https://example.test")), session: session)

        let result = try await client.refresh(token: "sess-old")

        XCTAssertEqual(result.token, "sess-renewed")
    }

    func testSyncClientPrefersBearerOverAdminToken() async throws {
        let session = mockSession()
        let payload = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":0,"clubs":[],"holes":[]}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            // A signed-in session uses Authorization: Bearer and NEVER the admin-token header.
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer sess-xyz")
            XCTAssertNil(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"))
            let response = HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(baseURL: try XCTUnwrap(URL(string: "https://example.test")),
                                adminToken: "admin-secret", sessionToken: "sess-xyz", session: session)

        _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
    }

    func testSyncClientFallsBackToAdminTokenWithoutSession() async throws {
        let session = mockSession()
        let payload = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":0,"clubs":[],"holes":[]}
        """.data(using: .utf8)!
        CapturingURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Caddie-Admin-Token"), "admin-secret")
            XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
            let response = HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 200, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let client = SyncClient(baseURL: try XCTUnwrap(URL(string: "https://example.test")),
                                adminToken: "admin-secret", session: session)

        _ = try await client.fetchCoursePrep(globalId: 31870, render: false)
    }
}
