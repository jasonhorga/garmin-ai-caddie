import SwiftUI

/// iPhone entry to Garmin's full CourseView catalogue. Search is deliberately explicit rather than
/// firing on every keystroke; the result list is metadata-only and selecting a row does not install
/// every match.
public struct MobileCourseSearchView: View {
    public let onSearch: (String) async throws -> [MobileCourseSearchMatch]
    public let onSelect: (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var city = ""
    @State private var query = ""
    @State private var matches: [MobileCourseSearchMatch] = []
    @State private var isSearching = false
    @State private var didSearch = false
    @State private var errorText: String?

    public init(
        onSearch: @escaping (String) async throws -> [MobileCourseSearchMatch],
        onSelect: @escaping (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void
    ) {
        self.onSearch = onSearch
        self.onSelect = onSelect
    }

    public var body: some View {
        List {
            Section {
                TextField("城市（例如：深圳）", text: $city)
                    .textContentType(.addressCity)
                    .submitLabel(.search)
                    .onSubmit { submitSearch() }

                TextField("球场关键字（可选）", text: $query)
                    .submitLabel(.search)
                    .onSubmit { submitSearch() }

                Button {
                    Task { await search() }
                } label: {
                    HStack(spacing: 8) {
                        if isSearching {
                            ProgressView()
                        } else {
                            Image(systemName: "magnifyingglass")
                        }
                        Text(isSearching ? "正在搜索" : "搜索 Garmin 全部球场")
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
                        description: Text("换一个城市或中文／英文球场关键字再试。")
                    )
                }
            }

            if !matches.isEmpty {
                Section("搜索结果") {
                    ForEach(matches) { match in
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
        (trimmedQuery.count >= 2 || trimmedCity.count >= 2) && !isSearching
    }

    private func submitSearch() {
        guard canSearch else { return }
        Task { await search() }
    }

    @MainActor
    private func search() async {
        guard canSearch else { return }
        isSearching = true
        didSearch = true
        errorText = nil
        defer { isSearching = false }
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
