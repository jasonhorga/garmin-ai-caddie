@testable import AICaddie
import XCTest

/// Speed plan batch 2: the course catalogue (`courses/options`) is kept per account so 开始一场 and
/// the home have loop names and tees before the network answers.
@MainActor
final class CourseOptionsCacheTests: XCTestCase {
    private final class Paths: @unchecked Sendable {
        private let lock = NSLock()
        private var paths: [String] = []
        func append(_ path: String) { lock.withLock { paths.append(path) } }
        var all: [String] { lock.withLock { paths } }
    }

    private static func catalogue(_ name: String) -> Data {
        Data("""
        {"schema": "mobile_course_options_v1", "dataMode": "live", "total": 1, "generatedAt": "2026-10-09T00:00:00Z",
         "courses": [{"globalId": 31793, "name": "\(name)", "roundCount": 3, "holes": 18,
                      "geometryCoverage": "ready", "sourceRefs": [], "tees": ["Blue"]}]}
        """.utf8)
    }

    /// Every courses/options request answers `name`, waiting for one `release` signal first when
    /// `held` is set.
    private func serve(_ name: String, into paths: Paths, held: DispatchSemaphore? = nil) {
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            paths.append(url.path)
            guard url.path == "/api/v2/mobile/courses/options" else {
                return (HTTPURLResponse(url: url, statusCode: 404, httpVersion: nil, headerFields: nil)!, Data())
            }
            if let held { _ = held.wait(timeout: .now() + 5) }
            return (
                HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!,
                Self.catalogue(name)
            )
        }
    }

    private func model(_ store: OfflineStore) -> LiveRoundAppModel {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        return LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: URL(string: "https://course-options.example.test")!,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: SyncClient(
                baseURL: URL(string: "https://course-options.example.test")!,
                session: URLSession(configuration: configuration),
                retrySleep: { _ in }
            ),
            offlineGeometryRetryDelaysNanoseconds: []
        )
    }

    private func freshDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    }

    private func waitForRequests(_ paths: Paths, count: Int) async throws {
        for _ in 0..<100 where paths.all.count < count {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertGreaterThanOrEqual(paths.all.count, count)
    }

    private func session(_ playerId: String) -> AppSession {
        AppSession(token: "token", playerId: playerId, expiresAt: Date().addingTimeInterval(600))
    }

    func testTheCatalogueRoundTripsPerAccountAndAnOlderRequestNeverOverwritesANewerOne() throws {
        let store = OfflineStore(directoryURL: freshDirectory())
        let older = [MobileCourseOption(globalId: 1, name: "Older")]
        let newer = [MobileCourseOption(globalId: 2, name: "Newer")]

        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        let olderTicket = store.beginResultsRequest()
        let newerTicket = store.beginResultsRequest()
        XCTAssertTrue(try store.commitCourseOptions(newer, ticket: newerTicket))
        XCTAssertFalse(try store.commitCourseOptions(older, ticket: olderTicket), "a slower older answer is dropped")
        XCTAssertEqual(try store.loadCourseOptions(), newer)

        let staleTicket = store.beginResultsRequest()
        store.bindAccount(playerId: "player-b", migrateLegacyData: false)
        XCTAssertNil(try store.loadCourseOptions())
        XCTAssertFalse(try store.commitCourseOptions(older, ticket: staleTicket), "A's answer never lands in B")
        XCTAssertNil(try store.loadCourseOptions())

        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        XCTAssertEqual(try store.loadCourseOptions(), newer)
    }

    /// A successful refresh is what the next launch shows before its own request answers.
    func testAFreshCatalogueIsWhatTheNextLaunchShowsFirst() async throws {
        let directory = freshDirectory()
        let paths = Paths()
        serve("Beijing Palace", into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }

        let first = model(OfflineStore(directoryURL: directory))
        XCTAssertTrue(first.courseOptions.isEmpty)
        await first.refreshCourseOptions()
        XCTAssertEqual(first.courseOptions.map(\.name), ["Beijing Palace"])

        let relaunched = model(OfflineStore(directoryURL: directory))
        XCTAssertEqual(relaunched.courseOptions.map(\.name), ["Beijing Palace"])
        XCTAssertEqual(relaunched.courseOptions.first?.tees, ["Blue"])
    }

    /// Switching account shows B's own catalogue (none here) at once, and A's answer that arrives
    /// afterwards is neither published nor written into B's files.
    func testAPreviousAccountsCatalogueIsNeitherPublishedNorWrittenAfterASwitch() async throws {
        let store = OfflineStore(directoryURL: freshDirectory())
        let previousClubBagPlayer = ClubBagStore.playerId
        defer { ClubBagSyncCoordinator.shared.activate(playerId: previousClubBagPlayer, migrateLegacy: false) }
        let paths = Paths()
        serve("A's course", into: paths)
        defer { CapturingURLProtocol.requestHandler = nil }
        let model = model(store)
        model.activateSession(session("player-a"), migrateLegacyData: false)
        await model.refreshCourseOptions()
        XCTAssertEqual(model.courseOptions.map(\.name), ["A's course"])

        let release = DispatchSemaphore(value: 0)
        serve("A's late course", into: paths, held: release)
        let requestsBefore = paths.all.count
        let refresh = Task { await model.refreshCourseOptions() }
        try await waitForRequests(paths, count: requestsBefore + 1)
        model.activateSession(session("player-b"), migrateLegacyData: false)
        XCTAssertTrue(model.courseOptions.isEmpty, "B has no cached catalogue; A's must not linger")
        release.signal()
        await refresh.value

        XCTAssertTrue(model.courseOptions.isEmpty)
        XCTAssertNil(try store.loadCourseOptions())
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        XCTAssertEqual(try store.loadCourseOptions()?.map(\.name), ["A's course"])
    }
}
