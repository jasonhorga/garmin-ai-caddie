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
                        onEvent: model.handleEvent
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

    public init(offlineStore: OfflineStore = OfflineStore()) {
        self.offlineStore = offlineStore
    }

    public func bootstrap() async {
        do {
            if let cached = try offlineStore.loadCurrentRoundPackage() {
                package = cached
                pendingEventCount = try offlineStore.loadEvents().count
                syncStatus = "Cached package ready"
                return
            }
            let fixture = try loadFixturePackage()
            try offlineStore.saveRoundPackage(fixture)
            package = fixture
            pendingEventCount = try offlineStore.loadEvents().count
            syncStatus = "Fixture package cached"
        } catch {
            syncStatus = "Offline package unavailable"
        }
    }

    public func handleEvent(_ event: LiveRoundEvent) {
        do {
            try offlineStore.appendEvent(event)
            pendingEventCount = try offlineStore.loadEvents().count
            syncStatus = "Offline event saved"
        } catch {
            syncStatus = "Event save failed"
        }
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
