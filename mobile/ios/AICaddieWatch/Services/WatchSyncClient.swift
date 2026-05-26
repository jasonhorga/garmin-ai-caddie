import Combine
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

    public init(eventId: String, roundId: String, hole: Int, kind: WatchInputKind, value: String, createdAt: String) {
        self.eventId = eventId
        self.roundId = roundId
        self.hole = hole
        self.kind = kind
        self.value = value
        self.createdAt = createdAt
    }
}

public final class WatchSyncClient: NSObject, ObservableObject {
    @Published public private(set) var currentState: WatchRoundState?

    private let queueURL: URL
    private let stateURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(queueURL: URL, stateURL: URL? = nil) {
        self.queueURL = queueURL
        self.stateURL = stateURL ?? queueURL.deletingLastPathComponent().appendingPathComponent("current_state.json")
        super.init()
        currentState = try? loadPersistedState()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    public override convenience init() {
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddieWatch", isDirectory: true)
        self.init(
            queueURL: directory.appendingPathComponent("queued_events.json"),
            stateURL: directory.appendingPathComponent("current_state.json")
        )
    }

    public func receiveState(_ state: WatchRoundState) {
        currentState = state
        try? persistState(state)
    }

    public func sendQuickInputEvent(_ event: WatchInputEvent) throws {
        if WCSession.isSupported(), WCSession.default.isReachable {
            try sendToPhone(event)
        } else {
            try queueInputEvent(event)
        }
    }

    public func queueInputEvent(_ event: WatchInputEvent) throws {
        var events = try loadQueuedEvents()
        events.append(event)
        try FileManager.default.createDirectory(at: queueURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try encoder.encode(events).write(to: queueURL, options: [.atomic])
    }

    public func loadQueuedEvents() throws -> [WatchInputEvent] {
        guard FileManager.default.fileExists(atPath: queueURL.path) else {
            return []
        }
        return try decoder.decode([WatchInputEvent].self, from: Data(contentsOf: queueURL))
    }

    public func loadPersistedState() throws -> WatchRoundState? {
        guard FileManager.default.fileExists(atPath: stateURL.path) else {
            return nil
        }
        return try decoder.decode(WatchRoundState.self, from: Data(contentsOf: stateURL))
    }

    private func persistState(_ state: WatchRoundState) throws {
        try FileManager.default.createDirectory(at: stateURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try encoder.encode(state).write(to: stateURL, options: [.atomic])
    }

    public func flushQueue() throws {
        let events = try loadQueuedEvents()
        guard !events.isEmpty else {
            return
        }
        for event in events {
            try sendToPhone(event)
        }
        try FileManager.default.removeItem(at: queueURL)
    }

    private func sendToPhone(_ event: WatchInputEvent) throws {
        let data = try encoder.encode(event)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw URLError(.cannotParseResponse)
        }
        WCSession.default.sendMessage(["event": object], replyHandler: nil) { [weak self] _ in
            try? self?.queueInputEvent(event)
        }
    }

    private func receiveStatePayload(_ state: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(state),
              let data = try? JSONSerialization.data(withJSONObject: state),
              let decoded = try? decoder.decode(WatchRoundState.self, from: data)
        else {
            return
        }
        receiveState(decoded)
    }
}

extension WatchSyncClient: WCSessionDelegate {
    public func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        if activationState == .activated, session.isReachable {
            try? flushQueue()
        }
    }

    public func sessionReachabilityDidChange(_ session: WCSession) {
        if session.isReachable {
            try? flushQueue()
        }
    }

    public func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        guard let state = message["state"] as? [String: Any] else {
            return
        }
        receiveStatePayload(state)
    }

    public func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        guard let state = userInfo["state"] as? [String: Any] else {
            return
        }
        receiveStatePayload(state)
    }
}
