import SwiftUI

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
    public let installedGlobalIds: Set<Int>
    public let retainedDownloads: [PrepCourseDownloadRecord]
    public let onSearch: (String, String?) async throws -> [MobileCourseSearchMatch]
    public let onNearby: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]
    public let onSelect: (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void
    public let onOpenRetainedDownload: (PrepCourseDownloadRecord) -> Void
    public let onRetryRetainedDownload: (String) -> Void

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
    @State private var errorText: String?

    public init(
        locationProvider: LocationProvider,
        mode: MobileCourseSearchMode = .nearbyAndName,
        title: String? = nil,
        dismissAfterSelection: Bool = true,
        installedGlobalIds: Set<Int> = [],
        retainedDownloads: [PrepCourseDownloadRecord] = [],
        onSearch: @escaping (String, String?) async throws -> [MobileCourseSearchMatch],
        onNearby: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch],
        onSelect: @escaping (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void,
        onOpenRetainedDownload: @escaping (PrepCourseDownloadRecord) -> Void = { _ in },
        onRetryRetainedDownload: @escaping (String) -> Void = { _ in }
    ) {
        self.locationProvider = locationProvider
        self.mode = mode
        self.title = title ?? (mode == .nameOnly ? "搜索备战球场" : "找球场")
        self.dismissAfterSelection = dismissAfterSelection
        self.installedGlobalIds = installedGlobalIds
        self.retainedDownloads = retainedDownloads
        self.onSearch = onSearch
        self.onNearby = onNearby
        self.onSelect = onSelect
        self.onOpenRetainedDownload = onOpenRetainedDownload
        self.onRetryRetainedDownload = onRetryRetainedDownload
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
                        Task { await searchNearby() }
                    } label: {
                        HStack(spacing: 8) {
                            if activeSearch == .nearby {
                                ProgressView()
                            } else {
                                Image(systemName: "location.fill")
                            }
                            Text(activeSearch == .nearby
                                ? "正在查找"
                                : (hasNearbyLocation ? "查看附近球场" : "正在定位…"))
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(LiveHoleStyle.green)
                    .disabled(!canSearchNearby)
                    .accessibilityIdentifier("course-catalog-nearby-action")
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

            if !retainedDownloads.isEmpty {
                Section {
                    ForEach(retainedDownloads) { download in
                        retainedDownloadRow(download)
                    }
                } header: {
                    Text("最近选择")
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
                        let download = retainedDownloads.first {
                            $0.course.globalId == match.globalId
                        }
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
                                        Text(searchResultStatus(
                                            isInstalled: isInstalled,
                                            download: download
                                        ))
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

    @ViewBuilder
    private func retainedDownloadRow(_ download: PrepCourseDownloadRecord) -> some View {
        HStack(spacing: 10) {
            Button {
                onOpenRetainedDownload(download)
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: download.phase == .ready ? "checkmark.circle.fill" : "flag.fill")
                        .foregroundStyle(download.phase == .ready ? .secondary : LiveHoleStyle.green)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(download.course.name)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.primary)
                        Text(downloadStatus(download))
                            .font(.caption)
                            .foregroundStyle(download.phase == .failed ? .orange : .secondary)
                        if download.phase == .downloading || download.phase == .preparing {
                            ProgressView(value: download.phase == .preparing
                                ? Double(download.preparedHoles) / Double(max(download.totalHoles, 1))
                                : download.progressFraction)
                                .tint(LiveHoleStyle.green)
                        }
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            Spacer(minLength: 4)
            if download.phase == .failed {
                Button {
                    onRetryRetainedDownload(download.id)
                } label: {
                    Label("下载", systemImage: "arrow.down.circle")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("prep-download-retry-\(download.course.globalId)")
            } else if download.isActive {
                ProgressView()
                    .controlSize(.small)
                    .accessibilityLabel("下载中")
            } else {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
        }
        .accessibilityIdentifier("prep-download-row-\(download.course.globalId)")
    }

    private func downloadStatus(_ download: PrepCourseDownloadRecord) -> String {
        switch download.phase {
        case .queued:
            return "等待下载"
        case .preparing:
            return "准备精确地图 \(download.preparedHoles)/\(download.totalHoles) 洞"
        case .downloading:
            return "已保存 \(download.downloadedHoles)/\(download.totalHoles) 洞"
        case .ready:
            return "已完整下载到本机"
        case .failed:
            return download.errorText ?? "下载中断，可继续"
        }
    }

    private func searchResultStatus(
        isInstalled: Bool,
        download: PrepCourseDownloadRecord?
    ) -> String {
        if isInstalled || download?.phase == .ready { return "已准备" }
        guard let download else { return "选择后下载" }
        switch download.phase {
        case .queued: return "等待下载"
        case .preparing: return "准备中 \(download.preparedHoles)/\(download.totalHoles)"
        case .downloading: return "下载中 \(download.downloadedHoles)/\(download.totalHoles)"
        case .ready: return "已准备"
        case .failed: return "可继续下载"
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
        guard let nearbyLatitude = locationProvider.latestFix?.coordinate.latitude,
              let nearbyLongitude = locationProvider.latestFix?.coordinate.longitude else { return false }
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
        focusedField = nil
        activeSearch = .manual
        lastSearch = .manual
        didSearch = true
        errorText = nil
        defer { activeSearch = nil }
        do {
            var seen = Set<Int>()
            let hasKeyword = trimmedQuery.count >= 2
            let results = try await onSearch(
                hasKeyword ? trimmedQuery : trimmedCity,
                hasKeyword && trimmedCity.count >= 2 ? trimmedCity : nil
            )
            matches = results.filter { seen.insert($0.globalId).inserted }
        } catch {
            matches = []
            errorText = "现在无法搜索球场，请检查网络后重试。"
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

}
