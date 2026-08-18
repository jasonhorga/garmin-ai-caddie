import Foundation
import AICaddieDomain
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

public struct MobileRoundFinishMetadata: Codable, Equatable {
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
}

public struct CourseGeometryHoleCoverage: Codable, Equatable {
    public let globalId: Int
    public let localHole: Int
    public let coverage: String
}

public struct CourseGeometryCoverageResponse: Codable, Equatable {
    public let schema: String
    public let globalId: Int
    public let coverage: String
    public let readyHoles: Int
    public let partialHoles: Int
    public let totalHoles: Int
    public let holes: [CourseGeometryHoleCoverage]
}

private struct MobileRoundFinishRequest: Codable {
    let meta: MobileRoundFinishMetadata
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
    /// Renderer contract shared with the phone's on-disk topo cache and Watch transfer metadata.
    /// Bump this whenever existing rendered pixels must be invalidated on installed devices.
    public static let topoStyleVersion = "topo-v8"
    /// Version only the focused View Green asset; changing it must not invalidate every course topo.
    public static let greenDetailStyleVersion = "green-v2"
    public static let greenDetailImageSize = 1024
    static let courseReleaseTimeoutInterval: TimeInterval = 180
    static let coursePackageTimeoutInterval: TimeInterval = 180
    static let courseReleaseMaximumAttempts = 3
    static let nearbyDiscoveryTimeoutInterval: TimeInterval = 30
    static let transientCourseReleaseHTTPStatuses: Set<Int> = [408, 425, 429, 500, 502, 503, 504]

    /// The configured API base (e.g. `https://caddie…ts.net`). Public so views can build the
    /// no-auth topo bitmap URL (see `topoImageURL(baseURL:globalId:localHole:)`).
    public let baseURL: URL
    private let adminToken: String?
    private let clientId: String
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private let retrySleep: (UInt64) async throws -> Void

    public init(baseURL: URL, adminToken: String? = nil, clientId: String = "ios-phone", session: URLSession = .shared) {
        self.baseURL = baseURL
        self.adminToken = adminToken
        self.clientId = clientId
        self.session = session
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
        self.retrySleep = { try await Task.sleep(nanoseconds: $0) }
    }

    init(
        baseURL: URL,
        adminToken: String? = nil,
        clientId: String = "ios-phone",
        session: URLSession = .shared,
        retrySleep: @escaping (UInt64) async throws -> Void
    ) {
        self.baseURL = baseURL
        self.adminToken = adminToken
        self.clientId = clientId
        self.session = session
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
        self.retrySleep = retrySleep
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
        if ensureGeometry {
            request.timeoutInterval = 900
        }
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(LiveRoundPackage.self, from: data)
    }

    public func fetchCoursePackage(globalId: Int, roundId: String, teeBox: String, nine: String = "all", capturedAt: Date = Date(), ensureGeometry: Bool = false, backgroundGeometry: Bool = false, backGlobalId: Int? = nil, includeEventCursor: Bool = true) async throws -> LiveRoundPackage {
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
            URLQueryItem(name: "background_geometry", value: backgroundGeometry ? "true" : "false"),
            URLQueryItem(name: "include_event_cursor", value: includeEventCursor ? "true" : "false"),
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
        // A first start for an arbitrary Garmin course has to fetch its factual courseData map.
        // Under concurrent all-hole downloads that cold path has exceeded URLSession's 60-second
        // default even though the server completed and cached it moments later. Keep the precise
        // geometry window, and give the lightweight package the same bounded cold-course window as
        // Tee metadata. This GET is idempotent, so a transient timeout can safely retry and then hit
        // the completed server cache.
        request.timeoutInterval = ensureGeometry ? 900 : Self.coursePackageTimeoutInterval
        applyAuth(to: &request)
        let data = try await fetchRetriableGetData(request)
        return try decoder.decode(LiveRoundPackage.self, from: data)
    }

    public func fetchCourseOptions() async throws -> MobileCourseOptionsResponse {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/courses/options"))
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(MobileCourseOptionsResponse.self, from: data)
    }

    /// Search Garmin's full CourseView catalogue by name. This downloads metadata only; choosing a
    /// row later uses `fetchCourseTees` and `fetchCoursePackage` for that one course.
    public func searchCourses(
        name: String,
        city: String? = nil,
        latitude: Double? = nil,
        longitude: Double? = nil
    ) async throws -> [MobileCourseSearchMatch] {
        let query = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.count >= 2 else { return [] }
        guard var components = URLComponents(
            url: endpointURL("/api/v2/courses/search"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [URLQueryItem(name: "name", value: query)]
        if let city = city?.trimmingCharacters(in: .whitespacesAndNewlines),
           city.count >= 2 {
            components.queryItems?.append(URLQueryItem(name: "city", value: city))
        }
        if let latitude, let longitude,
           latitude.isFinite, (-90...90).contains(latitude),
           longitude.isFinite, (-180...180).contains(longitude) {
            components.queryItems?.append(URLQueryItem(name: "latitude", value: String(latitude)))
            components.queryItems?.append(URLQueryItem(name: "longitude", value: String(longitude)))
        }
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        // Catalogue search is a small, idempotent metadata read. Give Funnel/DNS/TLS a bounded
        // budget and use the same transient-only retry policy as nearby discovery. In particular,
        // a one-off TLS transport handshake failure may retry; certificate validation failures may
        // not (see `isTransientCourseReleaseError`).
        request.timeoutInterval = Self.nearbyDiscoveryTimeoutInterval
        applyAuth(to: &request)
        let data = try await fetchRetriableGetData(request)
        return try decoder.decode(MobileCourseSearchResponse.self, from: data).matches
    }

    /// Discover every Garmin catalogue row around the current coordinate. Like name search this is
    /// metadata-only; Tee, holes and maps are fetched only after the player selects one row.
    public func nearbyCourses(
        latitude: Double,
        longitude: Double,
        radiusKm: Int = 50
    ) async throws -> [MobileCourseSearchMatch] {
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              (1...200).contains(radiusKm) else {
            throw URLError(.badURL)
        }
        guard var components = URLComponents(
            url: endpointURL("/api/v2/courses/nearby"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [
            URLQueryItem(name: "latitude", value: String(latitude)),
            URLQueryItem(name: "longitude", value: String(longitude)),
            URLQueryItem(name: "radius_km", value: String(radiusKm)),
        ]
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        // The backend bounds its Garmin pagination to 12 s and can return an explicitly marked
        // partial/cache result. Leave enough transport budget for that response plus Funnel/DNS
        // latency, then retry the idempotent GET using the transient-only metadata policy.
        request.timeoutInterval = Self.nearbyDiscoveryTimeoutInterval
        applyAuth(to: &request)
        let data = try await fetchRetriableGetData(request)
        return try decoder.decode(MobileNearbyCoursesResponse.self, from: data).matches
    }

    /// The course's selectable tee boxes (`GET /api/v2/courses/{id}/tees`): colour + total yards +
    /// which is default — the pre-round picker list, same as Garmin's new-round tee chooser. Public
    /// course knowledge (no player data); powers 开始一场's 发球台 selector with real yardage.
    public func fetchCourseTees(globalId: Int) async throws -> CourseTeesResponse {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/courses/\(globalId)/tees"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [URLQueryItem(name: "ensure_release", value: "true")]
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        // On the first use of an un-cached course the server may need to fetch and validate Garmin's
        // CourseView release. Give that explicit download action longer than URLSession's 60 s
        // default, and retry only failures that are safe for this idempotent GET.
        request.timeoutInterval = Self.courseReleaseTimeoutInterval
        applyAuth(to: &request)
        let data = try await fetchRetriableGetData(request)
        return try decoder.decode(CourseTeesResponse.self, from: data)
    }

    /// Compact 统计 payload (`GET /api/v2/history/stats/mobile`): basic / deep / periodic / course /
    /// club slices of the full stats build (~180KB, not the ~11MB full one). Used by StatsView.
    public func fetchMobileStats(window: String = "all") async throws -> MobileStats {
        let allowed = ["all", "12m", "last20", "last10"]
        let selected = allowed.contains(window) ? window : "all"
        var components = URLComponents(url: endpointURL("/api/v2/history/stats/mobile"), resolvingAgainstBaseURL: false)
        if selected != "all" { components?.queryItems = [URLQueryItem(name: "window", value: selected)] }
        guard let url = components?.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(MobileStats.self, from: data)
    }

    /// Full historical archive. Filters are server-side so a period/course drill-down
    /// reuses the same canonical round list instead of reconstructing it from stats refs.
    public func fetchHistoryRounds(
        year: String? = nil,
        course: String? = nil,
        hasShots: Bool? = nil,
        period: String? = nil,
        scoreBand: String? = nil,
        search: String? = nil,
        limit: Int = 2000
    ) async throws -> HistoryRoundsArchive {
        var components = URLComponents(url: endpointURL("/api/v2/history/rounds"), resolvingAgainstBaseURL: false)
        var items = [URLQueryItem(name: "limit", value: String(max(1, min(limit, 2000))))]
        if let year, !year.isEmpty { items.append(URLQueryItem(name: "year", value: year)) }
        if let course, !course.isEmpty { items.append(URLQueryItem(name: "course", value: course)) }
        if let hasShots { items.append(URLQueryItem(name: "hasShots", value: hasShots ? "true" : "false")) }
        if let period, !period.isEmpty { items.append(URLQueryItem(name: "period", value: period)) }
        if let scoreBand, !scoreBand.isEmpty { items.append(URLQueryItem(name: "scoreBand", value: scoreBand)) }
        if let search, !search.isEmpty { items.append(URLQueryItem(name: "search", value: search)) }
        components?.queryItems = items
        guard let url = components?.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(HistoryRoundsArchive.self, from: data)
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
    /// actual shots projected onto the hole's 2D render. The round screen prefetches all holes, so
    /// omit the duplicate embedded topo; its revision-bound PNG is fetched once through URLCache.
    public func fetchRoundShotMap(roundRef: String, hole: Int) async throws -> RoundHoleShotMap {
        let encoded = roundRef.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? roundRef
        let endpoint = endpointURL("/api/v2/history/rounds/\(encoded)/holes/\(hole)/shotmap")
        guard var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false) else {
            throw URLError(.badURL)
        }
        components.queryItems = [URLQueryItem(name: "includeImage", value: "false")]
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decoder.decode(RoundHoleShotMap.self, from: data)
    }

    /// Append one review-edit op to a round (`POST /api/v2/history/rounds/{ref}/corrections`): add /
    /// edit / delete a shot, drag a landing, reorder, or set a hole's manual penalty. Writes to the
    /// caller's own correction log (member-scoped), idempotent on `clientMutationId`. Succeeds (no
    /// throw) on 2xx; the read-side shotmap applies the op on the next fetch. Original data untouched.
    public func postRoundCorrection(roundRef: String, _ op: RoundCorrectionOp) async throws {
        let encoded = roundRef.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? roundRef
        var request = URLRequest(url: endpointURL("/api/v2/history/rounds/\(encoded)/corrections"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAuth(to: &request)
        request.httpBody = try encoder.encode(op)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
    }

    /// Single-round 复盘 detail (`GET /api/v2/history/rounds/{ref}`): hole-by-hole scorecard +
    /// phase summary + graceful missing-data. Used by RoundReviewView when the player taps a round.
    public func fetchRoundDetail(roundRef: String) async throws -> RoundDetail {
        let encoded = roundRef.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? roundRef
        var request = URLRequest(url: endpointURL("/api/v2/history/rounds/\(encoded)"))
        applyAuth(to: &request)
        // A round review should not become a permanent error screen because its first idempotent
        // GET crossed a one-off Funnel/DNS/TLS interruption. Reuse the bounded transient-only
        // policy used by course discovery: 404/auth/certificate failures still fail immediately.
        let data = try await fetchRetriableGetData(request)
        return try decoder.decode(RoundDetail.self, from: data)
    }

    public func fetchCoursePrep(
        globalId: Int,
        holes: [Int]? = nil,
        render: Bool = true
    ) async throws -> CoursePrepResponse {
        var url = endpointURL("/api/v2/courses/\(globalId)/prep")
        if holes != nil || !render {
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
            components?.queryItems = (holes ?? []).map {
                URLQueryItem(name: "holes", value: String($0))
            }
            if !render {
                components?.queryItems?.append(URLQueryItem(name: "render", value: "false"))
            }
            url = components?.url ?? url
        }
        var request = URLRequest(url: url)
        // Multi-hole lightweight prep drives both progressive 备战 and the whole-course offline
        // installer. Three real Garmin meshes can legitimately exceed URLSession's 60-second
        // default while the shared server is finishing cold geometry. Let the bounded request
        // finish once instead of repeating the same expensive batch and delaying every topo.
        request.timeoutInterval = 180
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        // Offline course installation intentionally issues a few bounded prep batches in parallel.
        // JSONDecoder has mutable decoding state and is not documented as safe for concurrent use;
        // keep this read path local rather than sharing the client's general-purpose decoder.
        return try JSONDecoder().decode(CoursePrepResponse.self, from: data)
    }

    /// Cheap readiness probe for a background CourseView geometry upgrade.  Unlike `/prep`, this
    /// reads file presence only, so an offline install can wait for newly-ready holes without
    /// repeatedly rebuilding the same partial route/hazard payloads.
    public func fetchCourseGeometryCoverage(
        globalId: Int,
        holes: [Int]
    ) async throws -> CourseGeometryCoverageResponse {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/geometry/course/\(globalId)/coverage"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = holes.map {
            URLQueryItem(name: "holes", value: String($0))
        }
        guard let url = components.url else { throw URLError(.badURL) }
        let (data, response) = try await session.data(for: URLRequest(url: url))
        try validate(response: response, data: data)
        return try JSONDecoder().decode(CourseGeometryCoverageResponse.self, from: data)
    }

    /// Prep for one hole. The default lightweight response carries factual geometry plus topo
    /// projection anchors; callers may explicitly request the legacy embedded rendered bitmap.
    public func fetchHolePrep(globalId: Int, localHole: Int, render: Bool = false) async throws -> CoursePrepHole? {
        guard var components = URLComponents(
            url: endpointURL("/api/v2/courses/\(globalId)/prep"),
            resolvingAgainstBaseURL: false
        ) else {
            throw URLError(.badURL)
        }
        components.queryItems = [URLQueryItem(name: "holes", value: String(localHole))]
        if !render {
            components.queryItems?.append(URLQueryItem(name: "render", value: "false"))
        }
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

    /// Download one public realistic-topo PNG through the client's injected URLSession so offline
    /// asset caching is deterministic in tests and shares the normal transport/cancellation rules.
    public func fetchTopoImage(
        globalId: Int,
        localHole: Int,
        geometryRevision: String? = nil
    ) async throws -> Data {
        guard let url = Self.topoImageURL(
            baseURL: baseURL,
            globalId: globalId,
            localHole: localHole,
            geometryRevision: geometryRevision
        ) else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        let pngSignature = Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        guard data.starts(with: pngSignature) else {
            throw URLError(.cannotDecodeContentData)
        }
        return data
    }

    public func fetchGreenDetailImage(
        globalId: Int,
        localHole: Int,
        crop: GreenDetailCrop,
        size: Int = SyncClient.greenDetailImageSize,
        geometryRevision: String? = nil
    ) async throws -> Data {
        guard let url = Self.greenDetailImageURL(
            baseURL: baseURL,
            globalId: globalId,
            localHole: localHole,
            crop: crop,
            size: size,
            geometryRevision: geometryRevision
        ) else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        applyAuth(to: &request)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        let pngSignature = Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        guard data.starts(with: pngSignature) else { throw URLError(.cannotDecodeContentData) }
        return data
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

    public func finishRound(
        roundId: String,
        metadata: MobileRoundFinishMetadata
    ) async throws {
        var request = URLRequest(url: endpointURL("/api/v2/mobile/rounds/\(roundId)/finish"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAuth(to: &request)
        request.httpBody = try encoder.encode(MobileRoundFinishRequest(meta: metadata))
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
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

    /// Public (no-auth) realistic-topo bitmap URL for a course hole:
    /// `…/api/v2/courses/{globalId}/holes/{localHole}/topo.png` (mirrors web `topoImageUrl`).
    /// Returns nil for the placeholder gid `0` or a non-positive hole (no real CourseView geometry →
    /// the caller keeps the flat render). The endpoint 404s when the mesh is absent → the base-image
    /// layer degrades to the fallback at load time.
    public static func topoImageURL(
        baseURL: URL,
        globalId: Int,
        localHole: Int,
        geometryRevision: String? = nil
    ) -> URL? {
        guard globalId != 0, localHole > 0 else { return nil }
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent("api/v2/courses/\(globalId)/holes/\(localHole)/topo.png"),
            resolvingAgainstBaseURL: false
        ) else {
            return nil
        }
        // Separate renderer styles at the URL layer. The server ETag also binds the current
        // Garmin geometry asset, so an updated course cannot reuse an older topo bitmap.
        var queryItems = [URLQueryItem(name: "v", value: topoStyleVersion)]
        if let revision = geometryRevision?.trimmingCharacters(in: .whitespacesAndNewlines),
           !revision.isEmpty {
            queryItems.append(URLQueryItem(name: "r", value: revision))
        }
        components.queryItems = queryItems
        return components.url
    }

    /// Public high-resolution View Green window. The crop is in the same full-hole display-pixel
    /// frame as `holeImageProjection`; the server re-renders that window from decoded geometry
    /// instead of enlarging a few pixels from `topo.png`.
    public static func greenDetailImageURL(
        baseURL: URL,
        globalId: Int,
        localHole: Int,
        crop: GreenDetailCrop,
        size: Int = SyncClient.greenDetailImageSize,
        geometryRevision: String? = nil
    ) -> URL? {
        guard globalId != 0, localHole > 0 else { return nil }
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent("api/v2/courses/\(globalId)/holes/\(localHole)/green.png"),
            resolvingAgainstBaseURL: false
        ) else { return nil }
        func number(_ value: Double) -> String {
            String(format: "%.1f", locale: Locale(identifier: "en_US_POSIX"), value)
        }
        var queryItems = [
            URLQueryItem(name: "x", value: number(crop.x)),
            URLQueryItem(name: "y", value: number(crop.y)),
            URLQueryItem(name: "width", value: number(crop.width)),
            URLQueryItem(name: "height", value: number(crop.height)),
            URLQueryItem(name: "size", value: String(size)),
            URLQueryItem(name: "v", value: topoStyleVersion),
            URLQueryItem(name: "g", value: greenDetailStyleVersion),
        ]
        if let revision = geometryRevision?.trimmingCharacters(in: .whitespacesAndNewlines),
           !revision.isEmpty {
            queryItems.append(URLQueryItem(name: "r", value: revision))
        }
        components.queryItems = queryItems
        return components.url
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

    private func fetchRetriableGetData(_ request: URLRequest) async throws -> Data {
        var attempt = 1
        while true {
            try Task.checkCancellation()
            do {
                let (data, response) = try await session.data(for: request)
                try validate(response: response, data: data)
                return data
            } catch {
                if Task.isCancelled || error is CancellationError {
                    throw CancellationError()
                }
                guard attempt < Self.courseReleaseMaximumAttempts,
                      Self.isTransientCourseReleaseError(error) else {
                    throw error
                }
                try await retrySleep(Self.courseReleaseRetryDelayNanoseconds(afterAttempt: attempt))
                attempt += 1
            }
        }
    }

    static func courseReleaseRetryDelayNanoseconds(afterAttempt attempt: Int) -> UInt64 {
        UInt64(1 << max(0, min(attempt - 1, 4))) * 500_000_000
    }

    static func isTransientCourseReleaseError(_ error: Error) -> Bool {
        if error is CancellationError { return false }
        if let syncError = error as? SyncClientError,
           case let .http(status, _) = syncError {
            return transientCourseReleaseHTTPStatuses.contains(status)
        }
        guard let urlError = error as? URLError else { return false }
        switch urlError.code {
        case .timedOut, .cannotFindHost, .cannotConnectToHost, .networkConnectionLost,
             .dnsLookupFailed, .notConnectedToInternet, .secureConnectionFailed:
            return true
        default:
            return false
        }
    }
}
