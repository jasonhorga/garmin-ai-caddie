@testable import AICaddie
import XCTest

/// Codex review of #396: the persistent review cache is written only for the player who started
/// the request, and every write path keeps each account to `retainedRounds` rounds.
@MainActor
final class RoundReviewDiskCacheTests: XCTestCase {
    private final class Player: @unchecked Sendable {
        private let lock = NSLock()
        private var value = "player-a"
        var current: String { lock.withLock { value } }
        func set(_ player: String) { lock.withLock { value = player } }
    }

    private final class Paths: @unchecked Sendable {
        private let lock = NSLock()
        private var paths: [String] = []
        func append(_ path: String) { lock.withLock { paths.append(path) } }
        var all: [String] { lock.withLock { paths } }
    }

    private let player = Player()
    private var root: URL!
    private var legacyRoot: URL!
    private var savedPlayerScope: (() -> String)!

    override func setUp() {
        super.setUp()
        let base = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        root = base.appendingPathComponent("support", isDirectory: true)
        legacyRoot = base.appendingPathComponent("caches", isDirectory: true)
        savedPlayerScope = RoundReviewDiskCache.currentPlayerScope
        RoundReviewDiskCache.rootOverride = root
        RoundReviewDiskCache.legacyRootOverride = legacyRoot
        let player = self.player
        RoundReviewDiskCache.currentPlayerScope = { player.current }
    }

    override func tearDown() {
        RoundReviewDiskCache.rootOverride = nil
        RoundReviewDiskCache.legacyRootOverride = nil
        RoundReviewDiskCache.currentPlayerScope = savedPlayerScope
        CapturingURLProtocol.requestHandler = nil
        super.tearDown()
    }

    private func roundDirectories(in base: URL) -> Int {
        let players = (try? FileManager.default.contentsOfDirectory(at: base, includingPropertiesForKeys: nil)) ?? []
        return players.reduce(0) { count, playerDirectory in
            count + ((try? FileManager.default.contentsOfDirectory(at: playerDirectory, includingPropertiesForKeys: nil))?.count ?? 0)
        }
    }

    private func detail(_ ref: String) throws -> RoundDetail {
        try JSONDecoder().decode(
            RoundDetail.self,
            from: Data(#"{"roundRef":"\#(ref)","found":true,"scorecard":[],"phaseSummary":[],"missingData":[]}"#.utf8)
        )
    }

    // MARK: - Retention on every write path

    func testShotMapOnlyRoundsStayWithinTheBoundAndKeepTheOneJustWritten() {
        let ticket = RoundReviewDiskCache.beginRequest()
        for index in 0...RoundReviewDiskCache.retainedRounds {
            XCTAssertTrue(RoundReviewDiskCache.saveShotMap(
                RoundHoleShotMap(found: true, hole: 1), roundRef: "r\(index)", hole: 1, ticket: ticket
            ))
        }
        XCTAssertEqual(roundDirectories(in: root), RoundReviewDiskCache.retainedRounds)
        XCTAssertNotNil(RoundReviewDiskCache.loadShotMap(roundRef: "r\(RoundReviewDiskCache.retainedRounds)", hole: 1))
    }

    func testMovingMoreThanTheBoundFromTheOldCachesLocationStaysBounded() throws {
        let ticket = RoundReviewDiskCache.beginRequest()
        let total = RoundReviewDiskCache.retainedRounds + 1
        // Build 41 rounds in the old location: write each through a scratch root (a write applies
        // the bound) and move its round directory under the old location's player directory.
        let scratch = legacyRoot.deletingLastPathComponent().appendingPathComponent("scratch", isDirectory: true)
        for index in 0..<total {
            RoundReviewDiskCache.rootOverride = scratch
            RoundReviewDiskCache.saveDetail(try detail("legacy\(index)"), roundRef: "legacy\(index)", ticket: ticket)
            let playerDirectory = try XCTUnwrap(FileManager.default.contentsOfDirectory(at: scratch, includingPropertiesForKeys: nil).first)
            let round = try XCTUnwrap(FileManager.default.contentsOfDirectory(at: playerDirectory, includingPropertiesForKeys: nil).first)
            let legacyPlayer = legacyRoot.appendingPathComponent(playerDirectory.lastPathComponent, isDirectory: true)
            try FileManager.default.createDirectory(at: legacyPlayer, withIntermediateDirectories: true)
            try FileManager.default.moveItem(at: round, to: legacyPlayer.appendingPathComponent(round.lastPathComponent))
        }
        XCTAssertEqual(roundDirectories(in: legacyRoot), total)

        RoundReviewDiskCache.rootOverride = root
        var read = 0
        for index in 0..<total where RoundReviewDiskCache.loadDetail(roundRef: "legacy\(index)") != nil {
            read += 1
        }
        XCTAssertEqual(read, total, "every round in the old location is still readable once")
        XCTAssertEqual(roundDirectories(in: root), RoundReviewDiskCache.retainedRounds, "moving them over applies the bound")
    }

    func testRewritingAnExistingRoundAndEqualTimestampsStillConverge() throws {
        let ticket = RoundReviewDiskCache.beginRequest()
        for index in 0..<RoundReviewDiskCache.retainedRounds {
            RoundReviewDiskCache.saveDetail(try detail("r\(index)"), roundRef: "r\(index)", ticket: ticket)
        }
        // Same timestamp everywhere: the tie-break must still leave exactly the bound.
        let same = Date(timeIntervalSince1970: 1_700_000_000)
        let players = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
        for playerDirectory in players {
            for round in try FileManager.default.contentsOfDirectory(at: playerDirectory, includingPropertiesForKeys: nil) {
                try FileManager.default.setAttributes([.modificationDate: same], ofItemAtPath: round.path)
            }
        }
        RoundReviewDiskCache.saveDetail(try detail("r0"), roundRef: "r0", ticket: ticket)
        XCTAssertEqual(roundDirectories(in: root), RoundReviewDiskCache.retainedRounds, "rewriting adds no round")
        RoundReviewDiskCache.saveDetail(try detail("new"), roundRef: "new", ticket: ticket)
        XCTAssertEqual(roundDirectories(in: root), RoundReviewDiskCache.retainedRounds)
        XCTAssertNotNil(RoundReviewDiskCache.loadDetail(roundRef: "new"))
    }

    func testEachAccountIsBoundedOnItsOwn() throws {
        for name in ["player-a", "player-b"] {
            player.set(name)
            let ticket = RoundReviewDiskCache.beginRequest()
            for index in 0...RoundReviewDiskCache.retainedRounds {
                RoundReviewDiskCache.saveDetail(try detail("\(name)-\(index)"), roundRef: "\(name)-\(index)", ticket: ticket)
            }
        }
        XCTAssertEqual(roundDirectories(in: root), RoundReviewDiskCache.retainedRounds * 2)
    }

    // MARK: - Account and cancellation (held responses)

    private func heldClient(release: DispatchSemaphore, paths: Paths) -> SyncClient {
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            paths.append(url.path)
            _ = release.wait(timeout: .now() + 5)
            let body: Data
            if url.path.hasSuffix("/shotmap") {
                body = Data(#"{"found":true,"hole":3}"#.utf8)
            } else {
                let ref = url.lastPathComponent
                body = Data(#"{"roundRef":"\#(ref)","found":true,"scorecard":[],"phaseSummary":[],"missingData":[]}"#.utf8)
            }
            return (HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!, body)
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        return SyncClient(
            baseURL: URL(string: "https://review-cache.example.test")!,
            session: URLSession(configuration: configuration),
            retrySleep: { _ in }
        )
    }

    private func waitForRequest(_ paths: Paths) async throws {
        for _ in 0..<100 where paths.all.isEmpty { try await Task.sleep(nanoseconds: 20_000_000) }
        XCTAssertFalse(paths.all.isEmpty)
    }

    /// A's scorecard request is in flight; A signs out and B signs in; A's answer arrives. B's
    /// files are untouched (empty, or holding B's own copy) and nothing is shown.
    func testAScorecardAnswerForAPreviousPlayerIsNeitherWrittenNorShown() async throws {
        for bHasCopy in [false, true] {
            let ref = "shared-\(UUID().uuidString)"
            player.set("player-b")
            if bHasCopy {
                RoundReviewDiskCache.saveDetail(try detail("b-copy"), roundRef: ref, ticket: RoundReviewDiskCache.beginRequest())
            }
            player.set("player-a")
            let release = DispatchSemaphore(value: 0)
            let paths = Paths()
            let client = heldClient(release: release, paths: paths)

            let pending = Task { @MainActor in
                await RoundReviewFreshLoad.detail(client, roundRef: ref, globalId: nil, backGlobalId: nil, nine: nil, teeBox: nil)
            }
            try await waitForRequest(paths)
            player.set("player-b")
            release.signal()
            guard case .staleAccount = await pending.value else {
                return XCTFail("A's scorecard must not be shown under B (bHasCopy=\(bHasCopy))")
            }
            XCTAssertEqual(RoundReviewDiskCache.loadDetail(roundRef: ref)?.roundRef, bHasCopy ? "b-copy" : nil)
            player.set("player-a")
            XCTAssertNil(RoundReviewDiskCache.loadDetail(roundRef: ref), "not even into A's directory while B was signed in")
        }
    }

    /// The page went away after the transport had already returned: the answer is not written.
    func testACancelledScorecardLoadNeverWritesAnAnswerThatStillArrived() async throws {
        let ref = "cancelled-\(UUID().uuidString)"
        let release = DispatchSemaphore(value: 0)
        let paths = Paths()
        let client = heldClient(release: release, paths: paths)
        let pending = Task { @MainActor () -> Bool in
            if case .cancelled = await RoundReviewFreshLoad.detail(
                client, roundRef: ref, globalId: nil, backGlobalId: nil, nine: nil, teeBox: nil
            ) { return true }
            return false
        }
        try await waitForRequest(paths)
        release.signal()
        Thread.sleep(forTimeInterval: 0.3)
        pending.cancel()
        let cancelled = await pending.value
        XCTAssertTrue(cancelled)
        XCTAssertNil(RoundReviewDiskCache.loadDetail(roundRef: ref))
    }

    /// The same for a hole's shot map loaded through the review repository.
    func testAShotMapAnswerForAPreviousPlayerIsNeitherWrittenNorShown() async throws {
        let ref = "map-\(UUID().uuidString)"
        let release = DispatchSemaphore(value: 0)
        let paths = Paths()
        _ = heldClient(release: release, paths: paths)
        URLProtocol.registerClass(CapturingURLProtocol.self)
        defer { URLProtocol.unregisterClass(CapturingURLProtocol.self) }
        let repository = RoundShotMapRepository(roundRef: ref, apiBaseURL: URL(string: "https://review-cache.example.test")!, adminToken: nil)

        let pending = Task { @MainActor in await repository.load(3) }
        try await waitForRequest(paths)
        player.set("player-b")
        release.signal()
        await pending.value
        XCTAssertNil(repository.map(for: 3), "A's map is not shown under B")
        XCTAssertNil(RoundReviewDiskCache.loadShotMap(roundRef: ref, hole: 3))
        player.set("player-a")
        XCTAssertNil(RoundReviewDiskCache.loadShotMap(roundRef: ref, hole: 3))
    }

    func testACancelledShotMapLoadNeverWritesAnAnswerThatStillArrived() async throws {
        let ref = "map-cancelled-\(UUID().uuidString)"
        let release = DispatchSemaphore(value: 0)
        let paths = Paths()
        _ = heldClient(release: release, paths: paths)
        URLProtocol.registerClass(CapturingURLProtocol.self)
        defer { URLProtocol.unregisterClass(CapturingURLProtocol.self) }
        let repository = RoundShotMapRepository(roundRef: ref, apiBaseURL: URL(string: "https://review-cache.example.test")!, adminToken: nil)

        let pending = Task { @MainActor in await repository.load(3) }
        try await waitForRequest(paths)
        release.signal()
        Thread.sleep(forTimeInterval: 0.3)
        pending.cancel()
        await pending.value
        XCTAssertNil(RoundReviewDiskCache.loadShotMap(roundRef: ref, hole: 3))
    }
}
