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
                        startingNine: model.startingNine,
                        isPreparingRound: model.isPreparingRound,
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
                        onDiscard: {
                            model.discardActiveRound()
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
                        pendingLiveHole: model.pendingLiveHole,
                        onConsumePendingLiveHole: {
                            model.consumePendingLiveHole()
                        }
                    )
                } else {
                    NavigationStack {
                        StartRoundView(
                            courseOptions: model.courseOptions,
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
                            onConnectGarmin: { showNoPackageSettings = true }
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
            // The app has a single deliberate light visual identity (green + white cards on a
            // light gray field). Lock it to light so it never renders white-on-white in the
            // system's Dark Mode (cards are Color.white but text is semantic .primary).
            .preferredColorScheme(.light)
            .task {
                await model.bootstrap()
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

@MainActor
public final class LiveRoundAppModel: ObservableObject {
    @Published public private(set) var package: LiveRoundPackage?
    @Published public private(set) var pendingEventCount: Int = 0
    @Published public private(set) var syncStatus: String = "离线就绪"
    @Published public private(set) var apiBaseURL: URL?
    @Published public private(set) var adminToken: String?
    @Published public private(set) var isPreparingRound = false
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
    /// 本局的起始九洞(用于「移除另外 9 洞」撤销目标);随新 roundId 重置。
    @Published public private(set) var startingNine: String?
    public let watchBridge: WatchEventBridge?
    public let offlineStore: OfflineStore
    public let garminSessionStore: GarminSessionStore?

    private var syncClient: SyncClient?
    private var mediaUploadClient: MediaUploadClient?
    private let preferredRoundId: String
    /// Keeps the Apple-session observer alive so the watch's standalone-sync auth tracks sign-in /
    /// refresh / sign-out (round-13 watch-auth).
    private var sessionCancellables = Set<AnyCancellable>()

    public convenience init(
        offlineStore: OfflineStore = OfflineStore(),
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        garminSessionStore: GarminSessionStore? = GarminSessionStore(),
        preferredRoundId: String? = nil,
        syncClient: SyncClient? = nil
    ) {
        self.init(
            offlineStore: offlineStore,
            apiBaseURL: apiBaseURL,
            adminToken: adminToken,
            watchBridge: WatchEventBridge(offlineStore: offlineStore, autoActivate: false),
            garminSessionStore: garminSessionStore,
            preferredRoundId: preferredRoundId,
            syncClient: syncClient
        )
    }

    public init(
        offlineStore: OfflineStore = OfflineStore(),
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        watchBridge: WatchEventBridge?,
        garminSessionStore: GarminSessionStore? = GarminSessionStore(),
        preferredRoundId: String? = nil,
        syncClient: SyncClient? = nil
    ) {
        let resolvedAPIBaseURL = apiBaseURL ?? Self.defaultAPIBaseURL()
        let resolvedAdminToken = adminToken ?? Self.defaultAdminToken()
        self.offlineStore = offlineStore
        self.apiBaseURL = resolvedAPIBaseURL
        self.adminToken = resolvedAdminToken
        self.watchBridge = watchBridge
        self.garminSessionStore = garminSessionStore
        self.preferredRoundId = preferredRoundId ?? Self.defaultLiveRoundId()
        self.syncClient = syncClient ?? resolvedAPIBaseURL.map { SyncClient(baseURL: $0, adminToken: resolvedAdminToken) }
        self.mediaUploadClient = resolvedAPIBaseURL.map { MediaUploadClient(baseURL: $0, adminToken: resolvedAdminToken) }
        watchBridge?.onAcceptedLiveEvent = { [weak self] event in
            guard let self else {
                return
            }
            try await self.acceptWatchEvent(event)
        }
        watchBridge?.activateSession()
        syncConfigToWatch()
        observeSessionForWatch()
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

    public func bootstrap() async {
        defer { isBootstrapping = false }
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
                return
            }
            #if DEBUG
            // Dev/simulator + CI harness: auto-fetch the preferred round so snapshots/dev render.
            if let remotePackage = await fetchRemotePackage() {
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
        guard let syncClient else {
            return
        }
        do {
            courseOptions = try await syncClient.fetchCourseOptions().courses
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

    public func prepareRound(roundId: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "无法开始这一场,请重试"
            return
        }
        let preparedAt = Date()

        isPreparingRound = true
        defer {
            isPreparingRound = false
        }

        do {
            if let remotePackage = await fetchRemotePackage(roundId: requestedRoundId, capturedAt: preparedAt) {
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
        // 新的一局才记录起始九洞;同一 roundId 改九洞(加打/撤销)时保留撤销目标。
        let isNewRound = package?.roundId != requestedRoundId
        if isNewRound {
            startingNine = (nine == "all") ? nil : nine
        }
        let preparedAt = Date()

        isPreparingRound = true
        defer {
            isPreparingRound = false
        }

        do {
            if let remotePackage = await fetchRemoteCoursePackage(globalId: globalId, roundId: requestedRoundId, teeBox: teeBox, nine: nine, capturedAt: preparedAt) {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "已下载离线")
                if isNewRound { signalFreshRoundEntry() }
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                // Persist the active-round pointer for the offline/cached start too, so a round
                // started without network still resumes on relaunch (continue card survives quit).
                try offlineStore.saveRoundPackage(cachedPackage)
                try activatePackage(cachedPackage, status: "已下载离线")
                if isNewRound { signalFreshRoundEntry() }
            } else {
                syncStatus = "暂时无法开始,稍后重试"
            }
        } catch {
            AICaddieLog.network.error("Course package prepare failed: \(String(describing: error), privacy: .public)")
            syncStatus = "开始失败,稍后重试"
        }
    }

    /// After a fresh round is prepared, point the UI at its first hole so it enters the live screen.
    private func signalFreshRoundEntry() {
        pendingLiveHole = liveRoundState?.activeHole ?? package?.holes.first?.number
    }

    /// 组合 18 洞:本环(1–9)+ 第二个环(10–18)。两个环各是独立 CourseView 球场,后端合并成一局。
    /// 组合局已是 18 洞,不设「移除九洞」撤销目标(startingNine 保持 nil)。
    public func prepareCompositeRound(globalId: Int, backGlobalId: Int, roundId: String, teeBox: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "无法开始这一场,请重试"
            return
        }
        let isNewRound = package?.roundId != requestedRoundId
        if isNewRound {
            startingNine = nil
        }
        let preparedAt = Date()
        isPreparingRound = true
        defer {
            isPreparingRound = false
        }
        do {
            if let remotePackage = await fetchRemoteCompositePackage(globalId: globalId, backGlobalId: backGlobalId, roundId: requestedRoundId, teeBox: teeBox, capturedAt: preparedAt) {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "已下载离线")
                if isNewRound { signalFreshRoundEntry() }
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                // Persist the active-round pointer for the offline/cached start too, so a round
                // started without network still resumes on relaunch (continue card survives quit).
                try offlineStore.saveRoundPackage(cachedPackage)
                try activatePackage(cachedPackage, status: "已下载离线")
                if isNewRound { signalFreshRoundEntry() }
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

    /// Cancel/discard the active round without recording it: forget it locally and return
    /// to 开始一场 (package = nil). Nothing for this round syncs afterwards.
    public func discardActiveRound() {
        guard let roundId = package?.roundId else {
            return
        }
        try? offlineStore.discardRound(roundId: roundId)
        package = nil
        liveRoundState = nil
        startingNine = nil
        pendingEventCount = 0
        syncStatus = "已结束本场"
    }

    public func handleEvent(_ event: LiveRoundEvent) {
        do {
            try offlineStore.appendEvent(event)
            if let package, package.roundId == event.roundId {
                liveRoundState = try offlineStore.restoreLiveRoundState(roundId: event.roundId, package: package)
            }
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: event.roundId).count
            syncStatus = "已保存"
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
        guard package != nil, pendingEventCount > 0 else {
            return
        }
        Task { await self.syncPendingEvents() }
    }

    public func syncPendingEvents() async {
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
                let result = try await syncClient.postEventBatchWithRetry(
                    events,
                    roundId: package.roundId,
                    idempotencyKey: idempotencyKey(roundId: package.roundId, events: events)
                )
                try offlineStore.appendSyncMarker(roundId: package.roundId, timestamp: ISO8601DateFormatter().string(from: Date()), result: result)
                _ = try? await syncClient.ackEventCursor(roundId: package.roundId, serverSequence: result.serverSequence)
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

    /// round-12 sync spine (gap f): pull events authored by OTHER clients via the replay endpoint and
    /// merge them into the local event log (idempotent by eventId), then re-project the round state.
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
            var batchPersisted = true
            for item in replay.events {
                let alreadyLocal = (try? offlineStore.containsEvent(eventId: item.event.eventId)) ?? false
                if !alreadyLocal {
                    do {
                        try offlineStore.appendEvent(item.event)
                        appliedAny = true
                    } catch {
                        // P1-2: a local append failed — do NOT advance/ack past it, or the server treats
                        // these events as delivered and never resends them (permanent on-disk loss).
                        batchPersisted = false
                        break
                    }
                }
            }
            // Only advance the cursor for a fully-persisted batch; ack below covers just what's durable.
            if !batchPersisted { break }
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
                try offlineStore.attachUploadedMediaId(eventId: media.eventId, mediaId: uploadResponse.media.id)
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
        // Baked at build time for the single-owner TestFlight build (Info.plist
        // AICaddieAdminToken = $(AI_CADDIE_ADMIN_TOKEN)); empty/unexpanded → nil.
        return sanitizedConfigurationValue(Bundle.main.object(forInfoDictionaryKey: "AICaddieAdminToken") as? String)
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

    private func fetchRemotePackage(roundId: String, capturedAt: Date = Date()) async -> LiveRoundPackage? {
        guard let syncClient else {
            syncStatus = "未联网,稍后同步"
            return nil
        }
        do {
            return try await syncClient.fetchRoundPackage(roundId: roundId, capturedAt: capturedAt)
        } catch {
            AICaddieLog.network.error("Round package fetch failed (using cache): \(String(describing: error), privacy: .public)")
            syncStatus = "离线中,使用已保存数据"
            return nil
        }
    }

    private func fetchRemoteCoursePackage(globalId courseGlobalId: Int, roundId: String, teeBox: String, nine: String = "all", capturedAt: Date = Date()) async -> LiveRoundPackage? {
        guard let syncClient else {
            syncStatus = "未联网,稍后同步"
            return nil
        }
        do {
            return try await syncClient.fetchCoursePackage(globalId: courseGlobalId, roundId: roundId, teeBox: teeBox, nine: nine, capturedAt: capturedAt, ensureGeometry: true)
        } catch {
            AICaddieLog.network.error("Course package fetch failed (using cache): \(String(describing: error), privacy: .public)")
            syncStatus = "离线中,使用已保存数据"
            return nil
        }
    }

    private func fetchRemoteCompositePackage(globalId courseGlobalId: Int, backGlobalId: Int, roundId: String, teeBox: String, capturedAt: Date = Date()) async -> LiveRoundPackage? {
        guard let syncClient else {
            syncStatus = "未联网,稍后同步"
            return nil
        }
        do {
            return try await syncClient.fetchCoursePackage(globalId: courseGlobalId, roundId: roundId, teeBox: teeBox, nine: "all", capturedAt: capturedAt, ensureGeometry: true, backGlobalId: backGlobalId)
        } catch {
            AICaddieLog.network.error("Course package fetch failed (using cache): \(String(describing: error), privacy: .public)")
            syncStatus = "离线中,使用已保存数据"
            return nil
        }
    }

    private func activatePackage(_ nextPackage: LiveRoundPackage, status: String) throws {
        package = nextPackage
        liveRoundState = try offlineStore.restoreLiveRoundState(roundId: nextPackage.roundId, package: nextPackage)
        pendingEventCount = try offlineStore.loadPendingEvents(roundId: nextPackage.roundId).count
        syncStatus = status
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
        syncStatus = status
    }

    /// Fetch the home package = most-played course's data (for the Hub's choices + 上一场 +
    /// 复盘 count). Falls back to the cached home package offline. Geometry not needed here.
    private func fetchHomePackage() async -> LiveRoundPackage? {
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
                ensureGeometry: false
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
}
