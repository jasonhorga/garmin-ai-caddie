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
    public let acceptedEventIds: [String]
    public let duplicateEventIds: [String]
    public let serverSequence: Int

    public var acknowledgedEventIds: [String] {
        acceptedEventIds + duplicateEventIds
    }
}

public struct WatchRoundFinishMetadata: Equatable {
    public let courseName: String
    public let holePars: [Int]
    public let holesCompleted: Int
    public let courseGlobalId: Int?

    public init(
        courseName: String,
        holePars: [Int],
        holesCompleted: Int,
        courseGlobalId: Int?
    ) {
        self.courseName = courseName
        self.holePars = holePars
        self.holesCompleted = holesCompleted
        self.courseGlobalId = courseGlobalId
    }

    fileprivate var jsonObject: [String: Any] {
        var value: [String: Any] = [
            "courseName": courseName,
            "holePars": holePars,
            "holesCompleted": holesCompleted,
        ]
        if let courseGlobalId {
            value["courseGlobalId"] = courseGlobalId
        }
        return value
    }
}

public enum WatchBackendClientError: Error {
    case invalidShotLocation
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
    public func backendEvent(from event: WatchInputEvent) throws -> [String: Any] {
        let kind: String
        var payload: [String: Any]
        switch event.kind {
        case .score:
            kind = "score"
            payload = ["strokes": Int(event.value) ?? 0]
            if let fairway = normalizedFairway(event.fairwayResult) {
                payload["fairway"] = fairway
            }
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
        case .location:
            guard let location = WatchShotLocationValue(encodedValue: event.value) else {
                throw WatchBackendClientError.invalidShotLocation
            }
            kind = "location"
            payload = [
                "latitude": location.latitude,
                "longitude": location.longitude,
                "horizontalAccuracyM": location.horizontalAccuracyM,
                "source": "apple_watch",
            ]
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

    private func normalizedFairway(_ value: String?) -> String? {
        guard let value else { return nil }
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return ["hit", "left", "right"].contains(normalized) ? normalized : nil
    }

    // MARK: - Endpoints (mirror the phone SyncClient event surface)

    public func makeCourseOptionsRequest() throws -> URLRequest {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/courses/options"))
        applyAuth(&request)
        return request
    }

    public func makeCoursePackageRequest(
        globalId: Int,
        roundId: String,
        teeBox: String
    ) throws -> URLRequest {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/mobile/courses/\(globalId)/package"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [
            URLQueryItem(name: "round_id", value: roundId),
            URLQueryItem(name: "tee_box", value: teeBox),
            URLQueryItem(name: "nine", value: "all"),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "ensure_geometry", value: "false"),
        ]
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        applyAuth(&request)
        return request
    }

    public func makeCoursePrepRequest(globalId: Int, localHoles: [Int]) throws -> URLRequest {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/courses/\(globalId)/prep"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = localHoles.map {
            URLQueryItem(name: "holes", value: String($0))
        } + [URLQueryItem(name: "render", value: "true")]
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        applyAuth(&request)
        return request
    }

    public func decodeCourseOptions(_ data: Data) throws -> [WatchCourseOption] {
        try JSONDecoder().decode(WatchCourseOptionsEnvelope.self, from: data).courses
    }

    public func decodeCoursePackage(_ data: Data) throws -> WatchCoursePackage {
        try JSONDecoder().decode(WatchCoursePackage.self, from: data)
    }

    public func decodeCoursePrep(_ data: Data) throws -> WatchCoursePrepResponse {
        try JSONDecoder().decode(WatchCoursePrepResponse.self, from: data)
    }

    public func fetchCourseOptions() async throws -> [WatchCourseOption] {
        let request = try makeCourseOptionsRequest()
        let data = try await sendForData(request)
        return try decodeCourseOptions(data)
    }

    public func fetchCoursePackage(
        globalId: Int,
        roundId: String,
        teeBox: String
    ) async throws -> WatchCoursePackage {
        let request = try makeCoursePackageRequest(globalId: globalId, roundId: roundId, teeBox: teeBox)
        let data = try await sendForData(request)
        return try decodeCoursePackage(data)
    }

    public func fetchCoursePrep(globalId: Int, localHoles: [Int]) async throws -> WatchCoursePrepResponse {
        let request = try makeCoursePrepRequest(globalId: globalId, localHoles: localHoles)
        let data = try await sendForData(request)
        return try decodeCoursePrep(data)
    }

    /// Build the POST /events request (headers + mapped batch body). Split out from `postEvents` so it
    /// can be unit-tested without a URLSession — watchOS makes URLProtocol stubbing of the live session
    /// unreliable, so the request construction (the meaningful logic) is verified directly instead.
    public func makeEventBatchRequest(_ events: [WatchInputEvent], roundId: String, idempotencyKey: String) throws -> URLRequest {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/rounds/\(roundId)/events"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        applyAuth(&request)
        let body: [String: Any] = ["roundId": roundId, "events": try events.map { try backendEvent(from: $0) }]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return request
    }

    public func makeRoundFinishRequest(
        roundId: String,
        metadata: WatchRoundFinishMetadata
    ) throws -> URLRequest {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/rounds/\(roundId)/finish"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAuth(&request)
        request.httpBody = try JSONSerialization.data(withJSONObject: ["meta": metadata.jsonObject])
        return request
    }

    public func parseEventResult(_ data: Data) -> WatchBackendEventResult {
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        return WatchBackendEventResult(
            accepted: json["accepted"] as? Int ?? 0,
            duplicate: json["duplicate"] as? Bool ?? false,
            acceptedEventIds: json["acceptedEventIds"] as? [String] ?? [],
            duplicateEventIds: json["duplicateEventIds"] as? [String] ?? [],
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

    public func finishRound(
        roundId: String,
        metadata: WatchRoundFinishMetadata
    ) async throws {
        let request = try makeRoundFinishRequest(roundId: roundId, metadata: metadata)
        _ = try await sendForJSON(request)
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
            return
        }
        // DEBUG/CI ONLY: the admin token is the dev/simulator fallback. The Release watch authenticates
        // ONLY with the phone-pushed Apple `sessionToken` (round-13 watch-auth) and never receives an
        // admin token (the phone compiles out the send), so this branch is compiled out of consumer
        // builds — a Release request without a live session token carries no auth header.
        #if DEBUG
        if let adminToken {
            request.setValue(adminToken, forHTTPHeaderField: "X-AI-Caddie-Admin-Token")
        }
        #endif
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
        let data = try await sendForData(request)
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    private func sendForData(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    private func endpointURL(_ endpoint: String) -> URL {
        let path = endpoint.hasPrefix("/") ? String(endpoint.dropFirst()) : endpoint
        return baseURL.appendingPathComponent(path)
    }
}
