import SwiftUI
import AICaddieDomain

/// 开始一场(README §8, `pre-round.html` 第 2 屏)— 一个球场列表(附近在前带距离，其后是搜索、
/// 最近、已下载，不分区、不写状态文字)；只选第一个 9 洞环(A / B / C 大块)；发球台是颜色圆点 +
/// 这个环的码数；按钮写明“从 B 场 开始 · 蓝 T”。第二个环在打完第一个环时选(NineLoopPlan)。
/// 附近只有一个球场时自动选中，多个时由玩家选择；GPS 不可用时搜索照常可用。
public struct StartRoundView: View {
    struct CourseSelectionState: Equatable {
        let globalIdText: String
        let roundId: String
        let teeBox: String
    }
    public let defaultRoundId: String
    public let courseOptions: [MobileCourseOption]
    public let downloadedCourseOptions: [MobileCourseOption]
    /// The last explicitly started Garmin course. It is shown separately when nearby omits it;
    /// this source never contributes to the nearby/GPS result set.
    public let recentCourseOption: MobileCourseOption?
    public let syncStatus: String
    public let isPreparing: Bool
    public let apiBaseURL: URL?
    public let adminTokenConfigured: Bool
    public let onPrepareRound: (String) -> Void
    public let onPrepareCourseRound: (Int, String, String, String) -> Void
    /// Kept for caller source compatibility only. 开始一场 prepares the first loop alone; the second
    /// loop is chosen at the turn (NineLoopPlan), which owns the composite preparation.
    public let onPrepareCompositeRound: (Int, Int, String, String) -> Void
    public let onSaveBackendConfiguration: (String, String?) -> Void
    public let onClearBackendConfiguration: () -> Void
    /// 还没有球场时的「连接 Garmin」CTA:由 app 注入(打开 Garmin 连接流程),拉取球场后就能记分。
    public let onConnectGarmin: () -> Void
    /// 拉取所选球场的可选发球台(GET /courses/{id}/tees:颜色 + 总码数 + 默认台)。
    /// 离线/出错返回 []：已安装球场可保留包内 Tee；全库新球场必须重试真实 Tee authority。
    public let onLoadCourseTees: (Int) async -> [CourseTee]
    /// Garmin 全库名称搜索。只返回轻量 metadata；选中后仍走本页已有的单球场准备链。
    public let onSearchCourses: (String, String?, Double?, Double?) async throws -> [MobileCourseSearchMatch]
    /// Garmin 全库坐标发现。半径内完整分页，只返回轻量 metadata。
    public let onNearbyCourses: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]

    @StateObject private var locationProvider = LocationProvider()
    @State private var roundId: String
    @State private var courseGlobalIdText: String
    @State private var userPickedVenue = false
    /// A text-search result is an explicit course choice even when Garmin is still loading its
    /// Tee authority.  Keep that provenance separate from the nearby picker so a cold/no-GPS
    /// search can start the round immediately without weakening the nearby loading gate.
    @State private var selectedCourseWasManualSearch = false
    @State private var teeBox: String
    @State private var nine: String
    /// 所选球场的发球台列表(含码数/默认),来自 GET /courses/{id}/tees;为空则用球场自带 Tee 名。
    @State private var fetchedTees: [CourseTee] = []
    @State private var nearbyCourseOptions: [MobileCourseOption] = []
    @State private var remoteCourseOptions: [MobileCourseOption] = []
    /// Downloaded packages are an explicit offline source. They must never be mixed into the
    /// provider-nearby list: a stale local package is not evidence that the course is nearby.
    @State private var offlineCourseOptions: [MobileCourseOption] = []
    @State private var showingCourseSearch = false
    @State private var isLoadingTees = false
    @State private var teeLoadFailed = false
    @State private var isLoadingNearby = false
    @State private var nearbyStatusText: String?
    @State private var nearbyDiscoveryFailed = false
    @State private var nearbyRetryToken = 0
    @State private var teeRequestToken: UUID?
    @State private var nearbyRequestToken: UUID?

    public init(
        // 不在消费者界面里写死可读的原始局号(如 900001):没显式传时生成一个不透明的本地局号,
        // 真正开始记分时局号由所选球场派生(applySelectedCourse),后端据此建局。
        defaultRoundId: String = "live-\(UUID().uuidString)",
        defaultCourseGlobalId: Int? = nil,
        defaultTeeBox: String = "unknown",
        courseOptions: [MobileCourseOption] = [],
        downloadedCourseOptions: [MobileCourseOption] = [],
        recentCourseOption: MobileCourseOption? = nil,
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
        onSearchCourses: @escaping (String, String?, Double?, Double?) async throws -> [MobileCourseSearchMatch] = { _, _, _, _ in [] },
        onNearbyCourses: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch] = { _, _, _ in [] }
    ) {
        self.defaultRoundId = defaultRoundId
        self.courseOptions = courseOptions
        self.downloadedCourseOptions = downloadedCourseOptions
        self.recentCourseOption = recentCourseOption
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
        // A caller-provided course is an explicit choice (for example a resumed deep link). History
        // supplied only through `courseOptions` must not become an implicit nearby selection.
        self._userPickedVenue = State(initialValue: defaultCourseGlobalId != nil)
        // The home "开始" preselects the recent course, which may be in neither list.
        let selected = (courseOptions + downloadedCourseOptions + (recentCourseOption.map { [$0] } ?? [])).first {
            String($0.globalId) == resolvedCourseId
        }
        self._courseGlobalIdText = State(initialValue: resolvedCourseId)
        // `suggestedLiveRoundId` describes a reusable course/home package, not a golf-round
        // identity.  Every explicit Start must own a fresh id even when this is the same course the
        // player just finished; otherwise its old progress/events can be restored into the new round.
        self._roundId = State(initialValue: selected.map {
            Self.freshLiveRoundId(globalId: $0.globalId)
        } ?? defaultRoundId)
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
        Self.isStartAllowed(
            isPreparing: isPreparing,
            isLoadingTees: isLoadingTees,
            roundId: roundId,
            courseGlobalId: courseGlobalId,
            teeBox: teeBox,
            selectedCourseRequiresRemoteTees: selectedCourseRequiresRemoteTees,
            teeOptions: teeOptions,
            selectedCourseWasManualSearch: selectedCourseWasManualSearch
        )
    }

    /// The primary action is independent of GPS. A manually searched course has explicit player
    /// intent and may enter the map with the server's `unknown` Tee while Tee authority continues in
    /// the background; nearby discovery keeps the stricter loading gate.
    static func isStartAllowed(
        isPreparing: Bool,
        isLoadingTees: Bool,
        roundId: String,
        courseGlobalId: Int?,
        teeBox: String,
        selectedCourseRequiresRemoteTees: Bool,
        teeOptions: [String],
        selectedCourseWasManualSearch: Bool
    ) -> Bool {
        let hasManualSearchFallback = selectedCourseWasManualSearch
            && !teeBox.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return !isPreparing
            && (hasManualSearchFallback || !isLoadingTees)
            && !roundId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && courseGlobalId != nil
            && !teeBox.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (!selectedCourseRequiresRemoteTees || !teeOptions.isEmpty || hasManualSearchFallback)
    }

    private static let surface = Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255)

    /// `pre-round.html` screen 2: one course list, the first nine-hole loop as big tiles, tee dots,
    /// and one primary action that names the choice. No location / download status prose.
    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                searchEntry
                courseList
                if selectedSegment != nil {
                    loopSection
                    teeSection
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 24)
        }
        // The primary action stays in the lower action band while the list scrolls.
        .safeAreaInset(edge: .bottom, spacing: 0) {
            startCard
                .padding(.horizontal, 16)
                .padding(.top, 10)
                .padding(.bottom, 8)
                .background(Self.surface)
        }
        .background(Self.surface)
        .navigationTitle("开始一场")
        .onAppear {
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onDisappear { locationProvider.stopUpdatingLocation() }
        .task(id: nearbyDiscoveryTaskKey) { await discoverNearbyCourses() }
        // 选了/换了球场 → 拉该球场的可选发球台(颜色 + 码数 + 默认),填充选台器。
        .task(id: courseGlobalIdText) {
            await loadTees()
        }
        .sheet(isPresented: $showingCourseSearch) {
            NavigationStack {
                MobileCourseSearchView(
                    locationProvider: locationProvider,
                    // The parent owns the sheet binding. Selection must commit the course and tee
                    // provenance here before the sheet closes; a child NavigationStack dismiss can
                    // otherwise race SwiftUI's state transaction and lose the selected row.
                    dismissAfterSelection: false,
                    installedGlobalIds: Set(downloadedCourseOptions.map(\.globalId)),
                    knownCourseOptions: courseOptions + downloadedCourseOptions,
                    onSearch: { query, city in
                        let coordinate = locationProvider.latestFix?.coordinate
                        return try await onSearchCourses(
                            query,
                            city,
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
        let requestToken = UUID()
        teeRequestToken = requestToken
        guard let globalId = courseGlobalId else {
            isLoadingTees = false
            teeLoadFailed = false
            return
        }
        let requiresRemoteTees = selectedCourseRequiresRemoteTees
        let hasCatalogueTeeAuthority = selectedSegment?.tees?.isEmpty == false
        // A recent row was produced from a successfully activated package and already carries
        // the accepted Tee authority. Do not make the recovery action wait behind a second Tee
        // request; still fetch the course's full tee list (colours + yards) in the background so
        // the player can change tee on the recent course.
        let recentHasTeeAuthority = recentResolvedCourseOption?.globalId == globalId
            && recentResolvedCourseOption?.tees?.isEmpty == false
        fetchedTees = []
        teeLoadFailed = false
        // A cached/history course may already have factual Tee names, but this request still
        // enriches them with Garmin yardage/default authority. Do not let Start race that request:
        // URLSession can otherwise queue the course-package behind a cold CourseView release and
        // silently hit its 60 s timeout. A failed refresh still falls back to the known Tee list.
        isLoadingTees = !recentHasTeeAuthority
        defer {
            if teeRequestToken == requestToken {
                isLoadingTees = false
            }
        }
        let tees = await onLoadCourseTees(globalId)
        guard !Task.isCancelled,
              teeRequestToken == requestToken,
              courseGlobalId == globalId else { return }
        guard !tees.isEmpty else {
            if requiresRemoteTees && !hasCatalogueTeeAuthority && !recentHasTeeAuthority { teeLoadFailed = true }
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
        selectedSegment.map(\.venueDisplayName)
            ?? courseRows.first?.venue
            ?? ""
    }

    static func roundDisplayName(
        front: MobileCourseOption,
        back: MobileCourseOption?
    ) -> String {
        // The active round keeps its selected loop(s) in the structured `nine`
        // fields. Its visible course title is always the physical venue so it
        // matches search, Watch and Web.
        _ = back
        return courseVenueName(front)
    }

    /// Select a venue → switch the chosen segment to that venue's first segment (keeps venue +
    /// loop tiles + tee all consistent).
    private func selectVenue(_ venue: String, userInitiated: Bool) {
        guard let group = displayVenues.first(where: { $0.venue == venue }) ?? displayVenues.first,
              let first = group.segments.first else {
            return
        }
        let retainsManualSearch = selectedCourseWasManualSearch
            && selectedSegment.map { Self.samePhysicalVenue($0, first) } == true
        if userInitiated {
            userPickedVenue = true
        }
        // A manual search remains an explicit start authority while the player switches among
        // loops in that same physical venue. Crossing to another venue returns to the normal Tee
        // loading gate, even when SwiftUI invokes this setter during catalogue refresh.
        selectedCourseWasManualSearch = retainsManualSearch
        fetchedTees = []
        teeLoadFailed = false
        applySelectedCourse(first)
    }

    /// S70 only auto-selects when GPS finds one nearby venue. With more than one, the player chooses
    /// from the nearby list; history never silently becomes the default course.
    private func ensureDefaultSelection() {
        guard nearbyVenues.count == 1, let top = nearbyVenues.first else { return }
        let currentIsValid = selectedSegment != nil
        if !currentIsValid {
            selectVenue(top.venue, userInitiated: false)
        } else if !userPickedVenue, !top.segments.contains(where: { String($0.globalId) == courseGlobalIdText }) {
            selectVenue(top.venue, userInitiated: false)
        }
    }

    /// Provider nearby/search venues. Offline packages are deliberately excluded: they are listed
    /// after the provider rows and must never count as nearby evidence (auto-selection).
    private var displayVenues: [(venue: String, segments: [MobileCourseOption])] {
        orderedVenues(makeVenueGroups(from: nearbyCourseOptions + remoteCourseOptions))
    }

    private var nearbyVenues: [(venue: String, segments: [MobileCourseOption])] {
        orderedVenues(makeVenueGroups(from: nearbyCourseOptions))
    }

    /// A cancelled/restarted GPS task can clear the async `offlineCourseOptions` assignment after
    /// the nearby request has already reported an error. Keep the explicitly labelled local section
    /// recoverable from the source-of-truth download list while the error state is visible. Provider
    /// rows remain separate, and factual coordinates still use the normal 50 km rule.
    private var offlineDisplayOptions: [MobileCourseOption] {
        guard nearbyDiscoveryFailed else { return offlineCourseOptions }
        let fallback: [MobileCourseOption]
        if let fix = locationProvider.latestFix {
            fallback = Self.locallyAvailableNearbyCourses(
                downloadedCourseOptions,
                latitude: fix.coordinate.latitude,
                longitude: fix.coordinate.longitude,
                radiusKm: 50,
                includeUnknownCoordinates: true
            )
        } else {
            fallback = downloadedCourseOptions
        }
        return resolvedOfflineOptions(offlineCourseOptions + fallback)
    }

    /// Order provider rows by distance only when a real fix exists. Search rows without a fix keep
    /// their provider order, and offline rows never use a distance claim.
    private func orderedVenues(
        _ groups: [(venue: String, segments: [MobileCourseOption])]
    ) -> [(venue: String, segments: [MobileCourseOption])] {
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
    /// The recovery-only `includeUnknownCoordinates` exception is safe because the caller lists
    /// those rows after the provider rows as downloaded courses, never as nearby/provider evidence.
    static func locallyAvailableNearbyCourses(
        _ options: [MobileCourseOption],
        latitude: Double,
        longitude: Double,
        radiusKm: Int,
        includeUnknownCoordinates: Bool = false
    ) -> [MobileCourseOption] {
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              radiusKm > 0 else { return [] }
        let radiusMetres = Double(radiusKm) * 1_000
        var seen = Set<Int>()
        return options.filter { option in
            guard seen.insert(option.globalId).inserted else {
                return false
            }
            guard let courseLatitude = option.latitude,
                  let courseLongitude = option.longitude else {
                // A complete downloaded package is still an explicit offline source even when an
                // older CourseView package did not carry a Tee anchor. It is listed as a downloaded
                // row (no distance); this flag is only used after the provider request fails and
                // never promotes the row into nearby/provider evidence.
                return includeUnknownCoordinates
            }
            guard courseLatitude.isFinite, (-90...90).contains(courseLatitude),
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

    // MARK: - Course list (README §8: one list, nearby first)

    /// Compact search entry. A failed nearby request adds only a retry icon; the list simply shows
    /// the other sources (no error prose).
    private var searchEntry: some View {
        HStack(spacing: 10) {
            Button {
                showingCourseSearch = true
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                    Text("搜索球场或城市")
                    Spacer(minLength: 0)
                }
                .font(.body)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .frame(maxWidth: .infinity, minHeight: 42, alignment: .leading)
                .background(Color.black.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("start-round-search-all-courses")
            if nearbyDiscoveryFailed {
                Button {
                    nearbyRetryToken &+= 1
                } label: {
                    Image(systemName: "location.circle")
                        .font(.title3.weight(.semibold))
                        .frame(width: 42, height: 42)
                }
                .buttonStyle(.plain)
                .foregroundStyle(LiveHoleStyle.green)
                .accessibilityLabel(nearbyStatusText ?? "重试附近球场")
                .accessibilityIdentifier("start-round-retry-nearby")
            } else if isLoadingNearby, courseRows.isEmpty {
                ProgressView()
                    .controlSize(.small)
                    .frame(width: 42, height: 42)
            }
        }
    }

    /// Nearby (distance order when a fix exists), the explicit search pick, the recent course (and
    /// a preselected course that no list carries), then downloaded packages — one row per venue.
    private var courseRows: [StartCourseListRow] {
        let nearby: [MobileCourseOption]
        if let fix = locationProvider.latestFix {
            nearby = StartRoundPresentation.sortedByDistance(
                nearbyCourseOptions,
                latitude: fix.coordinate.latitude,
                longitude: fix.coordinate.longitude
            )
        } else {
            nearby = nearbyCourseOptions
        }
        // Every downloaded course stays in the downloaded tail (a travel course outside the GPS
        // radius included); nearby local ones keep their earlier position, duplicates of a
        // nearby / search / recent row collapse into that row. Distance is never shown for them.
        let downloaded = resolvedOfflineOptions(offlineDisplayOptions + downloadedCourseOptions)
        var recent = recentCourseFallbackOption.map { [$0] } ?? []
        // A preselected course (the home "开始") that no source lists still gets its row; a listed
        // one keeps its own position so selecting a row never moves it.
        if let selectedSegment,
           !(nearbyCourseOptions + remoteCourseOptions + recent + downloaded).contains(where: {
               Self.samePhysicalVenue($0, selectedSegment)
           }) {
            recent.append(selectedSegment)
        }
        return StartRoundPresentation.mergedCourseRows(
            nearby: nearby,
            search: remoteCourseOptions,
            recent: recent,
            downloaded: downloaded
        )
    }

    @ViewBuilder private var courseList: some View {
        let rows = courseRows
        if !rows.isEmpty {
            VStack(spacing: 0) {
                ForEach(rows) { row in
                    courseRow(row)
                    if row.id != rows.last?.id {
                        Divider().padding(.leading, 60)
                    }
                }
            }
            .padding(.vertical, 4)
            .background(Color.white)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("start-round-course-list")
            .accessibilityValue(selectedVenueName)
        }
    }

    /// One venue row: name + "1.2 公里 · 27 洞". Distance only for provider-nearby rows with a fix.
    private func courseRow(_ row: StartCourseListRow) -> some View {
        let selected: Bool
        if let segment = selectedSegment {
            let sameVenue = row.segments.first.map { Self.samePhysicalVenue(segment, $0) } ?? false
            selected = sameVenue || row.segments.contains { $0.globalId == segment.globalId }
        } else {
            selected = false
        }
        return Button {
            selectCourseRow(row)
        } label: {
            HStack(spacing: 12) {
                Image(systemName: "flag.fill")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(LiveHoleStyle.green)
                    .frame(width: 36, height: 36)
                    .background(HubStyle.iconTint)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.venue)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                    if let subtitle = courseRowSubtitle(row) {
                        Text(subtitle)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 8)
                if selected {
                    Image(systemName: "checkmark")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(LiveHoleStyle.green)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            // The transparent Spacer is most of a wide row. Without an explicit shape, tapping that
            // centre area (including XCUITest's default tap point) can miss the Button.
            .contentShape(Rectangle())
            .background(selected ? LiveHoleStyle.green.opacity(0.08) : Color.clear)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("start-round-venue-\(row.id)")
        .accessibilityValue(selected ? "已选择" : "未选择")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func courseRowSubtitle(_ row: StartCourseListRow) -> String? {
        var parts: [String] = []
        if row.source == .nearby, let fix = locationProvider.latestFix {
            let metres = row.segments.compactMap { segment -> Double? in
                guard let lat = segment.latitude, let lon = segment.longitude else { return nil }
                return Self.haversineMetres(fix.coordinate.latitude, fix.coordinate.longitude, lat, lon)
            }.min()
            if let metres, let distance = StartRoundPresentation.distanceText(metres: metres) {
                parts.append(distance)
            }
        }
        if row.holes > 0 {
            parts.append("\(row.holes) 洞")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// Choosing a venue selects its first loop; tapping the already-selected venue keeps the loop.
    private func selectCourseRow(_ row: StartCourseListRow) {
        guard let first = row.segments.first else { return }
        if let current = selectedSegment, Self.samePhysicalVenue(current, first) { return }
        userPickedVenue = true
        selectedCourseWasManualSearch = Self.preservesManualSearchProvenance(
            wasManualSearch: selectedCourseWasManualSearch,
            previous: selectedSegment,
            next: first
        )
        fetchedTees = []
        teeLoadFailed = false
        applySelectedCourse(first)
    }

    // MARK: - First loop (README §8: only the first nine is chosen here)

    /// The selected venue's loops from the authority that supplied the selection, in the course's
    /// order. An 18-hole single course is one tile and starts as today (nine "all").
    private var selectedVenueLoops: [MobileCourseOption] {
        guard let selectedSegment else { return [] }
        guard selectedSegment.resolvedHoles == 9 else { return [selectedSegment] }
        let loops = Self.sameVenueNineHoleCandidates(
            selected: selectedSegment,
            candidates: [selectedSegment] + selectedAuthorityOptions
        )
        return loops.isEmpty ? [selectedSegment] : loops
    }

    @ViewBuilder private var loopSection: some View {
        let loops = selectedVenueLoops
        VStack(alignment: .leading, spacing: 10) {
            Text(loops.contains(where: { $0.resolvedHoles == 9 }) ? "从哪个 9 洞开始" : "从第 1 洞开始")
                .font(.footnote.weight(.bold))
                .foregroundStyle(.secondary)
            LazyVGrid(
                columns: Array(
                    repeating: GridItem(.flexible(), spacing: 8),
                    count: max(1, min(3, loops.count))
                ),
                spacing: 8
            ) {
                ForEach(loops) { segment in
                    segmentRow(segment)
                }
            }
        }
    }

    /// One loop tile: "B 场" + "9 洞 · 3201 码" (yards only when this tee's are known), or "18 洞".
    @ViewBuilder private func segmentRow(_ segment: MobileCourseOption) -> some View {
        let selected = String(segment.globalId) == courseGlobalIdText
        Button {
            selectLoop(segment)
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                Spacer(minLength: 0)
                Text(StartRoundPresentation.loopTileTitle(segment))
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                if let subtitle = loopTileSubtitle(segment, selected: selected) {
                    Text(subtitle)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 84, alignment: .bottomLeading)
            .background(selected ? LiveHoleStyle.green.opacity(0.10) : Color.white)
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(selected ? LiveHoleStyle.green : LiveHoleStyle.line, lineWidth: selected ? 2 : 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("start-round-course-segment-\(segment.globalId)")
        .accessibilityValue(selected ? "已选择" : "未选择")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func loopTileSubtitle(_ segment: MobileCourseOption, selected: Bool) -> String? {
        var parts: [String] = []
        if segment.resolvedHoles == 9 {
            parts.append("9 洞")
        }
        if selected, let yards = teeYards(teeBox) {
            parts.append("\(yards) 码")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private func selectLoop(_ segment: MobileCourseOption) {
        guard String(segment.globalId) != courseGlobalIdText else { return }
        userPickedVenue = true
        selectedCourseWasManualSearch = Self.preservesManualSearchProvenance(
            wasManualSearch: selectedCourseWasManualSearch,
            previous: selectedSegment,
            next: segment
        )
        fetchedTees = []
        teeLoadFailed = false
        applySelectedCourse(segment)
    }

    private var selectedSegment: MobileCourseOption? {
        guard let globalId = courseGlobalId else { return nil }
        return availableCourseOptions.first { $0.globalId == globalId }
            ?? offlineResolvedCourseOptions.first { $0.globalId == globalId }
            ?? explicitCourseOptions.first { $0.globalId == globalId }
            ?? recentResolvedCourseOption.flatMap { $0.globalId == globalId ? $0 : nil }
    }

    // MARK: - Tees (README §8: colour dots + this loop's yards)

    @ViewBuilder private var teeSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("发球台")
                .font(.footnote.weight(.bold))
                .foregroundStyle(.secondary)
            if selectedCourseRequiresRemoteTees, teeLoadFailed, teeOptions.isEmpty {
                // Tee authority failed: the course default still starts; retry is an icon.
                HStack(spacing: 12) {
                    Button {
                        teeBox = "unknown"
                        teeLoadFailed = false
                    } label: {
                        teeChipLabel("unknown", selected: false)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("start-round-use-course-default-tee")
                    Button {
                        Task { await loadTees() }
                    } label: {
                        Label("重试获取发球台", systemImage: "arrow.clockwise")
                            .labelStyle(.iconOnly)
                            .font(.title3.weight(.semibold))
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(LiveHoleStyle.green)
                    .accessibilityIdentifier("start-round-retry-course-tees")
                }
            } else if teeOptions.isEmpty {
                ProgressView()
                    .controlSize(.small)
                    .frame(height: 44)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(teeOptions, id: \.self) { tee in
                            teeChip(tee)
                        }
                    }
                    .padding(.vertical, 4)
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("start-round-tee-selector")
                }
            }
        }
    }

    private func teeChip(_ tee: String) -> some View {
        let selected = tee.caseInsensitiveCompare(teeBox) == .orderedSame
        return Button {
            teeBox = tee
        } label: {
            teeChipLabel(tee, selected: selected)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(teeMenuLabel(tee))
        .accessibilityIdentifier("start-round-tee-\(tee)")
        .accessibilityValue(selected ? "已选择" : "未选择")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    /// A filled dot in the tee's colour (shared `TeeColor`), "蓝 T" and this loop's yards.
    private func teeChipLabel(_ tee: String, selected: Bool) -> some View {
        let color = TeeColor.forTee(tee)
        return VStack(spacing: 4) {
            Circle()
                .fill(Color(red: color.red, green: color.green, blue: color.blue))
                .frame(width: 30, height: 30)
                .overlay(
                    Circle().stroke(Color.black.opacity(color.isLight ? 0.25 : 0.08), lineWidth: 1)
                )
                .padding(4)
                .overlay(
                    Circle().stroke(selected ? LiveHoleStyle.green : Color.clear, lineWidth: 2.5)
                )
            Text(zhTeeLabel(tee))
                .font(.caption.weight(.bold))
                .foregroundStyle(.primary)
                .lineLimit(1)
            if let yards = teeYards(tee) {
                Text("\(yards) 码")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .frame(minWidth: 64)
        .contentShape(Rectangle())
    }

    /// 发球台候选:优先用 /courses/{id}/tees 接口返回的台(带码数,back→forward 排序);没有则回退
    /// 所选球场 Garmin CourseView 的真实 Tee 名(金/黑/蓝/白/红…);再没有才回退通用集。
    /// 内部保留原始 key(传给后端),仅显示中文。
    private var teeOptions: [String] {
        let fetched = fetchedTees.map(\.teeBox)
        let courseTees = selectedSegment?.tees ?? []
        if !fetched.isEmpty {
            return Self.normalizedTeeOptions(fetched, currentTeeBox: teeBox)
        }
        if !courseTees.isEmpty {
            return Self.normalizedTeeOptions(courseTees, currentTeeBox: teeBox)
        }

        // A remotely searched course has no local Tee authority yet. Keep the explicit
        // `unknown` request available so it can start immediately, but never present a
        // fabricated colour list while the real `/tees` response is pending or unavailable.
        if selectedCourseRequiresRemoteTees || selectedCourseWasManualSearch {
            let current = teeBox.trimmingCharacters(in: .whitespacesAndNewlines)
            return current.caseInsensitiveCompare("unknown") == .orderedSame ? ["unknown"] : []
        }

        let base = ["blue", "white", "red", "gold", "black", "green", "yellow", "silver"]
        return Self.normalizedTeeOptions(base, currentTeeBox: teeBox)
    }

    private static func normalizedTeeOptions(_ values: [String], currentTeeBox: String) -> [String] {
        var seen = Set<String>()
        var result: [String] = []
        for tee in values {
            let trimmed = tee.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, seen.insert(trimmed.lowercased()).inserted else { continue }
            result.append(trimmed)
        }
        // 保证当前所选台一定可选,即使它不在解析出的列表里。
        let currentTrimmed = currentTeeBox.trimmingCharacters(in: .whitespaces)
        if !currentTrimmed.isEmpty, seen.insert(currentTrimmed.lowercased()).inserted {
            result.append(currentTrimmed)
        }
        return result
    }

    /// This tee's yards for what is being started, from the tees authority, else nil. The
    /// authority's `yards` is the total over its `holeCount`; it is shown only when that is the
    /// played hole count, never a total for a different set of holes.
    private func teeYards(_ tee: String) -> Int? {
        guard let row = fetchedTees.first(where: { $0.teeBox.lowercased() == tee.lowercased() }) else { return nil }
        return StartRoundPresentation.teeYards(
            total: row.yards,
            teeHoleCount: row.holeCount,
            playedHoles: selectedSegment?.resolvedHoles
        )
    }

    /// 选台菜单标签:中文台名 + 已知则附总码数,如「蓝 T · 6412 码」。
    private func teeMenuLabel(_ tee: String) -> String {
        if let yards = teeYards(tee) {
            return "\(zhTeeLabel(tee)) · \(yards) 码"
        }
        return zhTeeLabel(tee)
    }

    private func zhTeeLabel(_ tee: String) -> String {
        StartRoundPresentation.teeShortLabel(tee) ?? tee
    }

    /// "从 B 场 开始 · 蓝 T" — the shared `NineLoopPlan` copy for the chosen first loop.
    private var startActionTitle: String {
        StartRoundPresentation.startActionTitle(
            selected: selectedSegment,
            loops: selectedVenueLoops,
            teeBox: teeBox
        )
    }

    private var startCard: some View {
        VStack(spacing: 8) {
            if !isPreparing, let failure = Self.roundPreparationFailureMessage(from: syncStatus) {
                Label(failure, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier("start-round-preparation-error")
            }
            Button {
                if let courseGlobalId {
                    // Only the first loop is prepared. The second loop is chosen at the turn
                    // (NineLoopPlan / LiveRoundTurnSheet), never composed here.
                    onPrepareCourseRound(courseGlobalId, roundId, teeBox, nine)
                    // Don't pop manually — once the round is prepared the Hub navigates straight
                    // into the live hole (pendingLiveHole → path).
                }
            } label: {
                HStack(spacing: 8) {
                    if isPreparing {
                        ProgressView()
                            .tint(.white)
                    }
                    Text(startActionTitle)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
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
        }
    }

    /// The shared sync label contains both normal cache states and actionable start failures. Keep
    /// successful background/cache chatter out of the setup screen, but never turn a failed Start
    /// into an unexplained spinner that simply disappears.
    static func roundPreparationFailureMessage(from status: String) -> String? {
        let normalized = status.trimmingCharacters(in: .whitespacesAndNewlines)
        let failurePrefixes = [
            "无法开始", "暂时无法开始", "开始失败", "未联网", "离线中",
        ]
        return failurePrefixes.contains(where: { normalized.hasPrefix($0) }) ? normalized : nil
    }

    /// Group rows by physical venue without re-sorting them by historical play count. The source is
    /// supplied by the caller so provider results and downloaded offline packages stay separate.
    private func makeVenueGroups(
        from options: [MobileCourseOption]
    ) -> [(venue: String, segments: [MobileCourseOption])] {
        var groups: [(venue: String, segments: [MobileCourseOption])] = []
        for option in options {
            let venue = option.venueDisplayName
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
        segment.resolvedSegmentLabel ?? "~~"
    }

    private func baseCourseName(_ name: String) -> String {
        name.components(separatedBy: " ~ ").first?.trimmingCharacters(in: .whitespaces) ?? name
    }

    static func selectionState(
        for option: MobileCourseOption,
        currentTeeBox: String,
        uuid: UUID = UUID()
    ) -> CourseSelectionState {
        var selectedTee = currentTeeBox
        if let optionTeeBox = option.teeBox, optionTeeBox != "unknown" {
            selectedTee = optionTeeBox
        }
        // Default to a sensible real tee for the chosen course (Blue/White, else the first).
        let tees = option.tees ?? []
        if !tees.isEmpty, !tees.contains(where: { $0.lowercased() == selectedTee.lowercased() }) {
            selectedTee = tees.first(where: { ["blue", "white"].contains($0.lowercased()) }) ?? tees.first ?? selectedTee
        }
        return CourseSelectionState(
            globalIdText: String(option.globalId),
            roundId: Self.freshLiveRoundId(globalId: option.globalId, uuid: uuid),
            teeBox: selectedTee
        )
    }

    private func applySelectedCourse(_ option: MobileCourseOption) {
        let state = Self.selectionState(for: option, currentTeeBox: teeBox)
        courseGlobalIdText = state.globalIdText
        roundId = state.roundId
        teeBox = state.teeBox
    }

    static func freshLiveRoundId(globalId: Int, uuid: UUID = UUID()) -> String {
        "live-\(globalId)-\(uuid.uuidString)"
    }

    /// Provider-backed rows only. Downloaded packages are rendered in their own offline section and
    /// cannot silently become nearby/second-nine evidence.
    private var availableCourseOptions: [MobileCourseOption] {
        Self.reconciledCourseOptions(
            primary: nearbyCourseOptions + remoteCourseOptions,
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    /// Reconcile the persisted recovery row with any current Garmin facts for the same global id,
    /// while keeping the persisted row as the explicit source that made it visible.
    private var recentResolvedCourseOption: MobileCourseOption? {
        guard let recentCourseOption,
              recentCourseOption.globalId > 0 else { return nil }
        return Self.reconciledCourseOption(
            provider: recentCourseOption,
            catalogue: courseOptions.first { $0.globalId == recentCourseOption.globalId },
            downloaded: downloadedCourseOptions.first { $0.globalId == recentCourseOption.globalId }
        )
    }

    /// A recent row is only needed when the current provider response does not contain that global
    /// id. Search results and nearby rows win automatically, so this never duplicates a live row.
    private var recentCourseFallbackOption: MobileCourseOption? {
        Self.recentCourseFallback(
            recent: recentCourseOption,
            provider: nearbyCourseOptions + remoteCourseOptions,
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    /// Pure source-selection rule for the recent-course recovery row. Provider rows always win;
    /// catalogue/downloaded facts can enrich the row but can never turn it into nearby evidence.
    static func recentCourseFallback(
        recent: MobileCourseOption?,
        provider: [MobileCourseOption],
        catalogue: [MobileCourseOption] = [],
        downloaded: [MobileCourseOption] = []
    ) -> MobileCourseOption? {
        guard let recent,
              recent.globalId > 0,
              !recent.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        guard !Set(provider.map(\.globalId)).contains(recent.globalId) else { return nil }
        return reconciledCourseOption(
            provider: recent,
            catalogue: catalogue.first { $0.globalId == recent.globalId },
            downloaded: downloaded.first { $0.globalId == recent.globalId }
        )
    }

    private var offlineResolvedCourseOptions: [MobileCourseOption] {
        Self.reconciledCourseOptions(
            primary: offlineCourseOptions,
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    private var explicitCourseOptions: [MobileCourseOption] {
        Self.reconciledCourseOptions(
            primary: courseOptions + downloadedCourseOptions,
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    private var courseLookupOptions: [MobileCourseOption] {
        Self.reconciledCourseOptions(
            primary: availableCourseOptions
                + offlineResolvedCourseOptions
                + explicitCourseOptions
                + (recentResolvedCourseOption.map { [$0] } ?? []),
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    /// The source that granted the current selection owns its sibling loops. Mixing a stale local
    /// package into a provider row is what previously produced C/全场/全场 for Black Knight.
    private var selectedAuthorityOptions: [MobileCourseOption] {
        guard let selectedSegment else { return [] }
        let selectedID = selectedSegment.globalId
        if nearbyCourseOptions.contains(where: { $0.globalId == selectedID }) {
            return Self.reconciledCourseOptions(
                primary: nearbyCourseOptions,
                catalogue: courseOptions,
                downloaded: downloadedCourseOptions
            )
        }
        if remoteCourseOptions.contains(where: { $0.globalId == selectedID }) {
            return Self.reconciledCourseOptions(
                primary: remoteCourseOptions,
                catalogue: courseOptions,
                downloaded: downloadedCourseOptions
            )
        }
        if offlineCourseOptions.contains(where: { $0.globalId == selectedID }) {
            return offlineResolvedCourseOptions
        }
        if recentCourseOption?.globalId == selectedID,
           let recent = recentResolvedCourseOption {
            return Self.reconciledCourseOptions(
                primary: [recent] + courseOptions + downloadedCourseOptions,
                catalogue: courseOptions,
                downloaded: downloadedCourseOptions
            )
        }
        return explicitCourseOptions.filter { Self.samePhysicalVenue($0, selectedSegment) }
    }

    /// Nearby/search metadata determines which rows are in range, while the latest mobile catalogue
    /// owns each global ID's playable loop structure. Downloaded packages contribute offline state
    /// only. Older packages can retain a played combination such as `~ C/A` or an empty string in
    /// `segmentLabel`; treating either as the current loop produced C/全场/全场 for Black Knight.
    static func reconciledCourseOptions(
        primary: [MobileCourseOption],
        catalogue: [MobileCourseOption],
        downloaded: [MobileCourseOption]
    ) -> [MobileCourseOption] {
        var catalogueByID: [Int: MobileCourseOption] = [:]
        var downloadedByID: [Int: MobileCourseOption] = [:]
        for option in catalogue where catalogueByID[option.globalId] == nil {
            catalogueByID[option.globalId] = option
        }
        for option in downloaded where downloadedByID[option.globalId] == nil {
            downloadedByID[option.globalId] = option
        }

        var seen = Set<Int>()
        return primary.compactMap { provider in
            guard seen.insert(provider.globalId).inserted else { return nil }
            return reconciledCourseOption(
                provider: provider,
                catalogue: catalogueByID[provider.globalId],
                downloaded: downloadedByID[provider.globalId]
            )
        }
    }

    static func reconciledCourseOption(
        provider: MobileCourseOption,
        catalogue: MobileCourseOption?,
        downloaded: MobileCourseOption?
    ) -> MobileCourseOption {
        let segmentHoles = firstPositive([
            catalogue?.segmentHoles,
            provider.segmentHoles,
            downloaded?.segmentHoles,
            provider.holes,
            catalogue?.holes,
            downloaded?.holes,
        ]) ?? provider.holes
        // The fresh backend row is the sole name authority. Catalogue and downloaded rows may
        // still supply tee/geometry facts, but their names and loop labels are never merged into a
        // current provider row. This is what keeps search, nearby and package selection identical
        // after an old local package has been renamed or removed.
        let venue = MobileCourseDisplayLocalization.canonicalVenueName(
            providerName: provider.name,
            venueName: provider.venueName,
            venueNameSource: provider.venueNameSource,
            segmentLabel: provider.segmentLabel,
            globalId: provider.globalId
        )
        // Provider rows can retain Garmin's played route (for example A/B or C/A) in their
        // display name while the current catalogue only contains one factual nine-hole loop.
        // Recover the single-loop label from all factual sources without putting it back into the
        // physical venue name shown to the player.
        let providerLabel = resolvedSegmentLabel(
            explicit: [provider.segmentLabel, catalogue?.segmentLabel, downloaded?.segmentLabel],
            names: [provider.name, catalogue?.name, downloaded?.name],
            segmentHoles: segmentHoles,
            allowCompositePrefix: segmentHoles == 9
                && (catalogue?.resolvedHoles == 9 || downloaded?.resolvedHoles == 9)
        )
        let displayName = venue
        let facts = catalogue ?? downloaded ?? provider
        let tees = firstNonEmptyList([catalogue?.tees, downloaded?.tees, provider.tees])

        return MobileCourseOption(
            globalId: provider.globalId,
            courseKey: catalogue?.courseKey ?? downloaded?.courseKey ?? provider.courseKey,
            name: displayName,
            roundCount: facts.roundCount,
            latestRoundId: facts.latestRoundId,
            latestRoundDate: facts.latestRoundDate,
            templateRoundId: facts.templateRoundId,
            suggestedLiveRoundId: facts.suggestedLiveRoundId,
            holes: segmentHoles,
            teeBox: facts.teeBox ?? provider.teeBox,
            geometryCoverage: facts.geometryCoverage,
            sourceRefs: facts.sourceRefs,
            venueName: venue,
            venueNameSource: provider.venueNameSource,
            segmentLabel: providerLabel,
            segmentHoles: segmentHoles,
            latitude: provider.latitude ?? catalogue?.latitude ?? downloaded?.latitude,
            longitude: provider.longitude ?? catalogue?.longitude ?? downloaded?.longitude,
            tees: tees
        )
    }

    private static func firstPositive(_ values: [Int?]) -> Int? {
        values.compactMap { $0 }.first { $0 > 0 }
    }

    private static func firstNonEmpty(_ values: [String?]) -> String? {
        values.compactMap { value -> String? in
            guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !trimmed.isEmpty else { return nil }
            return trimmed
        }.first
    }

    private static func firstNonEmptyList(_ values: [[String]?]) -> [String]? {
        values.compactMap { value in
            guard let value, !value.isEmpty else { return nil }
            return value
        }.first
    }

    private static func resolvedSegmentLabel(
        explicit: [String?],
        names: [String?],
        segmentHoles: Int,
        allowCompositePrefix: Bool = false
    ) -> String? {
        for raw in explicit {
            if let label = normalizedSegmentLabel(raw, segmentHoles: segmentHoles) {
                return label
            }
        }
        guard segmentHoles == 9 else { return nil }
        for name in names {
            guard let name,
                  let suffix = MobileCourseDisplayLocalization.splitCourseName(name).suffix,
                  let label = normalizedSegmentLabel(suffix, segmentHoles: segmentHoles) else {
                if allowCompositePrefix,
                   let name,
                   let suffix = MobileCourseDisplayLocalization.splitCourseName(name).suffix,
                   let prefix = compositeSegmentPrefix(suffix),
                   let label = normalizedSegmentLabel(prefix, segmentHoles: segmentHoles) {
                    return label
                }
                continue
            }
            return label
        }
        return nil
    }

    /// Older Garmin history/package rows can retain the played route (`A/B`, `C/A`, `ABC`)
    /// even though the current nine-hole catalogue row represents one loop. Recover only the
    /// first single-loop code when a factual 9-hole structure is already available; never expose
    /// the composite value itself as a selectable segment.
    private static func compositeSegmentPrefix(_ raw: String) -> String? {
        let normalized = raw.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !normalized.isEmpty else { return nil }
        let first = normalized.split(whereSeparator: { $0 == "/" || $0 == "+" }).first.map(String.init)
        let candidate = first ?? (normalized.count > 1 ? String(normalized.prefix(1)) : nil)
        guard let candidate, candidate.count == 1,
              candidate.unicodeScalars.allSatisfy({ (65...72).contains($0.value) }) else {
            return nil
        }
        let compact = normalized.filter { !$0.isWhitespace && $0 != "/" && $0 != "+" }
        guard compact.count > 1,
              compact.unicodeScalars.allSatisfy({ (65...72).contains($0.value) }) else {
            return nil
        }
        return candidate
    }

    private static func normalizedSegmentLabel(_ raw: String?, segmentHoles: Int) -> String? {
        _ = segmentHoles
        guard let label = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !label.isEmpty else { return nil }
        // A/C, A+B, and compact AB/ABC values describe a played combination. Never truncate one
        // into a misleading single loop; the current CourseView row must provide that authority.
        guard !MobileCourseDisplayLocalization.isCompositeSegment(label) else { return nil }
        let wholeCourseLabels = Set(["all", "full", "全场", "整场"])
        guard !label.isEmpty, !wholeCourseLabels.contains(label.lowercased()) else { return nil }
        return label
    }

    private var selectedCourseRequiresRemoteTees: Bool {
        guard let courseGlobalId else { return false }
        return !courseOptions.contains { $0.globalId == courseGlobalId }
            && !downloadedCourseOptions.contains { $0.globalId == courseGlobalId }
            && recentResolvedCourseOption?.globalId != courseGlobalId
    }

    private func selectSearchResult(
        _ selected: MobileCourseSearchMatch,
        _ matches: [MobileCourseSearchMatch]
    ) {
        let isSameCourse = courseGlobalId == selected.globalId
        guard let option = resolvedOption(for: selected) else { return }
        // The explicit catalogue choice supersedes any prior nearby transport error. Do not leave
        // the old "nearby unavailable" banner beside a valid manually searched course.
        // Invalidate an in-flight nearby request as well; its late failure must not repaint this
        // explicit search result as a nearby-service error.
        nearbyRequestToken = nil
        isLoadingNearby = false
        nearbyCourseOptions = []
        nearbyStatusText = nil
        nearbyDiscoveryFailed = false
        offlineCourseOptions = []
        remoteCourseOptions = Self.sameVenueSearchOptions(
            selected: option,
            candidates: matches.compactMap { resolvedOption(for: $0) }
        )
        userPickedVenue = true
        selectedCourseWasManualSearch = true
        // Re-selecting the same search result (for example nearby first, then name search) keeps
        // its already-fetched Tee authority. Clearing it would not retrigger `.task(id:)` because
        // the globalId is unchanged, leaving the primary action disabled forever.
        if !isSameCourse {
            fetchedTees = []
            teeBox = ""
            teeLoadFailed = false
        }
        // Apply the resolved option directly. State writes are coalesced by SwiftUI, so looking
        // the option up again immediately after assigning remoteCourseOptions can observe the
        // previous candidate list when a long virtualized search result is being dismissed.
        applySelectedCourse(option)
        // A search result may have no Tee rows yet. `unknown` is an explicit server-side request
        // for the course default, not a fabricated colour or GPS-dependent choice; it lets the
        // player enter the map while the Tee request continues in the background. Do not carry a
        // previously selected colour into a course whose Tee authority is still unknown.
        let hasSearchTeeAuthority = !(option.tees ?? []).isEmpty
            || option.teeBox.map {
                let trimmed = $0.trimmingCharacters(in: .whitespacesAndNewlines)
                return !trimmed.isEmpty && trimmed.caseInsensitiveCompare("unknown") != .orderedSame
            } ?? false
        if fetchedTees.isEmpty && !hasSearchTeeAuthority {
            teeBox = "unknown"
        }
        // Close only after all selection state has been written. The child search view deliberately
        // leaves dismissal to this parent so a no-GPS manual search is immediately startable.
        showingCourseSearch = false
    }

    /// Selecting one catalogue row returns to the compact start form, but the sibling loops from
    /// that same physical venue must travel with it. Otherwise a searched 9-hole course can no longer
    /// offer A+A or A+B even though the catalogue response already supplied those choices.
    static func sameVenueSearchOptions(
        selected: MobileCourseOption,
        candidates: [MobileCourseOption]
    ) -> [MobileCourseOption] {
        let selectedVenue = courseVenueName(selected)
        var seen = Set<Int>()
        return ([selected] + candidates).filter {
            courseVenueName($0) == selectedVenue && seen.insert($0.globalId).inserted
        }
    }

    /// Return only factual 9-hole siblings from the authority that supplied the selected row.
    /// This is intentionally separate from the broad lookup used to resolve a back-course id.
    static func sameVenueNineHoleCandidates(
        selected: MobileCourseOption,
        candidates: [MobileCourseOption]
    ) -> [MobileCourseOption] {
        guard selected.resolvedHoles == 9 else { return [] }
        var seen = Set<Int>()
        return candidates
            .filter {
                selected.resolvedHoles == 9
                    && $0.resolvedHoles == 9
                    && samePhysicalVenue(selected, $0)
                    && seen.insert($0.globalId).inserted
            }
            .sorted { segmentSortKeyStatic($0) < segmentSortKeyStatic($1) }
    }

    private static func segmentSortKeyStatic(_ segment: MobileCourseOption) -> String {
        segment.resolvedSegmentLabel ?? "~~"
    }

    /// Keep the manual-search start exception scoped to one physical venue. The provider models
    /// each playable loop as a separate global ID, so comparing IDs here would incorrectly revoke
    /// the exception when the player changes A/B/C or chooses a second nine.
    static func courseVenueName(_ option: MobileCourseOption) -> String {
        MobileCourseDisplayLocalization.canonicalVenueName(
            providerName: option.name,
            venueName: option.venueName,
            venueNameSource: option.venueNameSource,
            segmentLabel: option.segmentLabel,
            globalId: option.globalId
        )
    }

    static func samePhysicalVenue(_ lhs: MobileCourseOption, _ rhs: MobileCourseOption) -> Bool {
        courseVenueName(lhs).trimmingCharacters(in: .whitespacesAndNewlines)
            .caseInsensitiveCompare(courseVenueName(rhs).trimmingCharacters(in: .whitespacesAndNewlines)) == .orderedSame
    }

    static func preservesManualSearchProvenance(
        wasManualSearch: Bool,
        previous: MobileCourseOption?,
        next: MobileCourseOption
    ) -> Bool {
        wasManualSearch && previous.map { samePhysicalVenue($0, next) } == true
    }

    private var locationDiscoveryKey: String {
        guard let coordinate = locationProvider.latestFix?.coordinate else {
            return "waiting:\(locationProvider.authorizationStatus.rawValue)"
        }
        return Self.nearbyDiscoveryBucket(
            latitude: coordinate.latitude,
            longitude: coordinate.longitude
        )
    }

    /// A retry changes the task identity even when the GPS bucket is unchanged.
    private var nearbyDiscoveryTaskKey: String {
        let downloadedIDs = downloadedCourseOptions
            .map(\.globalId)
            .sorted()
            .map(String.init)
            .joined(separator: ",")
        return "\(locationDiscoveryKey)#downloads-\(downloadedIDs)#retry-\(nearbyRetryToken)"
    }

    /// Nearby is a 50 km catalogue query, so restarting it for every 3–11 m Core Location update
    /// only cancels useful in-flight requests while the player walks or arrives by cart.  A roughly
    /// 1 km bucket still refreshes after meaningful travel without letting normal GPS jitter keep
    /// the start screen in an endless loading loop.
    static func nearbyDiscoveryBucket(latitude: Double, longitude: Double) -> String {
        "\(Int(floor(latitude * 100))):\(Int(floor(longitude * 100)))"
    }

    static func shouldApplyNearbyDiscoveryResult(
        isCancelled: Bool,
        requestToken: UUID,
        activeRequestToken: UUID?,
        requestKey: String,
        currentRequestKey: String
    ) -> Bool {
        !isCancelled
            && activeRequestToken == requestToken
            && currentRequestKey == requestKey
    }

    static func nearbyDiscoveryErrorMessage(_ error: Error) -> String {
        if case let SyncClientError.http(status, _) = error {
            switch status {
            case 401:
                return "登录已失效；请重新登录后再查找附近球场。"
            case 403:
                return "当前账号无权读取球场目录。"
            case 500...599:
                return "球场目录暂时不可用；可重试，或按球场名搜索。"
            default:
                break
            }
        }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost,
                 .cannotFindHost, .dnsLookupFailed, .timedOut, .secureConnectionFailed:
                return "附近球场暂时无法读取；可重试，或按城市或球场名搜索。"
            default:
                break
            }
        }
        return "附近球场暂时无法读取；可重试，或按球场名搜索。"
    }

    @MainActor
    private func discoverNearbyCourses() async {
        let requestToken = UUID()
        nearbyRequestToken = requestToken
        // Once the player has chosen a manual search result, nearby discovery is background noise.
        // Do not let a new GPS bucket or a late transport failure overwrite that explicit choice.
        guard !selectedCourseWasManualSearch else {
            isLoadingNearby = false
            return
        }
        guard let fix = locationProvider.latestFix else {
            nearbyCourseOptions = []
            offlineCourseOptions = resolvedOfflineOptions(downloadedCourseOptions)
            nearbyDiscoveryFailed = false
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
        let requestKey = locationDiscoveryKey
        // Keep local candidates in their explicit offline section while the provider request is in
        // flight. They are useful for an immediate offline start, but they are not nearby evidence.
        nearbyCourseOptions = []
        offlineCourseOptions = resolvedOfflineOptions(localNearby)
        nearbyDiscoveryFailed = false
        isLoadingNearby = true
        nearbyStatusText = nil
        defer {
            if nearbyRequestToken == requestToken {
                isLoadingNearby = false
            }
        }
        do {
            let matches = try await onNearbyCourses(
                fix.coordinate.latitude,
                fix.coordinate.longitude,
                50
            )
            guard Self.shouldApplyNearbyDiscoveryResult(
                isCancelled: Task.isCancelled,
                requestToken: requestToken,
                activeRequestToken: nearbyRequestToken,
                requestKey: requestKey,
                currentRequestKey: locationDiscoveryKey
            ) else { return }
            var seen = Set<Int>()
            let providerNearby = matches.compactMap { resolvedOption(for: $0) }
            nearbyCourseOptions = providerNearby.filter {
                seen.insert($0.globalId).inserted
            }
            let providerIDs = Set(nearbyCourseOptions.map(\.globalId))
            offlineCourseOptions = resolvedOfflineOptions(localNearby).filter {
                !providerIDs.contains($0.globalId)
            }
            nearbyDiscoveryFailed = false
            nearbyStatusText = nearbyCourseOptions.isEmpty
                ? "当前位置 50 km 内没有找到球场；可以扩大范围或按名称搜索。"
                : nil
            if !userPickedVenue {
                if nearbyVenues.count == 1 {
                    ensureDefaultSelection()
                } else if selectedSegment == nil || !nearbyCourseOptions.contains(where: {
                    String($0.globalId) == courseGlobalIdText
                }) {
                    clearAutomaticSelection()
                }
            }
        } catch {
            guard Self.shouldApplyNearbyDiscoveryResult(
                isCancelled: Task.isCancelled,
                requestToken: requestToken,
                activeRequestToken: nearbyRequestToken,
                requestKey: requestKey,
                currentRequestKey: locationDiscoveryKey
            ) else { return }
            nearbyCourseOptions = []
            // Keep a verified local package usable even when its older package format has no
            // per-hole Tee anchor. Rows with factual coordinates still need to be within 50 km;
            // coordinate-less rows are shown only in the explicitly labelled offline section.
            let offlineFallback = Self.locallyAvailableNearbyCourses(
                downloadedCourseOptions,
                latitude: fix.coordinate.latitude,
                longitude: fix.coordinate.longitude,
                radiusKm: 50,
                includeUnknownCoordinates: true
            )
            offlineCourseOptions = resolvedOfflineOptions(offlineFallback)
            nearbyDiscoveryFailed = true
            nearbyStatusText = Self.nearbyDiscoveryErrorMessage(error)
            // A failed provider request must not preserve an implicit historical/default course.
            // A player who tapped a row (including an offline row while loading) keeps that choice.
            clearAutomaticSelection()
        }
    }

    private func resolvedOfflineOptions(_ options: [MobileCourseOption]) -> [MobileCourseOption] {
        Self.reconciledCourseOptions(
            primary: options,
            catalogue: courseOptions,
            downloaded: downloadedCourseOptions
        )
    }

    private func clearAutomaticSelection() {
        guard !userPickedVenue else { return }
        courseGlobalIdText = ""
        roundId = defaultRoundId
        teeBox = ""
        fetchedTees = []
        teeLoadFailed = false
        selectedCourseWasManualSearch = false
    }

    private func resolvedOption(for match: MobileCourseSearchMatch) -> MobileCourseOption? {
        guard let provider = match.courseOption else { return nil }
        return Self.reconciledCourseOption(
            provider: provider,
            catalogue: courseOptions.first { $0.globalId == match.globalId },
            downloaded: downloadedCourseOptions.first { $0.globalId == match.globalId }
        )
    }
}
