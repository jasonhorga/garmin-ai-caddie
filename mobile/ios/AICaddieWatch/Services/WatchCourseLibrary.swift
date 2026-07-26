import Combine
import Foundation

/// Owns the Watch's small, user-visible course library. Remote options are ephemeral; only a course
/// that has completed package + prep download is advertised as cached and can start with no config.
@MainActor
public final class WatchCourseLibrary: ObservableObject {
    @Published public private(set) var courses: [WatchCourseOption]
    @Published public private(set) var cachedCourseIds: Set<Int>
    @Published public private(set) var isLoadingCourses = false
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
        courses = cached.map(\.option)
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
            for template in cached where !merged.contains(where: { $0.globalId == template.option.globalId }) {
                merged.append(template.option)
            }
            courses = merged
            cachedCourseIds = Set(cached.map { $0.option.globalId })
            errorMessage = nil
        } catch {
            errorMessage = courses.isEmpty
                ? "无法获取球场，请检查网络或登录状态"
                : "无法更新球场，已缓存球场仍可离线使用"
        }
    }

    public func startCourse(
        _ option: WatchCourseOption,
        config: WatchRoundConfig?
    ) async -> WatchPreparedCourse? {
        if let cached = store.course(globalId: option.globalId) {
            errorMessage = nil
            return cached.makeRound(roundId: makeRoundId())
        }
        guard let config else {
            errorMessage = "这个球场尚未下载，请联网后重试"
            return nil
        }

        preparingCourseId = option.globalId
        errorMessage = nil
        defer { preparingCourseId = nil }
        do {
            let client = makeClient(config)
            let roundId = makeRoundId()
            let package = try await client.fetchCoursePackage(
                globalId: option.globalId,
                roundId: roundId,
                teeBox: option.preferredTee
            )

            var requestedByGlobalId: [Int: Set<Int>] = [:]
            for hole in package.holes {
                let globalId = hole.sourceGlobalId ?? package.course.globalId
                let localHole = hole.sourceLocalHole ?? hole.number
                requestedByGlobalId[globalId, default: []].insert(localHole)
            }
            var preps: [Int: WatchCoursePrepResponse] = [:]
            for globalId in requestedByGlobalId.keys.sorted() {
                let localHoles = requestedByGlobalId[globalId, default: []].sorted()
                preps[globalId] = try await client.fetchCoursePrep(
                    globalId: globalId,
                    localHoles: localHoles
                )
            }

            let download = try WatchCourseTemplateBuilder.build(
                option: option,
                package: package,
                prepsByGlobalId: preps,
                cachedAt: now()
            )
            for image in download.images {
                try imageStore.store(data: image.data, globalId: image.globalId, hole: image.hole)
            }
            try store.save(download.template)
            cachedCourseIds.insert(option.globalId)
            if !courses.contains(where: { $0.globalId == option.globalId }) {
                courses.append(option)
            }
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
}
