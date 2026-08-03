import SwiftUI

struct WatchCourseRowPresentation: Equatable, Identifiable {
    var id: String { "\(course.globalId):\(course.segmentLabel ?? course.name)" }

    let course: WatchCourseOption
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

/// Home-before-a-round. Every production path starts from a real course; downloaded rows remain
/// available with no phone or network, while unavailable course data stays unavailable.
public struct WatchStartView: View {
    public let phoneReachable: Bool
    public let courses: [WatchCourseOption]
    public let searchMatches: [WatchCourseSearchMatch]
    public let cachedCourseIds: Set<Int>
    public let isLoadingCourses: Bool
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

    public init(
        phoneReachable: Bool,
        courses: [WatchCourseOption] = [],
        searchMatches: [WatchCourseSearchMatch] = [],
        cachedCourseIds: Set<Int> = [],
        isLoadingCourses: Bool = false,
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
        self.searchMatches = searchMatches
        self.cachedCourseIds = cachedCourseIds
        self.isLoadingCourses = isLoadingCourses
        self.isSearchingCourses = isSearchingCourses
        self.preparingCourseId = preparingCourseId
        self.errorMessage = errorMessage
        self.currentLatitude = currentLatitude
        self.currentLongitude = currentLongitude
        self.onRefresh = onRefresh
        self.onSearchAllCourses = onSearchAllCourses
        self.onLoadCourseTees = onLoadCourseTees
        self.onStartCourse = onStartCourse
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
            } else {
                coursePicker
            }
        }
        .persistentSystemOverlays(.hidden)
    }

    private var coursePicker: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if showRemoteSectionFirst {
                    remoteCourseSection
                }

                courseSections

                if !showRemoteSectionFirst {
                    remoteCourseSection
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 9, weight: .medium))
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
                .font(.system(size: 8, weight: .medium))
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8)
            .padding(.top, 8)
            .padding(.bottom, 6)
        }
        .ignoresSafeArea(edges: [.top, .leading, .trailing])
        .scrollIndicators(.hidden)
    }

    @ViewBuilder
    private var courseSections: some View {
        ForEach(courseGroups) { group in
            VStack(alignment: .leading, spacing: 4) {
                sectionHeader(group.title)
                    .padding(.bottom, 3.5)

                if group.rows.isEmpty {
                    if isLoadingCourses {
                        HStack(spacing: 5) {
                            ProgressView().controlSize(.small)
                            Text("正在获取球场")
                        }
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.secondary)
                        .padding(7)
                    } else {
                        Text(searchText.isEmpty ? "暂无已知球场" : "已知球场中没有匹配")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.secondary)
                            .padding(7)
                    }
                }

                ForEach(group.rows) { row in
                    courseButton(row)
                }

                if group.showsRefresh {
                    refreshCoursesButton
                        .padding(.top, 4)
                }
            }
        }
    }

    private var refreshCoursesButton: some View {
        Button(action: onRefresh) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.clockwise")
                Text(isLoadingCourses ? "正在更新" : "刷新球场")
                Spacer(minLength: 0)
            }
            .font(.system(size: 11, weight: .semibold))
            .padding(7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.white.opacity(0.06))
            )
        }
        .buttonStyle(.plain)
        .disabled(isLoadingCourses || preparingCourseId != nil)
    }

    private var remoteCourseSection: some View {
        VStack(alignment: .leading, spacing: 5) {
            sectionHeader("全部球场")

            TextField("输入球场名称", text: $searchText)
                .font(.system(size: 11, weight: .medium))
                .textFieldStyle(.plain)
                .submitLabel(.search)
                .padding(.horizontal, 8)
                .frame(maxWidth: .infinity, minHeight: 34, alignment: .leading)
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
                        Text("搜索全部球场")
                        Spacer(minLength: 0)
                    }
                }
            }
            .font(.system(size: 11, weight: .semibold))
            .padding(7)
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
                Text("搜索结果已在已知球场中")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
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
                        .font(.system(size: 13, weight: .semibold))
                        .lineLimit(2)
                    Text(searchResultSubtitle(match))
                        .font(.system(size: 9, weight: .medium))
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
            .frame(maxWidth: .infinity, minHeight: 45, alignment: .leading)
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
                    Text(row.course.displayName)
                        .font(.system(size: 14, weight: .semibold))
                        .lineLimit(2)
                        .minimumScaleFactor(0.78)
                    Text(row.subtitle)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 2)
                if preparingCourseId == row.course.globalId {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Image(systemName: "chevron.forward")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
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
        var groups: [WatchCourseGroupPresentation] = []

        if hasCurrentLocation, !nearbyCourses.isEmpty {
            groups.append(
                WatchCourseGroupPresentation(
                    title: "附近球场",
                    rows: nearbyCourses.map {
                        courseRow($0, subtitle: nearbySubtitle(for: $0))
                    },
                    showsRefresh: knownCourses.isEmpty
                )
            )
        }

        if !hasCurrentLocation || !knownCourses.isEmpty || nearbyCourses.isEmpty {
            let rows = knownCourses.map { courseRow($0) }
            if !rows.isEmpty || visibleSearchMatches.isEmpty {
                groups.append(
                    WatchCourseGroupPresentation(
                        title: hasCurrentLocation ? "已知球场" : "选择球场",
                        rows: rows,
                        showsRefresh: true
                    )
                )
            }
        }

        return groups
    }

    private func courseRow(
        _ course: WatchCourseOption,
        subtitle: String? = nil
    ) -> WatchCourseRowPresentation {
        WatchCourseRowPresentation(
            course: course,
            subtitle: subtitle ?? standardSubtitle(for: course),
            isCached: cachedCourseIds.contains(course.globalId)
        )
    }

    private func standardSubtitle(for course: WatchCourseOption) -> String {
        "\(course.playableHoleCount) 洞 · \(course.preferredTee)"
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 15, weight: .bold))
            .foregroundStyle(.primary)
            .padding(.horizontal, 2)
    }

    private var filteredCourses: [WatchCourseOption] {
        let query = trimmedSearchText
        let matches = query.isEmpty ? courses : courses.filter { course in
            [course.name, course.venueName, course.segmentLabel]
                .compactMap { $0 }
                .contains { $0.localizedCaseInsensitiveContains(query) }
        }
        guard hasCurrentLocation,
              let currentLatitude,
              let currentLongitude else { return matches }
        return WatchCourseProximity.ranked(
            matches,
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

    private var showRemoteSectionFirst: Bool {
        !trimmedSearchText.isEmpty || isSearchingCourses || !searchMatches.isEmpty
    }

    private var hasCurrentLocation: Bool {
        guard let currentLatitude, let currentLongitude else { return false }
        return currentLatitude.isFinite && currentLongitude.isFinite
            && (-90...90).contains(currentLatitude)
            && (-180...180).contains(currentLongitude)
    }

    private var nearbyCourses: [WatchCourseOption] {
        guard hasCurrentLocation else { return [] }
        return filteredCourses.filter { course in
            guard let distance = nearbyDistance(to: course) else { return false }
            return WatchCourseProximity.isNearby(distanceM: distance)
        }
    }

    private var knownCourses: [WatchCourseOption] {
        guard hasCurrentLocation else { return filteredCourses }
        let nearbyIds = Set(nearbyCourses.map(\.globalId))
        return filteredCourses.filter { !nearbyIds.contains($0.globalId) }
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
