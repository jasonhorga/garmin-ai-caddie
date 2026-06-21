import Combine
import Foundation
import WatchConnectivity

public enum WatchInputKind: String, Codable, Equatable {
    case score
    case putt
    case penalty
    case club
    case distance
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

public struct WatchSyncAcknowledgement: Equatable {
    public let acceptedEventIds: [String]
    public let duplicateEventIds: [String]
    public let rejectedEventIds: [String]
    public let phoneSequence: Int

    public var acknowledgedEventIds: [String] {
        acceptedEventIds + duplicateEventIds
    }

    public var resolvedEventIds: [String] {
        acceptedEventIds + duplicateEventIds + rejectedEventIds
    }

    public static func decode(_ reply: [String: Any], fallbackEventId: String) -> WatchSyncAcknowledgement {
        let accepted = reply["accepted"] as? Bool ?? false
        let eventId = reply["eventId"] as? String ?? fallbackEventId
        let explicitAcceptedEventIds = stringArray(reply["acceptedEventIds"])
        let acceptedEventIds = explicitAcceptedEventIds ?? (accepted ? [eventId] : [])
        let duplicateEventIds = stringArray(reply["duplicateEventIds"]) ?? []
        let rejectedEventIds = stringArray(reply["rejectedEventIds"]) ?? []
        let phoneSequence = intValue(reply["phoneSequence"]) ?? intValue(reply["watchAckSequence"]) ?? 0

        return WatchSyncAcknowledgement(
            acceptedEventIds: acceptedEventIds,
            duplicateEventIds: duplicateEventIds,
            rejectedEventIds: rejectedEventIds,
            phoneSequence: phoneSequence
        )
    }

    private static func stringArray(_ value: Any?) -> [String]? {
        value as? [String]
    }

    private static func intValue(_ value: Any?) -> Int? {
        if let raw = value as? Int {
            return raw
        }
        if let raw = value as? Double, raw.isFinite {
            return Int(raw)
        }
        return nil
    }
}

public final class WatchSyncClient: NSObject, ObservableObject {
    @Published public private(set) var currentState: WatchRoundState?
    @Published public private(set) var queuedEventCount = 0
    @Published public private(set) var phoneReachable = false
    @Published public private(set) var lastPhoneAcceptedAt: String?
    /// round-12 P3.4 (Watch standalone): backend connection info the phone delivers via application
    /// context, so a standalone round can sync on its own. Nil until the phone sends it.
    @Published public private(set) var config: WatchRoundConfig?

    private let queueURL: URL
    private let stateURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(queueURL: URL, stateURL: URL? = nil) {
        self.queueURL = queueURL
        self.stateURL = stateURL ?? queueURL.deletingLastPathComponent().appendingPathComponent("current_state.json")
        super.init()
        currentState = try? loadPersistedState()
        refreshQueuedEventCount()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
            phoneReachable = WCSession.default.isReachable
            applyApplicationContext(WCSession.default.receivedApplicationContext)  // config sent before launch
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
        publishStateUpdate { client in
            client.currentState = state
        }
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
        guard !events.contains(where: { $0.eventId == event.eventId }) else {
            return
        }
        events.append(event)
        try writeQueuedEvents(events)
        refreshQueuedEventCount()
        applyQuickInputToCurrentState(event)
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

    private func applyQuickInputToCurrentState(_ event: WatchInputEvent) {
        guard let currentState else {
            return
        }
        let updated = currentState.applying(event)
        publishStateUpdate { client in
            client.currentState = updated
        }
        try? persistState(updated)
    }

    public func markEventsAcknowledged(_ eventIds: [String]) throws {
        try removeAcknowledgedEventIds(Set(eventIds))
    }

    private func removeAcknowledgedEventIds(_ eventIds: Set<String>) throws {
        guard !eventIds.isEmpty else {
            return
        }
        let remaining = try loadQueuedEvents().filter { event in
            !eventIds.contains(event.eventId)
        }
        try writeQueuedEvents(remaining)
        refreshQueuedEventCount()
    }

    private func writeQueuedEvents(_ events: [WatchInputEvent]) throws {
        try FileManager.default.createDirectory(at: queueURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        guard !events.isEmpty else {
            if FileManager.default.fileExists(atPath: queueURL.path) {
                try FileManager.default.removeItem(at: queueURL)
            }
            return
        }
        try encoder.encode(events).write(to: queueURL, options: [.atomic])
    }

    public func flushQueue() throws {
        let events = try loadQueuedEvents()
        guard !events.isEmpty else {
            return
        }
        for event in events {
            try sendToPhone(event, queueOnFailure: false, removeFromQueueOnAck: true)
        }
    }

    private func sendToPhone(
        _ event: WatchInputEvent,
        queueOnFailure: Bool = true,
        removeFromQueueOnAck: Bool = false
    ) throws {
        let data = try encoder.encode(event)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw URLError(.cannotParseResponse)
        }
        WCSession.default.sendMessage(
            ["event": object],
            replyHandler: { [weak self] reply in
                let acknowledgement = WatchSyncAcknowledgement.decode(reply, fallbackEventId: event.eventId)
                if !acknowledgement.resolvedEventIds.isEmpty {
                    self?.publishPhoneAccepted()
                    if removeFromQueueOnAck {
                        try? self?.markEventsAcknowledged(acknowledgement.resolvedEventIds)
                    }
                } else if queueOnFailure {
                    try? self?.queueInputEvent(event)
                }
            },
            errorHandler: { [weak self] _ in
                self?.publishPhoneReachable(false)
                if queueOnFailure {
                    try? self?.queueInputEvent(event)
                }
            }
        )
    }

    private func refreshQueuedEventCount() {
        let count = (try? loadQueuedEvents().count) ?? 0
        publishStateUpdate { client in
            client.queuedEventCount = count
        }
    }

    private func publishPhoneReachable(_ reachable: Bool) {
        publishStateUpdate { client in
            client.phoneReachable = reachable
        }
    }

    private func publishPhoneAccepted() {
        let acceptedAt = ISO8601DateFormatter().string(from: Date())
        publishStateUpdate { client in
            client.phoneReachable = true
            client.lastPhoneAcceptedAt = acceptedAt
        }
    }

    private func publishStateUpdate(_ update: @escaping (WatchSyncClient) -> Void) {
        if Thread.isMainThread {
            update(self)
        } else {
            DispatchQueue.main.async { [weak self] in
                guard let self else {
                    return
                }
                update(self)
            }
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

    /// round-12 P3.4 (Watch standalone): parse the backend config the phone delivers in its application
    /// context. Exposed (not just used inside the delegate) so it can be unit-tested without WCSession.
    public func applyApplicationContext(_ context: [String: Any]) {
        guard let configDict = context["config"] as? [String: Any],
              let baseURLString = configDict["apiBaseURL"] as? String,
              let baseURL = URL(string: baseURLString)
        else {
            return
        }
        let adminToken = configDict["adminToken"] as? String
        let parsed = WatchRoundConfig(baseURL: baseURL, adminToken: adminToken)
        publishStateUpdate { client in
            client.config = parsed
        }
    }
}

extension WatchSyncClient: WCSessionDelegate {
    public func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        publishPhoneReachable(session.isReachable)
        if activationState == .activated, session.isReachable {
            try? flushQueue()
        }
    }

    public func sessionReachabilityDidChange(_ session: WCSession) {
        publishPhoneReachable(session.isReachable)
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

    public func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        applyApplicationContext(applicationContext)
    }
}
