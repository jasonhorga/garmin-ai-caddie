import SwiftUI

struct WatchCourseRowPresentation: Equatable, Identifiable {
    var id: String { "\(course.globalId):\(course.segmentLabel ?? course.name)" }

    let course: WatchCourseOption
    let title: String
    let subtitle: String
    let isCached: Bool
}

struct WatchCourseGroupPresentation: Equatable, Identifiable {
    var id: String { title }

    let title: String
    let rows: [WatchCourseRowPresentation]
    let showsRefresh: Bool
}

private struct WatchCourseSetupDestination: Equatable {
    let row: WatchCourseRowPresentation
    let ensureGeometry: Bool
}

/// Home-before-a-round. Every production path starts from a real course. The picker shows the
/// provider-wide nearby result and a precise downloaded fallback for courses the player has already
/// installed; arbitrary history rows still require explicit catalogue search.
public struct WatchStartView: View {
    public let phoneReachable: Bool
    public let courses: [WatchCourseOption]
    /// Provider-filtered nearby results. The full local library remains available for cached offline
    /// starts and 9-hole loop selection; it must never silently become the nearby feed.
    public let nearbyCourseOptions: [WatchCourseOption]?
    public let searchMatches: [WatchCourseSearchMatch]
    public let cachedCourseIds: Set<Int>
    public let isLoadingCourses: Bool
    public let discoveryState: WatchCourseDiscoveryState
    public let isSearchingCourses: Bool
    public let preparingCourseId: Int?
    public let errorMessage: String?
    public let currentLatitude: Double?
    public let currentLongitude: Double?
    public let onRefresh: () -> Void
    public let onSearchAllCourses: (String) -> Void
    public let onLoadCourseTees: (Int) async -> [WatchCourseTee]
    public let onStartCourse: (WatchCourseSelection) -> Void

    @State private var searchText = ""
    @State private var setupDestination: WatchCourseSetupDestination?
    @State private var showingRemoteSearch: Bool

    public init(
        phoneReachable: Bool,
        courses: [WatchCourseOption] = [],
        nearbyCourses: [WatchCourseOption]? = nil,
        searchMatches: [WatchCourseSearchMatch] = [],
        cachedCourseIds: Set<Int> = [],
        isLoadingCourses: Bool = false,
        discoveryState: WatchCourseDiscoveryState = .waitingForGPS,
        isSearchingCourses: Bool = false,
        preparingCourseId: Int? = nil,
        errorMessage: String? = nil,
        currentLatitude: Double? = nil,
        currentLongitude: Double? = nil,
        onRefresh: @escaping () -> Void = {},
        onSearchAllCourses: @escaping (String) -> Void = { _ in },
        onLoadCourseTees: @escaping (Int) async -> [WatchCourseTee] = { _ in [] },
        onStartCourse: @escaping (WatchCourseSelection) -> Void = { _ in }
    ) {
        self.phoneReachable = phoneReachable
        self.courses = courses
        self.nearbyCourseOptions = nearbyCourses
        self.searchMatches = searchMatches
        self.cachedCourseIds = cachedCourseIds
        self.isLoadingCourses = isLoadingCourses
        self.discoveryState = discoveryState
        self.isSearchingCourses = isSearchingCourses
        self.preparingCourseId = preparingCourseId
        self.errorMessage = errorMessage
        self.currentLatitude = currentLatitude
        self.currentLongitude = currentLongitude
        self.onRefresh = onRefresh
        self.onSearchAllCourses = onSearchAllCourses
        self.onLoadCourseTees = onLoadCourseTees
        self.onStartCourse = onStartCourse
        _showingRemoteSearch = State(initialValue: !searchMatches.isEmpty)
    }

    public var body: some View {
        Group {
            if let destination = setupDestination {
                WatchRoundSetupView(
                    front: destination.row.course,
                    courses: allSelectableCourses,
                    hasCachedVersion: destination.row.isCached,
                    isPreparing: preparingCourseId != nil,
                    errorMessage: errorMessage,
                    ensureGeometry: destination.ensureGeometry,
                    onLoadTees: onLoadCourseTees,
                    onStart: onStartCourse,
                    onBack: { setupDestination = nil }
                )
            } else if showingRemoteSearch {
                remoteSearchScreen
            } else {
                coursePicker
            }
        }
        .persistentSystemOverlays(.hidden)
        .onChange(of: singleNearbyVenue?.id, initial: true) { _, _ in
            openSingleNearbyCourseIfNeeded()
        }
    }

    private var coursePicker: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                courseSections

                discoveryStatus

                remoteSearchEntry

                if let errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.orange)
                        .padding(7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color.orange.opacity(0.10))
                        )
                }

                HStack(spacing: 4) {
                    Image(
                        systemName: phoneReachable
                            ? "iphone.radiowaves.left.and.right"
                            : "applewatch"
                    )
                    Text(phoneReachable ? "iPhone 已连接" : "已下载球场可离线开局")
                }
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
            .padding(.bottom, 14)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
    }

    @ViewBuilder
    private var discoveryStatus: some View {
        switch discoveryState {
        case .waitingForGPS:
            Label("正在等待 GPS 定位", systemImage: "location.slash")
                .foregroundStyle(.secondary)
        case .needsAuthentication:
            Label("附近球场需要先在 iPhone 登录并同步", systemImage: "lock")
                .foregroundStyle(.orange)
        case .discovering:
            Label("正在查询附近球场", systemImage: "location.magnifyingglass")
                .foregroundStyle(.secondary)
        case .ready:
            EmptyView()
        case .error:
            Label("附近球场查询失败，可重试或搜索名称", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.orange)
        }
    }

    @ViewBuilder
    private var courseSections: some View {
        ForEach(courseGroups) { group in
            VStack(alignment: .leading, spacing: 4) {
                sectionHeader(group.title, showsRefresh: group.showsRefresh)
                    .padding(.bottom, 3.5)

                if group.rows.isEmpty {
                    if isLoadingCourses {
                        HStack(spacing: 5) {
                            ProgressView().controlSize(.small)
                            Text("正在获取球场")
                        }
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(.secondary)
                        .padding(7)
                    } else {
                        Text(hasCurrentLocation ? "附近没有找到球场" : "正在等待 GPS 定位")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(.secondary)
                            .padding(7)
                    }
                }

                ForEach(group.rows) { row in
                    courseButton(row)
                }

            }
        }
    }

    private var remoteSearchEntry: some View {
        Button {
            showingRemoteSearch = true
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                Text("搜索全部球场")
                Spacer(minLength: 0)
                Image(systemName: "chevron.forward")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(.secondary)
            }
            .font(.system(size: 15, weight: .black))
            .padding(.horizontal, 8)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.white.opacity(0.06))
            )
        }
        .buttonStyle(.plain)
        .disabled(preparingCourseId != nil)
    }

    private var remoteSearchScreen: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 7) {
                Button {
                    showingRemoteSearch = false
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "chevron.backward")
                            .font(.system(size: 14, weight: .black))
                        Text("全部球场")
                            .font(.system(size: 17, weight: .black))
                    }
                    .foregroundStyle(.primary)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                TextField("输入球场名称", text: $searchText)
                    .font(.system(size: 15, weight: .bold))
                    .textFieldStyle(.plain)
                    .submitLabel(.search)
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 9, style: .continuous)
                            .fill(Color.white.opacity(0.06))
                    )
                    .onSubmit {
                        guard canSearchAllCourses else { return }
                        onSearchAllCourses(trimmedSearchText)
                    }

                Button {
                    onSearchAllCourses(trimmedSearchText)
                } label: {
                    if isSearchingCourses {
                        HStack(spacing: 6) {
                            ProgressView()
                                .controlSize(.small)
                            Text("正在搜索")
                            Spacer(minLength: 0)
                        }
                    } else {
                        HStack(spacing: 6) {
                            Image(systemName: "magnifyingglass")
                            Text("搜索")
                            Spacer(minLength: 0)
                        }
                    }
                }
                .font(.system(size: 15, weight: .black))
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.white.opacity(0.06))
                )
                .buttonStyle(.plain)
                .disabled(!canSearchAllCourses)
                .opacity(canSearchAllCourses ? 1 : 0.58)

                ForEach(visibleSearchMatches) { match in
                    searchResultRow(match)
                }

                if !searchMatches.isEmpty, visibleSearchMatches.isEmpty {
                    Text("该球场已在附近列表中")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.orange)
                        .padding(7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color.orange.opacity(0.10))
                        )
                }

                HStack(spacing: 4) {
                    Image(systemName: "arrow.down.circle")
                    Text("只下载选中的球场")
                }
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
            .padding(.bottom, 14)
        }
        .ignoresSafeArea(edges: .top)
        .scrollIndicators(.hidden)
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard WatchEdgeBackGesture.shouldTrigger(
                        startX: value.startLocation.x,
                        translation: value.translation
                    ) else { return }
                    showingRemoteSearch = false
                }
        )
    }

    private func sectionHeader(_ title: String, showsRefresh: Bool = false) -> some View {
        HStack(spacing: 6) {
            Text(title)
                .font(.system(size: 15, weight: .black))
                .foregroundStyle(.primary)
            if showsRefresh {
                Button(action: onRefresh) {
                    Group {
                        if isLoadingCourses {
                            ProgressView().controlSize(.mini)
                        } else {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 13, weight: .black))
                        }
                    }
                    .frame(width: 24, height: 20)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(isLoadingCourses || preparingCourseId != nil)
                .accessibilityLabel(isLoadingCourses ? "正在更新球场" : "刷新球场")
            }
            // This screen deliberately draws into the top safe area so its heading can share the
            // first row with the watchOS clock. Keep the refresh control beside the heading; putting
            // it after the spacer placed both the icon and loading spinner underneath that clock.
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 2)
    }

    @ViewBuilder
    private func searchResultRow(_ match: WatchCourseSearchMatch) -> some View {
        if let course = match.courseOption {
            courseButton(
                course,
                subtitle: searchResultSubtitle(match),
                ensureGeometry: true
            )
        } else {
            HStack(spacing: 6) {
                Circle()
                    .fill(Color.orange)
                    .frame(width: 6, height: 6)
                VStack(alignment: .leading, spacing: 2) {
                    Text(match.name)
                        .font(.system(size: 15, weight: .black))
                        .lineLimit(2)
                    Text(searchResultSubtitle(match))
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 2)
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.orange)
                    .accessibilityLabel("洞数未知，无法开局")
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 9)
                    .fill(Color.white.opacity(0.06))
            )
        }
    }

    @ViewBuilder
    private func courseButton(
        _ course: WatchCourseOption,
        subtitle: String? = nil,
        ensureGeometry: Bool = false
    ) -> some View {
        courseButton(
            WatchCourseRowPresentation(
                course: course,
                title: course.displayName,
                subtitle: subtitle ?? standardSubtitle(for: course),
                isCached: cachedCourseIds.contains(course.globalId)
            ),
            ensureGeometry: ensureGeometry
        )
    }

    @ViewBuilder
    private func courseButton(
        _ row: WatchCourseRowPresentation,
        ensureGeometry: Bool = false
    ) -> some View {
        Button {
            setupDestination = WatchCourseSetupDestination(
                row: row,
                ensureGeometry: ensureGeometry
            )
        } label: {
            HStack(alignment: .center, spacing: 6) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.title)
                        .font(.system(size: 16, weight: .black))
                        .lineLimit(2)
                        .minimumScaleFactor(0.72)
                    Text(row.subtitle)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 2)
                if preparingCourseId == row.course.globalId {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Image(systemName: "chevron.forward")
                        .font(.system(size: 12, weight: .black))
                        .foregroundStyle(.secondary)
                }
            }
                .padding(.horizontal, 8)
                .padding(.vertical, 9)
                .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 9)
                    .fill(
                        row.isCached
                            ? Color(red: 0.015, green: 0.115, blue: 0.055)
                            : Color.white.opacity(0.06)
                    )
            )
            .accessibilityHint(row.isCached ? "已下载，可离线" : "需要下载")
        }
        .buttonStyle(.plain)
        .disabled(preparingCourseId != nil)
    }

    var courseGroups: [WatchCourseGroupPresentation] {
        var groups = [
            WatchCourseGroupPresentation(
                title: "附近球场",
                // Garmin presents a nearby venue once, then lets the player choose A/B/C (or an
                // 18-hole layout) inside setup. Counting each nine-hole segment as another nearby
                // course prevented the single-venue fast path and duplicated one place three times.
                rows: nearbyVenueRows,
                showsRefresh: true
            )
        ]
        // A precise local package is an actionable offline source, not a history feed. Keep it
        // reachable even when nearby discovery succeeds: a valid GPS result must not hide a course
        // the player deliberately downloaded for offline use. Omit only venues already represented
        // by the nearby group so the same physical venue is not rendered twice.
        if !cachedFallbackVenueRows.isEmpty {
            groups.append(
                WatchCourseGroupPresentation(
                    title: "已下载球场",
                    rows: cachedFallbackVenueRows,
                    showsRefresh: false
                )
            )
        }
        return groups
    }

    private var cachedVenueRows: [WatchCourseRowPresentation] {
        var seen = Set<String>()
        return courses
            .filter { cachedCourseIds.contains($0.globalId) }
            .sorted { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
            .compactMap { course in
                let venue = venueName(for: course)
                let key = venue.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
                guard seen.insert(key).inserted else { return nil }
                let venueCourses = courses.filter {
                    cachedCourseIds.contains($0.globalId)
                        && venueName(for: $0).caseInsensitiveCompare(venue) == .orderedSame
                }
                return WatchCourseRowPresentation(
                    course: course,
                    title: venue,
                    subtitle: cachedVenueSubtitle(segments: venueCourses, representative: course),
                    isCached: true
                )
            }
    }

    private var cachedFallbackVenueRows: [WatchCourseRowPresentation] {
        let nearbyKeys = Set(nearbyVenueRows.map { venueKey($0.title) })
        return cachedVenueRows.filter { !nearbyKeys.contains(venueKey($0.title)) }
    }

    private func venueKey(_ name: String) -> String {
        name.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
    }

    private func cachedVenueSubtitle(
        segments: [WatchCourseOption],
        representative: WatchCourseOption
    ) -> String {
        if segments.count > 1, segments.allSatisfy({ $0.playableHoleCount == 9 }) {
            return "\(segments.count) 个 9 洞组 · 离线可用"
        }
        return "\(representative.playableHoleCount) 洞 · 离线可用"
    }

    private func courseRow(
        _ course: WatchCourseOption,
        subtitle: String? = nil
    ) -> WatchCourseRowPresentation {
        WatchCourseRowPresentation(
            course: course,
            title: course.displayName,
            subtitle: subtitle ?? standardSubtitle(for: course),
            isCached: cachedCourseIds.contains(course.globalId)
        )
    }

    private func standardSubtitle(for course: WatchCourseOption) -> String {
        "\(course.playableHoleCount) 洞 · \(course.preferredTee)"
    }

    private var filteredCourses: [WatchCourseOption] {
        guard hasCurrentLocation,
              let currentLatitude,
              let currentLongitude else { return [] }
        return WatchCourseProximity.ranked(
            nearbyCourseOptions ?? courses,
            fromLatitude: currentLatitude,
            longitude: currentLongitude
        )
    }

    private var trimmedSearchText: String {
        searchText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSearchAllCourses: Bool {
        trimmedSearchText.count >= 2
            && !isSearchingCourses
            && preparingCourseId == nil
    }

    private var hasCurrentLocation: Bool {
        guard let currentLatitude, let currentLongitude else { return false }
        return currentLatitude.isFinite && currentLongitude.isFinite
            && (-90...90).contains(currentLatitude)
            && (-180...180).contains(currentLongitude)
    }

    private var nearbyCourses: [WatchCourseOption] {
        hasCurrentLocation ? filteredCourses : []
    }

    private func nearbySubtitle(for course: WatchCourseOption) -> String? {
        guard let distance = nearbyDistance(to: course),
              let label = WatchCourseProximity.distanceLabel(distance) else {
            return nil
        }
        return "\(course.playableHoleCount) 洞 · \(label)"
    }

    private func nearbyDistance(to course: WatchCourseOption) -> Double? {
        guard let currentLatitude, let currentLongitude else { return nil }
        return WatchCourseProximity.distanceM(
            to: course,
            fromLatitude: currentLatitude,
            longitude: currentLongitude
        )
    }

    private var visibleSearchMatches: [WatchCourseSearchMatch] {
        let knownIds = Set(courses.map(\.globalId))
        return searchMatches.filter { !knownIds.contains($0.globalId) }
    }

    private var allSelectableCourses: [WatchCourseOption] {
        var seen = Set<Int>()
        return (courses + searchMatches.compactMap(\.courseOption)).filter {
            seen.insert($0.globalId).inserted
        }
    }

    var singleNearbyVenue: WatchCourseRowPresentation? {
        guard hasCurrentLocation, nearbyVenueRows.count == 1 else { return nil }
        return nearbyVenueRows[0]
    }

    private func openSingleNearbyCourseIfNeeded() {
        guard setupDestination == nil,
              !showingRemoteSearch,
              preparingCourseId == nil,
              let row = singleNearbyVenue else { return }
        setupDestination = WatchCourseSetupDestination(row: row, ensureGeometry: false)
    }

    /// One row per physical venue, retaining the provider's nearest-first order. The representative
    /// remains a real selectable segment, while setup receives `allSelectableCourses` and exposes the
    /// venue's other 9-hole groups without downloading them in advance.
    private var nearbyVenueRows: [WatchCourseRowPresentation] {
        var seen = Set<String>()
        var rows: [WatchCourseRowPresentation] = []
        for course in nearbyCourses {
            let venue = venueName(for: course)
            let key = venue.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
            guard seen.insert(key).inserted else { continue }
            let segments = nearbyCourses.filter {
                venueName(for: $0).caseInsensitiveCompare(venue) == .orderedSame
            }
            rows.append(WatchCourseRowPresentation(
                course: course,
                title: venue,
                subtitle: nearbyVenueSubtitle(segments: segments, representative: course),
                isCached: cachedCourseIds.contains(course.globalId)
            ))
        }
        return rows
    }

    private func venueName(for course: WatchCourseOption) -> String {
        let explicit = course.venueName?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let explicit, !explicit.isEmpty { return explicit }
        return course.name.components(separatedBy: " ~ ").first?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? course.name
    }

    private func nearbyVenueSubtitle(
        segments: [WatchCourseOption],
        representative: WatchCourseOption
    ) -> String {
        let structure: String
        if segments.count > 1, segments.allSatisfy({ $0.playableHoleCount == 9 }) {
            structure = "\(segments.count) 个 9 洞组"
        } else if segments.count > 1 {
            structure = "\(segments.count) 个洞组"
        } else {
            structure = "\(representative.playableHoleCount) 洞"
        }
        guard let distance = nearbyDistance(to: representative),
              let label = WatchCourseProximity.distanceLabel(distance) else {
            return structure
        }
        return "\(structure) · \(label)"
    }

    private func searchResultSubtitle(_ match: WatchCourseSearchMatch) -> String {
        let location = [match.city, match.province]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .reduce(into: [String]()) { values, value in
                if !values.contains(where: { $0.caseInsensitiveCompare(value) == .orderedSame }) {
                    values.append(value)
                }
            }
            .joined(separator: " · ")
        let holeText = match.holes.flatMap { $0 > 0 ? "\($0) 洞" : nil } ?? "洞数未知"
        return location.isEmpty ? holeText : "\(location) · \(holeText)"
    }
}
