import Foundation

/// round-12 P3 (Watch standalone): the Apple Watch talking to the AI Caddie backend DIRECTLY over
/// HTTP, so a round can be recorded on the watch without the phone relaying. This is the network
/// foundation for the standalone Watch app — the lifecycle/UI (start/score/finish) + offline log are
/// layered on top in later steps.
///
/// Events are stamped with clientId "apple-watch" so the sync spine (round-12 P2.1/P2.2) dedups them
/// per-client and the server projection attributes them correctly alongside phone/web events.
public struct WatchBackendEventResult: Equatable {
    public let accepted: Int
    public let duplicate: Bool
    public let serverSequence: Int
}

public final class WatchBackendClient {
    private let baseURL: URL
    private let adminToken: String?
    private let sessionToken: String?
    private let sessionTokenExpiresAt: Date?
    private let clientId: String
    private let session: URLSession

    public init(
        baseURL: URL,
        adminToken: String? = nil,
        sessionToken: String? = nil,
        sessionTokenExpiresAt: Date? = nil,
        clientId: String = "apple-watch",
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.adminToken = adminToken
        self.sessionToken = sessionToken
        self.sessionTokenExpiresAt = sessionTokenExpiresAt
        self.clientId = clientId
        self.session = session
    }

    // MARK: - WatchInputEvent → backend live-round-event wire dict

    /// Mirror of the phone's `WatchEventBridge.mapWatchInputEvent`, but emits the JSON wire dict the
    /// `/events` endpoint accepts (stamped with this client's id). Keeping the mapping here lets the
    /// watch post on its own when the phone is unreachable.
    public func backendEvent(from event: WatchInputEvent) -> [String: Any] {
        let kind: String
        var payload: [String: Any]
        switch event.kind {
        case .score:
            kind = "score"
            payload = ["strokes": Int(event.value) ?? 0]
        case .putt:
            kind = "putt"
            payload = ["putts": Int(event.value) ?? 0]
        case .penalty:
            kind = "penalty"
            payload = ["penalties": Int(event.value) ?? 0]
        case .club:
            kind = "club"
            payload = clubPayload(for: event, clubName: event.contextClub ?? event.value)
        case .distance:
            // A distance input is recorded as a club event carrying the new to-pin distance.
            kind = "club"
            payload = clubPayload(for: event, clubName: event.contextClub ?? event.value)
            payload["distanceToPinM"] = Double(event.value) ?? 0
        }
        return [
            "schema": "ai-caddie-live-round-event-v1",
            "eventId": event.eventId,
            "roundId": event.roundId,
            "clientId": clientId,
            "timestamp": event.createdAt,
            "hole": event.hole,
            "kind": kind,
            "payload": payload,
        ]
    }

    private func clubPayload(for event: WatchInputEvent, clubName: String) -> [String: Any] {
        var payload: [String: Any] = ["clubName": clubName]
        if let shotType = event.shotType { payload["shotType"] = shotType }
        if let strategyMode = event.strategyMode { payload["strategyMode"] = strategyMode }
        if let lie = event.lie { payload["lie"] = lie }
        if let distanceToPinM = event.distanceToPinM { payload["distanceToPinM"] = distanceToPinM }
        if let offlineOptionId = event.offlineOptionId { payload["offlineOptionId"] = offlineOptionId }
        if let decisionId = event.decisionId { payload["decisionId"] = decisionId }
        return payload
    }

    // MARK: - Endpoints (mirror the phone SyncClient event surface)

    /// Build the POST /events request (headers + mapped batch body). Split out from `postEvents` so it
    /// can be unit-tested without a URLSession — watchOS makes URLProtocol stubbing of the live session
    /// unreliable, so the request construction (the meaningful logic) is verified directly instead.
    public func makeEventBatchRequest(_ events: [WatchInputEvent], roundId: String, idempotencyKey: String) throws -> URLRequest {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/rounds/\(roundId)/events"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        applyAuth(&request)
        let body: [String: Any] = ["roundId": roundId, "events": events.map { backendEvent(from: $0) }]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return request
    }

    public func parseEventResult(_ data: Data) -> WatchBackendEventResult {
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        return WatchBackendEventResult(
            accepted: json["accepted"] as? Int ?? 0,
            duplicate: json["duplicate"] as? Bool ?? false,
            serverSequence: json["serverSequence"] as? Int ?? 0
        )
    }

    @discardableResult
    public func postEvents(_ events: [WatchInputEvent], roundId: String, idempotencyKey: String) async throws -> WatchBackendEventResult {
        let request = try makeEventBatchRequest(events, roundId: roundId, idempotencyKey: idempotencyKey)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return parseEventResult(data)
    }

    /// Pull events authored by other clients (phone/web) so the watch round stays in sync.
    public func fetchEventReplay(roundId: String, afterSequence: Int? = nil, limit: Int = 200) async throws -> [String: Any] {
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
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        applyAuth(&request)
        return try await sendForJSON(request)
    }

    @discardableResult
    public func ackEventCursor(roundId: String, serverSequence: Int) async throws -> [String: Any] {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/rounds/\(roundId)/events/ack"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAuth(&request)
        request.httpBody = try JSONSerialization.data(withJSONObject: ["clientId": clientId, "serverSequence": serverSequence])
        return try await sendForJSON(request)
    }

    // MARK: - helpers

    // member-auth (resolved): the watch target has no SessionStore / Apple sign-in, so it cannot read
    // a member's session token itself. Instead the phone pushes its live Apple session token over
    // WCSession (WatchEventBridge.sendConfigToWatch → WatchRoundConfig.sessionToken). We prefer that as
    // an `Authorization: Bearer` header — mirroring the phone's `applyAICaddieAuth` precedence — so the
    // watch's standalone sync authenticates as the signed-in member/owner and the backend scopes the
    // writes to their own partition (current_player_id). The admin token survives only as the DEBUG/CI
    // fallback. On sign-out the phone re-pushes config WITHOUT a session token, so the watch drops the
    // Bearer and falls back to admin/none (unauthenticated) rather than reusing a stale token.
    private func applyAuth(_ request: inout URLRequest) {
        if let token = liveSessionToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        } else if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
    }

    /// The pushed session token, honored only until it expires — mirrors the phone's
    /// `SessionStore.liveToken` so the watch never authenticates with an expired Bearer. A nil expiry
    /// means "no known expiry" and is treated as live (matching the phone, whose `liveToken` returns
    /// the token when its expiry is nil).
    private var liveSessionToken: String? {
        guard let sessionToken, !sessionToken.isEmpty else { return nil }
        if let sessionTokenExpiresAt, sessionTokenExpiresAt <= Date() { return nil }
        return sessionToken
    }

    private func sendForJSON(_ request: URLRequest) async throws -> [String: Any] {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    private func endpointURL(_ endpoint: String) -> URL {
        let path = endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint
        return baseURL.appendingPathComponent(path)
    }
}
