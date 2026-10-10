import XCTest
@testable import AICaddie

/// Every cached hole map of the live round reaches the Watch (field report 2026-10-10: the Watch sat
/// on "地图准备中" because only the hole on the phone's screen was ever sent).
@MainActor
final class WatchTopoSenderTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("watch-topo-\(UUID().uuidString)", isDirectory: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private final class Recorder {
        var cached = Set<Int>()
        var accepts = true
        var sent: [Int] = []
        var package: LiveRoundPackage?
    }

    private func sender(_ recorder: Recorder, retries: [UInt64] = [1_000_000, 1_000_000]) -> WatchTopoSender {
        let sender = WatchTopoSender(
            load: { item in recorder.cached.contains(item.roundHole) ? validOnePixelPNGData() : nil },
            enqueue: { item, _ in
                guard recorder.accepts else { return false }
                recorder.sent.append(item.roundHole)
                return true
            },
            livePackage: { recorder.package }
        )
        sender.retryDelaysNanoseconds = retries
        return sender
    }

    func testThePlanKeysEachHoleAsTheWatchLooksItUp() throws {
        let package = try LiveRoundPackageFixture.package()
        let plan = WatchTopoSender.plan(for: package)
        XCTAssertEqual(plan.map(\.roundHole), package.holes.map(\.number))
        for (item, hole) in zip(plan, package.holes) {
            XCTAssertEqual(item.globalId, hole.sourceGlobalId)
            XCTAssertEqual(item.localHole, hole.sourceLocalHole)
            XCTAssertEqual(
                item.revision,
                package.coursePrep?.holes.first(where: { $0.hole == hole.number })?.geometryRevision ?? hole.geometryRevision
            )
        }
    }

    func testEveryCachedHoleIsSentOnceAndALaterBitmapFollows() async throws {
        let recorder = Recorder()
        recorder.package = try LiveRoundPackageFixture.package()
        recorder.cached = [1, 2, 3]
        let sender = sender(recorder)

        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1, 2, 3])

        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1, 2, 3], "nothing is sent twice")

        recorder.cached.insert(4)
        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1, 2, 3, 4], "a bitmap that arrives later is sent on the next pass")
    }

    func testASessionThatCannotTakeItYetGetsItLater() async throws {
        let recorder = Recorder()
        recorder.package = try LiveRoundPackageFixture.package()
        recorder.cached = [1]
        recorder.accepts = false
        let sender = sender(recorder)

        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [])

        recorder.accepts = true
        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1])
    }

    /// No other trigger: the failed hole is retried on its own, a bounded number of times.
    func testAFailedTransferIsRetriedWithoutAnotherTriggerAndBounded() async throws {
        let recorder = Recorder()
        recorder.package = try LiveRoundPackageFixture.package()
        recorder.cached = [1, 2]
        let sender = sender(recorder, retries: [1_000_000, 1_000_000])
        let globalId = try XCTUnwrap(recorder.package?.holes.first?.sourceGlobalId)

        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1, 2])

        for expected in [[1, 2, 1], [1, 2, 1, 1]] {
            sender.transferFailed(globalId: globalId, roundHole: 1)
            await sender.waitUntilIdle()
            XCTAssertEqual(recorder.sent, expected)
        }
        sender.transferFailed(globalId: globalId, roundHole: 1)
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1, 2, 1, 1], "two retries, then no more")

        sender.forgetSent()
        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1, 2, 1, 1, 1, 2], "a re-activated session gets the round again")
    }

    func testARetryForARoundThatEndedOrChangedSendsNothingOfIt() async throws {
        let recorder = Recorder()
        let first = try LiveRoundPackageFixture.package()
        recorder.package = first
        recorder.cached = [1]
        let sender = sender(recorder, retries: [20_000_000])
        let globalId = try XCTUnwrap(first.holes.first?.sourceGlobalId)

        sender.sync()
        await sender.waitUntilIdle()
        sender.transferFailed(globalId: globalId, roundHole: 1)
        recorder.package = nil
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1], "the round ended before the retry")

        recorder.package = first.rebasedForOfflineStart(roundId: "watch-topo-next-round")
        XCTAssertNotEqual(recorder.package?.roundId, first.roundId)
        sender.sync()
        await sender.waitUntilIdle()
        XCTAssertEqual(recorder.sent, [1, 1], "a new round starts from nothing sent")
    }

    /// Codex review: the Watch session activates before any round, the phone resumes a cached round
    /// whose network refresh fails (no download pass), and its maps on disk still go to the Watch.
    func testACachedRoundResumedOfflineSendsItsMapsWithoutADownloadPass() async throws {
        let store = OfflineStore(directoryURL: directory)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        try store.saveRoundPackage(package)
        try store.saveActiveHole(roundId: package.roundId, hole: 1)
        try store.appendEvent(LiveRoundEvent(
            eventId: "resume-score",
            roundId: package.roundId,
            clientId: "ios-phone",
            timestamp: "2026-10-10T07:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        ))
        for item in WatchTopoSender.plan(for: package).prefix(3) {
            XCTAssertTrue(try store.saveCourseTopoImage(
                validOnePixelPNGData(),
                globalId: item.globalId,
                localHole: item.localHole,
                geometryRevision: item.revision
            ))
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        CapturingURLProtocol.requestHandler = { request in
            (HTTPURLResponse(url: try XCTUnwrap(request.url), statusCode: 503, httpVersion: nil, headerFields: nil)!,
             Data(#"{"detail":"offline"}"#.utf8))
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: SyncClient(
                baseURL: URL(string: "https://offline.example.test")!,
                session: URLSession(configuration: configuration),
                retrySleep: { _ in }
            )
        )
        var sent: [WatchTopoSender.Item] = []
        let sender = try XCTUnwrap(model.watchTopoSender)
        sender.enqueue = { item, _ in sent.append(item); return true }

        await model.bootstrap()
        await sender.waitUntilIdle()

        XCTAssertEqual(model.package?.roundId, package.roundId)
        XCTAssertEqual(sent, Array(WatchTopoSender.plan(for: package).prefix(3)))
    }
}
