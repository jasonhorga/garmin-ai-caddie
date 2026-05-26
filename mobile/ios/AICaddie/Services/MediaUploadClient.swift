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

    private func validate(response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
