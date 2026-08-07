import Combine
import Foundation

/// Owns the Watch's small, user-visible course library. Remote options are ephemeral; only a course
/// that has completed package + prep download is advertised as cached and can start with no config.
@MainActor
public final class WatchCourseLibrary: ObservableObject {
    @Published public private(set) var courses: [WatchCourseOption]
    /// Provider-wide rows around the Watch's current fix. This is the only list shown by the
    /// new-round picker; `courses` remains lookup/cache metadata and is never presented as history.
    @Published public private(set) var nearbyCourses: [WatchCourseOption] = []
    @Published public private(set) var searchMatches: [WatchCourseSearchMatch] = []
    @Published public private(set) var cachedCourseIds: Set<Int>
    @Published public private(set) var isLoadingCourses = false
    @Published public private(set) var isLoadingNearby = false
    @Published public private(set) var isSearchingCourses = false
    @Published public private(set) var preparingCourseId: Int?
    @Published public private(set) var errorMessage: String?
    public private(set) var diagnosticErrorMessage: String?

    private let store: WatchCourseStore
    private let imageStore: WatchHoleImageStore
    private let makeRoundId: () -> String
    private let now: () -> String

    public init(
        store: WatchCourseStore = WatchCourseStore(),
        imageStore: WatchHoleImageStore = WatchHoleImageStore(),
        makeRoundId: @escaping () -> String = { "watch-\(UUID().uuidString)" },
        now: @escaping () -> String = { ISO8601DateFormatter().string(from: Date()) }
    ) {
        self.store = store
        self.imageStore = imageStore
        self.makeRoundId = makeRoundId
        self.now = now
        let cached = store.loadCourses()
        courses = Self.uniqueOptions(from: cached.flatMap { [$0.option, $0.backOption].compactMap { $0 } })
        cachedCourseIds = Set(cached.map { $0.option.globalId })
    }

    public func refresh(config: WatchRoundConfig?) async {
        guard let config else {
            if courses.isEmpty {
                errorMessage = "请先在 iPhone 登录并同步一次"
            }
            return
        }
        isLoadingCourses = true
        defer { isLoadingCourses = false }
        do {
            let remote = try await makeClient(config).fetchCourseOptions()
            let cached = store.loadCourses()
            var merged = remote
            let cachedOptions = cached.flatMap { [$0.option, $0.backOption].compactMap { $0 } }
            for option in cachedOptions where !merged.contains(where: { $0.globalId == option.globalId }) {
                merged.append(option)
            }
            courses = Self.uniqueOptions(from: merged)
            cachedCourseIds = Set(cached.map { $0.option.globalId })
            errorMessage = nil
        } catch {
            errorMessage = courses.isEmpty
                ? "无法获取球场，请检查网络或登录状态"
                : "无法更新球场，已缓存球场仍可离线使用"
        }
    }

    /// Resolve Garmin's full catalogue around the current wrist location. Previously the Watch
    /// filtered only the player's historical/cached options, so a genuinely nearby new course could
    /// never appear. A failed network request may fall back to *nearby* cached rows, never to the
    /// complete history list.
    public func refreshNearby(
        latitude: Double,
        longitude: Double,
        radiusKm: Int = 50,
        config: WatchRoundConfig?
    ) async {
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              (1...200).contains(radiusKm) else {
            nearbyCourses = []
            errorMessage = "正在等待有效 GPS 定位"
            return
        }

        let cachedNearby = localNearbyCourses(
            latitude: latitude,
            longitude: longitude,
            radiusKm: radiusKm
        )
        guard let config else {
            nearbyCourses = cachedNearby
            errorMessage = cachedNearby.isEmpty ? "请先在 iPhone 登录并同步一次" : nil
            return
        }

        isLoadingNearby = true
        errorMessage = nil
        defer { isLoadingNearby = false }
        do {
            let matches = try await makeClient(config).nearbyCourses(
                latitude: latitude,
                longitude: longitude,
                radiusKm: radiusKm
            )
            var seen = Set<Int>()
            nearbyCourses = matches.compactMap { resolvedNearbyOption($0) }.filter {
                seen.insert($0.globalId).inserted
            }
            if nearbyCourses.isEmpty {
                errorMessage = "当前位置 \(radiusKm) km 内没有找到球场"
            }
        } catch {
            nearbyCourses = cachedNearby
            errorMessage = cachedNearby.isEmpty
                ? "无法读取附近球场，可改用名称搜索"
                : "无法更新附近球场，已显示本机附近缓存"
        }
    }

    public func searchAllCourses(name: String, config: WatchRoundConfig?) async {
        let query = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.count >= 2 else {
            searchMatches = []
            errorMessage = "请至少输入两个字再搜索全部球场"
            return
        }
        guard let config else {
            searchMatches = []
            errorMessage = "请先在 iPhone 登录并同步一次"
            return
        }

        isSearchingCourses = true
        searchMatches = []
        errorMessage = nil
        defer { isSearchingCourses = false }
        do {
            let matches = try await makeClient(config).searchCourses(name: query)
            var seen = Set<Int>()
            searchMatches = matches.filter { seen.insert($0.globalId).inserted }
            if searchMatches.isEmpty {
                errorMessage = "未返回匹配球场，请检查名称或稍后重试"
            }
        } catch {
            errorMessage = "无法搜索全部球场，请检查网络或登录状态"
        }
    }

    public func loadCourseTees(
        globalId: Int,
        config: WatchRoundConfig?
    ) async -> [WatchCourseTee] {
        guard let config else {
            errorMessage = "这个球场尚未下载，请联网后重试"
            diagnosticErrorMessage = errorMessage
            return []
        }
        diagnosticErrorMessage = nil
        do {
            let tees = try await makeClient(config).fetchCourseTees(globalId: globalId)
            errorMessage = tees.isEmpty ? "这个球场没有可用的发球台数据" : nil
            diagnosticErrorMessage = errorMessage
            return tees
        } catch {
            errorMessage = "无法获取发球台，请检查网络后重试"
            diagnosticErrorMessage = "\(errorMessage!): \(error.localizedDescription)"
            return []
        }
    }

    public func startCourse(
        _ option: WatchCourseOption,
        config: WatchRoundConfig?
    ) async -> WatchPreparedCourse? {
        await startCourse(
            WatchCourseSelection(front: option, teeBox: option.preferredTee),
            config: config
        )
    }

    public func startCourse(
        _ selection: WatchCourseSelection,
        config: WatchRoundConfig?
    ) async -> WatchPreparedCourse? {
        if let cached = store.course(globalId: selection.front.globalId), cached.matches(selection) {
            errorMessage = nil
            return cached.makeRound(roundId: makeRoundId())
        }
        guard let config else {
            errorMessage = "这个洞组和发球台尚未下载，请联网后重试"
            return nil
        }

        preparingCourseId = selection.front.globalId
        errorMessage = nil
        diagnosticErrorMessage = nil
        defer { preparingCourseId = nil }
        do {
            let roundId = makeRoundId()
            let download = try await fetchCourseDownload(
                selection,
                roundId: roundId,
                config: config,
                backgroundGeometry: selection.ensureGeometry
            )
            try persist(download)
            return download.template.makeRound(roundId: roundId)
        } catch {
            errorMessage = "球场下载失败，请保持联网后重试"
            diagnosticErrorMessage = "\(errorMessage!): \(error.localizedDescription)"
            return nil
        }
    }

    /// Continue the already-queued precise download without holding up play. The caller applies the
    /// returned map facts to the same round id; failures and service cooldowns retry at a bounded
    /// cadence while the task remains alive, and a later app entry can resume from the partial cache.
    public func upgradeCourseWhenReady(
        _ selection: WatchCourseSelection,
        roundId: String,
        config: WatchRoundConfig?
    ) async -> WatchPreparedCourse? {
        guard let config else { return nil }
        var delaySeconds: UInt64 = 5
        var shouldQueueGeometry = true

        while !Task.isCancelled {
            do {
                let download = try await fetchCourseDownload(
                    selection,
                    roundId: roundId,
                    config: config,
                    backgroundGeometry: shouldQueueGeometry
                )
                shouldQueueGeometry = false
                if Self.preciseDownloadReady(download) {
                    try persist(download)
                    errorMessage = nil
                    return download.template.makeRound(roundId: roundId)
                }
            } catch {
                // The lightweight template remains playable. Retry below instead of replacing the
                // screen with a transient network error during an active round.
            }

            do {
                try await Task.sleep(nanoseconds: delaySeconds * 1_000_000_000)
            } catch {
                return nil
            }
            delaySeconds = min(delaySeconds * 2, 60)
        }
        return nil
    }

    private func fetchCourseDownload(
        _ selection: WatchCourseSelection,
        roundId: String,
        config: WatchRoundConfig,
        backgroundGeometry: Bool
    ) async throws -> WatchCourseDownload {
        let client = makeClient(config)
        let package = try await client.fetchCoursePackage(
            globalId: selection.front.globalId,
            roundId: roundId,
            teeBox: selection.teeBox,
            backGlobalId: selection.back?.globalId,
            ensureGeometry: false,
            backgroundGeometry: backgroundGeometry
        )

        var requestedByGlobalId: [Int: Set<Int>] = [:]
        for hole in package.holes {
            let globalId = hole.sourceGlobalId ?? package.course.globalId
            let localHole = hole.sourceLocalHole ?? hole.number
            requestedByGlobalId[globalId, default: []].insert(localHole)
        }
        var preps: [Int: WatchCoursePrepResponse] = [:]
        var topoImages: [Int: [Int: Data]] = [:]
        for globalId in requestedByGlobalId.keys.sorted() {
            let localHoles = requestedByGlobalId[globalId, default: []].sorted()
            var prepParts: [WatchCoursePrepResponse] = []
            for start in stride(
                from: 0,
                to: localHoles.count,
                by: WatchBackendClient.maximumCoursePrepHolesPerRequest
            ) {
                let end = min(
                    start + WatchBackendClient.maximumCoursePrepHolesPerRequest,
                    localHoles.count
                )
                prepParts.append(try await client.fetchCoursePrep(
                    globalId: globalId,
                    localHoles: Array(localHoles[start..<end])
                ))
            }
            let prep = WatchCoursePrepResponse(
                globalId: globalId,
                clubs: prepParts.first?.clubs ?? [],
                holes: prepParts.flatMap(\.holes)
            )
            preps[globalId] = prep
            let readyHoles = Set(prep.holes.compactMap { hole in
                hole.geometryCoverage?.caseInsensitiveCompare("ready") == .orderedSame
                    ? hole.hole
                    : nil
            })
            for localHole in localHoles where readyHoles.contains(localHole) {
                if let data = try? await client.fetchCourseTopo(
                    globalId: globalId,
                    localHole: localHole
                ), !data.isEmpty {
                    topoImages[globalId, default: [:]][localHole] = data
                }
            }
        }

        return try WatchCourseTemplateBuilder.build(
            option: selection.front,
            backOption: selection.back,
            package: package,
            prepsByGlobalId: preps,
            topoImagesByGlobalId: topoImages,
            cachedAt: now()
        )
    }

    private func persist(_ download: WatchCourseDownload) throws {
        for image in download.images {
            try imageStore.store(data: image.data, globalId: image.globalId, hole: image.hole)
        }
        try store.save(download.template)
        cachedCourseIds.insert(download.template.option.globalId)
        courses = Self.uniqueOptions(
            from: [download.template.option, download.template.backOption].compactMap { $0 } + courses
        )
    }

    private static func preciseDownloadReady(_ download: WatchCourseDownload) -> Bool {
        !download.template.holeStates.isEmpty
            && download.template.holeStates.allSatisfy {
                $0.geometryCoverage?.caseInsensitiveCompare("ready") == .orderedSame
            }
            && download.images.count == download.template.holeStates.count
    }

    private func makeClient(_ config: WatchRoundConfig) -> WatchBackendClient {
        WatchBackendClient(
            baseURL: config.baseURL,
            adminToken: config.adminToken,
            sessionToken: config.sessionToken,
            sessionTokenExpiresAt: config.sessionTokenExpiresAt
        )
    }

    private static func uniqueOptions(from options: [WatchCourseOption]) -> [WatchCourseOption] {
        var seen = Set<Int>()
        return options.filter { seen.insert($0.globalId).inserted }
    }

    private func localNearbyCourses(
        latitude: Double,
        longitude: Double,
        radiusKm: Int
    ) -> [WatchCourseOption] {
        WatchCourseProximity.ranked(
            courses.filter { option in
                guard let distance = WatchCourseProximity.distanceM(
                    to: option,
                    fromLatitude: latitude,
                    longitude: longitude
                ) else { return false }
                return distance <= Double(radiusKm) * 1_000
            },
            fromLatitude: latitude,
            longitude: longitude
        )
    }

    private func resolvedNearbyOption(_ match: WatchCourseSearchMatch) -> WatchCourseOption? {
        guard let provider = match.courseOption else { return nil }
        guard let known = courses.first(where: { $0.globalId == match.globalId }) else {
            return provider
        }
        return WatchCourseOption(
            globalId: provider.globalId,
            name: provider.name,
            holes: provider.holes,
            teeBox: known.teeBox,
            venueName: provider.venueName ?? known.venueName,
            segmentLabel: provider.segmentLabel ?? known.segmentLabel,
            segmentHoles: provider.segmentHoles ?? known.segmentHoles,
            latitude: provider.latitude ?? known.latitude,
            longitude: provider.longitude ?? known.longitude,
            tees: known.tees,
            roundCount: known.roundCount
        )
    }
}
