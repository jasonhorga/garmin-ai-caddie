import Foundation
import SwiftUI

/// 球局主页(Hub)— 已批准设计稿的「三件事」卡片版:打球(开始/继续 + 中途加/减九洞)、
/// 备战 · 复盘磁贴、上一场速览。灰底圆角白卡(ScrollView),保留全部导航接线(实战逐洞、
/// 赛前攻略、历史复盘、离线就绪、同步/Garmin/后端)。表现型卡片组件(Hub*)纯输入,
/// 供 CI 设计快照复用。
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
    public let startingNine: String?
    public let isPreparingRound: Bool
    public let onEvent: (LiveRoundEvent) -> Void
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String, String) -> Void
    public let onChangeNine: (String) -> Void
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
        startingNine: String? = nil,
        isPreparingRound: Bool = false,
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in },
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String, String) -> Void = { _, _, _, _ in },
        onChangeNine: @escaping (String) -> Void = { _ in },
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
        self.startingNine = startingNine
        self.isPreparingRound = isPreparingRound
        self.onEvent = onEvent
        self.onPrepareRound = onPrepareRound
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onChangeNine = onChangeNine
        self.onSync = onSync
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    playCard
                    tilesRow
                    lastRoundCard
                    holesCard
                    PackageReadinessSection(package: package)
                    settingsCard
                }
                .padding(14)
            }
            .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
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

    // MARK: - 打球(开始 / 继续 + 加打/移除九洞)

    @ViewBuilder private var playCard: some View {
        if let liveRoundState, let hole = package.holes.first(where: { $0.number == liveRoundState.activeHole }) {
            NavigationLink {
                CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, liveRoundState: liveRoundState, onEvent: onEvent)
            } label: {
                HubInProgressCard(
                    courseName: package.course.name,
                    activeHole: liveRoundState.activeHole,
                    recorded: liveRoundState.holes.count,
                    total: package.holes.count
                )
            }
            .buttonStyle(.plain)
        }
        nineControl
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
                .font(.headline)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 15)
                .background(LiveHoleStyle.green)
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    /// 起始九洞的加打 / 撤销:nine 是对一局 18 洞的视图过滤,已记杆按 roundId 保留。
    @ViewBuilder private var nineControl: some View {
        if package.course.globalId != 0 {
            let currentNine = package.nine ?? "all"
            if currentNine != "all" {
                Button {
                    onChangeNine("all")
                } label: {
                    Label("＋加打另外 9 洞(凑 18)", systemImage: "plus.circle")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(LiveHoleStyle.green)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.green))
                }
                .buttonStyle(.plain)
                .disabled(isPreparingRound)
            } else if let startingNine, startingNine != "all" {
                Button {
                    onChangeNine(startingNine)
                } label: {
                    Label("移除另外 9 洞 · 只打\(nineText(startingNine))", systemImage: "minus.circle")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(.secondary)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
                }
                .buttonStyle(.plain)
                .disabled(isPreparingRound)
            }
        }
    }

    private func nineText(_ nine: String) -> String {
        switch nine {
        case "front":
            return "前九"
        case "back":
            return "后九"
        default:
            return "全 18 洞"
        }
    }

    // MARK: - 备战 · 复盘 磁贴

    @ViewBuilder private var tilesRow: some View {
        HStack(spacing: 10) {
            if let apiBaseURL, package.course.globalId != 0 {
                NavigationLink {
                    CourseReviewView(client: SyncClient(baseURL: apiBaseURL, adminToken: adminToken), globalId: package.course.globalId)
                } label: {
                    HubTile(icon: "map", title: "赛前攻略", subtitle: "逐洞攻略 · 试算一杆")
                }
                .buttonStyle(.plain)
            }
            NavigationLink {
                RecentRoundReviewView(package: package)
            } label: {
                HubTile(icon: "chart.line.uptrend.xyaxis", title: "历史复盘", subtitle: "\(package.recentHistory.rounds.count) 场近况")
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - 上一场速览

    @ViewBuilder private var lastRoundCard: some View {
        if let last = package.recentHistory.rounds.first {
            HubLastRoundCard(
                courseName: last.courseName,
                date: last.date,
                score: last.score,
                toPar: last.toPar
            )
        }
    }

    // MARK: - 本场球洞(逐洞进入实战)

    @ViewBuilder private var holesCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("本场球洞").font(.caption).foregroundStyle(.secondary)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                ForEach(package.holes) { hole in
                    NavigationLink {
                        CurrentHoleView(package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken, offlineStore: offlineStore, watchBridge: watchBridge, liveRoundState: liveRoundState, onEvent: onEvent)
                    } label: {
                        HStack(spacing: 6) {
                            Text("\(hole.number)").font(.subheadline.monospacedDigit().weight(.bold))
                            Text("Par \(hole.par)").font(.caption2).foregroundStyle(.secondary)
                            Spacer(minLength: 0)
                        }
                        .padding(.vertical, 9)
                        .padding(.horizontal, 10)
                        .frame(maxWidth: .infinity)
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(LiveHoleStyle.line))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.primary)
                }
            }
        }
        .liveCard()
    }

    // MARK: - 设置(同步 / 连接)

    @ViewBuilder private var settingsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("设置").font(.caption).foregroundStyle(.secondary)
            Button {
                onSync()
            } label: {
                Label("同步", systemImage: "arrow.triangle.2.circlepath")
            }
            .buttonStyle(.plain)
            .foregroundStyle(LiveHoleStyle.green)
            NavigationLink {
                GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken, sessionStore: sessionStore)
            } label: {
                settingsRow(Label("Garmin 账号", systemImage: "key"))
            }
            .buttonStyle(.plain)
            NavigationLink {
                BackendSettingsView(
                    apiBaseURL: apiBaseURL,
                    adminTokenConfigured: adminTokenConfigured,
                    syncStatus: syncStatus,
                    onSave: onSaveBackendConfiguration,
                    onClear: onClearBackendConfiguration
                )
            } label: {
                settingsRow(Label("后端", systemImage: "server.rack"))
            }
            .buttonStyle(.plain)
            HStack {
                Label("\(package.clubProfiles.count)", systemImage: "golfclub")
                Spacer()
                Label("\(pendingEventCount)", systemImage: "tray.full")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .liveCard()
    }

    private func settingsRow(_ label: some View) -> some View {
        HStack {
            label
            Spacer()
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
        }
        .foregroundStyle(.primary)
    }
}

// MARK: - 表现型卡片(纯输入 → CI 设计快照可复用)

/// 进行中卡:绿描边白卡,course + 第X/Z洞 + 已记进度 + 继续提示。
struct HubInProgressCard: View {
    let courseName: String
    let activeHole: Int
    let recorded: Int
    let total: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("进行中")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(LiveHoleStyle.green)
                Spacer()
                Text("第 \(activeHole)/\(total) 洞")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(courseName).font(.title3.weight(.bold))
            Text("已记 \(recorded) 洞 · 共 \(total) 洞")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("继续这场 →")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LiveHoleStyle.green)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(LiveHoleStyle.green, lineWidth: 1.5))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

/// 备战 / 历史复盘 入口磁贴(竖排图标 + 标题 + 副标题)。
struct HubTile: View {
    let icon: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(LiveHoleStyle.green)
            Text(title).font(.subheadline.weight(.bold)).foregroundStyle(.primary)
            Text(subtitle)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color.white)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(LiveHoleStyle.line))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

/// 上一场速览卡:杆数大字 + 相对标准杆 chip(score token 配色)。
struct HubLastRoundCard: View {
    let courseName: String
    let date: String
    let score: Int
    let toPar: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("上一场").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text(date).font(.caption).foregroundStyle(.secondary)
            }
            HStack(alignment: .firstTextBaseline) {
                Text(courseName).font(.subheadline.weight(.semibold))
                Spacer()
                Text("\(score)").font(.title2.monospacedDigit().weight(.bold))
                Text(toParText)
                    .font(.caption.monospacedDigit())
                    .padding(.vertical, 3)
                    .padding(.horizontal, 8)
                    .background(AICaddieDesignTokens.scoreColor(toPar: toPar).opacity(0.16))
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                    .clipShape(Capsule())
            }
        }
        .liveCard()
    }

    private var toParText: String {
        guard let toPar, toPar != 0 else {
            return "E"
        }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}

// MARK: - 离线就绪卡

private struct PackageReadinessSection: View {
    let package: LiveRoundPackage

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text("离线就绪").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Label(package.offlinePackageStatus.state.capitalized, systemImage: packageStatusIcon(package.offlinePackageStatus.state))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(readinessColor(package.offlinePackageStatus.state))
            }
            Text("到期 \(package.offlinePackageStatus.expiresAt)")
                .font(.caption2)
                .foregroundStyle(.secondary)

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
                Label("\(package.missingData.count) 项缺数据", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(AICaddieDesignTokens.bogey)
            }
        }
        .liveCard()
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
