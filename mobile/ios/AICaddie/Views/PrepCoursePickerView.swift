import SwiftUI

/// 备战入口与现场开局刻意分流：备战者已经知道准备去哪里，直接按城市/球场名搜索，
/// 选中结果后立即进入赛前攻略；不请求 GPS，也不展示附近或历史球场。
public struct PrepCoursePickerView: View {
    public let courseOptions: [MobileCourseOption]
    public let downloadedCourseOptions: [MobileCourseOption]
    public let downloads: [PrepCourseDownloadRecord]
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let offlineStore: OfflineStore?
    public let onDownload: (MobileCourseOption) -> Void
    public let onRetryDownload: (String) -> Void

    /// `MobileCourseSearchView` owns the shared catalogue-search UI. In `.nameOnly` mode this
    /// provider is never started and Core Location permission is never requested.
    @StateObject private var locationProvider = LocationProvider()
    @State private var selectedCourse: MobileCourseOption?

    public init(
        courseOptions: [MobileCourseOption],
        downloadedCourseOptions: [MobileCourseOption] = [],
        downloads: [PrepCourseDownloadRecord] = [],
        apiBaseURL: URL?,
        adminToken: String?,
        offlineStore: OfflineStore? = nil,
        onDownload: @escaping (MobileCourseOption) -> Void = { _ in },
        onRetryDownload: @escaping (String) -> Void = { _ in }
    ) {
        self.courseOptions = courseOptions
        self.downloadedCourseOptions = downloadedCourseOptions
        self.downloads = downloads
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.offlineStore = offlineStore
        self.onDownload = onDownload
        self.onRetryDownload = onRetryDownload
    }

    public var body: some View {
        MobileCourseSearchView(
            locationProvider: locationProvider,
            mode: .nameOnly,
            dismissAfterSelection: false,
            installedGlobalIds: Set(
                downloadedCourseOptions.map(\.globalId)
                    + downloads.filter { $0.phase == .ready }.map { $0.course.globalId }
            ),
            retainedDownloads: downloads,
            onSearch: searchCourses,
            onNearby: { _, _, _ in [] },
            onSelect: selectSearchResult,
            onOpenRetainedDownload: openRetainedDownload,
            onRetryRetainedDownload: onRetryDownload
        )
        .navigationDestination(isPresented: selectedCoursePresented) {
            if let course = selectedCourse, let apiBaseURL {
                CourseReviewView(
                    client: SyncClient(baseURL: apiBaseURL, adminToken: adminToken),
                    globalId: course.globalId,
                    holeCount: course.resolvedHoles,
                    teeBox: course.teeBox,
                    offlineStore: offlineStore,
                    download: downloads.first(where: { $0.course.globalId == course.globalId })
                )
            }
        }
    }

    private var selectedCoursePresented: Binding<Bool> {
        Binding(
            get: { selectedCourse != nil },
            set: { isPresented in
                if !isPresented {
                    selectedCourse = nil
                }
            }
        )
    }

    private func searchCourses(_ name: String) async throws -> [MobileCourseSearchMatch] {
        guard let apiBaseURL else { throw URLError(.notConnectedToInternet) }
        return try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).searchCourses(name: name)
    }

    private func selectSearchResult(
        _ selected: MobileCourseSearchMatch,
        _ matches: [MobileCourseSearchMatch]
    ) {
        _ = matches
        guard let course = resolvedOption(for: selected) else { return }
        onDownload(course)
        selectedCourse = course
    }

    private func openRetainedDownload(_ download: PrepCourseDownloadRecord) {
        if download.phase == .failed {
            onRetryDownload(download.id)
        }
        selectedCourse = download.course
    }

    private func resolvedOption(for match: MobileCourseSearchMatch) -> MobileCourseOption? {
        guard let provider = match.courseOption else { return nil }
        let knownOptions = courseOptions + downloadedCourseOptions
        guard let known = knownOptions.first(where: { $0.globalId == match.globalId }) else {
            return provider
        }
        return MobileCourseOption(
            globalId: provider.globalId,
            courseKey: known.courseKey,
            name: provider.name,
            roundCount: known.roundCount,
            latestRoundId: known.latestRoundId,
            latestRoundDate: known.latestRoundDate,
            templateRoundId: known.templateRoundId,
            suggestedLiveRoundId: known.suggestedLiveRoundId,
            holes: provider.holes,
            teeBox: known.teeBox,
            geometryCoverage: known.geometryCoverage,
            sourceRefs: known.sourceRefs,
            venueName: provider.venueName ?? known.venueName,
            segmentLabel: provider.segmentLabel ?? known.segmentLabel,
            segmentHoles: provider.segmentHoles ?? known.segmentHoles,
            latitude: provider.latitude ?? known.latitude,
            longitude: provider.longitude ?? known.longitude,
            tees: known.tees
        )
    }
}
