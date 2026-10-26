import SwiftUI
import AICaddieDomain

public enum MobileCourseSearchMode: Equatable {
    /// On-course entry: GPS nearby first, with manual catalogue search as the fallback.
    case nearbyAndName
    /// Pre-round planning: the player already has a destination in mind, so search only.
    case nameOnly
}

/// iPhone entry to Garmin's full CourseView catalogue. Search is deliberately explicit rather than
/// firing on every keystroke; the result list is metadata-only and selecting a row does not install
/// every match.
public struct MobileCourseSearchView: View {
    @ObservedObject public var locationProvider: LocationProvider
    public let mode: MobileCourseSearchMode
    public let title: String
    public let dismissAfterSelection: Bool
    public let onSearch: (String, String?) async throws -> [MobileCourseSearchMatch]
    public let onNearby: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]
    public let onSelect: (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void

    private enum SearchKind: Equatable {
        case nearby
        case manual
    }

    private enum SearchField: Hashable {
        case city
        case query
    }

    @Environment(\.dismiss) private var dismiss
    @FocusState private var focusedField: SearchField?
    @State private var city = ""
    @State private var query = ""
    @State private var nearbyRadiusKm = 50
    @State private var matches: [MobileCourseSearchMatch] = []
    @State private var activeSearch: SearchKind?
    @State private var lastSearch: SearchKind?
    @State private var didSearch = false
    @State private var searchCompleted = false
    @State private var errorText: String?
    /// 开始一场: the last nearby request failed (shown only as a retry icon).
    @State private var nearbyFailed = false

    public init(
        locationProvider: LocationProvider,
        mode: MobileCourseSearchMode = .nearbyAndName,
        title: String? = nil,
        dismissAfterSelection: Bool = true,
        onSearch: @escaping (String, String?) async throws -> [MobileCourseSearchMatch],
        onNearby: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch],
        onSelect: @escaping (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void
    ) {
        self.locationProvider = locationProvider
        self.mode = mode
        self.title = title ?? "找球场"
        self.dismissAfterSelection = dismissAfterSelection
        self.onSearch = onSearch
        self.onNearby = onNearby
        self.onSelect = onSelect
    }

    public var body: some View {
        List {
            if mode == .nearbyAndName {
                Section {
                    Picker("搜索范围", selection: $nearbyRadiusKm) {
                        Text("50 km").tag(50)
                        Text("100 km").tag(100)
                        Text("200 km").tag(200)
                    }
                    .pickerStyle(.segmented)

                    Button {
                        focusedField = nil
                        Task { await searchNearby() }
                    } label: {
                        HStack(spacing: 8) {
                            if activeSearch == .nearby {
                                ProgressView()
                            } else {
                                Image(systemName: "location.fill")
                            }
                            Text(nearbyActionTitle)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(LiveHoleStyle.green)
                    .disabled(!canSearchNearby)
                    .accessibilityIdentifier("course-catalog-nearby-action")

                    if nearbyFailed && activeSearch == nil {
                        Button {
                            Task { await searchNearby() }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .frame(maxWidth: .infinity)
                        }
                        .disabled(!canSearchNearby)
                        .accessibilityLabel("重试")
                        .accessibilityIdentifier("course-catalog-retry-nearby")
                    }
                } header: {
                    Text("附近球场")
                }
            }

            Section {
                TextField("城市（例如：深圳）", text: $city)
                    .accessibilityIdentifier("course-catalog-city-field")
                    .textContentType(.addressCity)
                    .focused($focusedField, equals: .city)
                    .submitLabel(.search)
                    .onSubmit { submitSearch() }

                TextField("球场关键字（例如：观澜）", text: $query)
                    .accessibilityIdentifier("course-catalog-keyword-field")
                    .focused($focusedField, equals: .query)
                    .submitLabel(.search)
                    .onSubmit { submitSearch() }

                Button {
                    focusedField = nil
                    Task { await search() }
                } label: {
                    HStack(spacing: 8) {
                        if activeSearch == .manual {
                            ProgressView()
                        } else {
                            Image(systemName: "magnifyingglass")
                        }
                        Text(activeSearch == .manual ? "正在搜索" : "搜索")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(LiveHoleStyle.green)
                .disabled(!canSearch)
                .accessibilityIdentifier("course-catalog-search-action")
            } header: {
                Text("搜索球场")
            }

            if let errorText {
                Section {
                    Label(errorText, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                }
            }

            // `didSearch` is set before the async request starts so the button can immediately
            // reflect the active query. Empty results are a conclusion, not a loading state: do not
            // render the empty state until the request's defer has marked it complete.
            if Self.shouldShowEmptyState(
                didSearch: didSearch,
                searchCompleted: searchCompleted,
                isSearching: activeSearch != nil,
                hasMatches: !matches.isEmpty,
                hasError: errorText != nil || nearbyFailed
            ) {
                Section {
                    ContentUnavailableView(
                        "没有匹配结果",
                        systemImage: "map",
                        description: Text(lastSearch == .nearby
                            ? "扩大到 100 或 200 km，或者改用城市／球场关键字。"
                            : "换一个城市或中文／英文球场关键字再试。")
                    )
                }
            }

            if !matches.isEmpty {
                Section(lastSearch == .nearby ? "附近结果" : "搜索结果") {
                    ForEach(matches) { match in
                        Button {
                            guard match.courseOption != nil else { return }
                            onSelect(match, matches)
                            if dismissAfterSelection {
                                dismiss()
                            }
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: match.courseOption == nil ? "exclamationmark.triangle" : "flag.fill")
                                    .foregroundStyle(match.courseOption == nil ? .orange : LiveHoleStyle.green)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(displayName(for: match))
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.primary)
                                    Text(match.subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 4)
                                if match.courseOption != nil {
                                    // README §8: the player selects a course and enters; download,
                                    // preparation and install state stay out of the picker.
                                    Image(systemName: "chevron.right")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.tertiary)
                                }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(match.courseOption == nil)
                        .accessibilityIdentifier("course-catalog-result-\(match.globalId)")
                    }
                }
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if mode == .nearbyAndName && dismissAfterSelection {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
            }
        }
    }

    private var trimmedQuery: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func displayName(for match: MobileCourseSearchMatch) -> String {
        // Search/nearby responses are backend-reconciled. A downloaded or
        // historical row is metadata only and must not rename this result.
        return match.displayName
    }

    private var trimmedCity: String {
        city.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSearch: Bool {
        (trimmedQuery.count >= 2 || trimmedCity.count >= 2) && activeSearch == nil
    }

    private var hasNearbyLocation: Bool {
        guard let nearbyLatitude = locationProvider.latestFix?.coordinate.latitude,
              let nearbyLongitude = locationProvider.latestFix?.coordinate.longitude else { return false }
        return nearbyLatitude.isFinite && (-90...90).contains(nearbyLatitude)
            && nearbyLongitude.isFinite && (-180...180).contains(nearbyLongitude)
    }

    private var nearbyActionTitle: String {
        if activeSearch == .nearby { return "正在查找" }
        return "查看附近球场"
    }

    private var canSearchNearby: Bool {
        hasNearbyLocation && activeSearch == nil
    }

    private func submitSearch() {
        guard canSearch else { return }
        focusedField = nil
        Task { await search() }
    }

    @MainActor
    private func search() async {
        guard canSearch else { return }
        focusedField = nil
        activeSearch = .manual
        lastSearch = .manual
        didSearch = true
        searchCompleted = false
        errorText = nil
        nearbyFailed = false
        defer {
            activeSearch = nil
            searchCompleted = true
        }
        do {
            var seen = Set<Int>()
            let hasKeyword = trimmedQuery.count >= 2
            let results = try await onSearch(
                hasKeyword ? trimmedQuery : trimmedCity,
                // Garmin's city metadata is provider-localised and can disagree with the words a
                // player types (for example a Beijing course whose city field is a district). For
                // city-only discovery, search the catalogue with the city text itself; apply the
                // strict location guard only when it narrows an independent course keyword.
                hasKeyword && trimmedCity.count >= 2 ? trimmedCity : nil
            )
            matches = results.filter { seen.insert($0.globalId).inserted }
        } catch {
            matches = []
            errorText = Self.searchErrorMessage(error, nearby: false)
        }
    }

    @MainActor
    private func searchNearby() async {
        guard canSearchNearby,
              let nearbyLatitude = locationProvider.latestFix?.coordinate.latitude,
              let nearbyLongitude = locationProvider.latestFix?.coordinate.longitude else { return }
        focusedField = nil
        activeSearch = .nearby
        lastSearch = .nearby
        didSearch = true
        searchCompleted = false
        errorText = nil
        nearbyFailed = false
        defer {
            activeSearch = nil
            searchCompleted = true
        }
        do {
            var seen = Set<Int>()
            matches = try await onNearby(
                nearbyLatitude,
                nearbyLongitude,
                nearbyRadiusKm
            ).filter { seen.insert($0.globalId).inserted }
        } catch {
            matches = []
            nearbyFailed = true
        }
    }

    static func searchErrorMessage(_ error: Error, nearby: Bool) -> String {
        if case let SyncClientError.http(status, _) = error, status == 401 {
            return "Apple 登录已失效，请重新登录。"
        }
        if case let SyncClientError.http(status, _) = error, status == 403 {
            return "当前 Apple 账号无权访问球场目录。"
        }
        return nearby
            ? "现在无法读取附近球场，请检查网络或改用名称搜索。"
            : "现在无法搜索球场，请检查网络后重试。"
    }

    static func shouldShowEmptyState(
        didSearch: Bool,
        searchCompleted: Bool,
        isSearching: Bool,
        hasMatches: Bool,
        hasError: Bool
    ) -> Bool {
        didSearch && searchCompleted && !isSearching && !hasMatches && !hasError
    }

}
