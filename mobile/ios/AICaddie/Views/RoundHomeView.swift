import Foundation
import SwiftUI

/// 球局主页(Hub)— 按已批准设计稿的「三件事」组织:打球(开始/继续)、
/// 备战 · 复盘、上一场速览。进行中可直接续打到当前洞;同步 / Garmin 账号 /
/// 后端等连接项收进底部「设置」段。保留全部导航目标的接线(实战逐洞、赛前攻略、
/// 历史复盘、离线就绪),仅重排呈现并中文化。
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
                playSection
                exploreSection
                lastRoundSection
                holesSection
                PackageReadinessSection(package: package)
                settingsSection
            }
            .navigationTitle("开球吧")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Text(syncStatus)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: - 打球(开始 / 继续)

    @ViewBuilder private var playSection: some View {
        Section {
            if let liveRoundState, let hole = package.holes.first(where: { $0.number == liveRoundState.activeHole }) {
                NavigationLink {
                    CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, liveRoundState: liveRoundState, onEvent: onEvent)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("进行中")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(AICaddieDesignTokens.par)
                        Text(package.course.name)
                            .font(.headline)
                        Text("第 \(liveRoundState.activeHole) 洞 · 已记 \(liveRoundState.holes.count)/\(package.holes.count) 洞")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Text("继续这场 →")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(AICaddieDesignTokens.par)
                    }
                    .padding(.vertical, 4)
                }
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
                Label("开始一场", systemImage: "flag.checkered")
            }
        } header: {
            Text("打球")
        }
    }

    // MARK: - 备战 · 复盘

    @ViewBuilder private var exploreSection: some View {
        Section {
            if let apiBaseURL, package.course.globalId != 0 {
                NavigationLink {
                    CourseReviewView(client: SyncClient(baseURL: apiBaseURL, adminToken: adminToken), globalId: package.course.globalId)
                } label: {
                    Label("赛前攻略", systemImage: "map")
                }
            }
            NavigationLink {
                RecentRoundReviewView(package: package)
            } label: {
                Label("历史复盘", systemImage: "chart.line.uptrend.xyaxis")
            }
        } header: {
            Text("备战 · 复盘")
        }
    }

    // MARK: - 上一场速览

    @ViewBuilder private var lastRoundSection: some View {
        if let last = package.recentHistory.rounds.first {
            Section("上一场") {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(last.courseName).font(.subheadline.weight(.semibold))
                        Text(last.date).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text("\(last.score)").font(.title3.monospacedDigit().weight(.bold))
                    Text(toParText(last.toPar))
                        .font(.caption.monospacedDigit())
                        .padding(.vertical, 3)
                        .padding(.horizontal, 8)
                        .background(AICaddieDesignTokens.scoreColor(toPar: last.toPar).opacity(0.16))
                        .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: last.toPar))
                        .clipShape(Capsule())
                }
            }
        }
    }

    // MARK: - 本场球洞(逐洞进入实战)

    @ViewBuilder private var holesSection: some View {
        Section("本场球洞") {
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

    // MARK: - 设置(同步 / 连接)

    @ViewBuilder private var settingsSection: some View {
        Section("设置") {
            Button {
                onSync()
            } label: {
                Label("同步", systemImage: "arrow.triangle.2.circlepath")
            }
            NavigationLink {
                GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken, sessionStore: sessionStore)
            } label: {
                Label("Garmin 账号", systemImage: "key")
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
                Label("后端", systemImage: "server.rack")
            }
            HStack {
                Label("\(package.clubProfiles.count)", systemImage: "golfclub")
                Spacer()
                Label("\(pendingEventCount)", systemImage: "tray.full")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }

    private func toParText(_ toPar: Int?) -> String {
        guard let toPar, toPar != 0 else {
            return "E"
        }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
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
