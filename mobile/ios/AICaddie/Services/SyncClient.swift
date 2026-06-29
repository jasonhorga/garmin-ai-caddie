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

/// Typed sync transport error. Previously every non-2xx collapsed into a generic
/// `URLError(.badServerResponse)`, discarding the HTTP status and the server's
/// error body — useless for diagnosing a failed sync on the course. This keeps
/// both so callers and logs can tell apart auth (401), missing round (404), and
/// server faults (5xx).
public enum SyncClientError: Error, Equatable {
    case notHTTPResponse
    case http(status: Int, body: String?)
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
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(LiveRoundPackage.self, from: data)
    }

    public func fetchCoursePackage(globalId: Int, roundId: String, teeBox: String, nine: String = "all", capturedAt: Date = Date(), ensureGeometry: Bool = false, backGlobalId: Int? = nil) async throws -> LiveRoundPackage {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/mobile/courses/\(globalId)/package"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        var items = [
            URLQueryItem(name: "round_id", value: roundId),
            URLQueryItem(name: "tee_box", value: teeBox),
            URLQueryItem(name: "nine", value: nine),
            URLQueryItem(name: "captured_at", value: ISO8601DateFormatter().string(from: capturedAt)),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "ensure_geometry", value: ensureGeometry ? "true" : "false"),
        ]
        if let backGlobalId {
            // Composite 18: play this loop (holes 1–9) + a second loop (holes 10–18).
            items.append(URLQueryItem(name: "back_global_id", value: String(backGlobalId)))
        }
        components.queryItems = items
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(LiveRoundPackage.self, from: data)
    }

    public func fetchCourseOptions() async throws -> MobileCourseOptionsResponse {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/courses/options"))
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(MobileCourseOptionsResponse.self, from: data)
    }

    /// Compact 统计 payload (`GET /api/v2/history/stats/mobile`): basic / deep / periodic / course /
    /// club slices of the full stats build (~180KB, not the ~11MB full one). Used by StatsView.
    public func fetchMobileStats() async throws -> MobileStats {
        var request = URLRequest(url: endpointURL("/api/v2/history/stats/mobile"))
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(MobileStats.self, from: data)
    }

    /// The player's real Garmin club bag (`GET /api/v2/history/clubs/bag`): the canonical roster
    /// (clubTypeId + custom name + retired/deleted) the backend pulls from Garmin's `/club/player`
    /// + `/club/types`. Resolved to Chinese catalog names on-device; powers the bag default + picker.
    public func fetchClubBag() async throws -> ClubBagResponse {
        var request = URLRequest(url: endpointURL("/api/v2/history/clubs/bag"))
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(ClubBagResponse.self, from: data)
    }

    /// Persist the player's MANUAL club bag (`PUT /api/v2/players/{id}/clubs/bag`): the tokens (+ any
    /// per-club metre distances) the player configured in 球杆设置. The owner's admin token targets
    /// "me". Returns the resulting EFFECTIVE bag (manual wins, else the synced Garmin bag).
    public func putManualClubBag(playerId: String = "me", clubs: [ManualClubInput]) async throws -> EffectiveClubBagResponse {
        var request = URLRequest(url: endpointURL("/api/v2/players/\(playerId)/clubs/bag"))
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAuth(to: &request)
        request.httpBody = try encoder.encode(ManualBagBody(clubs: clubs))
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(EffectiveClubBagResponse.self, from: data)
    }

    /// The EFFECTIVE club bag (`GET /api/v2/players/{id}/clubs/bag`): manual selection wins, else the
    /// synced Garmin bag, else empty — with per-club distances (metres) and their source.
    public func fetchEffectiveClubBag(playerId: String = "me") async throws -> EffectiveClubBagResponse {
        var request = URLRequest(url: endpointURL("/api/v2/players/\(playerId)/clubs/bag"))
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(EffectiveClubBagResponse.self, from: data)
    }

    private struct ManualBagBody: Encodable { let clubs: [ManualClubInput] }

    /// Per-hole 复盘 shot map (`GET /api/v2/history/rounds/{ref}/holes/{hole}/shotmap`): this round's
    /// actual shots projected onto the hole's 2D render. Fetched on demand when a hole is opened.
    public func fetchRoundShotMap(roundRef: String, hole: Int) async throws -> RoundHoleShotMap {
        let encoded = roundRef.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? roundRef
        var request = URLRequest(url: endpointURL("/api/v2/history/rounds/\(encoded)/holes/\(hole)/shotmap"))
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(RoundHoleShotMap.self, from: data)
    }

    /// Single-round 复盘 detail (`GET /api/v2/history/rounds/{ref}`): hole-by-hole scorecard +
    /// phase summary + graceful missing-data. Used by RoundReviewView when the player taps a round.
    public func fetchRoundDetail(roundRef: String) async throws -> RoundDetail {
        let encoded = roundRef.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? roundRef
        var request = URLRequest(url: endpointURL("/api/v2/history/rounds/\(encoded)"))
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(RoundDetail.self, from: data)
    }

    public func fetchCoursePrep(globalId: Int, render: Bool = true) async throws -> CoursePrepResponse {
        var url = endpointURL("/api/v2/courses/\(globalId)/prep")
        if !render {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
            components?.queryItems = [URLQueryItem(name: "render", value: "false")]
            url = components?.url ?? url
        }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(CoursePrepResponse.self, from: data)
    }

    /// Prep for a single hole (styled map image + overlay + strategy) — used by the live 2D map.
    public func fetchHolePrep(globalId: Int, localHole: Int) async throws -> CoursePrepHole? {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/courses/\(globalId)/prep"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [URLQueryItem(name: "holes", value: String(localHole))]
        guard let url = components.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        let prep = try decoder.decode(CoursePrepResponse.self, from: data)
        return prep.holes.first { $0.hole == localHole } ?? prep.holes.first
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
        applyAuth(to: &request)
        request.httpBody = try encoder.encode(EventBatch(roundId: roundId, events: events))

        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
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
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(EventReplayResponse.self, from: data)
    }

    public func ackEventCursor(roundId: String, serverSequence: Int) async throws -> EventCursorAckResponse {
        let url = endpointURL("/api/v2/mobile/rounds/\(roundId)/events/ack")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAuth(to: &request)
        request.httpBody = try encoder.encode(EventCursorAckRequest(clientId: clientId, serverSequence: serverSequence))

        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
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

    /// Read the LIVE session at request time (Bearer wins; admin token is the DEBUG/CI fallback).
    private func applyAuth(to request: inout URLRequest) {
        applyAICaddieAuth(to: &request, adminToken: adminToken)
    }

    private func endpointURL(_ endpoint: String) -> URL {
        let path = endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint
        return baseURL.appendingPathComponent(path)
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            AICaddieLog.network.error("Sync response was not an HTTP response")
            throw SyncClientError.notHTTPResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8)
            AICaddieLog.network.error("Sync HTTP \(http.statusCode, privacy: .public) at \(http.url?.path ?? "", privacy: .public): \(body ?? "<no body>", privacy: .public)")
            throw SyncClientError.http(status: http.statusCode, body: body)
        }
    }
}
