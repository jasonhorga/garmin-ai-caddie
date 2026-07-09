import Foundation
import WatchConnectivity

public enum WatchInputKind: String, Codable, Equatable {
    case score
    case putt
    case penalty
    case club
    case distance
}

public struct WatchClubOption: Codable, Equatable, Identifiable {
    public var id: String { clubName }

    public let clubName: String
    public let sampleSize: Int?
    public let medianM: Double?
    public let source: String?

    public init(
        clubName: String,
        sampleSize: Int? = nil,
        medianM: Double? = nil,
        source: String? = nil
    ) {
        self.clubName = clubName
        self.sampleSize = sampleSize
        self.medianM = medianM
        self.source = source
    }
}

/// round-13 spec ⑤: a 障碍 carry interval pushed to the watch Hazard View. Mirrors the watch-side
/// WatchHazard (same JSON shape); distances are along-route metres, the watch converts to 码.
public struct WatchHazard: Codable, Equatable, Identifiable {
    public var id: String { "\(kind)-\(label)" }

    public let kind: String     // "bunker" | "water"
    public let label: String    // 中文,如「沙坑 1」「水域」
    public let startM: Double?
    public let endM: Double?

    public init(kind: String, label: String, startM: Double? = nil, endM: Double? = nil) {
        self.kind = kind
        self.label = label
        self.startM = startM
        self.endM = endM
    }
}

/// round-13 spec ②: one AI-caddie play option (激进/推荐/保守) pushed to the watch 球童打法 screen.
/// Mirrors the watch-side WatchCaddieOption (same JSON shape). No success-% (intentionally absent).
public struct WatchCaddieOption: Codable, Equatable, Identifiable {
    public var id: String { optionId }

    public let optionId: String
    public let label: String
    public let clubName: String?
    public let carryM: Double?
    public let expectedStrokes: Double?
    public let confidence: String?

    public init(
        optionId: String,
        label: String,
        clubName: String? = nil,
        carryM: Double? = nil,
        expectedStrokes: Double? = nil,
        confidence: String? = nil
    ) {
        self.optionId = optionId
        self.label = label
        self.clubName = clubName
        self.carryM = carryM
        self.expectedStrokes = expectedStrokes
        self.confidence = confidence
    }
}

public struct WatchInputEvent: Codable, Equatable, Identifiable {
    public var id: String { eventId }

    public let schema: String = "ai-caddie-watch-input-event-v1"
    public let eventId: String
    public let roundId: String
    public let hole: Int
    public let kind: WatchInputKind
    public let value: String
    public let createdAt: String
    public let contextClub: String?
    public let shotType: String?
    public let strategyMode: String?
    public let lie: String?
    public let distanceToPinM: Double?
    public let offlineOptionId: String?
    public let decisionId: String?

    public init(
        eventId: String,
        roundId: String,
        hole: Int,
        kind: WatchInputKind,
        value: String,
        createdAt: String,
        contextClub: String? = nil,
        shotType: String? = nil,
        strategyMode: String? = nil,
        lie: String? = nil,
        distanceToPinM: Double? = nil,
        offlineOptionId: String? = nil,
        decisionId: String? = nil
    ) {
        self.eventId = eventId
        self.roundId = roundId
        self.hole = hole
        self.kind = kind
        self.value = value
        self.createdAt = createdAt
        self.contextClub = contextClub
        self.shotType = shotType
        self.strategyMode = strategyMode
        self.lie = lie
        self.distanceToPinM = distanceToPinM
        self.offlineOptionId = offlineOptionId
        self.decisionId = decisionId
    }
}

// watch P0.2 (phone-side mirror of the watch's WatchHoleImageProjection; same JSON keys).
public struct WatchProjectionRef: Codable, Equatable {
    public let lat: Double
    public let lon: Double
    public let px: Double
    public let py: Double
}

public struct WatchHoleImageProjection: Codable, Equatable {
    public let widthPx: Int?
    public let heightPx: Int?
    public let refs: [WatchProjectionRef]?
}

// watch P1b: the five hole-map overlay anchors (in /topo.png px space) the phone pre-computes from the
// hole's centreline route, so the watch just draws the cached image + anchors. Mirrors WatchHoleMap on
// the watch target (matched by JSON keys). Each point is `[px, py]`.
public struct WatchHoleMap: Codable, Equatable {
    public let w: Int
    public let h: Int
    public let you: [Double]
    public let pin: [Double]
    public let layup: [Double]
    public let apex: [Double]
    public let greenCtrl: [Double]
}

public struct WatchRoundStatePayload: Codable, Equatable {
    public let schema: String = "ai-caddie-watch-round-state-v1"
    public let roundId: String
    public let hole: Int
    public let par: Int
    public let distanceM: Double?
    public let targetNote: String?
    public let targetLatitude: Double?
    public let targetLongitude: Double?
    public let targetKind: String?
    public let suggestedClub: String?
    public let selectedClub: String?
    public let availableClubs: [WatchClubOption]
    public let shotType: String?
    public let strategyMode: String?
    public let lie: String?
    public let offlineOptionId: String?
    public let decisionId: String?
    public let nextShotPrompt: String?
    public let holePlanSummary: String?
    public let expectedStrokes: Double?
    public let expectedRemainingM: Double?
    public let evidenceSummary: String?
    public let missingDataSummary: String?
    // round-13 E4: Apple Watch live-screen fields (mirror WatchRoundState). Additive/optional;
    // populated by a later UI PR — the builder defaults them to nil so existing call sites compile.
    public let frontGreenM: Double?
    public let centerGreenM: Double?
    public let backGreenM: Double?
    // watch P0.2: green F/M/B WGS84 coords + topo geo→px projection (mirror WatchRoundState keys).
    public let frontGreenLat: Double?
    public let frontGreenLon: Double?
    public let centerGreenLat: Double?
    public let centerGreenLon: Double?
    public let backGreenLat: Double?
    public let backGreenLon: Double?
    public let holeImageProjection: WatchHoleImageProjection?
    // watch P1b: course global id (image-cache key) + pre-computed hole-map overlay anchors.
    public let globalId: Int?
    public let holeMap: WatchHoleMap?
    public let playsLikeDistanceM: Double?
    public let elevationDeltaM: Double?
    public let lastShotDistanceM: Double?
    public let distanceFromLastShotM: Double?
    public let greenInRegulation: Bool?
    public let fairwayResult: String?
    public let geometryCoverage: String?
    public let caddieOptions: [WatchCaddieOption]
    public let hazards: [WatchHazard]
    public let score: Int
    public let putts: Int
    public let penaltyCount: Int
    public let caddieConfidence: String
}

public enum WatchEventBridgeError: Error {
    case invalidNumericInput
    case missingClubContext
}

public final class WatchEventBridge: NSObject {
    public var onAcceptedLiveEvent: ((LiveRoundEvent) async throws -> Void)?

    private let offlineStore: OfflineStore
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    /// Latest backend config to hand the watch; re-pushed once the session activates (round-12 P3.4).
    private var pendingConfig: [String: Any]?

    public init(offlineStore: OfflineStore = OfflineStore(), autoActivate: Bool = false) {
        self.offlineStore = offlineStore
        super.init()
        if autoActivate {
            activateSession()
        }
    }

    public func activateSession() {
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    public func mapWatchInputEvent(_ event: WatchInputEvent) throws -> LiveRoundEvent {
        switch event.kind {
        case .score:
            return liveEvent(event, kind: .score, payload: ["strokes": try numericPayload(event.value, minimum: 1)])
        case .putt:
            return liveEvent(event, kind: .putt, payload: ["putts": try numericPayload(event.value, minimum: 0)])
        case .penalty:
            return liveEvent(event, kind: .penalty, payload: ["penalties": try numericPayload(event.value, minimum: 0)])
        case .club:
            guard let clubName = nonEmpty(event.value) else {
                throw WatchEventBridgeError.missingClubContext
            }
            return liveEvent(event, kind: .club, payload: clubPayload(for: event, clubName: clubName))
        case .distance:
            guard let clubName = nonEmpty(event.contextClub) else {
                throw WatchEventBridgeError.missingClubContext
            }
            var payload = clubPayload(for: event, clubName: clubName)
            payload["distanceToPinM"] = try numericDistancePayload(event.value, minimum: 0)
            return liveEvent(
                event,
                kind: .club,
                payload: payload
            )
        }
    }

    public func makeWatchRoundStatePayload(
        package: LiveRoundPackage,
        hole: Hole,
        score: Int,
        putts: Int,
        penaltyCount: Int,
        selectedClub: String?,
        decision: CaddieDecisionResponse?,
        offlineOption: OfflineCaddieOption? = nil,
        distanceToPinM: Double? = nil,
        targetLatitude: Double? = nil,
        targetLongitude: Double? = nil,
        targetKind: String? = nil,
        frontGreenM: Double? = nil,
        centerGreenM: Double? = nil,
        backGreenM: Double? = nil,
        frontGreenLat: Double? = nil,
        frontGreenLon: Double? = nil,
        centerGreenLat: Double? = nil,
        centerGreenLon: Double? = nil,
        backGreenLat: Double? = nil,
        backGreenLon: Double? = nil,
        holeImageProjection: WatchHoleImageProjection? = nil,
        globalId: Int? = nil,
        holeMap: WatchHoleMap? = nil,
        playsLikeDistanceM: Double? = nil,
        elevationDeltaM: Double? = nil,
        lastShotDistanceM: Double? = nil,
        distanceFromLastShotM: Double? = nil,
        greenInRegulation: Bool? = nil,
        fairwayResult: String? = nil,
        geometryCoverage: String? = nil,
        caddieOptions: [WatchCaddieOption] = [],
        hazards: [WatchHazard] = []
    ) -> WatchRoundStatePayload {
        let selected = selectedOption(from: decision)
        let offlineSelected = selectedOfflineOption(from: offlineOption)
        let selectedOptionId = string(selected?["id"]) ?? decision?.selectedOptionId ?? offlineSelected?.optionId
        let suggestedClub = clubName(selected?["clubRecommendation"]) ?? string(selected?["clubName"]) ?? offlineSelected?.clubName
        let selectedSequence = selectedSequence(from: decision)
        return WatchRoundStatePayload(
            roundId: package.roundId,
            hole: hole.number,
            par: hole.par,
            distanceM: distanceToPinM ?? number(selected?["carry_m"]) ?? number(selected?["carryM"]) ?? offlineSelected?.carryM,
            targetNote: watchTargetNote(
                selected: selected,
                offlineOption: offlineSelected,
                targetKind: targetKind,
                targetLatitude: targetLatitude,
                targetLongitude: targetLongitude
            ),
            targetLatitude: targetLatitude,
            targetLongitude: targetLongitude,
            targetKind: targetKind,
            suggestedClub: suggestedClub,
            selectedClub: selectedClub,
            availableClubs: watchClubOptions(
                package: package,
                hole: hole,
                selectedClub: selectedClub,
                suggestedClub: suggestedClub,
                selectedOption: selected,
                offlineOption: offlineSelected
            ),
            shotType: nonEmpty(decision?.shotType),
            strategyMode: strategyMode(selectedOption: selected, selectedOptionId: selectedOptionId),
            lie: nonEmpty(string(decision?.context["lie"])),
            offlineOptionId: selectedOptionId,
            decisionId: nonEmpty(decision?.decisionId),
            nextShotPrompt: nextShotPrompt(selected: selected, offlineOption: offlineSelected),
            holePlanSummary: sequenceSummary(from: selectedSequence),
            expectedStrokes: number(selectedSequence?["expectedStrokes"]),
            expectedRemainingM: number(selectedSequence?["expectedRemaining_m"]) ?? number(selectedSequence?["expectedRemainingM"]),
            evidenceSummary: evidenceSummary(from: decision, offlineOption: offlineSelected),
            missingDataSummary: missingDataSummary(from: decision),
            frontGreenM: frontGreenM,
            centerGreenM: centerGreenM,
            backGreenM: backGreenM,
            frontGreenLat: frontGreenLat,
            frontGreenLon: frontGreenLon,
            centerGreenLat: centerGreenLat,
            centerGreenLon: centerGreenLon,
            backGreenLat: backGreenLat,
            backGreenLon: backGreenLon,
            holeImageProjection: holeImageProjection,
            globalId: globalId,
            holeMap: holeMap,
            playsLikeDistanceM: playsLikeDistanceM,
            elevationDeltaM: elevationDeltaM,
            lastShotDistanceM: lastShotDistanceM,
            distanceFromLastShotM: distanceFromLastShotM,
            greenInRegulation: greenInRegulation,
            fairwayResult: fairwayResult,
            geometryCoverage: geometryCoverage,
            caddieOptions: caddieOptions,
            hazards: hazards,
            score: score,
            putts: putts,
            penaltyCount: penaltyCount,
            caddieConfidence: confidenceLevel(from: decision, offlineOption: offlineSelected)
        )
    }

    /// watch P1b: pre-compute the five hole-map overlay anchors from the hole's centreline route so the
    /// watch renders the map with zero projection math. `overlay.route` is `[[px, py, cumMetres]]` in the
    /// same /topo.png pixel space the watch caches. `you` = tee, `pin` = green centre, `layup` = the
    /// recommended lay-up (at `landingM` along the route, default 60%), `apex`/`greenCtrl` = the mid-route
    /// points that make the you→lay-up / lay-up→green curves bend with the dogleg. nil for < 2 route points.
    public static func makeHoleMap(overlay: CoursePrepOverlay, landingM: Double?, youPxOverride: [Double]? = nil) -> WatchHoleMap? {
        let route = overlay.route
        guard route.count >= 2, let first = route.first, let last = route.last,
              first.count >= 3, last.count >= 3, last[2] > 0 else { return nil }
        let total = last[2]
        let layupM = min(max(landingM ?? total * 0.6, 0), total)
        // watch P1c: `you` = the player's live GPS projected onto the topo (youPxOverride) when available,
        // else the tee (route start) as the pre-GPS default.
        let you = (youPxOverride?.count == 2) ? youPxOverride! : [first[0], first[1]]
        return WatchHoleMap(
            w: overlay.w,
            h: overlay.h,
            you: you,
            pin: [last[0], last[1]],
            layup: Self.interpRoute(route, atM: layupM),
            apex: Self.interpRoute(route, atM: layupM * 0.5),
            greenCtrl: Self.interpRoute(route, atM: layupM + (total - layupM) * 0.5)
        )
    }

    /// watch P1c: project a WGS84 point onto the /topo.png pixel space using the 3 affine reference points
    /// (`holeImageProjection.refs`). Works in coords RELATIVE to ref[0] (a 2×2 solve) so the tiny lat/lon
    /// deltas over a hole stay well-conditioned. Returns `[px, py]`, or nil if the refs are degenerate.
    public static func projectToTopoPx(lat: Double, lon: Double, refs: [(lat: Double, lon: Double, px: Double, py: Double)]) -> [Double]? {
        guard refs.count >= 3 else { return nil }
        let o = refs[0], r1 = refs[1], r2 = refs[2]
        let a = r1.lon - o.lon, b = r2.lon - o.lon
        let c = r1.lat - o.lat, d = r2.lat - o.lat
        let det = a * d - b * c
        guard abs(det) > 1e-12 else { return nil }
        let dlon = lon - o.lon, dlat = lat - o.lat
        let s = (dlon * d - b * dlat) / det
        let t = (a * dlat - dlon * c) / det
        let px = o.px + s * (r1.px - o.px) + t * (r2.px - o.px)
        let py = o.py + s * (r1.py - o.py) + t * (r2.py - o.py)
        return [px, py]
    }

    /// Interpolate the route (points `[px, py, cumMetres]`, sorted by cumMetres) at `atM` metres,
    /// returning `[px, py]`. Clamps to the first/last point outside the range.
    static func interpRoute(_ route: [[Double]], atM: Double) -> [Double] {
        guard let first = route.first, first.count >= 3 else { return [0, 0] }
        if atM <= first[2] { return [first[0], first[1]] }
        for i in 0..<(route.count - 1) {
            let a = route[i], b = route[i + 1]
            guard a.count >= 3, b.count >= 3 else { continue }
            if atM <= b[2] {
                let span = b[2] - a[2]
                let t = span > 0 ? (atM - a[2]) / span : 0
                return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
            }
        }
        let last = route[route.count - 1]
        return [last[0], last[1]]
    }

    public func sendStateToWatch(_ state: WatchRoundStatePayload) throws {
        let data = try encoder.encode(state)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw URLError(.cannotParseResponse)
        }
        guard WCSession.isSupported() else {
            return
        }
        if WCSession.default.isReachable {
            WCSession.default.sendMessage(["state": object], replyHandler: nil)
        } else {
            WCSession.default.transferUserInfo(["state": object])
        }
    }

    /// round-12 P3.4 (Watch standalone): hand the watch what it needs to reach the backend on its own
    /// (base URL + auth), so a standalone round can sync without the phone relaying each event. Sent via
    /// application context — latest-wins and delivered even when the watch isn't reachable now.
    ///
    /// round-13 watch-auth: the phone also forwards its live Apple `sessionToken` (and its expiry) here,
    /// so the watch's standalone `WatchBackendClient` authenticates as the signed-in member/owner with a
    /// Bearer token (member/owner-scoped) instead of the admin token. On sign-out the caller passes
    /// `sessionToken: nil`; the config is rebuilt WITHOUT the token, and because the application context
    /// is latest-wins the watch drops its Bearer. The admin token rides along only as the DEBUG/CI
    /// fallback.
    public func sendConfigToWatch(
        apiBaseURL: String,
        adminToken: String?,
        sessionToken: String? = nil,
        sessionTokenExpiresAt: Date? = nil
    ) {
        var config: [String: Any] = ["apiBaseURL": apiBaseURL]
        // DEBUG/CI ONLY: forward the admin token to the watch as its fallback auth. Consumer (Release)
        // builds hold no admin token (AICaddieApp.defaultAdminToken returns nil) and the watch
        // authenticates solely with the phone-pushed Apple `sessionToken` below, so this is compiled
        // out of Release — the watch config never carries an admin token.
        #if DEBUG
        if let adminToken, !adminToken.isEmpty {
            config["adminToken"] = adminToken
        }
        #endif
        if let sessionToken, !sessionToken.isEmpty {
            config["sessionToken"] = sessionToken
            if let sessionTokenExpiresAt {
                config["sessionTokenExpiresAt"] = ISO8601DateFormatter().string(from: sessionTokenExpiresAt)
            }
        }
        pendingConfig = config
        pushPendingConfig()
    }

    /// Push the stored config via application context. No-op until the session is activated — the
    /// activation callback re-invokes this, so a config set during launch still reaches the watch.
    private func pushPendingConfig() {
        guard WCSession.isSupported(), let pendingConfig else {
            return
        }
        guard WCSession.default.activationState == .activated else {
            return
        }
        try? WCSession.default.updateApplicationContext(["config": pendingConfig])
    }

    /// watch P0.4: push a hole's topo image to the watch via a guaranteed-delivery file transfer, keyed
    /// by {globalId, hole}. Called at round-start / hole-change so the watch has the current (+ next)
    /// hole's map cached for offline play. Best-effort — a failure just leaves the watch mapless.
    public func pushHoleImage(globalId: Int, hole: Int, imageData: Data) {
        guard WCSession.isSupported(), WCSession.default.activationState == .activated else {
            return
        }
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("holeimg-\(globalId)-\(hole).img")
        do {
            if FileManager.default.fileExists(atPath: tmp.path) {
                try? FileManager.default.removeItem(at: tmp)
            }
            try imageData.write(to: tmp, options: .atomic)
            WCSession.default.transferFile(tmp, metadata: ["globalId": globalId, "hole": hole])
        } catch {
            // best-effort; the watch simply renders no map for this hole
        }
    }

    public func handleWatchInputMessage(_ message: [String: Any], replyHandler: @escaping ([String: Any]) -> Void) {
        guard let object = message["event"] as? [String: Any],
              JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(withJSONObject: object),
              let event = try? decoder.decode(WatchInputEvent.self, from: data)
        else {
            replyHandler(["accepted": false])
            return
        }

        do {
            let liveEvent = try mapWatchInputEvent(event)
            if try offlineStore.containsEvent(eventId: liveEvent.eventId) {
                replyHandler(acknowledgementReply(eventId: event.eventId, duplicate: true))
                return
            }

            if let onAcceptedLiveEvent {
                Task {
                    do {
                        try await onAcceptedLiveEvent(liveEvent)
                        replyHandler(self.acknowledgementReply(eventId: event.eventId, duplicate: false))
                    } catch {
                        replyHandler(["accepted": false, "eventId": event.eventId])
                    }
                }
            } else {
                try offlineStore.appendEvent(liveEvent)
                replyHandler(acknowledgementReply(eventId: event.eventId, duplicate: false))
            }
        } catch WatchEventBridgeError.invalidNumericInput {
            replyHandler(rejectionReply(eventId: event.eventId, reason: "invalid_numeric_input"))
        } catch WatchEventBridgeError.missingClubContext {
            replyHandler(rejectionReply(eventId: event.eventId, reason: "missing_club_context"))
        } catch {
            replyHandler(["accepted": false, "eventId": event.eventId])
        }
    }

    private func clubPayload(for event: WatchInputEvent, clubName: String) -> [String: JSONValue] {
        var payload: [String: JSONValue] = ["clubName": .string(clubName)]
        if let shotType = nonEmpty(event.shotType) {
            payload["shotType"] = .string(shotType)
        }
        if let strategyMode = nonEmpty(event.strategyMode) {
            payload["strategyMode"] = .string(strategyMode)
        }
        if let lie = nonEmpty(event.lie) {
            payload["lie"] = .string(lie)
        }
        if let distanceToPinM = event.distanceToPinM, distanceToPinM.isFinite {
            payload["distanceToPinM"] = .number(distanceToPinM)
        }
        payload["offlineOptionId"] = jsonStringOrNull(event.offlineOptionId)
        if let decisionId = nonEmpty(event.decisionId) {
            payload["decisionId"] = .string(decisionId)
        }
        return payload
    }

    private func liveEvent(
        _ watchEvent: WatchInputEvent,
        kind: LiveRoundEventKind,
        payload: [String: JSONValue]
    ) -> LiveRoundEvent {
        var enrichedPayload = payload
        enrichedPayload["source"] = .string("apple_watch")
        // The watch authored this event, so stamp it "apple-watch" — the SAME clientId the standalone
        // WatchBackendClient uses. Whether the watch relays through the phone (this bridge) or posts
        // directly, the backend `(clientId, eventId)` dedup key matches, so the shot is never
        // double-counted. (Leaving it to the phone default would make it "ios-phone" here and collide.)
        return LiveRoundEvent(
            eventId: watchEvent.eventId,
            roundId: watchEvent.roundId,
            clientId: "apple-watch",
            timestamp: watchEvent.createdAt,
            hole: watchEvent.hole,
            kind: kind,
            payload: enrichedPayload
        )
    }

    private func acknowledgementReply(eventId: String, duplicate: Bool) -> [String: Any] {
        let acceptedEventIds: [String] = duplicate ? [] : [eventId]
        let duplicateEventIds: [String] = duplicate ? [eventId] : []
        return [
            "accepted": true,
            "eventId": eventId,
            "acceptedEventIds": acceptedEventIds,
            "duplicateEventIds": duplicateEventIds,
            "rejectedEventIds": [],
            "source": "ios_watch_bridge",
        ]
    }

    private func rejectionReply(eventId: String, reason: String) -> [String: Any] {
        [
            "accepted": false,
            "eventId": eventId,
            "acceptedEventIds": [],
            "duplicateEventIds": [],
            "rejectedEventIds": [eventId],
            "reason": reason,
            "source": "ios_watch_bridge",
        ]
    }

    private func numericPayload(_ value: String, minimum: Int) throws -> JSONValue {
        guard let parsed = Int(value.trimmingCharacters(in: .whitespacesAndNewlines)), parsed >= minimum else {
            throw WatchEventBridgeError.invalidNumericInput
        }
        return .number(Double(parsed))
    }

    private func numericDistancePayload(_ value: String, minimum: Double) throws -> JSONValue {
        guard let parsed = Double(value.trimmingCharacters(in: .whitespacesAndNewlines)), parsed.isFinite, parsed >= minimum else {
            throw WatchEventBridgeError.invalidNumericInput
        }
        return .number(parsed)
    }

    private func jsonStringOrNull(_ value: String?) -> JSONValue {
        guard let value = nonEmpty(value) else {
            return .null
        }
        return .string(value)
    }

    private func watchClubOptions(
        package: LiveRoundPackage,
        hole: Hole,
        selectedClub: String?,
        suggestedClub: String?,
        selectedOption: [String: JSONValue]?,
        offlineOption: OfflineCaddieOption?
    ) -> [WatchClubOption] {
        var options: [WatchClubOption] = []
        var seen = Set<String>()

        func append(_ option: WatchClubOption) {
            guard let clubName = nonEmpty(option.clubName) else {
                return
            }
            let key = clubName.lowercased()
            guard seen.insert(key).inserted else {
                return
            }
            options.append(
                WatchClubOption(
                    clubName: clubName,
                    sampleSize: option.sampleSize,
                    medianM: option.medianM,
                    source: option.source
                )
            )
        }

        for profile in package.clubProfiles {
            append(
                WatchClubOption(
                    clubName: profile.clubName,
                    sampleSize: profile.sampleSize,
                    medianM: profile.medianM,
                    source: "club_profile"
                )
            )
        }

        for option in package.caddieContextSeeds.first(where: { $0.hole == hole.number })?.offlineOptions ?? [] {
            append(
                WatchClubOption(
                    clubName: option.clubName,
                    medianM: option.carryM,
                    source: "offline_option:\(option.optionId)"
                )
            )
        }

        if let offlineOption {
            append(
                WatchClubOption(
                    clubName: offlineOption.clubName,
                    medianM: offlineOption.carryM,
                    source: "offline_option:\(offlineOption.optionId)"
                )
            )
        }
        append(WatchClubOption(clubName: string(selectedOption?["clubName"]) ?? "", source: "decision_option"))
        append(WatchClubOption(clubName: suggestedClub ?? "", source: "suggested"))
        append(WatchClubOption(clubName: selectedClub ?? "", source: "selected"))
        return options
    }

    private func strategyMode(selectedOption: [String: JSONValue]?, selectedOptionId: String?) -> String? {
        if let explicit = nonEmpty(string(selectedOption?["strategyMode"])) {
            return explicit
        }
        switch nonEmpty(selectedOptionId)?.lowercased() {
        case "safe":
            return "protect_score"
        case "stock":
            return "stock"
        case "attack":
            return "attack"
        default:
            return nil
        }
    }

    private func watchTargetNote(
        selected: [String: JSONValue]?,
        offlineOption: OfflineCaddieOption?,
        targetKind: String?,
        targetLatitude: Double?,
        targetLongitude: Double?
    ) -> String? {
        let label = string(selected?["label"]) ?? string(selected?["routeLabel"]) ?? offlineOption?.label
        if let targetKind, targetLatitude != nil, targetLongitude != nil {
            return [label, "\(targetKind) set on iPhone"].compactMap { $0 }.joined(separator: " / ")
        }
        if let label {
            return "\(label) / pin not set"
        }
        return "pin not set"
    }

    private func selectedOption(from decision: CaddieDecisionResponse?) -> [String: JSONValue]? {
        guard let decision else {
            return nil
        }
        if let selectedOption = decision.selectedOption {
            return selectedOption
        }
        if let selected = decision.selected {
            return selected
        }
        if let selectedOptionId = decision.selectedOptionId,
           let option = decision.options.first(where: { string($0["id"]) == selectedOptionId }) {
            return option
        }
        return decision.options.first
    }

    private func selectedSequence(from decision: CaddieDecisionResponse?) -> [String: JSONValue]? {
        guard let decision else {
            return nil
        }
        if let selectedSequence = decision.selectedSequence {
            return selectedSequence
        }
        if let selectedOptionId = decision.selectedOptionId,
           let sequence = decision.sequences?.first(where: { string($0["id"]) == selectedOptionId }) {
            return sequence
        }
        return decision.sequences?.first
    }

    private func selectedOfflineOption(from offlineOption: OfflineCaddieOption?) -> OfflineCaddieOption? {
        offlineOption
    }

    private func confidenceLevel(from decision: CaddieDecisionResponse?, offlineOption: OfflineCaddieOption?) -> String {
        guard let decision else {
            return offlineOption == nil ? "low" : "offline"
        }
        return string(decision.confidence["level"]) ?? string(decision.confidence["confidence"]) ?? "low"
    }

    private func evidenceSummary(from decision: CaddieDecisionResponse?, offlineOption: OfflineCaddieOption?) -> String? {
        if let decision, let summary = compactSummary(from: decision.evidence) {
            return summary
        }
        guard let offlineOption else {
            return nil
        }
        let parts = [safeSummaryText(offlineOption.source), safeSummaryText(offlineOption.sourceRefs.first)]
            .compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " / ")
    }

    private func missingDataSummary(from decision: CaddieDecisionResponse?) -> String? {
        guard let decision else {
            return nil
        }
        return compactSummary(from: decision.missingData)
    }

    private func compactSummary(from rows: [[String: JSONValue]]) -> String? {
        for row in rows {
            let labels = uniqueSummaryParts(["label", "source", "kind"].compactMap { summaryText(row[$0]) })
            let details = uniqueSummaryParts(["value", "text", "reason", "state"].compactMap { summaryText(row[$0]) })
            if !labels.isEmpty || !details.isEmpty {
                return [labels.joined(separator: " / "), details.joined(separator: " / ")]
                    .filter { !$0.isEmpty }
                    .joined(separator: ": ")
            }
        }
        return nil
    }

    private func uniqueSummaryParts(_ values: [String]) -> [String] {
        var seen = Set<String>()
        var result: [String] = []
        for value in values {
            let key = value.lowercased()
            if seen.insert(key).inserted {
                result.append(value)
            }
        }
        return result
    }

    private func summaryText(_ value: JSONValue?) -> String? {
        guard let value else {
            return nil
        }
        switch value {
        case .string(let raw):
            return safeSummaryText(raw)
        case .number(let raw):
            guard raw.isFinite else {
                return nil
            }
            return raw.rounded() == raw ? String(Int(raw)) : String(raw)
        case .bool(let raw):
            return raw ? "true" : "false"
        case .object(_), .array(_), .null:
            return nil
        }
    }

    private func safeSummaryText(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }
        let lower = trimmed.lowercased()
        let blockedFragments = [
            "/users/",
            "/home/",
            "/tmp/",
            "/private/",
            "file://",
            "password=",
            "secret=",
            "token=",
            "cookie=",
            "authorization:",
            "bearer ",
            "csrf",
        ]
        guard !trimmed.hasPrefix("/"),
              !trimmed.contains("\\"),
              !blockedFragments.contains(where: { lower.contains($0) })
        else {
            return "[redacted]"
        }
        return trimmed
    }

    private func nextShotPrompt(selected: [String: JSONValue]?, offlineOption: OfflineCaddieOption?) -> String? {
        let club = clubName(selected?["clubRecommendation"]) ?? string(selected?["clubName"]) ?? offlineOption?.clubName
        let label = string(selected?["label"]) ?? string(selected?["routeLabel"]) ?? offlineOption?.label
        let carry = number(selected?["carry_m"]) ?? number(selected?["carryM"]) ?? offlineOption?.carryM
        let carryText = carry.map { "\(Int($0))m" }
        let parts = [club, label, carryText].compactMap { value in
            value?.isEmpty == false ? value : nil
        }
        return parts.isEmpty ? nil : parts.joined(separator: " / ")
    }

    private func sequenceSummary(from selectedSequence: [String: JSONValue]?) -> String? {
        guard let selectedSequence else {
            return nil
        }
        var parts: [String] = []
        if let label = safeSummaryText(string(selectedSequence["label"]) ?? string(selectedSequence["id"])) {
            parts.append(label)
        }
        if let expectedStrokes = number(selectedSequence["expectedStrokes"]) {
            let shotCount = Int(expectedStrokes)
            parts.append("\(shotCount) \(shotCount == 1 ? "shot" : "shots")")
        }
        if let expectedRemaining = number(selectedSequence["expectedRemaining_m"]) ?? number(selectedSequence["expectedRemainingM"]) {
            parts.append("leave \(Int(expectedRemaining))m")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " / ")
    }

    private func clubName(_ value: JSONValue?) -> String? {
        guard case .object(let recommendation) = value,
              case .array(let clubs) = recommendation["clubs"],
              let first = clubs.first,
              case .object(let club) = first
        else {
            return nil
        }
        return string(club["clubName"])
    }

    private func string(_ value: JSONValue?) -> String? {
        if case .string(let raw) = value {
            return raw
        }
        return nil
    }

    private func nonEmpty(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }

    private func number(_ value: JSONValue?) -> Double? {
        if case .number(let raw) = value {
            return raw
        }
        return nil
    }
}

extension WatchEventBridge: WCSessionDelegate {
    public func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        if activationState == .activated {
            pushPendingConfig()  // deliver config queued before activation completed
        }
    }

    public func sessionDidBecomeInactive(_ session: WCSession) {}

    public func sessionDidDeactivate(_ session: WCSession) {
        WCSession.default.activate()
    }

    public func session(
        _ session: WCSession,
        didReceiveMessage message: [String: Any],
        replyHandler: @escaping ([String: Any]) -> Void
    ) {
        handleWatchInputMessage(message, replyHandler: replyHandler)
    }
}
