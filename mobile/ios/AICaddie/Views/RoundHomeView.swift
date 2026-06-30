import Foundation
import SwiftUI

/// 球局主页(Hub)— 已批准设计稿的「三件事」卡片版:打球(开始/继续 + 中途加/减九洞)、
/// 备战 · 复盘磁贴、上一场速览。灰底圆角白卡(ScrollView),保留导航接线(实战逐洞、
/// 赛前攻略、历史复盘、同步、Garmin 账号)。工程项(离线诊断、后端地址)不对用户暴露。
/// 表现型卡片组件(Hub*)纯输入,供 CI 设计快照复用。
/// Hub navigation routes driven by a path, so the app can jump straight into the live hole after
/// 开始记分 (instead of bouncing back to the Hub). 备战/复盘 stay simple leaf links.
public enum HubRoute: Hashable {
    case start
    case hole(Int)
}

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
    public let onPrepareCompositeRound: (Int, Int, String, String) -> Void
    public let onChangeNine: (String) -> Void
    public let onDiscard: () -> Void
    public let onSync: () -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void
    /// Set to a hole number right after a fresh round is prepared → auto-navigate into that hole.
    public let pendingLiveHole: Int?
    public let onConsumePendingLiveHole: () -> Void

    @State private var showSettings = false
    @State private var path: [HubRoute] = []

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
        onPrepareCompositeRound: @escaping (Int, Int, String, String) -> Void = { _, _, _, _ in },
        onChangeNine: @escaping (String) -> Void = { _ in },
        onDiscard: @escaping () -> Void = {},
        onSync: @escaping () -> Void = {},
        onSaveBackendConfiguration: @escaping (String, String?) -> Void = { _, _ in },
        onClearBackendConfiguration: @escaping () -> Void = {},
        pendingLiveHole: Int? = nil,
        onConsumePendingLiveHole: @escaping () -> Void = {}
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
        self.onPrepareCompositeRound = onPrepareCompositeRound
        self.onChangeNine = onChangeNine
        self.onDiscard = onDiscard
        self.onSync = onSync
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
        self.pendingLiveHole = pendingLiveHole
        self.onConsumePendingLiveHole = onConsumePendingLiveHole
    }

    public var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(spacing: 12) {
                    playCard
                    tilesRow
                    lastRoundCard
                }
                .padding(14)
            }
            .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
            .navigationTitle("AI 球童")
            .navigationDestination(for: HubRoute.self) { route in
                switch route {
                case .start:
                    startRoundView
                case .hole(let number):
                    currentHoleView(number)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                settingsSheet
            }
            // Prefetch the real Garmin bag so the live picker uses it even if 球杆设置 is never opened.
            .task {
                await refreshRealClubBag(apiBaseURL: apiBaseURL, adminToken: adminToken)
            }
        }
        .onChange(of: pendingLiveHole) { _, hole in
            // 开始记分后直接进实战屏:把刚开的洞设为唯一路径(替换掉「开始一场」),不弹回 Hub。
            guard let hole else { return }
            path = [.hole(hole)]
            onConsumePendingLiveHole()
        }
    }

    @ViewBuilder private func currentHoleView(_ number: Int) -> some View {
        if let hole = package.holes.first(where: { $0.number == number }) {
            // round-11: forward the round-management closures so 球局调整(加打/减九洞/结束本场)lives
            // inside the in-progress screen instead of the Hub.
            CurrentHoleView(
                package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken,
                offlineStore: offlineStore, watchBridge: watchBridge, liveRoundState: liveRoundState,
                courseOptions: courseOptions, startingNine: startingNine, isPreparingRound: isPreparingRound,
                onChangeNine: onChangeNine, onPrepareCourseRound: onPrepareCourseRound,
                onPrepareCompositeRound: onPrepareCompositeRound, onDiscard: onDiscard, onEvent: onEvent
            )
        }
    }

    private var startRoundView: some View {
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
            onPrepareCompositeRound: onPrepareCompositeRound,
            onSaveBackendConfiguration: onSaveBackendConfiguration,
            onClearBackendConfiguration: onClearBackendConfiguration,
            onConnectGarmin: { showSettings = true }
        )
    }

    // MARK: - 打球(开始 / 继续 + 加打/移除九洞)

    @ViewBuilder private var playCard: some View {
        if let liveRoundState, package.holes.contains(where: { $0.number == liveRoundState.activeHole }) {
            NavigationLink(value: HubRoute.hole(liveRoundState.activeHole)) {
                HubInProgressCard(
                    courseName: package.course.name,
                    activeHole: liveRoundState.activeHole,
                    recorded: liveRoundState.holes.count,
                    total: package.holes.count
                )
            }
            .buttonStyle(.plain)
        }
        NavigationLink(value: HubRoute.start) {
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

    // MARK: - 备战 · 复盘 · 统计 磁贴(复盘=单场逐洞,统计=历史宏观,分开)

    @ViewBuilder private var tilesRow: some View {
        HStack(spacing: 10) {
            if let apiBaseURL {
                NavigationLink {
                    // 备战先选球场,而不是锁死在当前球场。
                    PrepCoursePickerView(courseOptions: courseOptions, apiBaseURL: apiBaseURL, adminToken: adminToken)
                } label: {
                    HubTile(icon: "map", title: "赛前攻略", subtitle: "选球场 · 逐洞")
                }
                .buttonStyle(.plain)
            }
            NavigationLink {
                RecentRoundReviewView(package: package, apiBaseURL: apiBaseURL, adminToken: adminToken)
            } label: {
                HubTile(icon: "list.bullet.rectangle", title: "历史复盘", subtitle: "逐场逐洞")
            }
            .buttonStyle(.plain)
            NavigationLink {
                StatsView(apiBaseURL: apiBaseURL, adminToken: adminToken)
            } label: {
                HubTile(icon: "chart.bar.xaxis", title: "数据统计", subtitle: "均杆 · 趋势 · 球杆")
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - 上一场速览

    @ViewBuilder private var lastRoundCard: some View {
        if let last = package.recentHistory.rounds.first {
            NavigationLink {
                RoundReviewView(roundRef: last.roundId, fallbackCourseName: last.courseName,
                                apiBaseURL: apiBaseURL, adminToken: adminToken)
            } label: {
                HubLastRoundCard(
                    courseName: last.courseName,
                    date: last.date,
                    score: last.score,
                    toPar: last.toPar
                )
            }
            .buttonStyle(.plain)
        }
    }

    // 本场逐洞跳转网格已从首页移除(用户反馈:首页这块「不知道干嘛用的」)。进行中的球局从「继续这场」
    // 卡进入实战屏,逐洞推进;首页只保留 打球 / 球局调整 / 备战·复盘·统计 / 上一场,更精简。

    // MARK: - 设置 sheet(齿轮入口)— Garmin 账号 + 手动同步兜底。记分时已自动同步,
    // 主页不再放 Garmin/同步(用户要求:同步自动化、Garmin 不写在主页)。

    private var settingsSheet: some View {
        NavigationStack {
            List {
                Section {
                    NavigationLink {
                        ClubSettingsView(clubProfiles: package.clubProfiles, apiBaseURL: apiBaseURL, adminToken: adminToken)
                    } label: {
                        Label("球杆设置", systemImage: "bag")
                    }
                } header: {
                    Text("球包")
                } footer: {
                    Text("默认就是你 Garmin 里在用的那套球杆(真实名字),可手动增减;实战选杆和球童建议只用这些。")
                }
                Section {
                    NavigationLink {
                        GarminSessionView(apiBaseURL: apiBaseURL, adminToken: adminToken, sessionStore: sessionStore)
                    } label: {
                        Label("Garmin 账号", systemImage: "key")
                    }
                    Button {
                        onSync()
                    } label: {
                        Label("同步", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .foregroundStyle(LiveHoleStyle.green)
                    if pendingEventCount > 0 {
                        Label("\(pendingEventCount) 条待同步", systemImage: "tray.full")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("数据")
                } footer: {
                    Text("记分时会自动同步到 Garmin / 后端;这里可手动触发或管理账号。")
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") {
                        showSettings = false
                    }
                }
            }
        }
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
                Text(aiCaddieShortDate(date)).font(.caption).foregroundStyle(.secondary)
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
