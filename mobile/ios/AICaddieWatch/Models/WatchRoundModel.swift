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
    case autoShotCandidate
    case clubPrompt
    case scoring
    case finishing
    case scorecard   // round-13: 计分卡逐洞列表
    case currentHoleShots // 当前洞已记录的 GPS 击球事实与手动补杆入口
    case holeSelect  // round-13: 选洞
    case menu        // round-13: 菜单 hub(纯文字,S70 式)
    case holeMap     // watch P1b: 全屏球道图(真几何底图 + 事实标记)
    case caddie      // S70 式浅层仪表面: 当前洞球童详情
    case hazards     // S70 式浅层仪表面: 当前洞障碍距离
}

public enum WatchScoreFlowStep: String, Codable, Equatable {
    case recommendation
    case score
    case putts
    case fairway
    case penalty
}

public enum WatchFairwayResult: String, CaseIterable, Codable, Equatable {
    case hit = "HIT"
    case left = "LEFT"
    case right = "RIGHT"
}

public struct WatchOutcomeSummary: Equatable {
    public let hits: Int
    public let recorded: Int

    public init(hits: Int, recorded: Int) {
        self.hits = hits
        self.recorded = recorded
    }
}

/// One recorded shot reconstructed from the Watch's existing club/location event pair. The location
/// event is the identity-bearing fact; club may be nil when the player skipped Club Prompt. Carry is
/// measured only when a following shot origin exists, so the UI never invents a last-shot distance.
public struct WatchRecordedShot: Equatable, Identifiable {
    public var id: String { eventId }

    public let eventId: String
    public let hole: Int
    public let number: Int
    public let clubName: String?
    public let shotType: String?
    public let location: WatchShotLocationValue
    public let capturedAt: String
    public let distanceToNextM: Double?

    public init(
        eventId: String,
        hole: Int,
        number: Int,
        clubName: String?,
        shotType: String?,
        location: WatchShotLocationValue,
        capturedAt: String,
        distanceToNextM: Double?
    ) {
        self.eventId = eventId
        self.hole = hole
        self.number = number
        self.clubName = clubName
        self.shotType = shotType
        self.location = location
        self.capturedAt = capturedAt
        self.distanceToNextM = distanceToNextM
    }
}

public struct WatchPendingManualShot: Codable, Equatable {
    public let hole: Int
    /// Non-nil while this shot was captured at the ordered next tee before the previous hole was
    /// confirmed. Confirm clears it and keeps `hole`; Cancel reassigns the shot to this hole.
    public let candidateFromHole: Int?
    public let location: WatchShotLocationValue
    public let capturedAt: String
    public let shotNumber: Int
    public let shotType: String
    /// Optional for backward-compatible decoding of rounds written before map-origin resume existed.
    public let resumeHoleMap: Bool?
}

/// Durable AutoShot observation. Only the contemporaneous GPS fact is retained; raw Motion samples and
/// detector features never enter the round store. It is not a recorded shot until the player accepts it
/// and completes the existing club/location path.
public struct WatchPendingAutoShotCandidate: Codable, Equatable {
    public let location: WatchShotLocationValue
    public let capturedAt: String
    /// Optional for backward-compatible decoding of candidates written by an older app version.
    public let resumeHoleMap: Bool?
}

public struct WatchScoreDraft: Codable, Equatable {
    public let hole: Int
    public let score: Int
    public let putts: Int
    public let penalty: Int
    public let fairway: WatchFairwayResult?
    public let step: WatchScoreFlowStep
    public let advanceAfterSave: Bool
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
    @Published public private(set) var pendingAutoShotCandidate: WatchPendingAutoShotCandidate?
    @Published public private(set) var autoShotEnabled: Bool
    @Published public private(set) var isUploading: Bool = false
    @Published public private(set) var uploadError: String?

    /// Backend connection info delivered from the phone (round-12 P3.4, WCSession). When nil the watch
    /// can still score offline; uploads just fail and events stay queued.
    public var config: WatchRoundConfig?

    private let store: WatchRoundStore
    private let clientId: String
    private let makeEventId: () -> String
    private let now: () -> String
    private let persistAutoShotEnabled: (Bool) -> Void
    private let uploaderOverride: (([WatchInputEvent], String) async throws -> [String])?
    private let finisherOverride: ((String, WatchRoundFinishMetadata) async throws -> Void)?
    private var advanceAfterScoring = true
    private static let nextTeeCandidateRadiusM = 35.0
    private static let maximumCandidateAccuracyM = 12.0

    public init(
        store: WatchRoundStore,
        clientId: String = "apple-watch",
        config: WatchRoundConfig? = nil,
        autoShotEnabled: Bool = UserDefaults.standard.bool(forKey: "watch.autoshot.beta.enabled"),
        persistAutoShotEnabled: @escaping (Bool) -> Void = {
            UserDefaults.standard.set($0, forKey: "watch.autoshot.beta.enabled")
        },
        makeEventId: @escaping () -> String = { UUID().uuidString },
        now: @escaping () -> String = { ISO8601DateFormatter().string(from: Date()) },
        uploader: (([WatchInputEvent], String) async throws -> [String])? = nil,
        finisher: ((String, WatchRoundFinishMetadata) async throws -> Void)? = nil
    ) {
        self.store = store
        self.clientId = clientId
        self.config = config
        self.autoShotEnabled = autoShotEnabled
        self.persistAutoShotEnabled = persistAutoShotEnabled
        self.makeEventId = makeEventId
        self.now = now
        self.uploaderOverride = uploader
        self.finisherOverride = finisher
        let persisted = store.load()
        self.round = persisted
        restoreInteractionState(from: persisted)
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

    /// Current-hole shot facts in capture order. This is a projection of the already-persisted event
    /// queue, not a second shot store or protocol. Club Prompt writes club immediately before location
    /// with the same timestamp; skipped Club Prompt therefore remains an honest nil club.
    public var currentHoleShots: [WatchRecordedShot] {
        guard let round else { return [] }
        var unmatchedClubs: [String: [String]] = [:]
        var captured: [(event: WatchInputEvent, location: WatchShotLocationValue, club: String?)] = []

        for event in round.pendingEvents where event.hole == round.activeHole {
            switch event.kind {
            case .club:
                let club = (event.contextClub ?? event.value)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !club.isEmpty {
                    unmatchedClubs[event.createdAt, default: []].append(club)
                }
            case .location:
                guard let location = WatchShotLocationValue(encodedValue: event.value) else { continue }
                var clubs = unmatchedClubs[event.createdAt] ?? []
                let club = clubs.isEmpty ? nil : clubs.removeFirst()
                unmatchedClubs[event.createdAt] = clubs
                captured.append((event, location, club))
            default:
                continue
            }
        }

        return captured.enumerated().map { index, item in
            let distanceToNextM = captured.indices.contains(index + 1)
                ? WatchGeoMath.metres(
                    item.location.latitude,
                    item.location.longitude,
                    captured[index + 1].location.latitude,
                    captured[index + 1].location.longitude
                )
                : nil
            return WatchRecordedShot(
                eventId: item.event.eventId,
                hole: item.event.hole,
                number: index + 1,
                clubName: item.club,
                shotType: item.event.shotType,
                location: item.location,
                capturedAt: item.event.createdAt,
                distanceToNextM: distanceToNextM
            )
        }
    }

    /// Live distance from the active hole's latest recorded shot origin to the Watch's current fix.
    /// Location events are the existing durable shot facts; malformed or other-hole events cannot
    /// replace the last usable origin.
    public func distanceFromLatestShotM(latitude: Double, longitude: Double) -> Double? {
        guard let round,
              let current = WatchShotLocationValue(
                latitude: latitude,
                longitude: longitude,
                horizontalAccuracyM: 0
              ) else {
            return nil
        }
        for event in round.pendingEvents.reversed()
            where event.hole == round.activeHole && event.kind == .location {
            guard let shot = WatchShotLocationValue(encodedValue: event.value) else { continue }
            return WatchGeoMath.metres(
                shot.latitude,
                shot.longitude,
                current.latitude,
                current.longitude
            )
        }
        return nil
    }

    /// All holes' states, hole-ordered — feeds the round-13 计分卡 / 选洞 / 18洞环.
    public var allHoleStates: [WatchRoundState] {
        (round?.holeStates ?? []).sorted { $0.hole < $1.hole }
    }

    /// The detail surface may show an offline/prepared recommendation. It is deliberately separate from
    /// the stricter Hole Root gate below: useful detail data must not automatically become a live call.
    public var caddieDetailAvailable: Bool {
        guard let state = activeHoleState else { return false }
        let club = state.suggestedClub?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return !club.isEmpty || !state.caddieOptions.isEmpty
    }

    public var hazardDetailAvailable: Bool {
        !(activeHoleState?.hazards.isEmpty ?? true)
    }

    /// D02/C′ safety gate. Detail-only legacy fields cannot open this layer: it requires one coherent
    /// live recommendation, a current time window, trustworthy measured carry depth, a real route and
    /// one fresh, accurate Watch fix that has not moved beyond the recommendation's origin window.
    public func rootCaddieLayerAvailable(at fix: WatchLocationFix?) -> Bool {
        guard let fix,
              fix.coordinate.latitude.isFinite,
              (-90...90).contains(fix.coordinate.latitude),
              fix.coordinate.longitude.isFinite,
              (-180...180).contains(fix.coordinate.longitude),
              fix.horizontalAccuracyM.isFinite,
              (0...15).contains(fix.horizontalAccuracyM),
              let state = activeHoleState,
              let recommendation = state.rootCaddieRecommendation,
              state.decisionId == recommendation.decisionId,
              state.suggestedClub?.trimmingCharacters(in: .whitespacesAndNewlines)
                == recommendation.clubName.trimmingCharacters(in: .whitespacesAndNewlines),
              (state.holeMap?.route?.count ?? 0) >= 2,
              recommendation.source == "live",
              ["automatic", "manual"].contains(recommendation.mode),
              ["high", "medium"].contains(recommendation.confidence),
              recommendation.sampleSize >= 10,
              recommendation.evidenceCount > 0,
              recommendation.aimCarryM.isFinite, recommendation.aimCarryM > 0,
              recommendation.carryP10M.isFinite, recommendation.carryP10M > 0,
              recommendation.carryP90M.isFinite,
              recommendation.carryP90M >= recommendation.carryP10M,
              recommendation.carryP10M <= recommendation.aimCarryM,
              recommendation.aimCarryM <= recommendation.carryP90M,
              recommendation.originLatitude.isFinite,
              (-90...90).contains(recommendation.originLatitude),
              recommendation.originLongitude.isFinite,
              (-180...180).contains(recommendation.originLongitude),
              recommendation.originAccuracyM.isFinite,
              (0...15).contains(recommendation.originAccuracyM),
              recommendation.maximumMovementM.isFinite,
              recommendation.maximumMovementM > 0
        else {
            return false
        }

        let formatter = ISO8601DateFormatter()
        guard let generatedAt = formatter.date(from: recommendation.generatedAt),
              let validUntil = formatter.date(from: recommendation.validUntil),
              let fixCapturedAt = formatter.date(from: fix.capturedAt),
              let current = formatter.date(from: now()),
              generatedAt < validUntil,
              generatedAt <= current,
              current < validUntil,
              fixCapturedAt <= current,
              current.timeIntervalSince(fixCapturedAt) <= 15,
              WatchGeoMath.metres(
                recommendation.originLatitude,
                recommendation.originLongitude,
                fix.coordinate.latitude,
                fix.coordinate.longitude
              ) <= recommendation.maximumMovementM else {
            return false
        }
        return true
    }

    /// Source elevation is metres; every player-facing Watch distance is yards (L21).
    public var activePlaysLikeDeltaYards: Int {
        WatchUnits.yards(activeHoleState?.elevationDeltaM ?? 0)
    }

    // round-13 navigation between the standalone round screens (menu hub → scorecard / hole select).
    public func openScorecard() { screen = .scorecard }
    public func openCurrentHoleShots() { screen = .currentHoleShots }
    public func openHoleSelect() { screen = .holeSelect }
    public func openMenu() { screen = .menu }
    public func openHoleMap() { screen = .holeMap }
    public func openCaddie() {
        guard caddieDetailAvailable else { return }
        screen = .caddie
    }
    public func openHazards() {
        guard hazardDetailAvailable else { return }
        screen = .hazards
    }
    public func backToMenu() { screen = .menu }
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

    /// Only explicit HIT/LEFT/RIGHT facts on scored holes enter the fairway denominator. Unknown and
    /// legacy values stay unknown instead of becoming misses.
    public var fairwaySummary: WatchOutcomeSummary? {
        var hits = 0
        var recorded = 0
        for state in scoredHoleStates {
            guard let rawResult = state.fairwayResult?.uppercased(),
                  let result = WatchFairwayResult(rawValue: rawResult) else {
                continue
            }
            switch result {
            case .hit:
                hits += 1
                recorded += 1
            case .left, .right:
                recorded += 1
            }
        }
        guard recorded > 0 else { return nil }
        return WatchOutcomeSummary(hits: hits, recorded: recorded)
    }

    /// GIR is summarized only when a scored hole carries an explicit Boolean outcome.
    public var girSummary: WatchOutcomeSummary? {
        var hits = 0
        var recorded = 0
        for state in scoredHoleStates {
            guard let madeGIR = state.greenInRegulation else { continue }
            recorded += 1
            if madeGIR { hits += 1 }
        }
        guard recorded > 0 else { return nil }
        return WatchOutcomeSummary(hits: hits, recorded: recorded)
    }

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
            courseName: seed.courseName,
            pendingManualShot: existing?.pendingManualShot,
            pendingAutoShotCandidate: existing?.pendingAutoShotCandidate,
            scoreDraft: existing?.scoreDraft
        )
        try? store.save(persisted)
        round = persisted
        restoreInteractionState(from: persisted)
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
        restoreInteractionState(from: persisted)
    }

    public func refreshFromStore() {
        let persisted = store.load()
        round = persisted
        restoreInteractionState(from: persisted)
    }

    private func restoreInteractionState(from persisted: WatchRoundStore.PersistedRound?) {
        pendingManualShot = persisted?.pendingManualShot
        pendingAutoShotCandidate = persisted?.pendingAutoShotCandidate
        guard let draft = persisted?.scoreDraft,
              persisted?.holeStates.contains(where: { $0.hole == draft.hole }) == true else {
            scoringHole = nil
            draftScore = 0
            draftPutts = 0
            draftPenalty = 0
            draftFairway = nil
            scoreFlowStep = .recommendation
            advanceAfterScoring = true
            if let pendingManualShot, pendingManualShot.candidateFromHole == nil {
                screen = .clubPrompt
            } else if pendingAutoShotCandidate != nil {
                screen = .autoShotCandidate
            } else {
                screen = .home
            }
            return
        }

        scoringHole = draft.hole
        draftScore = draft.score
        draftPutts = draft.putts
        draftPenalty = draft.penalty
        draftFairway = draft.fairway
        scoreFlowStep = draft.step
        advanceAfterScoring = draft.advanceAfterSave
        screen = .scoring
    }

    private func persistInteractionState() {
        guard var current = round else { return }
        current.pendingManualShot = pendingManualShot
        current.pendingAutoShotCandidate = pendingAutoShotCandidate
        if let scoringHole {
            current.scoreDraft = WatchScoreDraft(
                hole: scoringHole,
                score: draftScore,
                putts: draftPutts,
                penalty: draftPenalty,
                fairway: draftFairway,
                step: scoreFlowStep,
                advanceAfterSave: advanceAfterScoring
            )
        } else {
            current.scoreDraft = nil
        }
        try? store.save(current)
        round = current
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
        persistInteractionState()
    }

    // MARK: - manual shot

    public func setAutoShotEnabled(_ enabled: Bool) {
        guard autoShotEnabled != enabled else { return }
        autoShotEnabled = enabled
        persistAutoShotEnabled(enabled)
        if !enabled, pendingAutoShotCandidate != nil {
            pendingAutoShotCandidate = nil
            screen = .home
            persistInteractionState()
        }
    }

    /// Stage a detector observation without creating a shot event. Returns true only when the candidate
    /// became the active user decision, allowing the caller to play one haptic and suppress duplicates.
    @discardableResult
    public func proposeAutoShotCandidate(
        latitude: Double,
        longitude: Double,
        horizontalAccuracyM: Double,
        capturedAt: String
    ) -> Bool {
        guard autoShotEnabled,
              round != nil,
              pendingAutoShotCandidate == nil,
              pendingManualShot == nil,
              round?.scoreDraft == nil,
              screen == .home || screen == .holeMap,
              let location = WatchShotLocationValue(
                  latitude: latitude,
                  longitude: longitude,
                  horizontalAccuracyM: horizontalAccuracyM
              ) else { return false }
        pendingAutoShotCandidate = WatchPendingAutoShotCandidate(
            location: location,
            capturedAt: capturedAt,
            resumeHoleMap: screen == .holeMap ? true : nil
        )
        screen = .autoShotCandidate
        persistInteractionState()
        return true
    }

    public func rejectAutoShotCandidate() {
        guard let candidate = pendingAutoShotCandidate else { return }
        pendingAutoShotCandidate = nil
        screen = candidate.resumeHoleMap == true ? .holeMap : .home
        persistInteractionState()
    }

    public func acceptAutoShotCandidate() {
        guard let candidate = pendingAutoShotCandidate else { return }
        pendingAutoShotCandidate = nil
        beginManualShot(
            latitude: candidate.location.latitude,
            longitude: candidate.location.longitude,
            horizontalAccuracyM: candidate.location.horizontalAccuracyM,
            capturedAt: candidate.capturedAt,
            resumeHoleMap: candidate.resumeHoleMap == true
        )
    }

    public func beginManualShot(
        latitude: Double,
        longitude: Double,
        horizontalAccuracyM: Double,
        capturedAt: String,
        resumeHoleMap: Bool = false
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
                capturedAt: capturedAt,
                resumeHoleMap: resumeHoleMap ? true : nil
            )
            startScoringActiveHole()
        } else {
            pendingManualShot = makePendingShot(
                assignedTo: hole,
                candidateFromHole: nil,
                location: location,
                capturedAt: capturedAt,
                resumeHoleMap: resumeHoleMap ? true : nil
            )
            screen = .clubPrompt
            persistInteractionState()
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
        screen = pendingManualShot.resumeHoleMap == true ? .holeMap : .home
        persistInteractionState()
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
        shotTypeOverride: String? = nil,
        resumeHoleMap: Bool? = nil
    ) -> WatchPendingManualShot {
        let shotNumber = recordedShotCount(for: hole.hole) + 1
        return WatchPendingManualShot(
            hole: hole.hole,
            candidateFromHole: candidateFromHole,
            location: location,
            capturedAt: capturedAt,
            shotNumber: shotNumber,
            shotType: shotTypeOverride ?? (shotNumber == 1 ? "tee" : (hole.shotType ?? "approach")),
            resumeHoleMap: resumeHoleMap
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
            shotTypeOverride: asRecovery ? "recovery" : nil,
            resumeHoleMap: pending.resumeHoleMap
        )
    }

    private func recordedShotCount(for hole: Int) -> Int {
        round?.pendingEvents.reduce(into: 0) { count, event in
            if event.hole == hole, event.kind == .location {
                count += 1
            }
        } ?? 0
    }

    public func adjustDraftScore(_ delta: Int) {
        draftScore = max(1, draftScore + delta)
        persistInteractionState()
    }

    public func adjustDraftPutts(_ delta: Int) {
        draftPutts = max(0, draftPutts + delta)
        persistInteractionState()
    }

    public func adjustDraftPenalty(_ delta: Int) {
        draftPenalty = max(0, draftPenalty + delta)
        persistInteractionState()
    }

    public func startManualScoreEntry() {
        guard screen == .scoring else { return }
        scoreFlowStep = .score
        persistInteractionState()
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
        persistInteractionState()
    }

    public func selectDraftFairway(_ result: WatchFairwayResult) {
        draftFairway = result
        scoreFlowStep = .penalty
        persistInteractionState()
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
            persistInteractionState()
            return
        }
        scoringHole = nil
        screen = .home
        persistInteractionState()
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
        let selectedFairway = hole.par == 3 ? nil : draftFairway?.rawValue
        if draftScore != hole.score || selectedFairway != hole.fairwayResult?.uppercased() {
            latest = record(
                hole: hole.hole,
                kind: .score,
                value: String(draftScore),
                fairwayResult: selectedFairway
            )
        }
        if draftPutts != hole.putts {
            latest = record(hole: hole.hole, kind: .putt, value: String(draftPutts))
        }
        if draftPenalty != hole.penaltyCount {
            latest = record(hole: hole.hole, kind: .penalty, value: String(draftPenalty))
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
        persistInteractionState()
    }

    private func record(
        hole: Int,
        kind: WatchInputKind,
        value: String,
        createdAt: String? = nil,
        contextClub: String? = nil,
        shotType: String? = nil,
        fairwayResult: String? = nil
    ) -> WatchRoundStore.PersistedRound? {
        let event = WatchInputEvent(
            eventId: makeEventId(),
            roundId: round?.roundId ?? "",
            hole: hole,
            kind: kind,
            value: value,
            createdAt: createdAt ?? now(),
            contextClub: contextClub,
            shotType: shotType,
            fairwayResult: fairwayResult
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

    /// Finish the round only after every queued event is explicitly acknowledged. Without backend
    /// config, on upload failure, or after a partial acknowledgement, the round and unresolved events
    /// stay on disk for a later retry.
    public func confirmFinish() async {
        guard let current = round else { return }
        isUploading = true
        uploadError = nil
        defer { isUploading = false }
        do {
            var readyToFinish = current
            let pending = current.pendingEvents
            if !pending.isEmpty {
                guard canUpload else {
                    uploadError = "尚未连接，已离线保存"
                    return
                }
                let posted = try await upload(pending, roundId: current.roundId)
                guard let updated = try store.markPosted(eventIds: posted) else {
                    uploadError = "本场状态不可用，未清除记录"
                    return
                }
                round = updated
                guard updated.pendingEvents.isEmpty else {
                    uploadError = "部分记录尚未确认，已离线保存"
                    return
                }
                readyToFinish = updated
            }
            guard canFinish else {
                uploadError = "尚未连接，已离线保存"
                return
            }
            try await finishRemotely(readyToFinish)
            finishLocally()
        } catch {
            uploadError = "上传失败,已离线保存"
        }
    }

    private var canUpload: Bool { uploaderOverride != nil || config != nil }
    private var canFinish: Bool { finisherOverride != nil || config != nil }

    private func finishLocally() {
        store.clear()
        round = nil
        restoreInteractionState(from: nil)
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
        let result = try await client.postEvents(
            events,
            roundId: roundId,
            idempotencyKey: makeEventId()
        )
        return result.acknowledgedEventIds
    }

    private func finishRemotely(_ current: WatchRoundStore.PersistedRound) async throws {
        let metadata = WatchRoundFinishMetadata(
            courseName: current.courseName ?? "Watch round",
            holePars: current.holeStates.sorted { $0.hole < $1.hole }.map(\.par),
            holesCompleted: current.holeStates.filter { $0.score > 0 }.count,
            courseGlobalId: current.holeStates.compactMap(\.globalId).first
        )
        if let finisherOverride {
            try await finisherOverride(current.roundId, metadata)
            return
        }
        guard let config else { throw WatchRoundModelError.notConfigured }
        let client = WatchBackendClient(
            baseURL: config.baseURL,
            adminToken: config.adminToken,
            sessionToken: config.sessionToken,
            sessionTokenExpiresAt: config.sessionTokenExpiresAt,
            clientId: clientId
        )
        try await client.finishRound(roundId: current.roundId, metadata: metadata)
    }
}
