import Foundation

/// round-12 P3.2 (Watch standalone): on-watch persistence so a round survives an app relaunch and so
/// events recorded with no network are queued for later upload. Deliberately simpler than the iOS
/// `OfflineStore` — it persists the per-hole `WatchRoundState` snapshots + a pending-event queue (not
/// a full event-log-replay), which is enough for the watch to keep score on its own and sync up when
/// it reaches the backend (via `WatchBackendClient`).
public final class WatchRoundStore {
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

        public init(
            roundId: String,
            activeHole: Int = 0,
            holeStates: [WatchRoundState] = [],
            pendingEvents: [WatchInputEvent] = [],
            courseName: String? = nil,
            pendingManualShot: WatchPendingManualShot? = nil,
            pendingAutoShotCandidate: WatchPendingAutoShotCandidate? = nil,
            scoreDraft: WatchScoreDraft? = nil
        ) {
            self.roundId = roundId
            self.activeHole = activeHole
            self.holeStates = holeStates
            self.pendingEvents = pendingEvents
            self.courseName = courseName
            self.pendingManualShot = pendingManualShot
            self.pendingAutoShotCandidate = pendingAutoShotCandidate
            self.scoreDraft = scoreDraft
        }
    }

    private let fileURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(directoryURL: URL? = nil) {
        let directory = directoryURL
            ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("watch-round", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        self.fileURL = directory.appendingPathComponent("round.json")
    }

    // MARK: persistence

    public func load() -> PersistedRound? {
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return try? decoder.decode(PersistedRound.self, from: data)
    }

    public func save(_ round: PersistedRound) throws {
        try encoder.encode(round).write(to: fileURL, options: [.atomic])
    }

    public func clear() {
        try? FileManager.default.removeItem(at: fileURL)
    }

    // MARK: round operations

    /// Seed/replace the snapshot for a hole (e.g. from a phone-synced state or a fetched package) and
    /// make it the active hole. Preserves the pending-event queue.
    @discardableResult
    public func upsertHoleState(_ state: WatchRoundState) throws -> PersistedRound {
        var round = load() ?? PersistedRound(roundId: state.roundId)
        if round.roundId != state.roundId {
            round = PersistedRound(roundId: state.roundId)  // a new round replaces the old persisted one
        }
        round.holeStates.removeAll { $0.hole == state.hole }
        round.holeStates.append(state)
        round.holeStates.sort { $0.hole < $1.hole }
        round.activeHole = state.hole
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
