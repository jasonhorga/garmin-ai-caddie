import Combine
import Foundation
import os
import WatchConnectivity

public enum WatchInputKind: String, Codable, Equatable {
    case score
    case putt
    case penalty
    case club
    case distance
    case location
}

/// Compact value carried by the existing Watch input adapter for a manually captured shot origin.
/// The domain/backend event remains the existing `location` live-round event; this is only the
/// WatchConnectivity/offline-queue representation and adds no second shot protocol.
public struct WatchShotLocationValue: Codable, Equatable {
    public let latitude: Double
    public let longitude: Double
    public let horizontalAccuracyM: Double

    public init?(latitude: Double, longitude: Double, horizontalAccuracyM: Double) {
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              horizontalAccuracyM.isFinite, horizontalAccuracyM >= 0 else {
            return nil
        }
        self.latitude = latitude
        self.longitude = longitude
        self.horizontalAccuracyM = horizontalAccuracyM
    }

    public init?(encodedValue: String) {
        let parts = encodedValue.split(separator: ",", omittingEmptySubsequences: false)
        guard parts.count == 3,
              let latitude = Double(parts[0]),
              let longitude = Double(parts[1]),
              let horizontalAccuracyM = Double(parts[2]) else {
            return nil
        }
        self.init(
            latitude: latitude,
            longitude: longitude,
            horizontalAccuracyM: horizontalAccuracyM
        )
    }

    public var encodedValue: String {
        "\(latitude),\(longitude),\(horizontalAccuracyM)"
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
    /// Optional Fairway result captured with a score on Par 4/5: HIT, LEFT, or RIGHT.
    public let fairwayResult: String?

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
        decisionId: String? = nil,
        fairwayResult: String? = nil
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
        self.fairwayResult = fairwayResult
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
    @Published public private(set) var roundSeed: WatchRoundSeed?
    @Published public private(set) var phoneRoundClosure: WatchRoundClosure?
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
    /// watch P0.4: local cache of per-hole topo images the phone pushes via WatchConnectivity file
    /// transfer, so the hole map renders offline mid-round. Read by `WatchHoleMapView`'s geometry.
    public let holeImageStore: WatchHoleImageStore
    @Published public private(set) var lastHoleImageKey: String?

    public init(
        queueURL: URL,
        stateURL: URL? = nil,
        holeImageStore: WatchHoleImageStore = WatchHoleImageStore()
    ) {
        self.queueURL = queueURL
        self.stateURL = stateURL ?? queueURL.deletingLastPathComponent().appendingPathComponent("current_state.json")
        self.holeImageStore = holeImageStore
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
        // P1-12: a phone snapshot must not clobber the watch's own unsynced edits. Re-apply the still-
        // queued (not-yet-acked) quick inputs on top of the snapshot so on-wrist score/club/putt/penalty
        // edits survive until the phone has actually accepted them (dirty-field merge).
        let merged = applyingQueuedEdits(to: state)
        publishStateUpdate { client in
            client.currentState = merged
        }
        do {
            try persistState(merged)
        } catch {
            WatchLog.storage.error("Persist received state failed: \(String(describing: error), privacy: .public)")
        }
    }

    public func receiveRoundSeed(_ seed: WatchRoundSeed) {
        publishStateUpdate { client in
            client.roundSeed = seed
        }
    }

    public func receiveRoundClosure(_ closure: WatchRoundClosure) {
        try? forgetRound(
            roundId: closure.roundId,
            discardQueuedEvents: closure.disposition != .savedLocally
        )
        publishStateUpdate { client in
            client.phoneRoundClosure = closure
        }
    }

    /// Clear only facts belonging to the terminal round. A newer in-flight state and its queue must
    /// survive a delayed completion message from either device.
    public func forgetRound(roundId: String, discardQueuedEvents: Bool) throws {
        if currentState?.roundId == roundId {
            publishStateUpdate { client in
                client.currentState = nil
            }
            if FileManager.default.fileExists(atPath: stateURL.path) {
                try FileManager.default.removeItem(at: stateURL)
            }
        }
        if roundSeed?.roundId == roundId {
            publishStateUpdate { client in
                client.roundSeed = nil
            }
        }
        if discardQueuedEvents {
            let remaining = try loadQueuedEvents().filter { $0.roundId != roundId }
            try writeQueuedEvents(remaining)
            refreshQueuedEventCount()
        }
    }

    /// `transferUserInfo` provides background delivery when the phone is currently unreachable.
    /// The local tombstone remains the safety authority if WatchConnectivity is unavailable.
    public func sendRoundClosureToPhone(_ closure: WatchRoundClosure) {
        guard WCSession.isSupported(),
              WCSession.default.activationState == .activated,
              let data = try? encoder.encode(closure),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return
        }
        WCSession.default.transferUserInfo(["roundClosure": object])
    }

    private func applyingQueuedEdits(to state: WatchRoundState) -> WatchRoundState {
        let queued = (try? loadQueuedEvents()) ?? []
        // `applying` ignores events for a different round/hole, so edits for other holes stay queued
        // and merge in when their hole's snapshot arrives; same-hole edits replay in queue order.
        return queued.reduce(state) { partial, event in partial.applying(event) }
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
        do {
            try persistState(updated)
        } catch {
            WatchLog.storage.error("Persist updated state failed: \(String(describing: error), privacy: .public)")
        }
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
                        do {
                            try self?.markEventsAcknowledged(acknowledgement.resolvedEventIds)
                        } catch {
                            WatchLog.sync.error("Mark events acknowledged failed: \(String(describing: error), privacy: .public)")
                        }
                    }
                } else if queueOnFailure {
                    do {
                        try self?.queueInputEvent(event)
                    } catch {
                        WatchLog.sync.error("Queue input event failed: \(String(describing: error), privacy: .public)")
                    }
                }
            },
            errorHandler: { [weak self] error in
                WatchLog.connectivity.error("Watch→phone sendMessage failed: \(String(describing: error), privacy: .public)")
                self?.publishPhoneReachable(false)
                if queueOnFailure {
                    do {
                        try self?.queueInputEvent(event)
                    } catch {
                        WatchLog.sync.error("Queue input event failed: \(String(describing: error), privacy: .public)")
                    }
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

    private func receiveRoundSeedPayload(_ seed: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(seed),
              let data = try? JSONSerialization.data(withJSONObject: seed),
              let decoded = try? decoder.decode(WatchRoundSeed.self, from: data)
        else {
            return
        }
        receiveRoundSeed(decoded)
    }

    private func receiveRoundClosurePayload(_ closure: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(closure),
              let data = try? JSONSerialization.data(withJSONObject: closure),
              let decoded = try? decoder.decode(WatchRoundClosure.self, from: data) else {
            return
        }
        receiveRoundClosure(decoded)
    }

    /// round-12 P3.4 (Watch standalone): parse the backend config the phone delivers in its application
    /// context. Exposed (not just used inside the delegate) so it can be unit-tested without WCSession.
    public func applyApplicationContext(_ context: [String: Any]) {
        if let configDict = context["config"] as? [String: Any],
           let baseURLString = configDict["apiBaseURL"] as? String,
           let baseURL = URL(string: baseURLString) {
            let adminToken = configDict["adminToken"] as? String
            // round-13 watch-auth: the phone's live Apple session token (Bearer) + its expiry. Absent when
            // the phone is signed out, so the rebuilt config clears the Bearer (latest-wins app context).
            let sessionToken = configDict["sessionToken"] as? String
            let sessionTokenExpiresAt = (configDict["sessionTokenExpiresAt"] as? String)
                .flatMap { ISO8601DateFormatter().date(from: $0) }
            let parsed = WatchRoundConfig(
                baseURL: baseURL,
                adminToken: adminToken,
                sessionToken: sessionToken,
                sessionTokenExpiresAt: sessionTokenExpiresAt
            )
            publishStateUpdate { client in
                client.config = parsed
            }
        }
        if let seed = context["roundSeed"] as? [String: Any] {
            receiveRoundSeedPayload(seed)
        } else {
            // Application context is a complete latest-wins snapshot. A config-only context is an
            // explicit seed retraction, not "no update".
            publishStateUpdate { client in
                client.roundSeed = nil
            }
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
            do {
                try flushQueue()
            } catch {
                WatchLog.sync.error("Flush queued events failed: \(String(describing: error), privacy: .public)")
            }
        }
    }

    public func sessionReachabilityDidChange(_ session: WCSession) {
        publishPhoneReachable(session.isReachable)
        if session.isReachable {
            do {
                try flushQueue()
            } catch {
                WatchLog.sync.error("Flush queued events failed: \(String(describing: error), privacy: .public)")
            }
        }
    }

    public func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        if let state = message["state"] as? [String: Any] {
            receiveStatePayload(state)
        }
        if let seed = message["roundSeed"] as? [String: Any] {
            receiveRoundSeedPayload(seed)
        }
        if let closure = message["roundClosure"] as? [String: Any] {
            receiveRoundClosurePayload(closure)
        }
    }

    public func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        if let state = userInfo["state"] as? [String: Any] {
            receiveStatePayload(state)
        }
        if let seed = userInfo["roundSeed"] as? [String: Any] {
            receiveRoundSeedPayload(seed)
        }
        if let closure = userInfo["roundClosure"] as? [String: Any] {
            receiveRoundClosurePayload(closure)
        }
    }

    public func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        applyApplicationContext(applicationContext)
    }

    // watch P0.4: the phone pushes each hole's topo image via `transferFile`; cache it locally (keyed
    // by the file's {globalId, hole} metadata) so the hole map renders offline while playing.
    public func session(_ session: WCSession, didReceive file: WCSessionFile) {
        receiveHoleImage(fileURL: file.fileURL, metadata: file.metadata ?? [:])
    }

    /// Accept only pixels produced for this Watch build's renderer contract. A transfer queued by
    /// the previous phone build may arrive after upgrade; silently caching it would reintroduce the
    /// exact stale map that the versioned directories are meant to retire.
    @discardableResult
    func receiveHoleImage(fileURL: URL, metadata meta: [String: Any]) -> Bool {
        guard meta["styleVersion"] as? String == WatchBackendClient.topoStyleVersion else {
            return false
        }
        guard let gid = (meta["globalId"] as? Int) ?? (meta["globalId"] as? NSNumber)?.intValue,
              let hole = (meta["hole"] as? Int) ?? (meta["hole"] as? NSNumber)?.intValue else {
            return false
        }
        do {
            try holeImageStore.store(
                fileURL: fileURL,
                globalId: gid,
                hole: hole,
                geometryRevision: meta["geometryRevision"] as? String
            )
            let key = WatchHoleImageStore.key(globalId: gid, hole: hole)
            DispatchQueue.main.async { self.lastHoleImageKey = key }
            return true
        } catch {
            WatchLog.sync.error("Store hole image failed: \(String(describing: error), privacy: .public)")
            return false
        }
    }
}
