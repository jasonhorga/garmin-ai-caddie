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
    public let installedCourseKeys: Set<String>?
    public let retainedDownloads: [PrepCourseDownloadRecord]
    public let validatingDownloadID: String?
    public let onSearch: (String, String?) async throws -> [MobileCourseSearchMatch]
    public let onNearby: (Double, Double, Int) async throws -> [MobileCourseSearchMatch]
    public let onSelect: (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void
    public let onOpenRetainedDownload: (PrepCourseDownloadRecord) -> Void
    public let onRetryRetainedDownload: (String) -> Void
    /// Resolves a search row to the exact durable download identity selected by its parent.
    /// Search metadata intentionally does not contain a tee/nine choice, while one Garmin
    /// globalId can have several installed tee variants. A nil resolver falls back to the
    /// catalogue row's explicit tee (or the documented blue/all default).
    public let retainedDownloadKey: ((MobileCourseSearchMatch) -> String?)?

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
        installedCourseKeys: Set<String>? = nil,
        retainedDownloads: [PrepCourseDownloadRecord] = [],
        validatingDownloadID: String? = nil,
        onSearch: @escaping (String, String?) async throws -> [MobileCourseSearchMatch],
        onNearby: @escaping (Double, Double, Int) async throws -> [MobileCourseSearchMatch],
        onSelect: @escaping (MobileCourseSearchMatch, [MobileCourseSearchMatch]) -> Void,
        onOpenRetainedDownload: @escaping (PrepCourseDownloadRecord) -> Void = { _ in },
        onRetryRetainedDownload: @escaping (String) -> Void = { _ in },
        retainedDownloadKey: ((MobileCourseSearchMatch) -> String?)? = nil
    ) {
        self.locationProvider = locationProvider
        self.mode = mode
        self.title = title ?? (mode == .nameOnly ? "搜索备战球场" : "找球场")
        self.dismissAfterSelection = dismissAfterSelection
        self.installedGlobalIds = installedGlobalIds
        self.installedCourseKeys = installedCourseKeys
        self.retainedDownloads = retainedDownloads
        self.validatingDownloadID = validatingDownloadID
        self.onSearch = onSearch
        self.onNearby = onNearby
        self.onSelect = onSelect
        self.onOpenRetainedDownload = onOpenRetainedDownload
        self.onRetryRetainedDownload = onRetryRetainedDownload
        self.retainedDownloadKey = retainedDownloadKey
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
                } footer: {
                    Text("服务器会继续准备；iOS 若被系统挂起，回到前台会从已保存的洞继续。")
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
                        let isInstalled = courseIsInstalled(match.courseOption)
                        let download = retainedDownload(for: match)
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
        let verifiedReady = download.phase == .ready && retainedDownloadIsInstalled(download)
        let isValidating = validatingDownloadID == download.id
        let status = isValidating
            ? "正在确认地图版本"
            : downloadStatus(download, verifiedReady: verifiedReady)
        HStack(spacing: 10) {
            Button {
                onOpenRetainedDownload(download)
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: verifiedReady ? "checkmark.circle.fill" : "flag.fill")
                        .foregroundStyle(verifiedReady ? .secondary : LiveHoleStyle.green)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(download.course.name)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.primary)
                        Text(status)
                            .font(.caption)
                            .foregroundStyle(download.phase == .failed ? .orange : .secondary)
                            .accessibilityHidden(true)
                        if download.phase == .downloading || download.phase == .preparing {
                            ProgressView(value: download.phase == .preparing
                                ? Double(download.preparedHoles) / Double(max(download.totalHoles, 1))
                                : download.progressFraction)
                                .tint(LiveHoleStyle.green)
                        }
                    }
                    Spacer(minLength: 4)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(download.isActive || isValidating)
            // Keep the stable row id on the actual opening button. Applying it to the wrapping
            // HStack makes SwiftUI expose a synthetic button that can inherit the id but not the
            // opening action when a retry control is present beside it.
            .accessibilityIdentifier("prep-download-row-\(download.course.globalId)")
            .accessibilityLabel(download.course.name)
            .accessibilityValue(status)
            .accessibilityHint(download.isActive
                ? "正在下载，完成后可打开"
                : (isValidating ? "正在确认本地地图是否为最新版本" : "打开赛前攻略"))

            if download.phase == .failed || (download.phase == .ready && !verifiedReady) {
                Button {
                    onRetryRetainedDownload(download.id)
                } label: {
                    Label("下载", systemImage: "arrow.down.circle")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("prep-download-retry-\(download.course.globalId)")
            } else if download.isActive || isValidating {
                ProgressView()
                    .controlSize(.small)
                    .accessibilityLabel(isValidating ? "正在确认地图版本" : "下载中")
            } else {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
        }
    }

    private func downloadStatus(
        _ download: PrepCourseDownloadRecord,
        verifiedReady: Bool
    ) -> String {
        switch download.phase {
        case .queued:
            return "等待下载"
        case .preparing:
            return "准备精确地图 \(download.preparedHoles)/\(download.totalHoles) 洞"
        case .downloading:
            return "已保存 \(download.downloadedHoles)/\(download.totalHoles) 洞"
        case .ready:
            return verifiedReady ? "已完整下载到本机" : "本地文件不完整，可继续下载"
        case .failed:
            return download.errorText ?? "下载中断，可继续"
        }
    }

    private func searchResultStatus(
        isInstalled: Bool,
        download: PrepCourseDownloadRecord?
    ) -> String {
        if isInstalled { return "已准备" }
        guard let download else { return "选择后下载" }
        switch download.phase {
        case .queued: return "等待下载"
        case .preparing: return "准备中 \(download.preparedHoles)/\(download.totalHoles)"
        case .downloading: return "下载中 \(download.downloadedHoles)/\(download.totalHoles)"
        case .ready: return "需要重新下载"
        case .failed: return "可继续下载"
        }
    }

    private var trimmedQuery: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func courseIsInstalled(_ course: MobileCourseOption?) -> Bool {
        guard let course else { return false }
        if let installedCourseKeys {
            let tee = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
            return installedCourseKeys.contains(PrepCourseDownloadRecord.key(
                globalId: course.globalId,
                teeBox: tee?.isEmpty == false ? tee! : "blue",
                nine: "all"
            ))
        }
        return installedGlobalIds.contains(course.globalId)
    }

    private func retainedDownloadIsInstalled(_ download: PrepCourseDownloadRecord) -> Bool {
        if let installedCourseKeys {
            return installedCourseKeys.contains(download.id)
        }
        return installedGlobalIds.contains(download.course.globalId)
    }

    private func retainedDownload(for match: MobileCourseSearchMatch) -> PrepCourseDownloadRecord? {
        guard let course = match.courseOption else { return nil }
        let key = retainedDownloadKey?(match) ?? PrepCourseDownloadRecord.key(
            globalId: course.globalId,
            teeBox: course.teeBox ?? "blue",
            nine: "all"
        )
        return retainedDownloads.first { $0.id == key }
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
                // Garmin's city metadata is provider-localised and can disagree with the words a
                // player types (for example a Beijing course whose city field is a district). For
                // city-only discovery, search the catalogue with the city text itself; apply the
                // strict location guard only when it narrows an independent course keyword.
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
