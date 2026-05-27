import Foundation

public struct MediaCreateRequest: Codable, Equatable {
    public let targetType: String
    public let targetId: String
    public let mediaKind: String
    public let fileName: String?
    public let contentBase64: String?
    public let capturedAt: String
    public let privacyState: String

    public init(
        targetType: String,
        targetId: String,
        mediaKind: String,
        fileName: String?,
        contentBase64: String?,
        capturedAt: String,
        privacyState: String = "private_local"
    ) {
        self.targetType = targetType
        self.targetId = targetId
        self.mediaKind = mediaKind
        self.fileName = fileName
        self.contentBase64 = contentBase64
        self.capturedAt = capturedAt
        self.privacyState = privacyState
    }
}

public struct MediaCreateResponse: Codable, Equatable {
    public let schema: String
    public let media: MediaRecord
}

public struct MediaRecord: Codable, Equatable, Identifiable {
    public let id: String
    public let createdAt: String
    public let targetType: String
    public let targetId: String
    public let mediaKind: String
    public let localPath: String
    public let capturedAt: String
    public let privacyState: String
    public let source: String
}

public struct VisionFinding: Codable, Equatable {
    public let id: String?
    public let createdAt: String?
    public let targetType: String?
    public let targetId: String?
    public let mediaId: String?
    public let mediaKind: String?
    public let findingType: String
    public let evidenceText: String
    public let confidence: String
    public let confirmationState: String
    public let confirmedAt: String?
    public let confirmedBy: String?
    public let missingInfo: [String]
    public let provider: String?
    public let model: String?
    public let source: String

    public var contextPayload: [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "findingType": .string(findingType),
            "evidenceText": .string(evidenceText),
            "confidence": .string(confidence),
            "confirmationState": .string(confirmationState),
            "missingInfo": .array(missingInfo.map { .string($0) }),
            "source": .string(source),
        ]
        if let id {
            payload["id"] = .string(id)
        }
        if let createdAt {
            payload["createdAt"] = .string(createdAt)
        }
        if let targetType {
            payload["targetType"] = .string(targetType)
        }
        if let targetId {
            payload["targetId"] = .string(targetId)
        }
        if let mediaId {
            payload["mediaId"] = .string(mediaId)
        }
        if let mediaKind {
            payload["mediaKind"] = .string(mediaKind)
        }
        if let confirmedAt {
            payload["confirmedAt"] = .string(confirmedAt)
        }
        if let confirmedBy {
            payload["confirmedBy"] = .string(confirmedBy)
        }
        if let provider {
            payload["provider"] = .string(provider)
        }
        if let model {
            payload["model"] = .string(model)
        }
        return payload
    }
}

public struct VisionAnalysisResponse: Codable, Equatable {
    public let schema: String
    public let mediaId: String?
    public let targetType: String?
    public let targetId: String?
    public let mediaKind: String?
    public let provider: String
    public let model: String
    public let findings: [VisionFinding]
}

public struct VisionFindingsListResponse: Codable, Equatable {
    public let schema: String
    public let total: Int
    public let findings: [VisionFinding]
    public let target: [String: String]
}

public struct VisionFindingConfirmationRequest: Codable, Equatable {
    public let confirmationState: String
    public let confirmedBy: String?

    public init(confirmationState: String, confirmedBy: String? = "ios") {
        self.confirmationState = confirmationState
        self.confirmedBy = confirmedBy
    }
}

public struct VisionFindingConfirmationResponse: Codable, Equatable {
    public let schema: String
    public let finding: VisionFinding
}

public final class MediaUploadClient {
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

    public func uploadMedia(_ requestBody: MediaCreateRequest) async throws -> MediaCreateResponse {
        let url = baseURL.appendingPathComponent("/api/v2/media")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        request.httpBody = try encoder.encode(requestBody)
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(MediaCreateResponse.self, from: data)
    }

    public func analyzeMedia(mediaId: String) async throws -> VisionAnalysisResponse {
        let url = baseURL.appendingPathComponent("/api/v2/media/" + mediaId + "/analyze")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(VisionAnalysisResponse.self, from: data)
    }

    public func fetchVisionFindingsForTarget(targetType: String, targetId: String) async throws -> VisionFindingsListResponse {
        let url = baseURL.appendingPathComponent("/api/v2/media/target/" + targetType + "/" + targetId + "/findings")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(VisionFindingsListResponse.self, from: data)
    }

    public func confirmVisionFinding(findingId: String, requestBody: VisionFindingConfirmationRequest) async throws -> VisionFindingConfirmationResponse {
        let url = baseURL.appendingPathComponent("/api/v2/media/findings/" + findingId + "/confirmation")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        request.httpBody = try encoder.encode(requestBody)
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(VisionFindingConfirmationResponse.self, from: data)
    }

    private func validate(response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
