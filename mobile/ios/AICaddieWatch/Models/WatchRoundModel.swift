import Foundation

/// round-12 P3.3 (Watch standalone): the brain that ties the three presentational watch screens
/// (`WatchRoundHomeView` → `WatchScoreHoleView` → `WatchFinishRoundView`) into a working standalone
/// round. It owns the persisted round (`WatchRoundStore`), drives navigation between screens, edits a
/// per-hole scoring draft, turns saves into `WatchInputEvent`s, and on finish uploads the queued events
/// to the backend (directly, via `WatchBackendClient`, with config delivered from the phone).
///
/// Side effects are injectable (`makeEventId` / `now` / `uploader`) so the whole state machine is
/// deterministic under unit test without a network or a real clock.

public enum WatchRoundScreen: Equatable {
    case home
    case clubPrompt
    case scoring
    case finishing
    case scorecard   // round-13: 计分卡逐洞列表
    case holeSelect  // round-13: 选洞
    case menu        // round-13: 菜单 hub(纯文字,S70 式)
    case holeMap     // watch P1b: 全屏球道图(真几何底图 + 球童线/落点/旗)
}

public enum WatchScoreFlowStep: Equatable {
    case recommendation
    case score
    case putts
    case fairway
    case penalty
}

public enum WatchFairwayResult: String, CaseIterable, Equatable {
    case hit = "HIT"
    case left = "LEFT"
    case right = "RIGHT"
}

public struct WatchPendingManualShot: Equatable {
    public let hole: Int
    /// Non-nil while this shot was captured at the ordered next tee before the previous hole was
    /// confirmed. Confirm clears it and keeps `hole`; Cancel reassigns the shot to this hole.
    public let candidateFromHole: Int?
    public let location: WatchShotLocationValue
    public let capturedAt: String
    public let shotNumber: Int
    public let shotType: String
}

public struct WatchRoundConfig: Equatable {
    public let baseURL: URL
    public let adminToken: String?
    /// round-13 watch-auth: the phone's live Apple session token (and its expiry), pushed over
    /// WCSession so the watch's standalone sync authenticates as the signed-in member/owner with a
    /// Bearer token instead of the admin token. Nil when signed out (or on a DEBUG/CI build).
    public let sessionToken: String?
    public let sessionTokenExpiresAt: Date?

    public init(
        baseURL: URL,
        adminToken: String?,
        sessionToken: String? = nil,
        sessionTokenExpiresAt: Date? = nil
    ) {
        self.baseURL = baseURL
        self.adminToken = adminToken
        self.sessionToken = sessionToken
        self.sessionTokenExpiresAt = sessionTokenExpiresAt
    }
}

public enum WatchRoundModelError: Error, Equatable {
    case notConfigured
}

@MainActor
public final class WatchRoundModel: ObservableObject {
    @Published public private(set) var round: WatchRoundStore.PersistedRound?
    @Published public var screen: WatchRoundScreen = .home
    @Published public var draftScore: Int = 0
    @Published public var draftPutts: Int = 0
    @Published public var draftPenalty: Int = 0
    @Published public var draftFairway: WatchFairwayResult?
    @Published public private(set) var scoreFlowStep: WatchScoreFlowStep = .recommendation
    @Published public private(set) var scoringHole: Int?
    @Published public private(set) var pendingManualShot: WatchPendingManualShot?
    @Published public private(set) var isUploading: Bool = false
    @Published public private(set) var uploadError: String?

    /// Backend connection info delivered from the phone (round-12 P3.4, WCSession). When nil the watch
    /// can still score offline; uploads just fail and events stay queued.
    public var config: WatchRoundConfig?

    private let store: WatchRoundStore
    private let clientId: String
    private let makeEventId: () -> String
    private let now: () -> String
    private let uploaderOverride: (([WatchInputEvent], String) async throws -> [String])?
    private var advanceAfterScoring = true
    private static let nextTeeCandidateRadiusM = 35.0
    private static let maximumCandidateAccuracyM = 12.0

    public init(
        store: WatchRoundStore,
        clientId: String = "apple-watch",
        config: WatchRoundConfig? = nil,
        makeEventId: @escaping () -> String = { UUID().uuidString },
        now: @escaping () -> String = { ISO8601DateFormatter().string(from: Date()) },
        uploader: (([WatchInputEvent], String) async throws -> [String])? = nil
    ) {
        self.store = store
        self.clientId = clientId
        self.config = config
        self.makeEventId = makeEventId
        self.now = now
        self.uploaderOverride = uploader
        self.round = store.load()
    }

    /// Default standalone model backed by the on-watch document store (for `@StateObject` in the app).
    public convenience init() {
        self.init(store: WatchRoundStore())
    }

    // MARK: - derived state (drives the views)

    public var activeHole: Int { round?.activeHole ?? 0 }

    public var activeHoleState: WatchRoundState? {
        guard let round else { return nil }
        return round.holeStates.first { $0.hole == round.activeHole }
    }

    public var scoringHoleState: WatchRoundState? {
        guard let round, let scoringHole else { return nil }
        return round.holeStates.first { $0.hole == scoringHole }
    }

    public var holeCount: Int { round?.holeStates.count ?? 0 }

    public var recordedShotCount: Int {
        recordedShotCount(for: activeHole)
    }

    /// All holes' states, hole-ordered — feeds the round-13 计分卡 / 选洞 / 18洞环.
    public var allHoleStates: [WatchRoundState] {
        (round?.holeStates ?? []).sorted { $0.hole < $1.hole }
    }

    // round-13 navigation between the standalone round screens (menu hub → scorecard / hole select).
    public func openScorecard() { screen = .scorecard }
    public func openHoleSelect() { screen = .holeSelect }
    public func openMenu() { screen = .menu }
    public func openHoleMap() { screen = .holeMap }
    public func backToHome() { screen = .home }
    public func selectHole(_ hole: Int) {
        setActiveHole(hole)
        screen = .home
    }

    private var scoredHoleStates: [WatchRoundState] {
        round?.holeStates.filter { $0.score > 0 } ?? []
    }

    public var scoredHoles: Int { scoredHoleStates.count }

    public var totalStrokes: Int { scoredHoleStates.reduce(0) { $0 + $1.score } }

    public var totalPutts: Int { scoredHoleStates.reduce(0) { $0 + $1.putts } }

    /// Cumulative score relative to par over the holes actually scored (nil before any hole is scored).
    public var toPar: Int? {
        let scored = scoredHoleStates
        guard !scored.isEmpty else { return nil }
        return scored.reduce(0) { $0 + ($1.score - $1.par) }
    }

    public var pendingUploads: Int { round?.pendingEvents.count ?? 0 }

    public var courseName: String { round?.courseName ?? "" }

    // MARK: - seeding (from a phone-synced round or a fetched package)

    /// Start (or refresh) the real phone-selected round. Existing snapshots and unsynced Watch edits
    /// for the same round are retained; newly added holes receive a truthful blank state from the seed.
    public func applyRoundSeed(_ seed: WatchRoundSeed) {
        guard !seed.holes.isEmpty else { return }
        let existing = round?.roundId == seed.roundId ? round : nil
        let states = seed.holes
            .sorted { $0.hole < $1.hole }
            .map { hole in
                existing?.holeStates.first { $0.hole == hole.hole }
                    ?? WatchRoundState(
                        roundId: seed.roundId,
                        hole: hole.hole,
                        par: hole.par,
                        distanceM: hole.distanceM,
                        teeLatitude: hole.teeLatitude,
                        teeLongitude: hole.teeLongitude,
                        selectedClub: nil,
                        score: 0,
                        putts: 0,
                        penaltyCount: 0,
                        caddieConfidence: "offline"
                    )
            }
        let holeNumbers = Set(states.map(\.hole))
        let activeHole = holeNumbers.contains(seed.activeHole) ? seed.activeHole : states[0].hole
        let persisted = WatchRoundStore.PersistedRound(
            roundId: seed.roundId,
            activeHole: activeHole,
            holeStates: states,
            pendingEvents: existing?.pendingEvents ?? [],
            courseName: seed.courseName
        )
        try? store.save(persisted)
        round = persisted
        screen = .home
    }

    /// Merge the richer live snapshot for one hole without dropping the seeded course or other holes.
    /// Pending on-Watch edits are replayed so a stale phone snapshot cannot silently undo them.
    public func receivePhoneState(_ state: WatchRoundState) {
        if let round, round.roundId != state.roundId {
            return
        }
        let merged = (round?.pendingEvents ?? []).reduce(state) { partial, event in
            partial.applying(event)
        }
        guard let persisted = try? store.upsertHoleState(merged) else {
            return
        }
        round = persisted
    }

    /// Replace the active round with a fresh set of per-hole snapshots and start at the given hole.
    public func seedRound(_ states: [WatchRoundState], activeHole: Int? = nil, courseName: String? = nil) {
        guard let first = states.first else { return }
        var persisted = WatchRoundStore.PersistedRound(roundId: first.roundId)
        persisted.holeStates = states.sorted { $0.hole < $1.hole }
        persisted.activeHole = activeHole ?? persisted.holeStates.first?.hole ?? 0
        persisted.courseName = courseName
        try? store.save(persisted)
        round = persisted
        screen = .home
    }

    public func refreshFromStore() {
        round = store.load()
    }

    /// Start a self-contained practice round on the watch (no phone needed) — `holeCount` blank holes at
    /// the given par. Scores are kept locally and synced on finish if backend config is available.
    public func startPracticeRound(holeCount: Int = 18, par: Int = 4, courseName: String = "练习记分") {
        let roundId = "watch-\(makeEventId())"
        let holes = (1...max(1, holeCount)).map { number in
            WatchRoundState(
                roundId: roundId, hole: number, par: par, distanceM: nil, selectedClub: nil,
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
            )
        }
        seedRound(holes, activeHole: 1, courseName: courseName)
    }

    // MARK: - scoring draft

    public func startScoringActiveHole() {
        guard let hole = activeHoleState else { return }
        beginScoring(hole: hole, advanceAfterSave: true, offerRecommendation: hole.score == 0)
    }

    /// Edit a completed/historical hole without moving the live-play cursor.
    public func startEditingHole(_ holeNumber: Int) {
        guard let hole = round?.holeStates.first(where: { $0.hole == holeNumber }) else { return }
        beginScoring(hole: hole, advanceAfterSave: false, offerRecommendation: false)
    }

    private func beginScoring(
        hole: WatchRoundState,
        advanceAfterSave: Bool,
        offerRecommendation: Bool
    ) {
        let unscored = hole.score == 0
        let shotCount = recordedShotCount(for: hole.hole)
        draftScore = unscored ? (shotCount > 0 ? shotCount + 2 : hole.par) : hole.score
        draftPutts = unscored ? 2 : hole.putts
        draftPenalty = hole.penaltyCount
        draftFairway = hole.fairwayResult.flatMap { WatchFairwayResult(rawValue: $0.uppercased()) }
        scoringHole = hole.hole
        self.advanceAfterScoring = advanceAfterSave
        scoreFlowStep = offerRecommendation ? .recommendation : .score
        screen = .scoring
    }

    // MARK: - manual shot

    public func beginManualShot(
        latitude: Double,
        longitude: Double,
        horizontalAccuracyM: Double,
        capturedAt: String
    ) {
        guard let hole = activeHoleState,
              let location = WatchShotLocationValue(
                  latitude: latitude,
                  longitude: longitude,
                  horizontalAccuracyM: horizontalAccuracyM
              ) else { return }
        if let nextHole = candidateNextHole(from: hole, location: location) {
            pendingManualShot = makePendingShot(
                assignedTo: nextHole,
                candidateFromHole: hole.hole,
                location: location,
                capturedAt: capturedAt
            )
            startScoringActiveHole()
        } else {
            pendingManualShot = makePendingShot(
                assignedTo: hole,
                candidateFromHole: nil,
                location: location,
                capturedAt: capturedAt
            )
            screen = .clubPrompt
        }
    }

    public func completePendingManualShot(clubName: String?) {
        guard let pendingManualShot, pendingManualShot.candidateFromHole == nil else { return }
        var latest = round
        if let clubName = clubName?.trimmingCharacters(in: .whitespacesAndNewlines), !clubName.isEmpty {
            latest = record(
                hole: pendingManualShot.hole,
                kind: .club,
                value: clubName,
                createdAt: pendingManualShot.capturedAt,
                contextClub: clubName,
                shotType: pendingManualShot.shotType
            )
        }
        latest = record(
            hole: pendingManualShot.hole,
            kind: .location,
            value: pendingManualShot.location.encodedValue,
            createdAt: pendingManualShot.capturedAt,
            shotType: pendingManualShot.shotType
        )
        round = latest
        self.pendingManualShot = nil
        screen = .home
    }

    private func candidateNextHole(
        from currentHole: WatchRoundState,
        location: WatchShotLocationValue
    ) -> WatchRoundState? {
        guard currentHole.score == 0,
              location.horizontalAccuracyM <= Self.maximumCandidateAccuracyM,
              let currentIndex = allHoleStates.firstIndex(where: { $0.hole == currentHole.hole }),
              currentIndex + 1 < allHoleStates.count else { return nil }
        let nextHole = allHoleStates[currentIndex + 1]
        guard let nextLat = nextHole.teeLatitude, let nextLon = nextHole.teeLongitude else { return nil }
        let nextDistance = WatchGeoMath.metres(
            location.latitude, location.longitude, nextLat, nextLon
        )
        guard nextDistance <= Self.nextTeeCandidateRadiusM + location.horizontalAccuracyM else {
            return nil
        }
        if let currentLat = currentHole.teeLatitude, let currentLon = currentHole.teeLongitude {
            let currentDistance = WatchGeoMath.metres(
                location.latitude, location.longitude, currentLat, currentLon
            )
            guard nextDistance < currentDistance else { return nil }
        }
        return nextHole
    }

    private func makePendingShot(
        assignedTo hole: WatchRoundState,
        candidateFromHole: Int?,
        location: WatchShotLocationValue,
        capturedAt: String,
        shotTypeOverride: String? = nil
    ) -> WatchPendingManualShot {
        let shotNumber = recordedShotCount(for: hole.hole) + 1
        return WatchPendingManualShot(
            hole: hole.hole,
            candidateFromHole: candidateFromHole,
            location: location,
            capturedAt: capturedAt,
            shotNumber: shotNumber,
            shotType: shotTypeOverride ?? (shotNumber == 1 ? "tee" : (hole.shotType ?? "approach"))
        )
    }

    private func reassignPendingShot(
        _ pending: WatchPendingManualShot,
        to holeNumber: Int,
        asRecovery: Bool = false
    ) -> WatchPendingManualShot? {
        guard let hole = round?.holeStates.first(where: { $0.hole == holeNumber }) else { return nil }
        return makePendingShot(
            assignedTo: hole,
            candidateFromHole: nil,
            location: pending.location,
            capturedAt: pending.capturedAt,
            shotTypeOverride: asRecovery ? "recovery" : nil
        )
    }

    private func recordedShotCount(for hole: Int) -> Int {
        round?.pendingEvents.reduce(into: 0) { count, event in
            if event.hole == hole, event.kind == .location {
                count += 1
            }
        } ?? 0
    }

    public func adjustDraftScore(_ delta: Int) { draftScore = max(1, draftScore + delta) }
    public func adjustDraftPutts(_ delta: Int) { draftPutts = max(0, draftPutts + delta) }
    public func adjustDraftPenalty(_ delta: Int) { draftPenalty = max(0, draftPenalty + delta) }

    public func startManualScoreEntry() {
        guard screen == .scoring else { return }
        scoreFlowStep = .score
    }

    public func advanceScoreEntry() {
        guard let hole = scoringHoleState else { return }
        switch scoreFlowStep {
        case .recommendation:
            scoreFlowStep = .score
        case .score:
            scoreFlowStep = .putts
        case .putts:
            scoreFlowStep = hole.par == 3 ? .penalty : .fairway
        case .fairway:
            if draftFairway != nil { scoreFlowStep = .penalty }
        case .penalty:
            break
        }
    }

    public func selectDraftFairway(_ result: WatchFairwayResult) {
        draftFairway = result
        scoreFlowStep = .penalty
    }

    /// Leave the scoring screen without recording anything (the draft is discarded).
    public func cancelScoring() {
        if let pendingManualShot,
           let previousHole = pendingManualShot.candidateFromHole,
           previousHole == scoringHole,
           let reassigned = reassignPendingShot(
               pendingManualShot,
               to: previousHole,
               asRecovery: true
           ) {
            self.pendingManualShot = reassigned
            scoringHole = nil
            screen = .clubPrompt
            return
        }
        scoringHole = nil
        screen = .home
    }

    public func acceptRecommendedScore() {
        guard scoreFlowStep == .recommendation else { return }
        persistScoreDraft()
    }

    public func saveManualScore() {
        persistScoreDraft()
    }

    /// Persist the draft for the active hole as `WatchInputEvent`s (only for fields that changed), then
    /// return to the round home and advance to the next hole.
    public func saveActiveHole() {
        persistScoreDraft()
    }

    private func persistScoreDraft() {
        guard let hole = scoringHoleState else { return }
        let shouldAdvance = advanceAfterScoring && hole.hole == activeHole
        let candidateShot = pendingManualShot?.candidateFromHole == hole.hole
            ? pendingManualShot
            : nil
        var latest = round
        if draftScore != hole.score {
            latest = record(hole: hole.hole, kind: .score, value: String(draftScore))
        }
        if draftPutts != hole.putts {
            latest = record(hole: hole.hole, kind: .putt, value: String(draftPutts))
        }
        if draftPenalty != hole.penaltyCount {
            latest = record(hole: hole.hole, kind: .penalty, value: String(draftPenalty))
        }

        // Fairway is already part of the persisted Watch hole projection. Keep it local in this
        // milestone; the existing backend event adapter is wired in milestone 3 with the rest of the
        // strong-sync path, rather than inventing a second score protocol here.
        if hole.par != 3, let draftFairway, var local = latest,
           let index = local.holeStates.firstIndex(where: { $0.hole == hole.hole }) {
            local.holeStates[index].fairwayResult = draftFairway.rawValue
            try? store.save(local)
            latest = local
        }

        round = latest
        scoringHole = nil
        if shouldAdvance {
            advanceToNextHole()
        }
        if let candidateShot,
           activeHole == candidateShot.hole,
           let resolved = reassignPendingShot(candidateShot, to: candidateShot.hole) {
            pendingManualShot = resolved
            screen = .clubPrompt
        } else {
            screen = .home
        }
    }

    private func record(
        hole: Int,
        kind: WatchInputKind,
        value: String,
        createdAt: String? = nil,
        contextClub: String? = nil,
        shotType: String? = nil
    ) -> WatchRoundStore.PersistedRound? {
        let event = WatchInputEvent(
            eventId: makeEventId(),
            roundId: round?.roundId ?? "",
            hole: hole,
            kind: kind,
            value: value,
            createdAt: createdAt ?? now(),
            contextClub: contextClub,
            shotType: shotType
        )
        return try? store.record(event, updateActiveHole: false)
    }

    // MARK: - hole navigation

    public func goToPreviousHole() {
        let holes = sortedHoleNumbers
        guard let current = holes.firstIndex(of: activeHole), current > 0 else { return }
        setActiveHole(holes[current - 1])
    }

    public func goToNextHole() {
        if activeHoleState?.score == 0 {
            startScoringActiveHole()
            return
        }
        advanceToNextHole()
    }

    private func advanceToNextHole() {
        let holes = sortedHoleNumbers
        guard let current = holes.firstIndex(of: activeHole), current + 1 < holes.count else { return }
        setActiveHole(holes[current + 1])
    }

    private var sortedHoleNumbers: [Int] {
        (round?.holeStates.map(\.hole) ?? []).sorted()
    }

    private func setActiveHole(_ hole: Int) {
        guard var current = round else { return }
        current.activeHole = hole
        try? store.save(current)
        round = current
    }

    // MARK: - finish

    public func requestFinish() {
        uploadError = nil
        screen = .finishing
    }

    public func keepPlaying() {
        screen = .home
    }

    /// Finish the round. When the backend is configured and there are queued events, they're uploaded
    /// first; on upload failure the round is kept and events stay queued (offline-safe) with
    /// `uploadError` set. A local practice round with no backend configured just finishes cleanly.
    public func confirmFinish() async {
        guard let current = round else { return }
        isUploading = true
        uploadError = nil
        defer { isUploading = false }
        let pending = current.pendingEvents
        guard !pending.isEmpty, canUpload else {
            finishLocally()   // nothing to sync, or no backend configured -> local practice round
            return
        }
        do {
            let posted = try await upload(pending, roundId: current.roundId)
            round = try store.markPosted(eventIds: posted)
            finishLocally()
        } catch {
            uploadError = "上传失败,已离线保存"
        }
    }

    private var canUpload: Bool { uploaderOverride != nil || config != nil }

    private func finishLocally() {
        store.clear()
        round = nil
        screen = .home
    }

    private func upload(_ events: [WatchInputEvent], roundId: String) async throws -> [String] {
        if let uploaderOverride {
            return try await uploaderOverride(events, roundId)
        }
        guard let config else { throw WatchRoundModelError.notConfigured }
        let client = WatchBackendClient(
            baseURL: config.baseURL,
            adminToken: config.adminToken,
            sessionToken: config.sessionToken,
            sessionTokenExpiresAt: config.sessionTokenExpiresAt,
            clientId: clientId
        )
        _ = try await client.postEvents(events, roundId: roundId, idempotencyKey: makeEventId())
        return events.map(\.eventId)
    }
}
