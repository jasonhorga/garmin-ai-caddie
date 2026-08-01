import Combine
import Foundation

/// Owns the Watch's small, user-visible course library. Remote options are ephemeral; only a course
/// that has completed package + prep download is advertised as cached and can start with no config.
@MainActor
public final class WatchCourseLibrary: ObservableObject {
    @Published public private(set) var courses: [WatchCourseOption]
    @Published public private(set) var searchMatches: [WatchCourseSearchMatch] = []
    @Published public private(set) var cachedCourseIds: Set<Int>
    @Published public private(set) var isLoadingCourses = false
    @Published public private(set) var isSearchingCourses = false
    @Published public private(set) var preparingCourseId: Int?
    @Published public private(set) var errorMessage: String?

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
            return []
        }
        do {
            let tees = try await makeClient(config).fetchCourseTees(globalId: globalId)
            errorMessage = tees.isEmpty ? "这个球场没有可用的发球台数据" : nil
            return tees
        } catch {
            errorMessage = "无法获取发球台，请检查网络后重试"
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
        defer { preparingCourseId = nil }
        do {
            let client = makeClient(config)
            let roundId = makeRoundId()
            let package = try await client.fetchCoursePackage(
                globalId: selection.front.globalId,
                roundId: roundId,
                teeBox: selection.teeBox,
                backGlobalId: selection.back?.globalId,
                ensureGeometry: selection.ensureGeometry
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
                preps[globalId] = WatchCoursePrepResponse(
                    globalId: globalId,
                    clubs: prepParts.first?.clubs ?? [],
                    holes: prepParts.flatMap(\.holes)
                )
                for localHole in localHoles {
                    if let data = try? await client.fetchCourseTopo(
                        globalId: globalId,
                        localHole: localHole
                    ), !data.isEmpty {
                        topoImages[globalId, default: [:]][localHole] = data
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
            for image in download.images {
                try imageStore.store(data: image.data, globalId: image.globalId, hole: image.hole)
            }
            try store.save(download.template)
            cachedCourseIds.insert(selection.front.globalId)
            courses = Self.uniqueOptions(
                from: [download.template.option, download.template.backOption].compactMap { $0 } + courses
            )
            return download.template.makeRound(roundId: package.roundId)
        } catch {
            errorMessage = "球场下载失败，请保持联网后重试"
            return nil
        }
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
}
