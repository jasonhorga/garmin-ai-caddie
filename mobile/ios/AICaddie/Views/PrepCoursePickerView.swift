import SwiftUI

/// 备战入口：既可以按城市／球场名搜索，也可以直接查看当前位置附近球场。
/// 选中结果只会加入 App 级下载库；完整球场包安装完成前不会进入赛前攻略。
public struct PrepCoursePickerView: View {
    public let courseOptions: [MobileCourseOption]
    public let downloadedCourseOptions: [MobileCourseOption]
    public let downloadedCourseKeys: Set<String>
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let offlineStore: OfflineStore?
    public let onDownload: (MobileCourseOption) -> Void
    public let onRetryDownload: (String) -> Void
    public let onValidateReadyDownload: (PrepCourseDownloadRecord) async -> Bool

    /// `MobileCourseSearchView` owns the shared catalogue-search UI; this screen owns only the
    /// short-lived location provider used to request an explicit nearby search.
    @StateObject private var locationProvider = LocationProvider()
    @ObservedObject private var downloadPresentation: PrepCourseDownloadPresentationState
    @State private var selectedCourse: MobileCourseOption?
    @State private var validatingDownloadID: String?
    @State private var validationMessage: String?

    public init(
        courseOptions: [MobileCourseOption],
        downloadedCourseOptions: [MobileCourseOption] = [],
        downloadedCourseKeys: Set<String> = [],
        downloads: [PrepCourseDownloadRecord] = [],
        downloadPresentation: PrepCourseDownloadPresentationState? = nil,
        apiBaseURL: URL?,
        adminToken: String?,
        offlineStore: OfflineStore? = nil,
        onDownload: @escaping (MobileCourseOption) -> Void = { _ in },
        onRetryDownload: @escaping (String) -> Void = { _ in },
        onValidateReadyDownload: @escaping (PrepCourseDownloadRecord) async -> Bool = { _ in true }
    ) {
        self.courseOptions = courseOptions
        self.downloadedCourseOptions = downloadedCourseOptions
        self.downloadedCourseKeys = downloadedCourseKeys
        self._downloadPresentation = ObservedObject(
            wrappedValue: downloadPresentation
                ?? PrepCourseDownloadPresentationState(downloads: downloads)
        )
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.offlineStore = offlineStore
        self.onDownload = onDownload
        self.onRetryDownload = onRetryDownload
        self.onValidateReadyDownload = onValidateReadyDownload
    }

    public var body: some View {
        MobileCourseSearchView(
            locationProvider: locationProvider,
            mode: .nearbyAndName,
            title: "备战球场",
            dismissAfterSelection: false,
            installedGlobalIds: [],
            installedCourseKeys: installedCourseKeys,
            retainedDownloads: visibleDownloads,
            validatingDownloadID: validatingDownloadID,
            onSearch: searchCourses,
            onNearby: nearbyCourses,
            onSelect: selectSearchResult,
            onOpenRetainedDownload: openRetainedDownload,
            onRetryRetainedDownload: onRetryDownload,
            retainedDownloadKey: { match in
                guard let course = resolvedOption(for: match) else { return nil }
                return downloadID(for: course)
            }
        )
        .onAppear {
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onDisappear {
            locationProvider.stopUpdatingLocation()
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
        .alert("地图正在更新", isPresented: validationAlertPresented) {
            Button("知道了", role: .cancel) {}
        } message: {
            Text(validationMessage ?? "地图更新完成后即可进入备战。")
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

    private var validationAlertPresented: Binding<Bool> {
        Binding(
            get: { validationMessage != nil },
            set: { isPresented in
                if !isPresented { validationMessage = nil }
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
        let wasReady = installedCourseKeys.contains(downloadID(for: course))
        // A catalogue hit is metadata only.  Starting a download must not push a destination that
        // owns a second, page-scoped loader (and could therefore show a partial map or be cancelled
        // when the user navigates back).  Already-installed courses are the sole exception.
        onDownload(course)
        if wasReady {
            let record = visibleDownloads.first(where: { $0.id == downloadID(for: course) })
                ?? readyDownloadIntent(for: course)
            validateAndOpen(record)
        }
    }

    private func openRetainedDownload(_ download: PrepCourseDownloadRecord) {
        if download.phase == .failed {
            onRetryDownload(download.id)
        }
        // Keep queued/preparing/downloading rows in the library.  The only legal route into the
        // prep map is a complete, locally verified course package.
        if download.phase == .ready, installedCourseKeys.contains(download.id) {
            validateAndOpen(download)
        } else if download.phase == .ready {
            // A stale row can survive an interrupted file cleanup or a renderer-version change.
            // Re-queue it instead of exposing a map that is only complete on paper.
            onRetryDownload(download.id)
        }
    }

    private func validateAndOpen(_ download: PrepCourseDownloadRecord) {
        guard validatingDownloadID == nil else { return }
        validatingDownloadID = download.id
        Task { @MainActor in
            let isCurrent = await onValidateReadyDownload(download)
            guard validatingDownloadID == download.id else { return }
            validatingDownloadID = nil
            if isCurrent {
                selectedCourse = download.course
            } else if let failed = downloads.first(where: { $0.id == download.id })?.errorText,
                      !failed.isEmpty {
                validationMessage = failed
            } else {
                validationMessage = "地图尚未准备完成，下载完成后即可进入备战。"
            }
        }
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

    private func readyDownloadIntent(for course: MobileCourseOption) -> PrepCourseDownloadRecord {
        let tee = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedTee = tee?.isEmpty == false ? tee! : "blue"
        return PrepCourseDownloadRecord(
            course: course,
            teeBox: resolvedTee,
            phase: .ready,
            preparedHoles: course.resolvedHoles,
            downloadedHoles: course.resolvedHoles,
            totalHoles: course.resolvedHoles
        )
    }

    private func downloadID(for course: MobileCourseOption) -> String {
        let tee = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines)
        return PrepCourseDownloadRecord.key(
            globalId: course.globalId,
            teeBox: tee?.isEmpty == false ? tee! : "blue",
            nine: "all"
        )
    }

    private var visibleDownloads: [PrepCourseDownloadRecord] {
        downloads.sorted { $0.updatedAt > $1.updatedAt }
    }

    private var installedCourseKeys: Set<String> {
        downloadedCourseKeys
    }

    private var downloads: [PrepCourseDownloadRecord] {
        downloadPresentation.downloads
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
