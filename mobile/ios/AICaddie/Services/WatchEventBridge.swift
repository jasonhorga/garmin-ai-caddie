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

public final class WatchEventBridge: NSObject {
    private let offlineStore: OfflineStore
    private let decoder = JSONDecoder()

    public init(offlineStore: OfflineStore = OfflineStore()) {
        self.offlineStore = offlineStore
        super.init()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    public func mapWatchInputEvent(_ event: WatchInputEvent) -> LiveRoundEvent {
        switch event.kind {
        case .score:
            return liveEvent(event, kind: .score, payload: ["strokes": numericPayload(event.value)])
        case .putt:
            return liveEvent(event, kind: .putt, payload: ["putts": numericPayload(event.value)])
        case .penalty:
            return liveEvent(event, kind: .penalty, payload: ["penalties": numericPayload(event.value)])
        case .club:
            return liveEvent(event, kind: .club, payload: ["clubName": .string(event.value)])
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

    private func numericPayload(_ value: String) -> JSONValue {
        .number(Double(value) ?? 0)
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
            let liveEvent = mapWatchInputEvent(event)
            try offlineStore.appendEvent(liveEvent)
            replyHandler(["accepted": true, "eventId": event.eventId])
        } catch {
            replyHandler(["accepted": false, "eventId": event.eventId])
        }
    }
}
