import SwiftUI

/// iPhone entry to Garmin's full CourseView catalogue. Search is deliberately explicit rather than
/// firing on every keystroke; the result list is metadata-only and selecting a row does not install
/// every match.
public struct MobileCourseSearchView: View {
    public let nearbyLatitude: Double?
    public let nearbyLongitude: Double?
    public let installedGlobalIds: Set<Int>
    public let onSearch: (String) async throws -> [MobileCourseSearchMatch]
    public let onNearby: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]
    public let onSelect: (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void

    private enum SearchKind: Equatable {
        case nearby
        case manual
    }

    @Environment(\.dismiss) private var dismiss
    @State private var city = ""
    @State private var query = ""
    @State private var nearbyRadiusKm = 50
    @State private var matches: [MobileCourseSearchMatch] = []
    @State private var activeSearch: SearchKind?
    @State private var lastSearch: SearchKind?
    @State private var didSearch = false
    @State private var errorText: String?

    public init(
        nearbyLatitude: Double? = nil,
        nearbyLongitude: Double? = nil,
        installedGlobalIds: Set<Int> = [],
        onSearch: @escaping (String) async throws -> [MobileCourseSearchMatch],
        onNearby: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch],
        onSelect: @escaping (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void
    ) {
        self.nearbyLatitude = nearbyLatitude
        self.nearbyLongitude = nearbyLongitude
        self.installedGlobalIds = installedGlobalIds
        self.onSearch = onSearch
        self.onNearby = onNearby
        self.onSelect = onSelect
    }

    public var body: some View {
        List {
            Section {
                Picker("搜索范围", selection: $nearbyRadiusKm) {
                    Text("50 km").tag(50)
                    Text("100 km").tag(100)
                    Text("200 km").tag(200)
                }
                .pickerStyle(.segmented)

                Button {
                    Task { await searchNearby() }
                } label: {
                    HStack(spacing: 8) {
                        if activeSearch == .nearby {
                            ProgressView()
                        } else {
                            Image(systemName: "location.fill")
                        }
                        Text(activeSearch == .nearby ? "正在查找" : "查找当前位置附近球场")
                        Spacer()
                    }
                }
                .disabled(!canSearchNearby)
                .accessibilityIdentifier("course-catalog-nearby-action")
            } header: {
                Text("附近球场")
            } footer: {
                Text(hasNearbyLocation
                    ? "直接读取 Garmin 在所选半径内的完整球场目录，并按真实距离排序。"
                    : "正在获取当前位置；你仍然可以先用下面的城市或球场名搜索。")
            }

            Section {
                TextField("城市（例如：深圳）", text: $city)
                    .textContentType(.addressCity)
                    .submitLabel(.search)
                    .onSubmit { submitSearch() }

                TextField("球场关键字（例如：观澜）", text: $query)
                    .submitLabel(.search)
                    .onSubmit { submitSearch() }

                Button {
                    Task { await search() }
                } label: {
                    HStack(spacing: 8) {
                        if activeSearch == .manual {
                            ProgressView()
                        } else {
                            Image(systemName: "magnifyingglass")
                        }
                        Text(activeSearch == .manual ? "正在搜索" : "搜索 Garmin 全部球场")
                        Spacer()
                    }
                }
                .disabled(!canSearch)
                .accessibilityIdentifier("course-catalog-search-action")
            } header: {
                Text("搜索条件")
            } footer: {
                Text("可以只填城市、只填球场关键字，或两项都填。搜索只取目录；选择后才下载这一座球场。")
            }

            if let errorText {
                Section {
                    Label(errorText, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                }
            }

            if didSearch, matches.isEmpty, errorText == nil {
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
                        let isInstalled = installedGlobalIds.contains(match.globalId)
                        Button {
                            guard match.courseOption != nil else { return }
                            onSelect(match, matches)
                            dismiss()
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: match.courseOption == nil ? "exclamationmark.triangle" : "flag.fill")
                                    .foregroundStyle(match.courseOption == nil ? .orange : LiveHoleStyle.green)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(match.name)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.primary)
                                    Text(match.subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 4)
                                if match.courseOption != nil {
                                    VStack(alignment: .trailing, spacing: 4) {
                                        Text(isInstalled ? "已准备" : "选择后下载")
                                            .font(.caption2.weight(.semibold))
                                            .foregroundStyle(isInstalled ? .secondary : LiveHoleStyle.green)
                                        Image(systemName: "chevron.right")
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(.tertiary)
                                    }
                                }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(match.courseOption == nil)
                        .accessibilityIdentifier("course-catalog-result-\(match.globalId)")
                        .accessibilityValue(isInstalled ? "已准备" : "选择后下载")
                    }
                }
            }
        }
        .navigationTitle("找球场")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
        }
    }

    private var trimmedQuery: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedCity: String {
        city.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSearch: Bool {
        (trimmedQuery.count >= 2 || trimmedCity.count >= 2) && activeSearch == nil
    }

    private var hasNearbyLocation: Bool {
        guard let nearbyLatitude, let nearbyLongitude else { return false }
        return nearbyLatitude.isFinite && (-90...90).contains(nearbyLatitude)
            && nearbyLongitude.isFinite && (-180...180).contains(nearbyLongitude)
    }

    private var canSearchNearby: Bool {
        hasNearbyLocation && activeSearch == nil
    }

    private func submitSearch() {
        guard canSearch else { return }
        Task { await search() }
    }

    @MainActor
    private func search() async {
        guard canSearch else { return }
        activeSearch = .manual
        lastSearch = .manual
        didSearch = true
        errorText = nil
        defer { activeSearch = nil }
        do {
            var seen = Set<Int>()
            let results: [MobileCourseSearchMatch]
            if trimmedCity.count >= 2, trimmedQuery.count >= 2 {
                async let cityResults = onSearch(trimmedCity)
                async let keywordResults = onSearch(trimmedQuery)
                results = Self.intersection(
                    cityMatches: try await cityResults,
                    keywordMatches: try await keywordResults
                )
            } else {
                results = try await onSearch(trimmedQuery.count >= 2 ? trimmedQuery : trimmedCity)
            }
            matches = results.filter { seen.insert($0.globalId).inserted }
        } catch {
            matches = []
            errorText = "现在无法搜索全部球场，请检查网络后重试。"
        }
    }

    @MainActor
    private func searchNearby() async {
        guard canSearchNearby, let nearbyLatitude, let nearbyLongitude else { return }
        activeSearch = .nearby
        lastSearch = .nearby
        didSearch = true
        errorText = nil
        defer { activeSearch = nil }
        do {
            var seen = Set<Int>()
            matches = try await onNearby(
                nearbyLatitude,
                nearbyLongitude,
                nearbyRadiusKm
            ).filter { seen.insert($0.globalId).inserted }
        } catch {
            matches = []
            errorText = "现在无法读取附近球场，请检查网络或改用名称搜索。"
        }
    }

    /// Garmin accepts a city or a course keyword, but mixed Chinese city/name text is not a stable
    /// provider query. Query each independently and intersect by factual globalId instead.
    static func intersection(
        cityMatches: [MobileCourseSearchMatch],
        keywordMatches: [MobileCourseSearchMatch]
    ) -> [MobileCourseSearchMatch] {
        let cityIds = Set(cityMatches.map(\.globalId))
        return keywordMatches.filter { cityIds.contains($0.globalId) }
    }
}
