import SwiftUI

/// 备战入口：既可以按城市／球场名搜索，也可以直接查看当前位置附近球场。选中结果后
/// 立即进入赛前攻略；下载归 App 级队列所有，离开本页不会丢掉进度。
public struct PrepCoursePickerView: View {
    public let courseOptions: [MobileCourseOption]
    public let downloadedCourseOptions: [MobileCourseOption]
    public let downloads: [PrepCourseDownloadRecord]
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let offlineStore: OfflineStore?
    public let onDownload: (MobileCourseOption) -> Void
    public let onRetryDownload: (String) -> Void

    /// `MobileCourseSearchView` owns the shared catalogue-search UI; this screen owns only the
    /// short-lived location provider used to request an explicit nearby search.
    @StateObject private var locationProvider = LocationProvider()
    @State private var selectedCourse: MobileCourseOption?
    /// `RoundHomeView` is already in a NavigationStack when this picker is pushed. SwiftUI can keep
    /// that destination's value-type inputs at their navigation-time snapshot even though the app
    /// model has synchronously created and persisted a new queue record. Keep only the unacknowledged
    /// selection intents here so returning from the detail screen shows the download immediately;
    /// the published app-owned records replace them as soon as they reach this destination.
    @State private var pendingDownloadIntents: [PrepCourseDownloadRecord] = []

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
            mode: .nearbyAndName,
            title: "备战球场",
            dismissAfterSelection: false,
            installedGlobalIds: Set(
                downloadedCourseOptions.map(\.globalId)
                    + visibleDownloads.filter { $0.phase == .ready }.map { $0.course.globalId }
            ),
            retainedDownloads: visibleDownloads,
            onSearch: searchCourses,
            onNearby: nearbyCourses,
            onSelect: selectSearchResult,
            onOpenRetainedDownload: openRetainedDownload,
            onRetryRetainedDownload: onRetryDownload
        )
        .onAppear {
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onDisappear {
            locationProvider.stopUpdatingLocation()
        }
        .onChange(of: downloads.map(\.id)) { _, authoritativeIDs in
            let acknowledged = Set(authoritativeIDs)
            pendingDownloadIntents.removeAll { acknowledged.contains($0.id) }
        }
        .navigationDestination(isPresented: selectedCoursePresented) {
            if let course = selectedCourse, let apiBaseURL {
                CourseReviewView(
                    client: SyncClient(baseURL: apiBaseURL, adminToken: adminToken),
                    globalId: course.globalId,
                    holeCount: course.resolvedHoles,
                    teeBox: course.teeBox,
                    offlineStore: offlineStore,
                    // `onDownload` updates the app-owned queue on the next published render. The
                    // destination must nevertheless enter managed-download mode on its FIRST frame;
                    // otherwise it briefly starts the standalone network loader, that task is then
                    // cancelled when the queue row arrives, and the player sees a false “加载失败”.
                    download: selectedDownload(for: course)
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

    private func searchCourses(
        _ name: String,
        _ city: String?
    ) async throws -> [MobileCourseSearchMatch] {
        guard let apiBaseURL else { throw URLError(.notConnectedToInternet) }
        return try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).searchCourses(
            name: name,
            city: city
        )
    }

    private func nearbyCourses(
        _ latitude: Double,
        _ longitude: Double,
        _ radiusKm: Int
    ) async throws -> [MobileCourseSearchMatch] {
        guard let apiBaseURL else { throw URLError(.notConnectedToInternet) }
        return try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).nearbyCourses(
            latitude: latitude,
            longitude: longitude,
            radiusKm: radiusKm
        )
    }

    private func selectSearchResult(
        _ selected: MobileCourseSearchMatch,
        _ matches: [MobileCourseSearchMatch]
    ) {
        _ = matches
        guard let course = resolvedOption(for: selected) else { return }
        let intent = queuedDownloadIntent(for: course)
        if !downloads.contains(where: { $0.id == intent.id }) {
            pendingDownloadIntents.removeAll { $0.id == intent.id }
            pendingDownloadIntents.insert(intent, at: 0)
        }
        onDownload(course)
        selectedCourse = course
    }

    private func openRetainedDownload(_ download: PrepCourseDownloadRecord) {
        if download.phase == .failed {
            onRetryDownload(download.id)
        }
        selectedCourse = download.course
    }

    /// Resolve the durable row when it has propagated, or use an equivalent queued snapshot for
    /// the short interval between selection and the app model's publication. Both have the same
    /// stable key, so the destination never changes loading ownership during navigation.
    private func selectedDownload(for course: MobileCourseOption) -> PrepCourseDownloadRecord {
        let queued = queuedDownloadIntent(for: course)
        return visibleDownloads.first(where: { $0.id == queued.id }) ?? queued
    }

    private func queuedDownloadIntent(for course: MobileCourseOption) -> PrepCourseDownloadRecord {
        let tee = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedTee = tee?.isEmpty == false ? tee! : "blue"
        return PrepCourseDownloadRecord(
            course: course,
            teeBox: resolvedTee,
            phase: .queued,
            totalHoles: course.resolvedHoles
        )
    }

    private var visibleDownloads: [PrepCourseDownloadRecord] {
        let authoritativeIDs = Set(downloads.map(\.id))
        return (downloads + pendingDownloadIntents.filter { !authoritativeIDs.contains($0.id) })
            .sorted { $0.updatedAt > $1.updatedAt }
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
