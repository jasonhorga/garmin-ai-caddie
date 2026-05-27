import Foundation
import WatchConnectivity

public enum WatchInputKind: String, Codable, Equatable {
    case score
    case putt
    case penalty
    case club
}

public struct WatchInputEvent: Codable, Equatable, Identifiable {
    public var id: String { eventId }

    public let eventId: String
    public let roundId: String
    public let hole: Int
    public let kind: WatchInputKind
    public let value: String
    public let createdAt: String
}

public struct WatchRoundStatePayload: Codable, Equatable {
    public let roundId: String
    public let hole: Int
    public let par: Int
    public let distanceM: Double?
    public let targetNote: String?
    public let suggestedClub: String?
    public let selectedClub: String?
    public let nextShotPrompt: String?
    public let score: Int
    public let putts: Int
    public let penaltyCount: Int
    public let caddieConfidence: String
}

public enum WatchEventBridgeError: Error {
    case invalidNumericInput
}

public final class WatchEventBridge: NSObject {
    private let offlineStore: OfflineStore
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(offlineStore: OfflineStore = OfflineStore()) {
        self.offlineStore = offlineStore
        super.init()
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
            return liveEvent(event, kind: .club, payload: ["clubName": .string(event.value)])
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
        offlineOption: OfflineCaddieOption? = nil
    ) -> WatchRoundStatePayload {
        let selected = selectedOption(from: decision)
        let offlineSelected = selectedOfflineOption(from: offlineOption)
        return WatchRoundStatePayload(
            roundId: package.roundId,
            hole: hole.number,
            par: hole.par,
            distanceM: number(selected?["carry_m"]) ?? number(selected?["carryM"]) ?? offlineSelected?.carryM,
            targetNote: string(selected?["label"]) ?? string(selected?["routeLabel"]) ?? offlineSelected?.label,
            suggestedClub: clubName(selected?["clubRecommendation"]) ?? string(selected?["clubName"]) ?? offlineSelected?.clubName,
            selectedClub: selectedClub,
            nextShotPrompt: nextShotPrompt(selected: selected, offlineOption: offlineSelected),
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

    private func numericPayload(_ value: String, minimum: Int) throws -> JSONValue {
        guard let parsed = Int(value.trimmingCharacters(in: .whitespacesAndNewlines)), parsed >= minimum else {
            throw WatchEventBridgeError.invalidNumericInput
        }
        return .number(Double(parsed))
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

    private func selectedOfflineOption(from offlineOption: OfflineCaddieOption?) -> OfflineCaddieOption? {
        offlineOption
    }

    private func confidenceLevel(from decision: CaddieDecisionResponse?, offlineOption: OfflineCaddieOption?) -> String {
        guard let decision else {
            return offlineOption == nil ? "low" : "offline"
        }
        return string(decision.confidence["level"]) ?? string(decision.confidence["confidence"]) ?? "low"
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
    ) {}

    public func sessionDidBecomeInactive(_ session: WCSession) {}

    public func sessionDidDeactivate(_ session: WCSession) {
        WCSession.default.activate()
    }

    public func session(
        _ session: WCSession,
        didReceiveMessage message: [String: Any],
        replyHandler: @escaping ([String: Any]) -> Void
    ) {
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
            try offlineStore.appendEvent(liveEvent)
            replyHandler(["accepted": true, "eventId": event.eventId])
        } catch WatchEventBridgeError.invalidNumericInput {
            replyHandler(["accepted": false, "eventId": event.eventId, "reason": "invalid_numeric_input"])
        } catch {
            replyHandler(["accepted": false, "eventId": event.eventId])
        }
    }
}
