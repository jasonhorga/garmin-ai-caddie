import Foundation
import SwiftUI

public struct RoundHomeView: View {
    public let package: LiveRoundPackage
    public let pendingEventCount: Int
    public let syncStatus: String
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let adminTokenConfigured: Bool
    public let offlineStore: OfflineStore?
    public let sessionStore: GarminSessionStore?
    public let watchBridge: WatchEventBridge?
    public let liveRoundState: LiveRoundStateSnapshot?
    public let courseOptions: [MobileCourseOption]
    public let isPreparingRound: Bool
    public let onEvent: (LiveRoundEvent) -> Void
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String, String) -> Void
    public let onSync: () -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void

    public init(
        package: LiveRoundPackage,
        pendingEventCount: Int = 0,
        syncStatus: String = "Offline ready",
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        adminTokenConfigured: Bool = false,
        offlineStore: OfflineStore? = nil,
        sessionStore: GarminSessionStore? = GarminSessionStore(),
        watchBridge: WatchEventBridge? = nil,
        liveRoundState: LiveRoundStateSnapshot? = nil,
        courseOptions: [MobileCourseOption] = [],
        isPreparingRound: Bool = false,
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in },
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String, String) -> Void = { _, _, _, _ in },
        onSync: @escaping () -> Void = {},
        onSaveBackendConfiguration: @escaping (String, String?) -> Void = { _, _ in },
        onClearBackendConfiguration: @escaping () -> Void = {}
    ) {
        self.package = package
        self.pendingEventCount = pendingEventCount
        self.syncStatus = syncStatus
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.adminTokenConfigured = adminTokenConfigured
        self.offlineStore = offlineStore
        self.sessionStore = sessionStore
        self.watchBridge = watchBridge
        self.liveRoundState = liveRoundState
        self.courseOptions = courseOptions
        self.isPreparingRound = isPreparingRound
        self.onEvent = onEvent
        self.onPrepareRound = onPrepareRound
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onSync = onSync
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
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
                        GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken, sessionStore: sessionStore)
                    } label: {
                        Label("Garmin Session", systemImage: "key")
                    }
                    NavigationLink {
                        BackendSettingsView(
                            apiBaseURL: apiBaseURL,
                            adminTokenConfigured: adminTokenConfigured,
                            syncStatus: syncStatus,
                            onSave: onSaveBackendConfiguration,
                            onClear: onClearBackendConfiguration
                        )
                    } label: {
                        Label("Backend", systemImage: "server.rack")
                    }
                    NavigationLink {
                        StartRoundView(
                            defaultRoundId: package.roundId,
                            defaultCourseGlobalId: package.course.globalId == 0 ? nil : package.course.globalId,
                            defaultTeeBox: package.course.teeBox,
                            courseOptions: courseOptions,
                            syncStatus: syncStatus,
                            isPreparing: isPreparingRound,
                            apiBaseURL: apiBaseURL,
                            adminTokenConfigured: adminTokenConfigured,
                            onPrepareRound: onPrepareRound,
                            onPrepareCourseRound: onPrepareCourseRound,
                            onSaveBackendConfiguration: onSaveBackendConfiguration,
                            onClearBackendConfiguration: onClearBackendConfiguration
                        )
                    } label: {
                        Label("Start Round", systemImage: "flag.checkered")
                    }
                    NavigationLink {
                        RecentRoundReviewView(package: package)
                    } label: {
                        Label("Recent Review", systemImage: "chart.line.uptrend.xyaxis")
                    }
                    if let apiBaseURL, package.course.globalId != 0 {
                        NavigationLink {
                            CourseReviewView(client: SyncClient(baseURL: apiBaseURL, adminToken: adminToken), globalId: package.course.globalId)
                        } label: {
                            Label("赛前攻略", systemImage: "map")
                        }
                    }
                }

                PackageReadinessSection(package: package)

                Section("Holes") {
                    ForEach(package.holes) { hole in
                        NavigationLink {
                            CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, liveRoundState: liveRoundState, onEvent: onEvent)
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

private struct PackageReadinessSection: View {
    let package: LiveRoundPackage

    var body: some View {
        Section("Offline Package") {
            HStack(alignment: .firstTextBaseline) {
                Label(package.offlinePackageStatus.state.capitalized, systemImage: packageStatusIcon(package.offlinePackageStatus.state))
                    .foregroundStyle(readinessColor(package.offlinePackageStatus.state))
                Spacer()
                Text("Expires \(package.offlinePackageStatus.expiresAt)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            ForEach(package.readinessChecks) { check in
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(readinessLabel(check.label))
                            .font(.subheadline.weight(.semibold))
                        Spacer()
                        Text(check.state.capitalized)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(readinessColor(check.state))
                    }
                    HStack(spacing: 10) {
                        ProgressView(value: Double(check.ready), total: Double(max(check.total, 1)))
                            .tint(readinessColor(check.state))
                        Text("\(check.ready)/\(check.total)")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    Text(check.reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 2)
            }

            if !package.missingData.isEmpty {
                Label("\(package.missingData.count) missing data items", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(AICaddieDesignTokens.bogey)
            }
        }
    }

    private func readinessLabel(_ label: String) -> String {
        label.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func readinessColor(_ state: String) -> Color {
        switch state.lowercased() {
        case "ready":
            return AICaddieDesignTokens.par
        case "degraded", "partial", "stale":
            return AICaddieDesignTokens.bogey
        case "missing", "expired":
            return AICaddieDesignTokens.doubleBogey
        default:
            return AICaddieDesignTokens.neutral
        }
    }

    private func packageStatusIcon(_ state: String) -> String {
        switch state.lowercased() {
        case "ready":
            return "checkmark.seal"
        case "expired":
            return "clock.badge.exclamationmark"
        default:
            return "exclamationmark.triangle"
        }
    }
}
