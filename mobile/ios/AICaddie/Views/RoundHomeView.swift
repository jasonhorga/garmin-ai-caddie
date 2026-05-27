import Foundation
import SwiftUI

public struct RoundHomeView: View {
    public let package: LiveRoundPackage
    public let pendingEventCount: Int
    public let syncStatus: String
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let offlineStore: OfflineStore?
    public let watchBridge: WatchEventBridge?
    public let isPreparingRound: Bool
    public let onEvent: (LiveRoundEvent) -> Void
    public let onPrepareRound: (String) -> Void
    public let onSync: () -> Void

    public init(
        package: LiveRoundPackage,
        pendingEventCount: Int = 0,
        syncStatus: String = "Offline ready",
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        offlineStore: OfflineStore? = nil,
        watchBridge: WatchEventBridge? = nil,
        isPreparingRound: Bool = false,
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in },
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onSync: @escaping () -> Void = {}
    ) {
        self.package = package
        self.pendingEventCount = pendingEventCount
        self.syncStatus = syncStatus
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.offlineStore = offlineStore
        self.watchBridge = watchBridge
        self.isPreparingRound = isPreparingRound
        self.onEvent = onEvent
        self.onPrepareRound = onPrepareRound
        self.onSync = onSync
    }

    public var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(package.course.name)
                            .font(.title2.weight(.semibold))
                        Text("Tee \(package.course.teeBox) / \(package.geometryCoverage.readyHoles)/\(package.geometryCoverage.totalHoles) geometry")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Label("\(package.clubProfiles.count)", systemImage: "golfclub")
                        Spacer()
                        Label("\(pendingEventCount)", systemImage: "tray.full")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    Button {
                        onSync()
                    } label: {
                        Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                    }
                    NavigationLink {
                        GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken)
                    } label: {
                        Label("Garmin Session", systemImage: "key")
                    }
                    NavigationLink {
                        StartRoundView(
                            defaultRoundId: package.roundId,
                            syncStatus: syncStatus,
                            isPreparing: isPreparingRound,
                            onPrepareRound: onPrepareRound
                        )
                    } label: {
                        Label("Start Round", systemImage: "flag.checkered")
                    }
                    NavigationLink {
                        RecentRoundReviewView(package: package)
                    } label: {
                        Label("Recent Review", systemImage: "chart.line.uptrend.xyaxis")
                    }
                }

                Section("Holes") {
                    ForEach(package.holes) { hole in
                        NavigationLink {
                            CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, onEvent: onEvent)
                        } label: {
                            HStack {
                                Text("\(hole.number)")
                                    .font(.headline.monospacedDigit())
                                    .frame(width: 32, alignment: .leading)
                                VStack(alignment: .leading) {
                                    Text("Par \(hole.par)")
                                    Text(hole.geometryCoverage.rawValue)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Live Round")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Text(syncStatus)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}
