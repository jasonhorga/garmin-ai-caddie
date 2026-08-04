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
    case history
    case roundReview(roundRef: String, courseName: String?)
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
    public let isFinishingRound: Bool
    public let finishErrorMessage: String?
    public let onEvent: (LiveRoundEvent) -> Void
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String, String) -> Void
    public let onPrepareCompositeRound: (Int, Int, String, String) -> Void
    public let onChangeNine: (String) -> Void
    public let onFinishRound: () async -> Bool
    public let onSetActiveHole: (Int) -> Void
    public let onSync: () -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void
    /// 拉取所选球场的可选发球台(供「开始一场」的选台器);仅转发给 StartRoundView。
    public let onLoadCourseTees: (Int) async -> [CourseTee]
    /// Garmin 全库名称搜索；StartRoundView 只保留本次结果，选中后走现有单球场准备链。
    public let onSearchCourses: (String, Double?, Double?) async throws -> [MobileCourseSearchMatch]
    /// Garmin 全库坐标发现；StartRoundView 只保留本次结果。
    public let onNearbyCourses: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]
    /// Set to a hole number right after a fresh round is prepared → auto-navigate into that hole.
    public let pendingLiveHole: Int?
    public let onConsumePendingLiveHole: () -> Void
    public let onLiveAppearanceChanged: (Bool) -> Void

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
        isFinishingRound: Bool = false,
        finishErrorMessage: String? = nil,
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in },
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String, String) -> Void = { _, _, _, _ in },
        onPrepareCompositeRound: @escaping (Int, Int, String, String) -> Void = { _, _, _, _ in },
        onChangeNine: @escaping (String) -> Void = { _ in },
        onFinishRound: @escaping () async -> Bool = { false },
        onSetActiveHole: @escaping (Int) -> Void = { _ in },
        onSync: @escaping () -> Void = {},
        onSaveBackendConfiguration: @escaping (String, String?) -> Void = { _, _ in },
        onClearBackendConfiguration: @escaping () -> Void = {},
        onLoadCourseTees: @escaping (Int) async -> [CourseTee] = { _ in [] },
        onSearchCourses: @escaping (String, Double?, Double?) async throws -> [MobileCourseSearchMatch] = { _, _, _ in [] },
        onNearbyCourses: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch] = { _, _, _ in [] },
        pendingLiveHole: Int? = nil,
        onConsumePendingLiveHole: @escaping () -> Void = {},
        onLiveAppearanceChanged: @escaping (Bool) -> Void = { _ in }
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
        self.isFinishingRound = isFinishingRound
        self.finishErrorMessage = finishErrorMessage
        self.onEvent = onEvent
        self.onPrepareRound = onPrepareRound
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onPrepareCompositeRound = onPrepareCompositeRound
        self.onChangeNine = onChangeNine
        self.onFinishRound = onFinishRound
        self.onSetActiveHole = onSetActiveHole
        self.onSync = onSync
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
        self.onLoadCourseTees = onLoadCourseTees
        self.onSearchCourses = onSearchCourses
        self.onNearbyCourses = onNearbyCourses
        self.pendingLiveHole = pendingLiveHole
        self.onConsumePendingLiveHole = onConsumePendingLiveHole
        self.onLiveAppearanceChanged = onLiveAppearanceChanged
        #if DEBUG
        let environment = ProcessInfo.processInfo.environment
        if environment["UITEST_MODE"] == "1",
           let roundRef = environment["UITEST_REVIEW_ROUND_REF"],
           !roundRef.isEmpty {
            self._path = State(initialValue: [
                .history,
                .roundReview(
                    roundRef: roundRef,
                    courseName: environment["UITEST_REVIEW_COURSE_NAME"]
                ),
            ])
        }
        #endif
    }

    /// Nameless, time-of-day greeting (早上好 / 中午好 / 下午好 / 晚上好) — the home's large title.
    private var greeting: String {
        switch Calendar.current.component(.hour, from: Date()) {
        case 5..<11: return "早上好"
        case 11..<13: return "中午好"
        case 13..<18: return "下午好"
        default: return "晚上好"
        }
    }

    public var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(spacing: 14) {
                    playSection
                    tilesRow
                    lastRoundSection
                }
                .padding(.horizontal, 16)
                .padding(.top, 4)
                .padding(.bottom, 22)
            }
            .background(HubStyle.grouped)
            // A nameless, time-of-day greeting stands in for the app-name title (no personal name).
            .navigationTitle(greeting)
            .navigationBarTitleDisplayMode(.large)
            .navigationDestination(for: HubRoute.self) { route in
                switch route {
                case .start:
                    startRoundView
                case .hole(let number):
                    currentHoleView(number)
                case .history:
                    RecentRoundReviewView(
                        package: package,
                        apiBaseURL: apiBaseURL,
                        adminToken: adminToken
                    )
                case .roundReview(let roundRef, let courseName):
                    RoundReviewView(
                        roundRef: roundRef,
                        fallbackCourseName: courseName,
                        apiBaseURL: apiBaseURL,
                        adminToken: adminToken
                    )
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
        // The NavigationStack owns the system status bar, so the immersive hole destination cannot
        // hide it reliably from inside CurrentHoleView. Keep normal chrome on every non-live route.
        .statusBarHidden(Self.isLiveHoleRoute(path.last))
        .onChange(of: pendingLiveHole) { _, hole in
            // 开始记分后直接进实战屏:把刚开的洞设为唯一路径(替换掉「开始一场」),不弹回 Hub。
            guard let hole else { return }
            path = [.hole(hole)]
            onConsumePendingLiveHole()
        }
        .onChange(of: liveRoundState?.roundId) { previousRoundId, currentRoundId in
            if previousRoundId != nil, currentRoundId == nil {
                path = []
            }
        }
        .onChange(of: path) { _, routes in
            onLiveAppearanceChanged(Self.isLiveHoleRoute(routes.last))
        }
        .onAppear {
            onLiveAppearanceChanged(Self.isLiveHoleRoute(path.last))
        }
        .onDisappear {
            onLiveAppearanceChanged(false)
        }
    }

    private static func isLiveHoleRoute(_ route: HubRoute?) -> Bool {
        guard case .hole = route else { return false }
        return true
    }

    @ViewBuilder private func currentHoleView(_ number: Int) -> some View {
        if let hole = package.holes.first(where: { $0.number == number }) {
            // round-11: forward the round-management closures so 球局调整(加打/减九洞/结束本场)lives
            // inside the in-progress screen instead of the Hub.
            CurrentHoleView(
                package: package, hole: hole, caddieBaseURL: apiBaseURL, adminToken: adminToken,
                offlineStore: offlineStore, watchBridge: watchBridge, liveRoundState: liveRoundState,
                courseOptions: courseOptions, startingNine: startingNine, isPreparingRound: isPreparingRound,
                pendingEventCount: pendingEventCount, isFinishingRound: isFinishingRound,
                finishErrorMessage: finishErrorMessage,
                onChangeNine: onChangeNine, onPrepareCourseRound: onPrepareCourseRound,
                onPrepareCompositeRound: onPrepareCompositeRound, onFinishRound: onFinishRound,
                onAdvanceHole: { next in
                    onSetActiveHole(next)
                    path = [.hole(next)]
                },
                onEvent: onEvent
            )
            // A hole owns its score/club/map/GPS presentation state and scroll position. NavigationStack
            // otherwise reuses the same destination view when `.hole(1)` becomes `.hole(2)`, carrying
            // the prior hole's @State and scroll offset into the next hole. Explicit round+hole identity
            // gives every ordered transition a fresh live surface; LocationProvider immediately republishes
            // its injected fix in UI tests and resumes Core Location normally on a real device.
            .id("\(package.roundId):\(hole.number)")
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
            onConnectGarmin: { showSettings = true },
            onLoadCourseTees: onLoadCourseTees,
            onSearchCourses: onSearchCourses,
            onNearbyCourses: onNearbyCourses
        )
    }

    // MARK: - 打球(开始 / 继续 + 加打/移除九洞)

    @ViewBuilder private var playSection: some View {
        if let liveRoundState, package.holes.contains(where: { $0.number == liveRoundState.activeHole }) {
            NavigationLink(value: HubRoute.hole(liveRoundState.activeHole)) {
                HubInProgressCard(
                    courseName: package.course.name,
                    activeHole: liveRoundState.activeHole,
                    recorded: recordedScoreHoleCount,
                    total: package.holes.count
                )
            }
            .buttonStyle(.plain)
        }
        // 打球 = the wide primary tile (was the full-width green button); opens 开始一场 (StartRoundView).
        NavigationLink(value: HubRoute.start) {
            HubPlayTile()
        }
        .buttonStyle(.plain)
    }

    /// A restored snapshot contains one default state for every package hole, including holes the
    /// player has not scored. Home progress therefore comes from the durable score events, matching
    /// the in-round scorecard, rather than from `liveRoundState.holes.count`.
    private var recordedScoreHoleCount: Int {
        guard let offlineStore, let events = try? offlineStore.loadEvents() else { return 0 }
        let displayedHoles = Set(package.holes.map(\.number))
        return Set<Int>(events.compactMap { event in
            guard event.roundId == package.roundId,
                  event.kind == .score,
                  displayedHoles.contains(event.hole) else {
                return nil
            }
            return event.hole
        }).count
    }

    // MARK: - 备战 · 复盘 · 统计 磁贴(复盘=单场逐洞,统计=历史宏观,分开)

    @ViewBuilder private var tilesRow: some View {
        HStack(spacing: 11) {
            if let apiBaseURL {
                NavigationLink {
                    // 备战先选球场,而不是锁死在当前球场。
                    PrepCoursePickerView(courseOptions: courseOptions, apiBaseURL: apiBaseURL, adminToken: adminToken)
                } label: {
                    HubTile(icon: "scope", title: "备战", subtitle: "选场 · 球童试算")
                }
                .buttonStyle(.plain)
            }
            NavigationLink(value: HubRoute.history) {
                HubTile(icon: "clock.arrow.circlepath", title: "历史复盘", subtitle: "逐洞落点")
            }
            .buttonStyle(.plain)
            NavigationLink {
                StatsView(apiBaseURL: apiBaseURL, adminToken: adminToken)
            } label: {
                HubTile(icon: "chart.bar.xaxis", title: "数据统计", subtitle: "均杆 · 趋势")
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - 上一场速览

    @ViewBuilder private var lastRoundSection: some View {
        if let last = package.recentHistory.rounds.first {
            VStack(alignment: .leading, spacing: 9) {
                HubSectionLabel("上一场")
                NavigationLink(
                    value: HubRoute.roundReview(
                        roundRef: last.roundId,
                        courseName: last.courseName
                    )
                ) {
                    HubLastRoundCard(
                        courseName: last.courseName,
                        date: last.date,
                        score: last.score,
                        toPar: last.toPar,
                        holesCompleted: last.holesCompleted,
                        par: last.par,
                        topoURL: lastRoundTopoURL(last)
                    )
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-last-round-row")
            }
            .padding(.top, 6)
        }
    }

    /// 上一场第 1 洞的真实地形缩略图 URL:需要 apiBaseURL + 该盘球场 globalId(后端随 summary 下发,
    /// 且 PR #263 已把最近一盘的 topo 预渲缓存 → 取图快)。缺任一 → nil → 卡片回退纯文字,绝不造图。
    private func lastRoundTopoURL(_ round: RecentRoundSummary) -> URL? {
        guard let apiBaseURL, let globalId = round.globalId else { return nil }
        return SyncClient.topoImageURL(baseURL: apiBaseURL, globalId: globalId, localHole: 1)
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

/// 进行中英雄卡:白卡 + 淡绿描边 + 绿点「进行中」标签,球场·当前洞 + 已打进度 + 绿「继续 ›」胶囊。
struct HubInProgressCard: View {
    let courseName: String
    let activeHole: Int
    let recorded: Int
    let total: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 7) {
                Circle().fill(HubStyle.liveDot).frame(width: 8, height: 8)
                Text("进行中")
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(LiveHoleStyle.green)
            }
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("\(courseName) · 第 \(activeHole) 洞")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("已打 \(recorded) 洞 · 共 \(total) 洞")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                Text("继续 ›")
                    .font(.subheadline.weight(.heavy))
                    .foregroundStyle(.white)
                    .padding(.vertical, 11)
                    .padding(.horizontal, 17)
                    .background(LiveHoleStyle.green)
                    .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(HubStyle.heroBorder, lineWidth: 1))
        .shadow(color: LiveHoleStyle.green.opacity(0.12), radius: 10, x: 0, y: 4)
    }
}

/// 打球:宽图块(绿色实心旗帜图标 + 标题/副标题 + 右侧 ›),点击开始一场(StartRoundView)。
struct HubPlayTile: View {
    var body: some View {
        HStack(spacing: 14) {
            HubIconSquare(system: "flag.fill", filled: true)
            VStack(alignment: .leading, spacing: 2) {
                Text("打球").font(.title3.weight(.bold)).foregroundStyle(.primary)
                Text("新开一场 · 选起始 9 洞").font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .hubCard()
    }
}

/// 备战 / 历史复盘 / 数据统计 入口磁贴(左上绿色图标方块 + 标题 + 副标题)。
struct HubTile: View {
    let icon: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HubIconSquare(system: icon)
            Spacer(minLength: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.bold)).foregroundStyle(.primary)
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 104, alignment: .leading)
        .hubCard(padding: 14)
    }
}

/// 上一场速览卡:左侧真实球道缩略图(那盘球场第 1 洞 topo)+ 球场 · 日期 + 杆数大字 +
/// 相对标准杆(score token 配色)。`topoURL == nil`(缺 globalId / 无 apiBaseURL)→ 不放图,
/// 布局与纯文字版一致,绝不破版、绝不造图。
struct HubLastRoundCard: View {
    let courseName: String
    let date: String
    let score: Int
    let toPar: Int?
    var holesCompleted: Int? = nil
    var par: Int? = nil
    /// 那盘球场第 1 洞的真实地形缩略图 URL;nil → 回退纯文字卡(见 `lastRoundTopoURL`)。
    var topoURL: URL? = nil

    var body: some View {
        HStack(spacing: 12) {
            if let topoURL {
                thumbnail(topoURL)
            }
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(courseName)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.primary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .layoutPriority(1)
                    Spacer(minLength: 8)
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Text("\(score)")
                            .font(.system(size: 26, weight: .heavy))
                            .monospacedDigit()
                            .foregroundStyle(.primary)
                        Text(toParText)
                            .font(.subheadline.weight(.bold))
                            .monospacedDigit()
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                    }
                    .fixedSize()
                }
                HStack(spacing: 5) {
                    Text(aiCaddieShortDate(date)).font(.caption.weight(.semibold))
                    if let subtitle = holesParText {
                        Text("· \(subtitle)").font(.caption2)
                    }
                }
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
        }
        .hubCard()
    }

    /// 小尺寸圆角地形缩略图。加载中 / 加载失败 / CI 快照无网络 → 克制的绿调占位(map 图标),
    /// 与卡片风格一致、绝不显示破图空框。真实地形图靠真机加载(ImageRenderer 快照里恒为占位)。
    @ViewBuilder private func thumbnail(_ url: URL) -> some View {
        AsyncImage(url: url) { phase in
            switch phase {
            case .success(let image):
                image.resizable().scaledToFill()
            default:
                thumbnailPlaceholder
            }
        }
        .frame(width: 56, height: 56)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color.black.opacity(0.06), lineWidth: 1)
        )
        .accessibilityHidden(true)
    }

    private var thumbnailPlaceholder: some View {
        ZStack {
            HubStyle.iconTint
            Image(systemName: "map")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(LiveHoleStyle.green.opacity(0.55))
        }
    }

    private var holesParText: String? {
        var parts: [String] = []
        if let holesCompleted { parts.append("\(holesCompleted) 洞") }
        if let par { parts.append("Par \(par)") }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var toParText: String {
        guard let toPar, toPar != 0 else {
            return "E"
        }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }
}
