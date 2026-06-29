import Foundation

public struct GarminSessionImportRequest: Codable, Equatable {
    public let webSessionHeader: String
    public let antiForgeryValue: String
    public let source: String?

    public init(webSessionHeader: String, antiForgeryValue: String, source: String? = nil) {
        self.webSessionHeader = webSessionHeader
        self.antiForgeryValue = antiForgeryValue
        self.source = source
    }
}

public struct GarminSessionImportResponse: Codable, Equatable {
    public let schema: String
    public let connector: String
    public let state: String
    public let detail: String
    public let sessionFieldCount: Int
    public let antiForgeryPresent: Bool
    public let source: String
    public let acceptedSources: [String]?
}

public final class GarminSessionClient {
    private let baseURL: URL
    private let adminToken: String?
    private let sessionToken: String?
    private let session: URLSession
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(baseURL: URL, adminToken: String? = nil, sessionToken: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.adminToken = adminToken
        self.sessionToken = sessionToken
        self.session = session
    }

    public func importSession(_ requestBody: GarminSessionImportRequest) async throws -> GarminSessionImportResponse {
        let url = endpointURL("/api/v2/sync/garmin/session")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // A signed-in session (Bearer) wins; the admin token is the DEBUG/CI fallback.
        if let sessionToken {
            request.setValue("Bearer \(sessionToken)", forHTTPHeaderField: "Authorization")
        } else if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        request.httpBody = try encoder.encode(requestBody)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(GarminSessionImportResponse.self, from: data)
    }

    private func endpointURL(_ endpoint: String) -> URL {
        let path = endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint
        return baseURL.appendingPathComponent(path)
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            AICaddieLog.network.error("Garmin session response was not an HTTP response")
            throw SyncClientError.notHTTPResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8)
            AICaddieLog.network.error("Garmin session HTTP \(http.statusCode, privacy: .public): \(body ?? "<no body>", privacy: .public)")
            throw SyncClientError.http(status: http.statusCode, body: body)
        }
    }
}
