import SwiftUI

/// iPhone entry to Garmin's full CourseView catalogue. Search is deliberately explicit rather than
/// firing on every keystroke; the result list is metadata-only and selecting a row does not install
/// every match.
public struct MobileCourseSearchView: View {
    public let onSearch: (String) async throws -> [MobileCourseSearchMatch]
    public let onSelect: (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void

    @Environment(\.dismiss) private var dismiss
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
            } footer: {
                Text("搜索只获取球场名称和洞数；选择后只准备并下载这个球场。")
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
                        description: Text("换一个中文或英文球场名称再试。")
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
        .navigationTitle("搜索全部球场")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "输入球场名称")
        .onSubmit(of: .search) {
            guard canSearch else { return }
            Task { await search() }
        }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("取消") { dismiss() }
            }
        }
    }

    private var trimmedQuery: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSearch: Bool {
        trimmedQuery.count >= 2 && !isSearching
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
            matches = try await onSearch(trimmedQuery).filter { seen.insert($0.globalId).inserted }
        } catch {
            matches = []
            errorText = "现在无法搜索全部球场，请检查网络后重试。"
        }
    }
}
