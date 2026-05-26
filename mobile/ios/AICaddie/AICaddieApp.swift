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

    private let offlineStore: OfflineStore
    private let syncClient: SyncClient?

    public init(offlineStore: OfflineStore = OfflineStore(), syncClient: SyncClient? = nil) {
        self.offlineStore = offlineStore
        self.syncClient = syncClient ?? Self.defaultSyncClient()
    }

    public func bootstrap() async {
        do {
            if let cached = try offlineStore.loadCurrentRoundPackage() {
                package = cached
                pendingEventCount = try offlineStore.loadPendingEvents(roundId: cached.roundId).count
                syncStatus = "Cached package ready"
                return
            }
            let fixture = try loadFixturePackage()
            try offlineStore.saveRoundPackage(fixture)
            package = fixture
            pendingEventCount = try offlineStore.loadPendingEvents(roundId: fixture.roundId).count
            syncStatus = "Fixture package cached"
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

    private static func defaultSyncClient() -> SyncClient? {
        guard
            let rawURL = ProcessInfo.processInfo.environment["AI_CADDIE_API_BASE_URL"],
            let baseURL = URL(string: rawURL)
        else {
            return nil
        }
        return SyncClient(baseURL: baseURL)
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
