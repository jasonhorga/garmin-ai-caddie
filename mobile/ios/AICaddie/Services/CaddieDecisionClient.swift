import Foundation

public struct CaddieDecisionRequest: Codable, Equatable {
    public let shotType: String
    public let context: [String: JSONValue]

    public init(shotType: String, context: [String: JSONValue]) {
        self.shotType = shotType
        self.context = context
    }
}

public struct CaddieDecisionResponse: Codable, Equatable {
    public let schema: String
    public let shotType: String
    public let phase: String
    public let context: [String: JSONValue]
    public let options: [[String: JSONValue]]
    public let selected: [String: JSONValue]?
    public let selectedOptionId: String?
    public let selectedOption: [String: JSONValue]?
    public let avoidZones: [[String: JSONValue]]
    public let forbiddenZones: [[String: JSONValue]]
    public let acceptableMiss: [String: JSONValue]
    public let evidence: [[String: JSONValue]]
    public let confidence: [String: JSONValue]
    public let missingData: [[String: JSONValue]]
    public let auditCriteria: [[String: JSONValue]]
}

public final class CaddieDecisionClient {
    private let baseURL: URL
    private let session: URLSession
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    public func fetchCaddieDecision(
        _ decisionRequest: CaddieDecisionRequest,
        endpoint: String = "/api/v2/caddie/decision"
    ) async throws -> CaddieDecisionResponse {
        let path = endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(decisionRequest)

        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(CaddieDecisionResponse.self, from: data)
    }

    private func validate(response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
