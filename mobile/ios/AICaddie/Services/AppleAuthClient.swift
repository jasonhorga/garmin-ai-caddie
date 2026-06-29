import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Response of `/api/v2/auth/apple` (and `/refresh`): a session bearer token + the resolved player.
/// `playerId` is present on sign-in; `/refresh` returns just the token, so it is optional here.
public struct AppleSignInResponse: Codable, Equatable {
    public let token: String
    public let playerId: String?
    public let userId: String?
    public let expiresAt: String?
}

/// Talks to the backend Apple-auth endpoints. The app passes Apple's identity token; the backend
/// verifies it (JWKS), routes the owner's allowlisted Apple IDs to "me" and everyone else to an
/// auto-registered member, and mints a short-lived session token. No Apple secret on the client.
public final class AppleAuthClient {
    private let baseURL: URL
    private let session: URLSession
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    private struct SignInBody: Encodable {
        let identityToken: String
        let displayName: String?
    }

    public func signIn(identityToken: String, displayName: String?) async throws -> AppleSignInResponse {
        var request = URLRequest(url: endpoint("/api/v2/auth/apple"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(SignInBody(identityToken: identityToken, displayName: displayName))
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(AppleSignInResponse.self, from: data)
    }

    public func refresh(token: String) async throws -> AppleSignInResponse {
        var request = URLRequest(url: endpoint("/api/v2/auth/apple/refresh"))
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(AppleSignInResponse.self, from: data)
    }

    /// Revoke the session server-side (best-effort) and ALWAYS clear it locally — even if the server
    /// call fails, the user must end up signed out.
    public func signOut(token: String) async {
        do {
            var request = URLRequest(url: endpoint("/api/v2/auth/logout"))
            request.httpMethod = "POST"
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            let (data, response) = try await session.data(for: request)
            try validate(response: response, data: data)
        } catch {
            // best-effort; fall through to the local clear
        }
        SessionStore.shared.signOut()
    }

    private func endpoint(_ path: String) -> URL {
        baseURL.appendingPathComponent(path.hasPrefix("/") ? String(path.dropFirst()) : path)
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw SyncClientError.notHTTPResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw SyncClientError.http(status: http.statusCode, body: String(data: data, encoding: .utf8))
        }
    }
}
