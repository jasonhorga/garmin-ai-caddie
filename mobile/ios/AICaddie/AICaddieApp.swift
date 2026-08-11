import Combine
import Foundation
import os
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

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
                        prepCourseDownloads: model.prepCourseDownloads,
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
                        onRememberCourseDisplayName: { globalId, name in
                            model.rememberSelectedCourseDisplayName(globalId: globalId, name: name)
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
                        onRetainReadyHolePrep: { roundId, roundHole, prep in
                            model.retainReadyHolePrep(
                                roundId: roundId,
                                roundHole: roundHole,
                                prep: prep
                            )
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
                        onDownloadPrepCourse: { course in
                            model.downloadPrepCourse(course)
                        },
                        onRetryPrepCourseDownload: { id in
                            model.retryPrepCourseDownload(id: id)
                        },
                        pendingLiveHole: model.pendingLiveHole,
                        onConsumePendingLiveHole: {
                            model.consumePendingLiveHole()
                        },
                        onLiveHoleInitialLoadDidFinish: {
                            model.liveHoleInitialLoadDidFinish()
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
                            onRememberCourseDisplayName: { globalId, name in
                                model.rememberSelectedCourseDisplayName(globalId: globalId, name: name)
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
                } else if phase == .background {
                    model.continuePrepDownloadsInBackground()
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
    case pendingMedia
}

private struct OfflineTopoDownloadResult: Sendable {
    let globalId: Int
    let localHole: Int
    let geometryRevision: String?
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
    @Published public private(set) var prepCourseDownloads: [PrepCourseDownloadRecord] = []
    /// 本局的起始九洞(用于「移除另外 9 洞」撤销目标);随新 roundId 重置。
    @Published public private(set) var startingNine: String?
    public let watchBridge: WatchEventBridge?
    public let offlineStore: OfflineStore
    public let garminSessionStore: GarminSessionStore?

    private var syncClient: SyncClient?
    private var mediaUploadClient: MediaUploadClient?
    private var isSyncingPendingEvents = false
    private var watchFinishedRoundReconciliationTask: Task<Void, Never>?
    private var offlineCourseDownloadTask: Task<Void, Never>?
    private var prepCourseDownloadTask: Task<Void, Never>?
    private var prepCourseDownloadGeneration: UUID?
    private var activePrepCourseDownloadID: String?
    #if canImport(UIKit)
    private var prepBackgroundTaskIdentifier: UIBackgroundTaskIdentifier = .invalid
    #endif
    /// A newly prepared round must commit its first live-hole navigation before this MainActor model
    /// starts the all-hole cache pipeline.  `false` means fill missing assets; `true` also revalidates
    /// the package release.  Optionality distinguishes "not deferred" from the normal false mode.
    private var deferredOfflineCourseDownloadRevalidation: Bool?
    private var roundPreparationToken: UUID?
    /// Ephemeral selection intent. The selected name is written into the durable round/template
    /// package before activation, so this dictionary never becomes a second persistence authority.
    private var selectedCourseDisplayNames: [Int: String] = [:]
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
        watchBridge?.onRoundClosure = { [weak self] closure in
            Task { @MainActor in
                self?.handleWatchRoundClosure(closure)
            }
        }
        watchBridge?.activateSession()
        syncConfigToWatch()
        observeSessionForWatch()
        refreshDownloadedCourseOptions()
        restorePrepCourseDownloadsFromDisk()
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
        pausePrepCourseDownload()
        watchFinishedRoundReconciliationTask?.cancel()
        watchFinishedRoundReconciliationTask = nil
        deferredOfflineCourseDownloadRevalidation = nil
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
        selectedCourseDisplayNames = [:]
        courseOptionsRefreshSucceeded = false
        syncStatus = "离线就绪"
        isBootstrapping = true
        refreshDownloadedCourseOptions()
        restorePrepCourseDownloadsFromDisk()
        syncConfigToWatch()
    }

    public func bootstrap() async {
        defer {
            isBootstrapping = false
            resumePrepCourseDownloads(retryFailed: true)
        }
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
                    beginOfflineCourseDownload(revalidatePackage: true)
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

    /// Start owns the live-round preparation generation. A previous live course's long package
    /// request may finish after the player has chosen another course; it must neither replace the new
    /// selection nor turn off the new request's spinner. The durable prep-library queue is independent
    /// and continues in the background when the player leaves prep or starts a round.
    private func beginRoundPreparation() -> UUID {
        let token = UUID()
        roundPreparationToken = token
        offlineCourseDownloadTask?.cancel()
        offlineCourseDownloadTask = nil
        deferredOfflineCourseDownloadRevalidation = nil
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
        // Live-course assets keep priority after a successful start: a fresh round has a deferred
        // installer, and a same-round nine change already owns `offlineCourseDownloadTask`. If the
        // start failed (or `prepareRound` did not create an installer), release the prep-library
        // queue here instead of leaving its durable jobs paused until the next app foreground.
        if deferredOfflineCourseDownloadRevalidation == nil,
           offlineCourseDownloadTask == nil {
            startPrepCourseDownloadQueueIfNeeded()
        }
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

    public func rememberSelectedCourseDisplayName(globalId: Int, name rawName: String) {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard globalId > 0, !name.isEmpty else { return }
        selectedCourseDisplayNames[globalId] = name
    }

    private func applyingSelectedCourseDisplayName(
        to package: LiveRoundPackage
    ) -> LiveRoundPackage {
        package.replacingCourseDisplayName(
            selectedCourseDisplayNames[package.course.globalId]
        )
    }

    public func prepareCourseRound(globalId: Int, roundId: String, teeBox: String, nine: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "无法开始这一场,请重试"
            return
        }
        recordUITestLatency(
            "course-start.begin globalId=\(globalId) holes=\(nine) tee=\(teeBox)"
        )
        let preparationToken = beginRoundPreparation()
        defer {
            recordUITestLatency("course-start.finish.begin globalId=\(globalId)")
            finishRoundPreparation(preparationToken)
            recordUITestLatency("course-start.finish.end globalId=\(globalId)")
        }
        // A home package can deliberately retain the last course/round id while no round is active.
        // `liveRoundState`, not package identity, therefore decides whether Start must enter hole 1.
        // The same active round's 加打/移除九洞 keeps its identity and does not re-enter as a new one.
        let isNewRound = liveRoundState?.roundId != requestedRoundId
        if isNewRound {
            startingNine = (nine == "all") ? nil : nine
        }
        let preparedAt = Date()

        do {
            // A course advertised as downloaded already has the exact Tee/hole-set facts and every
            // precise topo bitmap on disk.  Starting that new round must not sit behind a slow or
            // unavailable package request: rebase its immutable template to the new round identity
            // and enter hole 1 immediately.  Same-round nine changes deliberately keep the remote
            // path below because they mutate the active package rather than start a fresh round.
            if isNewRound,
               let template = try offlineStore.loadCourseTemplate(
                   globalId: globalId,
                   teeBox: teeBox,
                   nine: nine
               ),
               template.hasCompleteOfflineCoursePrep,
               offlineStore.hasCourseTopoImages(for: template) {
                let offlinePackage = applyingSelectedCourseDisplayName(to: template.rebasedForOfflineStart(
                    roundId: requestedRoundId,
                    generatedAt: preparedAt
                ))
                try offlineStore.saveRoundPackage(offlinePackage)
                try activatePackage(offlinePackage, status: "本地球场已就绪")
                signalFreshRoundEntry(revalidatePackage: true)
                // Enter immediately from local facts, then verify the Garmin release in the
                // background. Matching revisions reuse every byte; changed holes refresh only
                // their prep/topo while a network failure leaves this playable snapshot intact.
                return
            }

            let fetched = await fetchRemoteCoursePackage(
                globalId: globalId,
                roundId: requestedRoundId,
                teeBox: teeBox,
                nine: nine,
                capturedAt: preparedAt,
                preparationToken: preparationToken
            )
            recordUITestLatency(
                "course-start.fetch.end globalId=\(globalId) found=\(fetched != nil)"
            )
            guard isCurrentRoundPreparation(preparationToken) else { return }
            if let remotePackage = fetched {
                let remotePackage = applyingSelectedCourseDisplayName(to: remotePackage)
                recordUITestLatency(
                    "course-start.save.begin globalId=\(globalId) bytes-holes=\(remotePackage.holes.count)"
                )
                try offlineStore.saveRoundPackage(remotePackage)
                recordUITestLatency("course-start.save.end globalId=\(globalId)")
                recordUITestLatency("course-start.activate.begin globalId=\(globalId)")
                try activatePackage(remotePackage, status: "球场已就绪")
                recordUITestLatency("course-start.activate.end globalId=\(globalId)")
                if isNewRound {
                    recordUITestLatency("course-start.signal.begin globalId=\(globalId)")
                    signalFreshRoundEntry(cacheOfflineAssets: true)
                    recordUITestLatency("course-start.signal.end globalId=\(globalId)")
                } else {
                    // 加打另外九洞 changes the package in place but still needs the newly selected
                    // holes retained. beginRoundPreparation cancelled the superseded download above.
                    beginOfflineCourseDownload()
                }
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                let cachedPackage = applyingSelectedCourseDisplayName(to: cachedPackage)
                // Persist the active-round pointer for the offline/cached start too, so a round
                // started without network still resumes on relaunch (continue card survives quit).
                try offlineStore.saveRoundPackage(cachedPackage)
                try activatePackage(cachedPackage, status: "已下载离线")
                if isNewRound {
                    signalFreshRoundEntry(revalidatePackage: true)
                } else {
                    beginOfflineCourseDownload(revalidatePackage: true)
                }
            } else if let template = try offlineStore.loadCourseTemplate(
                globalId: globalId,
                teeBox: teeBox,
                nine: nine
            ) {
                let offlinePackage = applyingSelectedCourseDisplayName(to: template.rebasedForOfflineStart(
                    roundId: requestedRoundId,
                    generatedAt: preparedAt
                ))
                try offlineStore.saveRoundPackage(offlinePackage)
                try activatePackage(offlinePackage, status: "离线球场已就绪")
                if isNewRound {
                    signalFreshRoundEntry(revalidatePackage: true)
                } else {
                    beginOfflineCourseDownload(revalidatePackage: true)
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
    private func signalFreshRoundEntry(
        cacheOfflineAssets: Bool = false,
        revalidatePackage: Bool = false
    ) {
        pendingLiveHole = liveRoundState?.activeHole ?? package?.holes.first?.number
        deferredOfflineCourseDownloadRevalidation =
            (cacheOfflineAssets || revalidatePackage) ? revalidatePackage : nil
        recordUITestLatency(
            "course-start.pending-published hole=\(pendingLiveHole ?? -1) "
                + "cache=\(cacheOfflineAssets) revalidate=\(revalidatePackage)"
        )
    }

    /// `CurrentHoleView` calls this after its initial map and caddie request have settled. The cache
    /// pipeline deliberately starts here, rather than in `prepareCourseRound` or `onAppear`, so
    /// all-hole prep/file work can compete with neither navigation nor the first playable facts.
    func liveHoleInitialLoadDidFinish() {
        guard let revalidatePackage = deferredOfflineCourseDownloadRevalidation else { return }
        deferredOfflineCourseDownloadRevalidation = nil
        recordUITestLatency(
            "course-start.live-initial-load-finished-release-cache revalidate=\(revalidatePackage)"
        )
        // This pipeline downloads every topo itself. Running the server-wide prewarmer at the same
        // time makes both jobs parse/render the same 18 holes and more than doubles server work.
        beginOfflineCourseDownload(revalidatePackage: revalidatePackage)
    }

    /// Keep start latency low, then make the selected course genuinely reusable without a network:
    /// retain every hole's lightweight route/hazard/F-M-B facts and its precise topo bitmap. The
    /// package identity remains the live round's; the course template and bitmap keys are static.
    private func beginOfflineCourseDownload(revalidatePackage: Bool = false) {
        guard var snapshot = package, let syncClient else { return }
        // An explicit same-round refresh supersedes any one-shot fresh-entry release still pending.
        deferredOfflineCourseDownloadRevalidation = nil
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
            self?.recordUITestLatency(
                "offline-cache.task.begin globalId=\(downloadSnapshot.course.globalId)"
            )
            await self?.downloadOfflineCourseAssets(
                for: downloadSnapshot,
                using: syncClient,
                revalidatePackage: revalidatePackage
            )
            self?.recordUITestLatency(
                "offline-cache.task.end globalId=\(downloadSnapshot.course.globalId)"
            )
            self?.startPrepCourseDownloadQueueIfNeeded()
        }
    }

    #if DEBUG
    /// Test-only synchronization point. Course preparation intentionally returns before the
    /// complete-course cache finishes, but a test must not let that background work escape into
    /// the next test's process-wide URLProtocol handler.
    func waitForOfflineCourseDownloadForTesting() async {
        await offlineCourseDownloadTask?.value
    }

    /// Test-only synchronization point for the app-owned prep queue. Production views never await
    /// this task: they observe `prepCourseDownloads`, so navigation cannot become its owner.
    func waitForPrepCourseDownloadForTesting() async {
        await prepCourseDownloadTask?.value
    }
    #endif

    private func offlinePrepKey(globalId: Int, localHole: Int) -> String {
        "\(globalId):\(localHole)"
    }

    private func offlinePrepIsPrecise(_ prep: CoursePrepHole?) -> Bool {
        guard let prep, prep.resolvedMapOverlay != nil else { return false }
        return prep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame
    }

    private func geometryRevisionMatches(_ lhs: String?, _ rhs: String?) -> Bool {
        guard let lhs = lhs?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              let rhs = rhs?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !lhs.isEmpty, !rhs.isEmpty else { return lhs == nil && rhs == nil }
        return lhs == rhs
    }

    /// A downloaded course starts instantly, but online entry still asks the server for the current
    /// Garmin release. Only precise prep whose revision matches that response is carried forward;
    /// a partial response deliberately activates its current lightweight route until the replacement
    /// geometry arrives. Failure returns nil and leaves every last-known-good offline byte untouched.
    private func revalidatedCourseSnapshot(
        _ cached: LiveRoundPackage,
        using syncClient: SyncClient
    ) async -> LiveRoundPackage? {
        let frontGlobalId = cached.course.globalId
        let backGlobalId = cached.holes
            .filter { $0.number > 9 }
            .compactMap { $0.sourceGlobalId }
            .first { $0 != frontGlobalId }
        let remote: LiveRoundPackage
        do {
            remote = try await syncClient.fetchCoursePackage(
                globalId: frontGlobalId,
                roundId: cached.roundId,
                teeBox: cached.course.teeBox,
                nine: backGlobalId == nil ? (cached.nine ?? "all") : "all",
                capturedAt: Date(),
                ensureGeometry: false,
                backgroundGeometry: true,
                backGlobalId: backGlobalId,
                includeEventCursor: false
            )
        } catch {
            AICaddieLog.network.info(
                "Offline course release revalidation deferred: \(String(describing: error), privacy: .public)"
            )
            return nil
        }
        guard remote.roundId == cached.roundId, !remote.holes.isEmpty else { return nil }
        let remoteWithStableName = remote.replacingCourseDisplayName(cached.course.name)

        var prepByHole = Dictionary(
            uniqueKeysWithValues: (remoteWithStableName.coursePrep?.holes ?? []).map { ($0.hole, $0) }
        )
        for remoteHole in remoteWithStableName.holes {
            guard remoteHole.geometryCoverage == .ready,
                  let retained = cached.coursePrep?.holes.first(where: {
                      $0.hole == remoteHole.number
                  }),
                  offlinePrepIsPrecise(retained) else { continue }
            guard geometryRevisionMatches(
                retained.geometryRevision,
                remoteHole.geometryRevision
            ) else { continue }
            if !offlinePrepIsPrecise(prepByHole[remoteHole.number]) {
                prepByHole[remoteHole.number] = retained
            }
        }
        guard !prepByHole.isEmpty else { return remoteWithStableName }
        let base = remoteWithStableName.coursePrep
        return remoteWithStableName.replacingCoursePrep(CoursePrepPackage(
            schema: base?.schema ?? "ai-caddie-course-prep-v1",
            globalId: base?.globalId ?? remoteWithStableName.course.globalId,
            holes: prepByHole.values.sorted { $0.hole < $1.hole },
            missingData: base?.missingData
        ))
    }

    /// Persist one foreground hole as soon as its precise prep is available. The expected round ID
    /// rejects a late async callback after the player has started another round; renumbering keeps a
    /// composite back nine's source hole 1 attached to round hole 10. Saving precedes publication so
    /// a map that SwiftUI can display is already resumable on disk.
    @discardableResult
    public func retainReadyHolePrep(
        roundId: String,
        roundHole: Int,
        prep: CoursePrepHole
    ) -> Bool {
        guard offlinePrepIsPrecise(prep),
              let current = package,
              current.roundId == roundId,
              liveRoundState?.roundId == roundId,
              current.holes.contains(where: { $0.number == roundHole }) else {
            return false
        }

        let retained = prep.renumbered(to: roundHole)
        var holes = current.coursePrep?.holes.filter { $0.hole != roundHole } ?? []
        holes.append(retained)
        holes.sort { $0.hole < $1.hole }
        let updated = current.replacingCoursePrep(CoursePrepPackage(
            schema: current.coursePrep?.schema ?? "ai-caddie-course-prep-v1",
            globalId: current.coursePrep?.globalId ?? current.course.globalId,
            holes: holes,
            missingData: current.coursePrep?.missingData
        ))

        do {
            try offlineStore.saveRoundPackage(updated)
            package = updated
            refreshDownloadedCourseOptions()
            return true
        } catch {
            AICaddieLog.storage.error(
                "Live hole prep save failed for \(roundId, privacy: .public)/\(roundHole, privacy: .public): \(String(describing: error), privacy: .public)"
            )
            return false
        }
    }

    /// The all-hole downloader starts from an immutable snapshot. If the foreground has meanwhile
    /// retained a precise hole, do not let a later partial/missing snapshot overwrite that progress.
    private func preservingForegroundPrecisePrep(in candidate: LiveRoundPackage) -> LiveRoundPackage {
        guard let current = package,
              current.roundId == candidate.roundId,
              let currentPrep = current.coursePrep else { return candidate }

        var merged = Dictionary(
            uniqueKeysWithValues: (candidate.coursePrep?.holes ?? []).map { ($0.hole, $0) }
        )
        for retained in currentPrep.holes {
            let replacement = merged[retained.hole]
            let retainedOwnsNewerPreciseFacts = offlinePrepIsPrecise(retained)
                && (!offlinePrepIsPrecise(replacement)
                    || !geometryRevisionMatches(
                        retained.geometryRevision,
                        replacement?.geometryRevision
                    ))
            if replacement == nil || retainedOwnsNewerPreciseFacts {
                merged[retained.hole] = retained
            }
        }
        let base = candidate.coursePrep
        return candidate.replacingCoursePrep(CoursePrepPackage(
            schema: base?.schema ?? currentPrep.schema,
            globalId: base?.globalId ?? currentPrep.globalId,
            holes: merged.values.sorted { $0.hole < $1.hole },
            missingData: base?.missingData ?? currentPrep.missingData
        ))
    }

    /// Course prep cost grows non-linearly when one request parses all 18 large meshes. Keep the
    /// first playing hole as its own highest-priority request (the live view asks for the same key,
    /// so the backend singleflight can share it), then fetch the rest in small bounded batches.
    /// Two concurrent batches leave capacity for live map/caddie traffic on the four-core shared
    /// service; three cold batches reproduced a 60-second timeout in the real 18-hole journey.
    private func fetchOfflinePrepBatches(
        _ requests: [OfflinePrepBatchRequest],
        using syncClient: SyncClient,
        maximumConcurrentRequests: Int = 2
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

    /// Fetch topo PNGs with a bounded concurrency window. The offline caller uses two-hole batches:
    /// a cold topo render is CPU-heavy, and four simultaneous renders made interactive nearby/search/
    /// map requests wait behind the background course download. Returning after each small batch lets
    /// the caller persist progress before moving on, so a later resume skips completed holes.
    private func fetchOfflineTopoImages(
        _ holes: [(globalId: Int, localHole: Int, geometryRevision: String?)],
        using syncClient: SyncClient,
        maximumConcurrentRequests: Int = 2
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
            let fetch: @Sendable ((globalId: Int, localHole: Int, geometryRevision: String?)) async -> OfflineTopoDownloadResult = { hole in
                do {
                    let data = try await client.value.fetchTopoImage(
                        globalId: hole.globalId,
                        localHole: hole.localHole,
                        geometryRevision: hole.geometryRevision
                    )
                    return OfflineTopoDownloadResult(
                        globalId: hole.globalId,
                        localHole: hole.localHole,
                        geometryRevision: hole.geometryRevision,
                        data: data,
                        errorDescription: nil
                    )
                } catch {
                    return OfflineTopoDownloadResult(
                        globalId: hole.globalId,
                        localHole: hole.localHole,
                        geometryRevision: hole.geometryRevision,
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
        for initialSnapshot: LiveRoundPackage,
        using syncClient: SyncClient,
        revalidatePackage: Bool = false,
        prepDownloadID: String? = nil,
        prepDownloadGeneration: UUID? = nil
    ) async {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return
        }
        #endif
        var snapshot = initialSnapshot
        if revalidatePackage,
           let current = await revalidatedCourseSnapshot(initialSnapshot, using: syncClient) {
            snapshot = current
            // Once the server has positively identified a newer release, do not let a force-quit
            // reopen the old precise package. Network failure never enters this branch.
            if package?.roundId == current.roundId, liveRoundState != nil {
                do {
                    try offlineStore.saveRoundPackage(current)
                    package = current
                } catch {
                    AICaddieLog.storage.error(
                        "Revalidated course package save failed: \(String(describing: error), privacy: .public)"
                    )
                }
            }
        }
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

        func assembledSnapshot() -> LiveRoundPackage {
            let mapped = snapshot.holes.compactMap { roundHole -> CoursePrepHole? in
                let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
                let localHole = roundHole.sourceLocalHole ?? roundHole.number
                return prepBySource[offlinePrepKey(globalId: globalId, localHole: localHole)]?
                    .renumbered(to: roundHole.number)
            }
            return snapshot.replacingCoursePrep(CoursePrepPackage(
                schema: "ai-caddie-course-prep-v1",
                globalId: snapshot.course.globalId,
                holes: mapped,
                missingData: mapped.count == snapshot.holes.count
                    ? nil
                    : [CoursePrepMissingData(
                        label: "offline_course_prep",
                        reason: "\(mapped.count)/\(snapshot.holes.count) hole maps retained"
                    )]
            ))
        }

        func preparedHoleCount() -> Int {
            snapshot.holes.reduce(into: 0) { count, roundHole in
                let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
                let localHole = roundHole.sourceLocalHole ?? roundHole.number
                if offlinePrepIsPrecise(prepBySource[
                    offlinePrepKey(globalId: globalId, localHole: localHole)
                ]) {
                    count += 1
                }
            }
        }

        func downloadedHoleCount() -> Int {
            snapshot.holes.reduce(into: 0) { count, roundHole in
                let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
                let localHole = roundHole.sourceLocalHole ?? roundHole.number
                let prep = prepBySource[offlinePrepKey(globalId: globalId, localHole: localHole)]
                guard offlinePrepIsPrecise(prep),
                      offlineStore.loadCourseTopoImageURL(
                          globalId: globalId,
                          localHole: localHole,
                          geometryRevision: prep?.geometryRevision ?? roundHole.geometryRevision
                      ) != nil else { return }
                count += 1
            }
        }

        func retainPrepBatchResults(_ results: [OfflinePrepBatchResult]) {
            for result in results {
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
                }
            }
        }

        func persistPrepBatchProgress() {
            guard let prepDownloadID else { return }
            do {
                try offlineStore.saveCourseTemplate(assembledSnapshot())
            } catch {
                AICaddieLog.storage.error(
                    "Incremental prep facts save failed: \(String(describing: error), privacy: .public)"
                )
            }
            updatePrepCourseDownload(
                id: prepDownloadID,
                generation: prepDownloadGeneration
            ) { state in
                state.phase = .preparing
                state.preparedHoles = preparedHoleCount()
                state.downloadedHoles = downloadedHoleCount()
                state.totalHoles = max(1, snapshot.holes.count)
            }
        }

        /// Geometry installation and topo rendering are independent stages. Download every hole
        /// whose precise facts have just become available instead of waiting for the slowest of all
        /// 18 holes. Each successful bitmap is revision-keyed and atomically durable, so a later
        /// retry or app relaunch skips it.
        func downloadNewlyReadyTopoHoles() async {
            let ready = snapshot.holes.compactMap { roundHole -> (globalId: Int, localHole: Int, geometryRevision: String?)? in
                let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
                let localHole = roundHole.sourceLocalHole ?? roundHole.number
                let prep = prepBySource[offlinePrepKey(globalId: globalId, localHole: localHole)]
                let revision = prep?.geometryRevision ?? roundHole.geometryRevision
                guard offlinePrepIsPrecise(prep),
                      offlineStore.loadCourseTopoImageURL(
                          globalId: globalId,
                          localHole: localHole,
                          geometryRevision: revision
                      ) == nil else { return nil }
                return (globalId, localHole, revision)
            }
            // Keep the card the player opens first ahead of throughput work. Starting holes 1 and
            // 2 concurrently made the second request win the scheduler occasionally, so the first
            // visible map could still wait behind a later cold render. Fetch one priority bitmap,
            // persist it, then use the bounded two-hole window for the rest of the course.
            var readyIndex = 0
            while readyIndex < ready.count {
                guard !Task.isCancelled else { return }
                let window = readyIndex == 0 ? 1 : 2
                let end = min(readyIndex + window, ready.count)
                let downloads = await fetchOfflineTopoImages(
                    Array(ready[readyIndex..<end]),
                    using: syncClient
                )
                guard !Task.isCancelled else { return }
                for download in downloads {
                    guard let data = download.data else {
                        let errorDescription = download.errorDescription ?? "unknown error"
                        AICaddieLog.network.info(
                            "Incremental topo deferred for \(download.globalId, privacy: .public)/\(download.localHole, privacy: .public): \(errorDescription, privacy: .public)"
                        )
                        continue
                    }
                    do {
                        _ = try offlineStore.saveCourseTopoImage(
                            data,
                            globalId: download.globalId,
                            localHole: download.localHole,
                            geometryRevision: download.geometryRevision
                        )
                        if let prepDownloadID {
                            updatePrepCourseDownload(
                                id: prepDownloadID,
                                generation: prepDownloadGeneration
                            ) { state in
                                state.phase = preparedHoleCount() == snapshot.holes.count
                                    ? .downloading
                                    : .preparing
                                state.preparedHoles = preparedHoleCount()
                                state.downloadedHoles = downloadedHoleCount()
                                state.totalHoles = max(1, snapshot.holes.count)
                            }
                        }
                    } catch {
                        AICaddieLog.storage.error(
                            "Incremental topo save failed for \(download.globalId, privacy: .public)/\(download.localHole, privacy: .public): \(String(describing: error), privacy: .public)"
                        )
                    }
                }
                readyIndex = end
            }
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
        // A lightweight package deliberately embeds the first hole as a fast partial seed even
        // when that hole's Garmin geometry is already installed. The authoritative per-hole
        // revision on `snapshot.holes` is the stronger readiness fact. Promote those keys before
        // building prep batches so the first playing hole is upgraded first instead of waiting
        // behind topo downloads for holes 2...18.
        for roundHole in snapshot.holes {
            guard roundHole.geometryCoverage == .ready,
                  let revision = roundHole.geometryRevision?
                .trimmingCharacters(in: .whitespacesAndNewlines),
                  !revision.isEmpty else { continue }
            geometryReadyKeys.insert(offlinePrepKey(
                globalId: roundHole.sourceGlobalId ?? snapshot.course.globalId,
                localHole: roundHole.sourceLocalHole ?? roundHole.number
            ))
        }
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

            // Fetch the first playing hole to completion before starting the throughput batches.
            // Merely putting its singleton at the front of one task group still made it wait for
            // every other group result before the UI could persist and draw it.
            if let priorityRequest = batchRequests.first {
                let priorityResults = await fetchOfflinePrepBatches(
                    [priorityRequest],
                    using: syncClient,
                    maximumConcurrentRequests: 1
                )
                guard !Task.isCancelled else { return }
                retainPrepBatchResults(priorityResults)
                for prep in priorityResults.flatMap(\.holes) where offlinePrepIsPrecise(prep) {
                    geometryReadyKeys.insert(offlinePrepKey(
                        globalId: priorityRequest.globalId,
                        localHole: prep.hole
                    ))
                }
                persistPrepBatchProgress()
                await downloadNewlyReadyTopoHoles()
                guard !Task.isCancelled else { return }
                batchRequests.removeFirst()
            }

            let batchResults = await fetchOfflinePrepBatches(batchRequests, using: syncClient)
            guard !Task.isCancelled else { return }
            retainPrepBatchResults(batchResults)
            for result in batchResults {
                for prep in result.holes where offlinePrepIsPrecise(prep) {
                    geometryReadyKeys.insert(offlinePrepKey(
                        globalId: result.request.globalId,
                        localHole: prep.hole
                    ))
                }
            }
            persistPrepBatchProgress()
            // Do not hold the first finished holes hostage to the slowest geometry install. This
            // is the key latency fix for cold courses: cards become locally usable one by one.
            await downloadNewlyReadyTopoHoles()
            guard !Task.isCancelled else { return }
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

        guard !Task.isCancelled else { return }
        let enriched = assembledSnapshot()

        // Course facts and topo bitmaps have independent durability. Persist the precise per-hole
        // facts before starting the potentially long bitmap pass; otherwise a force-quit after the
        // visible first-hole topo succeeds can restore the old partial package and never select the
        // already-cached precise image. The downloaded-course list still requires every bitmap, so
        // this early save cannot falsely advertise that the whole course is offline-ready.
        do {
            let durableEnriched = preservingForegroundPrecisePrep(in: enriched)
            try offlineStore.saveCourseTemplate(durableEnriched)
            if package?.roundId == snapshot.roundId, liveRoundState != nil {
                try offlineStore.saveRoundPackage(durableEnriched)
                package = durableEnriched
            }
        } catch {
            AICaddieLog.storage.error(
                "Offline course facts save failed: \(String(describing: error), privacy: .public)"
            )
        }

        if let prepDownloadID {
            updatePrepCourseDownload(
                id: prepDownloadID,
                generation: prepDownloadGeneration
            ) { state in
                state.phase = .downloading
                state.preparedHoles = preparedHoleCount()
                state.downloadedHoles = downloadedHoleCount()
                state.totalHoles = max(1, snapshot.holes.count)
            }
        }

        let topoRetryDelays: [UInt64] = [5, 10, 20]
        for attempt in 0...topoRetryDelays.count {
            guard !Task.isCancelled else { return }
            let missingTopoHoles = snapshot.holes.compactMap { roundHole -> (globalId: Int, localHole: Int, geometryRevision: String?)? in
                let globalId = roundHole.sourceGlobalId ?? snapshot.course.globalId
                let localHole = roundHole.sourceLocalHole ?? roundHole.number
                let prep = prepBySource[offlinePrepKey(globalId: globalId, localHole: localHole)]
                let revision = prep?.geometryRevision ?? roundHole.geometryRevision
                guard prep?.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame,
                      offlineStore.loadCourseTopoImageURL(
                          globalId: globalId,
                          localHole: localHole,
                          geometryRevision: revision
                      ) == nil else { return nil }
                return (globalId, localHole, revision)
            }
            guard !missingTopoHoles.isEmpty else { break }

            // Persist each hole as soon as it arrives. The previous all-course task group returned
            // only after every cold render completed, so killing the app on hole 1 discarded even a
            // successfully downloaded first bitmap and four renders could starve foreground APIs.
            // As above, the first still-missing map owns the foreground lane; only later maps share
            // the two-request throughput window.
            var missingIndex = 0
            while missingIndex < missingTopoHoles.count {
                guard !Task.isCancelled else { return }
                let window = missingIndex == 0 ? 1 : 2
                let end = min(missingIndex + window, missingTopoHoles.count)
                let downloads = await fetchOfflineTopoImages(
                    Array(missingTopoHoles[missingIndex..<end]),
                    using: syncClient
                )
                guard !Task.isCancelled else { return }
                for download in downloads {
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
                            localHole: download.localHole,
                            geometryRevision: download.geometryRevision
                        )
                        if let prepDownloadID {
                            updatePrepCourseDownload(
                                id: prepDownloadID,
                                generation: prepDownloadGeneration
                            ) { state in
                                state.phase = .downloading
                                state.preparedHoles = preparedHoleCount()
                                state.downloadedHoles = downloadedHoleCount()
                                state.totalHoles = max(1, snapshot.holes.count)
                            }
                        }
                    } catch {
                        AICaddieLog.storage.error(
                            "Offline topo cache save failed for \(download.globalId, privacy: .public)/\(download.localHole, privacy: .public): \(String(describing: error), privacy: .public)"
                        )
                    }
                }
                missingIndex = end
            }

            let stillMissing = missingTopoHoles.contains { hole in
                offlineStore.loadCourseTopoImageURL(
                    globalId: hole.globalId,
                    localHole: hole.localHole,
                    geometryRevision: hole.geometryRevision
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
            let durableEnriched = preservingForegroundPrecisePrep(in: enriched)
            try offlineStore.saveCourseTemplate(durableEnriched)
            if package?.roundId == snapshot.roundId, liveRoundState != nil {
                try offlineStore.saveRoundPackage(durableEnriched)
                package = durableEnriched
            }
            refreshDownloadedCourseOptions()
            if durableEnriched.hasCompleteOfflineCoursePrep,
               offlineStore.hasCourseTopoImages(for: durableEnriched),
               prepDownloadID == nil {
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
                let remotePackage = applyingSelectedCourseDisplayName(to: remotePackage)
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
                let cachedPackage = applyingSelectedCourseDisplayName(to: cachedPackage)
                // Persist the active-round pointer for the offline/cached start too, so a round
                // started without network still resumes on relaunch (continue card survives quit).
                try offlineStore.saveRoundPackage(cachedPackage)
                try activatePackage(cachedPackage, status: "已下载离线")
                if isNewRound {
                    signalFreshRoundEntry(revalidatePackage: true)
                } else {
                    beginOfflineCourseDownload(revalidatePackage: true)
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
            _ = try await syncPendingMedia(roundId: package.roundId)
            guard try offlineStore.loadPendingMedia(roundId: package.roundId).isEmpty else {
                throw LiveRoundFinishError.pendingMedia
            }

            let pending = try offlineStore.loadPendingEvents(roundId: package.roundId)
            if !pending.isEmpty {
                try await postPendingEventsAndRequireFullAcknowledgement(
                    pending,
                    roundId: package.roundId,
                    syncClient: syncClient
                )
            }
            guard try offlineStore.loadPendingEvents(roundId: package.roundId).isEmpty,
                  try offlineStore.loadPendingMedia(roundId: package.roundId).isEmpty else {
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
            // Both Finish and the home refresh suspend the MainActor. A Watch event can arrive after
            // the upload watermark was proven empty; never delete that newly appended local fact.
            guard try offlineStore.loadPendingEvents(roundId: package.roundId).isEmpty else {
                throw LiveRoundFinishError.incompleteAcknowledgement
            }
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

    private func clearFinishedRoundLocally(
        roundId: String,
        notifyWatch: Bool = true
    ) throws {
        guard try offlineStore.loadPendingMedia(roundId: roundId).isEmpty else {
            throw LiveRoundFinishError.pendingMedia
        }
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
        if notifyWatch {
            watchBridge?.sendRoundClosureToWatch(
                roundId: roundId,
                disposition: .finished
            )
        } else {
            watchBridge?.clearRoundSeed(roundId: roundId)
        }
    }

    /// A Watch finish already completed the idempotent backend finish transaction. The phone may
    /// still own events that the Watch saw over Bluetooth but the backend never received. Preserve
    /// that complete local round until those events receive explicit server ACKs; abandon/save-
    /// locally on the wrist never deletes phone data.
    public func handleWatchRoundClosure(_ closure: WatchRoundClosurePayload) {
        guard closure.disposition == .finished,
              package?.roundId == closure.roundId,
              liveRoundState?.roundId == closure.roundId else {
            return
        }
        do {
            let pending = try offlineStore.loadPendingEvents(roundId: closure.roundId)
            let pendingMedia = try offlineStore.loadPendingMedia(roundId: closure.roundId)
            pendingEventCount = pending.count
            guard !pending.isEmpty || !pendingMedia.isEmpty else {
                try clearFinishedRoundLocally(roundId: closure.roundId, notifyWatch: false)
                return
            }

            syncStatus = "手表已结束,正在同步本机记录"
            finishErrorMessage = "本机记录同步完成后将自动结束"
            watchFinishedRoundReconciliationTask = Task { @MainActor [weak self] in
                await self?.reconcileWatchFinishedRound(roundId: closure.roundId)
            }
        } catch {
            AICaddieLog.storage.error("Watch-finished round cleanup failed: \(String(describing: error), privacy: .public)")
            finishErrorMessage = "手表已结束，本机记录仍保留"
        }
    }

    private func reconcileWatchFinishedRound(roundId: String) async {
        // A score tap may already own the uploader when the closure arrives. Let that exact batch
        // settle, then make one normal retry so cleanup observes a stable ACK watermark.
        while isSyncingPendingEvents {
            guard !Task.isCancelled else { return }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        guard !Task.isCancelled,
              package?.roundId == roundId,
              liveRoundState?.roundId == roundId else {
            return
        }

        await syncPendingEvents()

        guard !Task.isCancelled,
              package?.roundId == roundId,
              liveRoundState?.roundId == roundId else {
            return
        }
        do {
            var remaining = try offlineStore.loadPendingEvents(roundId: roundId)
            var remainingMedia = try offlineStore.loadPendingMedia(roundId: roundId)
            if !remaining.isEmpty || !remainingMedia.isEmpty {
                // The first sync can legitimately pull Watch-authored server events after its local
                // sync marker. One bounded second pass ACKs that imported tail; replaying those same
                // server identities is locally idempotent even if the cursor ACK was lost. Any genuine
                // offline/partial/newer-event or media failure remains on disk after this single retry.
                pendingEventCount = remaining.count
                await syncPendingEvents()
                guard !Task.isCancelled,
                      package?.roundId == roundId,
                      liveRoundState?.roundId == roundId else {
                    return
                }
                remaining = try offlineStore.loadPendingEvents(roundId: roundId)
                remainingMedia = try offlineStore.loadPendingMedia(roundId: roundId)
            }
            pendingEventCount = remaining.count
            guard remaining.isEmpty, remainingMedia.isEmpty else {
                syncStatus = "手表已结束,本机记录待同步"
                finishErrorMessage = "手表已结束，本机记录仍保留"
                return
            }
            try clearFinishedRoundLocally(roundId: roundId, notifyWatch: false)
        } catch {
            AICaddieLog.storage.error("Watch-finished round reconciliation failed: \(String(describing: error), privacy: .public)")
            finishErrorMessage = "手表已结束，本机记录仍保留"
        }
    }

    #if DEBUG
    func waitForWatchRoundClosureReconciliationForTesting() async {
        await watchFinishedRoundReconciliationTask?.value
    }
    #endif

    /// Explicit local discard remains distinct from Save & End. It is offline-capable and notifies
    /// the Watch only after the matching phone data has been removed.
    public func discardActiveRound() {
        guard let package, liveRoundState?.roundId == package.roundId else { return }
        do {
            try offlineStore.discardRound(roundId: package.roundId)
            watchBridge?.sendRoundClosureToWatch(
                roundId: package.roundId,
                disposition: .abandoned
            )
            if let home = try offlineStore.loadHomePackage() {
                try activateHomePackage(home, status: "本场已放弃")
            } else {
                self.package = nil
                liveRoundState = nil
                startingNine = nil
                pendingEventCount = 0
                finishErrorMessage = nil
                syncStatus = "本场已放弃"
            }
        } catch {
            AICaddieLog.storage.error("Round discard failed: \(String(describing: error), privacy: .public)")
            finishErrorMessage = "本地记录无法删除，请重试"
        }
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
        endPrepBackgroundTask()
        resumePrepCourseDownloads(retryFailed: true)
        guard !eventSyncSuppressedForUITests, let package else { return }
        let mayHavePendingMedia = (try? offlineStore.loadPendingMedia(
            roundId: package.roundId
        ).isEmpty) != true
        guard pendingEventCount > 0 || mayHavePendingMedia else { return }
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
                    roundId: package.roundId,
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
        roundId: String,
        syncClient: SyncClient
    ) async throws -> SyncResult {
        let result = try await syncClient.postEventBatchWithRetry(
            events,
            roundId: roundId,
            idempotencyKey: idempotencyKey(roundId: roundId, events: events)
        )
        let expected = events.map(\.eventId)
        let acknowledged = result.acceptedEventIds + result.duplicateEventIds
        guard Set(expected).count == expected.count,
              Set(acknowledged) == Set(expected),
              acknowledged.count == expected.count else {
            throw LiveRoundFinishError.incompleteAcknowledgement
        }
        // `await` above releases the MainActor. A score recorded while this request is in flight is
        // appended after the uploaded snapshot; writing a positional sync marker behind that new
        // event would silently mark it as uploaded. Advance the watermark only while the exact tail
        // acknowledged by this response is still the complete pending tail.
        let stillPending = try offlineStore.loadPendingEvents(roundId: roundId).map(\.eventId)
        guard stillPending == expected else {
            throw LiveRoundFinishError.incompleteAcknowledgement
        }
        try offlineStore.appendSyncMarker(
            roundId: roundId,
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
        pausePrepCourseDownload()
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        if !preserveInjectedSyncClient {
            self.syncClient = apiBaseURL.map { SyncClient(baseURL: $0, adminToken: adminToken) }
        }
        self.mediaUploadClient = apiBaseURL.map { MediaUploadClient(baseURL: $0, adminToken: adminToken) }
        syncConfigToWatch()
        startPrepCourseDownloadQueueIfNeeded()
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

    // MARK: - Prep course library / resumable downloads

    private func restorePrepCourseDownloadsFromDisk() {
        let restored = (try? offlineStore.loadPrepCourseDownloads()) ?? []
        prepCourseDownloads = restored.map { record in
            guard record.isActive else { return record }
            var resumable = record
            resumable.phase = .queued
            resumable.errorText = nil
            return resumable
        }
        persistPrepCourseDownloads()
    }

    private func persistPrepCourseDownloads() {
        prepCourseDownloads.sort { $0.updatedAt > $1.updatedAt }
        do {
            try offlineStore.savePrepCourseDownloads(prepCourseDownloads)
        } catch {
            AICaddieLog.storage.error(
                "Prep course download state save failed: \(String(describing: error), privacy: .public)"
            )
        }
    }

    private func updatePrepCourseDownload(
        id: String,
        generation: UUID? = nil,
        _ update: (inout PrepCourseDownloadRecord) -> Void
    ) {
        if let generation, prepCourseDownloadGeneration != generation { return }
        guard let index = prepCourseDownloads.firstIndex(where: { $0.id == id }) else { return }
        update(&prepCourseDownloads[index])
        prepCourseDownloads[index].updatedAt = Date()
        persistPrepCourseDownloads()
    }

    private func readyPrepTemplate(for record: PrepCourseDownloadRecord) -> LiveRoundPackage? {
        guard let template = try? offlineStore.loadCourseTemplate(
            globalId: record.course.globalId,
            teeBox: record.teeBox,
            nine: record.nine
        ), template.hasCompleteOfflineCoursePrep,
              offlineStore.hasCourseTopoImages(for: template) else { return nil }
        return template
    }

    /// Selecting a catalogue result creates/reattaches to one app-owned job before navigation.
    /// Reopening the same course never replaces a running task or discards its per-hole progress.
    public func downloadPrepCourse(_ course: MobileCourseOption) {
        let teeBox = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedTee = teeBox?.isEmpty == false ? teeBox! : "blue"
        let id = PrepCourseDownloadRecord.key(
            globalId: course.globalId,
            teeBox: resolvedTee,
            nine: "all"
        )
        if let existing = prepCourseDownloads.first(where: { $0.id == id }) {
            if readyPrepTemplate(for: existing) != nil {
                updatePrepCourseDownload(id: id) { record in
                    record.phase = .ready
                    record.preparedHoles = record.totalHoles
                    record.downloadedHoles = record.totalHoles
                    record.errorText = nil
                }
                return
            }
            if existing.id == activePrepCourseDownloadID {
                return
            }
            if existing.phase == .queued {
                startPrepCourseDownloadQueueIfNeeded()
                return
            }
            updatePrepCourseDownload(id: id) { record in
                record.phase = .queued
                record.errorText = nil
            }
        } else {
            prepCourseDownloads.append(PrepCourseDownloadRecord(
                course: course,
                teeBox: resolvedTee,
                totalHoles: course.resolvedHoles
            ))
            persistPrepCourseDownloads()
        }
        startPrepCourseDownloadQueueIfNeeded()
    }

    public func retryPrepCourseDownload(id: String) {
        updatePrepCourseDownload(id: id) { record in
            record.phase = .queued
            record.errorText = nil
        }
        startPrepCourseDownloadQueueIfNeeded()
    }

    private func resumePrepCourseDownloads(retryFailed: Bool) {
        guard syncClient != nil else { return }
        var changed = false
        for index in prepCourseDownloads.indices {
            if prepCourseDownloads[index].id == activePrepCourseDownloadID,
               prepCourseDownloadTask != nil {
                continue
            }
            let phase = prepCourseDownloads[index].phase
            if phase == .preparing || phase == .downloading || (retryFailed && phase == .failed) {
                prepCourseDownloads[index].phase = .queued
                prepCourseDownloads[index].errorText = nil
                changed = true
            }
        }
        if changed { persistPrepCourseDownloads() }
        startPrepCourseDownloadQueueIfNeeded()
    }

    private func pausePrepCourseDownload() {
        prepCourseDownloadTask?.cancel()
        prepCourseDownloadTask = nil
        prepCourseDownloadGeneration = nil
        if let id = activePrepCourseDownloadID {
            updatePrepCourseDownload(id: id) { record in
                record.phase = .queued
                record.errorText = nil
            }
        }
        activePrepCourseDownloadID = nil
        endPrepBackgroundTask()
    }

    private func startPrepCourseDownloadQueueIfNeeded() {
        guard prepCourseDownloadTask == nil, syncClient != nil,
              prepCourseDownloads.contains(where: { $0.phase == .queued }) else { return }
        let generation = UUID()
        prepCourseDownloadGeneration = generation
        prepCourseDownloadTask = Task { [weak self] in
            await self?.processPrepCourseDownloadQueue(generation: generation)
        }
    }

    private func processPrepCourseDownloadQueue(generation: UUID) async {
        while !Task.isCancelled, prepCourseDownloadGeneration == generation,
              let next = prepCourseDownloads
                .filter({ $0.phase == .queued })
                .sorted(by: { $0.updatedAt > $1.updatedAt })
                .first {
            activePrepCourseDownloadID = next.id
            await runPrepCourseDownload(id: next.id, generation: generation)
            guard prepCourseDownloadGeneration == generation else { return }
            activePrepCourseDownloadID = nil
        }
        guard prepCourseDownloadGeneration == generation else { return }
        prepCourseDownloadGeneration = nil
        prepCourseDownloadTask = nil
        endPrepBackgroundTask()
    }

    /// iOS grants a bounded grace period after the app enters the background. Use it to finish the
    /// current requests and persist each completed hole. If the system expires that time, move the
    /// job back to queued instead of reporting a failure; server-side geometry/topo preparation
    /// continues and foreground resume picks up only the missing holes.
    public func continuePrepDownloadsInBackground() {
        guard prepCourseDownloadTask != nil || prepCourseDownloads.contains(where: \.isActive) else {
            return
        }
        #if canImport(UIKit)
        guard prepBackgroundTaskIdentifier == .invalid else { return }
        prepBackgroundTaskIdentifier = UIApplication.shared.beginBackgroundTask(
            withName: "Prepare golf course maps"
        ) { [weak self] in
            Task { @MainActor in
                self?.pausePrepCourseDownload()
            }
        }
        #endif
    }

    private func endPrepBackgroundTask() {
        #if canImport(UIKit)
        guard prepBackgroundTaskIdentifier != .invalid else { return }
        UIApplication.shared.endBackgroundTask(prepBackgroundTaskIdentifier)
        prepBackgroundTaskIdentifier = .invalid
        #endif
    }

    private func runPrepCourseDownload(id: String, generation: UUID) async {
        guard prepCourseDownloadGeneration == generation,
              let syncClient,
              let record = prepCourseDownloads.first(where: { $0.id == id }) else { return }
        updatePrepCourseDownload(id: id, generation: generation) { state in
            state.phase = .preparing
            state.errorText = nil
        }
        do {
            let fetched = try await syncClient.fetchCoursePackage(
                globalId: record.course.globalId,
                roundId: "prep-library-\(record.course.globalId)",
                teeBox: record.teeBox,
                nine: record.nine,
                ensureGeometry: false,
                backgroundGeometry: true,
                includeEventCursor: false
            ).replacingCourseDisplayName(record.course.name)
            guard !Task.isCancelled,
                  prepCourseDownloadGeneration == generation else { throw CancellationError() }
            try offlineStore.saveCourseTemplate(fetched)
            updatePrepCourseDownload(id: id, generation: generation) { state in
                state.totalHoles = max(1, fetched.holes.count)
            }
            await downloadOfflineCourseAssets(
                for: fetched,
                using: syncClient,
                prepDownloadID: id,
                prepDownloadGeneration: generation
            )
            guard !Task.isCancelled,
                  prepCourseDownloadGeneration == generation else { throw CancellationError() }
            if let current = prepCourseDownloads.first(where: { $0.id == id }),
               readyPrepTemplate(for: current) != nil {
                updatePrepCourseDownload(id: id, generation: generation) { state in
                    state.phase = .ready
                    state.preparedHoles = state.totalHoles
                    state.downloadedHoles = state.totalHoles
                    state.errorText = nil
                }
            } else {
                updatePrepCourseDownload(id: id, generation: generation) { state in
                    state.phase = .failed
                    state.errorText = "精确地图仍在准备，点下载可继续"
                }
            }
        } catch is CancellationError {
            updatePrepCourseDownload(id: id, generation: generation) { state in
                state.phase = .queued
                state.errorText = nil
            }
        } catch {
            if Task.isCancelled {
                updatePrepCourseDownload(id: id, generation: generation) { state in
                    state.phase = .queued
                    state.errorText = nil
                }
            } else {
                updatePrepCourseDownload(id: id, generation: generation) { state in
                    state.phase = .failed
                    state.errorText = "下载中断，点下载继续"
                }
                AICaddieLog.network.error(
                    "Prep course download failed for \(record.course.globalId, privacy: .public): \(String(describing: error), privacy: .public)"
                )
            }
        }
    }

    /// Search the provider-wide catalogue without installing anything. The picker keeps these rows
    /// ephemeral until the player explicitly selects one; only that selected course enters the
    /// durable prep library above.
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
        // Deterministic regression seam for the exact cold-release race: while Tee authority is in
        // flight, Start must remain disabled instead of launching a second request into the same
        // connection queue. It is absent from Release/TestFlight.
        if let rawDelay = ProcessInfo.processInfo.environment["UITEST_COURSE_TEES_DELAY_MS"],
           let delayMS = UInt64(rawDelay), delayMS > 0 {
            try? await Task.sleep(nanoseconds: delayMS * 1_000_000)
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
        recordUITestLatency("activate.template.begin globalId=\(nextPackage.course.globalId)")
        try? offlineStore.saveCourseTemplate(nextPackage)
        recordUITestLatency("activate.template.end globalId=\(nextPackage.course.globalId)")
        recordUITestLatency("activate.downloaded-options.begin globalId=\(nextPackage.course.globalId)")
        refreshDownloadedCourseOptions()
        recordUITestLatency("activate.downloaded-options.end globalId=\(nextPackage.course.globalId)")
        package = nextPackage
        recordUITestLatency("activate.package-published globalId=\(nextPackage.course.globalId)")
        recordUITestLatency("activate.restore.begin globalId=\(nextPackage.course.globalId)")
        let restored = try offlineStore.restoreLiveRoundState(roundId: nextPackage.roundId, package: nextPackage)
        recordUITestLatency("activate.restore.end globalId=\(nextPackage.course.globalId)")
        recordUITestLatency("activate.cursor-save.begin globalId=\(nextPackage.course.globalId)")
        try offlineStore.saveActiveHole(roundId: nextPackage.roundId, hole: restored.activeHole)
        recordUITestLatency("activate.cursor-save.end globalId=\(nextPackage.course.globalId)")
        liveRoundState = restored
        recordUITestLatency("activate.live-state-published globalId=\(nextPackage.course.globalId)")
        recordUITestLatency("activate.pending-events.begin globalId=\(nextPackage.course.globalId)")
        pendingEventCount = try offlineStore.loadPendingEvents(roundId: nextPackage.roundId).count
        recordUITestLatency("activate.pending-events.end globalId=\(nextPackage.course.globalId)")
        syncStatus = status
        if let watchBridge,
           let activeHole = liveRoundState?.activeHole ?? nextPackage.holes.first?.number {
            recordUITestLatency("activate.watch-seed.begin globalId=\(nextPackage.course.globalId)")
            let seed = watchBridge.makeWatchRoundSeedPayload(
                package: nextPackage,
                activeHole: activeHole
            )
            watchBridge.sendRoundSeedToWatch(seed)
            recordUITestLatency("activate.watch-seed.end globalId=\(nextPackage.course.globalId)")
        }
    }

    /// Opt-in acceptance timing only. Release/TestFlight compile this to a no-op; DEBUG writes stage
    /// names and counts (never payloads, player data or credentials) beside the simulator screenshots.
    private func recordUITestLatency(_ message: String) {
        #if DEBUG
        UITestEventLatencyTrace.record(message)
        #endif
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

    private func acceptWatchEvent(_ event: LiveRoundEvent) async throws {
        let alreadyStored = try offlineStore.containsEvent(eventId: event.eventId)
        if !alreadyStored {
            try offlineStore.appendEvent(event)
        }
        do {
            if let package, package.roundId == event.roundId {
                liveRoundState = try offlineStore.restoreLiveRoundState(roundId: event.roundId, package: package)
                pendingEventCount = try offlineStore.loadPendingEvents(roundId: event.roundId).count
            }
            syncStatus = "手表已记录"
        } catch {
            AICaddieLog.watch.error("Watch event status update failed: \(String(describing: error), privacy: .public)")
            syncStatus = "手表已记录,稍后刷新"
        }

        if package?.roundId == event.roundId {
            if !eventSyncSuppressedForUITests {
                Task { await self.syncPendingEvents() }
            }
            return
        }

        // A pre-standalone Watch build may retry its old queue after the phone has already left this
        // round. There is no active-package foreground hook left to flush it, so acknowledge the
        // Watch only after the detached round's complete local pending tail reaches the backend.
        if eventSyncSuppressedForUITests { return }
        guard let syncClient else { throw URLError(.notConnectedToInternet) }
        let pending = try offlineStore.loadPendingEvents(roundId: event.roundId)
        guard !pending.isEmpty else { return }
        _ = try await postPendingEventsAndRequireFullAcknowledgement(
            pending,
            roundId: event.roundId,
            syncClient: syncClient
        )
        if package?.roundId == event.roundId {
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: event.roundId).count
        }
        syncStatus = "手表记录已同步"
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
