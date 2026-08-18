import Combine
import Foundation
import AICaddieDomain

/// Owns the Watch's small, user-visible course library. Remote options are ephemeral; only a course
/// that has completed package + prep download is advertised as cached and can start with no config.
@MainActor
public final class WatchCourseLibrary: ObservableObject {
    static let preciseUpgradeMaximumAttempts = 6
    static let preciseUpgradeRetryDelaysSeconds: [UInt64] = [5, 10, 20, 40, 60]

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
    private var refreshRequestToken: UUID?
    private var nearbyRequestToken: UUID?
    private var searchRequestToken: UUID?
    private var teeRequestToken: UUID?

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
        cachedCourseIds = Set(cached.compactMap {
            Self.preciseTemplateReady($0, imageStore: imageStore) ? $0.option.globalId : nil
        })
    }

    public func refresh(config: WatchRoundConfig?) async {
        let requestToken = UUID()
        refreshRequestToken = requestToken
        guard let config else {
            isLoadingCourses = false
            if courses.isEmpty {
                errorMessage = "请先在 iPhone 登录并同步一次"
            }
            return
        }
        isLoadingCourses = true
        defer {
            if refreshRequestToken == requestToken {
                isLoadingCourses = false
            }
        }
        do {
            let remote = try await makeClient(config).fetchCourseOptions()
            guard !Task.isCancelled, refreshRequestToken == requestToken else { return }
            let cached = store.loadCourses()
            var merged = remote
            let cachedOptions = cached.flatMap { [$0.option, $0.backOption].compactMap { $0 } }
            for option in cachedOptions where !merged.contains(where: { $0.globalId == option.globalId }) {
                merged.append(option)
            }
            courses = Self.uniqueOptions(from: merged)
            cachedCourseIds = Set(cached.compactMap {
                Self.preciseTemplateReady($0, imageStore: imageStore) ? $0.option.globalId : nil
            })
            errorMessage = nil
        } catch {
            guard !Task.isCancelled, refreshRequestToken == requestToken else { return }
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
        let requestToken = UUID()
        nearbyRequestToken = requestToken
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude),
              (1...200).contains(radiusKm) else {
            isLoadingNearby = false
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
            isLoadingNearby = false
            nearbyCourses = cachedNearby
            errorMessage = cachedNearby.isEmpty ? "请先在 iPhone 登录并同步一次" : nil
            return
        }

        isLoadingNearby = true
        errorMessage = nil
        defer {
            if nearbyRequestToken == requestToken {
                isLoadingNearby = false
            }
        }
        do {
            let matches = try await makeClient(config).nearbyCourses(
                latitude: latitude,
                longitude: longitude,
                radiusKm: radiusKm
            )
            guard !Task.isCancelled, nearbyRequestToken == requestToken else { return }
            var seen = Set<Int>()
            nearbyCourses = matches.compactMap { resolvedNearbyOption($0) }.filter {
                seen.insert($0.globalId).inserted
            }
            if nearbyCourses.isEmpty {
                errorMessage = "当前位置 \(radiusKm) km 内没有找到球场"
            }
        } catch {
            guard !Task.isCancelled, nearbyRequestToken == requestToken else { return }
            nearbyCourses = cachedNearby
            errorMessage = cachedNearby.isEmpty
                ? "无法读取附近球场，可改用名称搜索"
                : "无法更新附近球场，已显示本机附近缓存"
        }
    }

    public func searchAllCourses(name: String, config: WatchRoundConfig?) async {
        let requestToken = UUID()
        searchRequestToken = requestToken
        let query = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard query.count >= 2 else {
            isSearchingCourses = false
            searchMatches = []
            errorMessage = "请至少输入两个字再搜索全部球场"
            return
        }
        guard let config else {
            isSearchingCourses = false
            searchMatches = []
            errorMessage = "请先在 iPhone 登录并同步一次"
            return
        }

        isSearchingCourses = true
        searchMatches = []
        errorMessage = nil
        defer {
            if searchRequestToken == requestToken {
                isSearchingCourses = false
            }
        }
        do {
            let matches = try await makeClient(config).searchCourses(name: query)
            guard !Task.isCancelled, searchRequestToken == requestToken else { return }
            var seen = Set<Int>()
            searchMatches = matches.filter { seen.insert($0.globalId).inserted }
            if searchMatches.isEmpty {
                errorMessage = "未返回匹配球场，请检查名称或稍后重试"
            }
        } catch {
            guard !Task.isCancelled, searchRequestToken == requestToken else { return }
            errorMessage = "无法搜索全部球场，请检查网络或登录状态"
        }
    }

    public func loadCourseTees(
        globalId: Int,
        config: WatchRoundConfig?
    ) async -> [WatchCourseTee] {
        let requestToken = UUID()
        teeRequestToken = requestToken
        guard let config else {
            errorMessage = "这个球场尚未下载，请联网后重试"
            diagnosticErrorMessage = errorMessage
            return []
        }
        diagnosticErrorMessage = nil
        do {
            let tees = try await makeClient(config).fetchCourseTees(globalId: globalId)
            guard !Task.isCancelled, teeRequestToken == requestToken else { return [] }
            errorMessage = tees.isEmpty ? "这个球场没有可用的发球台数据" : nil
            diagnosticErrorMessage = errorMessage
            return tees
        } catch {
            guard !Task.isCancelled, teeRequestToken == requestToken else { return [] }
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
            if config == nil, !Self.preciseTemplateReady(cached, imageStore: imageStore) {
                let missing = Self.missingPreciseHoles(in: cached, imageStore: imageStore)
                errorMessage = "球场地图还没下载完整，请联网后继续补齐"
                diagnosticErrorMessage = "\(errorMessage!): 缺第 \(Self.holeList(missing)) 洞"
                return nil
            }
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
                backgroundGeometry: true,
                includePreparedGeometry: false
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
    /// returned map facts to the same round id. Failures and service cooldowns retry six times with
    /// bounded backoff; exhaustion stops the task so it cannot drain the Watch indefinitely. A later
    /// app entry starts a fresh bounded attempt from the persisted partial cache.
    public func upgradeCourseWhenReady(
        _ selection: WatchCourseSelection,
        roundId: String,
        config: WatchRoundConfig?,
        onProgress: (([WatchRoundState]) -> Void)? = nil
    ) async -> WatchPreparedCourse? {
        guard let config else { return nil }
        var shouldQueueGeometry = true

        for attempt in 0..<Self.preciseUpgradeMaximumAttempts {
            guard !Task.isCancelled else { return nil }
            do {
                let download = try await fetchCourseDownload(
                    selection,
                    roundId: roundId,
                    config: config,
                    backgroundGeometry: shouldQueueGeometry,
                    includePreparedGeometry: true
                )
                shouldQueueGeometry = false
                // Persist every valid partial attempt so one slow hole cannot make the Watch fetch
                // the other seventeen again after a relaunch. `cachedCourseIds` remains false until
                // the template, map geometry and every production raster are all present.
                try persist(download)
                let prepared = download.template.makeRound(roundId: roundId)
                onProgress?(prepared.holeStates)
                if Self.preciseDownloadReady(download) {
                    errorMessage = nil
                    return prepared
                }
            } catch {
                // The lightweight template remains playable. Retry below without replacing the
                // active-round screen with a transient network error.
            }

            guard attempt < Self.preciseUpgradeRetryDelaysSeconds.count else { break }
            do {
                try await Task.sleep(
                    nanoseconds: Self.preciseUpgradeRetryDelaysSeconds[attempt] * 1_000_000_000
                )
            } catch {
                return nil
            }
        }
        diagnosticErrorMessage = "地图后台补齐已暂停；下次进入本局时自动重试"
        return nil
    }

    /// Resume a precise-map download for an already-started/restored round. The immutable cached
    /// template retains the chosen Tee and optional back nine, so the app can recover after being
    /// killed without asking the golfer to choose the course again.
    public func upgradeCachedCourseWhenReady(
        globalId: Int,
        roundId: String,
        config: WatchRoundConfig?,
        onProgress: (([WatchRoundState]) -> Void)? = nil
    ) async -> WatchPreparedCourse? {
        guard let config,
              let cached = store.compositeCourse(containingGlobalId: globalId) else {
            return nil
        }
        let selection = WatchCourseSelection(
            front: cached.option,
            back: cached.backOption,
            teeBox: cached.teeBox,
            ensureGeometry: true
        )
        return await upgradeCourseWhenReady(
            selection,
            roundId: roundId,
            config: config,
            onProgress: onProgress
        )
    }

    private func fetchCourseDownload(
        _ selection: WatchCourseSelection,
        roundId: String,
        config: WatchRoundConfig,
        backgroundGeometry: Bool,
        includePreparedGeometry: Bool
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

        // Starting a round must not wait while a new course renders eighteen maps. Package facts
        // already provide ordered holes, Par, Tee and yardage, which are enough to start recording
        // honestly. The active-round recovery task fetches prep + rasters and upgrades in place.
        if !includePreparedGeometry {
            let lightweight = try WatchCourseTemplateBuilder.build(
                option: selection.front,
                backOption: selection.back,
                package: package,
                prepsByGlobalId: [:],
                topoImagesByGlobalId: [:],
                cachedAt: now()
            )
            let missing = Self.missingPreciseHoles(in: lightweight)
            diagnosticErrorMessage = "地图后台准备中：第 \(Self.holeList(missing)) 洞"
            return lightweight
        }

        var requestedByGlobalId: [Int: Set<Int>] = [:]
        var displayHoleByGlobalId: [Int: [Int: Int]] = [:]
        for hole in package.holes {
            let globalId = hole.sourceGlobalId ?? package.course.globalId
            let localHole = hole.sourceLocalHole ?? hole.number
            requestedByGlobalId[globalId, default: []].insert(localHole)
            displayHoleByGlobalId[globalId, default: [:]][localHole] = hole.number
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
                let displayHole = displayHoleByGlobalId[globalId]?[localHole] ?? localHole
                let prepHole = prep.holes.first { $0.hole == localHole }
                let packageHole = package.holes.first {
                    ($0.sourceGlobalId ?? package.course.globalId) == globalId
                        && ($0.sourceLocalHole ?? $0.number) == localHole
                }
                let geometryRevision = prepHole?.geometryRevision ?? packageHole?.geometryRevision
                var topoData: Data? = imageStore.data(
                    globalId: globalId,
                    hole: displayHole,
                    geometryRevision: geometryRevision
                )
                if topoData == nil {
                    do {
                        let data = try await client.fetchCourseTopo(
                            globalId: globalId,
                            localHole: localHole,
                            geometryRevision: geometryRevision
                        )
                        if WatchHoleImageStore.isValidImageData(data) {
                            topoData = data
                        }
                    } catch {
                        // The builder marks this exact display hole partial. The caller may begin with
                        // vector facts while the bounded background recovery retries only missing maps.
                    }
                }
                if let topoData {
                    topoImages[globalId, default: [:]][localHole] = topoData
                }

                // View Green has its own geometry-rendered detail asset. It is independent of the
                // whole-hole readiness branch: a cached topo must still be upgraded if an earlier
                // build predates the focused bitmap.
                if let prepHole,
                   let projection = prepHole.holeImageProjection,
                   let width = projection.widthPx,
                   let height = projection.heightPx,
                   let outline = prepHole.greenOutline,
                   let crop = GreenDetailCrop.around(
                       points: outline.pointsPx,
                       imageWidth: Double(width),
                       imageHeight: Double(height)
                   ),
                   !imageStore.hasImage(
                       globalId: globalId,
                       hole: displayHole,
                       geometryRevision: geometryRevision,
                       detail: true
                   ) {
                    if let detail = try? await client.fetchGreenDetailImage(
                        globalId: globalId,
                        localHole: localHole,
                        crop: crop,
                        geometryRevision: geometryRevision
                    ), WatchHoleImageStore.isValidImageData(detail) {
                        try? imageStore.store(
                            data: detail,
                            globalId: globalId,
                            hole: displayHole,
                            geometryRevision: geometryRevision,
                            detail: true
                        )
                    }
                }
            }
        }

        let download = try WatchCourseTemplateBuilder.build(
            option: selection.front,
            backOption: selection.back,
            package: package,
            prepsByGlobalId: preps,
            topoImagesByGlobalId: topoImages,
            cachedAt: now()
        )
        let missing = Self.missingPreciseHoles(in: download)
        diagnosticErrorMessage = missing.isEmpty
            ? nil
            : "地图仍待补齐：第 \(Self.holeList(missing)) 洞"
        return download
    }

    private func persist(_ download: WatchCourseDownload) throws {
        for image in download.images {
            try imageStore.store(
                data: image.data,
                globalId: image.globalId,
                hole: image.hole,
                geometryRevision: image.geometryRevision
            )
        }
        try store.save(download.template)
        if Self.preciseTemplateReady(download.template, imageStore: imageStore) {
            cachedCourseIds.insert(download.template.option.globalId)
        } else {
            cachedCourseIds.remove(download.template.option.globalId)
        }
        courses = Self.uniqueOptions(
            from: [download.template.option, download.template.backOption].compactMap { $0 } + courses
        )
    }

    private static func preciseDownloadReady(_ download: WatchCourseDownload) -> Bool {
        expectedHoleCount(for: download.template) > 0 && missingPreciseHoles(in: download).isEmpty
    }

    private static func missingPreciseHoles(in download: WatchCourseDownload) -> [Int] {
        let imageKeys = Set(download.images.map {
            WatchHoleImageStore.key(globalId: $0.globalId, hole: $0.hole)
        })
        var missing = Set(1...max(expectedHoleCount(for: download.template), 1))
        for state in download.template.holeStates {
            guard state.geometryCoverage?.caseInsensitiveCompare("ready") == .orderedSame,
                  state.holeMap != nil,
                  let globalId = state.globalId,
                  imageKeys.contains(WatchHoleImageStore.key(globalId: globalId, hole: state.hole)) else {
                missing.insert(state.hole)
                continue
            }
            missing.remove(state.hole)
        }
        return missing.sorted()
    }

    private static func preciseTemplateReady(
        _ template: WatchCourseTemplate,
        imageStore: WatchHoleImageStore
    ) -> Bool {
        expectedHoleCount(for: template) > 0
            && missingPreciseHoles(in: template, imageStore: imageStore).isEmpty
    }

    private static func missingPreciseHoles(
        in template: WatchCourseTemplate,
        imageStore: WatchHoleImageStore
    ) -> [Int] {
        var missing = Set(1...max(expectedHoleCount(for: template), 1))
        for state in template.holeStates {
            guard state.geometryCoverage?.caseInsensitiveCompare("ready") == .orderedSame,
                  state.holeMap != nil,
                  let globalId = state.globalId,
                  imageStore.hasImage(
                      globalId: globalId,
                      hole: state.hole,
                      geometryRevision: state.geometryRevision
                  ) else {
                missing.insert(state.hole)
                continue
            }
            missing.remove(state.hole)
        }
        return missing.sorted()
    }

    private static func expectedHoleCount(for template: WatchCourseTemplate) -> Int {
        template.option.playableHoleCount + (template.backOption?.playableHoleCount ?? 0)
    }

    private static func holeList(_ holes: [Int]) -> String {
        holes.sorted().map(String.init).joined(separator: "、")
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
