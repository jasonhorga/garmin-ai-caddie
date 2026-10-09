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

    /// A fetch that holds until `release()`, ignoring cancellation, then answers or throws: the
    /// refresh sees exactly the value arriving late, not URLSession's own cancellation error.
    private final class Held {
        private var continuation: CheckedContinuation<Void, Never>?
        var isWaiting: Bool { continuation != nil }
        func wait() async { await withCheckedContinuation { continuation = $0 } }
        func release() { continuation?.resume(); continuation = nil }
    }

    private func waitUntilHeld(_ held: Held) async throws {
        for _ in 0..<200 where !held.isWaiting { try await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertTrue(held.isWaiting)
    }

    private static let previous = [MobileCourseOption(globalId: 1, name: "Previous", roundCount: 2)]
    private static let older = [MobileCourseOption(globalId: 2, name: "Older answer")]
    private static let newer = [
        MobileCourseOption(globalId: 3, name: "Newer answer"),
        MobileCourseOption(globalId: 4, name: "Not downloaded"),
    ]

    private func seededModel(_ directory: URL) throws -> (LiveRoundAppModel, OfflineStore) {
        let store = OfflineStore(directoryURL: directory)
        XCTAssertTrue(try store.commitCourseOptions(Self.previous, ticket: store.beginResultsRequest()))
        return (model(store), store)
    }

    /// Cancelled while waiting, the request still receives a successful catalogue: it is neither
    /// written, nor shown, nor counted as a confirmed refresh.
    func testASuccessArrivingAfterCancellationChangesNothing() async throws {
        let (model, store) = try seededModel(freshDirectory())
        XCTAssertEqual(model.courseOptions, Self.previous)
        let held = Held()
        let refresh = Task { @MainActor in
            await model.refreshCourseOptions { await held.wait(); return Self.newer }
        }
        try await waitUntilHeld(held)
        refresh.cancel()
        held.release()
        await refresh.value

        XCTAssertEqual(model.courseOptions, Self.previous)
        XCTAssertEqual(try store.loadCourseOptions(), Self.previous)
        XCTAssertFalse(model.courseOptionsRefreshSucceededForTesting)
    }

    /// Launch and Garmin post-sync refreshes overlap: the older one times out after the newer one
    /// succeeded. Its failure must not narrow the newer catalogue to downloaded courses.
    func testAnOlderFailureAfterANewerSuccessKeepsTheNewerCatalogue() async throws {
        let (model, store) = try seededModel(freshDirectory())
        let held = Held()
        let slow = Task { @MainActor in
            await model.refreshCourseOptions { () async throws -> [MobileCourseOption] in
                await held.wait()
                throw URLError(.timedOut)
            }
        }
        try await waitUntilHeld(held)
        await model.refreshCourseOptions { Self.newer }
        held.release()
        await slow.value

        XCTAssertEqual(model.courseOptions, Self.newer, "nothing here is downloaded, so a wrongly accepted failure empties it")
        XCTAssertEqual(try store.loadCourseOptions(), Self.newer)
        XCTAssertTrue(model.courseOptionsRefreshSucceededForTesting)
    }

    /// A superseded request's late 401 is arbitrated before any side effect: it neither signs the
    /// player out nor narrows the newer catalogue. (Unit tests run without `UITEST_MODE`, so the
    /// sign-out path is real; the next test proves it fires for the current request.)
    func testAnOlder401AfterANewerSuccessKeepsTheSessionAndTheCatalogue() async throws {
        XCTAssertNil(ProcessInfo.processInfo.environment["UITEST_MODE"])
        SessionStore.shared.save(session("player-a"))
        defer { SessionStore.shared.signOut() }
        let (model, store) = try seededModel(freshDirectory())
        let held = Held()
        let slow = Task { @MainActor in
            await model.refreshCourseOptions { () async throws -> [MobileCourseOption] in
                await held.wait()
                throw SyncClientError.http(status: 401, body: nil)
            }
        }
        try await waitUntilHeld(held)
        await model.refreshCourseOptions { Self.newer }
        held.release()
        await slow.value

        XCTAssertNotNil(SessionStore.shared.currentSession, "a superseded 401 must not sign out")
        XCTAssertEqual(model.courseOptions, Self.newer)
        XCTAssertEqual(try store.loadCourseOptions(), Self.newer)
        XCTAssertTrue(model.courseOptionsRefreshSucceededForTesting)
    }

    func testTheCurrentRequests401StillSignsOut() async throws {
        SessionStore.shared.save(session("player-a"))
        defer { SessionStore.shared.signOut() }
        let (model, store) = try seededModel(freshDirectory())

        await model.refreshCourseOptions { () async throws -> [MobileCourseOption] in
            throw SyncClientError.http(status: 401, body: nil)
        }

        XCTAssertNil(SessionStore.shared.currentSession)
        XCTAssertTrue(model.courseOptions.isEmpty, "nothing cached is downloaded")
        XCTAssertEqual(try store.loadCourseOptions(), Self.previous)
        XCTAssertFalse(model.courseOptionsRefreshSucceededForTesting)
    }

    /// When the disk refuses the newer catalogue it is still shown, and an older answer arriving
    /// afterwards does not replace it.
    func testAnOlderSuccessDoesNotReplaceANewerCatalogueTheDiskRefused() async throws {
        let directory = freshDirectory()
        let (model, store) = try seededModel(directory)
        let held = Held()
        let slow = Task { @MainActor in
            await model.refreshCourseOptions { await held.wait(); return Self.older }
        }
        try await waitUntilHeld(held)
        try FileManager.default.setAttributes([.posixPermissions: 0o555], ofItemAtPath: directory.path)
        defer { try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: directory.path) }
        await model.refreshCourseOptions { Self.newer }
        XCTAssertEqual(try store.loadCourseOptions(), Self.previous, "the write really failed")
        XCTAssertEqual(model.courseOptions, Self.newer)
        held.release()
        await slow.value

        XCTAssertEqual(model.courseOptions, Self.newer)
        XCTAssertEqual(try store.loadCourseOptions(), Self.previous)
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
