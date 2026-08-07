import SwiftUI

/// 开始一场 — GPS 先列附近球场；其他球场由玩家按城市或名称主动搜索。
/// 附近只有一个球场时自动进入该球场的洞组/发球台选择，多个时由玩家选择。
/// 手动 ID / 仅刷新离线包 / 后端连接等工程项收进折叠的「高级设置」,默认不打扰。
public struct StartRoundView: View {
    public let defaultRoundId: String
    public let courseOptions: [MobileCourseOption]
    public let downloadedCourseOptions: [MobileCourseOption]
    public let syncStatus: String
    public let isPreparing: Bool
    public let apiBaseURL: URL?
    public let adminTokenConfigured: Bool
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String, String) -> Void
    /// 组合 18 洞:(front 环 globalId, back 环 globalId, teeBox, roundId)。选了第二个环时调用。
    public let onPrepareCompositeRound: (Int, Int, String, String) -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void
    /// 还没有球场时的「连接 Garmin」CTA:由 app 注入(打开 Garmin 连接流程),拉取球场后就能记分。
    public let onConnectGarmin: () -> Void
    /// 拉取所选球场的可选发球台(GET /courses/{id}/tees:颜色 + 总码数 + 默认台)。
    /// 离线/出错返回 [] → 选台器回退到球场自带的 CourseView Tee 名(无码数)。
    public let onLoadCourseTees: (Int) async -> [CourseTee]
    /// Garmin 全库名称搜索。只返回轻量 metadata；选中后仍走本页已有的单球场准备链。
    public let onSearchCourses: (String, Double?, Double?) async throws -> [MobileCourseSearchMatch]
    /// Garmin 全库坐标发现。半径内完整分页，只返回轻量 metadata。
    public let onNearbyCourses: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]

    @StateObject private var locationProvider = LocationProvider()
    @State private var roundId: String
    @State private var courseGlobalIdText: String
    @State private var backGlobalIdText: String = ""
    @State private var userPickedVenue = false
    @State private var teeBox: String
    @State private var nine: String
    /// 所选球场的发球台列表(含码数/默认),来自 GET /courses/{id}/tees;为空则用球场自带 Tee 名。
    @State private var fetchedTees: [CourseTee] = []
    @State private var nearbyCourseOptions: [MobileCourseOption] = []
    @State private var remoteCourseOptions: [MobileCourseOption] = []
    @State private var showingCourseSearch = false
    @State private var isLoadingTees = false
    @State private var teeLoadFailed = false
    @State private var isLoadingNearby = false
    @State private var nearbyStatusText: String?

    public init(
        // 不在消费者界面里写死可读的原始局号(如 900001):没显式传时生成一个不透明的本地局号,
        // 真正开始记分时局号由所选球场派生(applySelectedCourse),后端据此建局。
        defaultRoundId: String = "live-\(UUID().uuidString)",
        defaultCourseGlobalId: Int? = nil,
        defaultTeeBox: String = "unknown",
        courseOptions: [MobileCourseOption] = [],
        downloadedCourseOptions: [MobileCourseOption] = [],
        syncStatus: String = "Offline ready",
        isPreparing: Bool = false,
        apiBaseURL: URL? = nil,
        adminTokenConfigured: Bool = false,
        onPrepareRound: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String, String) -> Void = { _, _, _, _ in },
        onPrepareCompositeRound: @escaping (Int, Int, String, String) -> Void = { _, _, _, _ in },
        onSaveBackendConfiguration: @escaping (String, String?) -> Void = { _, _ in },
        onClearBackendConfiguration: @escaping () -> Void = {},
        onConnectGarmin: @escaping () -> Void = {},
        onLoadCourseTees: @escaping (Int) async -> [CourseTee] = { _ in [] },
        onSearchCourses: @escaping (String, Double?, Double?) async throws -> [MobileCourseSearchMatch] = { _, _, _ in [] },
        onNearbyCourses: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch] = { _, _, _ in [] }
    ) {
        self.defaultRoundId = defaultRoundId
        self.courseOptions = courseOptions
        self.downloadedCourseOptions = downloadedCourseOptions
        self.syncStatus = syncStatus
        self.isPreparing = isPreparing
        self.apiBaseURL = apiBaseURL
        self.adminTokenConfigured = adminTokenConfigured
        self.onPrepareRound = onPrepareRound
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onPrepareCompositeRound = onPrepareCompositeRound
        self.onSaveBackendConfiguration = onSaveBackendConfiguration
        self.onClearBackendConfiguration = onClearBackendConfiguration
        self.onConnectGarmin = onConnectGarmin
        self.onLoadCourseTees = onLoadCourseTees
        self.onSearchCourses = onSearchCourses
        self.onNearbyCourses = onNearbyCourses
        // An explicit caller selection may be retained, but history alone is not a course picker.
        // Normal new-round entry waits for Garmin's nearby catalogue, matching S70 behaviour.
        let resolvedCourseId = defaultCourseGlobalId.map(String.init) ?? ""
        let selected = (courseOptions + downloadedCourseOptions).first {
            String($0.globalId) == resolvedCourseId
        }
        self._courseGlobalIdText = State(initialValue: resolvedCourseId)
        self._roundId = State(initialValue: selected?.suggestedLiveRoundId ?? defaultRoundId)
        // Default to the course's real tee (prefer Blue/White), else the given/played tee.
        let courseTees = selected?.tees ?? []
        let resolvedTee = courseTees.first(where: { ["blue", "white"].contains($0.lowercased()) })
            ?? courseTees.first
            ?? selected?.teeBox.flatMap { $0 == "unknown" ? nil : $0 }
            ?? (defaultTeeBox == "unknown" ? "" : defaultTeeBox)
        self._teeBox = State(initialValue: resolvedTee)
        // The chosen segment (a 9-hole loop, or a whole 18) IS the unit now → no front/back slice.
        self._nine = State(initialValue: "all")
    }

    private var courseGlobalId: Int? {
        Int(courseGlobalIdText.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private var canStart: Bool {
        !isPreparing
            && !roundId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && courseGlobalId != nil
            && (!selectedCourseRequiresRemoteTees || (!isLoadingTees && !fetchedTees.isEmpty))
    }

    public var body: some View {
        GeometryReader { viewport in
            ScrollView {
                VStack(spacing: 0) {
                    VStack(spacing: 12) {
                        courseCard
                        secondNineCard
                    }
                    Spacer(minLength: 12)
                    startCard
                }
                // Keep the primary action in the approved lower action band when a real course
                // exposes only one playable 18-hole segment. Longer 9-hole combinations still
                // expand and scroll naturally instead of being compressed to the viewport.
                .frame(minHeight: max(0, viewport.size.height - 112), alignment: .top)
                .padding(.horizontal, 14)
                .padding(.top, 14)
                .padding(.bottom, 98)
            }
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("开始一场")
        .onAppear {
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onDisappear { locationProvider.stopUpdatingLocation() }
        .task(id: locationDiscoveryKey) { await discoverNearbyCourses() }
        // 选了/换了球场 → 拉该球场的可选发球台(颜色 + 码数 + 默认),填充选台器。
        .task(id: courseGlobalIdText) {
            await loadTees()
        }
        .sheet(isPresented: $showingCourseSearch) {
            NavigationStack {
                MobileCourseSearchView(
                    locationProvider: locationProvider,
                    installedGlobalIds: Set(downloadedCourseOptions.map(\.globalId)),
                    onSearch: { query in
                        let coordinate = locationProvider.latestFix?.coordinate
                        return try await onSearchCourses(
                            query,
                            coordinate?.latitude,
                            coordinate?.longitude
                        )
                    },
                    onNearby: onNearbyCourses,
                    onSelect: selectSearchResult
                )
            }
        }
    }

    /// Fetch the selected course's tee boxes (colour + yardage + default). Empty → keep the bundled
    /// tee colours. When the current pick isn't offered by this course, jump to the course default.
    private func loadTees() async {
        guard let globalId = courseGlobalId else { return }
        let requiresRemoteTees = selectedCourseRequiresRemoteTees
        if requiresRemoteTees {
            isLoadingTees = true
            teeLoadFailed = false
            fetchedTees = []
        }
        defer {
            if requiresRemoteTees { isLoadingTees = false }
        }
        let tees = await onLoadCourseTees(globalId)
        guard courseGlobalId == globalId else { return }
        guard !tees.isEmpty else {
            if requiresRemoteTees { teeLoadFailed = true }
            return
        }
        fetchedTees = tees
        if !tees.contains(where: { $0.teeBox.lowercased() == teeBox.lowercased() }),
           let fallback = tees.first(where: { $0.isDefault })?.teeBox ?? tees.first?.teeBox {
            teeBox = fallback
        }
    }

    /// The venue of the currently selected segment — the single source of truth (no separate state
    /// that can desync from courseGlobalIdText). Falls back to the top venue when nothing is selected.
    private var selectedVenueName: String {
        selectedSegment.map { $0.venueName ?? baseCourseName($0.name) } ?? displayVenues.first?.venue ?? ""
    }

    private var selectedVenueBinding: Binding<String> {
        Binding(
            get: { selectedVenueName },
            set: { newVenue in selectVenue(newVenue, userInitiated: true) }
        )
    }

    /// Select a venue → switch the chosen segment to that venue's first segment (keeps venue +
    /// segment list + 加打 + tee all consistent).
    private func selectVenue(_ venue: String, userInitiated: Bool) {
        guard let group = displayVenues.first(where: { $0.venue == venue }) ?? displayVenues.first,
              let first = group.segments.first else {
            return
        }
        if userInitiated {
            userPickedVenue = true
        }
        courseGlobalIdText = String(first.globalId)
        backGlobalIdText = ""
        fetchedTees = []
        teeLoadFailed = false
        applySelectedCourse(globalIdText: courseGlobalIdText)
    }

    /// S70 only auto-selects when GPS finds one nearby venue. With more than one, the player chooses
    /// from the nearby list; history never silently becomes the default course.
    private func ensureDefaultSelection() {
        guard displayVenues.count == 1, let top = displayVenues.first else { return }
        let currentIsValid = selectedSegment != nil
        if !currentIsValid {
            selectVenue(top.venue, userInitiated: false)
        } else if !userPickedVenue, !top.segments.contains(where: { String($0.globalId) == courseGlobalIdText }) {
            selectVenue(top.venue, userInitiated: false)
        }
    }

    /// Venues ordered nearest-first from the provider-wide GPS result.
    private var displayVenues: [(venue: String, segments: [MobileCourseOption])] {
        let groups = venueGroups
        guard let fix = locationProvider.latestFix else {
            return groups
        }
        func distance(_ group: (venue: String, segments: [MobileCourseOption])) -> Double {
            group.segments.compactMap { segment -> Double? in
                guard let lat = segment.latitude, let lon = segment.longitude else { return nil }
                return Self.haversineMetres(fix.coordinate.latitude, fix.coordinate.longitude, lat, lon)
            }.min() ?? .greatestFiniteMagnitude
        }
        return groups.sorted { distance($0) < distance($1) }
    }

    static func haversineMetres(_ lat1: Double, _ lon1: Double, _ lat2: Double, _ lon2: Double) -> Double {
        let r = 6_371_000.0
        let dLat = (lat2 - lat1) * .pi / 180
        let dLon = (lon2 - lon1) * .pi / 180
        let a = sin(dLat / 2) * sin(dLat / 2)
            + cos(lat1 * .pi / 180) * cos(lat2 * .pi / 180) * sin(dLon / 2) * sin(dLon / 2)
        let boundedA = min(max(a, 0), 1)
        return r * 2 * atan2(sqrt(boundedA), sqrt(1 - boundedA))
    }

    /// A downloaded course is an offline fallback only when its retained provider coordinate proves
    /// that it is actually near the current fix. `courseOptions` also contains play history, so rows
    /// without coordinates or outside the radius must never reappear as a disguised history list.
    static func locallyAvailableNearbyCourses(
        _ options: [MobileCourseOption],
        latitude: Double,
        longitude: Double,
        radiusKm: Int
    ) -> [MobileCourseOption] {
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              radiusKm > 0 else { return [] }
        let radiusMetres = Double(radiusKm) * 1_000
        var seen = Set<Int>()
        return options.filter { option in
            guard seen.insert(option.globalId).inserted,
                  let courseLatitude = option.latitude,
                  let courseLongitude = option.longitude,
                  courseLatitude.isFinite, (-90...90).contains(courseLatitude),
                  courseLongitude.isFinite, (-180...180).contains(courseLongitude) else {
                return false
            }
            return haversineMetres(
                latitude,
                longitude,
                courseLatitude,
                courseLongitude
            ) <= radiusMetres
        }
    }

    /// 按真实结构选场:每个球场列出它的各 9 洞环(黑骑士 A/B/C)或整场(北湖 18);选一个开始。
    @ViewBuilder private var courseCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("附近球场").font(.caption).foregroundStyle(.secondary)
            if displayVenues.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    if isLoadingNearby {
                        HStack(spacing: 8) {
                            ProgressView()
                            Text("正在定位并查找附近球场…")
                        }
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    } else {
                        Label(
                            effectiveNearbyStatusText,
                            systemImage: "location"
                        )
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    }
                }
            } else {
                Label("当前位置 50 km · 最近在前", systemImage: "location.fill")
                    .font(.caption2).foregroundStyle(LiveHoleStyle.green)
                if let nearbyStatusText {
                    Text(nearbyStatusText)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                // Only provider-nearby venues (plus one explicit text-search selection) appear here.
                Picker("球场", selection: selectedVenueBinding) {
                    ForEach(displayVenues, id: \.venue) { group in
                        Text(group.venue).tag(group.venue)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                // 选中球场的各 9 洞环 / 整场。
                if let group = displayVenues.first(where: { $0.venue == selectedVenueName }) ?? displayVenues.first {
                    ForEach(group.segments) { segment in
                        segmentRow(segment)
                    }
                }
                Text(segmentSelectionHelp)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if selectedSegment != nil {
                    Divider().padding(.vertical, 2)
                    HStack(spacing: 8) {
                        Text("发球台").font(.subheadline).foregroundStyle(.secondary)
                        Spacer()
                        Menu {
                            ForEach(teeOptions, id: \.self) { tee in
                                Button {
                                    teeBox = tee
                                } label: {
                                    if tee.caseInsensitiveCompare(teeBox) == .orderedSame {
                                        Label(teeMenuLabel(tee), systemImage: "checkmark")
                                    } else {
                                        Text(teeMenuLabel(tee))
                                    }
                                }
                            }
                            Divider()
                            Button("取消", role: .cancel) {}
                        } label: {
                            HStack(spacing: 4) {
                                Text(teeBox.isEmpty ? "默认" : teeMenuLabel(teeBox))
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(LiveHoleStyle.green)
                                Image(systemName: "chevron.up.chevron.down").font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        .disabled(teeOptions.isEmpty)
                    }
                }
                if selectedCourseRequiresRemoteTees, isLoadingTees {
                    ProgressView("正在获取发球台…")
                        .font(.caption)
                } else if selectedCourseRequiresRemoteTees, teeLoadFailed {
                    Text("这个球场暂时没有可用的发球台数据，请联网后重试。")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }

            Divider().padding(.vertical, 1)
            Button {
                showingCourseSearch = true
            } label: {
                Label("按城市或球场名搜索", systemImage: "magnifyingglass")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(LiveHoleStyle.green)
            .accessibilityIdentifier("start-round-search-all-courses")
        }
        .liveCard()
    }

    /// 单个可打段(9 洞环 / 整场)的可选行;选中绿描边高亮。
    @ViewBuilder private func segmentRow(_ segment: MobileCourseOption) -> some View {
        let selected = String(segment.globalId) == courseGlobalIdText
        Button {
            userPickedVenue = true
            courseGlobalIdText = String(segment.globalId)
            backGlobalIdText = ""  // changing the front loop resets any "add second nine" choice
            fetchedTees = []
            teeLoadFailed = false
            applySelectedCourse(globalIdText: courseGlobalIdText)
        } label: {
            HStack(spacing: 10) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(selected ? LiveHoleStyle.green : .secondary)
                Text(segmentTitle(segment))
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .foregroundStyle(.primary)
                Spacer()
                Text(segmentHolesText(segment))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            // The transparent Spacer is most of a wide course row. Without an explicit shape,
            // tapping that centre area (including Voice Control/XCUITest's default tap point) can
            // miss the Button even though its accessibility frame advertises the full row.
            .contentShape(Rectangle())
            .background(selected ? LiveHoleStyle.green.opacity(0.10) : Color.clear)
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected ? LiveHoleStyle.green : LiveHoleStyle.line))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("start-round-course-segment-\(segment.globalId)")
        .accessibilityValue(selected ? "已选择" : "未选择")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func segmentTitle(_ segment: MobileCourseOption) -> String {
        if let label = segment.segmentLabel, !label.isEmpty {
            return "\(label) 场"
        }
        return "全场"
    }

    private func segmentHolesText(_ segment: MobileCourseOption) -> String {
        "\(segment.segmentHoles ?? segment.holes) 洞"
    }

    private var selectedSegment: MobileCourseOption? {
        availableCourseOptions.first { String($0.globalId) == courseGlobalIdText }
    }

    private var segmentSelectionHelp: String {
        guard let selectedSegment else {
            return "选择一个球场开始。"
        }
        let holes = selectedSegment.segmentHoles ?? selectedSegment.holes
        if holes == 9 {
            return "选一个 9 洞环开始；想打 18 洞可在下方加打另一个环。"
        }
        return "选择全场开始 \(holes) 洞球局。"
    }

    /// 选中的是 9 洞环、且同球场有 9 洞环可作第二环时,提供「加打凑 18」。
    /// 含已选环本身 —— 同一个 9 洞环打两轮(A+A/B+B/C+C)是真实打法,不排除。
    private var secondNineCandidates: [MobileCourseOption] {
        guard let selectedSegment, (selectedSegment.segmentHoles ?? selectedSegment.holes) == 9 else {
            return []
        }
        let venue = selectedSegment.venueName ?? baseCourseName(selectedSegment.name)
        return availableCourseOptions
            .filter { ($0.venueName ?? baseCourseName($0.name)) == venue
                && ($0.segmentHoles ?? $0.holes) == 9 }
            .sorted { segmentSortKey($0) < segmentSortKey($1) }
    }

    /// 加打另一个 9 洞凑 18(可选):列出同球场的各 9 洞环 + 「不加打」。
    @ViewBuilder private var secondNineCard: some View {
        if !secondNineCandidates.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("加打另一个 9 洞(可选,凑 18 洞)").font(.caption).foregroundStyle(.secondary)
                secondNineRow(title: "不加打 · 只打 9 洞", globalId: nil)
                ForEach(secondNineCandidates) { segment in
                    secondNineRow(title: "＋ \(segmentTitle(segment)) · 后九", globalId: segment.globalId)
                }
            }
            .liveCard()
        }
    }

    @ViewBuilder private func secondNineRow(title: String, globalId: Int?) -> some View {
        let value = globalId.map(String.init) ?? ""
        let selected = backGlobalIdText == value
        Button {
            backGlobalIdText = value
        } label: {
            HStack(spacing: 10) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(selected ? LiveHoleStyle.green : .secondary)
                Text(title)
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .foregroundStyle(.primary)
                Spacer()
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(selected ? LiveHoleStyle.green.opacity(0.10) : Color.clear)
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected ? LiveHoleStyle.green : LiveHoleStyle.line))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }

    /// 发球台候选:优先用 /courses/{id}/tees 接口返回的台(带码数,back→forward 排序);没有则回退
    /// 所选球场 Garmin CourseView 的真实 Tee 名(金/黑/蓝/白/红…);再没有才回退通用集。
    /// 内部保留原始 key(传给后端),仅显示中文。
    private var teeOptions: [String] {
        let fetched = fetchedTees.map(\.teeBox)
        let courseTees = selectedSegment?.tees ?? []
        if selectedCourseRequiresRemoteTees, fetched.isEmpty { return [] }
        let base = !fetched.isEmpty
            ? fetched
            : (courseTees.isEmpty ? ["blue", "white", "red", "gold", "black", "green", "yellow", "silver"] : courseTees)
        var seen = Set<String>()
        var result: [String] = []
        for tee in base {
            let trimmed = tee.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, seen.insert(trimmed.lowercased()).inserted else { continue }
            result.append(trimmed)
        }
        // 保证当前所选台一定可选,即使它不在解析出的列表里。
        let currentTrimmed = teeBox.trimmingCharacters(in: .whitespaces)
        if !currentTrimmed.isEmpty, seen.insert(currentTrimmed.lowercased()).inserted {
            result.append(currentTrimmed)
        }
        return result
    }

    /// 该台的总码数(来自接口),没有则 nil。
    private func teeYards(_ tee: String) -> Int? {
        fetchedTees.first { $0.teeBox.lowercased() == tee.lowercased() }?.yards
    }

    /// 选台菜单标签:中文台名 + 已知则附总码数,如「蓝 T · 6412 码」。
    private func teeMenuLabel(_ tee: String) -> String {
        if let yards = teeYards(tee) {
            return "\(zhTeeLabel(tee)) · \(yards) 码"
        }
        return zhTeeLabel(tee)
    }

    private func zhTeeLabel(_ tee: String) -> String {
        switch tee.lowercased() {
        case "blue":
            return "蓝 T"
        case "white":
            return "白 T"
        case "red":
            return "红 T"
        case "gold":
            return "金 T"
        case "black", "championship", "tips":
            return "黑 T(锦标)"
        case "green":
            return "绿 T"
        case "yellow":
            return "黄 T"
        case "silver":
            return "银 T"
        default:
            return tee
        }
    }

    private var startCard: some View {
        VStack(spacing: 8) {
            Button {
                if let courseGlobalId {
                    if let backGlobalId = Int(backGlobalIdText), backGlobalId != 0 {
                        onPrepareCompositeRound(courseGlobalId, backGlobalId, teeBox, roundId)
                    } else {
                        onPrepareCourseRound(courseGlobalId, roundId, teeBox, nine)
                    }
                    // Don't pop manually — once the round is prepared the Hub navigates straight
                    // into the live hole (pendingLiveHole → path), so 开始记分 enters the round.
                }
            } label: {
                Label("开始记分", systemImage: "flag.checkered")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(canStart ? LiveHoleStyle.green : Color.gray.opacity(0.4))
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(!canStart)
            .accessibilityIdentifier("start-round-primary-action")
            if isPreparing {
                ProgressView("准备中…").font(.caption)
            }
        }
    }

    /// Group the provider-ranked nearby rows by venue without re-sorting them by historical play count.
    private var venueGroups: [(venue: String, segments: [MobileCourseOption])] {
        var groups: [(venue: String, segments: [MobileCourseOption])] = []
        for option in availableCourseOptions {
            let venue = option.venueName ?? baseCourseName(option.name)
            if let index = groups.firstIndex(where: { $0.venue == venue }) {
                groups[index].segments.append(option)
            } else {
                groups.append((venue: venue, segments: [option]))
            }
        }
        for index in groups.indices {
            groups[index].segments.sort { segmentSortKey($0) < segmentSortKey($1) }
        }
        return groups
    }

    private func segmentSortKey(_ segment: MobileCourseOption) -> String {
        // Labelled loops first (A < B < C), a single whole course (nil label) last.
        segment.segmentLabel ?? "~~"
    }

    private func baseCourseName(_ name: String) -> String {
        name.components(separatedBy: " ~ ").first?.trimmingCharacters(in: .whitespaces) ?? name
    }

    private func applySelectedCourse(globalIdText: String) {
        guard let globalId = Int(globalIdText),
              let option = courseLookupOptions.first(where: { $0.globalId == globalId }) else {
            return
        }
        // P1-3: a fixed "live-<globalId>" fallback is reused across rounds on the same course, so two
        // real rounds merge locally and post to the same backend round. Seed a unique id per round.
        roundId = option.suggestedLiveRoundId ?? "live-\(option.globalId)-\(UUID().uuidString)"
        if let optionTeeBox = option.teeBox, optionTeeBox != "unknown" {
            teeBox = optionTeeBox
        }
        // Default to a sensible real tee for the chosen course (Blue/White, else the first).
        let tees = option.tees ?? []
        if !tees.isEmpty, !tees.contains(where: { $0.lowercased() == teeBox.lowercased() }) {
            teeBox = tees.first(where: { ["blue", "white"].contains($0.lowercased()) }) ?? tees.first ?? teeBox
        }
    }

    private var availableCourseOptions: [MobileCourseOption] {
        var seen = Set<Int>()
        return (nearbyCourseOptions + remoteCourseOptions).filter { seen.insert($0.globalId).inserted }
    }

    private var courseLookupOptions: [MobileCourseOption] {
        var seen = Set<Int>()
        return (availableCourseOptions + courseOptions + downloadedCourseOptions)
            .filter { seen.insert($0.globalId).inserted }
    }

    private var selectedCourseRequiresRemoteTees: Bool {
        guard let courseGlobalId else { return false }
        return !courseOptions.contains { $0.globalId == courseGlobalId }
            && !downloadedCourseOptions.contains { $0.globalId == courseGlobalId }
    }

    private func selectSearchResult(
        _ selected: MobileCourseSearchMatch,
        _ matches: [MobileCourseSearchMatch]
    ) {
        _ = matches
        let isSameCourse = courseGlobalId == selected.globalId
        guard let option = resolvedOption(for: selected) else { return }
        remoteCourseOptions = [option]
        userPickedVenue = true
        courseGlobalIdText = String(selected.globalId)
        backGlobalIdText = ""
        // Re-selecting the same search result (for example nearby first, then name search) keeps
        // its already-fetched Tee authority. Clearing it would not retrigger `.task(id:)` because
        // the globalId is unchanged, leaving the primary action disabled forever.
        if !isSameCourse {
            fetchedTees = []
            teeBox = ""
            teeLoadFailed = false
        }
        applySelectedCourse(globalIdText: courseGlobalIdText)
    }

    private var locationDiscoveryKey: String {
        guard let coordinate = locationProvider.latestFix?.coordinate else {
            return "waiting:\(locationProvider.authorizationStatus.rawValue)"
        }
        return "\(Int((coordinate.latitude * 10_000).rounded())):\(Int((coordinate.longitude * 10_000).rounded()))"
    }

    /// Permission denial is a synchronous product state, not a network result. Derive its copy
    /// directly from the provider so the player never sees a transient "waiting for GPS" message
    /// while Core Location has already denied/restricted access. The async discovery task still
    /// owns empty-result and transport-error copy for authorized fixes.
    private var effectiveNearbyStatusText: String {
        if locationProvider.authorizationStatus == .denied
            || locationProvider.authorizationStatus == .restricted {
            return "定位权限未开启；可以直接按城市或球场名搜索。"
        }
        return nearbyStatusText ?? "等待 GPS 定位；也可以直接按城市或球场名搜索。"
    }

    @MainActor
    private func discoverNearbyCourses() async {
        guard let fix = locationProvider.latestFix else {
            nearbyCourseOptions = []
            isLoadingNearby = locationProvider.authorizationStatus == .notDetermined
                || locationProvider.authorizationStatus == .authorizedAlways
                || locationProvider.authorizationStatus == .authorizedWhenInUse
            nearbyStatusText = locationProvider.authorizationStatus == .denied
                || locationProvider.authorizationStatus == .restricted
                ? "定位权限未开启；可以直接按城市或球场名搜索。"
                : nil
            return
        }
        let localNearby = Self.locallyAvailableNearbyCourses(
            downloadedCourseOptions,
            latitude: fix.coordinate.latitude,
            longitude: fix.coordinate.longitude,
            radiusKm: 50
        )
        // Publish the factual local candidates immediately, but do not auto-select the only local
        // venue yet: the provider response may add a second nearby venue, which must restore the
        // explicit-choice rule. The player may still tap a local row while the request is pending.
        nearbyCourseOptions = localNearby
        isLoadingNearby = true
        nearbyStatusText = nil
        defer { isLoadingNearby = false }
        do {
            let matches = try await onNearbyCourses(
                fix.coordinate.latitude,
                fix.coordinate.longitude,
                50
            )
            var seen = Set<Int>()
            let providerNearby = matches.compactMap { resolvedOption(for: $0) }
            nearbyCourseOptions = (providerNearby + localNearby).filter {
                seen.insert($0.globalId).inserted
            }
            nearbyStatusText = nearbyCourseOptions.isEmpty
                ? "当前位置 50 km 内没有找到球场；可以扩大范围或按名称搜索。"
                : nil
            if !userPickedVenue {
                if displayVenues.count == 1 {
                    ensureDefaultSelection()
                } else if selectedSegment == nil || !nearbyCourseOptions.contains(where: {
                    String($0.globalId) == courseGlobalIdText
                }) {
                    courseGlobalIdText = ""
                    teeBox = ""
                    fetchedTees = []
                }
            }
        } catch {
            nearbyCourseOptions = localNearby
            nearbyStatusText = localNearby.isEmpty
                ? "附近球场暂时读取失败；可以先按城市或球场名搜索。"
                : "附近服务不可用；已显示下载到本机的附近球场。"
            if !userPickedVenue {
                ensureDefaultSelection()
            }
        }
    }

    private func resolvedOption(for match: MobileCourseSearchMatch) -> MobileCourseOption? {
        guard let provider = match.courseOption else { return nil }
        let knownOptions = courseOptions + downloadedCourseOptions
        guard let known = knownOptions.first(where: { $0.globalId == match.globalId }) else {
            return provider
        }
        // Catalogue coordinates remain authoritative for a nearby result, while an installed row
        // keeps the player's established display name and loop labels. Garmin can return an English
        // provider alias for the same globalId (for example Shadow Creek for the locally known
        // 北京丽宫); replacing the installed name made 开始一场 disagree with history, prep and the
        // downloaded package. Do not prefer the old row wholesale, because that can still discard
        // fresh catalogue coordinates and break nearest-first ordering.
        return MobileCourseOption(
            globalId: provider.globalId,
            courseKey: known.courseKey,
            name: known.name,
            roundCount: known.roundCount,
            latestRoundId: known.latestRoundId,
            latestRoundDate: known.latestRoundDate,
            templateRoundId: known.templateRoundId,
            suggestedLiveRoundId: known.suggestedLiveRoundId,
            holes: provider.holes,
            teeBox: known.teeBox,
            geometryCoverage: known.geometryCoverage,
            sourceRefs: known.sourceRefs,
            venueName: known.venueName ?? provider.venueName,
            segmentLabel: known.segmentLabel ?? provider.segmentLabel,
            segmentHoles: known.segmentHoles ?? provider.segmentHoles,
            latitude: provider.latitude ?? known.latitude,
            longitude: provider.longitude ?? known.longitude,
            tees: known.tees
        )
    }
}
