@testable import AICaddie
import XCTest

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
