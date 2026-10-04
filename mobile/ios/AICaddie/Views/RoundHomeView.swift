import CoreLocation
import Foundation
import SwiftUI

/// 球局主页(Hub)— README §8 / `pre-round.html` 第 1 屏:最大一块主卡随情况变(进行中 =
/// “继续第 N 洞”;有上次/已知球场 = 该球场 + 上次的第一个环和发球台 + “开始”;都没有 = 搜索),
/// 备战 · 成绩磁贴、上一场速览(18 洞记分符号条)。灰底圆角白卡(ScrollView),保留导航接线(实战逐洞、
/// 赛前攻略、历史复盘、Garmin 账号)。Garmin 同步状态只在设置里,首页不写。
/// 表现型卡片组件(Hub*)纯输入,供 CI 设计快照复用。
/// Hub navigation routes driven by a path, so the app can jump straight into the live hole after
/// 开始记分 (instead of bouncing back to the Hub). 备战/复盘 stay simple leaf links.
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

public struct RoundHomeView: View {
    public let package: LiveRoundPackage
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
    public let onGarminSessionForgot: () -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void
    /// 拉取所选球场的可选发球台(供「开始一场」的选台器);仅转发给 StartRoundView。
    public let onLoadCourseTees: (Int) async -> [CourseTee]
    /// Garmin 全库名称搜索；StartRoundView 只保留本次结果，选中后走现有单球场准备链。
    public let onSearchCourses: (String, String?, Double?, Double?) async throws -> [MobileCourseSearchMatch]
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

    @State private var showSettings = false
    /// The in-progress card's 结束: the same finish page as the live map's 结束本场.
    @State private var showFinishSummary = false
    @State private var pendingHomeDiscard = false
    @State private var showHomeDiscardConfirmation = false
    @State private var path: [HubRoute] = []
    /// The last round's 18-hole symbol strip, from the cached round archive (empty when unknown).
    @State private var lastRoundStrip: [HistoryScoreCell] = []
    /// README §8 "在球场附近": the home's own fix (never a permission prompt here — the start
    /// screen asks) and the provider-nearby courses around it, from the same nearby authority as
    /// 开始一场.
    @StateObject private var heroLocation = LocationProvider()
    @State private var heroNearbyOptions: [MobileCourseOption] = []
    /// Archived rounds, newest first: each venue's last first loop and tee.
    @State private var heroHistory: [HistoryRoundCard] = []

    /// The clock the greeting reads; design snapshots pin it so the title never depends on when CI ran.
    @Environment(\.homeGreetingDate) private var greetingDate

    public init(
        package: LiveRoundPackage,
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
        onGarminSessionForgot: @escaping () -> Void = {},
        onSaveBackendConfiguration: @escaping (String, String?) -> Void = { _, _ in },
        onClearBackendConfiguration: @escaping () -> Void = {},
        onLoadCourseTees: @escaping (Int) async -> [CourseTee] = { _ in [] },
        onSearchCourses: @escaping (String, String?, Double?, Double?) async throws -> [MobileCourseSearchMatch] = { _, _, _, _ in [] },
        onNearbyCourses: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch] = { _, _, _ in [] },
        onDownloadPrepCourse: @escaping (MobileCourseOption) -> Void = { _ in },
        onRetryPrepCourseDownload: @escaping (String) -> Void = { _ in },
        onValidateReadyPrepCourse: @escaping (PrepCourseDownloadRecord) async -> Bool = { _ in true },
        pendingLiveHole: Int? = nil,
        onConsumePendingLiveHole: @escaping () -> Void = {},
        onLiveHoleInitialLoadDidFinish: @escaping () -> Void = {},
        onLiveAppearanceChanged: @escaping (Bool) -> Void = { _ in },
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
        self.onGarminSessionForgot = onGarminSessionForgot
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
        self.onLoadCourseTees = onLoadCourseTees
        self.onSearchCourses = onSearchCourses
        self.onNearbyCourses = onNearbyCourses
        self.onDownloadPrepCourse = onDownloadPrepCourse
        self.onRetryPrepCourseDownload = onRetryPrepCourseDownload
        self.onValidateReadyPrepCourse = onValidateReadyPrepCourse
        self.pendingLiveHole = pendingLiveHole
        self.onConsumePendingLiveHole = onConsumePendingLiveHole
        self.onLiveHoleInitialLoadDidFinish = onLiveHoleInitialLoadDidFinish
        self.onLiveAppearanceChanged = onLiveAppearanceChanged
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
        NavigationStack(path: $path) {
            ScrollView {
                VStack(spacing: 14) {
                    playSection
                    tilesRow
                    lastRoundSection
                }
                .padding(.horizontal, 16)
                .padding(.top, 4)
                .padding(.bottom, 22)
            }
            .background(HubStyle.grouped)
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
                    currentHoleView(number)
                case .history:
                    RecentRoundReviewView(
                        package: package,
                        apiBaseURL: apiBaseURL,
                        adminToken: adminToken
                    )
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
            .task(id: package.recentHistory.rounds.first?.roundId) {
                loadLastRoundStrip()
            }
            .onAppear(perform: startHeroLocation)
            .task(id: heroNearbyKey) {
                await refreshHeroNearby()
            }
        }
        // The NavigationStack owns the system status bar, so the immersive hole destination cannot
        // hide it reliably from inside CurrentHoleView. Keep normal chrome on every non-live route.
        .statusBarHidden(Self.isLiveHoleRoute(path.last))
        .sheet(isPresented: $showFinishSummary, onDismiss: {
            // 放弃本场 asks once, after the finish page has closed (a dialog requested while the
            // sheet is still dismissing is dropped).
            guard pendingHomeDiscard else { return }
            pendingHomeDiscard = false
            showHomeDiscardConfirmation = true
        }) {
            LiveRoundFinishSummaryView(
                courseName: package.course.venueDisplayName,
                holes: package.holes,
                loopTitles: LiveScorecardLoops.titles(
                    package: package,
                    catalogue: NineLoopTurn.loopCatalogue(network: courseOptions, downloaded: downloadedCourseOptions)
                ),
                scores: LiveRoundFinishSummaryView.completedScores(
                    holes: package.holes,
                    liveRoundState: liveRoundState,
                    recordedScoreHoles: recordedScoreHoles
                ),
                isFinishingRound: isFinishingRound,
                finishErrorMessage: finishErrorMessage,
                onFinish: {
                    Task {
                        if await onFinishRound() {
                            showFinishSummary = false
                        }
                    }
                },
                onContinue: { showFinishSummary = false },
                onDiscard: {
                    pendingHomeDiscard = true
                    showFinishSummary = false
                }
            )
        }
        .confirmationDialog(
            "确定放弃本场？",
            isPresented: $showHomeDiscardConfirmation,
            titleVisibility: .visible
        ) {
            Button("放弃本场", role: .destructive) { onDiscardRound() }
            Button("取消", role: .cancel) {}
        } message: {
            Text("放弃后这一场不会保存，已记的成绩、落点和待上传媒体会删除。")
        }
        .onChange(of: pendingLiveHole) { _, hole in
            #if DEBUG
            UITestEventLatencyTrace.record("round-home.pending-change hole=\(hole ?? -1)")
            #endif
            enterPendingLiveHole(hole)
        }
        .onChange(of: liveRoundState?.roundId) { previousRoundId, currentRoundId in
            if previousRoundId != nil, currentRoundId == nil {
                path = []
            }
        }
        .onChange(of: package.holeSetIdentity) { _, _ in
            reconcileLiveHoleRouteWithPackage()
        }
        .onChange(of: liveRoundState?.activeHole) { _, _ in
            reconcileLiveHoleRouteWithPackage()
        }
        .onChange(of: path) { _, routes in
            onLiveAppearanceChanged(Self.isLiveHoleRoute(routes.last))
        }
        .onAppear {
            #if DEBUG
            UITestEventLatencyTrace.record(
                "round-home.appear pending=\(pendingLiveHole ?? -1) course=\(package.course.globalId)"
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

    /// Adding/removing a physical nine changes the destination's valid hole set without ending the
    /// round. Keep the current hole when it still exists; otherwise move immediately to the restored
    /// active hole (or the first retained hole) instead of leaving an empty NavigationStack page.
    private func reconcileLiveHoleRouteWithPackage() {
        // A discarded or finished round swaps in the home package; the round's own route is
        // cleared by the roundId change, never re-pointed at the home package's holes.
        guard liveRoundState != nil,
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
            "round-home.enter.begin hole=\(hole) course=\(package.course.globalId)"
        )
        #endif
        path = [.hole(hole)]
        onConsumePendingLiveHole()
        #if DEBUG
        UITestEventLatencyTrace.record(
            "round-home.enter.end hole=\(hole) course=\(package.course.globalId)"
        )
        #endif
    }

    @ViewBuilder private func currentHoleView(_ number: Int) -> some View {
        if let hole = package.holes.first(where: { $0.number == number }) {
            // round-11: forward the round-management closures so 球局调整(加打/减九洞/结束本场)lives
            // inside the in-progress screen instead of the Hub.
            CurrentHoleView(
                package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken,
                offlineStore: offlineStore, watchBridge: watchBridge, liveRoundState: liveRoundState,
                // Network catalogue + installed templates: the turn's loops must resolve offline too.
                courseOptions: NineLoopTurn.loopCatalogue(network: courseOptions, downloaded: downloadedCourseOptions),
                isPreparingRound: isPreparingRound,
                pendingEventCount: pendingEventCount, isFinishingRound: isFinishingRound,
                finishErrorMessage: finishErrorMessage,
                onSetSecondLoop: onSetSecondLoop,
                onContinueIntoSecondLoop: onContinueIntoSecondLoop, onFinishRound: onFinishRound,
                onDiscardRound: onDiscardRound,
                onAdvanceHole: { next in
                    onSetActiveHole(next)
                    path = [.hole(next)]
                },
                onLiveHoleInitialLoadDidFinish: onLiveHoleInitialLoadDidFinish,
                onRetainReadyHolePrep: onRetainReadyHolePrep,
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
            onNearbyCourses: onNearbyCourses
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

    /// "开始" / "再打上次那个": start that loop and tee directly; the Hub enters the first hole when
    /// the round is prepared (pendingLiveHole → path).
    private func startSuggested(_ suggestion: HubCourseSuggestion) {
        let request = suggestion.startRequest(roundId: StartRoundView.freshLiveRoundId(globalId: suggestion.globalId))
        onPrepareCourseRound(request.roundId, request.teeBox, request.loops)
    }

    /// An active or Watch-created round owns this card. Starting a second round would orphan the
    /// durable score/shot state, so the new-round entry only exists when neither state does.
    @ViewBuilder private var playSection: some View {
        switch heroState {
        case .inProgress:
            if let liveRoundState {
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
                        reservesEndAction: true
                    )
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-in-progress-round")
                .overlay(alignment: .bottomTrailing) {
                    Button { showFinishSummary = true } label: { HubEndRoundPill() }
                        .buttonStyle(.plain)
                        .padding(18)
                        .accessibilityLabel("结束本场")
                        .accessibilityIdentifier("home-end-round")
                }
            }
        case .pendingWatch:
            if let pendingWatchRoundStart {
                HubPendingWatchCard(
                    courseName: pendingWatchRoundStart.courseName,
                    activeHole: pendingWatchRoundStart.activeHole
                )
            }
        case .nearby(let suggestion):
            // At this course: "开始" starts its last first loop + tee directly; "换球场或组合" opens
            // 开始一场.
            HubSuggestedCourseCard(courseName: suggestion.courseName, startTitle: suggestion.startTitle) {
                Button {
                    startSuggested(suggestion)
                } label: {
                    HubPrimaryPill(title: "开始")
                }
                .buttonStyle(.plain)
                .disabled(isPreparingRound)
                .accessibilityIdentifier("home-start-nearby")
                // 开始一场 opens with the course here (its loop and tee) already selected.
                NavigationLink(value: HubRoute.startCourse(globalId: suggestion.globalId, teeBox: suggestion.teeBox)) {
                    HubSecondaryLinkLabel(title: "换球场或组合")
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-change-course")
            }
        case .search(let replay):
            VStack(spacing: 10) {
                NavigationLink(value: HubRoute.start) {
                    HubSearchHeroCard()
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-new-round")
                if let replay {
                    Button {
                        startSuggested(replay)
                    } label: {
                        HubReplayLastCard(courseName: replay.courseName, startTitle: replay.startTitle)
                    }
                    .buttonStyle(.plain)
                    .disabled(isPreparingRound)
                    .accessibilityIdentifier("home-replay-last")
                }
            }
        }
    }

    /// A restored snapshot contains one default state for every package hole, including holes the
    /// player has not scored. Home progress therefore comes from the durable score events, matching
    /// the in-round scorecard, rather than from `liveRoundState.holes.count`.
    private var recordedScoreHoles: Set<Int> {
        guard let offlineStore, let events = try? offlineStore.loadEvents() else {
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

    // MARK: - 备战 · 成绩（球局与统计统一入口）

    @ViewBuilder private var tilesRow: some View {
        HStack(spacing: 11) {
            if let apiBaseURL {
                NavigationLink {
                    // 备战者已有目的地：直接名称搜索，不走现场 GPS 选场。
                    PrepCoursePickerView(
                        courseOptions: courseOptions,
                        downloadedCourseOptions: downloadedCourseOptions,
                        downloadedCourseKeys: downloadedCourseKeys,
                        downloads: prepCourseDownloads,
                        downloadPresentation: prepCourseDownloadPresentation,
                        apiBaseURL: apiBaseURL,
                        adminToken: adminToken,
                        offlineStore: offlineStore,
                        onDownload: onDownloadPrepCourse,
                        onRetryDownload: onRetryPrepCourseDownload,
                        onValidateReadyDownload: onValidateReadyPrepCourse,
                        onLoadCourseTees: onLoadCourseTees
                    )
                } label: {
                    HubTile(icon: "scope", title: "备战", subtitle: "搜索 · 球童试算")
                }
                .buttonStyle(.plain)
            }
            NavigationLink {
                // Public compatibility entry remains ResultsView(apiBaseURL: apiBaseURL, adminToken: adminToken);
                // the injected OfflineStore below enables stale-while-refresh without changing that API.
                ResultsView(
                    apiBaseURL: apiBaseURL,
                    adminToken: adminToken,
                    offlineStore: offlineStore
                )
            } label: {
                HubTile(icon: "chart.line.uptrend.xyaxis", title: "成绩", subtitle: "球局 · 统计")
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - 上一场速览

    @ViewBuilder private var lastRoundSection: some View {
        if let last = package.recentHistory.rounds.first {
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
        guard let last = package.recentHistory.rounds.first else {
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
                        ClubSettingsView(clubProfiles: package.clubProfiles, apiBaseURL: apiBaseURL, adminToken: adminToken)
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

// MARK: - 表现型卡片(纯输入 → CI 设计快照可复用)

/// 主卡 · 进行中(`pre-round.html` live):“进行中”、球场、大号累计成绩(已知时)、“已打 N 洞”、
/// “继续第 N 洞”。白卡 + 淡绿描边。Progress shows recorded holes only.
struct HubInProgressCard: View {
    let courseName: String
    let activeHole: Int
    let recorded: Int
    /// Score to par over the recorded holes; nil → omitted, never guessed.
    var toPar: Int? = nil
    /// Leaves room on the right of 继续 for the home's 结束 button, which the app lays over the
    /// card (a button cannot live inside the card's NavigationLink).
    var reservesEndAction = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                Circle().fill(HubStyle.liveDot).frame(width: 8, height: 8)
                Text("进行中")
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(LiveHoleStyle.green)
            }
            Text(courseName)
                .font(.title2.weight(.bold))
                .foregroundStyle(.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                if let toPar {
                    Text(Self.toParText(toPar))
                        .font(.system(size: 34, weight: .heavy))
                        .monospacedDigit()
                        .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                }
                Text("已打 \(recorded) 洞")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            HubPrimaryPill(title: "继续第 \(activeHole) 洞", fullWidth: true)
                .padding(.trailing, reservesEndAction ? HubEndRoundPill.reservedWidth : 0)
                .padding(.top, 6)
        }
        .hubHeroCard()
    }

    static func toParText(_ toPar: Int) -> String {
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}

/// 主卡 · 上次的球场(`pre-round.html` near):球场名 + “从 B 场 开始 · 蓝 T” + 开始 / 换球场或组合。
/// The actions are injected so the app wraps them in navigation links while the CI snapshot can
/// render plain labels.
struct HubSuggestedCourseCard<Actions: View>: View {
    let courseName: String
    let startTitle: String
    let actions: Actions

    init(courseName: String, startTitle: String, @ViewBuilder actions: () -> Actions) {
        self.courseName = courseName
        self.startTitle = startTitle
        self.actions = actions()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(courseName)
                .font(.title2.weight(.bold))
                .foregroundStyle(.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Text(startTitle)
                .font(.subheadline.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(.secondary)
            HStack(spacing: 18) {
                actions
            }
            .padding(.top, 12)
        }
        .hubHeroCard()
    }
}

/// 主卡 · 没有已知球场:“今天去哪打？” + 搜索入口(整卡打开开始一场)。
struct HubSearchHeroCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("今天去哪打？")
                .font(.title2.weight(.bold))
                .foregroundStyle(.primary)
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                Text("搜索球场或城市")
                Spacer(minLength: 0)
            }
            .font(.body)
            .foregroundStyle(.secondary)
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
            .background(Color.black.opacity(0.05))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .padding(.top, 10)
        }
        .hubHeroCard()
    }
}

/// The hero's green primary action ("开始" / "继续第 N 洞").
struct HubPrimaryPill: View {
    let title: String
    var fullWidth: Bool = false

    var body: some View {
        Text(title)
            .font(.headline)
            .foregroundStyle(.white)
            .lineLimit(1)
            .padding(.horizontal, 28)
            .padding(.vertical, 12)
            .frame(maxWidth: fullWidth ? .infinity : nil)
            .background(LiveHoleStyle.green)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

/// 结束 beside 继续 on the in-progress card: opens the finish page (保存并结束 / 继续打球 / 放弃本场).
struct HubEndRoundPill: View {
    static let width: CGFloat = 76
    static let reservedWidth: CGFloat = width + 10

    var body: some View {
        Text("结束")
            .font(.headline)
            .foregroundStyle(LiveHoleStyle.green)
            .frame(width: Self.width)
            .padding(.vertical, 12)
            .background(HubStyle.iconTint)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

/// "再打上次那个": the last course with its first loop + tee, one tap starts it.
struct HubReplayLastCard: View {
    let courseName: String
    let startTitle: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.counterclockwise")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(LiveHoleStyle.green)
                .frame(width: 36, height: 36)
                .background(HubStyle.iconTint)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text("再打上次那个")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(courseName)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Text(startTitle)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Image(systemName: "play.fill")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(LiveHoleStyle.green)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .contentShape(Rectangle())
    }
}

/// The hero's secondary text link ("换球场或组合").
struct HubSecondaryLinkLabel: View {
    let title: String

    var body: some View {
        Text(title)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(LiveHoleStyle.green)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
    }
}

private extension View {
    /// The hero surface: white card, faint green ring, soft green shadow.
    func hubHeroCard() -> some View {
        self
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white)
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(HubStyle.heroBorder, lineWidth: 1))
            .shadow(color: LiveHoleStyle.green.opacity(0.12), radius: 10, x: 0, y: 4)
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
