import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct EventBatch: Codable, Equatable {
    public let roundId: String
    public let events: [LiveRoundEvent]
}

public struct SyncResult: Codable, Equatable {
    public let accepted: Int
    public let duplicate: Bool
    public let acceptedEventIds: [String]
    public let duplicateEventIds: [String]
    public let serverSequence: Int

    private enum CodingKeys: String, CodingKey {
        case accepted
        case duplicate
        case acceptedEventIds
        case duplicateEventIds
        case serverSequence
    }

    public init(
        accepted: Int,
        duplicate: Bool,
        acceptedEventIds: [String] = [],
        duplicateEventIds: [String] = [],
        serverSequence: Int = 0
    ) {
        self.accepted = accepted
        self.duplicate = duplicate
        self.acceptedEventIds = acceptedEventIds
        self.duplicateEventIds = duplicateEventIds
        self.serverSequence = serverSequence
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.accepted = try container.decode(Int.self, forKey: .accepted)
        self.duplicate = try container.decode(Bool.self, forKey: .duplicate)
        self.acceptedEventIds = try container.decodeIfPresent([String].self, forKey: .acceptedEventIds) ?? []
        self.duplicateEventIds = try container.decodeIfPresent([String].self, forKey: .duplicateEventIds) ?? []
        self.serverSequence = try container.decodeIfPresent(Int.self, forKey: .serverSequence) ?? 0
    }
}

public struct EventReplayItem: Codable, Equatable {
    public let serverSequence: Int
    public let idempotencyKey: String
    public let event: LiveRoundEvent
}

public struct EventReplayResponse: Codable, Equatable {
    public let schema: String
    public let roundId: String
    public let clientId: String?
    public let afterSequence: Int
    public let latestServerSequence: Int
    public let nextCursor: Int
    public let eventCount: Int
    public let hasMore: Bool
    public let events: [EventReplayItem]
}

public struct EventCursorAckRequest: Codable, Equatable {
    public let clientId: String
    public let serverSequence: Int
}

public struct EventCursorAckResponse: Codable, Equatable {
    public let schema: String
    public let roundId: String
    public let clientId: String
    public let ackedServerSequence: Int
    public let latestServerSequence: Int
    public let pendingEventCount: Int
}

public final class SyncClient {
    private let baseURL: URL
    private let adminToken: String?
    private let clientId: String
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(baseURL: URL, adminToken: String? = nil, clientId: String = "ios-phone", session: URLSession = .shared) {
        self.baseURL = baseURL
        self.adminToken = adminToken
        self.clientId = clientId
        self.session = session
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
    }

    public func fetchRoundPackage(roundId: String, capturedAt: Date = Date(), ensureGeometry: Bool = false) async throws -> LiveRoundPackage {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/mobile/rounds/\(roundId)/package"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [
            URLQueryItem(name: "captured_at", value: ISO8601DateFormatter().string(from: capturedAt)),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "ensure_geometry", value: ensureGeometry ? "true" : "false"),
        ]
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(LiveRoundPackage.self, from: data)
    }

    public func fetchCoursePackage(globalId: Int, roundId: String, teeBox: String, capturedAt: Date = Date(), ensureGeometry: Bool = false) async throws -> LiveRoundPackage {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/mobile/courses/\(globalId)/package"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [
            URLQueryItem(name: "round_id", value: roundId),
            URLQueryItem(name: "tee_box", value: teeBox),
            URLQueryItem(name: "captured_at", value: ISO8601DateFormatter().string(from: capturedAt)),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "ensure_geometry", value: ensureGeometry ? "true" : "false"),
        ]
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(LiveRoundPackage.self, from: data)
    }

    public func fetchCourseOptions() async throws -> MobileCourseOptionsResponse {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/courses/options"))
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(MobileCourseOptionsResponse.self, from: data)
    }

    public func fetchCoursePrep(globalId: Int, render: Bool = true) async throws -> CoursePrepResponse {
        let path = "/api/v2/courses/\(globalId)/prep" + (render ? "" : "?render=false")
        var request = URLRequest(url: endpointURL(path))
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(CoursePrepResponse.self, from: data)
    }

    public func postEventBatch(
        _ events: [LiveRoundEvent],
        roundId: String,
        idempotencyKey: String
    ) async throws -> SyncResult {
        let url = endpointURL("/api/v2/mobile/rounds/\(roundId)/events")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        request.httpBody = try encoder.encode(EventBatch(roundId: roundId, events: events))

        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(SyncResult.self, from: data)
    }

    public func fetchEventReplay(
        roundId: String,
        afterSequence: Int? = nil,
        limit: Int = 100
    ) async throws -> EventReplayResponse {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/mobile/rounds/\(roundId)/events/replay"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        var queryItems = [
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        if let afterSequence {
            queryItems.append(URLQueryItem(name: "after_sequence", value: String(afterSequence)))
        }
        components.queryItems = queryItems
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(EventReplayResponse.self, from: data)
    }

    public func ackEventCursor(roundId: String, serverSequence: Int) async throws -> EventCursorAckResponse {
        let url = endpointURL("/api/v2/mobile/rounds/\(roundId)/events/ack")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        request.httpBody = try encoder.encode(EventCursorAckRequest(clientId: clientId, serverSequence: serverSequence))

        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(EventCursorAckResponse.self, from: data)
    }

    public func postEventBatchWithRetry(
        _ events: [LiveRoundEvent],
        roundId: String,
        idempotencyKey: String,
        attempts: Int = 3
    ) async throws -> SyncResult {
        var lastError: Error?
        for attempt in 1...max(1, attempts) {
            do {
                return try await postEventBatch(events, roundId: roundId, idempotencyKey: idempotencyKey)
            } catch {
                lastError = error
                if attempt < attempts {
                    try await Task.sleep(nanoseconds: UInt64(attempt) * 250_000_000)
                }
            }
        }
        throw lastError ?? URLError(.cannotConnectToHost)
    }

    private func endpointURL(_ endpoint: String) -> URL {
        let path = endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint
        return baseURL.appendingPathComponent(path)
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
