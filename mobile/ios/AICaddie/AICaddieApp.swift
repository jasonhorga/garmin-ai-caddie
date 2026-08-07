import Combine
import Foundation
import os
import SwiftUI

@main
public struct AICaddieApp: App {
    @StateObject private var model = LiveRoundAppModel()
    @StateObject private var sessionStore = SessionStore.shared
    @Environment(\.scenePhase) private var scenePhase
    @State private var showNoPackageSettings = false
    @State private var usesDarkLiveChrome = false

    public init() {}

    /// Production: everyone signs in with Apple (no admin token / 「本人」 in the product). DEBUG —
    /// the simulator/CI cannot perform a real Apple sign-in — skips the gate so tests keep running
    /// on the existing admin-token / empty path.
    private var requiresSignIn: Bool {
        #if DEBUG
        return false
        #else
        guard let session = sessionStore.currentSession else { return true }
        return session.isExpired
        #endif
    }

    public var body: some Scene {
        WindowGroup {
            Group {
                if requiresSignIn {
                    SignInView(apiBaseURL: model.apiBaseURL) { session in
                        sessionStore.save(session)
                        model.activateSession(session, migrateLegacyData: false)
                        Task { await model.bootstrap() }
                    }
                } else if model.isBootstrapping {
                    ZStack {
                        Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255).ignoresSafeArea()
                        VStack(spacing: 12) {
                            Image(systemName: "flag.checkered").font(.largeTitle).foregroundStyle(LiveHoleStyle.green)
                            ProgressView()
                        }
                    }
                } else if let package = model.package {
                    RoundHomeView(
                        package: package,
                        pendingEventCount: model.pendingEventCount,
                        syncStatus: model.syncStatus,
                        apiBaseURL: model.apiBaseURL,
                        adminToken: model.adminToken,
                        adminTokenConfigured: model.adminTokenConfigured,
                        offlineStore: model.offlineStore,
                        sessionStore: model.garminSessionStore,
                        watchBridge: model.watchBridge,
                        liveRoundState: model.liveRoundState,
                        courseOptions: model.courseOptions,
                        downloadedCourseOptions: model.downloadedCourseOptions,
                        startingNine: model.startingNine,
                        isPreparingRound: model.isPreparingRound,
                        isFinishingRound: model.isFinishingRound,
                        finishErrorMessage: model.finishErrorMessage,
                        onEvent: model.handleEvent,
                        onPrepareRound: { roundId in
                            Task {
                                await model.prepareRound(roundId: roundId)
                            }
                        },
                        onPrepareCourseRound: { globalId, roundId, teeBox, nine in
                            Task {
                                await model.prepareCourseRound(globalId: globalId, roundId: roundId, teeBox: teeBox, nine: nine)
                            }
                        },
                        onPrepareCompositeRound: { globalId, backGlobalId, teeBox, roundId in
                            Task {
                                await model.prepareCompositeRound(globalId: globalId, backGlobalId: backGlobalId, roundId: roundId, teeBox: teeBox)
                            }
                        },
                        onChangeNine: { nine in
                            Task {
                                await model.setActiveNine(nine)
                            }
                        },
                        onFinishRound: {
                            return await model.finishActiveRound()
                        },
                        onSetActiveHole: { hole in
                            model.setActiveHole(hole)
                        },
                        onSync: {
                            Task {
                                await model.syncPendingEvents()
                            }
                        },
                        onSaveBackendConfiguration: { apiBaseURLText, adminTokenText in
                            Task {
                                await model.saveBackendConfiguration(apiBaseURLText: apiBaseURLText, adminTokenText: adminTokenText)
                            }
                        },
                        onClearBackendConfiguration: {
                            Task {
                                await model.clearBackendConfiguration()
                            }
                        },
                        onLoadCourseTees: { globalId in await model.loadCourseTees(globalId: globalId) },
                        onSearchCourses: { name, latitude, longitude in
                            try await model.searchCourses(name: name, latitude: latitude, longitude: longitude)
                        },
                        onNearbyCourses: { latitude, longitude, radiusKm in
                            try await model.nearbyCourses(
                                latitude: latitude,
                                longitude: longitude,
                                radiusKm: radiusKm
                            )
                        },
                        pendingLiveHole: model.pendingLiveHole,
                        onConsumePendingLiveHole: {
                            model.consumePendingLiveHole()
                        },
                        onLiveAppearanceChanged: { isLive in
                            usesDarkLiveChrome = isLive
                        }
                    )
                } else {
                    NavigationStack {
                        StartRoundView(
                            courseOptions: model.courseOptions,
                            downloadedCourseOptions: model.downloadedCourseOptions,
                            syncStatus: model.syncStatus,
                            isPreparing: model.isPreparingRound,
                            apiBaseURL: model.apiBaseURL,
                            adminTokenConfigured: model.adminTokenConfigured,
                            onPrepareRound: { roundId in
                                Task {
                                    await model.prepareRound(roundId: roundId)
                                }
                            },
                            onPrepareCourseRound: { globalId, roundId, teeBox, nine in
                                Task {
                                    await model.prepareCourseRound(globalId: globalId, roundId: roundId, teeBox: teeBox, nine: nine)
                                }
                            },
                            onPrepareCompositeRound: { globalId, backGlobalId, teeBox, roundId in
                                Task {
                                    await model.prepareCompositeRound(globalId: globalId, backGlobalId: backGlobalId, roundId: roundId, teeBox: teeBox)
                                }
                            },
                            onSaveBackendConfiguration: { apiBaseURLText, adminTokenText in
                                Task {
                                    await model.saveBackendConfiguration(apiBaseURLText: apiBaseURLText, adminTokenText: adminTokenText)
                                }
                            },
                            onClearBackendConfiguration: {
                                Task {
                                    await model.clearBackendConfiguration()
                                }
                            },
                            onConnectGarmin: { showNoPackageSettings = true },
                            onLoadCourseTees: { globalId in await model.loadCourseTees(globalId: globalId) },
                            onSearchCourses: { name, latitude, longitude in
                                try await model.searchCourses(name: name, latitude: latitude, longitude: longitude)
                            },
                            onNearbyCourses: { latitude, longitude, radiusKm in
                                try await model.nearbyCourses(
                                    latitude: latitude,
                                    longitude: longitude,
                                    radiusKm: radiusKm
                                )
                            }
                        )
                        // First launch with no data: the empty-state CTA + this gear both open the
                        // Garmin-connect sheet so a signed-in user can pull their courses and score.
                        .toolbar {
                            ToolbarItem(placement: .topBarTrailing) {
                                Button { showNoPackageSettings = true } label: { Image(systemName: "gearshape") }
                            }
                        }
                        .sheet(isPresented: $showNoPackageSettings) {
                            noPackageSettingsSheet
                        }
                    }
                }
            }
            // Product chrome is light except for the immersive live-hole instrument. Drive the
            // presentation-level scheme here (rather than from the destination child) because the
            // hosting controller owns status-bar contrast for the whole NavigationStack.
            .preferredColorScheme(usesDarkLiveChrome ? .dark : .light)
            .task {
                #if DEBUG
                await model.bootstrap()
                #else
                if let session = sessionStore.currentSession {
                    model.activateSession(session, migrateLegacyData: true)
                    await model.bootstrap()
                }
                #endif
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    model.syncOnForeground()
                }
            }
        }
    }

    /// 无数据首启时的 sheet(用户已用 Apple 登录):连接 Garmin 拉取球场,或直接开始记分。
    private var noPackageSettingsSheet: some View {
        NavigationStack {
            List {
                Section {
                    NavigationLink {
                        GarminSessionView(apiBaseURL: model.apiBaseURL, adminToken: model.adminToken, sessionStore: model.garminSessionStore)
                    } label: {
                        Label("连接 Garmin", systemImage: "link")
                    }
                    Button {
                        Task { await model.bootstrap() }
                        showNoPackageSettings = false
                    } label: {
                        Label("开始记分", systemImage: "flag.checkered")
                    }
                    .foregroundStyle(LiveHoleStyle.green)
                } header: {
                    Text("打球")
                } footer: {
                    Text("连接 Garmin 会自动拉取你的球场和历史;连接好后点「开始记分」,用手机就能记分。")
                }
            }
            .navigationTitle("开始")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { showNoPackageSettings = false }
                }
            }
        }
    }
}

private enum LiveRoundFinishError: Error {
    case incompleteAcknowledgement
}

private struct OfflineTopoDownloadResult: Sendable {
    let globalId: Int
    let localHole: Int
    let data: Data?
    let errorDescription: String?
}

private struct OfflinePrepBatchRequest: Sendable {
    let globalId: Int
    let localHoles: [Int]
}

private struct OfflinePrepBatchResult: @unchecked Sendable {
    let request: OfflinePrepBatchRequest
    let holes: [CoursePrepHole]
    let errorDescription: String?
}

private struct OfflineDownloadClient: @unchecked Sendable {
    let value: SyncClient
}

@MainActor
public final class LiveRoundAppModel: ObservableObject {
    @Published public private(set) var package: LiveRoundPackage?
    @Published public private(set) var pendingEventCount: Int = 0
    @Published public private(set) var syncStatus: String = "离线就绪"
    @Published public private(set) var apiBaseURL: URL?
    @Published public private(set) var adminToken: String?
    @Published public private(set) var isPreparingRound = false
    @Published public private(set) var isFinishingRound = false
    @Published public private(set) var finishErrorMessage: String?
    /// True until the first bootstrap() resolves, so the root shows a loading state instead of
    /// flashing the 开始一场 form before the home package lands.
    @Published public private(set) var isBootstrapping = true
    /// When a NEW round is freshly prepared, the hole to jump straight into (so 开始记分 enters
    /// the live screen directly instead of bouncing back to the Hub). UI consumes + clears it.
    @Published public private(set) var pendingLiveHole: Int?

    public func consumePendingLiveHole() {
        pendingLiveHole = nil
    }
    @Published public private(set) var liveRoundState: LiveRoundStateSnapshot?
    @Published public private(set) var courseOptions: [MobileCourseOption] = []
    @Published public private(set) var downloadedCourseOptions: [MobileCourseOption] = []
    /// 本局的起始九洞(用于「移除另外 9 洞」撤销目标);随新 roundId 重置。
    @Published public private(set) var startingNine: String?
    public let watchBridge: WatchEventBridge?
    public let offlineStore: OfflineStore
    public let garminSessionStore: GarminSessionStore?

    private var syncClient: SyncClient?
    private var mediaUploadClient: MediaUploadClient?
    private var isSyncingPendingEvents = false
    private var offlineCourseDownloadTask: Task<Void, Never>?
    private var roundPreparationToken: UUID?
    private var courseOptionsRefreshSucceeded = false
    private var boundPlayerId: String?
    private let preferredRoundId: String
    private let offlineGeometryRetryDelaysNanoseconds: [UInt64]
    /// Keeps the Apple-session observer alive so the watch's standalone-sync auth tracks sign-in /
    /// refresh / sign-out (round-13 watch-auth).
    private var sessionCancellables = Set<AnyCancellable>()

    public convenience init(
        offlineStore: OfflineStore = OfflineStore(),
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        garminSessionStore: GarminSessionStore? = GarminSessionStore(),
        preferredRoundId: String? = nil,
        syncClient: SyncClient? = nil,
        offlineGeometryRetryDelaysNanoseconds: [UInt64] = [
            5_000_000_000, 10_000_000_000, 20_000_000_000, 40_000_000_000,
            60_000_000_000, 60_000_000_000, 60_000_000_000,
        ]
    ) {
        self.init(
            offlineStore: offlineStore,
            apiBaseURL: apiBaseURL,
            adminToken: adminToken,
            watchBridge: WatchEventBridge(offlineStore: offlineStore, autoActivate: false),
            garminSessionStore: garminSessionStore,
            preferredRoundId: preferredRoundId,
            syncClient: syncClient,
            offlineGeometryRetryDelaysNanoseconds: offlineGeometryRetryDelaysNanoseconds
        )
    }

    public init(
        offlineStore: OfflineStore = OfflineStore(),
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        watchBridge: WatchEventBridge?,
        garminSessionStore: GarminSessionStore? = GarminSessionStore(),
        preferredRoundId: String? = nil,
        syncClient: SyncClient? = nil,
        offlineGeometryRetryDelaysNanoseconds: [UInt64] = [
            5_000_000_000, 10_000_000_000, 20_000_000_000, 40_000_000_000,
            60_000_000_000, 60_000_000_000, 60_000_000_000,
        ]
    ) {
        let resolvedAPIBaseURL = apiBaseURL ?? Self.defaultAPIBaseURL()
        let resolvedAdminToken = adminToken ?? Self.defaultAdminToken()
        self.offlineStore = offlineStore
        self.apiBaseURL = resolvedAPIBaseURL
        self.adminToken = resolvedAdminToken
        self.watchBridge = watchBridge
        self.garminSessionStore = garminSessionStore
        self.preferredRoundId = preferredRoundId ?? Self.defaultLiveRoundId()
        self.offlineGeometryRetryDelaysNanoseconds = offlineGeometryRetryDelaysNanoseconds
        self.syncClient = syncClient ?? resolvedAPIBaseURL.map { SyncClient(baseURL: $0, adminToken: resolvedAdminToken) }
        self.mediaUploadClient = resolvedAPIBaseURL.map {
            MediaUploadClient(baseURL: $0, adminToken: resolvedAdminToken)
        }
        watchBridge?.onAcceptedLiveEvent = { [weak self] event in
            guard let self else {
                return
            }
            try await self.acceptWatchEvent(event)
        }
        watchBridge?.activateSession()
        syncConfigToWatch()
        observeSessionForWatch()
        refreshDownloadedCourseOptions()
    }

    /// round-12 P3.4 (Watch standalone): hand the watch this phone's backend config so a standalone
    /// round can sync on its own. The bridge stores it and re-pushes once the WCSession activates.
    ///
    /// round-13 watch-auth: forward the LIVE Apple session token (and its expiry) so the watch's
    /// standalone sync uses a member/owner Bearer instead of the admin token. A nil token (signed out)
    /// clears the watch's Bearer; the admin token stays only as the DEBUG/CI fallback.
    private func syncConfigToWatch() {
        guard let apiBaseURL else {
            return
        }
        let session = SessionStore.shared.currentSession
        watchBridge?.sendConfigToWatch(
            apiBaseURL: apiBaseURL.absoluteString,
            adminToken: adminToken,
            sessionToken: session?.token,
            sessionTokenExpiresAt: session?.expiresAt
        )
    }

    /// round-13 watch-auth: re-push backend config to the watch whenever the Apple session changes
    /// (sign-in / refresh / sign-out), so the watch's standalone sync always carries the CURRENT
    /// member/owner Bearer — or clears it on sign-out. `dropFirst` skips the initial published value;
    /// the explicit `syncConfigToWatch()` in init already delivered it.
    private func observeSessionForWatch() {
        SessionStore.shared.$currentSession
            .dropFirst()
            .sink { [weak self] _ in
                Task { @MainActor in
                    self?.syncConfigToWatch()
                }
            }
            .store(in: &sessionCancellables)
    }

    public var defaultRoundId: String {
        preferredRoundId
    }

    public var adminTokenConfigured: Bool {
        adminToken?.isEmpty == false
    }

    /// Bind all personal offline state before a production bootstrap. A new account starts with an
    /// empty in-memory model and its own disk scope, while immutable course topo images remain
    /// reusable. This must run synchronously after sign-in so bootstrap cannot see another member's
    /// cached package, bag or history.
    public func activateSession(_ session: AppSession, migrateLegacyData: Bool) {
        guard boundPlayerId != session.playerId else {
            syncConfigToWatch()
            return
        }
        offlineCourseDownloadTask?.cancel()
        offlineCourseDownloadTask = nil
        roundPreparationToken = nil
        isPreparingRound = false
        offlineStore.bindAccount(
            playerId: session.playerId,
            migrateLegacyData: migrateLegacyData
        )
        boundPlayerId = session.playerId
        package = nil
        liveRoundState = nil
        pendingEventCount = 0
        pendingLiveHole = nil
        startingNine = nil
        courseOptions = []
        courseOptionsRefreshSucceeded = false
        syncStatus = "离线就绪"
        isBootstrapping = true
        refreshDownloadedCourseOptions()
        syncConfigToWatch()
    }

    public func bootstrap() async {
        defer { isBootstrapping = false }
        #if DEBUG
        // A deterministic, backend-free two-hole round for the phone scoring XCUITest. Force it
        // before cache bootstrap so another UI test's real-course cache cannot change what failure
        // the scoring regression test observes. This path is not compiled into Release/TestFlight.
        if ProcessInfo.processInfo.environment["UITEST_FORCE_SCORING_FIXTURE"] == "1" {
            do {
                let fixture = try loadScoringUITestFixture()
                try? offlineStore.discardRound(roundId: fixture.roundId)
                try offlineStore.saveRoundPackage(fixture)
                try activatePackage(fixture, status: "离线记分测试")
            } catch {
                AICaddieLog.storage.error("Scoring UI fixture failed: \(String(describing: error), privacy: .public)")
            }
            return
        }
        #endif
        // Phase 1 — INSTANT (no network): show a cached package so the menu appears immediately.
        // This is the fix for slow startup — we never block the menu on a network package build.
        do {
            if let active = try offlineStore.loadResumablePackage(),
               active.dataMode != "fixture",
               active.course.globalId != 0,
               try offlineStore.hasRecordedEvents(roundId: active.roundId) {
                try activatePackage(active, status: "继续进行中的球局")
                isBootstrapping = false
            } else if let cachedHome = try offlineStore.loadHomePackage() {
                try activateHomePackage(cachedHome, status: "主页就绪(缓存)")
                isBootstrapping = false
            }
        } catch {
            // Phase 2 will populate (or fall back); record why the cache bootstrap was skipped (P1-11).
            AICaddieLog.storage.info("Phase-1 cache bootstrap skipped: \(String(describing: error), privacy: .public)")
        }

        // Phase 2 — BACKGROUND refresh (network): course options + a fresh active/home package.
        // Runs after the menu is already on screen (when a cache existed), so it never delays it.
        await refreshCourseOptions()
        do {
            // RESUME an in-progress round first — recorded holes must never be lost/clobbered.
            if let active = try offlineStore.loadResumablePackage(),
               active.dataMode != "fixture",
               active.course.globalId != 0,
                try offlineStore.hasRecordedEvents(roundId: active.roundId) {
                try activatePackage(active, status: "继续进行中的球局")
                if courseOptionsRefreshSucceeded {
                    beginOfflineCourseDownload()
                }
                return
            }
            #if DEBUG
            // Keep the legacy preferred-round shortcut for interactive DEBUG builds. Real-flow UI
            // tests must exercise the normal home -> choose course -> start path instead of silently
            // activating the implicit 900001 round.
            if ProcessInfo.processInfo.environment["UITEST_MODE"] != "1",
               let remotePackage = await fetchRemotePackage() {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "Remote package cached")
                return
            }
            #endif
            // No in-progress round → land on the Hub with a fresh home package (most-played course).
            // Guard: never overwrite a round Phase 1 already resumed (activateHomePackage nils
            // liveRoundState). If Phase 1 restored an active round, keep it and skip the home swap.
            if let home = await fetchHomePackage() {
                guard liveRoundState == nil else { return }
                try activateHomePackage(home, status: "主页就绪")
                return
            }
            #if DEBUG
            let fixture = try loadFixturePackage()
            try offlineStore.saveRoundPackage(fixture)
            try activatePackage(fixture, status: "Fixture package cached")
            #endif
            // Truly offline first launch (no network, no cache): package stays nil → 开始一场 fallback.
        } catch {
            AICaddieLog.network.error("Offline package bootstrap failed: \(String(describing: error), privacy: .public)")
            syncStatus = "离线数据暂不可用,稍后重试"
        }
    }

    public func refreshCourseOptions() async {
        courseOptionsRefreshSucceeded = false
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            courseOptions = []
            return
        }
        #endif
        guard let syncClient else {
            return
        }
        do {
            courseOptions = try await syncClient.fetchCourseOptions().courses
            courseOptionsRefreshSucceeded = true
        } catch {
            AICaddieLog.network.error("Course options fetch failed: \(String(describing: error), privacy: .public)")
            courseOptions = []
        }
    }

    public func saveBackendConfiguration(apiBaseURLText: String, adminTokenText: String?) async {
        guard let resolvedAPIBaseURL = BackendConfigurationStore.normalizedAPIBaseURL(from: apiBaseURLText) else {
            syncStatus = "地址无效(需 https)"
            return
        }
        BackendConfigurationStore.saveAPIBaseURL(resolvedAPIBaseURL)
        let nextAdminToken: String?
        if let adminTokenText, let sanitizedAdminToken = Self.sanitizedConfigurationValue(adminTokenText) {
            BackendConfigurationStore.saveAdminToken(sanitizedAdminToken)
            nextAdminToken = sanitizedAdminToken
        } else {
            nextAdminToken = adminToken ?? Self.defaultAdminToken()
        }
        applyBackendConfiguration(apiBaseURL: resolvedAPIBaseURL, adminToken: nextAdminToken)
        syncStatus = "已保存"
        await refreshCourseOptions()
    }

    public func clearBackendConfiguration() async {
        BackendConfigurationStore.saveAPIBaseURL(nil)
        BackendConfigurationStore.saveAdminToken(nil)
        let resolvedAPIBaseURL = Self.defaultAPIBaseURL(includePersisted: false)
        let resolvedAdminToken = Self.defaultAdminToken(includePersisted: false)
        applyBackendConfiguration(apiBaseURL: resolvedAPIBaseURL, adminToken: resolvedAdminToken)
        syncStatus = resolvedAPIBaseURL == nil ? "已切换为离线" : "已恢复默认服务器"
        await refreshCourseOptions()
    }

    /// Start owns the preparation generation.  A previous course's long package request may finish
    /// after the player has chosen another course; it must neither replace the new selection nor turn
    /// off the new request's spinner.  Its separate offline map download is cancelled immediately so
    /// server/network capacity follows the latest explicit choice.
    private func beginRoundPreparation() -> UUID {
        let token = UUID()
        roundPreparationToken = token
        offlineCourseDownloadTask?.cancel()
        offlineCourseDownloadTask = nil
        isPreparingRound = true
        return token
    }

    private func isCurrentRoundPreparation(_ token: UUID) -> Bool {
        roundPreparationToken == token
    }

    private func finishRoundPreparation(_ token: UUID) {
        guard roundPreparationToken == token else { return }
        roundPreparationToken = nil
        isPreparingRound = false
    }

    public func prepareRound(roundId: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "无法开始这一场,请重试"
            return
        }
        let preparedAt = Date()
        let preparationToken = beginRoundPreparation()
        defer { finishRoundPreparation(preparationToken) }

        do {
            let fetched = await fetchRemotePackage(
                roundId: requestedRoundId,
                capturedAt: preparedAt,
                preparationToken: preparationToken
            )
            guard isCurrentRoundPreparation(preparationToken) else { return }
            if let remotePackage = fetched {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "已下载离线")
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                switch cachedPackage.cacheState() {
                case .expired:
                    if try canContinueExpiredPackage(cachedPackage) {
                        try activatePackage(cachedPackage, status: "离线继续本场")
                        return
                    }
                    syncStatus = "离线数据已过期,稍后重试"
                case .stale:
                    try activatePackage(cachedPackage, status: "已下载离线")
                    return
                case .ready:
                    try activatePackage(cachedPackage, status: "已下载离线")
                    return
                case .degraded:
                    try activatePackage(cachedPackage, status: "已下载离线")
                    return
                }
            } else {
                syncStatus = "暂时无法开始,稍后重试"
            }
        } catch {
            AICaddieLog.network.error("Round package prepare failed: \(String(describing: error), privacy: .public)")
            syncStatus = "开始失败,稍后重试"
        }
    }

    public func prepareCourseRound(globalId: Int, roundId: String, teeBox: String, nine: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "无法开始这一场,请重试"
            return
        }
        let preparationToken = beginRoundPreparation()
        defer { finishRoundPreparation(preparationToken) }
        // A home package can deliberately retain the last course/round id while no round is active.
        // `liveRoundState`, not package identity, therefore decides whether Start must enter hole 1.
        // The same active round's 加打/移除九洞 keeps its identity and does not re-enter as a new one.
        let isNewRound = liveRoundState?.roundId != requestedRoundId
        if isNewRound {
            startingNine = (nine == "all") ? nil : nine
        }
        let preparedAt = Date()

        do {
            let fetched = await fetchRemoteCoursePackage(
                globalId: globalId,
                roundId: requestedRoundId,
                teeBox: teeBox,
                nine: nine,
                capturedAt: preparedAt,
                preparationToken: preparationToken
            )
            guard isCurrentRoundPreparation(preparationToken) else { return }
            if let remotePackage = fetched {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "球场已就绪")
                if isNewRound {
                    signalFreshRoundEntry(cacheOfflineAssets: true)
                } else {
                    // 加打另外九洞 changes the package in place but still needs the newly selected
                    // holes retained. beginRoundPreparation cancelled the superseded download above.
                    beginOfflineCourseDownload()
                }
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                // Persist the active-round pointer for the offline/cached start too, so a round
                // started without network still resumes on relaunch (continue card survives quit).
                try offlineStore.saveRoundPackage(cachedPackage)
                try activatePackage(cachedPackage, status: "已下载离线")
                if isNewRound {
                    signalFreshRoundEntry()
                } else {
                    beginOfflineCourseDownload()
                }
            } else if let template = try offlineStore.loadCourseTemplate(
                globalId: globalId,
                teeBox: teeBox,
                nine: nine
            ) {
                let offlinePackage = template.rebasedForOfflineStart(
                    roundId: requestedRoundId,
                    generatedAt: preparedAt
                )
                try offlineStore.saveRoundPackage(offlinePackage)
                try activatePackage(offlinePackage, status: "离线球场已就绪")
                if isNewRound {
                    signalFreshRoundEntry()
                } else {
                    beginOfflineCourseDownload()
                }
            } else {
                syncStatus = "暂时无法开始,稍后重试"
            }
        } catch {
            AICaddieLog.network.error("Course package prepare failed: \(String(describing: error), privacy: .public)")
            syncStatus = "开始失败,稍后重试"
        }
    }

    /// After a fresh round is prepared, point the UI at its first hole so it enters the live screen.
    private func signalFreshRoundEntry(cacheOfflineAssets: Bool = false) {
        pendingLiveHole = liveRoundState?.activeHole ?? package?.holes.first?.number
        if cacheOfflineAssets {
            // This pipeline downloads every topo itself. Running the server-wide prewarmer at the
            // same time makes both jobs parse/render the same 18 holes and, on a four-core server,
            // more than doubles the time before the course is actually available offline.
            beginOfflineCourseDownload()
        }
    }

    /// Keep start latency low, then make the selected course genuinely reusable without a network:
    /// retain every hole's lightweight route/hazard/F-M-B facts and its precise topo bitmap. The
    /// package identity remains the live round's; the course template and bitmap keys are static.
    private func beginOfflineCourseDownload() {
        guard var snapshot = package, let syncClient else { return }
        if let retained = try? offlineStore.loadCourseTemplate(
            globalId: snapshot.course.globalId,
            teeBox: snapshot.course.teeBox,
            nine: snapshot.nine ?? "all"
        ), retained.hasCompleteOfflineCoursePrep {
            snapshot = snapshot.replacingCoursePrep(retained.coursePrep)
        }
        let downloadSnapshot = snapshot
        offlineCourseDownloadTask?.cancel()
        offlineCourseDownloadTask = Task { [weak self] in
            await self?.downloadOfflineCourseAssets(for: downloadSnapshot, using: syncClient)
        }
    }

    private func offlinePrepKey(globalId: Int, localHole: Int) -> String {
        "\(globalId):\(localHole)"
    }

    private func offlinePrepIsPrecise(_ prep: CoursePrepHole?) -> Bool {
        guard let prep, prep.resolvedMapOverlay != nil else { return false }
        return prep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame
    }

    /// Course prep cost grows non-linearly when one request parses all 18 large meshes. Keep the
    /// first playing hole as its own highest-priority request (the live view asks for the same key,
    /// so the backend singleflight can share it), then fetch the rest in small bounded batches.
    private func fetchOfflinePrepBatches(
        _ requests: [OfflinePrepBatchRequest],
        using syncClient: SyncClient,
        maximumConcurrentRequests: Int = 3
    ) async -> [OfflinePrepBatchResult] {
        guard !requests.isEmpty else { return [] }
        let client = OfflineDownloadClient(value: syncClient)
        let limit = max(1, min(maximumConcurrentRequests, requests.count))
        return await withTaskGroup(
            of: OfflinePrepBatchResult.self,
            returning: [OfflinePrepBatchResult].self
        ) { group in
            var iterator = requests.makeIterator()
            var results: [OfflinePrepBatchResult] = []
            results.reserveCapacity(requests.count)
            let fetch: @Sendable (OfflinePrepBatchRequest) async -> OfflinePrepBatchResult = { request in
                do {
                    let response = try await client.value.fetchCoursePrep(
                        globalId: request.globalId,
                        holes: request.localHoles,
                        render: false
                    )
                    return OfflinePrepBatchResult(
                        request: request,
                        holes: response.holes,
                        errorDescription: nil
                    )
                } catch {
                    return OfflinePrepBatchResult(
                        request: request,
                        holes: [],
                        errorDescription: String(describing: error)
                    )
                }
            }

            for _ in 0..<limit {
                if let request = iterator.next() {
                    group.addTask { await fetch(request) }
                }
            }
            while let result = await group.next() {
                results.append(result)
                if !Task.isCancelled, let request = iterator.next() {
                    group.addTask { await fetch(request) }
                }
            }
            return results
        }
    }

    /// Fetch topo PNGs with a bounded concurrency window. The offline caller deliberately invokes
    /// this one hole at a time: a cold topo render is CPU-heavy, and four simultaneous renders made
    /// interactive nearby/search/map requests wait behind the background course download. Returning
    /// after each hole also lets the caller persist that bitmap before a process death.
    private func fetchOfflineTopoImages(
        _ holes: [(globalId: Int, localHole: Int)],
        using syncClient: SyncClient,
        maximumConcurrentRequests: Int = 1
    ) async -> [OfflineTopoDownloadResult] {
        guard !holes.isEmpty else { return [] }
        let client = OfflineDownloadClient(value: syncClient)
        let limit = max(1, min(maximumConcurrentRequests, holes.count))
        return await withTaskGroup(
            of: OfflineTopoDownloadResult.self,
            returning: [OfflineTopoDownloadResult].self
        ) { group in
            var iterator = holes.makeIterator()
            var results: [OfflineTopoDownloadResult] = []
            results.reserveCapacity(holes.count)
            let fetch: @Sendable ((globalId: Int, localHole: Int)) async -> OfflineTopoDownloadResult = { hole in
                do {
                    let data = try await client.value.fetchTopoImage(
                        globalId: hole.globalId,
                        localHole: hole.localHole
                    )
                    return OfflineTopoDownloadResult(
                        globalId: hole.globalId,
                        localHole: hole.localHole,
                        data: data,
                        errorDescription: nil
                    )
                } catch {
                    return OfflineTopoDownloadResult(
                        globalId: hole.globalId,
                        localHole: hole.localHole,
                        data: nil,
                        errorDescription: String(describing: error)
                    )
                }
            }

            for _ in 0..<limit {
                if let hole = iterator.next() {
                    group.addTask { await fetch(hole) }
                }
            }
            while let result = await group.next() {
                results.append(result)
                if !Task.isCancelled, let hole = iterator.next() {
                    group.addTask { await fetch(hole) }
                }
            }
            return results
        }
    }

    private func downloadOfflineCourseAssets(
        for snapshot: LiveRoundPackage,
        using syncClient: SyncClient
    ) async {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return
        }
        #endif
        var prepBySource: [String: CoursePrepHole] = [:]

        // Preserve any facts already embedded in an older/full package before fetching only gaps.
        for roundHole in snapshot.holes {
            guard let existing = snapshot.coursePrep?.holes.first(where: {
                $0.hole == roundHole.number
            }) else { continue }
            let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
            let localHole = roundHole.sourceLocalHole ?? roundHole.number
            prepBySource[offlinePrepKey(globalId: globalId, localHole: localHole)] = existing
        }

        let groups = Dictionary(grouping: snapshot.holes) { hole in
            hole.sourceGlobalId ?? snapshot.course.globalId
        }
        var orderedGlobalIds: [Int] = []
        for hole in snapshot.holes {
            let globalId = hole.sourceGlobalId ?? snapshot.course.globalId
            if !orderedGlobalIds.contains(globalId) {
                orderedGlobalIds.append(globalId)
            }
        }
        var geometryReadyKeys = Set(prepBySource.compactMap { key, prep in
            offlinePrepIsPrecise(prep) ? key : nil
        })
        let retryDelays = offlineGeometryRetryDelaysNanoseconds
        for attempt in 0...retryDelays.count {
            var batchRequests: [OfflinePrepBatchRequest] = []
            for globalId in orderedGlobalIds {
                guard !Task.isCancelled else { return }
                guard let roundHoles = groups[globalId] else { continue }
                let localHoles = Array(Set(roundHoles.map {
                    $0.sourceLocalHole ?? $0.number
                })).sorted()
                let requested = localHoles.filter { localHole in
                    let key = offlinePrepKey(globalId: globalId, localHole: localHole)
                    let prep = prepBySource[key]
                    // Fetch missing lightweight facts immediately.  Once a partial response exists,
                    // wait on the cheap coverage endpoint and rebuild it exactly once when geometry
                    // becomes ready instead of repeatedly paying for the same partial prep.
                    return prep?.resolvedMapOverlay == nil
                        || (geometryReadyKeys.contains(key) && !offlinePrepIsPrecise(prep))
                }
                guard !requested.isEmpty else { continue }
                // The playing group's first hole is deliberately a singleton. Remaining requests
                // use three-hole batches: production measurements were ~7s/3 holes versus ~138s/18.
                batchRequests.append(OfflinePrepBatchRequest(
                    globalId: globalId,
                    localHoles: [requested[0]]
                ))
                var index = 1
                while index < requested.count {
                    let end = min(index + 3, requested.count)
                    batchRequests.append(OfflinePrepBatchRequest(
                        globalId: globalId,
                        localHoles: Array(requested[index..<end])
                    ))
                    index = end
                }
            }

            let batchResults = await fetchOfflinePrepBatches(batchRequests, using: syncClient)
            guard !Task.isCancelled else { return }
            for result in batchResults {
                if let errorDescription = result.errorDescription {
                    let holeList = result.request.localHoles.map(String.init).joined(separator: ",")
                    AICaddieLog.network.error(
                        "Offline course facts download failed for \(result.request.globalId, privacy: .public)/\(holeList, privacy: .public): \(errorDescription, privacy: .public)"
                    )
                }
                for prep in result.holes {
                    let key = offlinePrepKey(
                        globalId: result.request.globalId,
                        localHole: prep.hole
                    )
                    prepBySource[key] = prep
                    if offlinePrepIsPrecise(prep) {
                        geometryReadyKeys.insert(key)
                    }
                }
            }
            let unresolvedByGlobalId = orderedGlobalIds.reduce(
                into: [Int: [Int]]()
            ) { unresolved, globalId in
                guard let roundHoles = groups[globalId] else { return }
                let localHoles = Array(Set(roundHoles.map {
                    $0.sourceLocalHole ?? $0.number
                })).sorted()
                let missing = localHoles.filter { localHole in
                    !offlinePrepIsPrecise(prepBySource[
                        offlinePrepKey(globalId: globalId, localHole: localHole)
                    ])
                }
                if !missing.isEmpty {
                    unresolved[globalId] = missing
                }
            }
            guard !unresolvedByGlobalId.isEmpty, attempt < retryDelays.count else { break }
            do {
                try await Task.sleep(nanoseconds: retryDelays[attempt])
            } catch {
                return
            }
            guard !Task.isCancelled else { return }
            for globalId in orderedGlobalIds {
                guard let unresolved = unresolvedByGlobalId[globalId] else { continue }
                do {
                    let coverage = try await syncClient.fetchCourseGeometryCoverage(
                        globalId: globalId,
                        holes: unresolved
                    )
                    for hole in coverage.holes where
                        hole.coverage.caseInsensitiveCompare("ready") == .orderedSame {
                        geometryReadyKeys.insert(offlinePrepKey(
                            globalId: globalId,
                            localHole: hole.localHole
                        ))
                    }
                } catch {
                    AICaddieLog.network.info(
                        "Offline geometry readiness probe deferred for \(globalId, privacy: .public): \(String(describing: error), privacy: .public)"
                    )
                }
                guard !Task.isCancelled else { return }
            }
        }

        let mappedPrep = snapshot.holes.compactMap { roundHole -> CoursePrepHole? in
            let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
            let localHole = roundHole.sourceLocalHole ?? roundHole.number
            return prepBySource[offlinePrepKey(globalId: globalId, localHole: localHole)]?
                .renumbered(to: roundHole.number)
        }
        guard !Task.isCancelled else { return }
        let enriched = snapshot.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: snapshot.course.globalId,
            holes: mappedPrep,
            missingData: mappedPrep.count == snapshot.holes.count
                ? nil
                : [CoursePrepMissingData(
                    label: "offline_course_prep",
                    reason: "\(mappedPrep.count)/\(snapshot.holes.count) hole maps retained"
                )]
        ))

        // Course facts and topo bitmaps have independent durability. Persist the precise per-hole
        // facts before starting the potentially long bitmap pass; otherwise a force-quit after the
        // visible first-hole topo succeeds can restore the old partial package and never select the
        // already-cached precise image. The downloaded-course list still requires every bitmap, so
        // this early save cannot falsely advertise that the whole course is offline-ready.
        do {
            try offlineStore.saveCourseTemplate(enriched)
            if package?.roundId == snapshot.roundId, liveRoundState != nil {
                try offlineStore.saveRoundPackage(enriched)
                package = enriched
            }
        } catch {
            AICaddieLog.storage.error(
                "Offline course facts save failed: \(String(describing: error), privacy: .public)"
            )
        }

        let topoRetryDelays: [UInt64] = [5, 10, 20]
        for attempt in 0...topoRetryDelays.count {
            guard !Task.isCancelled else { return }
            let missingTopoHoles = snapshot.holes.compactMap { roundHole -> (globalId: Int, localHole: Int)? in
                let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
                let localHole = roundHole.sourceLocalHole ?? roundHole.number
                let prep = prepBySource[offlinePrepKey(globalId: globalId, localHole: localHole)]
                guard prep?.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame,
                      offlineStore.loadCourseTopoImageURL(
                          globalId: globalId,
                          localHole: localHole
                      ) == nil else { return nil }
                return (globalId, localHole)
            }
            guard !missingTopoHoles.isEmpty else { break }

            // Persist each hole as soon as it arrives. The previous all-course task group returned
            // only after every cold render completed, so killing the app on hole 1 discarded even a
            // successfully downloaded first bitmap and four renders could starve foreground APIs.
            for hole in missingTopoHoles {
                guard !Task.isCancelled else { return }
                let downloads = await fetchOfflineTopoImages([hole], using: syncClient)
                guard !Task.isCancelled else { return }
                guard let download = downloads.first else { continue }
                guard let data = download.data else {
                    let errorDescription = download.errorDescription ?? "unknown error"
                    AICaddieLog.network.error(
                        "Offline topo download failed for \(download.globalId, privacy: .public)/\(download.localHole, privacy: .public): \(errorDescription, privacy: .public)"
                    )
                    continue
                }
                do {
                    _ = try offlineStore.saveCourseTopoImage(
                        data,
                        globalId: download.globalId,
                        localHole: download.localHole
                    )
                } catch {
                    AICaddieLog.storage.error(
                        "Offline topo cache save failed for \(download.globalId, privacy: .public)/\(download.localHole, privacy: .public): \(String(describing: error), privacy: .public)"
                    )
                }
            }

            let stillMissing = missingTopoHoles.contains { hole in
                offlineStore.loadCourseTopoImageURL(
                    globalId: hole.globalId,
                    localHole: hole.localHole
                ) == nil
            }
            guard stillMissing, attempt < topoRetryDelays.count else { break }
            do {
                try await Task.sleep(nanoseconds: topoRetryDelays[attempt] * 1_000_000_000)
            } catch {
                return
            }
        }

        guard !Task.isCancelled else { return }
        do {
            try offlineStore.saveCourseTemplate(enriched)
            if package?.roundId == snapshot.roundId, liveRoundState != nil {
                try offlineStore.saveRoundPackage(enriched)
                package = enriched
            }
            refreshDownloadedCourseOptions()
            if enriched.hasCompleteOfflineCoursePrep,
               offlineStore.hasCourseTopoImages(for: enriched) {
                syncStatus = "离线地图已准备"
            }
        } catch {
            AICaddieLog.storage.error(
                "Offline course cache save failed: \(String(describing: error), privacy: .public)"
            )
        }
    }

    /// 组合 18 洞:本环(1–9)+ 第二个环(10–18)。两个环各是独立 CourseView 球场,后端合并成一局。
    /// 组合局已是 18 洞,不设「移除九洞」撤销目标(startingNine 保持 nil)。
    public func prepareCompositeRound(globalId: Int, backGlobalId: Int, roundId: String, teeBox: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "无法开始这一场,请重试"
            return
        }
        let preparationToken = beginRoundPreparation()
        defer { finishRoundPreparation(preparationToken) }
        let isNewRound = liveRoundState?.roundId != requestedRoundId
        if isNewRound {
            startingNine = nil
        }
        let preparedAt = Date()
        do {
            let fetched = await fetchRemoteCompositePackage(
                globalId: globalId,
                backGlobalId: backGlobalId,
                roundId: requestedRoundId,
                teeBox: teeBox,
                capturedAt: preparedAt,
                preparationToken: preparationToken
            )
            guard isCurrentRoundPreparation(preparationToken) else { return }
            if let remotePackage = fetched {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "球场已就绪")
                if isNewRound {
                    signalFreshRoundEntry(cacheOfflineAssets: true)
                } else {
                    beginOfflineCourseDownload()
                }
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                // Persist the active-round pointer for the offline/cached start too, so a round
                // started without network still resumes on relaunch (continue card survives quit).
                try offlineStore.saveRoundPackage(cachedPackage)
                try activatePackage(cachedPackage, status: "已下载离线")
                if isNewRound {
                    signalFreshRoundEntry()
                } else {
                    beginOfflineCourseDownload()
                }
            } else {
                syncStatus = "暂时无法开始,稍后重试"
            }
        } catch {
            AICaddieLog.network.error("Course package prepare failed: \(String(describing: error), privacy: .public)")
            syncStatus = "开始失败,稍后重试"
        }
    }

    /// 中途改当前局的起始九洞(加打另外 9 洞 → all,或撤销回起始九洞)。
    /// 同一 roundId 重取并重新激活,已记杆/事件按 roundId 保留(restoreLiveRoundState 重建)。
    public func setActiveNine(_ nine: String) async {
        guard let package, package.course.globalId != 0 else {
            return
        }
        // 首次扩展到 18 洞时,记下当前九洞作为「移除」撤销目标(覆盖 bootstrap 恢复的局)。
        if nine == "all", startingNine == nil {
            let current = package.nine ?? "all"
            startingNine = (current == "all") ? nil : current
        }
        await prepareCourseRound(
            globalId: package.course.globalId,
            roundId: package.roundId,
            teeBox: package.course.teeBox,
            nine: nine
        )
    }

    /// Persist a completed round only after every local event has an explicit server identity ACK
    /// and the idempotent finish endpoint succeeds. Any failure leaves the package, progress and
    /// event log intact so the player can retry or keep playing.
    @discardableResult
    public func finishActiveRound() async -> Bool {
        guard !isFinishingRound, let package else { return false }
        isFinishingRound = true
        finishErrorMessage = nil
        defer { isFinishingRound = false }

        #if DEBUG
        // The real-flow simulator uses a real course package but deliberately keeps synthetic scores
        // off the owner's backend. Reaching this branch still requires the user's explicit Save & End
        // tap; only then may the local test round be cleared.
        if eventSyncSuppressedForUITests {
            do {
                try clearFinishedRoundLocally(roundId: package.roundId)
                return true
            } catch {
                AICaddieLog.storage.error("Test-round cleanup failed: \(String(describing: error), privacy: .public)")
                finishErrorMessage = "本地保存状态不可用，本场已完整保留"
                return false
            }
        }
        #endif

        guard let syncClient else {
            finishErrorMessage = "尚未联网，本场已完整保留"
            syncStatus = "结束失败,稍后重试"
            return false
        }

        // A score tap auto-schedules background sync. Let an already-running batch settle before the
        // finish transaction starts; new background batches are suppressed by isFinishingRound.
        while isSyncingPendingEvents {
            try? await Task.sleep(nanoseconds: 50_000_000)
        }

        do {
            let pending = try offlineStore.loadPendingEvents(roundId: package.roundId)
            if !pending.isEmpty {
                try await postPendingEventsAndRequireFullAcknowledgement(
                    pending,
                    package: package,
                    syncClient: syncClient
                )
            }
            guard try offlineStore.loadPendingEvents(roundId: package.roundId).isEmpty else {
                throw LiveRoundFinishError.incompleteAcknowledgement
            }

            let events = try offlineStore.loadEvents().filter { $0.roundId == package.roundId }
            let completedHoles = Set(events.compactMap { event in
                event.kind == .score && event.hole > 0 ? event.hole : nil
            })
            let metadata = MobileRoundFinishMetadata(
                courseName: package.course.name,
                holePars: package.holes.sorted { $0.number < $1.number }.map(\.par),
                holesCompleted: completedHoles.count,
                courseGlobalId: package.course.globalId
            )
            try await syncClient.finishRound(roundId: package.roundId, metadata: metadata)
            // Finish ingestion updates the acting player's history synchronously. Fetch a fresh home
            // package before clearing the active pointer so the first Hub frame already shows the
            // round that was just saved instead of the package's pre-round `recentHistory` snapshot.
            // A failed refresh is non-fatal: the completed round is already durable server-side and
            // the cached home remains available until the normal next bootstrap refresh.
            let refreshedHome = await fetchHomePackage(preferredCourse: package.course)
            try clearFinishedRoundLocally(roundId: package.roundId)
            if let refreshedHome {
                try activateHomePackage(refreshedHome, status: "本场已保存")
            }
            return true
        } catch {
            AICaddieLog.network.error("Round finish failed: \(String(describing: error), privacy: .public)")
            finishErrorMessage = error is LiveRoundFinishError
                ? "部分记录尚未确认，本场已完整保留"
                : "保存结束失败，本场已完整保留"
            syncStatus = "结束失败,稍后重试"
            pendingEventCount = (try? offlineStore.loadPendingEvents(roundId: package.roundId).count) ?? pendingEventCount
            return false
        }
    }

    private func clearFinishedRoundLocally(roundId: String) throws {
        let homePackage = package
        try offlineStore.discardRound(roundId: roundId)
        if let homePackage {
            try offlineStore.saveHomePackage(homePackage)
        }
        package = homePackage
        liveRoundState = nil
        startingNine = nil
        pendingEventCount = 0
        finishErrorMessage = nil
        syncStatus = "本场已保存"
    }

    public func setActiveHole(_ hole: Int) {
        guard let package, package.holes.contains(where: { $0.number == hole }) else {
            return
        }
        do {
            try offlineStore.saveActiveHole(roundId: package.roundId, hole: hole)
            liveRoundState = try offlineStore.restoreLiveRoundState(roundId: package.roundId, package: package)
            if let watchBridge {
                watchBridge.sendRoundSeedToWatch(
                    watchBridge.makeWatchRoundSeedPayload(package: package, activeHole: hole)
                )
            }
        } catch {
            AICaddieLog.storage.error("Active-hole save failed: \(String(describing: error), privacy: .public)")
            syncStatus = "当前洞保存失败,请重试"
        }
    }

    public func handleEvent(_ event: LiveRoundEvent) {
        do {
            #if DEBUG
            UITestEventLatencyTrace.record("handle.start kind=\(event.kind.rawValue) hole=\(event.hole)")
            #endif
            try offlineStore.appendEvent(event)
            #if DEBUG
            UITestEventLatencyTrace.record("handle.append.end kind=\(event.kind.rawValue) hole=\(event.hole)")
            #endif
            if let package, package.roundId == event.roundId {
                liveRoundState = try offlineStore.restoreLiveRoundState(roundId: event.roundId, package: package)
            }
            #if DEBUG
            UITestEventLatencyTrace.record("handle.restore.end kind=\(event.kind.rawValue) hole=\(event.hole)")
            #endif
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: event.roundId).count
            #if DEBUG
            UITestEventLatencyTrace.record("handle.pending.end kind=\(event.kind.rawValue) hole=\(event.hole) count=\(pendingEventCount)")
            #endif
            syncStatus = "已保存"
            // Real-flow XCUITest reads the owner's real course package/prep/map, then plays the
            // round entirely in the simulator. Keep those events local so visual evidence can use
            // real course data without writing a synthetic score into the owner's backend history.
            if eventSyncSuppressedForUITests {
                #if DEBUG
                UITestEventLatencyTrace.record("handle.return.suppressed kind=\(event.kind.rawValue) hole=\(event.hole)")
                #endif
                return
            }
            // Auto-sync: push to Garmin/backend in the background after each recorded hole, so the
            // player never manages sync manually. Silently no-ops offline (events stay pending and
            // sync on the next event / app foreground).
            Task { await self.syncPendingEvents() }
        } catch {
            AICaddieLog.storage.error("Event save failed: \(String(describing: error), privacy: .public)")
            syncStatus = "保存失败,稍后重试"
        }
    }

    /// Auto-sync hook for app foreground (scenePhase .active): flush anything still pending.
    public func syncOnForeground() {
        guard !eventSyncSuppressedForUITests, package != nil, pendingEventCount > 0 else {
            return
        }
        Task { await self.syncPendingEvents() }
    }

    private var eventSyncSuppressedForUITests: Bool {
        #if DEBUG
        ProcessInfo.processInfo.environment["UITEST_DISABLE_EVENT_SYNC"] == "1"
        #else
        false
        #endif
    }

    public func syncPendingEvents() async {
        guard !isFinishingRound, !isSyncingPendingEvents else { return }
        isSyncingPendingEvents = true
        defer { isSyncingPendingEvents = false }
        guard let package else {
            syncStatus = "没有进行中的球局"
            return
        }
        guard let syncClient else {
            syncStatus = "未联网,稍后同步"
            return
        }

        do {
            let uploadedMediaCount = try await syncPendingMedia(roundId: package.roundId)
            let events = try offlineStore.loadPendingEvents(roundId: package.roundId)
            pendingEventCount = events.count
            if events.isEmpty {
                syncStatus = uploadedMediaCount > 0 ? "已同步 \(uploadedMediaCount) 张照片/视频" : "已是最新"
            } else {
                syncStatus = "同步中…"
                let result = try await postPendingEventsAndRequireFullAcknowledgement(
                    events,
                    package: package,
                    syncClient: syncClient
                )
                pendingEventCount = try offlineStore.loadPendingEvents(roundId: package.roundId).count
                let mediaSuffix = uploadedMediaCount > 0 ? " · \(uploadedMediaCount) 张照片/视频" : ""
                syncStatus = result.duplicate ? "已同步" : "已同步\(mediaSuffix)"
            }
            // round-12 sync spine: ALWAYS pull events authored by OTHER clients (runs even with no
            // local pending events) so a round edited on the watch/web shows up here.
            await pullAndApplyRemoteEvents(roundId: package.roundId)
        } catch {
            AICaddieLog.network.error("Pending-event sync failed: \(String(describing: error), privacy: .public)")
            syncStatus = "同步失败,稍后重试"
        }
    }

    private func postPendingEventsAndRequireFullAcknowledgement(
        _ events: [LiveRoundEvent],
        package: LiveRoundPackage,
        syncClient: SyncClient
    ) async throws -> SyncResult {
        let result = try await syncClient.postEventBatchWithRetry(
            events,
            roundId: package.roundId,
            idempotencyKey: idempotencyKey(roundId: package.roundId, events: events)
        )
        let expected = events.map(\.eventId)
        let acknowledged = result.acceptedEventIds + result.duplicateEventIds
        guard Set(expected).count == expected.count,
              Set(acknowledged) == Set(expected),
              acknowledged.count == expected.count else {
            throw LiveRoundFinishError.incompleteAcknowledgement
        }
        try offlineStore.appendSyncMarker(
            roundId: package.roundId,
            timestamp: ISO8601DateFormatter().string(from: Date()),
            result: result
        )
        return result
    }

    /// round-12 sync spine (gap f): pull events authored by OTHER clients via the replay endpoint and
    /// merge them into the local event log (idempotent by full server identity), then re-project.
    /// Best-effort: a pull failure never fails the push. Today this is a no-op for a single client
    /// (no other clients' events exist); it activates the moment the watch/web write to the same round.
    /// NOTE: re-projection folds by local-log order; cross-client SAME-field ordering uses the
    /// authoritative `GET …/state` projection (round-12 P2.2) — wired here when multi-client lands.
    private func pullAndApplyRemoteEvents(roundId: String) async {
        guard let syncClient, let package, package.roundId == roundId else { return }
        var appliedAny = false
        var cursor: Int? = nil  // nil → server uses THIS client's ack cursor (events since last ack)
        var latestCursor = 0
        for _ in 0..<20 {  // bounded pagination guard
            guard let replay = try? await syncClient.fetchEventReplay(roundId: roundId, afterSequence: cursor, limit: 200) else {
                return
            }
            do {
                let pageAppliedAny = try offlineStore.applyReplayEvents(replay.events.map(\.event))
                appliedAny = appliedAny || pageAppliedAny
            } catch {
                // A missing or conflicting local envelope leaves the whole page unacknowledged.
                // Already-appended prefix events are exact-identity idempotent on the next replay.
                break
            }
            // Only a fully-present or fully-persisted page advances the durable replay cursor.
            latestCursor = replay.nextCursor
            cursor = replay.nextCursor
            if !replay.hasMore { break }
        }
        if latestCursor > 0 {
            _ = try? await syncClient.ackEventCursor(roundId: roundId, serverSequence: latestCursor)
        }
        if appliedAny {
            liveRoundState = try? offlineStore.restoreLiveRoundState(roundId: roundId, package: package)
        }
    }

    public func syncPendingMedia(roundId: String) async throws -> Int {
        guard let mediaUploadClient else {
            return 0
        }
        let pendingMedia = try offlineStore.loadPendingMedia(roundId: roundId)
        var uploadedIds = Set<String>()
        for media in pendingMedia {
            do {
                let mediaData = try Data(contentsOf: media.fileURL)
                let request = MediaCreateRequest(
                    targetType: "hole",
                    targetId: media.targetId,
                    mediaKind: media.mediaKind,
                    fileName: media.fileName,
                    contentBase64: mediaData.base64EncodedString(),
                    capturedAt: media.capturedAt,
                    mimeType: inferredMimeType(fileName: media.fileName, mediaKind: media.mediaKind)
                )
                let uploadResponse = try await mediaUploadClient.uploadMediaWithRetry(request)
                try? await mediaUploadClient.analyzeMedia(mediaId: uploadResponse.media.id)
                uploadedIds.insert(media.id)
            } catch {
                AICaddieLog.network.error("Pending media upload failed: \(String(describing: error), privacy: .public)")
                continue
            }
        }
        try offlineStore.removePendingMedia(ids: uploadedIds)
        return uploadedIds.count
    }

    private func inferredMimeType(fileName: String, mediaKind: String) -> String {
        let lower = fileName.lowercased()
        if mediaKind == "video" {
            if lower.hasSuffix(".mov") {
                return "video/quicktime"
            }
            return "video/mp4"
        }
        if lower.hasSuffix(".png") {
            return "image/png"
        }
        if lower.hasSuffix(".heic") || lower.hasSuffix(".heif") {
            return "image/heic"
        }
        return "image/jpeg"
    }

    private func applyBackendConfiguration(apiBaseURL: URL?, adminToken: String?, preserveInjectedSyncClient: Bool = false) {
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        if !preserveInjectedSyncClient {
            self.syncClient = apiBaseURL.map { SyncClient(baseURL: $0, adminToken: adminToken) }
        }
        self.mediaUploadClient = apiBaseURL.map { MediaUploadClient(baseURL: $0, adminToken: adminToken) }
        syncConfigToWatch()
    }

    private static func defaultAPIBaseURL(includePersisted: Bool = true) -> URL? {
        var candidates: [String?] = [
            ProcessInfo.processInfo.environment["AI_CADDIE_API_BASE_URL"],
        ]
        if includePersisted {
            candidates.append(BackendConfigurationStore.loadAPIBaseURL()?.absoluteString)
        }
        candidates.append(Bundle.main.object(forInfoDictionaryKey: "AICaddieAPIBaseURL") as? String)
        for candidate in candidates {
            guard let resolvedAPIBaseURL = BackendConfigurationStore.normalizedAPIBaseURL(from: candidate) else {
                continue
            }
            return resolvedAPIBaseURL
        }
        return nil
    }

    private static func sanitizedConfigurationValue(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let trimmed, !trimmed.isEmpty, !trimmed.contains("$(") else {
            return nil
        }
        return trimmed
    }

    private static func defaultAdminToken(includePersisted: Bool = true) -> String? {
        // DEBUG/CI ONLY: the admin token is the dev/simulator auth fallback (a real Apple sign-in
        // can't run there). Consumer (Release) builds never load or hold one — they authenticate only
        // via the Apple session — so the whole load path (env / Keychain / Info.plist) is compiled out
        // and Release always resolves a nil admin token.
        #if DEBUG
        if let token = sanitizedConfigurationValue(ProcessInfo.processInfo.environment["AI_CADDIE_ADMIN_TOKEN"]) {
            return token
        }
        if includePersisted, let persisted = BackendConfigurationStore.loadAdminToken() {
            return persisted
        }
        return nil
        #else
        return nil
        #endif
    }

    private static func defaultLiveRoundId() -> String {
        let roundId = ProcessInfo.processInfo.environment["AI_CADDIE_LIVE_ROUND_ID"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let roundId, !roundId.isEmpty {
            return roundId
        }
        return "900001"
    }

    private func fetchRemotePackage(capturedAt: Date = Date()) async -> LiveRoundPackage? {
        guard let syncClient else {
            return nil
        }
        do {
            return try await syncClient.fetchRoundPackage(roundId: preferredRoundId, capturedAt: capturedAt)
        } catch {
            AICaddieLog.network.error("Round package fetch failed (using cache): \(String(describing: error), privacy: .public)")
            syncStatus = "离线中,使用已保存数据"
            return nil
        }
    }

    private func fetchRemotePackage(
        roundId: String,
        capturedAt: Date = Date(),
        preparationToken: UUID? = nil
    ) async -> LiveRoundPackage? {
        guard let syncClient else {
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "未联网,稍后同步"
            }
            return nil
        }
        do {
            return try await syncClient.fetchRoundPackage(roundId: roundId, capturedAt: capturedAt)
        } catch {
            AICaddieLog.network.error("Round package fetch failed (using cache): \(String(describing: error), privacy: .public)")
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "离线中,使用已保存数据"
            }
            return nil
        }
    }

    private func fetchRemoteCoursePackage(
        globalId courseGlobalId: Int,
        roundId: String,
        teeBox: String,
        nine: String = "all",
        capturedAt: Date = Date(),
        preparationToken: UUID? = nil
    ) async -> LiveRoundPackage? {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_COURSE_PACKAGE_FAILURE"] == "1"
            || ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "离线中,使用已保存数据"
            }
            return nil
        }
        #endif
        guard let syncClient else {
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "未联网,稍后同步"
            }
            return nil
        }
        do {
            // A newly generated round has no server events yet. Replay/ACK owns recovery later;
            // scanning the owner's historical event log here only delays the first-hole screen.
            return try await syncClient.fetchCoursePackage(globalId: courseGlobalId, roundId: roundId, teeBox: teeBox, nine: nine, capturedAt: capturedAt, ensureGeometry: false, backgroundGeometry: true, includeEventCursor: false)
        } catch {
            AICaddieLog.network.error("Course package fetch failed (using cache): \(String(describing: error), privacy: .public)")
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "离线中,使用已保存数据"
            }
            return nil
        }
    }

    private func fetchRemoteCompositePackage(
        globalId courseGlobalId: Int,
        backGlobalId: Int,
        roundId: String,
        teeBox: String,
        capturedAt: Date = Date(),
        preparationToken: UUID? = nil
    ) async -> LiveRoundPackage? {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "离线中,使用已保存数据"
            }
            return nil
        }
        #endif
        guard let syncClient else {
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "未联网,稍后同步"
            }
            return nil
        }
        do {
            return try await syncClient.fetchCoursePackage(globalId: courseGlobalId, roundId: roundId, teeBox: teeBox, nine: "all", capturedAt: capturedAt, ensureGeometry: false, backgroundGeometry: true, backGlobalId: backGlobalId, includeEventCursor: false)
        } catch {
            AICaddieLog.network.error("Course package fetch failed (using cache): \(String(describing: error), privacy: .public)")
            if preparationToken == nil || preparationToken == roundPreparationToken {
                syncStatus = "离线中,使用已保存数据"
            }
            return nil
        }
    }

    /// Search the provider-wide catalogue without installing anything. The picker keeps these rows
    /// ephemeral until the player chooses one and starts the existing selected-course download.
    public func searchCourses(
        name: String,
        latitude: Double? = nil,
        longitude: Double? = nil
    ) async throws -> [MobileCourseSearchMatch] {
        prioritizeCourseDiscovery()
        guard let syncClient else { throw URLError(.notConnectedToInternet) }
        return try await syncClient.searchCourses(
            name: name,
            latitude: latitude,
            longitude: longitude
        )
    }

    public func nearbyCourses(
        latitude: Double,
        longitude: Double,
        radiusKm: Int
    ) async throws -> [MobileCourseSearchMatch] {
        prioritizeCourseDiscovery()
        #if DEBUG
        // Real-simulator acceptance seam: keep bootstrap, search and course downloads on the live
        // backend while forcing only the automatic nearby request offline. Release/TestFlight never
        // compile this branch.
        if ProcessInfo.processInfo.environment["UITEST_FORCE_NEARBY_FAILURE"] == "1" {
            throw URLError(.notConnectedToInternet)
        }
        #endif
        guard let syncClient else { throw URLError(.notConnectedToInternet) }
        return try await syncClient.nearbyCourses(
            latitude: latitude,
            longitude: longitude,
            radiusKm: radiusKm
        )
    }

    /// Nearby/name discovery is the player's foreground intent. Stop an older round's best-effort
    /// all-hole cache pass before issuing it so background topo work cannot strand Start Round.
    /// A selected course starts its own download again after preparation.
    private func prioritizeCourseDiscovery() {
        offlineCourseDownloadTask?.cancel()
        offlineCourseDownloadTask = nil
    }

    /// Load the course's selectable tee boxes (GET /courses/{id}/tees) for the 开始一场 picker —
    /// colour + total yards + default. Returns [] offline / on error: known/downloaded courses can
    /// retain their bundled Tee names, while a newly searched course stays gated and exposes an
    /// explicit retry rather than starting with invented Tee authority.
    public func loadCourseTees(globalId: Int) async -> [CourseTee] {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return []
        }
        #endif
        guard let syncClient else { return [] }
        do {
            return try await syncClient.fetchCourseTees(globalId: globalId).tees
        } catch {
            AICaddieLog.network.error("Course tees fetch failed (preserving current course state): \(String(describing: error), privacy: .public)")
            return []
        }
    }

    private func activatePackage(_ nextPackage: LiveRoundPackage, status: String) throws {
        try? offlineStore.saveCourseTemplate(nextPackage)
        refreshDownloadedCourseOptions()
        package = nextPackage
        let restored = try offlineStore.restoreLiveRoundState(roundId: nextPackage.roundId, package: nextPackage)
        try offlineStore.saveActiveHole(roundId: nextPackage.roundId, hole: restored.activeHole)
        liveRoundState = restored
        pendingEventCount = try offlineStore.loadPendingEvents(roundId: nextPackage.roundId).count
        syncStatus = status
        if let watchBridge,
           let activeHole = liveRoundState?.activeHole ?? nextPackage.holes.first?.number {
            let seed = watchBridge.makeWatchRoundSeedPayload(
                package: nextPackage,
                activeHole: activeHole
            )
            watchBridge.sendRoundSeedToWatch(seed)
        }
    }

    /// Activate a HOME/landing package: populate the Hub (course, last round, choices) WITHOUT
    /// marking an active round — liveRoundState stays nil (no 进行中 card) and it is not the
    /// current-round pointer. Cached to home_package.json for offline relaunch.
    private func activateHomePackage(_ nextPackage: LiveRoundPackage, status: String) throws {
        package = nextPackage
        liveRoundState = nil
        startingNine = nil
        pendingEventCount = 0
        try? offlineStore.saveHomePackage(nextPackage)
        refreshDownloadedCourseOptions()
        syncStatus = status
    }

    private func refreshDownloadedCourseOptions() {
        let templates = (try? offlineStore.loadCourseTemplates()) ?? []
        let standalone = templates.filter { package in
            Set(package.holes.map { $0.sourceGlobalId ?? package.course.globalId })
                == Set([package.course.globalId])
                && package.hasCompleteOfflineCoursePrep
                && offlineStore.hasCourseTopoImages(for: package)
        }
        downloadedCourseOptions = Dictionary(grouping: standalone, by: { $0.course.globalId })
            .values
            .compactMap { packages -> MobileCourseOption? in
                let ranked = packages.sorted { lhs, rhs in
                    if lhs.holes.count != rhs.holes.count {
                        return lhs.holes.count > rhs.holes.count
                    }
                    if lhs.geometryCoverage.readyHoles != rhs.geometryCoverage.readyHoles {
                        return lhs.geometryCoverage.readyHoles > rhs.geometryCoverage.readyHoles
                    }
                    return lhs.generatedAt > rhs.generatedAt
                }
                guard let preferred = ranked.first else {
                    return nil
                }
                var seenTees = Set<String>()
                let tees = ranked.compactMap { package -> String? in
                    let tee = package.course.teeBox.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !tee.isEmpty, tee.lowercased() != "unknown",
                          seenTees.insert(tee.lowercased()).inserted else { return nil }
                    return tee
                }
                let parts = preferred.course.name.split(
                    separator: "~",
                    maxSplits: 1,
                    omittingEmptySubsequences: false
                )
                let venue = String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)
                let segment = parts.count > 1
                    ? String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)
                    : nil
                let anchor = preferred.holes.first {
                    $0.teeLatitude != nil && $0.teeLongitude != nil
                }
                return MobileCourseOption(
                    globalId: preferred.course.globalId,
                    name: preferred.course.name,
                    holes: preferred.holes.count,
                    teeBox: preferred.course.teeBox,
                    geometryCoverage: preferred.geometryCoverage.state.rawValue,
                    venueName: venue.isEmpty ? preferred.course.name : venue,
                    segmentLabel: segment?.isEmpty == false ? segment : nil,
                    segmentHoles: preferred.holes.count,
                    latitude: anchor?.teeLatitude,
                    longitude: anchor?.teeLongitude,
                    tees: tees
                )
            }
            .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    /// Fetch the home package for an explicitly finished course, or the most-played course during
    /// ordinary bootstrap. The bootstrap path falls back to cache offline; geometry is unnecessary.
    private func fetchHomePackage(preferredCourse: Course? = nil) async -> LiveRoundPackage? {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return try? offlineStore.loadHomePackage()
        }
        #endif
        if let preferredCourse {
            guard let syncClient else { return nil }
            return try? await syncClient.fetchCoursePackage(
                globalId: preferredCourse.globalId,
                roundId: "home-\(preferredCourse.globalId)",
                teeBox: preferredCourse.teeBox,
                nine: "all",
                capturedAt: Date(),
                ensureGeometry: false,
                includeEventCursor: false
            )
        }
        let mostPlayed = courseOptions.max { $0.roundCount < $1.roundCount }
        if let syncClient, let mostPlayed {
            let homeRoundId = mostPlayed.suggestedLiveRoundId ?? "home-\(mostPlayed.globalId)"
            let teeBox = mostPlayed.teeBox.flatMap { $0 == "unknown" ? nil : $0 } ?? "unknown"
            if let fetched = try? await syncClient.fetchCoursePackage(
                globalId: mostPlayed.globalId,
                roundId: homeRoundId,
                teeBox: teeBox,
                nine: "all",
                capturedAt: Date(),
                ensureGeometry: false,
                includeEventCursor: false
            ) {
                return fetched
            }
        }
        return try? offlineStore.loadHomePackage()
    }

    private func canContinueExpiredPackage(_ cachedPackage: LiveRoundPackage) throws -> Bool {
        try offlineStore.loadPendingEvents(roundId: cachedPackage.roundId).isEmpty == false
    }

    private func acceptWatchEvent(_ event: LiveRoundEvent) throws {
        try offlineStore.appendEvent(event)
        do {
            if let package, package.roundId == event.roundId {
                liveRoundState = try offlineStore.restoreLiveRoundState(roundId: event.roundId, package: package)
            }
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: event.roundId).count
            syncStatus = "手表已记录"
        } catch {
            AICaddieLog.watch.error("Watch event status update failed: \(String(describing: error), privacy: .public)")
            syncStatus = "手表已记录,稍后刷新"
        }
    }

    private func idempotencyKey(roundId: String, events: [LiveRoundEvent]) -> String {
        let eventKey = events.map(\.eventId).joined(separator: "-")
        return "\(roundId)-\(eventKey)"
    }

    private func loadFixturePackage() throws -> LiveRoundPackage {
        let resourceName = "live_round_package.fixture"
        #if SWIFT_PACKAGE
        let resourceURL = Bundle.module.url(forResource: resourceName, withExtension: "json")
        #else
        let resourceURL = Bundle.main.url(forResource: resourceName, withExtension: "json")
        #endif
        guard let resourceURL else {
            throw URLError(.fileDoesNotExist)
        }
        let data = try Data(contentsOf: resourceURL)
        return try JSONDecoder().decode(LiveRoundPackage.self, from: data)
    }

    #if DEBUG
    private func loadScoringUITestFixture() throws -> LiveRoundPackage {
        let package = try loadFixturePackage()
        guard let first = package.holes.first else { return package }
        let second = Hole(
            number: 2,
            par: 3,
            yards: 165,
            geometryCoverage: .missing,
            sourceGlobalId: first.sourceGlobalId,
            sourceLocalHole: 2
        )
        return LiveRoundPackage(
            schema: package.schema,
            roundId: package.roundId,
            dataMode: package.dataMode,
            sourceCoverage: package.sourceCoverage,
            missingData: package.missingData,
            playerProfile: package.playerProfile,
            course: package.course,
            holes: [first, second],
            nine: package.nine,
            coursePrep: package.coursePrep,
            geometryCoverage: package.geometryCoverage,
            readinessChecks: package.readinessChecks,
            caddieContextSeeds: package.caddieContextSeeds,
            weatherSnapshot: package.weatherSnapshot,
            clubProfiles: package.clubProfiles,
            caddieDecisionEndpoint: package.caddieDecisionEndpoint,
            offlinePackageStatus: package.offlinePackageStatus,
            eventCursor: package.eventCursor,
            recentHistory: package.recentHistory,
            cachedCaddieRules: package.cachedCaddieRules,
            generatedAt: package.generatedAt
        )
    }
    #endif
}
