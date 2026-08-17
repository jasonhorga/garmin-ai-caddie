import Foundation

public enum WatchRoundDisposition: String, Codable, Equatable {
    case finished
    case savedLocally
    case abandoned
}

public struct WatchRoundClosure: Codable, Equatable, Identifiable {
    public var id: String { "\(roundId):\(disposition.rawValue):\(closedAt)" }

    public let schema: String
    public let roundId: String
    public let disposition: WatchRoundDisposition
    public let closedAt: String

    public init(
        schema: String = "ai-caddie-watch-round-closure-v1",
        roundId: String,
        disposition: WatchRoundDisposition,
        closedAt: String
    ) {
        self.schema = schema
        self.roundId = roundId
        self.disposition = disposition
        self.closedAt = closedAt
    }
}

/// A player-selected flag position for one hole of one active round. The point is normalized to the
/// downloaded hole image so a later bitmap refresh can change pixel dimensions without moving the
/// flag. Rotation is presentation state for View Green only; Hole Root and Touch Target consume the
/// canonical image-space flag point.
public struct WatchGreenPlacement: Codable, Equatable {
    public let hole: Int
    /// `globalId` identifies the course package in the current protocol; pair it with `hole` rather
    /// than treating it as a globally unique hole id.
    public let globalId: Int?
    public let normalizedPinX: Double
    public let normalizedPinY: Double
    public let rotationDegrees: Double

    public init(
        hole: Int,
        globalId: Int? = nil,
        normalizedPinX: Double,
        normalizedPinY: Double,
        rotationDegrees: Double
    ) {
        self.hole = hole
        self.globalId = globalId
        self.normalizedPinX = normalizedPinX
        self.normalizedPinY = normalizedPinY
        self.rotationDegrees = rotationDegrees
    }

    public func matches(hole: Int, globalId: Int?) -> Bool {
        guard self.hole == hole else { return false }
        // Old/offline rounds may not know the package id. Reject only a real authority conflict.
        if let stored = self.globalId, let requested = globalId {
            return stored == requested
        }
        return true
    }
}

/// round-12 P3.2 (Watch standalone): on-watch persistence so a round survives an app relaunch and so
/// events recorded with no network are queued for later upload. Deliberately simpler than the iOS
/// `OfflineStore` — it persists the per-hole `WatchRoundState` snapshots + a pending-event queue (not
/// a full event-log-replay), which is enough for the watch to keep score on its own and sync up when
/// it reaches the backend (via `WatchBackendClient`).
public final class WatchRoundStore {
    public struct DeferredFinish: Codable, Equatable {
        public var round: PersistedRound
        public let savedAt: String

        public init(round: PersistedRound, savedAt: String) {
            self.round = round
            self.savedAt = savedAt
        }
    }

    public struct PersistedRound: Codable, Equatable {
        public var roundId: String
        public var activeHole: Int
        public var holeStates: [WatchRoundState]
        public var pendingEvents: [WatchInputEvent]
        /// Round-level course label for the watch UI (optional — older persisted rounds decode it as nil).
        public var courseName: String?
        /// In-progress user facts are optional so rounds written by older app versions still decode.
        public var pendingManualShot: WatchPendingManualShot?
        public var pendingAutoShotCandidate: WatchPendingAutoShotCandidate?
        public var scoreDraft: WatchScoreDraft?
        /// Round-scoped View Green choices. Optional keeps rounds written by older builds decodable.
        /// Terminal round closure removes the containing round, so these never leak into a new game.
        public var greenPlacements: [WatchGreenPlacement]?

        public init(
            roundId: String,
            activeHole: Int = 0,
            holeStates: [WatchRoundState] = [],
            pendingEvents: [WatchInputEvent] = [],
            courseName: String? = nil,
            pendingManualShot: WatchPendingManualShot? = nil,
            pendingAutoShotCandidate: WatchPendingAutoShotCandidate? = nil,
            scoreDraft: WatchScoreDraft? = nil,
            greenPlacements: [WatchGreenPlacement]? = nil
        ) {
            self.roundId = roundId
            self.activeHole = activeHole
            self.holeStates = holeStates
            self.pendingEvents = pendingEvents
            self.courseName = courseName
            self.pendingManualShot = pendingManualShot
            self.pendingAutoShotCandidate = pendingAutoShotCandidate
            self.scoreDraft = scoreDraft
            self.greenPlacements = greenPlacements
        }
    }

    private let fileURL: URL
    private let deferredFinishesURL: URL
    private let closuresURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(directoryURL: URL? = nil) {
        let directory = directoryURL
            ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("watch-round", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        self.fileURL = directory.appendingPathComponent("round.json")
        self.deferredFinishesURL = directory.appendingPathComponent("deferred-finishes.json")
        self.closuresURL = directory.appendingPathComponent("round-closures.json")
    }

    // MARK: persistence

    public func load() -> PersistedRound? {
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        guard let round = try? decoder.decode(PersistedRound.self, from: data),
              !isClosed(roundId: round.roundId) else {
            return nil
        }
        return round
    }

    public func save(_ round: PersistedRound) throws {
        try encoder.encode(round).write(to: fileURL, options: [.atomic])
    }

    public func clear() {
        try? FileManager.default.removeItem(at: fileURL)
    }

    /// Record terminal intent before removing the active file. The closure ledger is deliberately
    /// separate from `round.json`: deleting the round must not delete the fact that an old phone
    /// application context is no longer allowed to resurrect it.
    public func closeActiveRound(
        roundId: String,
        disposition: WatchRoundDisposition,
        closedAt: String
    ) throws -> WatchRoundClosure {
        let closure = WatchRoundClosure(
            roundId: roundId,
            disposition: disposition,
            closedAt: closedAt
        )
        try recordClosure(closure)
        if rawLoad()?.roundId == roundId,
           FileManager.default.fileExists(atPath: fileURL.path) {
            try FileManager.default.removeItem(at: fileURL)
        }
        return closure
    }

    /// Leave the playing UI immediately while retaining every unresolved fact for an idempotent
    /// upload/finish retry. Archive first, then tombstone, then remove the active pointer so a crash
    /// at any boundary cannot silently lose the round.
    public func deferFinish(_ round: PersistedRound, savedAt: String) throws -> WatchRoundClosure {
        var deferred = loadDeferredFinishes()
        deferred.removeAll { $0.round.roundId == round.roundId }
        deferred.append(DeferredFinish(round: round, savedAt: savedAt))
        try write(deferred, to: deferredFinishesURL)
        return try closeActiveRound(
            roundId: round.roundId,
            disposition: .savedLocally,
            closedAt: savedAt
        )
    }

    public func loadDeferredFinishes() -> [DeferredFinish] {
        guard let data = try? Data(contentsOf: deferredFinishesURL) else { return [] }
        return (try? decoder.decode([DeferredFinish].self, from: data)) ?? []
    }

    @discardableResult
    public func markDeferredEventsPosted(
        roundId: String,
        eventIds: [String]
    ) throws -> DeferredFinish? {
        var deferred = loadDeferredFinishes()
        guard let index = deferred.firstIndex(where: { $0.round.roundId == roundId }) else {
            return nil
        }
        let posted = Set(eventIds)
        deferred[index].round.pendingEvents.removeAll { posted.contains($0.eventId) }
        try writeDeferredFinishes(deferred)
        return deferred[index]
    }

    public func removeDeferredFinish(roundId: String) throws {
        var deferred = loadDeferredFinishes()
        deferred.removeAll { $0.round.roundId == roundId }
        try writeDeferredFinishes(deferred)
    }

    public func closure(roundId: String) -> WatchRoundClosure? {
        loadClosures().last { $0.roundId == roundId }
    }

    public func isClosed(roundId: String) -> Bool {
        closure(roundId: roundId) != nil
    }

    private func rawLoad() -> PersistedRound? {
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return try? decoder.decode(PersistedRound.self, from: data)
    }

    private func loadClosures() -> [WatchRoundClosure] {
        guard let data = try? Data(contentsOf: closuresURL) else { return [] }
        return (try? decoder.decode([WatchRoundClosure].self, from: data)) ?? []
    }

    private func recordClosure(_ closure: WatchRoundClosure) throws {
        var closures = loadClosures()
        closures.removeAll { $0.roundId == closure.roundId }
        closures.append(closure)
        // Round IDs are unique. A bounded ledger prevents years of stale application contexts while
        // keeping Documents growth deterministic.
        if closures.count > 64 {
            closures.removeFirst(closures.count - 64)
        }
        try write(closures, to: closuresURL)
    }

    private func writeDeferredFinishes(_ deferred: [DeferredFinish]) throws {
        if deferred.isEmpty {
            if FileManager.default.fileExists(atPath: deferredFinishesURL.path) {
                try FileManager.default.removeItem(at: deferredFinishesURL)
            }
            return
        }
        try write(deferred, to: deferredFinishesURL)
    }

    private func write<T: Encodable>(_ value: T, to url: URL) throws {
        try encoder.encode(value).write(to: url, options: [.atomic])
    }

    // MARK: round operations

    /// Seed/replace the snapshot for a hole (e.g. from a phone-synced state or a fetched package) and
    /// make it the active hole. Preserves the pending-event queue.
    @discardableResult
    public func upsertHoleState(
        _ state: WatchRoundState,
        makeActive: Bool = true
    ) throws -> PersistedRound {
        var round = load() ?? PersistedRound(roundId: state.roundId)
        if round.roundId != state.roundId {
            round = PersistedRound(roundId: state.roundId)  // a new round replaces the old persisted one
        }
        round.holeStates.removeAll { $0.hole == state.hole }
        round.holeStates.append(state)
        round.holeStates.sort { $0.hole < $1.hole }
        if makeActive {
            round.activeHole = state.hole
        }
        try save(round)
        return round
    }

    /// Record a user input: apply it to the matching hole snapshot (last-write-wins per field) and
    /// enqueue the event for upload. No-op for the snapshot if the hole isn't seeded yet, but the
    /// event is still queued so it isn't lost.
    @discardableResult
    public func record(_ event: WatchInputEvent, updateActiveHole: Bool = true) throws -> PersistedRound {
        var round = load() ?? PersistedRound(roundId: event.roundId)
        if round.roundId != event.roundId {
            round = PersistedRound(roundId: event.roundId)
        }
        if let index = round.holeStates.firstIndex(where: { $0.hole == event.hole }) {
            round.holeStates[index] = round.holeStates[index].applying(event)
        }
        round.pendingEvents.append(event)
        if updateActiveHole {
            round.activeHole = event.hole
        }
        try save(round)
        return round
    }

    public func pendingEvents() -> [WatchInputEvent] {
        load()?.pendingEvents ?? []
    }

    /// Drop events confirmed posted to the backend from the pending queue.
    @discardableResult
    public func markPosted(eventIds: [String]) throws -> PersistedRound? {
        guard var round = load() else { return nil }
        let posted = Set(eventIds)
        round.pendingEvents.removeAll { posted.contains($0.eventId) }
        try save(round)
        return round
    }

    public func holeState(hole: Int) -> WatchRoundState? {
        load()?.holeStates.first { $0.hole == hole }
    }
}
