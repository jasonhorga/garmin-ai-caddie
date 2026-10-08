@testable import AICaddie
import XCTest

/// Every package request (`loops=` and `tee_box=`), in order (filled from the URLProtocol thread).
private final class LoopRequests: @unchecked Sendable {
    private let lock = NSLock()
    private var entries: [(loops: String, tee: String)] = []
    func append(loops: String, tee: String) { lock.withLock { entries.append((loops, tee)) } }
    var all: [String] { lock.withLock { entries.map(\.loops) } }
    func contains(loops: String, tee: String) -> Bool {
        lock.withLock { entries.contains { $0.loops == loops && $0.tee == tee } }
    }
    func contains(tee: String) -> Bool { lock.withLock { entries.contains { $0.tee == tee } } }
}

/// B4b-2 offline acquisition acceptance. Not pre-seeded: the store starts with no v2 cache, the
/// player starts one half, the app itself acquires the whole-course template in the background,
/// the network then goes away and the app restarts. From that state the turn composes both the
/// opposite half (后→前) and the same half (后→后) — each equal to the server's table.
@MainActor
final class TemplateAcquisitionTests: XCTestCase {
    private struct Row: Decodable, Equatable {
        let number: Int
        let sourceGlobalId: Int
        let sourceLocalHole: Int
        let courseHoleNumber: Int
        let par: Int
    }

    private struct Table: Decodable {
        let roundLoops: [RoundLoop]
        let holes: [Row]
    }

    private struct Tables: Decodable {
        let globalId: Int
        let tables: [String: Table]
    }

    private struct Oracle {
        let globalId: Int
        let tables: [String: Table]
        /// Server responses by `loops=` query value.
        let responses: [String: Data]
        let roundId: String
    }

    private func oracle() throws -> Oracle {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: TemplateAcquisitionTests.self)
        #endif
        let url = try XCTUnwrap(
            bundle.url(forResource: "b4b2_server_loop_tables", withExtension: "json", subdirectory: "Fixtures")
                ?? bundle.url(forResource: "b4b2_server_loop_tables", withExtension: "json")
        )
        let data = try Data(contentsOf: url)
        let decoded = try JSONDecoder().decode(Tables.self, from: data)
        let raw = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        func payload(_ key: String) throws -> Data {
            try JSONSerialization.data(withJSONObject: try XCTUnwrap(raw[key]))
        }
        let gid = decoded.globalId
        let whole = try XCTUnwrap(raw["wholeCourseTemplate"] as? [String: Any])
        return Oracle(
            globalId: gid,
            tables: decoded.tables,
            responses: [
                "\(gid):front,\(gid):back": try payload("wholeCourseTemplate"),
                "\(gid):front": try payload("frontHalf"),
                "\(gid):back": try payload("backHalf"),
            ],
            roundId: try XCTUnwrap(whole["roundId"] as? String)
        )
    }

    private func rows(_ package: LiveRoundPackage?) -> [Row] {
        (package?.holes ?? []).sorted { $0.number < $1.number }.map {
            Row(
                number: $0.number,
                sourceGlobalId: $0.sourceGlobalId,
                sourceLocalHole: $0.sourceLocalHole,
                courseHoleNumber: $0.courseHoleNumber,
                par: $0.par
            )
        }
    }

    private nonisolated static func response(
        _ request: URLRequest,
        status: Int,
        body: Data
    ) throws -> (HTTPURLResponse, Data) {
        (
            HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: status,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!,
            body
        )
    }

    func testOneHalfStartAcquiresTheWholeCourseThenComposesEitherSecondLoopOffline() async throws {
        try await assertOneHalfAcquisition(serverEchoesRequestedRoundId: true)
    }

    /// The template is an asset source, never the live round's identity: even a template response
    /// that (wrongly) claims the live round's id cannot replace the active `G:back` round.
    func testWholeCourseTemplateNeverReplacesTheActiveOneHalfRound() async throws {
        try await assertOneHalfAcquisition(serverEchoesRequestedRoundId: false)
    }

    // MARK: - PR #389: the whole-course job is recorded at once and released within the session

    /// Online oracle server; the prep download asks for its own `prep-library-…` round id.
    private func serveOracle(_ oracle: Oracle, into requests: LoopRequests) {
        let gid = oracle.globalId
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            guard url.path == "/api/v2/mobile/courses/\(gid)/package" else {
                return try Self.response(request, status: 404, body: Data(#"{"detail":"not found"}"#.utf8))
            }
            let queryItems = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
            let loops = queryItems.first { $0.name == "loops" }?.value ?? ""
            let tee = queryItems.first { $0.name == "tee_box" }?.value ?? ""
            requests.append(loops: loops, tee: tee)
            guard let body = oracle.responses[loops] else {
                return try Self.response(request, status: 422, body: Data(#"{"detail":"loops"}"#.utf8))
            }
            guard let requestedRoundId = queryItems.first(where: { $0.name == "round_id" })?.value,
                  !requestedRoundId.isEmpty else {
                return try Self.response(request, status: 200, body: body)
            }
            var object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            object["roundId"] = requestedRoundId
            return try Self.response(request, status: 200, body: try JSONSerialization.data(withJSONObject: object))
        }
    }

    private func acquisitionModel(
        directory: URL,
        preferredRoundId: String? = nil,
        freshEntryReleaseFallbackNanoseconds: UInt64 = 60_000_000_000
    ) -> LiveRoundAppModel {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        return LiveRoundAppModel(
            offlineStore: OfflineStore(directoryURL: directory),
            // A test host, not a bundle default: `syncOnForeground` configures the club-bag sync
            // with it, and nothing here may reach a real backend.
            apiBaseURL: URL(string: "https://acquisition.example.test")!,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: preferredRoundId,
            syncClient: SyncClient(
                baseURL: URL(string: "https://acquisition.example.test")!,
                session: URLSession(configuration: configuration),
                retrySleep: { _ in }
            ),
            offlineGeometryRetryDelaysNanoseconds: [],
            freshEntryReleaseFallbackNanoseconds: freshEntryReleaseFallbackNanoseconds
        )
    }

    private func freshDirectory() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    }

    private func settleDownloads(_ model: LiveRoundAppModel) async {
        await model.waitForOfflineCourseDownloadForTesting()
        await model.waitForPrepCourseDownloadForTesting()
    }

    /// Live Native 37456686597 / 37247820045: the player left every hole before its first load
    /// settled, so `liveHoleInitialLoadDidFinish` never ran and the whole-course job was never
    /// queued — after a relaunch 备战 had no row for the course. The job must be durable as soon as
    /// the one-half round is published, while its download still waits for the first live hole.
    func testOneHalfStartQueuesTheWholeCourseDurablyWithoutTheFirstHoleCallback() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let directory = freshDirectory()
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let online = acquisitionModel(directory: directory)
        await online.prepareCourseRound(
            roundId: oracle.roundId,
            teeBox: "blue",
            loops: [RoundLoopEntry(globalId: gid, half: "back")]
        )
        XCTAssertEqual(online.package?.loopKey, "\(gid):back")
        // No `liveHoleInitialLoadDidFinish()`: every hole was left before its first load settled.
        let queued = try XCTUnwrap(
            online.prepCourseDownloads.first { $0.course.globalId == gid },
            "the one-half start must list its whole course in the prep library at once"
        )
        XCTAssertEqual(queued.phase, .queued)
        XCTAssertEqual(queued.totalHoles, 18)
        XCTAssertTrue(
            try OfflineStore(directoryURL: directory).loadPrepCourseDownloads().contains { $0.id == queued.id },
            "the queued whole-course job is durable before the first hole settles"
        )
        XCTAssertFalse(
            requests.all.contains("\(gid):front,\(gid):back"),
            "the whole-course download still waits behind the first live hole"
        )

        // The app is terminated mid-round and relaunched: the job resumes and installs.
        let relaunched = acquisitionModel(directory: directory, preferredRoundId: oracle.roundId)
        await relaunched.bootstrap()
        await relaunched.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(
            requests.all.contains("\(gid):front,\(gid):back"),
            "the relaunch resumes the queued whole-course job"
        )
        // The row survives the relaunch, so 备战 lists the course (RealFlowUITests:141). Its final
        // phase is not asserted: this fixture serves no per-hole prep or topo, so the job can
        // install the template but never reach `.ready` — the acquisition test below does not
        // assert it either.
        XCTAssertNotNil(
            relaunched.prepCourseDownloads.first { $0.id == queued.id },
            "备战 still lists the whole course after the relaunch"
        )
        XCTAssertEqual(
            try OfflineStore(directoryURL: directory).loadCourseTemplate(globalId: gid, teeBox: "blue")?.loopKey,
            "\(gid):front+\(gid):back"
        )
        XCTAssertEqual(relaunched.package?.loopKey, "\(gid):back", "the live round keeps its own identity")
    }

    /// The RCA user path, in one session: foreground, online, no first-hole callback, no relaunch
    /// and no foreground resume. Leaving the entry hole releases the download; the whole course is
    /// fetched and durable during the first loop, and the turn then composes offline.
    func testLeavingTheEntryHoleFetchesTheWholeCourseInTheSameSessionForAnOfflineTurn() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let roundId = oracle.roundId
        let directory = freshDirectory()
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: directory)
        await model.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        model.consumePendingLiveHole()
        model.setActiveHole(1)
        XCTAssertFalse(requests.all.contains("\(gid):front,\(gid):back"), "the entry hole keeps priority")
        XCTAssertNotNil(model.freshEntryReleaseGenerationForTesting)

        // Each hole is left before its first load settles: the callback never runs.
        model.setActiveHole(2)
        XCTAssertNil(model.freshEntryReleaseGenerationForTesting, "leaving the entry hole released it")
        for hole in 3...9 { model.setActiveHole(hole) }
        await settleDownloads(model)
        XCTAssertTrue(
            requests.all.contains("\(gid):front,\(gid):back"),
            "the canonical whole course is fetched during the first loop, in this session"
        )
        XCTAssertEqual(
            try OfflineStore(directoryURL: directory).loadCourseTemplate(globalId: gid, teeBox: "blue")?.loopKey,
            "\(gid):front+\(gid):back"
        )
        XCTAssertEqual(model.package?.loopKey, "\(gid):back", "the template never replaces the live loop")

        // The network goes away before the turn; the turn composes the opposite half offline.
        let store = OfflineStore(directoryURL: directory)
        for hole in 1...9 {
            try store.appendEvent(LiveRoundEvent(
                eventId: "release-\(hole)",
                roundId: roundId,
                timestamp: "2026-10-06T08:0\(hole):00Z",
                hole: hole,
                kind: .score,
                payload: ["score": .number(4)]
            ))
        }
        let requestsBeforeOffline = requests.all.count
        CapturingURLProtocol.requestHandler = { _ in throw URLError(.notConnectedToInternet) }
        await model.continueIntoSecondLoop(RoundLoopEntry(globalId: gid, half: "front"), roundId: roundId)
        XCTAssertEqual(model.package?.loopKey, "\(gid):back+\(gid):front")
        XCTAssertEqual(rows(model.package), oracle.tables["\(gid):back+\(gid):front"]?.holes)
        XCTAssertEqual(model.pendingLiveHole, 10)
        XCTAssertEqual(requests.all.count, requestsBeforeOffline, "no package request succeeded offline")
    }

    /// No live event at all (the player stays on a hole whose load never settles): the bounded
    /// fallback releases the download.
    func testFallbackReleasesTheWholeCourseWithoutAnyLiveEvent() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory(), freshEntryReleaseFallbackNanoseconds: 50_000_000)
        await model.prepareCourseRound(roundId: oracle.roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        XCTAssertNotNil(model.freshEntryReleaseGenerationForTesting)
        await model.waitForFreshEntryReleaseFallbackForTesting()
        XCTAssertNil(model.freshEntryReleaseGenerationForTesting)
        await settleDownloads(model)
        XCTAssertTrue(requests.all.contains("\(gid):front,\(gid):back"))
        XCTAssertEqual(model.package?.loopKey, "\(gid):back")
    }

    /// While the entry hole is still loading, re-selecting it and the real foreground hook do not
    /// start the all-hole pipeline or the durable whole-course row; its first load finishing does.
    func testTheEntryHoleKeepsPriorityOverTheRealForegroundHook() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        await model.prepareCourseRound(roundId: oracle.roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        model.consumePendingLiveHole()
        model.setActiveHole(1)
        let pending = try XCTUnwrap(model.freshEntryReleaseGenerationForTesting)
        model.syncOnForeground()
        await settleDownloads(model)
        XCTAssertEqual(model.freshEntryReleaseGenerationForTesting, pending, "the foreground hook keeps the gate")
        XCTAssertFalse(
            requests.contains(loops: "\(gid):front,\(gid):back", tee: "blue"),
            "a foreground return must not take the durable row ahead of the entry hole"
        )

        model.liveHoleInitialLoadDidFinish()
        XCTAssertNil(model.freshEntryReleaseGenerationForTesting)
        await settleDownloads(model)
        XCTAssertTrue(requests.contains(loops: "\(gid):front,\(gid):back", tee: "blue"))
    }

    /// A 备战 download the player starts during the entry hole runs at once; when that job finishes,
    /// the worker takes no further automatic job — not the round's whole-course row — until the
    /// fresh entry is released, and then continues. (The worker re-checks the gate before every
    /// job, so a worker that was already running when the round started behaves the same.)
    func testAPrepWorkerTakesOnlyThePlayersJobUntilTheFreshEntryIsReleased() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        await model.prepareCourseRound(roundId: oracle.roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        let pending = try XCTUnwrap(model.freshEntryReleaseGenerationForTesting)
        let roundRow = try XCTUnwrap(model.prepCourseDownloads.first { $0.course.globalId == gid && $0.teeBox == "blue" })

        model.downloadPrepCourse(MobileCourseOption(globalId: gid, name: "Prep white", holes: 18, teeBox: "white"))
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(requests.contains(tee: "white"), "the player's own 备战 job is never held behind the gate")
        XCTAssertEqual(model.freshEntryReleaseGenerationForTesting, pending)
        XCTAssertFalse(
            requests.contains(loops: "\(gid):front,\(gid):back", tee: "blue"),
            "after the player's job the worker must not take the fresh entry's whole-course job"
        )
        XCTAssertEqual(model.prepCourseDownloads.first { $0.id == roundRow.id }?.phase, .queued)

        model.consumePendingLiveHole()
        model.setActiveHole(2)
        await settleDownloads(model)
        XCTAssertTrue(
            requests.contains(loops: "\(gid):front,\(gid):back", tee: "blue"),
            "after the release the queue continues with the whole-course job"
        )
    }

    /// A requested 备战 job paused in the background during the entry hole resumes on the real
    /// foreground hook — making another request — without releasing the gate; the round's own
    /// row still waits.
    func testARequestedJobPausedAndResumedDuringTheEntryHoleKeepsItsExemption() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        await model.prepareCourseRound(roundId: oracle.roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        model.consumePendingLiveHole()
        model.setActiveHole(1)
        let pending = try XCTUnwrap(model.freshEntryReleaseGenerationForTesting)

        model.downloadPrepCourse(MobileCourseOption(globalId: gid, name: "Prep white", holes: 18, teeBox: "white"))
        let requested = try XCTUnwrap(model.prepCourseDownloads.first { $0.teeBox == "white" })
        // The background grace period expires before the worker gets to run.
        await model.cancelPrepCourseDownloadForTesting()
        XCTAssertEqual(model.prepCourseDownloads.first { $0.id == requested.id }?.phase, .queued)
        XCTAssertTrue(model.userRequestedPrepDownloadIDsForTesting.contains(requested.id))
        XCTAssertFalse(requests.contains(tee: "white"))

        model.syncOnForeground()
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(requests.contains(tee: "white"), "the resumed requested job makes its request")
        XCTAssertEqual(model.freshEntryReleaseGenerationForTesting, pending, "without releasing the gate")
        XCTAssertFalse(
            requests.contains(loops: "\(gid):front,\(gid):back", tee: "blue"),
            "the round's automatic row still waits"
        )
    }

    /// Requested-job intent is account-scoped: a rebind drops it with the previous library.
    func testAccountRebindDropsRequestedJobIntent() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        await model.prepareCourseRound(roundId: oracle.roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        model.downloadPrepCourse(MobileCourseOption(globalId: gid, name: "Prep white", holes: 18, teeBox: "white"))
        await model.cancelPrepCourseDownloadForTesting()
        XCTAssertFalse(model.userRequestedPrepDownloadIDsForTesting.isEmpty)

        // The rebind also binds the process-wide club-bag store; restore it for later tests.
        let previousClubBagPlayer = ClubBagStore.playerId
        defer { ClubBagSyncCoordinator.shared.activate(playerId: previousClubBagPlayer, migrateLegacy: false) }
        model.activateSession(
            AppSession(token: "token", playerId: "another-player", expiresAt: Date().addingTimeInterval(600)),
            migrateLegacyData: false
        )
        XCTAssertTrue(model.userRequestedPrepDownloadIDsForTesting.isEmpty)
        XCTAssertNil(model.freshEntryReleaseGenerationForTesting)
        await model.waitForPrepCourseDownloadForTesting()
    }

    /// A fallback armed for an earlier round can never release a later round's deferral.
    func testAStaleFallbackCannotReleaseANewRound() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        await model.prepareCourseRound(roundId: oracle.roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        let first = try XCTUnwrap(model.freshEntryReleaseGenerationForTesting)
        await model.prepareCourseRound(
            roundId: oracle.roundId + "-second",
            teeBox: "blue",
            loops: [RoundLoopEntry(globalId: gid, half: "back")]
        )
        let second = try XCTUnwrap(model.freshEntryReleaseGenerationForTesting)
        XCTAssertNotEqual(first, second)

        model.releaseFreshEntryForTesting(generation: first)
        XCTAssertEqual(model.freshEntryReleaseGenerationForTesting, second, "the stale fallback is ignored")
        XCTAssertFalse(requests.all.contains("\(gid):front,\(gid):back"))

        model.releaseFreshEntryForTesting(generation: second)
        XCTAssertNil(model.freshEntryReleaseGenerationForTesting)
        await settleDownloads(model)
        XCTAssertTrue(requests.all.contains("\(gid):front,\(gid):back"))
        XCTAssertEqual(model.package?.roundId, oracle.roundId + "-second")
    }

    // MARK: - Ready before the first tee: intent prefetch and resumable live downloads

    /// Settling on a course (开始一场 / 在这个球场) installs its whole-course template with the Tee
    /// Start will use, before any round exists.
    func testCourseIntentInstallsTheWholeCourseBeforeStart() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        model.prefetchIntendedCourses(
            [MobileCourseOption(globalId: gid, name: "Intent", holes: 18, teeBox: "blue")],
            teeBox: "white"
        )
        let row = try XCTUnwrap(model.prepCourseDownloads.first { $0.course.globalId == gid })
        XCTAssertTrue(row.isIntentPrefetch)
        XCTAssertEqual(row.teeBox, "white", "the template is keyed by the Tee Start will use")
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(requests.contains(loops: "\(gid):front,\(gid):back", tee: "white"))
        XCTAssertNil(model.package, "an intent never creates a round")
    }

    /// Tapping through the list: a newer intent drops the older one's unfinished row, so only the
    /// course the player settled on is fetched.
    func testANewerCourseIntentDropsAnUnfinishedOlderOne() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        let course = MobileCourseOption(globalId: gid, name: "Intent", holes: 18, teeBox: "blue")
        model.prefetchIntendedCourses([course], teeBox: "white")
        model.prefetchIntendedCourses([course], teeBox: "red")
        XCTAssertEqual(model.prepCourseDownloads.map(\.teeBox), ["red"])
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(requests.contains(tee: "red"))
        XCTAssertFalse(requests.contains(tee: "white"), "the superseded intent never made a request")
    }

    /// A 备战 download of the same course makes the row the player's: a later intent keeps it.
    func testThePlayersOwnDownloadAdoptsAnIntentRow() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        let course = MobileCourseOption(globalId: gid, name: "Intent", holes: 18, teeBox: "white")
        model.prefetchIntendedCourses([course], teeBox: "white")
        model.downloadPrepCourse(course)
        let adopted = try XCTUnwrap(model.prepCourseDownloads.first { $0.teeBox == "white" })
        XCTAssertFalse(adopted.isIntentPrefetch)
        model.prefetchIntendedCourses([course], teeBox: "red")
        XCTAssertNotNil(model.prepCourseDownloads.first { $0.id == adopted.id }, "the player's row stays")
        await model.waitForPrepCourseDownloadForTesting()
    }

    /// Live Native 37729778000: the home's intent prefetch held 开始一场's Tee request until Start
    /// timed out. An intent never starts while a foreground course request is in flight, and resumes
    /// on its own once the last one ends.
    func testAnIntentWaitsForForegroundCourseRequestsThenResumes() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        model.beginForegroundCourseRequestForTesting()
        model.beginForegroundCourseRequestForTesting()
        model.prefetchIntendedCourses(
            [MobileCourseOption(globalId: gid, name: "Intent", holes: 18, teeBox: "white")],
            teeBox: "white"
        )
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertFalse(requests.contains(tee: "white"), "no intent request while the Tee request is in flight")
        XCTAssertEqual(model.prepCourseDownloads.first { $0.teeBox == "white" }?.phase, .queued)

        model.endForegroundCourseRequestForTesting()
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertFalse(requests.contains(tee: "white"), "one foreground request is still in flight")

        model.endForegroundCourseRequestForTesting()
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(requests.contains(tee: "white"), "the intent resumes when the last one ends")
    }

    /// A 备战 job the player asked for is never held behind a foreground request.
    func testAForegroundRequestDoesNotHoldThePlayersOwnDownload() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        model.beginForegroundCourseRequestForTesting()
        model.downloadPrepCourse(MobileCourseOption(globalId: gid, name: "Prep", holes: 18, teeBox: "white"))
        await model.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(requests.contains(tee: "white"))
        model.endForegroundCourseRequestForTesting()
    }

    /// Course discovery stops the round's all-hole download; returning to the round's live view
    /// resumes it, and a finished pass is not restarted.
    func testDiscoveryStopsTheRoundsDownloadAndItsLiveViewResumesIt() async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let requests = LoopRequests()
        serveOracle(oracle, into: requests)
        defer { CapturingURLProtocol.requestHandler = nil }

        let model = acquisitionModel(directory: freshDirectory())
        await model.prepareCourseRound(roundId: oracle.roundId, teeBox: "blue", loops: [RoundLoopEntry(globalId: gid, half: "back")])
        model.consumePendingLiveHole()
        model.liveHoleInitialLoadDidFinish()
        XCTAssertEqual(model.offlineCourseDownloadRoundIdForTesting, oracle.roundId)

        model.prioritizeCourseDiscoveryForTesting()
        XCTAssertNil(model.offlineCourseDownloadRoundIdForTesting)
        XCTAssertEqual(model.interruptedOfflineCourseDownloadRoundIdForTesting, oracle.roundId)

        model.liveHoleInitialLoadDidFinish()
        XCTAssertNil(model.interruptedOfflineCourseDownloadRoundIdForTesting)
        XCTAssertEqual(model.offlineCourseDownloadRoundIdForTesting, oracle.roundId, "the live view resumes it")
        await settleDownloads(model)
        XCTAssertNil(model.offlineCourseDownloadRoundIdForTesting)

        model.prioritizeCourseDiscoveryForTesting()
        XCTAssertNil(
            model.interruptedOfflineCourseDownloadRoundIdForTesting,
            "a finished pass has nothing to resume"
        )
    }

    private func assertOneHalfAcquisition(serverEchoesRequestedRoundId: Bool) async throws {
        let oracle = try oracle()
        let gid = oracle.globalId
        let roundId = oracle.roundId
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let store = OfflineStore(directoryURL: directory)
        XCTAssertTrue(try store.loadCourseTemplates().isEmpty, "the run starts with no v2 cache")

        // Online: the package route answers exactly the `loops=` it is asked for.
        let lock = NSLock()
        var requestedLoops: [String] = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        let session = URLSession(configuration: configuration)
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            if url.path == "/api/v2/mobile/courses/\(gid)/package" {
                let queryItems = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
                let loops = queryItems.first { $0.name == "loops" }?.value ?? ""
                lock.withLock { requestedLoops.append(loops) }
                if let body = oracle.responses[loops] {
                    // Every oracle package carries the oracle round id; the server answers with
                    // the round the request names (the background prep download asks for its own
                    // `prep-library-…` id and must never claim the live round's id).
                    guard serverEchoesRequestedRoundId,
                          let requestedRoundId = queryItems.first(where: { $0.name == "round_id" })?.value,
                          !requestedRoundId.isEmpty else {
                        return try Self.response(request, status: 200, body: body)
                    }
                    var object = try XCTUnwrap(
                        JSONSerialization.jsonObject(with: body) as? [String: Any]
                    )
                    object["roundId"] = requestedRoundId
                    return try Self.response(
                        request,
                        status: 200,
                        body: try JSONSerialization.data(withJSONObject: object)
                    )
                }
                return try Self.response(request, status: 422, body: Data(#"{"detail":"loops"}"#.utf8))
            }
            return try Self.response(request, status: 404, body: Data(#"{"detail":"not found"}"#.utf8))
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let online = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: SyncClient(
                baseURL: URL(string: "https://acquisition.example.test")!,
                session: session,
                retrySleep: { _ in }
            ),
            offlineGeometryRetryDelaysNanoseconds: []
        )

        // One-half start: 后九 is published at once and entered on round hole 1 (course hole 10).
        let back = RoundLoopEntry(globalId: gid, half: "back")
        await online.prepareCourseRound(roundId: roundId, teeBox: "blue", loops: [back])
        XCTAssertEqual(online.package?.loopKey, "\(gid):back")
        XCTAssertEqual(rows(online.package), oracle.tables["\(gid):back"]?.holes)
        XCTAssertEqual(online.package?.courseHoleNumber(forRoundHole: 1), 10)
        XCTAssertNil(
            try store.loadCourseTemplate(globalId: gid, teeBox: "blue"),
            "one half is published immediately but is never the whole-course template"
        )

        // Background acquisition through the prep install job, then durable on disk.
        online.liveHoleInitialLoadDidFinish()
        await online.waitForOfflineCourseDownloadForTesting()
        await online.waitForPrepCourseDownloadForTesting()
        XCTAssertTrue(
            lock.withLock { requestedLoops }.contains("\(gid):front,\(gid):back"),
            "the canonical whole course must be fetched in the background"
        )
        let durable = try XCTUnwrap(
            OfflineStore(directoryURL: directory).loadCourseTemplate(globalId: gid, teeBox: "blue"),
            "the whole-course template must be durable before the network goes away"
        )
        XCTAssertEqual(durable.loopKey, "\(gid):front+\(gid):back")
        XCTAssertEqual(
            try store.loadRoundPackage(roundId: roundId)?.loopKey,
            "\(gid):back",
            "the durable live round keeps its own ordered identity after the template install"
        )
        XCTAssertEqual(online.package?.loopKey, "\(gid):back")
        XCTAssertEqual(rows(durable), oracle.tables["\(gid):front+\(gid):back"]?.holes)

        // The first loop is played.
        for hole in 1...9 {
            try store.appendEvent(LiveRoundEvent(
                eventId: "acq-\(hole)",
                roundId: roundId,
                timestamp: "2026-09-29T08:0\(hole):00Z",
                hole: hole,
                kind: .score,
                payload: ["score": .number(4)]
            ))
        }

        // Network gone; the app restarts from disk.
        let offlineRequestsBefore = lock.withLock { requestedLoops.count }
        CapturingURLProtocol.requestHandler = { _ in throw URLError(.notConnectedToInternet) }
        let offline = LiveRoundAppModel(
            offlineStore: OfflineStore(directoryURL: directory),
            apiBaseURL: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: roundId,
            syncClient: SyncClient(
                baseURL: URL(string: "https://acquisition.example.test")!,
                session: session,
                retrySleep: { _ in }
            ),
            offlineGeometryRetryDelaysNanoseconds: []
        )
        await offline.bootstrap()
        XCTAssertEqual(offline.liveRoundState?.roundId, roundId)
        XCTAssertEqual(offline.package?.loopKey, "\(gid):back")

        // 后→前: the opposite half, composed offline, equals the server table.
        let front = RoundLoopEntry(globalId: gid, half: "front")
        await offline.continueIntoSecondLoop(front, roundId: roundId)
        XCTAssertEqual(offline.package?.loopKey, "\(gid):back+\(gid):front")
        XCTAssertEqual(offline.package?.roundLoops, oracle.tables["\(gid):back+\(gid):front"]?.roundLoops)
        XCTAssertEqual(rows(offline.package), oracle.tables["\(gid):back+\(gid):front"]?.holes)
        XCTAssertEqual(offline.pendingLiveHole, 10, "the turn opens round hole 10")
        XCTAssertEqual(offline.package?.courseHoleNumber(forRoundHole: 10), 1, "shown as 第 1 洞")
        XCTAssertFalse(
            try XCTUnwrap(offline.package).isSecondLoopLocked(by: try store.loadEvents()),
            "nothing is recorded on round hole 10 yet"
        )

        // 后→后: the same half, still before hole 10 is played, from the same offline state.
        await offline.setSecondLoop(back, roundId: roundId)
        XCTAssertEqual(offline.package?.loopKey, "\(gid):back+\(gid):back")
        XCTAssertEqual(offline.package?.roundLoops, oracle.tables["\(gid):back+\(gid):back"]?.roundLoops)
        XCTAssertEqual(rows(offline.package), oracle.tables["\(gid):back+\(gid):back"]?.holes)
        XCTAssertEqual(
            lock.withLock { requestedLoops.count },
            offlineRequestsBefore,
            "no package request can have succeeded offline"
        )

        // The composition is durable: another restart restores the same ordered round.
        let restored = LiveRoundAppModel(
            offlineStore: OfflineStore(directoryURL: directory),
            apiBaseURL: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            preferredRoundId: roundId,
            syncClient: SyncClient(
                baseURL: URL(string: "https://acquisition.example.test")!,
                session: session,
                retrySleep: { _ in }
            ),
            offlineGeometryRetryDelaysNanoseconds: []
        )
        await restored.bootstrap()
        XCTAssertEqual(restored.package?.loopKey, "\(gid):back+\(gid):back")
        XCTAssertEqual(rows(restored.package), oracle.tables["\(gid):back+\(gid):back"]?.holes)
    }
}
