import CoreLocation
import Foundation
import SwiftUI

/// C99 球局主页：单一「打一场球」入口、快捷球场、天气一行、上一场与最近走势。
/// 进行中的球局只保留「继续」主卡；结束和球局调整在洞屏内完成。
/// Hub navigation routes driven by a path, so a selected course can open its prep hole directly
/// and the first stroke can promote it into the live round.
public enum HubRoute: Hashable {
    case start
    /// 开始一场 with the home card's course (and its last tee) preselected.
    case startCourse(globalId: Int, teeBox: String?)
    case hole(Int)
    case history
    case roundReview(roundRef: String, courseName: String?, globalId: Int?, backGlobalId: Int?, nine: String?, teeBox: String?)
}

enum LiveHoleRouteReconciliation {
    static func target(
        routedHole: Int,
        packageHoles: [Int],
        restoredActiveHole: Int?
    ) -> Int? {
        guard !packageHoles.contains(routedHole) else { return nil }
        if let restoredActiveHole, packageHoles.contains(restoredActiveHole) {
            return restoredActiveHole
        }
        return packageHoles.first
    }
}

enum LiveHoleRoutePath {
    static func afterAdvance(current: [HubRoute], nextHole: Int, isPrepMode: Bool) -> [HubRoute] {
        guard isPrepMode, let base = current.first, isPrepBase(base) else { return [.hole(nextHole)] }
        return [base, .hole(nextHole)]
    }

    static func forPendingHole(current: [HubRoute], hole: Int, isPrepMode: Bool) -> [HubRoute] {
        if isPrepMode, let base = current.first, isPrepBase(base) { return [base, .hole(hole)] }
        return [.hole(hole)]
    }

    static func afterPrepPackageRefresh(current: [HubRoute], pendingHole: Int?) -> [HubRoute] {
        guard let pendingHole else { return current }
        return forPendingHole(current: current, hole: pendingHole, isPrepMode: true)
    }

    static func isPrepBase(_ route: HubRoute) -> Bool {
        if case .startCourse = route { return true }
        return false
    }
}

/// Guards the one-hole-at-a-time transition owned by the live pager.  Keeping this rule pure
/// makes a second fast swipe harmless: it cannot enqueue a transition against a page that has
/// already started moving, and a stale page cannot advance the current page.
struct LiveHoleNavigationLock: Equatable {
    private(set) var currentHole: Int
    private(set) var isTransitioning = false

    init(currentHole: Int) {
        self.currentHole = currentHole
    }

    static func accepts(from: Int, current: Int, isTransitioning: Bool) -> Bool {
        !isTransitioning && from == current
    }

    mutating func begin(from: Int, to: Int) -> Bool {
        guard Self.accepts(from: from, current: currentHole, isTransitioning: isTransitioning),
              to != currentHole else { return false }
        currentHole = to
        isTransitioning = true
        return true
    }

    mutating func finish(at hole: Int) {
        guard hole == currentHole else { return }
        isTransitioning = false
    }
}

/// A selected hole can temporarily own a direct-manipulation map gesture.  The preference is
/// reduced by the pager so a target drag or a zoomed pan cannot be interpreted as a page swipe.
struct LiveHolePagerGestureStateKey: PreferenceKey {
    static let defaultValue = false

    static func reduce(value: inout Bool, nextValue: () -> Bool) {
        value = value || nextValue()
    }
}

enum LiveHolePagerInitialSelection {
    static func resolve(
        current: Int?,
        ordered: [Int],
        preferredHole: Int?,
        fallbackHole: Int?
    ) -> Int? {
        guard !ordered.isEmpty else { return nil }
        if let current, ordered.contains(current) { return current }
        if let preferredHole, ordered.contains(preferredHole) { return preferredHole }
        if let fallbackHole, ordered.contains(fallbackHole) { return fallbackHole }
        return ordered.first
    }
}

/// Model-layer data that survives a page being unloaded by SwiftUI.  The network tasks remain
/// owned by the round model; this cache only retains their published result and request identity.
public final class LiveHoleSessionCache {
    struct Key: Hashable {
        let roundId: String
        let hole: Int
        let sourceGlobalId: Int
        let sourceLocalHole: Int
        let teeBox: String
    }

    struct Entry {
        var geometryRevision: String?
        var holePrep: CoursePrepHole?
        var garminRaster: GarminRasterResponse?
        var garminRevision: String?
        var caddieDecision: CaddieDecisionResponse?
        var caddieDecisionInputSignature: String?
        var caddieDecisionIsOnline = false
        var caddieRoutes: [CaddiePlanSequence] = []
        var localTopoURL: URL?
        var prepRequestStarted = false
        var prepRequestCompleted = false
        var preciseProbeStarted = false
        var garminRequestStarted = false
    }

    private var entries: [Key: Entry] = [:]

    public init() {}

    /// The one revision authority used by the cache key's entry validation and every producer
    /// that writes a hole result. A missing revision means "unknown" and must not invalidate a
    /// previously retained entry.
    static func cacheRevision(hole: Hole, prep: CoursePrepHole?) -> String? {
        if hole.topoAvailable == true,
           let topoRevision = normalizedRevision(hole.topoRevision) {
            return topoRevision
        }
        if prep?.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame,
           let revision = normalizedRevision(prep?.geometryRevision) {
            return revision
        }
        return normalizedRevision(hole.geometryRevision) ?? normalizedRevision(prep?.geometryRevision)
    }

    func entry(
        roundId: String,
        hole: Int,
        sourceGlobalId: Int = 0,
        sourceLocalHole: Int = 0,
        teeBox: String = "",
        geometryRevision: String? = nil
    ) -> Entry {
        let value = entries[key(
            roundId: roundId,
            hole: hole,
            sourceGlobalId: sourceGlobalId,
            sourceLocalHole: sourceLocalHole,
            teeBox: teeBox
        )] ?? Entry()
        return value.rebased(for: geometryRevision)
    }

    func update(
        roundId: String,
        hole: Int,
        sourceGlobalId: Int = 0,
        sourceLocalHole: Int = 0,
        teeBox: String = "",
        geometryRevision: String? = nil,
        _ update: (inout Entry) -> Void
    ) {
        let key = key(
            roundId: roundId,
            hole: hole,
            sourceGlobalId: sourceGlobalId,
            sourceLocalHole: sourceLocalHole,
            teeBox: teeBox
        )
        var value = entries[key] ?? Entry()
        value = value.rebased(for: geometryRevision)
        if let geometryRevision = Self.normalizedRevision(geometryRevision) {
            value.geometryRevision = geometryRevision
        }
        update(&value)
        entries[key] = value
    }

    /// Replace the factual prep and advance the entry revision atomically. The revision must be
    /// derived from the prep being written, never from the entry's previous prep.
    func updatePrep(
        roundId: String,
        hole: Hole,
        teeBox: String,
        prep: CoursePrepHole?
    ) {
        update(
            roundId: roundId,
            hole: hole.number,
            sourceGlobalId: hole.sourceGlobalId,
            sourceLocalHole: hole.sourceLocalHole,
            teeBox: teeBox,
            geometryRevision: Self.cacheRevision(hole: hole, prep: prep)
        ) { entry in
            entry.holePrep = prep
        }
    }

    func reset(roundId: String? = nil) {
        guard let roundId else {
            entries.removeAll()
            return
        }
        entries = entries.filter { $0.key.roundId != roundId }
    }

    func trim(roundId: String, keeping keys: Set<Key>) {
        for key in entries.keys where key.roundId == roundId && !keys.contains(key) {
            guard var entry = entries[key] else { continue }
            entry.dropHeavyFields()
            entries[key] = entry
        }
    }

    func trim(roundId: String, keepingHoles holes: Set<Int>) {
        for key in entries.keys where key.roundId == roundId && !holes.contains(key.hole) {
            guard var entry = entries[key] else { continue }
            entry.dropHeavyFields()
            entries[key] = entry
        }
    }

    private func key(
        roundId: String,
        hole: Int,
        sourceGlobalId: Int,
        sourceLocalHole: Int,
        teeBox: String
    ) -> Key {
        Key(
            roundId: roundId,
            hole: hole,
            sourceGlobalId: sourceGlobalId,
            sourceLocalHole: sourceLocalHole,
            teeBox: teeBox
        )
    }

    fileprivate static func normalizedRevision(_ revision: String?) -> String? {
        guard let revision = revision?.trimmingCharacters(in: .whitespacesAndNewlines),
              !revision.isEmpty else { return nil }
        return revision
    }
}

fileprivate extension LiveHoleSessionCache.Entry {
    func rebased(for revision: String?) -> Self {
        let requested = LiveHoleSessionCache.normalizedRevision(revision)
        let cached = LiveHoleSessionCache.normalizedRevision(geometryRevision)
        // A producer that does not know the current release must not destroy a useful entry.
        guard requested != nil else { return self }
        guard requested != cached else { return self }
        var copy = self
        copy.holePrep = nil
        copy.localTopoURL = nil
        copy.prepRequestStarted = false
        copy.prepRequestCompleted = false
        copy.preciseProbeStarted = false
        copy.caddieRoutes = []
        if LiveHoleSessionCache.normalizedRevision(copy.garminRevision) != requested {
            copy.garminRaster = nil
            copy.garminRevision = nil
        }
        return copy
    }

    mutating func dropHeavyFields() {
        if let prep = holePrep, let map = prep.map, map.image != nil {
            holePrep = CoursePrepHole(
                hole: prep.hole,
                par: prep.par,
                parSource: prep.parSource,
                blueYards: prep.blueYards,
                teeYards: prep.teeYards,
                routeLenM: prep.routeLenM,
                route: prep.route,
                geometryCoverage: prep.geometryCoverage,
                geometryRevision: prep.geometryRevision,
                sourceRefs: prep.sourceRefs,
                missingData: prep.missingData,
                candidateRoutes: prep.candidateRoutes,
                carryTargets: prep.carryTargets,
                steps: prep.steps,
                cautions: prep.cautions,
                landingM: prep.landingM,
                teeClub: prep.teeClub,
                hazards: prep.hazards,
                map: CoursePrepMap(image: nil, overlay: map.overlay),
                greenDistances: prep.greenDistances,
                playsLike: prep.playsLike,
                holeImageProjection: prep.holeImageProjection,
                greenOutline: prep.greenOutline,
                fairwayOutline: prep.fairwayOutline
            )
            // A request already using this entry must finish; otherwise its completion can race the
            // trim and publish a second request. Only a real bitmap eviction reopens the gate.
            if !prepRequestStarted {
                prepRequestCompleted = false
                preciseProbeStarted = false
            }
        }
        localTopoURL = nil
    }
}

enum LiveHolePagerSelectionLifecycle {
    static func shouldReset(
        previousPath: [HubRoute],
        currentPath: [HubRoute]
    ) -> Bool {
        let leftHole = previousPath.contains { if case .hole = $0 { return true }; return false }
        let stillHasHole = currentPath.contains { if case .hole = $0 { return true }; return false }
        return leftHole && !stillHasHole
    }

    static func selectionAfterSessionChange(
        path: [HubRoute],
        ordered: [Int],
        activeHole: Int?,
        pendingLiveHole: Int?
    ) -> Int? {
        guard let routedHole = path.reversed().compactMap({ route -> Int? in
            if case let .hole(number) = route { return number }
            return nil
        }).first else { return nil }
        return LiveHolePagerInitialSelection.resolve(
            current: nil,
            ordered: ordered,
            preferredHole: activeHole ?? pendingLiveHole ?? routedHole,
            fallbackHole: routedHole
        )
    }

    /// A route change is a handoff between destinations, even though both routes contain a hole.
    /// The new route must win over the pager's previous selection (for example, `.hole(9)` to
    /// `.hole(10)` when a second nine is appended).
    static func targetForRouteChange(
        previousPath: [HubRoute],
        currentPath: [HubRoute],
        ordered: [Int]
    ) -> Int? {
        let previousHole = previousPath.reversed().compactMap { route -> Int? in
            if case let .hole(number) = route { return number }
            return nil
        }.first
        guard let currentHole = currentPath.reversed().compactMap({ route -> Int? in
            if case let .hole(number) = route { return number }
            return nil
        }).first,
        currentHole != previousHole,
        ordered.contains(currentHole) else { return nil }
        return currentHole
    }

    /// A rebuilt pager may still report the old visible page while the round cursor already moved
    /// to a new routed hole. Retain a live selection only when it agrees with that cursor; prep
    /// browsing has no persisted cursor and can retain its own page.
    static func retainedSelectionAfterRefresh(
        current: Int?,
        activeHole: Int?,
        isPrepMode: Bool
    ) -> Int? {
        guard isPrepMode else {
            guard current == activeHole else { return nil }
            return current
        }
        return current
    }
}

enum LiveHoleSessionCachePolicy {
    static func shouldFetchPrep(cached: CoursePrepHole?, requestStarted: Bool) -> Bool {
        cached == nil && !requestStarted
    }

    static func shouldFetchPrep(
        cached: CoursePrepHole?, requestStarted: Bool, requestCompleted: Bool,
        forMapping: Bool = false
    ) -> Bool {
        if forMapping { return !requestStarted }
        return !requestStarted && !requestCompleted
    }

    static func shouldFetchGarmin(cached: GarminRasterResponse?, requestStarted: Bool, revision: String?, cachedRevision: String?) -> Bool {
        guard !requestStarted else { return false }
        guard let cached else { return true }
        return cachedRevision != revision || !cached.hasDisplayableImage
    }

    static func shouldFetchDecision(inputSignature: String, cachedSignature: String?, hasCachedDecision: Bool) -> Bool {
        !hasCachedDecision || cachedSignature != inputSignature
    }
}

public struct RoundHomeView: View {
    private static let historyISOFormatter = ISO8601DateFormatter()
    private static let historyDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
    /// The active round's package, or the home package (most-played course). Nil until the first
    /// one is cached or fetched (first launch, a slow backend): the home still renders and offers
    /// 开始一场, instead of a separate legacy list.
    public let package: LiveRoundPackage?
    public let pendingEventCount: Int
    public let syncStatus: String
    public let localEventUploadStatus: String
    public let garminConnectionState: GarminConnectionState
    /// Deprecated source-compatible alias. The typed connection state remains the only mutable
    /// authority; this read-only projection keeps older contract callers from breaking.
    @available(*, deprecated, message: "Use garminConnectionState instead")
    public var garminSyncStatus: String { garminConnectionState.statusText }
    public let lastGarminSyncAt: Date?
    public let isGarminSyncing: Bool
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let adminTokenConfigured: Bool
    public let offlineStore: OfflineStore?
    public let sessionStore: GarminSessionStore?
    public let watchBridge: WatchEventBridge?
    public let liveRoundState: LiveRoundStateSnapshot?
    public let pendingWatchRoundStart: WatchRoundStartPayload?
    public let courseOptions: [MobileCourseOption]
    public let downloadedCourseOptions: [MobileCourseOption]
    /// Explicitly started course fallback; this is not nearby/GPS evidence.
    public let recentCourseOption: MobileCourseOption?
    public let downloadedCourseKeys: Set<String>
    public let prepCourseDownloads: [PrepCourseDownloadRecord]
    public let prepCourseDownloadPresentation: PrepCourseDownloadPresentationState?
    public let liveCourseDownloadProgress: LiveCourseDownloadProgress?
    public let offlineStorageUsage: OfflineStorageUsage?
    public let isPreparingRound: Bool
    public let isFinishingRound: Bool
    public let finishErrorMessage: String?
    public let onEvent: (LiveRoundEvent) -> Void
    public let onPrepareRound: (String) -> Void
    /// Start a round: (roundId, teeBox, ordered loops) — B4b-2 `loops=`.
    public let onPrepareCourseRound: (String, String, [RoundLoopEntry]) -> Void
    /// Set, change or drop (nil) the second loop before it is played: (entry, roundId).
    public let onSetSecondLoop: (RoundLoopEntry?, String) -> Void
    /// B4 turn: add the chosen second loop and open its first hole (the model navigates).
    public let onContinueIntoSecondLoop: (RoundLoopEntry, String) -> Void
    public let onFinishRound: () async -> Bool
    public let onDiscardRound: () -> Void
    public let onSetActiveHole: (Int) -> Void
    public let onRetainReadyHolePrep: (String, Int, CoursePrepHole) -> Void
    public let onSync: () -> Void
    public let onCancelGarminSync: () async -> Void
    public let onGarminSessionImported: () async -> Bool
    /// Typed variant used by the Garmin account screen. The Bool callback remains as a compatibility
    /// bridge for older snapshot/test callers.
    public let onGarminSessionImportedOutcome: (() async -> GarminSyncOutcome)?
    public let onRefreshGarminSyncStatus: () async -> Void
    public let onRefreshOfflineStorageUsage: () async -> Void
    public let onSpeculativePrefetchSettingChanged: () -> Void
    public let onGarminSessionForgot: () -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void
    /// 拉取所选球场的可选发球台(供「开始一场」的选台器);仅转发给 StartRoundView。
    public let onLoadCourseTees: (Int) async -> [CourseTee]
    /// Garmin 全库名称搜索；StartRoundView 只保留本次结果，选中后走现有单球场准备链。
    public let onSearchCourses: (String, String?, Double?, Double?) async throws -> [MobileCourseSearchMatch]
    /// The course the player is about to play (在这个球场, or settled on 开始一场): its loops and
    /// Tee, for the app's whole-course prefetch.
    public let onCourseIntent: ([MobileCourseOption], String) -> Void
    /// Garmin 全库坐标发现；StartRoundView 只保留本次结果。
    public let onNearbyCourses: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]
    public let onDownloadPrepCourse: (MobileCourseOption) -> Void
    public let onRetryPrepCourseDownload: (String) -> Void
    /// Re-check a locally complete prep package against the current Garmin release before opening it.
    /// A transport failure is handled by the model as a deferred check, so offline use remains valid.
    public let onValidateReadyPrepCourse: (PrepCourseDownloadRecord) async -> Bool
    /// Set to a hole number right after a fresh round is prepared → auto-navigate into that hole.
    public let pendingLiveHole: Int?
    public let onConsumePendingLiveHole: () -> Void
    public let onLiveHoleInitialLoadDidFinish: () -> Void
    public let onLiveAppearanceChanged: (Bool) -> Void
    /// 备战 on the hole screen: the course package shown while no round exists (memory only).
    public let prepPackage: LiveRoundPackage?
    public let prepTeeOptions: [String]
    public let isOpeningPrepCourse: Bool
    /// Open a 备战 course on the hole screen; false when a round is in progress.
    public let onOpenPrepCourse: (MobileCourseOption) -> Bool
    public let onPrepHoleChanged: (Int) -> Void
    public let onClosePrep: () -> Void
    public let onChangePrepTee: (String, Int?) -> Void
    /// The first stroke inside a hole's area starts the round there; false when it could not.
    public let onStartRoundFromFirstStroke: (Int) -> Bool
    public let onUndoRoundStart: () -> Void

    @State private var showSettings = false
    @State private var path: [HubRoute] = []
    /// The live route is one destination containing a paging surface. Keeping the selection here
    /// avoids rebuilding a CurrentHoleView (and its location/task state) for every swipe.
    @State private var holePager = LiveHolePagerState()
    // Only the native display binding gets the two-phase correction; the authoritative selection
    // and every page's identity remain unchanged (including the selected page's sheet/map state).
    @State private var pagerNativeSelectionOverride: Int?
    @State private var pagerCorrectionTarget: Int?
    @State private var pagerCorrectionID = UUID()
    @State private var pagerCorrectionApplying = false
    @State private var pagerCorrectionTask: Task<Void, Never>?
    @State private var pagerPresentationEndTask: Task<Void, Never>?
    @State private var pagerPresentationRequested = false
    @GestureState private var pagerTouchIsActive = false
    @State private var pagerGestureStarted = false
    private var holePagerSelection: Int? { holePager.selection }
    @State private var holePagerNavigationLock: LiveHoleNavigationLock?
    @State private var holePagerScrollDisabled = false
    @State private var liveHoleSessions = LiveHoleSessionCache()
    /// The last GPS-resolved prep hole lives above `CurrentHoleView`, so recreating a destination
    /// after a manual hole preview does not mistake the same fix for a new location.
    @State private var prepHoleFollowing = PrepHoleFollowingState()
    /// The last round's 18-hole symbol strip, from the cached round archive (empty when unknown).
    @State private var lastRoundStrip: [HistoryScoreCell] = []
    /// README §8 "在球场附近": the home's own fix (never a permission prompt here — the start
    /// screen asks) and the provider-nearby courses around it, from the same nearby authority as
    /// 开始一场.
    @StateObject private var heroLocation = LocationProvider()
    @State private var heroNearbyOptions: [MobileCourseOption] = []
    /// Archived rounds, newest first: each venue's last first loop and tee.
    @State private var heroHistory: [HistoryRoundCard] = []
    /// Weather is a single compact line below the greeting; nil means the line is omitted.
    @State private var homeWeather: HomeWeather?
    @State private var homeCity: String?

    /// The clock the greeting reads; design snapshots pin it so the title never depends on when CI ran.
    @Environment(\.homeGreetingDate) private var greetingDate

    public init(
        package: LiveRoundPackage?,
        pendingEventCount: Int = 0,
        syncStatus: String = "Offline ready",
        localEventUploadStatus: String = "自动上传已开启",
        garminConnectionState: GarminConnectionState = .disconnected,
        garminSyncStatus: String? = nil,
        lastGarminSyncAt: Date? = nil,
        isGarminSyncing: Bool = false,
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        adminTokenConfigured: Bool = false,
        offlineStore: OfflineStore? = nil,
        sessionStore: GarminSessionStore? = GarminSessionStore(),
        watchBridge: WatchEventBridge? = nil,
        liveRoundState: LiveRoundStateSnapshot? = nil,
        pendingWatchRoundStart: WatchRoundStartPayload? = nil,
        courseOptions: [MobileCourseOption] = [],
        downloadedCourseOptions: [MobileCourseOption] = [],
        recentCourseOption: MobileCourseOption? = nil,
        downloadedCourseKeys: Set<String> = [],
        prepCourseDownloads: [PrepCourseDownloadRecord] = [],
        prepCourseDownloadPresentation: PrepCourseDownloadPresentationState? = nil,
        liveCourseDownloadProgress: LiveCourseDownloadProgress? = nil,
        offlineStorageUsage: OfflineStorageUsage? = nil,
        isPreparingRound: Bool = false,
        isFinishingRound: Bool = false,
        finishErrorMessage: String? = nil,
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in },
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (String, String, [RoundLoopEntry]) -> Void = { _, _, _ in },
        onSetSecondLoop: @escaping (RoundLoopEntry?, String) -> Void = { _, _ in },
        onContinueIntoSecondLoop: @escaping (RoundLoopEntry, String) -> Void = { _, _ in },
        onFinishRound: @escaping () async -> Bool = { false },
        onDiscardRound: @escaping () -> Void = {},
        onSetActiveHole: @escaping (Int) -> Void = { _ in },
        onRetainReadyHolePrep: @escaping (String, Int, CoursePrepHole) -> Void = { _, _, _ in },
        onSync: @escaping () -> Void = {},
        onCancelGarminSync: @escaping () async -> Void = {},
        onGarminSessionImported: @escaping () async -> Bool = { false },
        onGarminSessionImportedOutcome: (() async -> GarminSyncOutcome)? = nil,
        onRefreshGarminSyncStatus: @escaping () async -> Void = {},
        onRefreshOfflineStorageUsage: @escaping () async -> Void = {},
        onSpeculativePrefetchSettingChanged: @escaping () -> Void = {},
        onGarminSessionForgot: @escaping () -> Void = {},
        onSaveBackendConfiguration: @escaping (String, String?) -> Void = { _, _ in },
        onClearBackendConfiguration: @escaping () -> Void = {},
        onLoadCourseTees: @escaping (Int) async -> [CourseTee] = { _ in [] },
        onSearchCourses: @escaping (String, String?, Double?, Double?) async throws -> [MobileCourseSearchMatch] = { _, _, _, _ in [] },
        onNearbyCourses: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch] = { _, _, _ in [] },
        onCourseIntent: @escaping ([MobileCourseOption], String) -> Void = { _, _ in },
        onDownloadPrepCourse: @escaping (MobileCourseOption) -> Void = { _ in },
        onRetryPrepCourseDownload: @escaping (String) -> Void = { _ in },
        onValidateReadyPrepCourse: @escaping (PrepCourseDownloadRecord) async -> Bool = { _ in true },
        pendingLiveHole: Int? = nil,
        onConsumePendingLiveHole: @escaping () -> Void = {},
        onLiveHoleInitialLoadDidFinish: @escaping () -> Void = {},
        onLiveAppearanceChanged: @escaping (Bool) -> Void = { _ in },
        prepPackage: LiveRoundPackage? = nil,
        prepTeeOptions: [String] = [],
        isOpeningPrepCourse: Bool = false,
        onOpenPrepCourse: @escaping (MobileCourseOption) -> Bool = { _ in false },
        onPrepHoleChanged: @escaping (Int) -> Void = { _ in },
        onClosePrep: @escaping () -> Void = {},
        onChangePrepTee: @escaping (String, Int?) -> Void = { _, _ in },
        onStartRoundFromFirstStroke: @escaping (Int) -> Bool = { _ in false },
        onUndoRoundStart: @escaping () -> Void = {},
        heroLocationProvider: LocationProvider? = nil,
        initialHeroNearbyOptions: [MobileCourseOption] = []
    ) {
        // The home's location authority and its first nearby rows; a fixture passes an authorised
        // fixed fix and the rows `HubNearby.options` built from its nearby matches, so the first
        // render already resolves through the production venue path (the task refresh then
        // re-queries onNearbyCourses as in the app).
        _heroLocation = StateObject(wrappedValue: heroLocationProvider ?? LocationProvider())
        _heroNearbyOptions = State(initialValue: initialHeroNearbyOptions)
        self.package = package
        self.pendingEventCount = pendingEventCount
        self.syncStatus = syncStatus
        self.localEventUploadStatus = localEventUploadStatus
        self.garminConnectionState = garminConnectionState
        // Kept only so older source callers continue to compile. Do not revive string-driven state.
        _ = garminSyncStatus
        self.lastGarminSyncAt = lastGarminSyncAt
        self.isGarminSyncing = isGarminSyncing
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.adminTokenConfigured = adminTokenConfigured
        self.offlineStore = offlineStore
        self.sessionStore = sessionStore
        self.watchBridge = watchBridge
        self.liveRoundState = liveRoundState
        self.pendingWatchRoundStart = pendingWatchRoundStart
        self.courseOptions = courseOptions
        self.downloadedCourseOptions = downloadedCourseOptions
        self.recentCourseOption = recentCourseOption
        self.downloadedCourseKeys = downloadedCourseKeys
        self.prepCourseDownloads = prepCourseDownloads
        self.prepCourseDownloadPresentation = prepCourseDownloadPresentation
        self.liveCourseDownloadProgress = liveCourseDownloadProgress
        self.offlineStorageUsage = offlineStorageUsage
        self.isPreparingRound = isPreparingRound
        self.isFinishingRound = isFinishingRound
        self.finishErrorMessage = finishErrorMessage
        self.onEvent = onEvent
        self.onPrepareRound = onPrepareRound
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onSetSecondLoop = onSetSecondLoop
        self.onContinueIntoSecondLoop = onContinueIntoSecondLoop
        self.onFinishRound = onFinishRound
        self.onDiscardRound = onDiscardRound
        self.onSetActiveHole = onSetActiveHole
        self.onRetainReadyHolePrep = onRetainReadyHolePrep
        self.onSync = onSync
        self.onCancelGarminSync = onCancelGarminSync
        self.onGarminSessionImported = onGarminSessionImported
        self.onGarminSessionImportedOutcome = onGarminSessionImportedOutcome
        self.onRefreshGarminSyncStatus = onRefreshGarminSyncStatus
        self.onRefreshOfflineStorageUsage = onRefreshOfflineStorageUsage
        self.onSpeculativePrefetchSettingChanged = onSpeculativePrefetchSettingChanged
        self.onGarminSessionForgot = onGarminSessionForgot
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
        self.onLoadCourseTees = onLoadCourseTees
        self.onSearchCourses = onSearchCourses
        self.onCourseIntent = onCourseIntent
        self.onNearbyCourses = onNearbyCourses
        self.onDownloadPrepCourse = onDownloadPrepCourse
        self.onRetryPrepCourseDownload = onRetryPrepCourseDownload
        self.onValidateReadyPrepCourse = onValidateReadyPrepCourse
        self.pendingLiveHole = pendingLiveHole
        self.onConsumePendingLiveHole = onConsumePendingLiveHole
        self.onLiveHoleInitialLoadDidFinish = onLiveHoleInitialLoadDidFinish
        self.onLiveAppearanceChanged = onLiveAppearanceChanged
        self.prepPackage = prepPackage
        self.prepTeeOptions = prepTeeOptions
        self.isOpeningPrepCourse = isOpeningPrepCourse
        self.onOpenPrepCourse = onOpenPrepCourse
        self.onPrepHoleChanged = onPrepHoleChanged
        self.onClosePrep = onClosePrep
        self.onChangePrepTee = onChangePrepTee
        self.onStartRoundFromFirstStroke = onStartRoundFromFirstStroke
        self.onUndoRoundStart = onUndoRoundStart
        #if DEBUG
        let environment = ProcessInfo.processInfo.environment
        if environment["UITEST_MODE"] == "1",
           let roundRef = environment["UITEST_REVIEW_ROUND_REF"],
           !roundRef.isEmpty {
            self._path = State(initialValue: [
                .history,
                .roundReview(
                    roundRef: roundRef,
                    courseName: environment["UITEST_REVIEW_COURSE_NAME"],
                    globalId: nil,
                    backGlobalId: nil,
                    nine: nil,
                    teeBox: nil
                ),
            ])
        }
        #endif
    }

    /// Nameless, time-of-day greeting (早上好 / 中午好 / 下午好 / 晚上好) — the home's large title.
    private var greeting: String {
        Self.greeting(at: greetingDate ?? Date())
    }

    static func greeting(at date: Date, calendar: Calendar = .current) -> String {
        switch calendar.component(.hour, from: date) {
        case 5..<11: return "早上好"
        case 11..<13: return "中午好"
        case 13..<18: return "下午好"
        default: return "晚上好"
        }
    }

    public var body: some View {
        #if DEBUG
        let _ = UITestPagerTrace.shared.metric(.roundHomeBody)
        #endif
        NavigationStack(path: $path) {
            ScrollView {
                VStack(spacing: 10) {
                    weatherLine
                    playSection
                    quickCoursesSection
                    lastRoundSection
                    recentTrendSection
                }
                .padding(.horizontal, 16)
                .padding(.top, 4)
                .padding(.bottom, 22)
            }
            .background(HubBentoStyle.ground)
            // A nameless, time-of-day greeting stands in for the app-name title (no personal name).
            .navigationTitle(greeting)
            .navigationBarTitleDisplayMode(.large)
            .navigationDestination(for: HubRoute.self) { route in
                switch route {
                case .start:
                    startRoundView(globalId: nil, teeBox: nil)
                case .startCourse(let globalId, let teeBox):
                    startRoundView(globalId: globalId, teeBox: teeBox)
                case .hole(let number):
                    holePagerView(number)
                case .history:
                    if let package {
                        RecentRoundReviewView(
                            package: package,
                            apiBaseURL: apiBaseURL,
                            adminToken: adminToken
                        )
                    }
                case .roundReview(let roundRef, let courseName, let globalId, let backGlobalId, let nine, let teeBox):
                    RoundReviewView(
                        roundRef: roundRef,
                        fallbackCourseName: courseName,
                        apiBaseURL: apiBaseURL,
                        adminToken: adminToken,
                        globalId: globalId,
                        backGlobalId: backGlobalId,
                        nine: nine,
                        teeBox: teeBox
                    )
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                settingsSheet
            }
            // Prefetch the real Garmin bag so the live picker uses it even if 球杆设置 is never opened.
            .task {
                await refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken)
            }
            .task(id: package?.recentHistory.rounds.first?.roundId) {
                loadLastRoundStrip()
            }
            .onAppear(perform: startHeroLocation)
            .task(id: heroNearbyKey) {
                await refreshHeroNearby()
            }
            .task(id: heroCourseIntentKey) {
                announceHeroCourseIntent()
            }
            .onReceive(NotificationCenter.default.publisher(for: .resultsCacheDidUpdate)) { _ in
                heroHistory = (try? offlineStore?.loadHistoryRoundsArchive())?.groups.flatMap(\.rounds) ?? heroHistory
                loadLastRoundStrip()
            }
            .task(id: weatherKey) {
                if weatherKey == "none" {
                    homeWeather = nil
                    homeCity = nil
                }
                await refreshHomeWeather()
            }
        }
        // The NavigationStack owns the system status bar, so the immersive hole destination cannot
        // hide it reliably from inside CurrentHoleView. Keep normal chrome on every non-live route.
        .statusBarHidden(Self.isLiveHoleRoute(path.last))
        .onChange(of: pendingLiveHole) { _, hole in
            #if DEBUG
            UITestEventLatencyTrace.record("round-home.pending-change hole=\(hole ?? -1)")
            #endif
            enterPendingLiveHole(hole)
        }
        .onChange(of: liveRoundState?.roundId) { previousRoundId, currentRoundId in
            if previousRoundId != currentRoundId {
                liveHoleSessions.reset()
            }

            // 撤销开打 ends the round but keeps the hole screen, back in 备战.
            if previousRoundId != nil, currentRoundId == nil, prepPackage == nil {
                path = []
            }
            if previousRoundId != currentRoundId {
                reconcilePagerSelectionAfterSessionChange()
            }
        }
        .onChange(of: prepPackage?.roundId) { previousRoundID, roundId in
            if previousRoundID != roundId {
                prepHoleFollowing.reset()
                liveHoleSessions.reset()
            }
            if liveRoundState == nil, roundId != nil {
                path = LiveHoleRoutePath.afterPrepPackageRefresh(
                    current: path,
                    pendingHole: pendingLiveHole ?? prepPackage?.holes.first?.number
                )
            }
            if previousRoundID != roundId {
                reconcilePagerSelectionAfterSessionChange()
            }
        }
        .onChange(of: holeScreenPackage?.holeSetIdentity) { _, _ in
            refreshPagerPageSet()
            reconcileLiveHoleRouteWithPackage()
        }
        .onChange(of: liveRoundState?.activeHole) { _, activeHole in
            if !isPrepHoleScreen, let activeHole, holePager.activeHole != activeHole {
                sendPager(.programmaticHole(activeHole), source: "setActiveHole observer")
            }
            reconcileLiveHoleRouteWithPackage()
        }
        .onChange(of: path) { previousRoutes, routes in
            if let screenPackage = holeScreenPackage {
                let ordered = RoundPlayOrder.holes(
                    screenPackage.holes.map(\.number),
                    startingAt: liveRoundState?.startHole,
                    loops: screenPackage.roundLoops
                )
                if let target = LiveHolePagerSelectionLifecycle.targetForRouteChange(
                    previousPath: previousRoutes,
                    currentPath: routes,
                    ordered: ordered
                ) {
                    sendPager(.programmaticHole(target), source: "route")
                    holePagerNavigationLock = LiveHoleNavigationLock(currentHole: target)
                    trimLiveHoleSessions(around: target, package: screenPackage)
                }
            }
            // A pager selection belongs to one hole destination. Drop it when that destination is
            // left so a later course/round opening honors its routed initial hole.
            if LiveHolePagerSelectionLifecycle.shouldReset(
                previousPath: previousRoutes,
                currentPath: routes
            ) {
                sendPager(.programmaticHole(nil), source: "leave route")
                holePagerNavigationLock = nil
            }
            onLiveAppearanceChanged(Self.isLiveHoleRoute(routes.last))
            // Leaving the picker or the hole screen before the first stroke drops 备战 (and any
            // course still opening): nothing was recorded, so there is nothing to keep.
            if liveRoundState == nil, !routes.contains(where: Self.isPrepOrHoleRoute) {
                onClosePrep()
            }
        }
        .onAppear {
            #if DEBUG
            UITestEventLatencyTrace.record(
                "round-home.appear pending=\(pendingLiveHole ?? -1) course=\(package?.course.globalId ?? -1)"
            )
            #endif
            // Replacing the home package can create this view with the pending hole already set.
            // `onChange` does not fire for that initial value, so consume it here as well.
            enterPendingLiveHole(pendingLiveHole)
            onLiveAppearanceChanged(Self.isLiveHoleRoute(path.last))
        }
        .onDisappear {
            onLiveAppearanceChanged(false)
        }
    }

    private static func isLiveHoleRoute(_ route: HubRoute?) -> Bool {
        guard case .hole = route else { return false }
        return true
    }

    private static func isPrepOrHoleRoute(_ route: HubRoute) -> Bool {
        switch route {
        case .startCourse, .hole: return true
        default: return false
        }
    }

    /// Adding/removing a physical nine changes the destination's valid hole set without ending the
    /// round. Keep the current hole when it still exists; otherwise move immediately to the restored
    /// active hole (or the first retained hole) instead of leaving an empty NavigationStack page.
    private func reconcileLiveHoleRouteWithPackage() {
        // A discarded or finished round swaps in the home package; the round's own route is
        // cleared by the roundId change, never re-pointed at the home package's holes.
        guard let package,
              liveRoundState != nil,
              case .hole(let routedHole) = path.last,
              let target = LiveHoleRouteReconciliation.target(
                  routedHole: routedHole,
                  packageHoles: package.holes.map(\.number),
                  restoredActiveHole: liveRoundState?.activeHole
              ) else { return }
        path = [.hole(target)]
    }

    /// 开始记分后直接进实战屏:把刚开的洞设为唯一路径(替换掉「开始一场」),不弹回 Hub。
    private func enterPendingLiveHole(_ hole: Int?) {
        guard let hole else { return }
        #if DEBUG
        UITestEventLatencyTrace.record(
            "round-home.enter.begin hole=\(hole) course=\(package?.course.globalId ?? -1)"
        )
        #endif
        path = LiveHoleRoutePath.forPendingHole(
            current: path,
            hole: hole,
            isPrepMode: prepPackage != nil
        )
        onConsumePendingLiveHole()
        #if DEBUG
        UITestEventLatencyTrace.record(
            "round-home.enter.end hole=\(hole) course=\(package?.course.globalId ?? -1)"
        )
        #endif
    }

    /// The hole screen's package: the live round's, else the 备战 course's, else the home package.
    private var holeScreenPackage: LiveRoundPackage? {
        if liveRoundState == nil, let prepPackage { return prepPackage }
        return package
    }

    /// Before the first stroke nothing is a round: hole changes only move the screen (no cursor is
    /// saved) and the Watch is not told about a course the player is only looking at.
    private var isPrepHoleScreen: Bool {
        liveRoundState == nil && prepPackage != nil
    }

    @ViewBuilder private func currentHoleView(_ number: Int) -> some View {
        if let package = holeScreenPackage, let hole = package.holes.first(where: { $0.number == number }) {
            // round-11: forward the round-management closures so 球局调整(加打/减九洞/结束本场)lives
            // inside the in-progress screen instead of the Hub.
            CurrentHoleView(
                package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken,
                offlineStore: offlineStore, watchBridge: isPrepHoleScreen ? nil : watchBridge,
                liveRoundState: liveRoundState,
                // Network catalogue + installed templates: the turn's loops must resolve offline too.
                courseOptions: NineLoopTurn.loopCatalogue(network: courseOptions, downloaded: downloadedCourseOptions),
                isPreparingRound: isPreparingRound,
                pendingEventCount: pendingEventCount, isFinishingRound: isFinishingRound,
                finishErrorMessage: finishErrorMessage,
                onSetSecondLoop: onSetSecondLoop,
                onContinueIntoSecondLoop: onContinueIntoSecondLoop, onFinishRound: onFinishRound,
                onDiscardRound: onDiscardRound,
                sessionCache: liveHoleSessions,
                usesExternalHolePager: true,
                // On a cold restore the pager selection is seeded after its first TabView pass.
                // The persisted model cursor is the safe initial selection so the visible page
                // starts location updates before the delayed native binding acknowledgement.
                isSelected: holePagerSelection == number
                    || (holePagerSelection == nil && liveRoundState?.activeHole == number),
                onAdvanceHole: { next in
                    guard var lock = holePagerNavigationLock,
                          lock.begin(from: number, to: next) else { return }
                    holePagerNavigationLock = lock
                    withAnimation(.interactiveSpring(response: 0.28, dampingFraction: 0.92)) {
                        sendPager(.advance(next), source: "onAdvanceHole")
                    }
                    // A cancelled TabView animation may never deliver a selection change. Release
                    // the one-shot guard after the same short window as the interactive spring so
                    // scorecard/GPS/rapid-swipe recovery remains possible.
                    Task { @MainActor in
                        try? await Task.sleep(nanoseconds: 900_000_000)
                        guard var current = holePagerNavigationLock,
                              current.currentHole == next,
                              current.isTransitioning else { return }
                        current.finish(at: next)
                        holePagerNavigationLock = current
                    }
                },
                onPrepLocationChanged: { locatedHole, displayedHole in
                    guard isPrepHoleScreen else { return nil }
                    return prepHoleFollowing.navigationTarget(
                        currentLocatedHole: locatedHole,
                        displayedHole: displayedHole
                    )
                },
                onLiveHoleInitialLoadDidFinish: onLiveHoleInitialLoadDidFinish,
                onRetainReadyHolePrep: onRetainReadyHolePrep,
                isPrepMode: isPrepHoleScreen,
                prepTeeOptions: prepTeeOptions,
                onStartRoundFromFirstStroke: onStartRoundFromFirstStroke,
                onFirstStrokeClubPromptDismissed: {
                    // Keep the prep base route while the first-stroke sheet is presented. Once
                    // the player has chosen or skipped a club, the live hole becomes the sole
                    // destination and Back can no longer return to the picker.
                    guard liveRoundState != nil,
                          path.first.map({ LiveHoleRoutePath.isPrepBase($0) }) == true else { return }
                    var transaction = Transaction()
                    transaction.disablesAnimations = true
                    withTransaction(transaction) {
                        path = [.hole(number)]
                    }
                },
                onUndoRoundStart: onUndoRoundStart,
                onChangePrepTee: onChangePrepTee,
                onEvent: onEvent
            )
            // A hole owns its score/club/map/GPS presentation state and scroll position. NavigationStack
            // otherwise reuses the same destination view when `.hole(1)` becomes `.hole(2)`, carrying
            // the prior hole's @State and scroll offset into the next hole. Explicit round+hole identity
            // gives every ordered transition a fresh live surface; LocationProvider immediately republishes
            // its injected fix in UI tests and resumes Core Location normally on a real device.
            // A new round starts with a one-hole fast package and gains the complete hole list in
            // the background. Keep the live destination identity stable across that handoff so its
            // precise map, zoom and pole-drag state are not discarded; the value update still gives
            // the surface the new adjacent-hole navigation metadata.
            // The identity is the round hole's physical hole, not the whole hole set: the turn
            // appends the second loop and replaces the path in the same update, and re-identifying
            // the outgoing destination then left NavigationStack on the old hole (live Native
            // 37126990984). Changing or removing the second loop still re-identifies holes 10–18.
            .id("\(package.roundId):\(hole.number):\(hole.sourceGlobalId):\(hole.sourceLocalHole)")
        }
    }

    /// UIKit owns the interactive page animation. The simultaneous drag supplies an explicit
    /// navigation intent at finger-up; UIKit's binding reports only acknowledge displayed pages.
    @ViewBuilder private func holePagerView(_ initialHole: Int) -> some View {
        if let package = holeScreenPackage {
            let packageOrdered = RoundPlayOrder.holes(
                package.holes.map(\.number),
                startingAt: liveRoundState?.startHole,
                loops: package.roundLoops
            )
            // The state machine owns the mounted order. A package can rotate its preferred order
            // while a child sheet is presented; using the package value directly would reorder
            // ForEach and tear down the sheet before the deferred update is safe.
            let ordered = holePager.ordered.isEmpty ? packageOrdered : holePager.ordered
            TabView(selection: pagerSelectionBinding) {
                ForEach(ordered, id: \.self) { number in
                    currentHoleView(number)
                        .tag(Optional(number))
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .onAppear {
                if holePager.ordered != ordered || holePagerSelection == nil {
                    refreshPagerPageSet(fallback: initialHole)
                }
                if let selected = holePagerSelection {
                    holePagerNavigationLock = LiveHoleNavigationLock(currentHole: selected)
                    trimLiveHoleSessions(around: selected, package: package)
                }
            }
            .onChange(of: packageOrdered) { _, _ in
                refreshPagerPageSet(fallback: initialHole)
            }
            .onPreferenceChange(LiveHolePagerGestureStateKey.self) { disabled in
                #if DEBUG
                UITestPagerTrace.shared.metric(.preferenceCallback)
                #endif
                holePagerScrollDisabled = disabled
                if disabled, holePager.touchOrigin != nil {
                    sendPager(.touchEnded(step: 0), source: "map owns gesture")
                }
            }
            .onPreferenceChange(LiveHolePagerPresentationKey.self) { blocked in
                #if DEBUG
                UITestPagerTrace.shared.metric(.preferenceCallback)
                #endif
                if blocked {
                    pagerPresentationEndTask?.cancel()
                    pagerPresentationRequested = true
                    sendPager(.presentationChanged(true), source: "sheet presentation")
                } else {
                    // SwiftUI removes sheet content before UIKit finishes its dismissal animation.
                    // Keep the old ForEach order mounted until the presented controller is gone.
                    pagerPresentationEndTask?.cancel()
                    pagerPresentationEndTask = Task { @MainActor in
                        #if DEBUG
                        UITestPagerTrace.shared.taskStarted(.presentationEndTask)
                        defer { UITestPagerTrace.shared.taskFinished(.presentationEndTask) }
                        #endif
                        while !Task.isCancelled && LiveHolePagerDisplayProbe.presentationIsActive {
                            try? await Task.sleep(nanoseconds: 50_000_000)
                        }
                        guard !Task.isCancelled else { return }
                        pagerPresentationRequested = false
                        sendPager(.presentationChanged(false), source: "sheet dismissal complete")
                    }
                }
            }
            .background {
                LiveHolePagerDisplayProbe(
                    selection: pagerSelectionBinding.wrappedValue, requestID: pagerCorrectionID
                ) { requestID, displayed in
                    completePagerDisplayUpdate(requestID: requestID, displayed: displayed)
                }
                .frame(width: 0, height: 0)
            }
            .scrollDisabled(holePagerScrollDisabled)
            .simultaneousGesture(pagerDragGesture)
            .onChange(of: pagerTouchIsActive) { _, active in
                guard !active else { return }
                // A system cancellation has no onEnded. Let a normal onEnded commit first.
                Task { @MainActor in
                    await Task.yield()
                    guard !pagerTouchIsActive else { return }
                    pagerGestureStarted = false
                    if holePager.touchOrigin != nil {
                        sendPager(.touchEnded(step: 0), source: "cancelled user gesture")
                    }
                }
            }
            .onChange(of: holePagerSelection) { previous, selected in
                tracePager("onChange \(previous ?? -1)->\(selected ?? -1)")
                guard let selected, previous != selected else { return }
                holePagerNavigationLock = LiveHoleNavigationLock(currentHole: selected)
                trimLiveHoleSessions(around: selected, package: package)
            }
            .onDisappear {
                cancelPagerCorrection()
                pagerPresentationEndTask?.cancel()
                pagerPresentationEndTask = nil
                holePagerNavigationLock = nil
                holePagerScrollDisabled = false
            }
            .accessibilityIdentifier("live-hole-pager")
            .accessibilityValue(holePagerSelection.map { "第 \($0) 洞" } ?? "")
            // Keep the marker outside the pager's AX modifier so its identifier is not replaced.
            .overlay(alignment: .topLeading) { pagerTraceElement }
        } else {
            Color.clear
        }
    }

    private var pagerSelectionBinding: Binding<Int?> {
        Binding(
            get: { pagerNativeSelectionOverride ?? holePagerSelection },
            set: { sendPager(.bindingReported($0), source: "binding set") }
        )
    }

    private var pagerDragGesture: some Gesture {
        DragGesture(minimumDistance: 12)
            .updating($pagerTouchIsActive) { _, active, _ in active = true }
            .onChanged { value in
                guard !pagerGestureStarted else { return }
                pagerGestureStarted = true
                guard !holePagerScrollDisabled,
                      abs(value.translation.width) > abs(value.translation.height) else { return }
                sendPager(.touchBegan, source: "user gesture begin")
            }
            .onEnded { value in
                pagerGestureStarted = false
                guard holePager.touchOrigin != nil else { return }
                let step = LiveHolePagerState.swipeStep(
                    translationX: Double(value.translation.width),
                    translationY: Double(value.translation.height),
                    predictedX: Double(value.predictedEndTranslation.width),
                    scrollDisabled: holePagerScrollDisabled
                )
                sendPager(.touchEnded(step: step), source: "user gesture end")
            }
    }

    private func refreshPagerPageSet(fallback: Int? = nil) {
        guard let package = holeScreenPackage else { return }
        let ordered = RoundPlayOrder.holes(
            package.holes.map(\.number), startingAt: liveRoundState?.startHole, loops: package.roundLoops
        )
        let active = isPrepHoleScreen ? (holePager.activeHole ?? fallback)
            : (liveRoundState?.activeHole ?? pendingLiveHole ?? fallback)
        guard (holePager.deferredOrdered ?? holePager.ordered) != ordered
            || holePager.activeHole != active else { return }
        tracePager("package holes=\(ordered.count)")
        sendPager(.pageSetChanged(ordered: ordered, activeHole: active), source: "package")
    }

    private func sendPager(_ event: LiveHolePagerState.Event, source: String) {
        let oldSelection = holePager.selection
        let oldPending = holePager.pendingTarget
        let oldActive = holePager.activeHole
        let oldOrdered = holePager.ordered
        let lastReport = holePager.reportedSelection
        let effect = holePager.send(event)
        tracePager("\(source) \(event) selection \(oldSelection ?? -1)->\(holePager.selection ?? -1) pending \(oldPending ?? -1)->\(holePager.pendingTarget ?? -1)")
        if let deferred = holePager.deferredOrdered {
            tracePager("page order deferred count=\(deferred.count) active=\(holePager.activeHole ?? -1)")
        } else if oldOrdered != holePager.ordered {
            tracePager("page order applied count=\(holePager.ordered.count) active=\(holePager.activeHole ?? -1)")
        }
        if oldActive != holePager.activeHole || oldOrdered != holePager.ordered || event == .touchBegan {
            cancelPagerCorrection()
        }
        if let target = effect.forceScrollTo {
            tracePager("discard report; request correction=\(target) attempt=\(holePager.correctionAttempts)")
            if holePager.touchOrigin == nil {
                schedulePagerCorrection(target: target, reported: holePager.reportedSelection ?? lastReport)
            }
        } else if holePager.correctionAttempts >= 3, holePager.pendingTarget != nil {
            tracePager("correction limit reached target=\(holePager.pendingTarget ?? -1); stop")
        }
        if let selected = effect.activeHoleToPersist {
            // Explicit gesture/save intent only. Never called from a selection observer or binding.
            Task { @MainActor in
                await Task.yield()
                guard holePager.activeHole == selected else { return }
                if isPrepHoleScreen {
                    onPrepHoleChanged(selected)
                } else {
                    tracePager("onSetActiveHole=\(selected) source=\(source)")
                    onSetActiveHole(selected)
                }
            }
        }
    }

    private func cancelPagerCorrection() {
        pagerCorrectionTask?.cancel()
        pagerCorrectionTask = nil
        pagerCorrectionTarget = nil
        pagerCorrectionID = UUID()
        pagerCorrectionApplying = false
        pagerNativeSelectionOverride = nil
    }

    private func schedulePagerCorrection(target: Int, reported: Int?) {
        guard pagerCorrectionTarget == nil, holePager.ordered.contains(target) else { return }
        // The bounce must change the binding value. During sheet dismissal the stale native
        // report can already equal the current selection; assigning it again would produce no
        // UIViewRepresentable update and leave the correction request stuck forever. If the page
        // set has only two usable values, jump directly to the target instead.
        let currentSelection = holePager.selection
        let bounce = reported.flatMap {
            holePager.ordered.contains($0) && $0 != target && $0 != currentSelection ? $0 : nil
        } ?? holePager.ordered.first {
            $0 != target && $0 != currentSelection
        }
        guard bounce != nil || currentSelection != target else { return }
        pagerCorrectionTarget = target
        pagerCorrectionID = UUID()
        pagerCorrectionApplying = false
        pagerCorrectionTask = Task { @MainActor in
            #if DEBUG
            UITestPagerTrace.shared.taskStarted(.correctionTask)
            defer { UITestPagerTrace.shared.taskFinished(.correctionTask) }
            #endif
            guard await waitForPagerCorrection(target: target) else { return }
            tracePager("correction binding bounce=\(bounce ?? target) target=\(target)")
            var transaction = Transaction()
            transaction.disablesAnimations = true
            withTransaction(transaction) { pagerNativeSelectionOverride = bounce ?? target }
            // The probe acknowledges this distinct binding value after SwiftUI's update pass.
            // Only then can completePagerDisplayUpdate deliver the target in a later runloop.
        }
    }

    private func completePagerDisplayUpdate(requestID: UUID, displayed: Int?) {
        guard pagerCorrectionID == requestID, let target = pagerCorrectionTarget,
              let override = pagerNativeSelectionOverride, displayed == override else { return }
        if displayed == target {
            tracePager("correction binding target delivered=\(target)")
            pagerNativeSelectionOverride = nil
            pagerCorrectionTarget = nil
            pagerCorrectionApplying = false
            pagerCorrectionTask = nil
            return
        }
        guard !pagerCorrectionApplying else { return }
        pagerCorrectionApplying = true
        pagerCorrectionTask?.cancel()
        pagerCorrectionTask = Task { @MainActor in
            #if DEBUG
            UITestPagerTrace.shared.taskStarted(.correctionTask)
            defer { UITestPagerTrace.shared.taskFinished(.correctionTask) }
            #endif
            guard await waitForPagerCorrection(target: target) else { return }
            tracePager("correction binding apply=\(target)")
            var transaction = Transaction()
            transaction.disablesAnimations = true
            withTransaction(transaction) { pagerNativeSelectionOverride = target }
        }
    }

    @MainActor private func waitForPagerCorrection(target: Int) async -> Bool {
        // Preference values include requested and still-mounted sheets. UIKit covers the closing
        // animation as well, including the gap before onDismiss presents the turn/finish sheet.
        var deferred = false
        await Task.yield()
        while !Task.isCancelled, pagerCorrectionTarget == target, holePager.activeHole == target {
            if !pagerPresentationRequested, !LiveHolePagerDisplayProbe.presentationIsActive,
               holePager.touchOrigin == nil, !pagerTouchIsActive, !holePagerScrollDisabled {
                return true
            }
            if !deferred { tracePager("correction deferred target=\(target) sheet/touch"); deferred = true }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        return false
    }

    private func tracePager(_ message: @autoclosure () -> String) {
        #if DEBUG
        UITestPagerTrace.shared.record(message())
        #endif
    }

    @ViewBuilder private var pagerTraceElement: some View {
        #if DEBUG
        UITestPagerTraceElement()
            .frame(width: 1, height: 1)
        #endif
    }

    private func trimLiveHoleSessions(around selected: Int, package: LiveRoundPackage) {
        let ordered = RoundPlayOrder.holes(
            package.holes.map(\.number),
            startingAt: liveRoundState?.startHole,
            loops: package.roundLoops
        )
        guard let index = ordered.firstIndex(of: selected), !ordered.isEmpty else { return }
        let lower = max(0, index - 2)
        let upper = min(ordered.count - 1, index + 2)
        liveHoleSessions.trim(
            roundId: package.roundId,
            keepingHoles: Set(ordered[lower...upper])
        )
    }

    /// Session/package replacement can leave the same `.hole` route value in the path. Re-seed the
    /// pager explicitly so clearing the old cache never leaves every retained page unselected.
    private func reconcilePagerSelectionAfterSessionChange() {
        guard let screenPackage = holeScreenPackage else {
            sendPager(.programmaticHole(nil), source: "session clear")
            holePagerNavigationLock = nil
            return
        }
        let ordered = RoundPlayOrder.holes(
            screenPackage.holes.map(\.number),
            startingAt: liveRoundState?.startHole,
            loops: screenPackage.roundLoops
        )
        guard let selected = LiveHolePagerSelectionLifecycle.selectionAfterSessionChange(
            path: path,
            ordered: ordered,
            activeHole: liveRoundState?.activeHole,
            pendingLiveHole: pendingLiveHole
        ) else {
            sendPager(.programmaticHole(nil), source: "session clear")
            holePagerNavigationLock = nil
            return
        }
        refreshPagerPageSet(fallback: selected)
        sendPager(.programmaticHole(selected), source: "session")
        holePagerNavigationLock = LiveHoleNavigationLock(currentHole: selected)
        trimLiveHoleSessions(around: selected, package: screenPackage)
    }

    private func startRoundView(globalId: Int?, teeBox: String?) -> some View {
        StartRoundView(
            defaultCourseGlobalId: globalId,
            defaultTeeBox: teeBox ?? "unknown",
            // 换球场或组合 carries the course-here venue's provider loops (already fetched here).
            preselectedVenueOptions: globalId.map { HubNearby.venueLoops(containing: $0, in: heroNearbyOptions) } ?? [],
            courseOptions: courseOptions,
            downloadedCourseOptions: downloadedCourseOptions,
            recentCourseOption: recentCourseOption,
            syncStatus: syncStatus,
            isPreparing: isPreparingRound,
            apiBaseURL: apiBaseURL,
            adminTokenConfigured: adminTokenConfigured,
            onPrepareRound: onPrepareRound,
            onPrepareCourseRound: onPrepareCourseRound,
            onSaveBackendConfiguration: onSaveBackendConfiguration,
            onClearBackendConfiguration: onClearBackendConfiguration,
            onConnectGarmin: { showSettings = true },
            onLoadCourseTees: onLoadCourseTees,
            onSearchCourses: onSearchCourses,
            onNearbyCourses: onNearbyCourses,
            onCourseIntent: onCourseIntent,
            onOpenPrepCourse: onOpenPrepCourse,
            prepCourseDownloads: prepCourseDownloads,
            onDownloadPrepCourse: onDownloadPrepCourse,
            onRetryPrepCourseDownload: onRetryPrepCourseDownload,
            onValidateReadyPrepCourse: onValidateReadyPrepCourse,
            isOpeningPrepCourse: isOpeningPrepCourse
        )
    }

    // MARK: - 主卡(README §8:进行中 / 上次的球场 / 搜索)

    private var heroState: HubHeroState {
        HubHeroState.resolve(
            hasActiveRound: liveRoundState != nil,
            hasPendingWatchRound: pendingWatchRoundStart != nil,
            fix: heroLocation.latestFix.map { (latitude: $0.coordinate.latitude, longitude: $0.coordinate.longitude) },
            nearbyOptions: heroNearbyOptions,
            history: heroHistory,
            recent: recentCourseOption,
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    /// The home never prompts for location; it listens when the player has already allowed it.
    private func startHeroLocation() {
        switch heroLocation.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways:
            heroLocation.startUpdatingLocation()
        default:
            break
        }
        heroHistory = (try? offlineStore?.loadHistoryRoundsArchive())?.groups.flatMap(\.rounds) ?? []
    }

    /// Re-query nearby only when the fix moves materially (≈100 m) and no round is active.
    private var heroNearbyKey: String {
        guard liveRoundState == nil, let fix = heroLocation.latestFix else { return "none" }
        let lat = (fix.coordinate.latitude * 1_000).rounded() / 1_000
        let lon = (fix.coordinate.longitude * 1_000).rounded() / 1_000
        return "\(lat),\(lon)"
    }

    /// The 在这个球场 card: the player is standing at this venue, so its loops are installed with the
    /// tee its one-tap start would use. Empty when the card is not showing.
    private var heroCourseIntentKey: String {
        guard case let .nearby(suggestion) = heroState else { return "" }
        return "\(suggestion.globalId):\((suggestion.teeBox ?? "unknown").lowercased())"
    }

    private func announceHeroCourseIntent() {
        guard case let .nearby(suggestion) = heroState else { return }
        let loops = HubNearby.venueLoops(containing: suggestion.globalId, in: heroNearbyOptions)
        onCourseIntent(loops, suggestion.teeBox ?? "unknown")
    }

    @MainActor
    private func refreshHeroNearby() async {
        guard liveRoundState == nil, let fix = heroLocation.latestFix else { return }
        guard let matches = try? await onNearbyCourses(
            fix.coordinate.latitude,
            fix.coordinate.longitude,
            5
        ) else { return }
        heroNearbyOptions = HubNearby.options(
            from: matches,
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    private var quickCourseCandidates: [HubQuickCourseOrdering.Candidate] {
        let downloadedByID = prepCourseDownloads.reduce(into: [Int: PrepCourseDownloadRecord]()) { result, record in
            if (result[record.course.globalId]?.updatedAt ?? .distantPast) < record.updatedAt {
                result[record.course.globalId] = record
            }
        }
        let nearbyVenues: Set<String> = {
            guard let fix = heroLocation.latestFix else { return [] }
            return Set(HubNearby.currentVenue(
                options: heroNearbyOptions,
                latitude: fix.coordinate.latitude,
                longitude: fix.coordinate.longitude
            )?.map { $0.venueDisplayName.lowercased() } ?? [])
        }()
        var optionsByID: [Int: MobileCourseOption] = [:]
        for option in courseOptions + downloadedCourseOptions + heroNearbyOptions {
            optionsByID[option.globalId] = option
        }
        let rounds = heroHistory
        let candidates = optionsByID.values.map { option in
            let matching = rounds.filter { $0.globalId == option.globalId }
            let historyTee = matching.compactMap { HubCourseSuggestion.knownTee($0.teeBox) }.first
            let chipOption = historyTee.map { option.replacingTeeBox($0) } ?? option
            return HubQuickCourseOrdering.Candidate(
                option: chipOption,
                isNearby: nearbyVenues.contains(option.venueDisplayName.lowercased()),
                lastPlayedAt: matching.compactMap { Self.historyDate($0.date) }.max()
                    ?? Self.historyDate(option.latestRoundDate),
                downloadedAt: downloadedByID[option.globalId]?.updatedAt,
                playCount: max(option.roundCount, matching.count)
            )
        }
        return HubQuickCourseOrdering.ordered(Array(candidates))
    }

    private static func historyDate(_ value: String?) -> Date? {
        guard let value, !value.isEmpty else { return nil }
        if let date = historyISOFormatter.date(from: value) { return date }
        return historyDateFormatter.date(from: value)
    }

    /// An active or Watch-created round owns this card. Starting a second round would orphan the
    /// durable score/shot state, so the new-round entry only exists when neither state does.
    @ViewBuilder private var playSection: some View {
        switch heroState {
        case .inProgress:
            if let liveRoundState, let package {
                let activeHole = package.holes.contains(where: { $0.number == liveRoundState.activeHole })
                    ? liveRoundState.activeHole
                    : (package.holes.first?.number ?? liveRoundState.activeHole)
                let scored = recordedScoreHoles
                NavigationLink(value: HubRoute.hole(activeHole)) {
                    HubInProgressCard(
                        courseName: localizedCourseDisplayName(
                            package.course.venueDisplayName,
                            globalId: package.course.globalId
                        ),
                        // "继续第 N 洞" names the course's own hole (B4b-2 courseHoleNumber).
                        activeHole: package.courseHoleNumber(forRoundHole: activeHole),
                        recorded: scored.count,
                        toPar: liveToPar(scoredHoles: scored),
                        dots: HubHoleDot.loopDots(
                            roundHoles: package.holes.map(\.number),
                            activeHole: activeHole
                        ) { hole in
                            guard scored.contains(hole),
                                  let state = liveRoundState.holeState(for: hole) else { return nil }
                            return state.score - state.par
                        }
                    )
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-in-progress-round")
            } else if liveRoundState != nil {
                // An active round whose package has not loaded yet (first launch, slow backend):
                // keep the card and say so; the round's own card replaces it when the package lands.
                HubInProgressLoadingCard()
            }
        case .pendingWatch:
            if let pendingWatchRoundStart {
                HubPendingWatchCard(
                    courseName: pendingWatchRoundStart.courseName,
                    activeHole: pendingWatchRoundStart.activeHole
                )
            }
        case .nearby, .search:
            NavigationLink(value: HubRoute.start) { HubStartPlayCard() }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-new-round")
        }
    }

    /// A restored snapshot contains one default state for every package hole, including holes the
    /// player has not scored. Home progress therefore comes from the durable score events, matching
    /// the in-round scorecard, rather than from `liveRoundState.holes.count`.
    private var recordedScoreHoles: Set<Int> {
        guard let package, let offlineStore, let events = try? offlineStore.cachedEvents() else {
            return Set(liveRoundState?.scoredHoles ?? [])
        }
        let displayedHoles = Set(package.holes.map(\.number))
        return Set<Int>(events.compactMap { event in
            guard event.roundId == package.roundId,
                  event.kind == .score,
                  displayedHoles.contains(event.hole) else {
                return nil
            }
            return event.hole
        })
    }

    /// The big to-par on the in-progress card; nil (omitted) when any recorded hole is unknown.
    private func liveToPar(scoredHoles: Set<Int>) -> Int? {
        guard let liveRoundState else { return nil }
        return HubHeroState.toPar(scoredHoles: scoredHoles) { hole in
            liveRoundState.holeState(for: hole).map { (par: $0.par, score: $0.score) }
        }
    }

    @ViewBuilder private var quickCoursesSection: some View {
        let candidates = quickCourseCandidates
        if !candidates.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("快捷球场")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.secondary)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(candidates, id: \.option.globalId) { candidate in
                            NavigationLink(value: Self.quickCourseRoute(for: candidate.option)) {
                                HubQuickCourseChip(
                                    title: candidate.option.venueDisplayName,
                                    isNearby: candidate.isNearby
                                )
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("home-quick-course-\(candidate.option.globalId)")
                        }
                    }
                }
            }
        }
    }

    static func quickCourseRoute(for option: MobileCourseOption) -> HubRoute {
        .startCourse(globalId: option.globalId, teeBox: option.teeBox)
    }

    @ViewBuilder private var recentTrendSection: some View {
        let scores = HubRecentTrendRow.recentScores(history: heroHistory, limit: 5)
        if !scores.isEmpty {
            NavigationLink {
                ResultsView(apiBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore)
            } label: {
                HubRecentTrendRow(scores: scores)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("home-recent-trend")
        }
    }

    /// Weather reads the home's own fix, else the round's first Tee.
    private var weatherCoordinate: (latitude: Double, longitude: Double)? {
        guard let fix = heroLocation.latestFix else { return nil }
        return (fix.coordinate.latitude, fix.coordinate.longitude)
    }

    /// Re-read only when the place moves ≈5 km; the hour bucket refreshes a long-open home.
    private var weatherKey: String {
        guard apiBaseURL != nil, let place = weatherCoordinate else { return "none" }
        let lat = (place.latitude * 20).rounded() / 20
        let lon = (place.longitude * 20).rounded() / 20
        let hour = Int(Date().timeIntervalSince1970 / 3600)
        return "\(lat),\(lon),\(hour)"
    }

    @MainActor
    private func refreshHomeWeather() async {
        guard let apiBaseURL, let place = weatherCoordinate else { return }
        let city = await Self.cityName(for: place)
        if let weather = await HomeWeatherClient.fetch(
            baseURL: apiBaseURL,
            adminToken: adminToken,
            latitude: place.latitude,
            longitude: place.longitude
        ) {
            homeWeather = weather
        }
        if let city, !city.isEmpty { homeCity = city }
    }

    @ViewBuilder private var weatherLine: some View {
        if let presentation = homeWeather?.presentation {
            HStack(spacing: 5) {
                if let homeCity, !homeCity.isEmpty { Text(homeCity) }
                Text(presentation.temperatureText)
                if let condition = presentation.conditionText { Text(condition) }
                if let wind = presentation.windForceText {
                    Text("·")
                    Text(wind)
                }
            }
            .font(.subheadline.weight(.medium))
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier("home-weather-line")
        }
    }

    private static func cityName(for place: (latitude: Double, longitude: Double)) async -> String? {
        await withCheckedContinuation { continuation in
            let geocoder = CLGeocoder()
            geocoder.reverseGeocodeLocation(
                CLLocation(latitude: place.latitude, longitude: place.longitude)
            ) { marks, _ in
                let mark = marks?.first
                continuation.resume(returning: mark?.locality ?? mark?.administrativeArea)
            }
        }
    }

    // MARK: - 上一场速览

    @ViewBuilder private var lastRoundSection: some View {
        if let package, let last = package.recentHistory.rounds.first {
            VStack(alignment: .leading, spacing: 9) {
                HubSectionLabel("上一场")
                NavigationLink(
                    value: HubRoute.roundReview(
                        roundRef: last.roundId,
                        courseName: last.localizedCourseDisplayName,
                        globalId: last.globalId ?? package.course.globalId,
                        // The past-round API still speaks nine / back_global_id: a single half
                        // is its `nine`; a sibling second loop is its back course.
                        backGlobalId: package.secondLoop.map(\.globalId).flatMap {
                            $0 == package.course.globalId ? nil : $0
                        },
                        nine: package.roundLoops.count == 1 && package.roundLoops[0].isCourseHalf
                            ? package.roundLoops[0].half
                            : nil,
                        teeBox: package.course.teeBox
                    )
                ) {
                    HubLastRoundCard(
                        courseName: last.localizedCourseDisplayName,
                        date: last.date,
                        score: last.score,
                        toPar: last.toPar,
                        holesCompleted: last.holesCompleted,
                        par: last.par,
                        topoURL: lastRoundTopoURL(last),
                        scoreStrip: lastRoundStrip
                    )
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-last-round")
            }
            .padding(.top, 6)
        }
    }

    /// `RecentRoundSummary` has no per-hole scores; the cached round archive does. Use its newest
    /// card only when it is this same round, otherwise show no strip.
    private func loadLastRoundStrip() {
        guard let last = package?.recentHistory.rounds.first else {
            lastRoundStrip = []
            return
        }
        let archive = try? offlineStore?.loadHistoryRoundsArchive()
        lastRoundStrip = HubHeroState.lastRoundStrip(
            lastRoundId: last.roundId,
            newest: archive?.groups.first?.rounds.first
        )
    }

    /// 上一场第 1 洞的真实地形缩略图 URL:需要 apiBaseURL + 该盘球场 globalId(后端随 summary 下发,
    /// 且 PR #263 已把最近一盘的 topo 预渲缓存 → 取图快)。缺任一 → nil → 卡片回退纯文字,绝不造图。
    private func lastRoundTopoURL(_ round: RecentRoundSummary) -> URL? {
        guard let apiBaseURL, let globalId = round.globalId else { return nil }
        return SyncClient.topoImageURL(baseURL: apiBaseURL, globalId: globalId, localHole: 1)
    }

    // 本场逐洞跳转网格已从首页移除(用户反馈:首页这块「不知道干嘛用的」)。进行中的球局从主卡
    // 「继续第 N 洞」进入实战屏,逐洞推进;首页只保留 主卡 / 备战·成绩 / 上一场,更精简。

    // MARK: - 设置 sheet(齿轮入口)— Garmin 账号 + 手动同步兜底。记分时已自动同步,
    // 主页不再放 Garmin/同步(用户要求:同步自动化、Garmin 不写在主页)。

    private var settingsSheet: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 12) {
                        Image(systemName: "arrow.triangle.2.circlepath.circle.fill")
                            .font(.title2)
                            .foregroundStyle(LiveHoleStyle.green)
                        VStack(alignment: .leading, spacing: 3) {
                            // The model owns the sync state. During an in-flight operation, prefer
                            // the explicit loading label over the previous terminal result so a
                            // SwiftUI update cannot briefly show “已更新” beside the spinner.
                            Text(garminConnectionState.statusText)
                                .font(.subheadline.weight(.semibold))
                            if let lastGarminSyncAt, !isGarminSyncing {
                                Text("上次成功 · \(lastGarminSyncAt, format: .dateTime.month().day().hour().minute())")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if isGarminSyncing {
                            ProgressView()
                                .controlSize(.small)
                        }
                    }
                    Button {
                        if isGarminSyncing {
                            Task { await onCancelGarminSync() }
                        } else {
                            onSync()
                        }
                    } label: {
                        Label(
                            isGarminSyncing ? "取消同步" : "立即同步 Garmin",
                            systemImage: isGarminSyncing ? "xmark.circle" : "arrow.clockwise"
                        )
                    }
                    .foregroundStyle(LiveHoleStyle.green)
                    .disabled(apiBaseURL == nil)
                    .accessibilityIdentifier("settings-sync-garmin")
                } header: {
                    Text("Garmin 数据")
                }

                Section {
                    NavigationLink {
                        GarminSessionView(
                            apiBaseURL: apiBaseURL,
                            adminToken: adminToken,
                            sessionStore: sessionStore,
                            onSessionImported: onGarminSessionImported,
                            onSessionImportedOutcome: onGarminSessionImportedOutcome,
                            connectionState: garminConnectionState,
                            onSessionForgot: onGarminSessionForgot
                        )
                    } label: {
                        Label("Garmin 账号", systemImage: "link")
                    }
                    NavigationLink {
                        ClubSettingsView(clubProfiles: package?.clubProfiles ?? [], apiBaseURL: apiBaseURL, adminToken: adminToken)
                    } label: {
                        Label("球包", systemImage: "bag")
                    }
                    ClubBagSyncSettingsRow(sync: .shared)
#if DEBUG
                    NavigationLink {
                        BackendSettingsView(
                            apiBaseURL: apiBaseURL,
                            adminTokenConfigured: adminTokenConfigured,
                            syncStatus: syncStatus,
                            onSave: onSaveBackendConfiguration,
                            onClear: onClearBackendConfiguration
                        )
                    } label: {
                        Label("开发者连接", systemImage: "server.rack")
                    }
                    .accessibilityIdentifier("settings-backend")
#endif
                } header: {
                    Text("账号与球包")
                }

                OfflineCourseDownloadsSection(rows: OfflineCourseDownloadRow.rows(
                    live: liveCourseDownloadProgress,
                    current: liveRoundState.flatMap { state in
                        package.flatMap { $0.roundId == state.roundId ? LiveCourseDownloadProgress.Identity(package: $0) : nil }
                    },
                    // A guess shows only while it is actually downloading, never as a standing
                    // "等待下载" the player did not ask for.
                    downloads: prepCourseDownloads.filter { !$0.isSpeculative || $0.phase != .queued }
                ), usage: offlineStorageUsage)
                SpeculativePrefetchSettingsSection(onChange: onSpeculativePrefetchSettingChanged)
            }
            .task {
                await onRefreshOfflineStorageUsage()
            }
            .task {
                await onRefreshGarminSyncStatus()
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") {
                        showSettings = false
                    }
                }
            }
        }
    }
}

/// 设置 → 离线球场: the only place download progress and storage use are shown (design README §8
/// and IMPLEMENTATION_PLAN keep process status off the play and prep screens). Nothing to list and
/// nothing stored → no section.
struct OfflineCourseDownloadsSection: View {
    let rows: [OfflineCourseDownloadRow]
    var usage: OfflineStorageUsage? = nil

    private var storedUsage: OfflineStorageUsage? {
        usage.flatMap { $0.totalBytes > 0 ? $0 : nil }
    }

    var body: some View {
        if !rows.isEmpty || storedUsage != nil {
            Section {
                ForEach(rows) { row in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.title)
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                if let subtitle = row.subtitle {
                                    Text(subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Spacer(minLength: 8)
                            Text(row.status)
                                .font(.caption)
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                        if let fraction = row.fraction {
                            // Drawn in SwiftUI rather than `ProgressView(value:)`, which is
                            // UIKit-backed and renders as a placeholder in design snapshots.
                            Capsule()
                                .fill(Color(.systemFill))
                                .frame(height: 4)
                                .overlay(alignment: .leading) {
                                    GeometryReader { proxy in
                                        Capsule()
                                            .fill(LiveHoleStyle.green)
                                            .frame(width: proxy.size.width * fraction)
                                    }
                                }
                                .accessibilityHidden(true)
                        }
                    }
                    .padding(.vertical, 2)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel([row.title, row.subtitle, row.status].compactMap { $0 }.joined(separator: "，"))
                    .accessibilityIdentifier("settings-offline-course-\(row.id)")
                }
            } header: {
                Text("离线球场")
            } footer: {
                if let storedUsage {
                    Text(storedUsage.summaryText)
                        .monospacedDigit()
                        .accessibilityIdentifier("settings-offline-storage-usage")
                }
            }
        }
    }
}

/// 设置: courses the player has played (可能会打) and the nearest courses somewhere new (新区域)
/// download on their own, on Wi-Fi unless this is on.
struct SpeculativePrefetchSettingsSection: View {
    var onChange: () -> Void = {}
    @AppStorage(SpeculativePrefetchSettings.cellularKey) private var cellularAllowed = false

    var body: some View {
        Section {
            Toggle("用蜂窝网络预下载球场", isOn: $cellularAllowed)
                .accessibilityIdentifier("settings-prefetch-cellular")
        } footer: {
            Text("常打的球场、到新地方时附近的球场，默认只在 Wi-Fi 下自动下载；低数据模式下不下载。")
        }
        .onChange(of: cellularAllowed) { _, _ in onChange() }
    }
}

// MARK: - 表现型卡片(纯输入 → CI 设计快照可复用)

/// 主卡 · 进行中 (首页 C): deep-green card — 进行中, the course, 已打 N 洞, the big to-par (when
/// known), this loop's holes as dots (scored = colour by result, current = ring), and the C99
/// continue action with hole and to-par in one label.
/// Progress shows recorded holes only.
struct HubInProgressCard: View {
    let courseName: String
    let activeHole: Int
    let recorded: Int
    /// Score to par over the recorded holes; nil → omitted, never guessed.
    var toPar: Int? = nil
    /// The loop holding the active hole; empty → no dot row.
    var dots: [HubHoleDot] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Circle().fill(HubBentoStyle.lightGreen).frame(width: 8, height: 8)
                        Text("进行中")
                            .font(.caption.weight(.heavy))
                            .foregroundStyle(HubBentoStyle.lightGreen)
                    }
                    Text(courseName)
                        .font(.title2.weight(.heavy))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("已打 \(recorded) 洞")
                        .font(.subheadline)
                        .foregroundStyle(HubBentoStyle.onGreenSecondary)
                }
                Spacer(minLength: 8)
                if let toPar {
                    VStack(alignment: .trailing, spacing: 0) {
                        Text(Self.toParText(toPar))
                            .font(.system(size: 40, weight: .heavy, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(.white)
                        Text("对标准杆")
                            .font(.caption)
                            .foregroundStyle(HubBentoStyle.onGreenSecondary)
                    }
                    .fixedSize()
                }
            }
            Spacer(minLength: 14)
            if !dots.isEmpty {
                HStack(spacing: 4) {
                    ForEach(dots) { dot in
                        Capsule()
                            .fill(dot.fill)
                            .overlay(Capsule().stroke(Color.white, lineWidth: dot.isCurrent ? 2 : 0))
                            .frame(height: 16)
                            .frame(maxWidth: .infinity)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("本圈逐洞")
                .accessibilityIdentifier("home-in-progress-dots")
                Spacer(minLength: 14)
            }
            HubBentoPrimaryButtonLabel(title: continueTitle, fullWidth: true)
        }
        .padding(18)
        .hubBentoHero { HubBentoStyle.deepGreen }
    }

    static func toParText(_ toPar: Int) -> String {
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }

    private var continueTitle: String {
        if let toPar { return "继续 · 第 \(activeHole) 洞 · \(Self.toParText(toPar))" }
        return "继续 · 第 \(activeHole) 洞"
    }
}

/// Visible while a Watch round-start fact is durable but the iPhone has not received its full course
/// package yet. It is informational only: no fake distance, score, or navigation destination is shown.
struct HubPendingWatchCard: View {
    let courseName: String
    let activeHole: Int

    var body: some View {
        HStack(spacing: 12) {
            ProgressView()
                .controlSize(.small)
                .tint(LiveHoleStyle.green)
            VStack(alignment: .leading, spacing: 3) {
                Text("手表已开始")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(LiveHoleStyle.green)
                Text("\(courseName) · 第 \(activeHole) 洞")
                    .font(.headline.weight(.semibold))
                    .lineLimit(1)
                Text("正在获取球场数据，完成后自动进入进行中球局")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(LiveHoleStyle.green.opacity(0.35), lineWidth: 1)
        )
        .accessibilityIdentifier("home-watch-round-pending")
    }
}

/// 备战 / 历史复盘 / 数据统计 入口磁贴(左上绿色图标方块 + 标题 + 副标题)。
struct HubTile: View {
    let icon: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HubIconSquare(system: icon)
            Spacer(minLength: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.bold)).foregroundStyle(.primary)
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 104, alignment: .leading)
        .hubCard(padding: 14)
    }
}

/// 上一场速览卡:左侧真实球道缩略图(那盘球场第 1 洞 topo)+ 球场 · 日期 + 杆数大字 +
/// 相对标准杆(score token 配色)。`topoURL == nil`(缺 globalId / 无 apiBaseURL)→ 不放图,
/// 布局与纯文字版一致,绝不破版、绝不造图。
struct HubLastRoundCard: View {
    let courseName: String
    let date: String
    let score: Int
    let toPar: Int?
    var holesCompleted: Int? = nil
    var par: Int? = nil
    /// 那盘球场第 1 洞的真实地形缩略图 URL;nil → 回退纯文字卡(见 `lastRoundTopoURL`)。
    var topoURL: URL? = nil
    /// 18 洞记分符号条(README §8);空 → 不显示。
    var scoreStrip: [HistoryScoreCell] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            summaryRow
            if !scoreStrip.isEmpty {
                HubScoreStrip(cells: scoreStrip)
            }
        }
        .hubCard()
    }

    private var summaryRow: some View {
        HStack(spacing: 12) {
            if let topoURL {
                thumbnail(topoURL)
            }
            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .top, spacing: 8) {
                    Text(courseName)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.primary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .layoutPriority(1)
                    Spacer(minLength: 4)
                    VStack(alignment: .trailing, spacing: 0) {
                        Text("\(score)")
                            .font(.system(size: 26, weight: .heavy))
                            .monospacedDigit()
                            .foregroundStyle(.primary)
                        Text(toParText)
                            .font(.subheadline.weight(.bold))
                            .monospacedDigit()
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                    }
                    // A long CJK course name has a much larger ideal width than the card. Reserve
                    // the score's intrinsic width first, then let the name wrap into its two lines;
                    // otherwise SwiftUI may compress "98 / +26" into one digit per line.
                    .fixedSize(horizontal: true, vertical: false)
                    .layoutPriority(2)
                }
                Text(metadataText)
                    .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
        }
    }

    private var metadataText: String {
        [Optional(aiCaddieShortDate(date)), holesParText]
            .compactMap { $0 }
            .joined(separator: " · ")
    }

    /// 小尺寸圆角地形缩略图。加载中 / 加载失败 / CI 快照无网络 → 克制的绿调占位(map 图标),
    /// 与卡片风格一致、绝不显示破图空框。真实地形图靠真机加载(ImageRenderer 快照里恒为占位)。
    @ViewBuilder private func thumbnail(_ url: URL) -> some View {
        AsyncImage(url: url) { phase in
            switch phase {
            case .success(let image):
                image.resizable().scaledToFill()
            default:
                thumbnailPlaceholder
            }
        }
        .frame(width: 56, height: 56)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color.black.opacity(0.06), lineWidth: 1)
        )
        .accessibilityHidden(true)
    }

    private var thumbnailPlaceholder: some View {
        ZStack {
            HubStyle.iconTint
            Image(systemName: "map")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(LiveHoleStyle.green.opacity(0.55))
        }
    }

    private var holesParText: String? {
        var parts: [String] = []
        if let holesCompleted { parts.append("\(holesCompleted) 洞") }
        if let par { parts.append("Par \(par)") }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var toParText: String {
        guard let toPar, toPar != 0 else {
            return "E"
        }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}

/// 上一场卡的 18 洞记分符号条:每洞一个圈方码(形状 + 颜色双编码),按洞序排开。
struct HubScoreStrip: View {
    let cells: [HistoryScoreCell]

    var body: some View {
        HStack(spacing: 1) {
            ForEach(cells) { cell in
                ScoreChip(score: cell.score, toPar: cell.toPar, size: 17)
                    .frame(maxWidth: .infinity)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("逐洞成绩")
        .accessibilityIdentifier("home-last-round-strip")
    }
}

private struct HomeGreetingDateKey: EnvironmentKey {
    static let defaultValue: Date? = nil
}

extension EnvironmentValues {
    /// Overrides "now" for the home greeting; nil (production) uses the real clock.
    var homeGreetingDate: Date? {
        get { self[HomeGreetingDateKey.self] }
        set { self[HomeGreetingDateKey.self] = newValue }
    }
}
