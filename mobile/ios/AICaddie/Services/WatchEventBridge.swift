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
    /// (base URL + admin token), so a standalone round can sync without the phone relaying each event.
    /// Sent via application context — latest-wins and delivered even when the watch isn't reachable now.
    public func sendConfigToWatch(apiBaseURL: String, adminToken: String?) {
        var config: [String: Any] = ["apiBaseURL": apiBaseURL]
        if let adminToken, !adminToken.isEmpty {
            config["adminToken"] = adminToken
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
        return LiveRoundEvent(
            eventId: watchEvent.eventId,
            roundId: watchEvent.roundId,
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
