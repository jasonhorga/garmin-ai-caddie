import SwiftUI

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
        NavigationStack {
            List {
                if showRemoteSectionFirst {
                    remoteCourseSection
                }

                knownCourseSection

                if !showRemoteSectionFirst {
                    remoteCourseSection
                }

                if let errorMessage {
                    Section {
                        Text(errorMessage)
                            .font(.caption2)
                            .foregroundStyle(.orange)
                    }
                }

                Section {
                    Label(
                        phoneReachable ? "iPhone 已连接" : "已下载球场可离线开局",
                        systemImage: phoneReachable ? "iphone.radiowaves.left.and.right" : "applewatch"
                    )
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("AI Caddie")
            .searchable(text: $searchText, prompt: "搜索球场")
        }
    }

    private var knownCourseSection: some View {
        Section(knownCourseSectionTitle) {
            if filteredCourses.isEmpty {
                if isLoadingCourses {
                    ProgressView("正在获取球场")
                } else {
                    Text(searchText.isEmpty ? "暂无已知球场" : "已知球场中没有匹配")
                        .foregroundStyle(.secondary)
                }
            } else {
                ForEach(filteredCourses) { course in
                    courseButton(course, subtitle: nearbySubtitle(for: course))
                }
            }

            Button(action: onRefresh) {
                Label(isLoadingCourses ? "正在更新" : "更新已知球场", systemImage: "arrow.clockwise")
            }
            .disabled(isLoadingCourses || preparingCourseId != nil)
        }
    }

    private var remoteCourseSection: some View {
        Section("全部球场") {
            Button {
                onSearchAllCourses(trimmedSearchText)
            } label: {
                if isSearchingCourses {
                    HStack {
                        ProgressView()
                            .controlSize(.small)
                        Text("正在搜索")
                    }
                } else {
                    Label("搜索全部球场", systemImage: "magnifyingglass")
                }
            }
            .disabled(!canSearchAllCourses)

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
                VStack(alignment: .leading, spacing: 2) {
                    Text(match.name)
                        .font(.body.weight(.semibold))
                        .lineLimit(2)
                    Text(searchResultSubtitle(match))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 2)
                Image(systemName: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
                    .accessibilityLabel("洞数未知，无法开局")
            }
        }
    }

    @ViewBuilder
    private func courseButton(
        _ course: WatchCourseOption,
        subtitle: String? = nil,
        ensureGeometry: Bool = false
    ) -> some View {
        NavigationLink {
            WatchRoundSetupView(
                front: course,
                courses: allSelectableCourses,
                hasCachedVersion: cachedCourseIds.contains(course.globalId),
                isPreparing: preparingCourseId == course.globalId,
                errorMessage: errorMessage,
                ensureGeometry: ensureGeometry,
                onLoadTees: onLoadCourseTees,
                onStart: onStartCourse
            )
        } label: {
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(course.displayName)
                        .font(.body.weight(.semibold))
                        .lineLimit(2)
                    Text(subtitle ?? "\(course.playableHoleCount) 洞 · \(course.preferredTee)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 2)
                if preparingCourseId == course.globalId {
                    ProgressView()
                        .controlSize(.small)
                } else if cachedCourseIds.contains(course.globalId) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(AICaddieDesignTokens.par)
                        .accessibilityLabel("已下载，可离线")
                } else {
                    Image(systemName: "arrow.down.circle")
                        .foregroundStyle(.secondary)
                        .accessibilityLabel("需要下载")
                }
            }
        }
        .disabled(preparingCourseId != nil)
    }

    private var filteredCourses: [WatchCourseOption] {
        let query = trimmedSearchText
        let matches = query.isEmpty ? courses : courses.filter { course in
            [course.name, course.venueName, course.segmentLabel]
                .compactMap { $0 }
                .contains { $0.localizedCaseInsensitiveContains(query) }
        }
        guard let currentLatitude, let currentLongitude else { return matches }
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

    private var knownCourseSectionTitle: String {
        let locatedCount = filteredCourses.filter { nearbyDistance(to: $0) != nil }.count
        guard locatedCount > 0 else { return "选择球场" }
        return locatedCount == filteredCourses.count ? "附近球场" : "附近/已知球场"
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
