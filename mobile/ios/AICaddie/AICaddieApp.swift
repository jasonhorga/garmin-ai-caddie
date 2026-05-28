import Foundation
import SwiftUI

@main
public struct AICaddieApp: App {
    @StateObject private var model = LiveRoundAppModel()

    public init() {}

    public var body: some Scene {
        WindowGroup {
            Group {
                if let package = model.package {
                    RoundHomeView(
                        package: package,
                        pendingEventCount: model.pendingEventCount,
                        syncStatus: model.syncStatus,
                        apiBaseURL: model.apiBaseURL,
                        adminToken: model.adminToken,
                        offlineStore: model.offlineStore,
                        sessionStore: model.garminSessionStore,
                        watchBridge: model.watchBridge,
                        liveRoundState: model.liveRoundState,
                        courseOptions: model.courseOptions,
                        isPreparingRound: model.isPreparingRound,
                        onEvent: model.handleEvent,
                        onPrepareRound: { roundId in
                            Task {
                                await model.prepareRound(roundId: roundId)
                            }
                        },
                        onPrepareCourseRound: { globalId, roundId, teeBox in
                            Task {
                                await model.prepareCourseRound(globalId: globalId, roundId: roundId, teeBox: teeBox)
                            }
                        },
                        onSync: {
                            Task {
                                await model.syncPendingEvents()
                            }
                        }
                    )
                } else {
                    NavigationStack {
                        StartRoundView(
                            defaultRoundId: model.defaultRoundId,
                            courseOptions: model.courseOptions,
                            syncStatus: model.syncStatus,
                            isPreparing: model.isPreparingRound,
                            onPrepareRound: { roundId in
                                Task {
                                    await model.prepareRound(roundId: roundId)
                                }
                            },
                            onPrepareCourseRound: { globalId, roundId, teeBox in
                                Task {
                                    await model.prepareCourseRound(globalId: globalId, roundId: roundId, teeBox: teeBox)
                                }
                            }
                        )
                    }
                }
            }
            .task {
                await model.bootstrap()
            }
        }
    }
}

@MainActor
public final class LiveRoundAppModel: ObservableObject {
    @Published public private(set) var package: LiveRoundPackage?
    @Published public private(set) var pendingEventCount: Int = 0
    @Published public private(set) var syncStatus: String = "Offline ready"
    @Published public private(set) var apiBaseURL: URL?
    @Published public private(set) var adminToken: String?
    @Published public private(set) var isPreparingRound = false
    @Published public private(set) var liveRoundState: LiveRoundStateSnapshot?
    @Published public private(set) var courseOptions: [MobileCourseOption] = []
    public let watchBridge: WatchEventBridge?
    public let offlineStore: OfflineStore
    public let garminSessionStore: GarminSessionStore?

    private let syncClient: SyncClient?
    private let mediaUploadClient: MediaUploadClient?
    private let preferredRoundId: String

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
    }

    public var defaultRoundId: String {
        preferredRoundId
    }

    public func bootstrap() async {
        do {
            await refreshCourseOptions()
            if let remotePackage = await fetchRemotePackage() {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "Remote package cached")
                return
            }
            if let cached = try offlineStore.loadCurrentRoundPackage() {
                switch cached.cacheState() {
                case .expired:
                    if try canContinueExpiredPackage(cached) {
                        try activatePackage(cached, status: "Cached package expired; continuing active round offline")
                        return
                    }
                    syncStatus = "Cached package expired; using fallback"
                case .stale:
                    try activatePackage(cached, status: "Cached package stale")
                    return
                case .ready:
                    try activatePackage(cached, status: "Cached package ready")
                    return
                case .degraded:
                    try activatePackage(cached, status: "Cached package degraded")
                    return
                }
            }
            let fixture = try loadFixturePackage()
            try offlineStore.saveRoundPackage(fixture)
            try activatePackage(fixture, status: "Fixture package cached")
        } catch {
            syncStatus = "Offline package unavailable"
        }
    }

    public func refreshCourseOptions() async {
        guard let syncClient else {
            return
        }
        do {
            courseOptions = try await syncClient.fetchCourseOptions().courses
        } catch {
            courseOptions = []
        }
    }

    public func prepareRound(roundId: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "Round id is required"
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
                try activatePackage(remotePackage, status: "Offline package prepared")
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                switch cachedPackage.cacheState() {
                case .expired:
                    if try canContinueExpiredPackage(cachedPackage) {
                        try activatePackage(cachedPackage, status: "Cached package expired; continuing active round offline")
                        return
                    }
                    syncStatus = "Cached package expired"
                case .stale:
                    try activatePackage(cachedPackage, status: "Cached package stale")
                    return
                case .ready:
                    try activatePackage(cachedPackage, status: "Cached package ready")
                    return
                case .degraded:
                    try activatePackage(cachedPackage, status: "Cached package degraded")
                    return
                }
            } else {
                syncStatus = "Round package unavailable"
            }
        } catch {
            syncStatus = "Round package prepare failed"
        }
    }

    public func prepareCourseRound(globalId: Int, roundId: String, teeBox: String) async {
        let requestedRoundId = roundId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !requestedRoundId.isEmpty else {
            syncStatus = "Round id is required"
            return
        }
        let preparedAt = Date()

        isPreparingRound = true
        defer {
            isPreparingRound = false
        }

        do {
            if let remotePackage = await fetchRemoteCoursePackage(globalId: globalId, roundId: requestedRoundId, teeBox: teeBox, capturedAt: preparedAt) {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "Course package prepared")
                return
            }
            if let cachedPackage = try offlineStore.loadRoundPackage(roundId: requestedRoundId) {
                try activatePackage(cachedPackage, status: "Cached package ready")
            } else {
                syncStatus = "Course package unavailable"
            }
        } catch {
            syncStatus = "Course package prepare failed"
        }
    }

    public func handleEvent(_ event: LiveRoundEvent) {
        do {
            try offlineStore.appendEvent(event)
            if let package, package.roundId == event.roundId {
                liveRoundState = try offlineStore.restoreLiveRoundState(roundId: event.roundId, package: package)
            }
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: event.roundId).count
            syncStatus = "Offline event saved"
        } catch {
            syncStatus = "Event save failed"
        }
    }

    public func syncPendingEvents() async {
        guard let package else {
            syncStatus = "No round package loaded"
            return
        }
        guard let syncClient else {
            syncStatus = "No sync server configured"
            return
        }

        do {
            let uploadedMediaCount = try await syncPendingMedia(roundId: package.roundId)
            let events = try offlineStore.loadPendingEvents(roundId: package.roundId)
            pendingEventCount = events.count
            guard !events.isEmpty else {
                syncStatus = uploadedMediaCount > 0 ? "Synced \(uploadedMediaCount) media" : "No pending events"
                return
            }
            syncStatus = "Syncing \(events.count) events"
            let result = try await syncClient.postEventBatchWithRetry(
                events,
                roundId: package.roundId,
                idempotencyKey: idempotencyKey(roundId: package.roundId, events: events)
            )
            try offlineStore.appendSyncMarker(roundId: package.roundId, timestamp: ISO8601DateFormatter().string(from: Date()), result: result)
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: package.roundId).count
            let mediaSuffix = uploadedMediaCount > 0 ? ", \(uploadedMediaCount) media" : ""
            syncStatus = result.duplicate ? "Events already synced" : "Synced \(result.accepted) events\(mediaSuffix)"
        } catch {
            syncStatus = "Sync failed"
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

    private static func defaultAPIBaseURL() -> URL? {
        guard
            let rawURL = ProcessInfo.processInfo.environment["AI_CADDIE_API_BASE_URL"],
            let resolvedAPIBaseURL = URL(string: rawURL)
        else {
            return nil
        }
        return resolvedAPIBaseURL
    }

    private static func defaultAdminToken() -> String? {
        let token = ProcessInfo.processInfo.environment["AI_CADDIE_ADMIN_TOKEN"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        return token?.isEmpty == false ? token : nil
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
            syncStatus = "Package sync unavailable; using cache"
            return nil
        }
    }

    private func fetchRemotePackage(roundId: String, capturedAt: Date = Date()) async -> LiveRoundPackage? {
        guard let syncClient else {
            syncStatus = "No sync server configured"
            return nil
        }
        do {
            return try await syncClient.fetchRoundPackage(roundId: roundId, capturedAt: capturedAt)
        } catch {
            syncStatus = "Package sync unavailable; using cache"
            return nil
        }
    }

    private func fetchRemoteCoursePackage(globalId courseGlobalId: Int, roundId: String, teeBox: String, capturedAt: Date = Date()) async -> LiveRoundPackage? {
        guard let syncClient else {
            syncStatus = "No sync server configured"
            return nil
        }
        do {
            return try await syncClient.fetchCoursePackage(globalId: courseGlobalId, roundId: roundId, teeBox: teeBox, capturedAt: capturedAt)
        } catch {
            syncStatus = "Course package sync unavailable; using cache"
            return nil
        }
    }

    private func activatePackage(_ nextPackage: LiveRoundPackage, status: String) throws {
        package = nextPackage
        liveRoundState = try offlineStore.restoreLiveRoundState(roundId: nextPackage.roundId, package: nextPackage)
        pendingEventCount = try offlineStore.loadPendingEvents(roundId: nextPackage.roundId).count
        syncStatus = status
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
            syncStatus = "Watch event saved"
        } catch {
            syncStatus = "Watch event status unavailable"
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
