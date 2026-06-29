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
    public let decisionId: String?
    public let sourceRef: String?
    public let evidenceRefs: [String]?
    public let shotType: String
    public let phase: String
    public let context: [String: JSONValue]
    public let options: [[String: JSONValue]]
    public let selected: [String: JSONValue]?
    public let selectedOptionId: String?
    public let selectedOption: [String: JSONValue]?
    public let sequences: [[String: JSONValue]]?
    public let selectedSequence: [String: JSONValue]?
    public let avoidZones: [[String: JSONValue]]
    public let forbiddenZones: [[String: JSONValue]]
    public let acceptableMiss: [String: JSONValue]
    public let evidence: [[String: JSONValue]]
    public let confidence: [String: JSONValue]
    public let missingData: [[String: JSONValue]]
    public let auditCriteria: [[String: JSONValue]]

    public var auditPayload: [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "schema": .string(schema),
            "shotType": .string(shotType),
            "phase": .string(phase),
            "context": .object(context),
            "options": .array(options.map { .object($0) }),
            "avoidZones": .array(avoidZones.map { .object($0) }),
            "forbiddenZones": .array(forbiddenZones.map { .object($0) }),
            "acceptableMiss": .object(acceptableMiss),
            "evidence": .array(evidence.map { .object($0) }),
            "confidence": .object(confidence),
            "missingData": .array(missingData.map { .object($0) }),
            "auditCriteria": .array(auditCriteria.map { .object($0) }),
        ]
        if let decisionId {
            payload["decisionId"] = .string(decisionId)
        }
        if let sourceRef {
            payload["sourceRef"] = .string(sourceRef)
        }
        if let evidenceRefs {
            payload["evidenceRefs"] = .array(evidenceRefs.map { .string($0) })
        }
        if let selectedOptionId {
            payload["selectedOptionId"] = .string(selectedOptionId)
        }
        if let selected {
            payload["selected"] = .object(selected)
        }
        if let selectedOption {
            payload["selectedOption"] = .object(selectedOption)
        }
        if let sequences {
            payload["sequences"] = .array(sequences.map { .object($0) })
        }
        if let selectedSequence {
            payload["selectedSequence"] = .object(selectedSequence)
        }
        return payload
    }
}

public final class CaddieDecisionClient {
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

    public func fetchCaddieDecision(
        _ decisionRequest: CaddieDecisionRequest,
        endpoint: String = "/api/v2/caddie/decision"
    ) async throws -> CaddieDecisionResponse {
        let path = endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAICaddieAuth(to: &request, adminToken: adminToken)
        request.httpBody = try encoder.encode(decisionRequest)

        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(CaddieDecisionResponse.self, from: data)
    }

    // Reuses SyncClientError so callers see the HTTP status + server body instead
    // of a generic URLError (a failed caddie call on the course was undiagnosable).
    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            AICaddieLog.caddie.error("Caddie decision response was not an HTTP response")
            throw SyncClientError.notHTTPResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8)
            AICaddieLog.caddie.error("Caddie decision HTTP \(http.statusCode, privacy: .public): \(body ?? "<no body>", privacy: .public)")
            throw SyncClientError.http(status: http.statusCode, body: body)
        }
    }
}
