import Foundation
import AICaddieDomain

/// round-12 P3.3 (Watch standalone): the brain that ties the three presentational watch screens
/// (`WatchRoundHomeView` → `WatchScoreHoleView` → `WatchFinishRoundView`) into a working standalone
/// round. It owns the persisted round (`WatchRoundStore`), drives navigation between screens, edits a
/// per-hole scoring draft, turns saves into `WatchInputEvent`s, and on finish uploads the queued events
/// to the backend (directly, via `WatchBackendClient`, with config delivered from the phone).
///
/// Side effects are injectable (`makeEventId` / `now` / `uploader`) so the whole state machine is
/// deterministic under unit test without a network or a real clock.

public enum WatchRoundScreen: Equatable {
    case resume
    case home
    case autoShotCandidate
    case scoring
    case finishing
    case finishConfirmation
    case abandonConfirmation
    case scorecard   // round-13: 计分卡逐洞列表
    case holeSelect  // round-13: 选洞
    case menu        // round-13: 菜单 hub(纯文字,S70 式)
    case holeMap     // watch P1b: 全屏球道图(真几何底图 + 事实标记)
    case viewGreen   // S70 View Green 等价入口；局部 topo + 临时旗位实时距离/四向边距
    case caddie      // S70 式浅层仪表面: 当前洞球童详情
    case hazards     // S70 式浅层仪表面: 当前洞障碍距离
    case clubStats   // 下载球包内的真实球杆 median 距离
    case settings    // 腕上真实设置与系统状态
    case flagDirection // 基于有效真北 heading 的旗向指引
    case turn          // B4b-2 转场: 18 洞球场的第一个半场打完，选第二个 9 洞（前九 / 后九 / 只打 9 洞）
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

/// B6 本洞成绩 rules (README §3): putts and penalties are wheels that wrap (0 sits under the
/// maximum), and the total never drops below putts + penalties + 1.
public enum WatchScoreRules {
    public static let puttRange = 0...5
    public static let penaltyRange = 0...4
    public static let scoreRange = 1...15

    public static func wrap(_ value: Int, in range: ClosedRange<Int>) -> Int {
        let count = range.count
        return range.lowerBound + ((value - range.lowerBound) % count + count) % count
    }

    public static func minimumScore(putts: Int, penalty: Int) -> Int {
        putts + penalty + 1
    }

    /// The total for a requested value: inside `scoreRange` and never below the minimum.
    public static func score(_ requested: Int, putts: Int, penalty: Int) -> Int {
        min(scoreRange.upperBound, max(requested, minimumScore(putts: putts, penalty: penalty), scoreRange.lowerBound))
    }
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

extension WatchPendingManualShot {
    private enum CodingKeys: String, CodingKey {
        case hole
        case candidateFromHole
        case location
        case capturedAt
        case shotNumber
        case shotType
        case resumeHoleMap
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.hole = try container.decode(Int.self, forKey: .hole)
        self.candidateFromHole = try container.decodeIfPresent(Int.self, forKey: .candidateFromHole)
        self.location = try container.decode(WatchShotLocationValue.self, forKey: .location)
        self.capturedAt = try container.decode(String.self, forKey: .capturedAt)
        // Rounds written before ordered shot metadata existed still carry a valid GPS fact. Preserve
        // it with neutral defaults rather than failing the entire persisted-round decode on update.
        self.shotNumber = try container.decodeIfPresent(Int.self, forKey: .shotNumber) ?? 1
        self.shotType = try container.decodeIfPresent(String.self, forKey: .shotType) ?? "approach"
        self.resumeHoleMap = try container.decodeIfPresent(Bool.self, forKey: .resumeHoleMap)
    }
}

extension WatchScoreDraft {
    private enum CodingKeys: String, CodingKey {
        case hole
        case score
        case putts
        case penalty
        case fairway
        case step
        case advanceAfterSave
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.hole = try container.decode(Int.self, forKey: .hole)
        self.score = try container.decode(Int.self, forKey: .score)
        self.putts = try container.decode(Int.self, forKey: .putts)
        self.penalty = try container.decode(Int.self, forKey: .penalty)
        self.fairway = try container.decodeIfPresent(WatchFairwayResult.self, forKey: .fairway)
        self.step = try container.decode(WatchScoreFlowStep.self, forKey: .step)
        // Older score flows always advanced after Save; retain that behaviour when the persisted key
        // predates the explicit control instead of dropping scores, queue and round together.
        self.advanceAfterSave = try container.decodeIfPresent(Bool.self, forKey: .advanceAfterSave) ?? true
    }
}

public struct WatchRoundConfig: Codable, Equatable {
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
    /// A newer phone round that cannot safely replace this Watch round until the player resolves it.
    @Published public private(set) var pendingPhoneRoundCourseName: String?
    /// Terminal lifecycle event consumed by the app shell to clear the second WatchConnectivity
    /// cache, stop runtime services and retract the phone seed. It is not the persistence authority;
    /// `WatchRoundStore` writes the durable closure before publishing this value.
    @Published public private(set) var lastRoundClosure: WatchRoundClosure? = nil
    /// The shared nine-loop state machine at the turn (前九 / 后九, the other half preselected, the
    /// same half allowed, 只打 9 洞). Nil outside the turn.
    @Published public private(set) var turnPlan: NineLoopPlan?
    @Published public private(set) var isLoadingSecondLoop = false
    /// Honest reason the chosen second nine could not be prepared (offline without a whole-course
    /// download, network failure). The round stays at the turn; nothing is invented.
    @Published public private(set) var turnMessage: String?

    /// Resolves round holes 10–18 for the turn (the app wires `WatchCourseLibrary.secondLoop`).
    public var secondLoopLoader: ((WatchSecondLoopRequest) async -> WatchSecondLoopResult)?

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
    private var scoreEntryReturnScreen: WatchRoundScreen = .home
    private var scorecardReturnScreen: WatchRoundScreen = .menu
    private var screenBeforeFinishConfirmation: WatchRoundScreen = .finishing
    private var screenBeforeAbandon: WatchRoundScreen = .finishing
    private var isRetryingDeferredFinishes = false
    private var pendingPhoneRoundSeed: WatchRoundSeed?
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
        if persisted == nil {
            restoreInteractionState(from: nil)
        } else {
            // A restored or update-migrated round never throws the player directly into an old score
            // draft. The draft remains intact and is restored only after explicit Resume.
            pendingManualShot = persisted?.pendingManualShot
            pendingAutoShotCandidate = persisted?.pendingAutoShotCandidate
            screen = .resume
        }
    }

    /// Default standalone model backed by the on-watch document store (for `@StateObject` in the app).
    public convenience init() {
        self.init(store: WatchRoundStore())
    }

    // MARK: - derived state (drives the views)

    public var activeHole: Int {
        guard let round else { return 0 }
        return round.holeStates.first { $0.hole == round.activeHole }?.hole
            ?? round.holeStates.first?.hole
            ?? round.activeHole
    }

    public var activeHoleState: WatchRoundState? {
        guard let round else { return nil }
        return round.holeStates.first { $0.hole == round.activeHole } ?? round.holeStates.first
    }

    /// The current round's saved View Green choice for one hole. Corrupt/out-of-frame values fail
    /// closed to the package's canonical pin instead of sending a marker off the visible course.
    public func greenPlacement(forHole hole: Int, globalId: Int?) -> WatchGreenPlacement? {
        round?.greenPlacements?.last(where: { placement in
            placement.matches(hole: hole, globalId: globalId)
                && placement.normalizedPinX.isFinite
                && placement.normalizedPinY.isFinite
                && (0...1).contains(placement.normalizedPinX)
                && (0...1).contains(placement.normalizedPinY)
                && placement.rotationDegrees.isFinite
        })
    }

    /// Persist a moved flag and the player's paper-alignment rotation as one per-hole fact. This is
    /// intentionally local round state, not a backend scoring event and not immutable course data.
    public func saveGreenPlacement(
        hole: Int,
        globalId: Int?,
        normalizedPinX: Double,
        normalizedPinY: Double,
        rotationDegrees: Double
    ) {
        guard var current = round,
              current.holeStates.contains(where: { $0.hole == hole }),
              normalizedPinX.isFinite,
              normalizedPinY.isFinite,
              (0...1).contains(normalizedPinX),
              (0...1).contains(normalizedPinY),
              rotationDegrees.isFinite else { return }

        let wrappedRotation = Self.wrappedGreenRotation(rotationDegrees)
        let placement = WatchGreenPlacement(
            hole: hole,
            globalId: globalId,
            normalizedPinX: normalizedPinX,
            normalizedPinY: normalizedPinY,
            rotationDegrees: wrappedRotation
        )
        var placements = current.greenPlacements ?? []
        placements.removeAll { $0.hole == hole }
        placements.append(placement)
        placements.sort { $0.hole < $1.hole }
        current.greenPlacements = placements
        do {
            try store.save(current)
            round = current
        } catch {
            return
        }
    }

    static func wrappedGreenRotation(_ degrees: Double) -> Double {
        let positive = (degrees + 180).truncatingRemainder(dividingBy: 360)
        return (positive < 0 ? positive + 360 : positive) - 180
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
        let watchShots: [(id: String, shot: WatchShotLocationValue)] = round.pendingEvents.compactMap { event in
            guard event.hole == round.activeHole, event.kind == .location,
                  let shot = WatchShotLocationValue(encodedValue: event.value) else { return nil }
            return (event.eventId, shot)
        }
        let phoneShotIds = Set(round.phoneShots?.first { $0.hole == round.activeHole }?.eventIds ?? [])
        let phoneLast = round.holeStates.first { $0.hole == round.activeHole }.flatMap { state in
            state.lastShotLatitude.flatMap { latitude in
                state.lastShotLongitude.flatMap { longitude in
                    WatchShotLocationValue(latitude: latitude, longitude: longitude, horizontalAccuracyM: 0)
                }
            }
        }
        // A Watch shot the phone has not acknowledged yet is the newest; otherwise the phone's
        // newest shot (marked on either device) is, so a shot marked only on the phone counts too.
        let origin = watchShots.last { !phoneShotIds.contains($0.id) }?.shot
            ?? phoneLast
            ?? watchShots.last?.shot
        guard let origin else { return nil }
        return WatchGeoMath.metres(origin.latitude, origin.longitude, current.latitude, current.longitude)
    }

    /// All holes' states, hole-ordered — feeds the round-13 计分卡 / 选洞 / 18洞环.
    public var allHoleStates: [WatchRoundState] {
        (round?.holeStates ?? []).sorted { $0.hole < $1.hole }
    }

    /// The detail surface may show an offline/prepared recommendation. It is deliberately separate from
    /// the stricter Hole Root gate below: useful detail data must not automatically become a live call.
    public var caddieDetailAvailable: Bool {
        guard let state = activeHoleState else { return false }
        // With plans on the hole, only a current one opens the detail: a finished or stale plan
        // (and the decision's own text about it) is never brought back from the menu.
        guard state.caddieOptions.isEmpty else { return !currentCaddieOptions(progressM: nil).isEmpty }
        let club = state.suggestedClub?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return !club.isEmpty
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

    /// Driver Distance is a Tee fact, not an AI recommendation. Keep its location gate independent so
    /// a player can still see the arc when no prepared Caddie option is available.
    public func playerAtActiveTee(at fix: WatchLocationFix?) -> Bool {
        guard let fix,
              fix.coordinate.latitude.isFinite,
              (-90...90).contains(fix.coordinate.latitude),
              fix.coordinate.longitude.isFinite,
              (-180...180).contains(fix.coordinate.longitude),
              fix.horizontalAccuracyM.isFinite,
              (0...20).contains(fix.horizontalAccuracyM),
              let state = activeHoleState,
              let teeLatitude = state.teeLatitude,
              let teeLongitude = state.teeLongitude,
              teeLatitude.isFinite, (-90...90).contains(teeLatitude),
              teeLongitude.isFinite, (-180...180).contains(teeLongitude) else {
            return false
        }
        let distanceFromTeeM = WatchGeoMath.metres(
            teeLatitude,
            teeLongitude,
            fix.coordinate.latitude,
            fix.coordinate.longitude
        )
        // Keep the arc on the selected Tee box, not the first stretch of fairway. Allow only a
        // bounded GPS cushion; the former 35 m + full accuracy rule could remain active 55 m away.
        let teeRadiusM = 25 + min(fix.horizontalAccuracyM, 10)
        return distanceFromTeeM <= teeRadiusM
    }

    /// A downloaded course already contains a real Tee recommendation, landing point, route and the
    /// player's bag distances. Keep that prepared plan visible while the player is still at this Tee;
    /// once they leave, only a fresh live recommendation may remain on Hole Root.
    public func preparedRootCaddieLayerAvailable(at fix: WatchLocationFix?) -> Bool {
        guard playerAtActiveTee(at: fix),
              let state = activeHoleState,
              state.geometryCoverage?.caseInsensitiveCompare("ready") == .orderedSame,
              state.suggestedClub?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false,
              !state.caddieOptions.isEmpty,
              (state.holeMap?.route?.count ?? 0) >= 2 else {
            return false
        }
        return true
    }

    /// Source elevation is metres; every player-facing Watch distance is yards (L21).
    public var activePlaysLikeDeltaYards: Int {
        WatchUnits.yards(activeHoleState?.elevationDeltaM ?? 0)
    }

    // round-13 navigation between the standalone round screens (menu hub → scorecard / hole select).
    public func openScorecard() {
        scorecardReturnScreen = .menu
        screen = .scorecard
    }
    public func openScorecardFromFinish() {
        guard screen == .finishing else { return }
        scorecardReturnScreen = .finishing
        screen = .scorecard
    }
    public func closeScorecard() {
        guard screen == .scorecard else { return }
        screen = scorecardReturnScreen
    }
    public func openHoleSelect() { screen = .holeSelect }
    public func openMenu() { screen = .menu }
    public func openSettings() { screen = .settings }
    public func openFlagDirection() { screen = .flagDirection }
    public func openClubStats() {
        guard clubStatsAvailable else { return }
        screen = .clubStats
    }
    public func openHoleMap() { screen = .holeMap }
    public func openViewGreen() { screen = .viewGreen }
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

    public var clubStatsAvailable: Bool {
        allHoleStates.contains { state in
            state.availableClubs.contains { club in
                guard let metres = club.medianM else { return false }
                return metres.isFinite && metres > 0
            }
        }
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

    /// A freshly delivered phone round shares the safe Resume gate with a restored round, but it has
    /// nothing the backend can finish yet. Drafts and unsynced facts count as real progress too.
    public var hasRecordedProgress: Bool {
        scoredHoles > 0
            || pendingUploads > 0
            || pendingManualShot != nil
            || pendingAutoShotCandidate != nil
            || round?.scoreDraft != nil
    }

    /// Save & End must have at least one fact that the backend can materialize as a round. A staged
    /// shot must be resolved first; a score draft is safe because confirmFinish materializes it.
    public var canSaveAndEndFromResume: Bool {
        guard let round else { return false }
        guard round.pendingManualShot == nil, round.pendingAutoShotCandidate == nil else {
            return false
        }
        return hasMaterializableFacts(in: round)
    }

    private func hasMaterializableFacts(in round: WatchRoundStore.PersistedRound) -> Bool {
        if round.holeStates.contains(where: { $0.score > 0 }) {
            return true
        }
        if round.pendingEvents.contains(where: { $0.kind == .score }) {
            return true
        }
        guard let draft = round.scoreDraft, draft.score > 0 else { return false }
        return round.holeStates.contains { $0.hole == draft.hole }
    }

    public var courseName: String { round?.courseName ?? "" }

    /// The printed number of round hole `hole` (B4b-2 §2); the round number when unknown.
    public func displayHoleNumber(_ hole: Int) -> Int {
        round?.holeStates.first { $0.hole == hole }?.displayHoleNumber ?? hole
    }

    public var activeDisplayHoleNumber: Int { displayHoleNumber(activeHole) }

    /// The seed's own table (round hole → globalId / localHole / courseHoleNumber) under its loop key.
    static func seedHasValidIdentity(_ seed: WatchRoundSeed) -> Bool {
        let states = seed.holes.map { hole in
            WatchRoundState(
                roundId: seed.roundId,
                hole: hole.hole,
                par: hole.par,
                distanceM: hole.distanceM,
                selectedClub: nil,
                globalId: hole.globalId,
                sourceLocalHole: hole.localHole,
                courseHoleNumber: hole.courseHoleNumber,
                score: 0,
                putts: 0,
                penaltyCount: 0,
                caddieConfidence: "offline"
            )
        }
        // Identity only: the real active hole is checked on the merged round before it is saved.
        return WatchRoundStore.PersistedRound(
            roundId: seed.roundId,
            activeHole: states.first?.hole ?? 0,
            holeStates: states,
            courseGlobalId: seed.globalId,
            loopKey: seed.loopKey
        ).hasValidIdentity
    }

    // MARK: - seeding (from a phone-synced round or a fetched package)

    /// Start (or refresh) the real phone-selected round. Existing snapshots and unsynced Watch edits
    /// for the same round are retained; newly added holes receive a truthful blank state from the seed.
    public func applyRoundSeed(_ seed: WatchRoundSeed) {
        guard !seed.holes.isEmpty, !store.isClosed(roundId: seed.roundId) else { return }
        // A seed must carry the complete physical identity of every hole for its loop key; a
        // legacy/contradictory seed never replaces or refreshes the round.
        guard Self.seedHasValidIdentity(seed) else { return }
        if pendingPhoneRoundSeed?.roundId == seed.roundId {
            pendingPhoneRoundSeed = nil
            pendingPhoneRoundCourseName = nil
        }
        // A blank standalone round is only a stale course pointer and can yield to the phone's real
        // round. Any score, event, draft or staged shot is user data: retain it, stop the user from
        // accidentally recording against the wrong roundId, and expose the conflict at Resume.
        if let current = round, current.roundId != seed.roundId {
            if canReplaceWithPhoneSeed(current) {
                do {
                    let closure = try store.closeActiveRound(
                        roundId: current.roundId,
                        disposition: .abandoned,
                        closedAt: now()
                    )
                    round = nil
                    restoreInteractionState(from: nil)
                    lastRoundClosure = closure
                } catch {
                    pendingPhoneRoundSeed = seed
                    pendingPhoneRoundCourseName = seed.courseName
                    screen = .resume
                    uploadError = "旧球局无法安全关闭，请重试"
                    return
                }
            } else {
                pendingPhoneRoundSeed = seed
                pendingPhoneRoundCourseName = seed.courseName
                pendingManualShot = current.pendingManualShot
                pendingAutoShotCandidate = current.pendingAutoShotCandidate
                screen = .resume
                return
            }
        }
        let createsPhoneRound = round == nil
        let awaitingExplicitResume = screen == .resume || createsPhoneRound
        let existing = round?.roundId == seed.roundId ? round : nil
        let seededStates = seed.holes
            .sorted { $0.hole < $1.hole }
            .map { hole in
                let seeded = WatchRoundState(
                    roundId: seed.roundId,
                    hole: hole.hole,
                    par: hole.par,
                    distanceM: hole.distanceM,
                    teeLatitude: hole.teeLatitude,
                    teeLongitude: hole.teeLongitude,
                    selectedClub: nil,
                    globalId: hole.globalId,
                    sourceLocalHole: hole.localHole,
                    courseHoleNumber: hole.courseHoleNumber,
                    score: 0,
                    putts: 0,
                    penaltyCount: 0,
                    caddieConfidence: "offline"
                )
                if let retained = existing?.holeStates.first(where: { $0.hole == hole.hole }) {
                    return retained.applyingCourseMapUpgrade(seeded)
                }
                return seeded
            }
        // The Watch may already have taken the turn (`G:back` → `G:back+G:front`) while the phone
        // still holds the one-half start. That stale seed must not drop round holes 10–18 or
        // shorten the ordered loop key.
        var states = seededStates
        var loopKey = seed.loopKey
        if let existingKey = existing?.loopKey,
           existingKey.hasPrefix(seed.loopKey + "+"),
           let existing {
            let seededHoles = Set(seededStates.map(\.hole))
            states += existing.holeStates.filter { !seededHoles.contains($0.hole) }
            states.sort { $0.hole < $1.hole }
            loopKey = existingKey
        }
        let holeNumbers = Set(states.map(\.hole))
        let retainedActiveHole = existing?.activeHole
        let activeHole = retainedActiveHole.flatMap { holeNumbers.contains($0) ? $0 : nil }
            ?? (holeNumbers.contains(seed.activeHole) ? seed.activeHole : states[0].hole)
        let retainedScoreDraft = existing?.scoreDraft.flatMap { draft in
            holeNumbers.contains(draft.hole) ? draft : nil
        }
        let retainedManualShot = existing?.pendingManualShot.flatMap { shot -> WatchPendingManualShot? in
            guard holeNumbers.contains(shot.hole) else { return nil }
            guard let candidateFromHole = shot.candidateFromHole else { return shot }
            return holeNumbers.contains(candidateFromHole) ? shot : nil
        }
        let retainedGreenPlacements = existing?.greenPlacements?.filter { placement in
            states.contains { state in
                placement.matches(hole: state.hole, globalId: state.globalId)
            }
        }
        // The phone's shots and snapshot order are round-owned: a same-round seed never forgets
        // them (that would bring a played plan back).
        let retainedPhoneShots = existing?.phoneShots?.filter { holeNumbers.contains($0.hole) }
        let persisted = WatchRoundStore.PersistedRound(
            roundId: seed.roundId,
            activeHole: activeHole,
            holeStates: states,
            pendingEvents: existing?.pendingEvents ?? [],
            courseName: seed.courseName,
            courseGlobalId: seed.globalId ?? existing?.courseGlobalId ?? states.first?.globalId,
            teeBox: seed.teeBox ?? existing?.teeBox,
            loopKey: loopKey,
            pendingManualShot: retainedManualShot,
            pendingAutoShotCandidate: existing?.pendingAutoShotCandidate,
            scoreDraft: retainedScoreDraft,
            greenPlacements: retainedGreenPlacements,
            phoneShots: retainedPhoneShots
        )
        guard persisted.hasValidIdentity else { return }
        try? store.save(persisted)
        round = persisted
        let removedCurrentInteraction =
            (existing?.scoreDraft != nil && retainedScoreDraft == nil)
            || (existing?.pendingManualShot != nil && retainedManualShot == nil)
        if removedCurrentInteraction
            || scoringHole.map({ !holeNumbers.contains($0) }) == true {
            restoreInteractionState(from: persisted)
        }
        if awaitingExplicitResume {
            pendingManualShot = persisted.pendingManualShot
            pendingAutoShotCandidate = persisted.pendingAutoShotCandidate
            screen = .resume
        }
    }

    private func canReplaceWithPhoneSeed(_ current: WatchRoundStore.PersistedRound) -> Bool {
        !hasMaterializableFacts(in: current)
            && current.pendingEvents.isEmpty
            && current.pendingManualShot == nil
            && current.pendingAutoShotCandidate == nil
            && current.scoreDraft == nil
            && (current.greenPlacements?.isEmpty ?? true)
    }

    /// Merge the richer live snapshot for one hole without dropping the seeded course or other holes.
    /// Pending on-Watch edits are replayed so a stale phone snapshot cannot silently undo them.
    public func receivePhoneState(_ state: WatchRoundState) {
        guard let current = round, current.roundId == state.roundId,
              !store.isClosed(roundId: state.roundId) else {
            return
        }
        // Order before anything is replaced: a snapshot not newer than the last one applied to this
        // hole (a late transferUserInfo delivery, a duplicate) never rolls back its state.
        let lastApplied = current.phoneShots?.first { $0.hole == state.hole }
        if let revision = state.snapshotRevision, let lastApplied, revision <= lastApplied.revision {
            return
        }
        var merged = current.pendingEvents.reduce(state) { partial, event in
            partial.applying(event)
        }
        // A phone snapshot may predate physical identity; keep the round's printed hole number.
        if merged.courseHoleNumber == nil || merged.sourceLocalHole == nil,
           let previous = current.holeStates.first(where: { $0.hole == merged.hole }) {
            merged = merged.replacingRoundId(
                merged.roundId,
                hole: merged.hole,
                sourceLocalHole: merged.sourceLocalHole ?? previous.sourceLocalHole,
                courseHoleNumber: merged.courseHoleNumber ?? previous.courseHoleNumber
            )
        }
        guard var persisted = try? store.upsertHoleState(merged, makeActive: false) else {
            return
        }
        // This snapshot is now the newest applied to the hole: record its revision and the phone's
        // current shots (a phone shot deleted later leaves the newer, smaller set).
        if let revision = state.snapshotRevision {
            let applied = WatchPhoneShotSet(
                hole: state.hole,
                eventIds: state.phoneShotEventIds ?? lastApplied?.eventIds ?? [],
                revision: revision
            )
            persisted.phoneShots = (persisted.phoneShots ?? []).filter { $0.hole != state.hole } + [applied]
            try? store.save(persisted)
        }
        self.round = persisted
    }

    /// The active hole's caddie options as they stand now for a player `progressM` metres along
    /// the route (nil: unknown): shots recorded since each plan was made are gone and every offset
    /// counts from the player. The 方案 page (club tag, note, legs) and the 球童 detail all read
    /// these, never the raw `caddieOptions`.
    public func currentCaddieOptions(progressM: Double?) -> [WatchCaddieOption] {
        guard let state = activeHoleState else { return [] }
        let shots = knownShotEventIds(for: state.hole)
        // A plan with nothing left to play (finished, or a stale live plan that failed closed) is
        // not offered at all.
        return state.caddieOptions
            .map { $0.remaining(fromProgressM: progressM, watchShotEventIds: shots) }
            .filter { $0.plan.map { !$0.isEmpty } ?? true }
    }

    /// Replace the active round with a fresh set of per-hole snapshots and start at the given hole.
    public func seedRound(
        _ states: [WatchRoundState],
        activeHole: Int? = nil,
        courseName: String? = nil,
        courseGlobalId: Int? = nil,
        teeBox: String? = nil,
        loopKey: String? = nil
    ) {
        guard let first = states.first else { return }
        var persisted = WatchRoundStore.PersistedRound(roundId: first.roundId)
        persisted.holeStates = states.sorted { $0.hole < $1.hole }
        persisted.activeHole = activeHole ?? persisted.holeStates.first?.hole ?? 0
        persisted.courseName = courseName
        persisted.courseGlobalId = courseGlobalId
        persisted.teeBox = teeBox
        persisted.loopKey = loopKey
        // The same identity gate as the round store: a course round must carry its canonical loop
        // key and every hole's physical identity; nothing is derived from `hole`.
        guard persisted.hasValidIdentity else {
            uploadError = "球局数据不完整，无法开局"
            return
        }
        try? store.save(persisted)
        round = persisted
        restoreInteractionState(from: persisted)
    }

    /// Merge a background course-map upgrade without reseeding the round or moving the live cursor.
    /// Pending events and in-progress score/shot drafts remain in the existing persisted container.
    public func applyCourseMapUpgrade(_ states: [WatchRoundState]) {
        guard var current = round, !states.isEmpty else { return }
        let upgrades = Dictionary(uniqueKeysWithValues: states.map { ($0.hole, $0) })
        current.holeStates = current.holeStates.map { state in
            guard let upgraded = upgrades[state.hole] else { return state }
            return state.applyingCourseMapUpgrade(upgraded)
        }
        do {
            try store.save(current)
            round = current
        } catch {
            return
        }
    }

    public func refreshFromStore() {
        let persisted = store.load()
        round = persisted
        if persisted == nil {
            restoreInteractionState(from: nil)
        } else {
            pendingManualShot = persisted?.pendingManualShot
            pendingAutoShotCandidate = persisted?.pendingAutoShotCandidate
            screen = .resume
        }
    }

    public func resumeRound() {
        guard screen == .resume, let round else { return }
        restoreInteractionState(from: round)
    }

    private func restoreInteractionState(from persisted: WatchRoundStore.PersistedRound?) {
        pendingManualShot = persisted?.pendingManualShot
        pendingAutoShotCandidate = persisted?.pendingAutoShotCandidate
        scoreEntryReturnScreen = .home
        guard let draft = persisted?.scoreDraft,
              persisted?.holeStates.contains(where: { $0.hole == draft.hole }) == true else {
            scoringHole = nil
            draftScore = 0
            draftPutts = 0
            draftPenalty = 0
            draftFairway = nil
            scoreFlowStep = .recommendation
            advanceAfterScoring = true
            screen = .home
            // A candidate persisted by an older build becomes the same undoable shot, never a page.
            if pendingAutoShotCandidate != nil { acceptAutoShotCandidate() }
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
        scoreEntryReturnScreen = .home
        beginScoring(
            hole: hole,
            advanceAfterSave: true,
            // A bootstrap round has no factual Par yet. It can still accept manual scoring, but it
            // must never present a fabricated recommended score while the package is pending.
            offerRecommendation: hole.score == 0 && hole.geometryCoverage != "pending"
        )
    }

    /// Edit a completed/historical hole without moving the live-play cursor.
    public func startEditingHole(_ holeNumber: Int) {
        guard let hole = round?.holeStates.first(where: { $0.hole == holeNumber }) else { return }
        scoreEntryReturnScreen = screen == .scorecard ? .scorecard : .home
        beginScoring(hole: hole, advanceAfterSave: false, offerRecommendation: false)
    }

    private func beginScoring(
        hole: WatchRoundState,
        advanceAfterSave: Bool,
        offerRecommendation: Bool
    ) {
        let unscored = hole.score == 0
        let shotCount = recordedShotCount(for: hole.hole)
        draftScore = unscored
            ? (shotCount > 0 ? shotCount + 2 : (hole.geometryCoverage == "pending" ? 1 : hole.par))
            : hole.score
        draftPutts = unscored ? 2 : hole.putts
        draftPenalty = hole.penaltyCount
        draftFairway = hole.fairwayResult.flatMap { WatchFairwayResult(rawValue: $0.uppercased()) }
        scoringHole = hole.hole
        self.advanceAfterScoring = advanceAfterSave
        scoreFlowStep = offerRecommendation ? .recommendation : .score
        screen = .scoring
        persistInteractionState()
    }

    // MARK: - hole end (B6)

    /// The active hole's 洞结束 detector, rebuilt whenever the active hole changes.
    private var holeEndDetector: (hole: Int, detector: WatchHoleEndDetector)?
    /// A hole end the detector reported (once) while the model could not open scoring yet — a menu
    /// or a pending shot on screen. It is kept and consumed on the next fix that can take it, so
    /// the one-shot trigger is never lost.
    private(set) var pendingHoleEnd: Int?

    /// Feed every live fix. Once the player has been on the green and walks more than 25 m off it
    /// toward the next tee, an unscored hole opens 本洞成绩 (README §3); the other trigger is the next
    /// hole's first shot (`beginManualShot`). Returns true when it opened scoring, so the caller can
    /// play one haptic.
    @discardableResult
    public func observeLocation(latitude: Double, longitude: Double, horizontalAccuracyM: Double) -> Bool {
        guard let hole = activeHoleState else { return false }
        if holeEndDetector?.hole != hole.hole {
            holeEndDetector = WatchHoleEndDetector.Green(hole: hole).map { green in
                (hole: hole.hole, detector: WatchHoleEndDetector(green: green, nextTee: nextTeePoint(after: hole)))
            }
        }
        guard var entry = holeEndDetector else { return false }
        if entry.detector.observe(
            latitude: latitude, longitude: longitude, horizontalAccuracyM: horizontalAccuracyM
        ) {
            pendingHoleEnd = hole.hole
        }
        holeEndDetector = entry
        return consumePendingHoleEnd()
    }

    /// Open 本洞成绩 for a reported hole end once nothing else is on screen. A hole that was scored
    /// meanwhile (or is no longer active) drops the trigger.
    @discardableResult
    func consumePendingHoleEnd() -> Bool {
        guard let ended = pendingHoleEnd else { return false }
        guard let hole = activeHoleState, hole.hole == ended, hole.score == 0, scoringHole == nil else {
            pendingHoleEnd = nil
            return false
        }
        guard pendingManualShot == nil, pendingAutoShotCandidate == nil,
              screen == .home || screen == .holeMap else { return false }
        pendingHoleEnd = nil
        startScoringActiveHole()
        return true
    }

    private func nextTeePoint(after hole: WatchRoundState) -> WatchHoleEndDetector.Point? {
        guard let index = allHoleStates.firstIndex(where: { $0.hole == hole.hole }),
              index + 1 < allHoleStates.count,
              let lat = allHoleStates[index + 1].teeLatitude,
              let lon = allHoleStates[index + 1].teeLongitude else { return nil }
        return WatchHoleEndDetector.Point(latitude: lat, longitude: lon)
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

    /// A detected swing (README §3): no per-shot confirmation page. It goes straight into the same
    /// undoable pending shot as a manual one — the caller plays one haptic and the bottom strip
    /// shows 第 N 杆 for `shotUndoSeconds`, tap to undo — and is recorded when that window ends.
    /// Returns true when a shot was staged, so duplicates are suppressed.
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
              pendingManualShot?.candidateFromHole == nil,
              // B6: an open 本洞成绩 for the active hole can be saved by the next tee shot.
              round?.scoreDraft == nil || scoringHole == activeHole,
              screen == .home || screen == .holeMap || screen == .scoring,
              let location = WatchShotLocationValue(
                  latitude: latitude,
                  longitude: longitude,
                  horizontalAccuracyM: horizontalAccuracyM
              ) else { return false }
        beginManualShot(
            latitude: location.latitude,
            longitude: location.longitude,
            horizontalAccuracyM: location.horizontalAccuracyM,
            capturedAt: capturedAt,
            resumeHoleMap: screen == .holeMap
        )
        return true
    }

    public func rejectAutoShotCandidate() {
        guard let candidate = pendingAutoShotCandidate else { return }
        pendingAutoShotCandidate = nil
        screen = scoringHole != nil ? .scoring : (candidate.resumeHoleMap == true ? .holeMap : .home)
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
        if pendingManualShot != nil, pendingManualShot?.candidateFromHole == nil {
            // The previous shot's undo window ends with the next shot.
            completePendingManualShot(clubName: nil)
        }
        if let nextHole = candidateNextHole(from: hole, location: location) {
            pendingManualShot = makePendingShot(
                assignedTo: nextHole,
                candidateFromHole: hole.hole,
                location: location,
                capturedAt: capturedAt,
                resumeHoleMap: resumeHoleMap ? true : nil
            )
            if scoringHole == hole.hole, advanceAfterScoring {
                // B6: 本洞成绩 was open and not confirmed; the next hole's tee shot saves it as drafted.
                persistScoreDraft()
            } else {
                startScoringActiveHole()
            }
        } else {
            // B6: no 刚才用哪支杆？ — the shot shows as 第 N 杆 with an undo and commits after
            // `shotUndoSeconds` (`completePendingManualShot`). The club is inferred later (B7).
            pendingManualShot = makePendingShot(
                assignedTo: hole,
                candidateFromHole: nil,
                location: location,
                capturedAt: capturedAt,
                resumeHoleMap: resumeHoleMap ? true : nil
            )
            if screen == .autoShotCandidate {
                screen = scoringHole != nil ? .scoring : (resumeHoleMap ? .holeMap : .home)
            }
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
        persistInteractionState()
    }

    /// How long a detected shot can be undone before it is recorded.
    public static let shotUndoSeconds: UInt64 = 4

    /// The just-detected shot awaiting its undo window ("第 2 杆"), nil otherwise.
    public var undoableShotText: String? {
        guard let pendingManualShot, pendingManualShot.candidateFromHole == nil else { return nil }
        return "第 \(pendingManualShot.shotNumber) 杆"
    }

    /// Tap the 第 N 杆 strip: the detected shot is dropped without any event.
    public func undoPendingManualShot() {
        guard let pendingManualShot, pendingManualShot.candidateFromHole == nil else { return }
        self.pendingManualShot = nil
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
            shotType: shotTypeOverride ?? Self.shotType(shotNumber: shotNumber, decisionShotType: hole.shotType),
            resumeHoleMap: resumeHoleMap
        )
    }

    /// The phase comes from the shot identity: shot 1 is the tee shot; after it, a decision's own
    /// "tee" (an older decision still in place while the phone fetches the next one) is never
    /// written, while a legitimate later phase (approach, recovery) is kept.
    static func shotType(shotNumber: Int, decisionShotType: String?) -> String {
        guard shotNumber > 1 else { return "tee" }
        guard let decisionShotType, decisionShotType != "tee" else { return "approach" }
        return decisionShotType
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

    /// This hole's Watch-recorded location events, by id, in capture order.
    func watchShotEventIds(for hole: Int) -> [String] {
        round?.pendingEvents.compactMap { event in
            event.hole == hole && event.kind == .location ? event.eventId : nil
        } ?? []
    }

    /// Every shot on this hole either device knows of: the phone's newest shot set plus the Watch's
    /// own location events (a Watch shot keeps its id on the phone, so none is counted twice).
    func knownShotEventIds(for hole: Int) -> [String] {
        let phone = round?.phoneShots?.first { $0.hole == hole }?.eventIds ?? []
        var seen = Set(phone)
        return phone + watchShotEventIds(for: hole).filter { seen.insert($0).inserted }
    }

    /// Every shot on the hole either device recorded (`knownShotEventIds`, deduplicated by event
    /// id): the shot number and type, the score recommendation and the tee origin all read this,
    /// so a shot recorded on the iPhone counts on the Watch too. The Watch's own upload queue is
    /// `pendingEvents` / `watchShotEventIds`.
    private func recordedShotCount(for hole: Int) -> Int {
        knownShotEventIds(for: hole).count
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

    // B6 one-screen 本洞成绩.

    public func setDraftScore(_ value: Int) {
        draftScore = WatchScoreRules.score(value, putts: draftPutts, penalty: draftPenalty)
        persistInteractionState()
    }

    /// Putts wrap 0–5; the total is raised when it would fall below putts + penalties + 1.
    public func setDraftPutts(_ value: Int) {
        draftPutts = WatchScoreRules.wrap(value, in: WatchScoreRules.puttRange)
        draftScore = WatchScoreRules.score(draftScore, putts: draftPutts, penalty: draftPenalty)
        persistInteractionState()
    }

    /// Penalties wrap 0–4; the total is raised when it would fall below putts + penalties + 1.
    public func setDraftPenalty(_ value: Int) {
        draftPenalty = WatchScoreRules.wrap(value, in: WatchScoreRules.penaltyRange)
        draftScore = WatchScoreRules.score(draftScore, putts: draftPutts, penalty: draftPenalty)
        persistInteractionState()
    }

    /// 开球三格; tapping the selected cell clears it.
    public func setDraftFairway(_ result: WatchFairwayResult) {
        draftFairway = draftFairway == result ? nil : result
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
            screen = scoreEntryReturnScreen
            persistInteractionState()
            return
        }
        scoringHole = nil
        screen = scoreEntryReturnScreen
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
            screen = resolved.resumeHoleMap == true ? .holeMap : .home
        } else if shouldAdvance, isAtTurn {
            // The last hole of the first half was saved: ask which nine comes next.
            openTurn()
        } else {
            screen = scoreEntryReturnScreen
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
        if isAtTurn {
            openTurn()
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

    // MARK: - the turn (B4b-2 §7)

    /// The round is one half of an 18-hole course (`G:front` / `G:back`) and its ninth hole is the
    /// scored live hole: the second nine can be chosen.
    public var isAtTurn: Bool {
        guard let round,
              let loopKey = round.loopKey,
              let loop = WatchCourseSelection.halfLoop(loopKey: loopKey),
              loop.halves.count == 1,
              round.holeStates.map(\.hole).max() == 9,
              activeHole == 9,
              (round.holeStates.first(where: { $0.hole == 9 })?.score ?? 0) > 0 else {
            return false
        }
        return true
    }

    /// The shared plan for a one-half round at its turn: loops 前九 / 后九 (ids `G:front` /
    /// `G:back`), the other half preselected.
    public static func makeTurnPlan(loopKey: String) -> NineLoopPlan? {
        guard let loop = WatchCourseSelection.halfLoop(loopKey: loopKey), loop.halves.count == 1 else {
            return nil
        }
        let loops = WatchCourseSelection.halves.map {
            NineLoop(id: "\(loop.globalId):\($0)", name: WatchCourseSelection.halfName($0))
        }
        let course = NineLoopCourse(id: String(loop.globalId), loops: loops)
        guard var plan = NineLoopPlan(course: course, first: "\(loop.globalId):\(loop.halves[0])") else {
            return nil
        }
        plan.beginFirstLoop()
        plan.reachTurn()
        return plan
    }

    public func openTurn() {
        guard isAtTurn, let loopKey = round?.loopKey else { return }
        if turnPlan == nil {
            turnPlan = Self.makeTurnPlan(loopKey: loopKey)
        }
        guard turnPlan != nil else { return }
        turnMessage = nil
        screen = .turn
    }

    public func chooseTurnSecond(_ choice: NineLoopPlan.Second) {
        guard screen == .turn, !isLoadingSecondLoop else { return }
        turnPlan?.chooseSecond(choice)
        turnMessage = nil
    }

    /// Back to the ninth hole (e.g. to fix its score); the turn is offered again on 下一洞.
    public func leaveTurn() {
        guard screen == .turn, !isLoadingSecondLoop else { return }
        turnMessage = nil
        screen = .home
    }

    /// Continue with the chosen half (round holes 10–18, same round id) or end after nine.
    public func confirmTurn() async {
        guard screen == .turn, !isLoadingSecondLoop,
              var plan = turnPlan,
              let current = round,
              let firstLoopKey = current.loopKey else { return }
        guard case .loop(let secondId) = plan.second else {
            plan.finishAfterNine()
            turnPlan = nil
            requestFinish()
            return
        }
        guard let half = secondId.split(separator: ":").last.map(String.init),
              let loader = secondLoopLoader else {
            turnMessage = "暂时无法准备第二个 9 洞，请重试"
            return
        }
        isLoadingSecondLoop = true
        turnMessage = nil
        let result = await loader(WatchSecondLoopRequest(
            roundId: current.roundId,
            firstLoopKey: firstLoopKey,
            secondHalf: half,
            teeBox: current.teeBox
        ))
        isLoadingSecondLoop = false
        guard round?.roundId == current.roundId, screen == .turn else { return }
        switch result {
        case .ready(let loopKey, let states):
            if applySecondLoop(states, loopKey: loopKey) {
                plan.beginSecondLoop()
                turnPlan = nil
                screen = .home
            } else {
                turnMessage = "第二个 9 洞数据不完整，请重试"
            }
        case .unavailable(let message):
            turnMessage = message
        }
    }

    /// Append the second nine to the same round: holes 1–9, every score and every pending event
    /// stay; holes 10–18 are the chosen half's physical holes in play order; the round's loop key
    /// becomes `G:first+G:second` so a relaunch restores the ordered table.
    @discardableResult
    public func applySecondLoop(_ states: [WatchRoundState], loopKey: String) -> Bool {
        guard var current = round,
              let firstLoopKey = current.loopKey,
              loopKey.hasPrefix(firstLoopKey + "+"),
              let loop = WatchCourseSelection.halfLoop(loopKey: loopKey),
              loop.halves.count == 2,
              Set(current.holeStates.map(\.hole)) == Set(1...9) else {
            return false
        }
        let second = states.sorted { $0.hole < $1.hole }
        let start = WatchCourseSelection.physicalStartHole(loop.halves[1])
        guard second.map(\.hole) == Array(10...18) else { return false }
        for (offset, state) in second.enumerated() {
            guard state.globalId == loop.globalId, state.sourceLocalHole == start + offset else {
                return false
            }
        }
        current.holeStates += second.map { $0.replacingRoundId(current.roundId) }
        current.loopKey = loopKey
        current.activeHole = 10
        do {
            try store.save(current)
        } catch {
            return false
        }
        round = current
        return true
    }

    // MARK: - finish

    public func requestFinish() {
        uploadError = nil
        screen = .finishing
    }

    public func requestSaveAndEndFromResume() {
        guard screen == .resume, canSaveAndEndFromResume else { return }
        uploadError = nil
        screenBeforeFinishConfirmation = .resume
        screen = .finishConfirmation
    }

    public func keepPlaying() {
        screen = .home
    }

    public func requestFinishConfirmation() {
        guard screen == .finishing else { return }
        guard let round, hasMaterializableFacts(in: round) else {
            requestAbandon()
            return
        }
        uploadError = nil
        screenBeforeFinishConfirmation = .finishing
        screen = .finishConfirmation
    }

    public func cancelFinishConfirmation() {
        guard screen == .finishConfirmation else { return }
        uploadError = nil
        screen = screenBeforeFinishConfirmation
    }

    public func requestAbandon() {
        guard round != nil, screen != .abandonConfirmation else { return }
        screenBeforeAbandon = screen
        uploadError = nil
        screen = .abandonConfirmation
    }

    public func cancelAbandon() {
        guard screen == .abandonConfirmation else { return }
        uploadError = nil
        screen = screenBeforeAbandon
    }

    /// Abandon is intentionally independent of network, phone reachability and authentication. The
    /// Watch closure is local-only; the app shell tells the phone to retract its seed but never deletes
    /// the phone's copy of the round.
    public func confirmAbandon() {
        guard screen == .abandonConfirmation, let current = round else { return }
        do {
            let closure = try store.closeActiveRound(
                roundId: current.roundId,
                disposition: .abandoned,
                closedAt: now()
            )
            publishLocalClosure(closure)
        } catch {
            uploadError = "本地记录无法删除，请重试"
        }
    }

    /// Finish remotely only after every queued event is explicitly acknowledged. Without backend
    /// config, on upload failure, or after a partial acknowledgement, the exact unresolved round is
    /// archived for retry while the player is still allowed to leave the playing UI.
    public func confirmFinish() async {
        guard screen == .finishConfirmation else { return }
        guard var current = round else { return }
        isUploading = true
        uploadError = nil
        defer { isUploading = false }
        do {
            current = try materializeScoreDraftForFinish(current)
            guard hasMaterializableFacts(in: current) else {
                screenBeforeAbandon = screenBeforeFinishConfirmation
                screen = .abandonConfirmation
                return
            }
            var readyToFinish = current
            let pending = current.pendingEvents
            if !pending.isEmpty {
                guard canUpload else {
                    try saveForLater(current)
                    return
                }
                let posted = try await upload(pending, roundId: current.roundId)
                guard let updated = try store.markPosted(eventIds: posted) else {
                    try saveForLater(current)
                    return
                }
                round = updated
                guard updated.pendingEvents.isEmpty else {
                    try saveForLater(updated)
                    return
                }
                readyToFinish = updated
            }
            guard canFinish else {
                try saveForLater(readyToFinish)
                return
            }
            try await finishRemotely(readyToFinish)
            let closure = try store.closeActiveRound(
                roundId: readyToFinish.roundId,
                disposition: .finished,
                closedAt: now()
            )
            publishLocalClosure(closure)
        } catch {
            // Save & End must remain an exit even in Airplane Mode, with an expired phone token or
            // after a response is lost. The retry archive keeps the exact unresolved IDs and finish
            // metadata; backend event/finish endpoints are idempotent.
            do {
                try saveForLater(store.load() ?? current)
            } catch {
                uploadError = "本地保存失败，本场已完整保留"
            }
        }
    }

    /// A restored draft is durable user intent but is not yet part of the upload queue. Convert its
    /// changed fields and the resulting hole snapshot in one atomic store write before finishing.
    private func materializeScoreDraftForFinish(
        _ current: WatchRoundStore.PersistedRound
    ) throws -> WatchRoundStore.PersistedRound {
        guard let draft = current.scoreDraft,
              current.pendingManualShot == nil,
              current.pendingAutoShotCandidate == nil,
              let holeIndex = current.holeStates.firstIndex(where: { $0.hole == draft.hole }) else {
            return current
        }
        let hole = current.holeStates[holeIndex]
        let selectedFairway = hole.par == 3 ? nil : draft.fairway?.rawValue
        let createdAt = now()
        var events: [WatchInputEvent] = []

        if draft.score != hole.score || selectedFairway != hole.fairwayResult?.uppercased() {
            events.append(WatchInputEvent(
                eventId: makeEventId(),
                roundId: current.roundId,
                hole: draft.hole,
                kind: .score,
                value: String(draft.score),
                createdAt: createdAt,
                fairwayResult: selectedFairway
            ))
        }
        if draft.putts != hole.putts {
            events.append(WatchInputEvent(
                eventId: makeEventId(),
                roundId: current.roundId,
                hole: draft.hole,
                kind: .putt,
                value: String(draft.putts),
                createdAt: createdAt
            ))
        }
        if draft.penalty != hole.penaltyCount {
            events.append(WatchInputEvent(
                eventId: makeEventId(),
                roundId: current.roundId,
                hole: draft.hole,
                kind: .penalty,
                value: String(draft.penalty),
                createdAt: createdAt
            ))
        }

        var updated = current
        for event in events {
            updated.holeStates[holeIndex] = updated.holeStates[holeIndex].applying(event)
            updated.pendingEvents.append(event)
        }
        updated.scoreDraft = nil
        try store.save(updated)
        round = updated
        scoringHole = nil
        return updated
    }

    private var canUpload: Bool { uploaderOverride != nil || config != nil }
    private var canFinish: Bool { finisherOverride != nil || config != nil }

    private func saveForLater(_ current: WatchRoundStore.PersistedRound) throws {
        let closure = try store.deferFinish(current, savedAt: now())
        publishLocalClosure(closure)
    }

    private func publishLocalClosure(_ closure: WatchRoundClosure) {
        let nextPhoneSeed = pendingPhoneRoundSeed
        pendingPhoneRoundSeed = nil
        pendingPhoneRoundCourseName = nil
        round = nil
        restoreInteractionState(from: nil)
        uploadError = nil
        lastRoundClosure = closure
        if let nextPhoneSeed {
            applyRoundSeed(nextPhoneSeed)
        }
    }

    /// Retry rounds whose player already left the playing UI through Save & End. This never revives
    /// the round UI; failures retain the archive for the next config/reachability opportunity.
    public func retryDeferredFinishes() async {
        guard !isRetryingDeferredFinishes else { return }
        isRetryingDeferredFinishes = true
        defer { isRetryingDeferredFinishes = false }
        for deferred in store.loadDeferredFinishes() {
            do {
                var ready = deferred.round
                if !ready.pendingEvents.isEmpty {
                    guard canUpload else { continue }
                    let posted = try await upload(ready.pendingEvents, roundId: ready.roundId)
                    guard let updated = try store.markDeferredEventsPosted(
                        roundId: ready.roundId,
                        eventIds: posted
                    ) else {
                        continue
                    }
                    ready = updated.round
                    guard ready.pendingEvents.isEmpty else { continue }
                }
                // Older builds allowed a location-only Save & End. Preserve that real GPS fact by
                // waiting for an explicit upload acknowledgement, then retire the invalid archive
                // without asking the backend to fabricate a scored round. A truly empty archive can
                // still be removed immediately.
                guard hasMaterializableFacts(in: ready) else {
                    try store.removeDeferredFinish(roundId: ready.roundId)
                    continue
                }
                guard canFinish else { continue }
                try await finishRemotely(ready)
                let closure = try store.closeActiveRound(
                    roundId: ready.roundId,
                    disposition: .finished,
                    closedAt: now()
                )
                try store.removeDeferredFinish(roundId: ready.roundId)
                lastRoundClosure = closure
            } catch {
                continue
            }
        }
    }

    /// A phone-side Finish/Discard is authoritative only for the matching round. It records the same
    /// tombstone but deliberately does not publish `lastRoundClosure`, avoiding a connectivity echo.
    public func applyPhoneRoundClosure(_ closure: WatchRoundClosure) {
        guard closure.disposition != .savedLocally else { return }
        do {
            let visibleRound = round?.roundId == closure.roundId ? round : nil
            let closesVisibleRound = visibleRound != nil
            if closure.disposition == .finished,
               let visibleRound,
               !visibleRound.pendingEvents.isEmpty {
                // Phone Finish cannot prove that wrist-authored facts reached the backend: the
                // standalone Watch queue is uploaded only by this model. Leave the playing UI, but
                // archive those exact event IDs for the existing idempotent deferred retry path.
                _ = try store.deferFinish(visibleRound, savedAt: closure.closedAt)
            } else {
                _ = try store.closeActiveRound(
                    roundId: closure.roundId,
                    disposition: closure.disposition,
                    closedAt: closure.closedAt
                )
            }
            if closure.disposition == .abandoned {
                try? store.removeDeferredFinish(roundId: closure.roundId)
            }
            if closesVisibleRound {
                round = nil
                restoreInteractionState(from: nil)
                uploadError = nil
                if let nextPhoneSeed = pendingPhoneRoundSeed {
                    pendingPhoneRoundSeed = nil
                    pendingPhoneRoundCourseName = nil
                    applyRoundSeed(nextPhoneSeed)
                }
            }
        } catch {
            return
        }
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
