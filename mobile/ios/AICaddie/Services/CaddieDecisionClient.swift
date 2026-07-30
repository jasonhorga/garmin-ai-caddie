import Foundation

public struct CaddieDecisionRequest: Codable, Equatable {
    public let shotType: String
    public let context: [String: JSONValue]
    /// The live screen consumes the deterministic options/sequences, not generated prose. Keeping
    /// this false prevents a slow or rate-limited LLM explanation from blocking the on-course plan.
    public let includeExplanation: Bool

    public init(
        shotType: String,
        context: [String: JSONValue],
        includeExplanation: Bool = false
    ) {
        self.shotType = shotType
        self.context = context
        self.includeExplanation = includeExplanation
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

    /// Online decisions are already stored by `decisionId` before the API returns them. Only the
    /// deterministic offline evaluator needs to carry a decision snapshot with a later live event.
    public var isOfflineFallback: Bool {
        confidence["source"] == .string("offline_package_seed")
            || decisionId?.hasPrefix("offline-") == true
    }

    /// Minimal facts consumed by `audit_decision`. This is intentionally not a second copy of the
    /// display decision: route meshes, history samples, evidence prose, and full source-ref lists
    /// belong in the decision ledger/package, not in every live-round event.
    public var auditPayload: [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "schema": .string("ai-caddie-decision-audit-snapshot-v1"),
            "shotType": .string(shotType),
            "phase": .string(phase),
            "context": .object(Self.compactFields(
                context,
                keys: ["sourceRef", "roundId", "hole", "localHole", "globalId"]
            )),
            "options": .array(options.prefix(16).map { .object(Self.compactOption($0)) }),
            "confidence": .object(Self.compactFields(confidence, keys: ["level"])),
            "auditCriteria": .array(auditCriteria.prefix(16).map {
                .object(Self.compactFields(
                    $0,
                    keys: ["label", "rule", "targetOptionId", "sourceRef", "clubName", "confidence", "sampleSize"]
                ))
            }),
        ]
        if let decisionId {
            payload["decisionId"] = .string(decisionId)
        }
        if let sourceRef {
            payload["sourceRef"] = .string(sourceRef)
        }
        if let evidenceRefs {
            let compactRefs = evidenceRefs.prefix(32)
            payload["evidenceRefs"] = .array(compactRefs.map { .string($0) })
            if compactRefs.count < evidenceRefs.count {
                payload["evidenceRefCount"] = .number(Double(evidenceRefs.count))
            }
        }
        if let selectedOptionId {
            payload["selectedOptionId"] = .string(selectedOptionId)
        }
        if let selected = selectedOption ?? self.selected {
            payload["selectedOption"] = .object(Self.compactSelectedOption(selected))
        }
        return payload
    }

    private static func compactFields(
        _ source: [String: JSONValue],
        keys: [String]
    ) -> [String: JSONValue] {
        var result: [String: JSONValue] = [:]
        for key in keys {
            if let value = source[key] {
                result[key] = value
            }
        }
        return result
    }

    private static func compactOption(_ source: [String: JSONValue]) -> [String: JSONValue] {
        var result = compactFields(source, keys: ["id", "label", "carry_m", "riskScore"])
        if result["carry_m"] == nil, let carry = source["carryM"] {
            result["carry_m"] = carry
        }
        return result
    }

    private static func compactSelectedOption(_ source: [String: JSONValue]) -> [String: JSONValue] {
        var result = compactOption(source)
        if case .object(let targetWindow) = source["targetWindow"] {
            let compactWindow = compactFields(
                targetWindow,
                keys: ["frontCarry_m", "backCarry_m"]
            )
            if !compactWindow.isEmpty {
                result["targetWindow"] = .object(compactWindow)
            }
        }

        var clubs: [JSONValue] = []
        if case .object(let recommendation) = source["clubRecommendation"],
           case .array(let rows) = recommendation["clubs"] {
            for value in rows.prefix(8) {
                guard case .object(let row) = value,
                      let clubName = row["clubName"]
                else {
                    continue
                }
                clubs.append(.object(["clubName": clubName]))
            }
        }
        if clubs.isEmpty, let clubName = source["clubName"] {
            clubs.append(.object(["clubName": clubName]))
        }
        if !clubs.isEmpty {
            result["clubRecommendation"] = .object(["clubs": .array(clubs)])
        }
        return result
    }
}

/// SwiftUI cancels a view task when its hole identity changes or the live surface leaves the
/// hierarchy. URLSession may surface that as either Swift `CancellationError` or
/// `URLError.cancelled`; neither means the network is unavailable and neither should replace a
/// valid/cached recommendation with an error banner.
enum LiveCaddieLoadFailure {
    static func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError {
            return true
        }
        return (error as? URLError)?.code == .cancelled
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
