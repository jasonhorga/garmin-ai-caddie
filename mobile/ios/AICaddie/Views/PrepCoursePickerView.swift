import SwiftUI

/// 备战入口：既可以按城市／球场名搜索，也可以直接查看当前位置附近球场。
/// 选了就进（README §8）：选中的球场加入 App 级下载库并继续在后台下载，同时立即进入赛前攻略；
/// 未就绪的洞按地图降级契约显示，进入前不再弹任何地图准备提示。
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
    public let onLoadCourseTees: (Int) async -> [CourseTee]

    /// `MobileCourseSearchView` owns the shared catalogue-search UI; this screen owns only the
    /// short-lived location provider used to request an explicit nearby search.
    @StateObject private var locationProvider = LocationProvider()
    @ObservedObject private var downloadPresentation: PrepCourseDownloadPresentationState
    @State private var selectedCourse: MobileCourseOption?

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
        onValidateReadyDownload: @escaping (PrepCourseDownloadRecord) async -> Bool = { _ in true },
        onLoadCourseTees: @escaping (Int) async -> [CourseTee] = { _ in [] }
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
        self.onLoadCourseTees = onLoadCourseTees
    }

    public var body: some View {
        MobileCourseSearchView(
            locationProvider: locationProvider,
            mode: .nearbyAndName,
            title: "备战球场",
            dismissAfterSelection: false,
            installedGlobalIds: [],
            installedCourseKeys: installedCourseKeys,
            knownCourseOptions: courseOptions + downloadedCourseOptions,
            retainedDownloads: visibleDownloads,
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
                    // destination must nevertheless observe that durable row from its FIRST frame,
                    // so it resolves an equivalent queued snapshot until the row is published.
                    download: selectedDownload(for: course),
                    courseTees: course.tees ?? [],
                    onLoadCourseTees: onLoadCourseTees,
                    onChangeTee: changeTee
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
        // 选了就进 (README §8): the catalogue hit joins the app-owned library, whose download keeps
        // running (and survives relaunch) there, and the prep map opens at once. The destination
        // only reads what is installed; holes that are not ready follow the map degradation contract.
        onDownload(course)
        open(course)
    }

    private func openRetainedDownload(_ download: PrepCourseDownloadRecord) {
        guard !download.isTerminalFailure else { return }
        // A failed row, or a ready row whose files are no longer complete (an interrupted cleanup or
        // a renderer-version change), resumes its download; the prep map opens either way.
        if download.phase == .failed
            || (download.phase == .ready && !installedCourseKeys.contains(download.id)) {
            onRetryDownload(download.id)
        }
        open(download.course.replacingTeeBox(download.teeBox))
    }

    /// 右上换发球台: the other Tee is its own durable library row (its own download and template);
    /// the open prep screen keeps its hole and follows the new Tee's facts as they install.
    private func changeTee(_ tee: String) {
        guard let course = selectedCourse else { return }
        let trimmed = tee.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              downloadID(for: course) != downloadID(for: course.replacingTeeBox(trimmed)) else { return }
        let next = course.replacingTeeBox(trimmed)
        onDownload(next)
        open(next)
    }

    private func open(_ course: MobileCourseOption) {
        selectedCourse = course
        revalidateIfInstalled(course)
    }

    /// A complete local package opens at once and is checked against the server's current Garmin
    /// release in the background — never before navigation. A positive revision mismatch re-queues
    /// the row with its required revisions: the open prep screen then shows those holes on their
    /// factual route (the replaced topo is withheld) until the new precise maps install and replace
    /// them in place. An unreachable server keeps the verified local package, as before.
    private func revalidateIfInstalled(_ course: MobileCourseOption) {
        let id = downloadID(for: course)
        guard installedCourseKeys.contains(id) else { return }
        let record = downloads.first(where: { $0.id == id }) ?? readyDownloadIntent(for: course)
        guard record.phase == .ready else { return }
        Task { @MainActor in
            _ = await onValidateReadyDownload(record)
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
            teeBox: tee?.isEmpty == false ? tee! : "blue"
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
        return StartRoundView.reconciledCourseOption(
            provider: provider,
            catalogue: courseOptions.first { $0.globalId == match.globalId },
            downloaded: downloadedCourseOptions.first { $0.globalId == match.globalId }
        )
    }
}
