import Foundation

public struct EventBatch: Codable, Equatable {
    public let roundId: String
    public let events: [LiveRoundEvent]
}

public struct SyncResult: Codable, Equatable {
    public let accepted: Int
    public let duplicate: Bool
}

public final class SyncClient {
    private let baseURL: URL
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
    }

    public func fetchRoundPackage(roundId: String) async throws -> LiveRoundPackage {
        let url = baseURL.appendingPathComponent("/api/v2/mobile/rounds/\(roundId)/package")
        let (data, response) = try await session.data(from: url)
        try validate(response: response)
        return try decoder.decode(LiveRoundPackage.self, from: data)
    }

    public func postEventBatch(
        _ events: [LiveRoundEvent],
        roundId: String,
        idempotencyKey: String
    ) async throws -> SyncResult {
        let url = baseURL.appendingPathComponent("/api/v2/mobile/rounds/\(roundId)/events")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        request.httpBody = try encoder.encode(EventBatch(roundId: roundId, events: events))

        let (data, response) = try await session.data(for: request)
        try validate(response: response)
        return try decoder.decode(SyncResult.self, from: data)
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

    private func validate(response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
