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

    // MARK: - Codex review of #395: abandoned refreshes, late answers, notification ordering

    private final class Gate: @unchecked Sendable {
        private let lock = NSLock()
        private var holding = true
        let release = DispatchSemaphore(value: 0)
        var isHolding: Bool { lock.withLock { holding } }
        func open() { lock.withLock { holding = false } }
    }

    private static func statsPayload(rounds: Int) -> Data {
        Data(#"{"summary":{"totalRounds":\#(rounds)}}"#.utf8)
    }

    /// While `gate` holds, answers are the old snapshot (1 round) and wait for `release`; after
    /// `open()` every request answers the new snapshot (2 rounds) at once.
    private func serveHeld(_ gate: Gate, into paths: Paths) {
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            paths.append(url.path)
            let held = gate.isHolding
            if held { _ = gate.release.wait(timeout: .now() + 5) }
            let body: Data
            switch url.path {
            case "/api/v2/history/stats/mobile": body = Self.statsPayload(rounds: held ? 1 : 2)
            case "/api/v2/history/rounds": body = Self.archivePayload
            default:
                return (HTTPURLResponse(url: url, statusCode: 404, httpVersion: nil, headerFields: nil)!, Data())
            }
            return (HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!, body)
        }
    }

    private func waitForRequests(_ paths: Paths, count: Int) async throws {
        for _ in 0..<100 where paths.all.count < count {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertGreaterThanOrEqual(paths.all.count, count)
    }

    /// A Tee / nearby / search request arriving after the refresh's requests are in flight abandons
    /// them; their late answer is never written, and the refresh runs again once the request ends.
    func testAForegroundRequestAbandonsARefreshInFlightAndItRunsAgainAfterwards() async throws {
        let gate = Gate()
        let paths = Paths()
        serveHeld(gate, into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }
        let store = freshStore()
        let model = model(store)

        model.refreshResultsCacheForTesting()
        try await waitForRequests(paths, count: 1)
        model.beginForegroundCourseRequestForTesting()
        XCTAssertTrue(model.resultsCacheRefreshPendingForTesting)
        gate.open()
        gate.release.signal()
        gate.release.signal()
        try await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertNil(try store.loadMobileStats(), "the abandoned answer is never written")

        model.endForegroundCourseRequestForTesting()
        await model.waitForResultsCacheRefreshForTesting()
        XCTAssertFalse(model.resultsCacheRefreshPendingForTesting)
        XCTAssertEqual(try store.loadMobileStats()?.summary?.totalRounds, 2)
    }

    /// Old snapshot already fetched → Garmin pull completes → the old answer lands late: it is
    /// dropped and the new snapshot is what ends up on disk.
    func testAGarminPullDropsARefreshThatReadThePrePullData() async throws {
        let gate = Gate()
        let paths = Paths()
        serveHeld(gate, into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }
        let store = freshStore()
        let model = model(store)

        model.refreshResultsCacheForTesting()
        try await waitForRequests(paths, count: 1)
        gate.open()
        model.invalidateResultsCacheAfterGarminPullForTesting()
        // The pre-pull answers land only now, after the pull invalidated them.
        gate.release.signal()
        gate.release.signal()
        await model.waitForResultsCacheRefreshForTesting()
        XCTAssertEqual(try store.loadMobileStats()?.summary?.totalRounds, 2)
        try await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertEqual(try store.loadMobileStats()?.summary?.totalRounds, 2, "the late pre-pull answer is dropped")
    }

    /// 成绩 and the background refresh write the same files: an answer whose request started
    /// earlier never overwrites one already committed for the same account.
    func testAnOlderRequestsAnswerNeverOverwritesANewerCommit() throws {
        let store = freshStore()
        let older = try JSONDecoder().decode(MobileStats.self, from: Self.statsPayload(rounds: 1))
        let newer = try JSONDecoder().decode(MobileStats.self, from: Self.statsPayload(rounds: 2))
        let olderTicket = store.beginResultsRequest()
        Thread.sleep(forTimeInterval: 0.01)
        let newerTicket = store.beginResultsRequest()
        XCTAssertTrue(try store.commitMobileStats(newer, ticket: newerTicket))
        XCTAssertFalse(try store.commitMobileStats(older, ticket: olderTicket))
        XCTAssertEqual(try store.loadMobileStats()?.summary?.totalRounds, 2)
    }

    // MARK: - Codex review of #395 (P1): an answer for account A never lands in account B

    private func heldClient(_ gate: Gate, into paths: Paths) -> SyncClient {
        serveHeld(gate, into: paths)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        return SyncClient(
            baseURL: URL(string: "https://results-cache.example.test")!,
            session: URLSession(configuration: configuration),
            retrySleep: { _ in }
        )
    }

    /// A 成绩 stats request starts for A; the session expires and B signs in on the same store; A's
    /// answer arrives. It is neither written to B (empty, or holding its own cache) nor published.
    func testAStatsAnswerForAPreviousAccountIsNeitherWrittenNorPublished() async throws {
        for bHasCache in [false, true] {
            let gate = Gate()
            let paths = Paths()
            let client = heldClient(gate, into: paths)
            defer { CapturingURLProtocol.requestHandler = nil }
            let store = freshStore()
            store.bindAccount(playerId: "player-b", migrateLegacyData: false)
            let bStats = try JSONDecoder().decode(MobileStats.self, from: Self.statsPayload(rounds: 77))
            if bHasCache { try store.saveMobileStats(bStats) }
            store.bindAccount(playerId: "player-a", migrateLegacyData: false)

            let pending = Task { @MainActor in await ResultsFreshLoad.stats(client, store: store) }
            try await waitForRequests(paths, count: 1)
            store.bindAccount(playerId: "player-b", migrateLegacyData: false)
            gate.release.signal()
            let outcome = await pending.value

            guard case .staleAccount = outcome else {
                return XCTFail("A's answer must not be published under B (bHasCache=\(bHasCache))")
            }
            XCTAssertEqual(try store.loadMobileStats()?.summary?.totalRounds, bHasCache ? 77 : nil)
        }
    }

    func testAnArchiveAnswerForAPreviousAccountIsNeitherWrittenNorPublished() async throws {
        let gate = Gate()
        let paths = Paths()
        let client = heldClient(gate, into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }
        let store = freshStore()
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)

        let pending = Task { @MainActor in await ResultsFreshLoad.archive(client, store: store) }
        try await waitForRequests(paths, count: 1)
        store.bindAccount(playerId: "player-b", migrateLegacyData: false)
        gate.release.signal()
        let outcome = await pending.value

        guard case .staleAccount = outcome else { return XCTFail("A's archive must not be published under B") }
        XCTAssertNil(try store.loadHistoryRoundsArchive())
    }

    /// Rebinding even back to the same player retires tickets issued before it.
    func testARebindRetiresEveryEarlierTicket() throws {
        let store = freshStore()
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        let ticket = store.beginResultsRequest()
        store.bindAccount(playerId: "player-b", migrateLegacyData: false)
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        let stats = try JSONDecoder().decode(MobileStats.self, from: Self.statsPayload(rounds: 5))
        XCTAssertFalse(store.isCurrentAccount(ticket))
        XCTAssertFalse(try store.commitMobileStats(stats, ticket: ticket))
        XCTAssertNil(try store.loadMobileStats())
    }

    /// The background refresh keeps its own account-switch guard: A's held answer is dropped
    /// after the model binds B.
    func testTheBackgroundRefreshNeverWritesAPreviousAccountsAnswer() async throws {
        let gate = Gate()
        let paths = Paths()
        serveHeld(gate, into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }
        let store = freshStore()
        let model = model(store)
        let previousClubBagPlayer = ClubBagStore.playerId
        defer { ClubBagSyncCoordinator.shared.activate(playerId: previousClubBagPlayer, migrateLegacy: false) }
        model.activateSession(
            AppSession(token: "token", playerId: "player-a", expiresAt: Date().addingTimeInterval(600)),
            migrateLegacyData: false
        )

        model.refreshResultsCacheForTesting()
        try await waitForRequests(paths, count: 1)
        model.activateSession(
            AppSession(token: "token", playerId: "player-b", expiresAt: Date().addingTimeInterval(600)),
            migrateLegacyData: false
        )
        gate.release.signal()
        gate.release.signal()
        try await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertNil(try store.loadMobileStats())
        XCTAssertNil(try store.loadHistoryRoundsArchive())
    }

    /// The cache notification arrives while 成绩's own requests run, then both fail: the page shows
    /// the fresh cache without a failure note. A successful answer still wins over it.
    func testACacheArrivingBeforeAFailedAnswerIsShownInsteadOfTheFailure() throws {
        let cached = try JSONDecoder().decode(MobileStats.self, from: Self.statsPayload(rounds: 2))
        let network = try JSONDecoder().decode(MobileStats.self, from: Self.statsPayload(rounds: 3))
        let archive = try JSONDecoder().decode(HistoryRoundsArchive.self, from: Self.archivePayload)
        var load = ResultsLandingLoad()
        let generation = load.begin()
        load.adoptCache(stats: cached, archive: archive)
        XCTAssertNil(load.stats, "not shown over the running request")
        load.completeStats(generation, nil)
        load.completeArchive(generation, nil)
        XCTAssertEqual(load.stats?.summary?.totalRounds, 2)
        XCTAssertEqual(load.archive?.groups.first?.rounds.first?.id, "r-new")
        XCTAssertNil(load.errorText)

        let next = load.begin()
        load.adoptCache(stats: cached, archive: nil)
        load.completeStats(next, network)
        XCTAssertEqual(load.stats?.summary?.totalRounds, 3, "a successful answer wins")
    }
}
