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
                        watchBridge: model.watchBridge,
                        onEvent: model.handleEvent,
                        onSync: {
                            Task {
                                await model.syncPendingEvents()
                            }
                        }
                    )
                } else {
                    ProgressView("Loading round")
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
    public let watchBridge: WatchEventBridge?

    private let offlineStore: OfflineStore
    private let syncClient: SyncClient?
    private let preferredRoundId: String

    public init(
        offlineStore: OfflineStore = OfflineStore(),
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        watchBridge: WatchEventBridge? = WatchEventBridge(),
        preferredRoundId: String? = nil,
        syncClient: SyncClient? = nil
    ) {
        let resolvedAPIBaseURL = apiBaseURL ?? Self.defaultAPIBaseURL()
        let resolvedAdminToken = adminToken ?? Self.defaultAdminToken()
        self.offlineStore = offlineStore
        self.apiBaseURL = resolvedAPIBaseURL
        self.adminToken = resolvedAdminToken
        self.watchBridge = watchBridge
        self.preferredRoundId = preferredRoundId ?? Self.defaultLiveRoundId()
        self.syncClient = syncClient ?? resolvedAPIBaseURL.map { SyncClient(baseURL: $0, adminToken: resolvedAdminToken) }
    }

    public func bootstrap() async {
        do {
            if let remotePackage = await fetchRemotePackage() {
                try offlineStore.saveRoundPackage(remotePackage)
                try activatePackage(remotePackage, status: "Remote package cached")
                return
            }
            if let cached = try offlineStore.loadCurrentRoundPackage() {
                try activatePackage(cached, status: "Cached package ready")
                return
            }
            let fixture = try loadFixturePackage()
            try offlineStore.saveRoundPackage(fixture)
            try activatePackage(fixture, status: "Fixture package cached")
        } catch {
            syncStatus = "Offline package unavailable"
        }
    }

    public func handleEvent(_ event: LiveRoundEvent) {
        do {
            try offlineStore.appendEvent(event)
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
            let events = try offlineStore.loadPendingEvents(roundId: package.roundId)
            pendingEventCount = events.count
            guard !events.isEmpty else {
                syncStatus = "No pending events"
                return
            }
            syncStatus = "Syncing \(events.count) events"
            let result = try await syncClient.postEventBatchWithRetry(
                events,
                roundId: package.roundId,
                idempotencyKey: idempotencyKey(roundId: package.roundId, events: events)
            )
            try offlineStore.appendSyncMarker(roundId: package.roundId, timestamp: ISO8601DateFormatter().string(from: Date()))
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: package.roundId).count
            syncStatus = result.duplicate ? "Events already synced" : "Synced \(result.accepted) events"
        } catch {
            syncStatus = "Sync failed"
        }
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

    private func fetchRemotePackage() async -> LiveRoundPackage? {
        guard let syncClient else {
            return nil
        }
        do {
            return try await syncClient.fetchRoundPackage(roundId: preferredRoundId)
        } catch {
            syncStatus = "Package sync unavailable; using cache"
            return nil
        }
    }

    private func activatePackage(_ nextPackage: LiveRoundPackage, status: String) throws {
        package = nextPackage
        pendingEventCount = try offlineStore.loadPendingEvents(roundId: nextPackage.roundId).count
        syncStatus = status
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
