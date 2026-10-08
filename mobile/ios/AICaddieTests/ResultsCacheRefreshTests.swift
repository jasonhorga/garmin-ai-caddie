@testable import AICaddie
import XCTest

/// Speed plan batch 2: 成绩 and the home open on fresh cached history/stats because the app
/// rewrites those files in the background, not only when 成绩 itself is opened.
@MainActor
final class ResultsCacheRefreshTests: XCTestCase {
    private final class Paths: @unchecked Sendable {
        private let lock = NSLock()
        private var paths: [String] = []
        func append(_ path: String) { lock.withLock { paths.append(path) } }
        var all: [String] { lock.withLock { paths } }
    }

    private static let statsPayload = Data("""
    {"summary": {"totalRounds": 20, "recent20Average": 88.4, "handicapTrend": -0.8}, "courses": [], "clubs": []}
    """.utf8)

    private static let archivePayload = Data("""
    {
      "total": 1,
      "groups": [{
        "key": "2026-10", "label": "October 2026", "count": 1, "average18": 86, "bestScore": 86,
        "rounds": [{"id": "r-new", "date": "2026-10-08", "courseName": "Half Moon Bay", "score": 86, "scoreStrip": [], "badges": []}]
      }],
      "availableYears": ["2026"],
      "availableCourses": []
    }
    """.utf8)

    private func serve(into paths: Paths, failing: Bool = false) {
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            paths.append(url.path)
            let body: Data
            switch url.path {
            case "/api/v2/history/stats/mobile" where !failing: body = Self.statsPayload
            case "/api/v2/history/rounds" where !failing: body = Self.archivePayload
            default:
                return (HTTPURLResponse(url: url, statusCode: 503, httpVersion: nil, headerFields: nil)!, Data())
            }
            return (
                HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!,
                body
            )
        }
    }

    private func model(_ store: OfflineStore) -> LiveRoundAppModel {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: URL(string: "https://results-cache.example.test")!,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: SyncClient(
                baseURL: URL(string: "https://results-cache.example.test")!,
                session: URLSession(configuration: configuration),
                retrySleep: { _ in }
            ),
            offlineGeometryRetryDelaysNanoseconds: []
        )
        model.resultsCacheRefreshDelayNanoseconds = 0
        return model
    }

    private func freshStore() -> OfflineStore {
        OfflineStore(directoryURL: FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true))
    }

    func testTheBackgroundRefreshRewritesTheCachedFilesAndAnnouncesIt() async throws {
        let paths = Paths()
        serve(into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }
        let store = freshStore()
        let model = model(store)
        let announced = expectation(forNotification: .resultsCacheDidUpdate, object: nil)

        model.refreshResultsCacheForTesting()
        await model.waitForResultsCacheRefreshForTesting()
        await fulfillment(of: [announced], timeout: 2)

        XCTAssertEqual(try store.loadMobileStats()?.summary?.recent20Average, 88.4)
        XCTAssertEqual(try store.loadHistoryRoundsArchive()?.groups.first?.rounds.first?.id, "r-new")
    }

    /// Launch, foreground and Garmin all call it; within five minutes of a refresh it does nothing.
    func testARefreshWithinFiveMinutesIsSkipped() async throws {
        let paths = Paths()
        serve(into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }
        let model = model(freshStore())

        model.refreshResultsCacheForTesting()
        await model.waitForResultsCacheRefreshForTesting()
        let afterFirst = paths.all.count
        model.refreshResultsCacheForTesting()
        await model.waitForResultsCacheRefreshForTesting()
        XCTAssertEqual(paths.all.count, afterFirst)
    }

    /// A failed refresh keeps the previous files and is retried at the next trigger.
    func testAFailedRefreshKeepsTheCacheAndRetriesNextTime() async throws {
        let paths = Paths()
        serve(into: paths, failing: true)
        defer { CapturingURLProtocol.requestHandler = nil }
        let store = freshStore()
        let model = model(store)

        model.refreshResultsCacheForTesting()
        await model.waitForResultsCacheRefreshForTesting()
        XCTAssertNil(try store.loadMobileStats())
        let afterFailure = paths.all.count
        XCTAssertGreaterThan(afterFailure, 0)

        serve(into: paths)
        model.refreshResultsCacheForTesting()
        await model.waitForResultsCacheRefreshForTesting()
        XCTAssertGreaterThan(paths.all.count, afterFailure)
        XCTAssertNotNil(try store.loadMobileStats())
    }

    func testAdoptingTheCacheNeverReplacesASectionStillLoading() {
        var load = ResultsLandingLoad()
        let generation = load.begin()
        let stats = try? JSONDecoder().decode(MobileStats.self, from: Self.statsPayload)
        let archive = try? JSONDecoder().decode(HistoryRoundsArchive.self, from: Self.archivePayload)
        load.completeStats(generation, nil)
        XCTAssertNotNil(load.errorText)
        load.adoptCache(stats: stats, archive: archive)
        XCTAssertEqual(load.stats?.summary?.recent20Average, 88.4, "a failed section takes the fresh cache")
        XCTAssertNil(load.archive, "the archive request is still in flight")
        XCTAssertNil(load.errorText)
    }
}
