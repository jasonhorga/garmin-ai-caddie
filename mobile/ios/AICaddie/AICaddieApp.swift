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
                        localEventUploadStatus: model.localEventUploadStatus,
                        garminSyncStatus: model.garminSyncStatus,
                        lastGarminSyncAt: model.lastGarminSyncAt,
                        isGarminSyncing: model.isGarminSyncing,
                        apiBaseURL: model.apiBaseURL,
                        adminToken: model.adminToken,
                        adminTokenConfigured: model.adminTokenConfigured,
                        offlineStore: model.offlineStore,
                        sessionStore: model.garminSessionStore,
                        watchBridge: model.watchBridge,
                        liveRoundState: model.liveRoundState,
                        pendingWatchRoundStart: model.pendingWatchRoundStart,
                        courseOptions: model.courseOptions,
                        downloadedCourseOptions: model.downloadedCourseOptions,
                        downloadedCourseKeys: model.downloadedCourseKeys,
                        prepCourseDownloads: model.prepCourseDownloads,
                        prepCourseDownloadPresentation: model.prepCourseDownloadPresentation,
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
                        onDiscardRound: {
                            model.discardActiveRound()
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
                                await model.syncGarminData()
                            }
                        },
                        onGarminSessionImported: {
                            await model.syncGarminData()
                        },
                        onRefreshGarminSyncStatus: {
                            await model.refreshGarminSyncPresentation()
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
                        onSearchCourses: { name, city, latitude, longitude in
                            try await model.searchCourses(
                                name: name,
                                city: city,
                                latitude: latitude,
                                longitude: longitude
                            )
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
                        onValidateReadyPrepCourse: { record in
                            await model.validateReadyPrepCourse(record)
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
                            onSearchCourses: { name, city, latitude, longitude in
                                try await model.searchCourses(
                                    name: name,
                                    city: city,
                                    latitude: latitude,
                                    longitude: longitude
                                )
                            },
                            onNearbyCourses: { latitude, longitude, radiusKm in
                                try await model.nearbyCourses(
                                    latitude: latitude,
                                    longitude: longitude,
                                    radiusKm: radiusKm
                                )
                            }
                        )
                        .safeAreaInset(edge: .top, spacing: 0) {
                            if let pending = model.pendingWatchRoundStart {
                                HubPendingWatchCard(
                                    courseName: pending.courseName,
                                    activeHole: pending.activeHole
                                )
                                .padding(.horizontal, 16)
                                .padding(.top, 8)
                                .padding(.bottom, 4)
                                .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
                                .accessibilityIdentifier("no-package-watch-round-pending")
                            }
                        }
                        .disabled(model.pendingWatchRoundStart != nil)
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
                        GarminSessionView(
                            apiBaseURL: model.apiBaseURL,
                            adminToken: model.adminToken,
                            sessionStore: model.garminSessionStore,
                            onSessionImported: { await model.syncGarminData() }
                        )
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

/// Live, read-only presentation stream for the app-owned prep queue. The queue and its disk file
/// remain authoritative in `LiveRoundAppModel`; this stable reference only lets a destination that
/// SwiftUI has already pushed observe later per-hole progress without relying on a captured array.
@MainActor
public final class PrepCourseDownloadPresentationState: ObservableObject {
    @Published public private(set) var downloads: [PrepCourseDownloadRecord]

    public init(downloads: [PrepCourseDownloadRecord] = []) {
        self.downloads = downloads
    }

    fileprivate func replace(with downloads: [PrepCourseDownloadRecord]) {
        self.downloads = downloads
    }

    /// Publish the player's selection before the detail destination is pushed. This is only a
    /// presentation mirror; `LiveRoundAppModel.downloadPrepCourse` remains the queue/disk authority
    /// and immediately replaces this row with its persisted state.
    fileprivate func retainSelection(_ course: MobileCourseOption) {
        let record = PrepCourseDownloadRecord(course: course)
        guard !downloads.contains(where: { $0.id == record.id }) else { return }
        downloads.insert(record, at: 0)
    }
}

@MainActor
public final class LiveRoundAppModel: ObservableObject {
    @Published public private(set) var package: LiveRoundPackage?
    @Published public private(set) var pendingEventCount: Int = 0
    @Published public private(set) var syncStatus: String = "离线就绪"
    @Published public private(set) var localEventUploadStatus: String = "自动上传已开启"
    @Published public private(set) var garminSyncStatus: String = "尚未手动更新"
    @Published public private(set) var lastGarminSyncAt: Date?
    @Published public private(set) var isGarminSyncing = false
    /// Monotonic guard for an async status read that started before a user-initiated pull. Without it,
    /// the old server status can land after a successful pull and repaint the UI as "failed".
    private var garminSyncPresentationGeneration = 0
    /// The server status endpoint may lag a completed pull by a few seconds. Keep the local terminal
    /// result authoritative during that handoff instead of repainting it with the previous run.
    private var garminSyncPresentationLockedUntil: Date?
    /// Login completion, foreground refresh and the manual button share one in-flight operation.
    /// This prevents duplicate Garmin jobs and avoids reporting a coalesced call as a failure.
    private var garminSyncTask: Task<Bool, Never>?
    /// A cancelled/account-scoped sync must not clear or repaint a newer account's operation when
    /// its URLSession continuation eventually unwinds.
    private var garminSyncOperationGeneration = 0
    /// Server status can lag the POST response. This local watermark keeps an older `/sync/status`
    /// payload from replacing a newer terminal result after the short presentation lock expires.
    private var garminSyncPresentationWatermark: Date?
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
    /// A Watch-created round can arrive before its richer course package. Keep that fact visible on
    /// the Hub instead of making the phone look idle while the bounded package retry is running.
    @Published public private(set) var pendingWatchRoundStart: WatchRoundStartPayload? = nil
    @Published public private(set) var courseOptions: [MobileCourseOption] = []
    @Published public private(set) var downloadedCourseOptions: [MobileCourseOption] = []
    @Published public private(set) var downloadedCourseKeys: Set<String> = []
    public let prepCourseDownloadPresentation = PrepCourseDownloadPresentationState()
    @Published public private(set) var prepCourseDownloads: [PrepCourseDownloadRecord] = [] {
        didSet {
            prepCourseDownloadPresentation.replace(with: prepCourseDownloads)
        }
    }
    /// 本局的起始九洞(用于「移除另外 9 洞」撤销目标);随新 roundId 重置。
    @Published public private(set) var startingNine: String?
    public let watchBridge: WatchEventBridge?
    public let offlineStore: OfflineStore
    public let garminSessionStore: GarminSessionStore?

    private var syncClient: SyncClient?
    private var mediaUploadClient: MediaUploadClient?
    private var isSyncingPendingEvents = false
    private var watchFinishedRoundReconciliationTask: Task<Void, Never>?
    /// Round-start relays can arrive twice (immediate message + background userInfo). Keep only the
    /// in-flight IDs here so the second delivery does not launch a competing package fetch.
    private var watchRoundStartInFlight = Set<String>()
    /// Keep a transient Watch-created round visible to the phone until its course package request
    /// succeeds. The Watch has its own durable relay; this bounded retry closes the gap where the
    /// phone receives that relay but is briefly offline.
    private var watchRoundStartRetryTasks: [String: Task<Void, Never>] = [:]
    private static let watchRoundStartRetryDelaysNanoseconds: [UInt64] = [
        2_000_000_000,
        5_000_000_000,
        10_000_000_000,
    ]
    private var deferredRoundFinishTask: Task<Void, Never>?
    private var deferredRoundFinishGeneration: UUID?
    private var deferredRoundFinishRetryRequested = false
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
    /// Optional DEBUG/CI round to open explicitly. Production and ordinary DEBUG launches must not
    /// invent a demo round: with no configured id bootstrap lands on the normal home package.
    private let preferredRoundId: String?
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
            2_000_000_000, 3_000_000_000, 5_000_000_000, 8_000_000_000,
            12_000_000_000, 20_000_000_000, 30_000_000_000, 45_000_000_000,
            60_000_000_000, 60_000_000_000,
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
            2_000_000_000, 3_000_000_000, 5_000_000_000, 8_000_000_000,
            12_000_000_000, 20_000_000_000, 30_000_000_000, 45_000_000_000,
            60_000_000_000, 60_000_000_000,
        ]
    ) {
        let resolvedAPIBaseURL = apiBaseURL ?? Self.defaultAPIBaseURL()
        let resolvedAdminToken = adminToken ?? Self.defaultAdminToken()
        self.offlineStore = offlineStore
        self.apiBaseURL = resolvedAPIBaseURL
        self.adminToken = resolvedAdminToken
        self.watchBridge = watchBridge
        self.garminSessionStore = garminSessionStore
        let requestedRoundId = preferredRoundId?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.preferredRoundId = requestedRoundId?.isEmpty == false
            ? requestedRoundId
            : Self.configuredLiveRoundId()
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
        watchBridge?.onRoundStarted = { [weak self] start in
            Task { @MainActor in
                await self?.handleWatchRoundStart(start)
            }
        }
        watchBridge?.activateSession()
        syncConfigToWatch()
        observeSessionForWatch()
        restorePrepCourseDownloadsFromDisk()
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
        watchRoundStartRetryTasks.values.forEach { $0.cancel() }
        watchRoundStartRetryTasks.removeAll()
        deferredRoundFinishTask?.cancel()
        deferredRoundFinishTask = nil
        deferredRoundFinishGeneration = nil
        deferredRoundFinishRetryRequested = false
        garminSyncTask?.cancel()
        garminSyncTask = nil
        garminSyncOperationGeneration += 1
        garminSyncPresentationLockedUntil = nil
        garminSyncPresentationWatermark = nil
        garminSyncPresentationGeneration += 1
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
        pendingWatchRoundStart = nil
        pendingEventCount = 0
        pendingLiveHole = nil
        startingNine = nil
        courseOptions = []
        selectedCourseDisplayNames = [:]
        courseOptionsRefreshSucceeded = false
        syncStatus = "离线就绪"
        localEventUploadStatus = "自动上传已开启"
        garminSyncStatus = "尚未手动更新"
        lastGarminSyncAt = nil
        isBootstrapping = true
        restorePrepCourseDownloadsFromDisk()
        refreshDownloadedCourseOptions()
        syncConfigToWatch()
    }

    public func bootstrap() async {
        defer {
            isBootstrapping = false
            resumePrepCourseDownloads(retryFailed: true)
            retryDeferredRoundFinishes()
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

    public func refreshGarminSyncPresentation() async {
        // A user-initiated pull owns the visible state until it completes. A background status
        // read can otherwise race the request and put the previous `ready` result back on screen
        // while the spinner is still running.
        guard !isGarminSyncing else { return }
        if let lockedUntil = garminSyncPresentationLockedUntil,
           lockedUntil > Date() {
            return
        }
        let generation = garminSyncPresentationGeneration
        guard let syncClient,
              let status = try? await syncClient.fetchGarminSyncStatus(),
              let lastRun = status.lastRun else { return }
        guard !isGarminSyncing, generation == garminSyncPresentationGeneration else { return }
        let serverDate = lastRun.updatedAt.flatMap { ISO8601DateFormatter().date(from: $0) }
        // A completed local pull is authoritative until the server exposes an equally-new (or
        // newer) run. Without this check an old error/running row can arrive after the POST has
        // returned ready and repaint the settings page with a false failure.
        if let watermark = garminSyncPresentationWatermark {
            guard let serverDate, serverDate >= watermark else { return }
        }
        if let serverDate {
            garminSyncPresentationWatermark = serverDate
            // `lastGarminSyncAt` is explicitly a last-success timestamp. An error or running
            // status may have a newer updatedAt, but must never be presented as "上次成功".
            if lastRun.state == "ready" {
                lastGarminSyncAt = serverDate
            }
        }
        switch lastRun.state {
        case "ready":
            garminSyncStatus = lastRun.newRoundCount == 0
                ? "Garmin 已同步，暂无新球局"
                : "Garmin 数据已更新"
        case "running", "syncing":
            garminSyncStatus = "Garmin 同步正在进行"
        case "reauth_required":
            garminSyncStatus = "Garmin 登录已过期，请重新连接"
        case "error":
            garminSyncStatus = "上次 Garmin 拉取失败"
        default:
            break
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
        // A Watch can create a round while the phone has no configured backend. Once the user
        // supplies the endpoint, immediately consume that durable start fact instead of waiting for
        // another WCSession delivery or a manual app restart.
        if let pendingWatchRoundStart {
            await handleWatchRoundStart(pendingWatchRoundStart)
        }
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

    /// Test-only cleanup for a validation test that deliberately queues a replacement download.
    /// Production callers use the foreground/background lifecycle methods instead.
    func cancelPrepCourseDownloadForTesting() async {
        let task = prepCourseDownloadTask
        pausePrepCourseDownload()
        await task?.value
    }
    #endif

    private func offlinePrepKey(globalId: Int, localHole: Int) -> String {
        "\(globalId):\(localHole)"
    }

    private func courseInstallBackGlobalId(for snapshot: LiveRoundPackage) -> Int? {
        let primaryGlobalId = snapshot.course.globalId
        return snapshot.holes
            .map { $0.sourceGlobalId ?? primaryGlobalId }
            .first { $0 != primaryGlobalId }
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
        let backGlobalId = courseInstallBackGlobalId(for: cached)
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
        prepDownloadGeneration: UUID? = nil,
        deferTemplateReplacement: Bool = false
    ) async -> Bool {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return false
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
                // During a release replacement the last-known-good template remains the live-round
                // fallback. The replacement package is staged in memory and written only after all
                // precise facts and topo bytes have arrived.
                if !deferTemplateReplacement {
                    try offlineStore.saveCourseTemplate(assembledSnapshot())
                }
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

        var serverInstallStatusAvailable = false
        var serverGeometryReadyKeys = Set<String>()
        var serverTopoReadyKeys = Set<String>()
        var serverInstallPhase: String?

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
                let key = offlinePrepKey(globalId: globalId, localHole: localHole)
                guard offlinePrepIsPrecise(prep),
                      (prepDownloadID == nil
                        || !serverInstallStatusAvailable
                        || serverTopoReadyKeys.contains(key)),
                      offlineStore.loadCourseTopoImageURL(
                          globalId: globalId,
                          localHole: localHole,
                          geometryRevision: revision
                      ) == nil else { return nil }
                return (globalId, localHole, revision)
            }
            // Keep the card the player opens first ahead of throughput work. Starting holes 1 and
            // 2 concurrently made the second request win the scheduler occasionally, so a wholly
            // cold course gets one priority bitmap first. Once any map is durable, later incremental
            // passes use the bounded two-hole window immediately instead of serialising a new hole.
            let needsPriorityLane = prepDownloadID == nil && downloadedHoleCount() == 0
            var readyIndex = 0
            while readyIndex < ready.count {
                guard !Task.isCancelled else { return }
                let window = readyIndex == 0 && needsPriorityLane ? 1 : 2
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
        // New servers expose a durable per-hole install journal. When it is available, use it as
        // the geometry scheduler instead of repeatedly rebuilding partial prep payloads while the
        // server is still decoding Garmin ZIPs. Older servers simply fall back to the existing
        // coverage probe path.
        func refreshServerInstallStatus() async {
            let status: CourseInstallStatus?
            let primaryGlobalId = snapshot.course.globalId
            let backGlobalId = courseInstallBackGlobalId(for: snapshot)
            do {
                status = try await syncClient.fetchCourseInstallStatus(
                    globalId: primaryGlobalId,
                    teeBox: snapshot.course.teeBox,
                    nine: snapshot.nine ?? "all",
                    backGlobalId: backGlobalId
                )
            } catch {
                return
            }
            guard let status else { return }
            serverInstallStatusAvailable = true
            serverInstallPhase = status.phase.lowercased()
            serverGeometryReadyKeys = Set(status.holes.compactMap { row in
                row.geometry.caseInsensitiveCompare("ready") == .orderedSame
                    ? offlinePrepKey(globalId: row.globalId, localHole: row.localHole)
                    : nil
            })
            serverTopoReadyKeys = Set(status.holes.compactMap { row in
                row.topo.caseInsensitiveCompare("ready") == .orderedSame
                    ? offlinePrepKey(globalId: row.globalId, localHole: row.localHole)
                    : nil
            })
        }
        await refreshServerInstallStatus()
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
                guard !Task.isCancelled else { return false }
                guard let roundHoles = groups[globalId] else { continue }
                let localHoles = Array(Set(roundHoles.map {
                    $0.sourceLocalHole ?? $0.number
                })).sorted()
                let requested = localHoles.filter { localHole in
                    let key = offlinePrepKey(globalId: globalId, localHole: localHole)
                    let prep = prepBySource[key]
                    let geometryReady = geometryReadyKeys.contains(key)
                        || serverGeometryReadyKeys.contains(key)
                    // Fetch missing lightweight facts immediately.  Once a partial response exists,
                    // wait on the cheap coverage endpoint and rebuild it exactly once when geometry
                    // becomes ready instead of repeatedly paying for the same partial prep.
                    // The durable journal is a prep-throughput scheduler only. Live play must still
                    // fetch its first factual row immediately while server geometry is cold.
                    if prepDownloadID != nil && serverInstallStatusAvailable && !geometryReady {
                        return false
                    }
                    return prep?.resolvedMapOverlay == nil
                        || (geometryReady && !offlinePrepIsPrecise(prep))
                }
                guard !requested.isEmpty else { continue }
                // Live play keeps its first hole as a latency-critical singleton. Pre-round prep
                // cannot be opened until all holes are installed, so it uses the bounded two-lane
                // throughput path from the beginning instead of serialising a map nobody can view.
                var index = 0
                if prepDownloadID == nil {
                    batchRequests.append(OfflinePrepBatchRequest(
                        globalId: globalId,
                        localHoles: [requested[0]]
                    ))
                    index = 1
                }
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
            if prepDownloadID == nil, let priorityRequest = batchRequests.first {
                let priorityResults = await fetchOfflinePrepBatches(
                    [priorityRequest],
                    using: syncClient,
                    maximumConcurrentRequests: 1
                )
                guard !Task.isCancelled else { return false }
                retainPrepBatchResults(priorityResults)
                for prep in priorityResults.flatMap(\.holes) where offlinePrepIsPrecise(prep) {
                    geometryReadyKeys.insert(offlinePrepKey(
                        globalId: priorityRequest.globalId,
                        localHole: prep.hole
                    ))
                }
                persistPrepBatchProgress()
                await downloadNewlyReadyTopoHoles()
                guard !Task.isCancelled else { return false }
                batchRequests.removeFirst()
            }

            let batchResults = await fetchOfflinePrepBatches(batchRequests, using: syncClient)
            guard !Task.isCancelled else { return false }
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
            guard !Task.isCancelled else { return false }
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
            await refreshServerInstallStatus()
            do {
                try await Task.sleep(nanoseconds: retryDelays[attempt])
            } catch {
                return false
            }
            guard !Task.isCancelled else { return false }
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
                guard !Task.isCancelled else { return false }
            }
        }

        guard !Task.isCancelled else { return false }
        let enriched = assembledSnapshot()

        // Course facts and topo bitmaps have independent durability. Persist the precise per-hole
        // facts before starting the potentially long bitmap pass; otherwise a force-quit after the
        // visible first-hole topo succeeds can restore the old partial package and never select the
        // already-cached precise image. The downloaded-course list still requires every bitmap, so
        // this early save cannot falsely advertise that the whole course is offline-ready.
        do {
            let durableEnriched = preservingForegroundPrecisePrep(in: enriched)
            if !deferTemplateReplacement {
                try offlineStore.saveCourseTemplate(durableEnriched)
            }
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

        let topoRetryDelays: [UInt64] = prepDownloadID == nil
            ? [5_000_000_000, 10_000_000_000, 20_000_000_000]
            : retryDelays
        for attempt in 0...topoRetryDelays.count {
            guard !Task.isCancelled else { return false }
            if prepDownloadID != nil {
                await refreshServerInstallStatus()
            }
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

            // A prep download is invisible until the whole course is installed, so let the durable
            // server worker finish its single-flight render and fetch only immutable ready bytes.
            // Live play keeps the direct request path so its first visible hole is never held back.
            let fetchableTopoHoles = missingTopoHoles.filter { hole in
                prepDownloadID == nil
                    || !serverInstallStatusAvailable
                    || serverTopoReadyKeys.contains(
                        offlinePrepKey(globalId: hole.globalId, localHole: hole.localHole)
                    )
            }

            // Persist each hole as soon as it arrives. The previous all-course task group returned
            // only after every cold render completed, so killing the app on hole 1 discarded even a
            // successfully downloaded first bitmap and four renders could starve foreground APIs.
            // As above, the first still-missing map owns the foreground lane only while this course
            // has no durable topo yet; a resumed/partially complete course starts at two-wide.
            let needsPriorityLane = prepDownloadID == nil && downloadedHoleCount() == 0
            var missingIndex = 0
            while missingIndex < fetchableTopoHoles.count {
                guard !Task.isCancelled else { return false }
                let window = missingIndex == 0 && needsPriorityLane ? 1 : 2
                let end = min(missingIndex + window, fetchableTopoHoles.count)
                let downloads = await fetchOfflineTopoImages(
                    Array(fetchableTopoHoles[missingIndex..<end]),
                    using: syncClient
                )
                guard !Task.isCancelled else { return false }
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
            if prepDownloadID != nil && serverInstallStatusAvailable && serverInstallPhase == "failed" {
                break
            }
            guard stillMissing, attempt < topoRetryDelays.count else { break }
            do {
                try await Task.sleep(nanoseconds: topoRetryDelays[attempt])
            } catch {
                return false
            }
        }

        guard !Task.isCancelled else { return false }
        var replacementCompleted = false
        do {
            let durableEnriched = preservingForegroundPrecisePrep(in: enriched)
            let replacementMatchesRequiredRevisions: Bool
            if deferTemplateReplacement,
               let prepDownloadID,
               let current = prepCourseDownloads.first(where: { $0.id == prepDownloadID }) {
                replacementMatchesRequiredRevisions = templateSatisfiesRequiredGeometryRevisions(
                    durableEnriched,
                    record: current
                )
            } else {
                replacementMatchesRequiredRevisions = !deferTemplateReplacement
            }
            let replacementIsComplete = durableEnriched.hasCompleteOfflineCoursePrep
                && offlineStore.hasCourseTopoImages(for: durableEnriched)
                && replacementMatchesRequiredRevisions
            if !deferTemplateReplacement || replacementIsComplete {
                try offlineStore.saveCourseTemplate(
                    durableEnriched,
                    replacingExisting: deferTemplateReplacement
                )
                replacementCompleted = replacementIsComplete
            }
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
        return replacementCompleted
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

    /// Save & End is local-first. The tap seals the round and exits live play immediately; delivery
    /// is a durable outbox transaction that retries now and on every future foreground. Network
    /// reachability must never become a prison around the player.
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

        do {
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
            try offlineStore.sealRoundForDeferredFinish(package: package, metadata: metadata)
            try leaveSealedRoundLocally(package: package)
            watchBridge?.sendRoundClosureToWatch(
                roundId: package.roundId,
                disposition: .finished
            )
            retryDeferredRoundFinishes()
            return true
        } catch {
            AICaddieLog.storage.error("Round seal failed: \(String(describing: error), privacy: .public)")
            finishErrorMessage = "本地保存状态不可用，本场已完整保留"
            syncStatus = "本地保存失败,请重试"
            pendingEventCount = (try? offlineStore.loadPendingEvents(roundId: package.roundId).count) ?? pendingEventCount
            return false
        }
    }

    private func leaveSealedRoundLocally(package sealedPackage: LiveRoundPackage) throws {
        if let cachedHome = try offlineStore.loadHomePackage() {
            try activateHomePackage(cachedHome, status: "本场已保存 · 后台同步中")
        } else {
            package = sealedPackage
            liveRoundState = nil
            startingNine = nil
            pendingEventCount = 0
            pendingLiveHole = nil
            finishErrorMessage = nil
            syncStatus = "本场已保存 · 后台同步中"
        }
    }

    private func retryDeferredRoundFinishes() {
        guard deferredRoundFinishTask == nil else {
            // A late Watch fact or a foreground transition can arrive while Finish is awaiting the
            // server. Remember that edge instead of losing it; run one more pass after this pass
            // settles. This is bounded (not a connectivity retry loop).
            deferredRoundFinishRetryRequested = true
            return
        }
        guard !isSyncingPendingEvents,
              !eventSyncSuppressedForUITests,
              syncClient != nil,
              (try? offlineStore.loadPendingRoundFinishes().isEmpty) == false else { return }
        deferredRoundFinishRetryRequested = false
        let generation = UUID()
        deferredRoundFinishGeneration = generation
        deferredRoundFinishTask = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.processDeferredRoundFinishes()
            // Account activation cancels the old task and can start a new account's task before a
            // suspended URLSession continuation unwinds. The old generation must not clear or drive
            // the new account's state.
            guard self.deferredRoundFinishGeneration == generation else { return }
            let rerun = self.deferredRoundFinishRetryRequested
                && ((try? self.offlineStore.loadPendingRoundFinishes().isEmpty) == false)
            self.deferredRoundFinishRetryRequested = false
            self.deferredRoundFinishTask = nil
            self.deferredRoundFinishGeneration = nil
            if rerun {
                self.retryDeferredRoundFinishes()
            } else if self.liveRoundState != nil {
                // A player may already have started the next round while the old one finished. Its
                // score taps were durably queued while the finish transaction owned the uploader.
                await self.syncPendingEvents(wakeDeferredAfterCompletion: true)
            }
        }
    }

    private func processDeferredRoundFinishes() async {
        guard let syncClient else { return }
        let playerScope = boundPlayerId
        let records = (try? offlineStore.loadPendingRoundFinishes()) ?? []
        for record in records {
            guard !Task.isCancelled, boundPlayerId == playerScope else { return }
            do {
                let finishedPackage = try offlineStore.loadRoundPackage(roundId: record.roundId)
                _ = try await syncPendingMedia(roundId: record.roundId)
                guard !Task.isCancelled, boundPlayerId == playerScope else { return }
                guard try offlineStore.loadPendingMedia(roundId: record.roundId).isEmpty else {
                    throw LiveRoundFinishError.pendingMedia
                }
                let pending = try offlineStore.loadPendingEvents(roundId: record.roundId)
                if !pending.isEmpty {
                    try await postPendingEventsAndRequireFullAcknowledgement(
                        pending,
                        roundId: record.roundId,
                        syncClient: syncClient
                    )
                }
                guard !Task.isCancelled, boundPlayerId == playerScope else { return }
                guard try offlineStore.loadPendingEvents(roundId: record.roundId).isEmpty,
                      try offlineStore.loadPendingMedia(roundId: record.roundId).isEmpty else {
                    throw LiveRoundFinishError.incompleteAcknowledgement
                }
                try await syncClient.finishRound(
                    roundId: record.roundId,
                    metadata: record.metadata
                )
                guard !Task.isCancelled, boundPlayerId == playerScope else { return }
                let refreshedHome: LiveRoundPackage? = if let course = finishedPackage?.course {
                    await fetchHomePackage(preferredCourse: course)
                } else {
                    nil
                }
                guard !Task.isCancelled, boundPlayerId == playerScope else { return }
                // A late Watch event cannot be deleted merely because the request above suspended.
                guard try offlineStore.loadPendingEvents(roundId: record.roundId).isEmpty else {
                    throw LiveRoundFinishError.incompleteAcknowledgement
                }
                try offlineStore.discardRound(roundId: record.roundId)
                if let refreshedHome {
                    if liveRoundState == nil {
                        try activateHomePackage(refreshedHome, status: "本场已同步")
                    } else {
                        try offlineStore.saveHomePackage(refreshedHome)
                    }
                }
                syncStatus = "已同步结束的球局"
            } catch {
                AICaddieLog.network.info(
                    "Deferred round finish retained for retry \(record.roundId, privacy: .public): \(String(describing: error), privacy: .public)"
                )
                syncStatus = "已保存 · 等待网络同步"
            }
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
        watchRoundStartRetryTasks.removeValue(forKey: roundId)?.cancel()
        try offlineStore.discardRound(roundId: roundId)
        if let homePackage {
            try offlineStore.saveHomePackage(homePackage)
        }
        package = homePackage
        liveRoundState = nil
        if pendingWatchRoundStart?.roundId == roundId {
            pendingWatchRoundStart = nil
        }
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

    /// Activate a round created on the Watch even when the phone was asleep or the Watch had no
    /// qualified GPS fix. The Watch's compact start fact is idempotent; the phone owns the richer
    /// package and fetches it independently, falling back to a matching offline template first.
    @MainActor
    public func handleWatchRoundStart(_ start: WatchRoundStartPayload) async {
        let roundId = start.roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !roundId.isEmpty, !start.holes.isEmpty else { return }

        if package?.roundId == roundId, liveRoundState?.roundId == roundId {
            pendingWatchRoundStart = nil
            pendingLiveHole = start.activeHole
            return
        }
        // Never replace an unrelated active round with a delayed WatchConnectivity delivery.
        if liveRoundState != nil, liveRoundState?.roundId != roundId {
            syncStatus = "手表已有新球局，当前球局仍在进行"
            return
        }
        guard watchRoundStartInFlight.insert(roundId).inserted else { return }
        defer { watchRoundStartInFlight.remove(roundId) }
        pendingWatchRoundStart = start

        let sourceIds = Set(start.holes.compactMap(\.globalId))
        let frontGlobalId = start.globalId
            ?? start.holes.compactMap(\.globalId).first
        let requestedNine = (start.nine?.isEmpty == false ? start.nine : "all") ?? "all"

        do {
            var nextPackage: LiveRoundPackage?
            if let frontGlobalId {
                let templates = (try? offlineStore.loadCourseTemplates()) ?? []
                nextPackage = templates.first { candidate in
                    guard candidate.course.globalId == frontGlobalId,
                          candidate.course.teeBox.caseInsensitiveCompare(start.teeBox) == .orderedSame,
                          (candidate.nine ?? "all").caseInsensitiveCompare(requestedNine) == .orderedSame else {
                        return false
                    }
                    let candidateSourceIds = Set(candidate.holes.map {
                        $0.sourceGlobalId ?? candidate.course.globalId
                    })
                    return sourceIds.isEmpty || candidateSourceIds == sourceIds
                }?.rebasedForOfflineStart(roundId: roundId)
            }

            if nextPackage == nil, let frontGlobalId, let syncClient {
                nextPackage = try await syncClient.fetchCoursePackage(
                    globalId: frontGlobalId,
                    roundId: roundId,
                    teeBox: start.teeBox,
                    nine: requestedNine,
                    ensureGeometry: false,
                    backgroundGeometry: true,
                    backGlobalId: start.backGlobalId,
                    includeEventCursor: false
                )
            }

            guard let nextPackage else {
                syncStatus = "手表已开始，球场数据稍后同步"
                scheduleWatchRoundStartRetry(start)
                return
            }
            try offlineStore.saveRoundPackage(nextPackage)
            try activatePackage(nextPackage, status: "手表已开始 · iPhone 已同步")
            if nextPackage.holes.contains(where: { $0.number == start.activeHole }) {
                try offlineStore.saveActiveHole(roundId: roundId, hole: start.activeHole)
                liveRoundState = try offlineStore.restoreLiveRoundState(
                    roundId: roundId,
                    package: nextPackage
                )
            }
            pendingLiveHole = start.activeHole
            pendingWatchRoundStart = nil
            signalFreshRoundEntry(revalidatePackage: true)
            watchRoundStartRetryTasks.removeValue(forKey: roundId)?.cancel()
        } catch {
            AICaddieLog.watch.error(
                "Watch round-start activation failed: \(String(describing: error), privacy: .public)"
            )
            syncStatus = "手表已开始，iPhone 正在重试同步"
            scheduleWatchRoundStartRetry(start)
        }
    }

    private func scheduleWatchRoundStartRetry(_ start: WatchRoundStartPayload) {
        guard watchRoundStartRetryTasks[start.roundId] == nil else { return }
        watchRoundStartRetryTasks[start.roundId] = Task { [weak self] in
            await self?.retryWatchRoundStart(start)
        }
    }

    private func retryWatchRoundStart(_ start: WatchRoundStartPayload) async {
        defer { watchRoundStartRetryTasks.removeValue(forKey: start.roundId) }
        for delay in Self.watchRoundStartRetryDelaysNanoseconds {
            do {
                try await Task.sleep(nanoseconds: delay)
            } catch {
                return
            }
            guard !Task.isCancelled else { return }
            if let active = liveRoundState, active.roundId != start.roundId {
                return
            }
            await handleWatchRoundStart(start)
            if package?.roundId == start.roundId,
               liveRoundState?.roundId == start.roundId {
                return
            }
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
        watchRoundStartRetryTasks.removeValue(forKey: package.roundId)?.cancel()
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
                if pendingWatchRoundStart?.roundId == package.roundId {
                    pendingWatchRoundStart = nil
                }
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
            if try offlineStore.isRoundPendingFinish(event.roundId) {
                syncStatus = "已保存 · 记录待同步"
                retryDeferredRoundFinishes()
                return
            }
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
        retryDeferredRoundFinishes()
        // Only a real live state enters the ordinary uploader. A sealed round can remain as the Hub's
        // visual home fallback with the same package ID, but its durable finish worker owns that tail.
        guard !eventSyncSuppressedForUITests,
              liveRoundState != nil,
              let package else { return }
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
        await syncPendingEvents(wakeDeferredAfterCompletion: true)
    }

    /// User-initiated data refresh. Phone/watch event upload and Garmin import are deliberately two
    /// independent stages: a local upload failure must not suppress a Garmin pull, and vice versa.
    /// The Bool is used by the post-login screen only to choose clear success/failure copy.
    @discardableResult
    public func syncGarminData() async -> Bool {
        if let garminSyncTask {
            return await garminSyncTask.value
        }
        garminSyncOperationGeneration += 1
        let operationGeneration = garminSyncOperationGeneration
        let task = Task { [weak self] in
            guard let self else { return false }
            return await self.performGarminSync(operationGeneration: operationGeneration)
        }
        garminSyncTask = task
        let result = await task.value
        // Account activation can cancel this task and start another one before the old network
        // request returns. Never clear the newer task in that case.
        if garminSyncOperationGeneration == operationGeneration {
            garminSyncTask = nil
        }
        return result
    }

    private func performGarminSync(operationGeneration: Int) async -> Bool {
        guard operationGeneration == garminSyncOperationGeneration else { return false }
        guard !isGarminSyncing else { return false }
        garminSyncPresentationGeneration += 1
        garminSyncPresentationLockedUntil = nil
        isGarminSyncing = true
        // Publish the in-flight state before uploading local events. The upload can take a while,
        // and leaving the previous success label visible makes the settings screen claim both
        // "updated" and "syncing" at once.
        garminSyncStatus = "正在同步 Garmin 数据…"
        defer {
            if operationGeneration == garminSyncOperationGeneration {
                isGarminSyncing = false
            }
        }

        if liveRoundState != nil || pendingEventCount > 0 {
            await syncPendingEvents()
        } else {
            localEventUploadStatus = "没有待上传的本机记录"
        }
        guard operationGeneration == garminSyncOperationGeneration else { return false }

        guard let syncClient else {
            garminSyncStatus = "未联网，Garmin 数据未更新"
            garminSyncPresentationLockedUntil = Date().addingTimeInterval(3)
            garminSyncPresentationWatermark = Date()
            return false
        }
        garminSyncStatus = "正在拉取 Garmin 数据…"
        do {
            let result = try await syncClient.runGarminSync(withShots: true)
            guard operationGeneration == garminSyncOperationGeneration,
                  !Task.isCancelled else {
                if operationGeneration == garminSyncOperationGeneration {
                    garminSyncPresentationLockedUntil = Date().addingTimeInterval(3)
                }
                return false
            }
            if result.reauthRequired || result.state == "reauth_required" {
                garminSyncStatus = "Garmin 登录已过期，请重新连接"
                garminSyncPresentationLockedUntil = Date().addingTimeInterval(3)
                garminSyncPresentationWatermark = Date()
                return false
            }
            guard result.state == "ready" else {
                garminSyncStatus = "Garmin 拉取失败，请稍后重试"
                garminSyncPresentationLockedUntil = Date().addingTimeInterval(3)
                garminSyncPresentationWatermark = Date()
                return false
            }

            await refreshCourseOptions()
            if liveRoundState == nil, let home = await fetchHomePackage() {
                // Keep the generic home-sync banner separate from the Garmin section. The latter is
                // the sole owner of "Garmin 数据已更新", so the settings page cannot show two success
                // labels while a later status poll is still resolving.
                try? activateHomePackage(home, status: "主页数据已刷新")
            }
            if let bag = try? await syncClient.fetchClubBag(), bag.found {
                let names = resolvedBagNames(bag)
                if !names.isEmpty {
                    ClubBagStore.saveRealBag(names)
                }
            }
            let refreshedStatus = try? await syncClient.fetchGarminSyncStatus()
            let completedAt = refreshedStatus?.lastRun?.updatedAt
                .flatMap { ISO8601DateFormatter().date(from: $0) }
                ?? Date()
            guard operationGeneration == garminSyncOperationGeneration else { return false }
            lastGarminSyncAt = completedAt
            garminSyncStatus = refreshedStatus?.lastRun?.newRoundCount == 0
                ? "Garmin 已同步，暂无新球局"
                : "Garmin 数据已更新"
            garminSyncPresentationLockedUntil = Date().addingTimeInterval(5)
            // Use local completion time for the watermark. The server's updatedAt can be stale by
            // several seconds even though the POST has already returned ready.
            garminSyncPresentationWatermark = Date()
            NotificationCenter.default.post(name: .garminDataDidRefresh, object: nil)
            return true
        } catch let error as SyncClientError {
            guard operationGeneration == garminSyncOperationGeneration else { return false }
            if case .http(let status, _) = error, status == 409 {
                garminSyncStatus = "已有一次 Garmin 同步在进行，请稍后再试"
            } else {
                garminSyncStatus = "Garmin 拉取失败，请稍后重试"
            }
            garminSyncPresentationLockedUntil = Date().addingTimeInterval(3)
            garminSyncPresentationWatermark = Date()
            AICaddieLog.network.error("Garmin pull failed: \(String(describing: error), privacy: .public)")
            return false
        } catch {
            guard operationGeneration == garminSyncOperationGeneration else { return false }
            garminSyncStatus = "Garmin 拉取失败，请稍后重试"
            garminSyncPresentationLockedUntil = Date().addingTimeInterval(3)
            garminSyncPresentationWatermark = Date()
            AICaddieLog.network.error("Garmin pull failed: \(String(describing: error), privacy: .public)")
            return false
        }
    }

    private func syncPendingEvents(wakeDeferredAfterCompletion: Bool) async {
        guard !isFinishingRound,
              !isSyncingPendingEvents,
              deferredRoundFinishTask == nil else { return }
        isSyncingPendingEvents = true
        let playerScope = boundPlayerId
        defer {
            isSyncingPendingEvents = false
            if wakeDeferredAfterCompletion {
                retryDeferredRoundFinishes()
            }
        }
        guard let package else {
            syncStatus = "没有进行中的球局"
            localEventUploadStatus = "没有待上传的本机记录"
            return
        }
        guard let syncClient else {
            syncStatus = "未联网,稍后同步"
            localEventUploadStatus = "等待网络上传"
            return
        }

        do {
            let uploadedMediaCount = try await syncPendingMedia(roundId: package.roundId)
            guard !Task.isCancelled, boundPlayerId == playerScope else { return }
            if try offlineStore.isRoundPendingFinish(package.roundId) { return }
            let events = try offlineStore.loadPendingEvents(roundId: package.roundId)
            pendingEventCount = events.count
            if events.isEmpty {
                syncStatus = uploadedMediaCount > 0 ? "已同步 \(uploadedMediaCount) 张照片/视频" : "已是最新"
                localEventUploadStatus = uploadedMediaCount > 0
                    ? "已上传本机记录和 \(uploadedMediaCount) 个媒体文件"
                    : "本机记录已上传"
            } else {
                syncStatus = "同步中…"
                let result = try await postPendingEventsAndRequireFullAcknowledgement(
                    events,
                    roundId: package.roundId,
                    syncClient: syncClient
                )
                guard !Task.isCancelled, boundPlayerId == playerScope else { return }
                if try offlineStore.isRoundPendingFinish(package.roundId) { return }
                pendingEventCount = try offlineStore.loadPendingEvents(roundId: package.roundId).count
                let mediaSuffix = uploadedMediaCount > 0 ? " · \(uploadedMediaCount) 张照片/视频" : ""
                syncStatus = result.duplicate ? "已同步" : "已同步\(mediaSuffix)"
                localEventUploadStatus = pendingEventCount == 0
                    ? "本机记录已上传"
                    : "仍有 \(pendingEventCount) 条记录待上传"
            }
            // round-12 sync spine: ALWAYS pull events authored by OTHER clients (runs even with no
            // local pending events) so a round edited on the watch/web shows up here.
            await pullAndApplyRemoteEvents(roundId: package.roundId)
        } catch {
            AICaddieLog.network.error("Pending-event sync failed: \(String(describing: error), privacy: .public)")
            syncStatus = "同步失败,稍后重试"
            localEventUploadStatus = pendingEventCount > 0
                ? "\(pendingEventCount) 条记录等待重试"
                : "本机记录上传失败，稍后重试"
        }
    }

    #if DEBUG
    func waitForDeferredRoundFinishesForTesting() async {
        await deferredRoundFinishTask?.value
    }
    #endif

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
        guard !Task.isCancelled else { throw CancellationError() }
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
        guard let syncClient,
              let package,
              package.roundId == roundId,
              liveRoundState?.roundId == roundId,
              (try? offlineStore.isRoundPendingFinish(roundId)) != true else { return }
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
            guard liveRoundState?.roundId == roundId,
                  (try? offlineStore.isRoundPendingFinish(roundId)) != true else { return }
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
            try Task.checkCancellation()
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
                try Task.checkCancellation()
                try? await mediaUploadClient.analyzeMedia(mediaId: uploadResponse.media.id)
                try Task.checkCancellation()
                uploadedIds.insert(media.id)
            } catch {
                AICaddieLog.network.error("Pending media upload failed: \(String(describing: error), privacy: .public)")
                continue
            }
        }
        try Task.checkCancellation()
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

    private static func configuredLiveRoundId() -> String? {
        let roundId = ProcessInfo.processInfo.environment["AI_CADDIE_LIVE_ROUND_ID"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let roundId, !roundId.isEmpty {
            return roundId
        }
        return nil
    }

    private func fetchRemotePackage(capturedAt: Date = Date()) async -> LiveRoundPackage? {
        guard let preferredRoundId else {
            return nil
        }
        return await fetchRemotePackage(roundId: preferredRoundId, capturedAt: capturedAt)
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
            var resumable = record
            // A ready row is only a convenience index; the revision-bound facts and every topo
            // file remain the install authority. Reconcile stale rows at launch so the library
            // never advertises files that were evicted, cleaned up, or invalidated by a renderer
            // revision as ready.
            if record.phase == .ready, readyPrepTemplate(for: record) == nil {
                resumable.phase = .queued
                resumable.errorText = nil
            } else if record.phase == .preparing || record.phase == .downloading {
                promoteInterruptedPrepCourseDownloadForResume(&resumable)
            }
            return resumable
        }
        persistPrepCourseDownloads()
    }

    /// Interrupted rows should keep their durable progress but re-enter the queue as the newest
    /// in-flight intent. Queued rows retain their existing order so a relaunch does not invent a
    /// fresh priority over jobs that were already waiting.
    private func promoteInterruptedPrepCourseDownloadForResume(_ record: inout PrepCourseDownloadRecord) {
        record.phase = .queued
        record.errorText = nil
        record.updatedAt = Date()
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
              offlineStore.hasCourseTopoImages(for: template),
              templateSatisfiesRequiredGeometryRevisions(template, record: record) else { return nil }
        return template
    }

    private func geometryRevisions(in template: LiveRoundPackage) -> [String: String] {
        template.holes.reduce(into: [:]) { result, hole in
            let sourceGlobalId = hole.sourceGlobalId ?? template.course.globalId
            let sourceLocalHole = hole.sourceLocalHole ?? hole.number
            let prepRevision = template.coursePrep?.holes.first(where: {
                $0.hole == hole.number
            })?.geometryRevision
            let revision = (prepRevision ?? hole.geometryRevision)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            guard let revision, !revision.isEmpty else { return }
            result[offlinePrepKey(globalId: sourceGlobalId, localHole: sourceLocalHole)] = revision
        }
    }

    private func geometryKeys(in template: LiveRoundPackage) -> Set<String> {
        Set(template.holes.map { hole in
            offlinePrepKey(
                globalId: hole.sourceGlobalId ?? template.course.globalId,
                localHole: hole.sourceLocalHole ?? hole.number
            )
        })
    }

    private func templateSatisfiesRequiredGeometryRevisions(
        _ template: LiveRoundPackage,
        record: PrepCourseDownloadRecord
    ) -> Bool {
        templateSatisfiesRequiredGeometryRevisions(
            template,
            required: record.requiredGeometryRevisions
        )
    }

    private func templateSatisfiesRequiredGeometryRevisions(
        _ template: LiveRoundPackage,
        required: [String: String]?
    ) -> Bool {
        guard let required, !required.isEmpty else { return true }
        let installed = geometryRevisions(in: template)
        return required.allSatisfy { key, revision in
            installed[key] == revision.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        }
    }

    /// Selecting a catalogue result creates/reattaches to one app-owned job before navigation.
    /// Reopening the same course never replaces a running task or discards its per-hole progress.
    public func downloadPrepCourse(_ course: MobileCourseOption) {
        prepCourseDownloadPresentation.retainSelection(course)
        let teeBox = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedTee = teeBox?.isEmpty == false ? teeBox! : "blue"
        let candidate = PrepCourseDownloadRecord(
            course: course,
            teeBox: resolvedTee,
            totalHoles: course.resolvedHoles
        )
        let id = candidate.id
        if let existing = prepCourseDownloads.first(where: { $0.id == id }) {
            if readyPrepTemplate(for: existing) != nil {
                updatePrepCourseDownload(id: id) { record in
                    record.phase = .ready
                    record.preparedHoles = record.totalHoles
                    record.downloadedHoles = record.totalHoles
                    record.errorText = nil
                    record.requiredGeometryRevisions = nil
                }
                refreshDownloadedCourseOptions()
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
            refreshDownloadedCourseOptions()
        } else if let installed = readyPrepTemplate(for: candidate) {
            var ready = candidate
            ready.phase = .ready
            ready.totalHoles = max(1, installed.holes.count)
            ready.preparedHoles = ready.totalHoles
            ready.downloadedHoles = ready.totalHoles
            prepCourseDownloads.append(ready)
            persistPrepCourseDownloads()
            refreshDownloadedCourseOptions()
            return
        } else {
            prepCourseDownloads.append(candidate)
            persistPrepCourseDownloads()
            refreshDownloadedCourseOptions()
        }
        startPrepCourseDownloadQueueIfNeeded()
    }

    public func retryPrepCourseDownload(id: String) {
        guard let existing = prepCourseDownloads.first(where: { $0.id == id }),
              !existing.isTerminalFailure else { return }
        updatePrepCourseDownload(id: id) { record in
            record.phase = .queued
            record.errorText = nil
        }
        refreshDownloadedCourseOptions()
        startPrepCourseDownloadQueueIfNeeded()
    }

    /// Verify a locally complete prep package against the server's release-bound install journal
    /// before opening the map. A missing/temporarily unreachable status endpoint is deliberately
    /// non-blocking: the local package is internally consistent and remains usable offline. A
    /// positive revision mismatch, however, invalidates the row and queues a fresh install so an
    /// old Garmin bitmap is never presented as current.
    public func validateReadyPrepCourse(_ record: PrepCourseDownloadRecord) async -> Bool {
        guard record.phase == .ready else {
            updatePrepCourseDownload(id: record.id) { state in
                state.errorText = state.isActive
                    ? "地图仍在准备中，完成后即可进入备战。"
                    : "地图尚未准备完成，请继续下载。"
            }
            return false
        }
        guard let template = readyPrepTemplate(for: record) else {
            updatePrepCourseDownload(id: record.id) { state in
                state.phase = .queued
                state.errorText = "本机地图文件不完整，正在重新下载。"
            }
            refreshDownloadedCourseOptions()
            startPrepCourseDownloadQueueIfNeeded()
            return false
        }
        guard let syncClient else { return true }

        let status: CourseInstallStatus?
        do {
            status = try await syncClient.probeCourseInstallStatusForRevalidation(
                globalId: record.course.globalId,
                teeBox: record.teeBox,
                nine: record.nine,
                backGlobalId: courseInstallBackGlobalId(for: template)
            )
        } catch {
            AICaddieLog.network.info(
                "Prep release revalidation deferred for \(record.course.globalId, privacy: .public): \(String(describing: error), privacy: .public)"
            )
            guard let current = prepCourseDownloads.first(where: { $0.id == record.id }),
                  current.phase == .ready,
                  readyPrepTemplate(for: current) != nil else { return false }
            return true
        }
        // The app-owned queue may have changed this exact course while the network request was
        // suspended. Compare against the current durable row/template, never the captured snapshot.
        guard let current = prepCourseDownloads.first(where: { $0.id == record.id }),
              current.phase == .ready,
              let currentTemplate = readyPrepTemplate(for: current) else { return false }
        // A pruned/legacy journal is not evidence that the local package is stale. The next
        // explicit download will recreate it, while this open remains available offline.
        guard let status else { return true }

        let localRevisions = geometryRevisions(in: currentTemplate)
        let installedKeys = geometryKeys(in: currentTemplate)
        let requiredRevisions: [String: String] = status.holes.reduce(into: [:]) { result, row in
            guard let remote = row.geometryRevision?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
                  !remote.isEmpty else { return }
            let key = offlinePrepKey(globalId: row.globalId, localHole: row.localHole)
            // The server journal can retain rows from another compatible request. Only a positive
            // mismatch for a hole in this installed template is evidence that this selection is
            // stale. A missing local revision is also stale; otherwise an older package with a
            // complete-looking bitmap could bypass the release gate.
            guard installedKeys.contains(key), localRevisions[key] != remote else { return }
            result[key] = remote
        }
        guard !requiredRevisions.isEmpty else { return true }

        updatePrepCourseDownload(id: record.id) { state in
            state.phase = .queued
            state.preparedHoles = 0
            state.downloadedHoles = 0
            state.errorText = "检测到地图有新版本，正在更新。"
            state.requiredGeometryRevisions = requiredRevisions
        }
        refreshDownloadedCourseOptions()
        startPrepCourseDownloadQueueIfNeeded()
        return false
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
            let staleReady = phase == .ready
                && readyPrepTemplate(for: prepCourseDownloads[index]) == nil
            if staleReady {
                prepCourseDownloads[index].phase = .queued
                prepCourseDownloads[index].errorText = nil
                changed = true
            } else if phase == .preparing || phase == .downloading {
                promoteInterruptedPrepCourseDownloadForResume(&prepCourseDownloads[index])
                changed = true
            } else if retryFailed && phase == .failed && !prepCourseDownloads[index].isTerminalFailure {
                prepCourseDownloads[index].phase = .queued
                prepCourseDownloads[index].errorText = nil
                changed = true
            }
        }
        if changed {
            persistPrepCourseDownloads()
            refreshDownloadedCourseOptions()
        }
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
            if courseInstallBackGlobalId(for: fetched) != nil {
                // The prep library currently installs one physical course. A composite 9+9
                // package belongs to the live-round path; ending this job explicitly avoids a
                // silent ready/failed/re-download loop while preserving the normal 9+9 scorer.
                updatePrepCourseDownload(id: id, generation: generation) { state in
                    state.phase = .failed
                    state.errorText = "两段 9 洞组合暂不支持备战下载，请在开始一场中使用"
                }
                refreshDownloadedCourseOptions()
                return
            }
            // Keep the previous template available for an offline live round until this
            // replacement package has actually arrived. The atomic write then supersedes it even
            // when the old package has richer prep coverage than the newly fetched package.
            let replacingExisting = prepCourseDownloads
                .first(where: { $0.id == id })?
                .requiredGeometryRevisions?
                .isEmpty == false
            if !replacingExisting {
                try offlineStore.saveCourseTemplate(fetched)
            }
            updatePrepCourseDownload(id: id, generation: generation) { state in
                state.totalHoles = max(1, fetched.holes.count)
                // A Garmin release can move again while the replacement is downloading. Bind this
                // install to every revision carried by the package we actually fetched, rather
                // than only the hole that triggered revalidation; mixed old/new topo is not a
                // coherent offline package.
                if replacingExisting {
                    let fetchedRevisions = geometryRevisions(in: fetched)
                    if !fetchedRevisions.isEmpty {
                        var required = state.requiredGeometryRevisions ?? [:]
                        required.merge(fetchedRevisions) { _, fetchedRevision in fetchedRevision }
                        state.requiredGeometryRevisions = required
                    }
                }
            }
            let replacementCompleted = await downloadOfflineCourseAssets(
                for: fetched,
                using: syncClient,
                prepDownloadID: id,
                prepDownloadGeneration: generation,
                deferTemplateReplacement: replacingExisting
            )
            guard !Task.isCancelled,
                  prepCourseDownloadGeneration == generation else { throw CancellationError() }
            if (!replacingExisting || replacementCompleted),
               let current = prepCourseDownloads.first(where: { $0.id == id }),
               readyPrepTemplate(for: current) != nil {
                updatePrepCourseDownload(id: id, generation: generation) { state in
                    state.phase = .ready
                    state.preparedHoles = state.totalHoles
                    state.downloadedHoles = state.totalHoles
                    state.errorText = nil
                    state.requiredGeometryRevisions = nil
                }
                refreshDownloadedCourseOptions()
            } else {
                let serverStatus: CourseInstallStatus?
                let statusProbeFailed: Bool
                do {
                    serverStatus = try await syncClient.fetchCourseInstallStatus(
                        globalId: record.course.globalId,
                        teeBox: record.teeBox,
                        nine: record.nine,
                        backGlobalId: courseInstallBackGlobalId(for: fetched)
                    )
                    statusProbeFailed = false
                } catch {
                    serverStatus = nil
                    statusProbeFailed = true
                    AICaddieLog.network.info(
                        "Course install status deferred for \(record.course.globalId, privacy: .public): \(String(describing: error), privacy: .public)"
                    )
                }
                let serverIsProgressing = serverStatus.map {
                    $0.phase.caseInsensitiveCompare("queued") == .orderedSame
                        || $0.phase.caseInsensitiveCompare("running") == .orderedSame
                } ?? statusProbeFailed
                if serverIsProgressing {
                    // The server is still making durable progress; do not turn an ordinary cold
                    // 18-hole render into a red failure row. Keep the app-scoped worker attached and
                    // retry at a low cadence, resuming only missing revision-keyed files.
                    updatePrepCourseDownload(id: id, generation: generation) { state in
                        state.phase = state.downloadedHoles > 0 ? .downloading : .preparing
                        state.errorText = nil
                    }
                    try await Task.sleep(nanoseconds: 15_000_000_000)
                    guard !Task.isCancelled,
                          prepCourseDownloadGeneration == generation else { throw CancellationError() }
                    updatePrepCourseDownload(id: id, generation: generation) { state in
                        state.phase = .queued
                        state.errorText = nil
                    }
                } else {
                    updatePrepCourseDownload(id: id, generation: generation) { state in
                        state.phase = .failed
                        state.errorText = "下载未完成，点下载继续"
                    }
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
        city: String? = nil,
        latitude: Double? = nil,
        longitude: Double? = nil
    ) async throws -> [MobileCourseSearchMatch] {
        prioritizeCourseDiscovery()
        guard let syncClient else { throw URLError(.notConnectedToInternet) }
        return try await syncClient.searchCourses(
            name: name,
            city: city,
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
        let prepReady = standalone.filter { package in
            let key = PrepCourseDownloadRecord.key(
                globalId: package.course.globalId,
                teeBox: package.course.teeBox,
                nine: package.nine ?? "all"
            )
            guard let pendingRelease = prepCourseDownloads.first(where: { $0.id == key }) else {
                return true
            }
            guard pendingRelease.phase == .ready else { return false }
            return templateSatisfiesRequiredGeometryRevisions(package, record: pendingRelease)
        }
        downloadedCourseKeys = Set(prepReady.map { package in
            PrepCourseDownloadRecord.key(
                globalId: package.course.globalId,
                teeBox: package.course.teeBox,
                nine: package.nine ?? "all"
            )
        })
        // Keep the ordinary live-round library independent from a prep-release refresh. A complete
        // local template remains a valid offline start even while its prep row is queued for a newer
        // Garmin release; only the prep picker consumes the stricter exact-key readiness set above.
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

        // Save & End has already removed this round from the live UI. A late wrist event belongs to
        // the sealed transaction; wake that transaction without restoring the round or routing it
        // through the normal current-package uploader (which could race Finish).
        if try offlineStore.isRoundPendingFinish(event.roundId) {
            syncStatus = "已保存 · 手表记录待同步"
            if !eventSyncSuppressedForUITests {
                retryDeferredRoundFinishes()
            }
            return
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
