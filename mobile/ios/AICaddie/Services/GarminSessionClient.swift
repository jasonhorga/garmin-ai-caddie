import Foundation

public struct GarminSessionImportRequest: Codable, Equatable {
    public let webSessionHeader: String
    public let antiForgeryValue: String

    public init(webSessionHeader: String, antiForgeryValue: String) {
        self.webSessionHeader = webSessionHeader
        self.antiForgeryValue = antiForgeryValue
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
}

public final class GarminSessionClient {
    private let baseURL: URL
    private let adminToken: String?
    private let session: URLSession
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(baseURL: URL, adminToken: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.adminToken = adminToken
        self.session = session
    }

    public func importSession(_ requestBody: GarminSessionImportRequest) async throws -> GarminSessionImportResponse {
        let url = baseURL.appendingPathComponent("/api/v2/sync/garmin/session")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        request.httpBody = try encoder.encode(requestBody)
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(GarminSessionImportResponse.self, from: data)
    }

    private func validate(response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
