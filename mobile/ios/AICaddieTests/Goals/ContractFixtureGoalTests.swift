// size: medium
// goals: I-03, I-08, I-10
import XCTest
@testable import AICaddie

/// The shared contract fixtures under mobile/contracts/fixtures are the cross-client source of
/// truth (the backend and Python contract tests read the same files). These tests read them in
/// place and hold the phone's event builder, local queue, upload body and package download to them.
final class ContractFixtureGoalTests: XCTestCase {
    private var directories: [URL] = []

    override func setUp() {
        super.setUp()
        ensureC156TopoBundleStub()
    }

    override func tearDown() {
        for directory in directories {
            try? FileManager.default.removeItem(at: directory)
        }
        directories = []
        super.tearDown()
    }

    // MARK: - live_round_event.fixture.json

    // goals: I-08
    func testPhoneScoreEventBuilderProducesTheSharedEventFixture() throws {
        let data = try Data(contentsOf: ContractFixtureFile.url("live_round_event.fixture.json"))
        let fixture = try ContractFixtureFile.object(data)
        let fixtureEvent = try JSONDecoder().decode(LiveRoundEvent.self, from: data)
        let fixturePayload = try XCTUnwrap(fixture["payload"] as? [String: Any])
        let strokes = try XCTUnwrap(fixturePayload["strokes"] as? Int)
        let createdAt = try XCTUnwrap(ISO8601DateFormatter().date(from: fixtureEvent.timestamp))

        let built = LiveRoundEventBuilder(
            roundId: fixtureEvent.roundId,
            idFactory: { fixtureEvent.eventId },
            now: { createdAt }
        ).makeScoreEvent(hole: fixtureEvent.hole, strokes: strokes)
        XCTAssertEqual(built.kind, fixtureEvent.kind)

        var produced = try ContractFixtureFile.object(JSONEncoder().encode(built))
        // The builder stamps its author, an optional contract field the fixture omits.
        XCTAssertEqual(produced.removeValue(forKey: "clientId") as? String, "ios-phone")
        let producedPayload = try XCTUnwrap(produced.removeValue(forKey: "payload") as? [String: Any])
        var expected = fixture
        var expectedPayload = try XCTUnwrap(expected.removeValue(forKey: "payload") as? [String: Any])
        // The fixture's payload.source only names where the fixture came from; a phone score has none.
        XCTAssertEqual(expectedPayload.removeValue(forKey: "source") as? String, "fixture")

        XCTAssertEqual(produced as NSDictionary, expected as NSDictionary)
        XCTAssertEqual(producedPayload as NSDictionary, expectedPayload as NSDictionary)
    }

    // goals: I-10
    func testSharedEventFixtureIsQueuedLocallyAndUploadedInContractShape() async throws {
        let data = try Data(contentsOf: ContractFixtureFile.url("live_round_event.fixture.json"))
        let fixture = try ContractFixtureFile.object(data)
        let event = try JSONDecoder().decode(LiveRoundEvent.self, from: data)

        // Recorded locally first: the queue keeps the contract event exactly.
        let store = makeStore()
        try store.appendEvent(event)
        let pending = try store.loadPendingEvents(roundId: event.roundId)
        XCTAssertEqual(pending, [event])

        // Then uploaded: the request body carries the same contract object.
        let bodies = ContractBodyLog()
        let scope = CapturingURLProtocolScope { request in
            let url = try XCTUnwrap(request.url)
            let body = try CapturingURLProtocol.requestBodyData(from: request)
            bodies.append(body)
            let batch = try JSONDecoder().decode(EventBatch.self, from: body)
            let reply = try JSONEncoder().encode(SyncResult(
                accepted: batch.events.count, duplicate: false,
                acceptedEventIds: batch.events.map(\.eventId), serverSequence: 1
            ))
            return (
                HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil,
                                headerFields: ["Content-Type": "application/json"])!,
                reply
            )
        }
        let urlSession = URLSession(configuration: scope.configuration())
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract-goal.example.test")),
            clientId: "ios-phone", session: urlSession, retrySleep: { _ in }
        )

        let result = try await client.postEventBatch(
            pending, roundId: event.roundId, idempotencyKey: "contract-fixture-upload"
        )
        XCTAssertEqual(result.acceptedEventIds, [event.eventId])
        let sentBodies = bodies.values
        XCTAssertEqual(sentBodies.count, 1)
        let sent = try ContractFixtureFile.object(try XCTUnwrap(sentBodies.first))
        XCTAssertEqual(sent["roundId"] as? String, event.roundId)
        let sentEvents = try XCTUnwrap(sent["events"] as? [[String: Any]])
        XCTAssertEqual(sentEvents.count, 1)
        XCTAssertEqual(try XCTUnwrap(sentEvents.first) as NSDictionary, fixture as NSDictionary)

        client.invalidateForTesting()
        urlSession.invalidateAndCancel()
        withExtendedLifetime(scope) {}
    }

    // MARK: - live_round_package.fixture.json

    // goals: I-03
    func testSharedPackageFixtureDecodesWithItsRoundIdentityIntact() throws {
        let data = try Data(contentsOf: ContractFixtureFile.url("live_round_package.fixture.json"))
        let raw = try ContractFixtureFile.object(data)
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: data).validatedRoundIdentity()

        XCTAssertEqual(package.schema, LiveRoundPackage.supportedSchema)
        XCTAssertEqual(package.schema, raw["schema"] as? String)
        XCTAssertEqual(package.roundId, raw["roundId"] as? String)
        XCTAssertEqual(package.loopKey, raw["loopKey"] as? String)
        XCTAssertEqual(package.caddieDecisionEndpoint, raw["caddieDecisionEndpoint"] as? String)

        let rawCourse = try XCTUnwrap(raw["course"] as? [String: Any])
        XCTAssertEqual(package.course.globalId, rawCourse["globalId"] as? Int)
        XCTAssertEqual(package.course.name, rawCourse["name"] as? String)
        XCTAssertEqual(package.course.teeBox, rawCourse["teeBox"] as? String)

        let rawHoles = try XCTUnwrap(raw["holes"] as? [[String: Any]])
        XCTAssertFalse(rawHoles.isEmpty)
        XCTAssertEqual(package.holes.map(\.number), rawHoles.compactMap { $0["number"] as? Int })
        XCTAssertEqual(package.holes.map(\.par), rawHoles.compactMap { $0["par"] as? Int })
        XCTAssertEqual(package.holes.map(\.sourceGlobalId), rawHoles.compactMap { $0["sourceGlobalId"] as? Int })
        XCTAssertEqual(package.holes.map(\.sourceLocalHole), rawHoles.compactMap { $0["sourceLocalHole"] as? Int })
        XCTAssertEqual(
            package.holes.map(\.courseHoleNumber), rawHoles.compactMap { $0["courseHoleNumber"] as? Int }
        )

        let rawLoops = try XCTUnwrap(raw["roundLoops"] as? [[String: Any]])
        XCTAssertEqual(package.roundLoops.count, rawLoops.count)
        for (loop, rawLoop) in zip(package.roundLoops, rawLoops) {
            XCTAssertEqual(loop.globalId, rawLoop["globalId"] as? Int)
            XCTAssertEqual(loop.half, rawLoop["half"] as? String)
            XCTAssertEqual(loop.roundStartHole, rawLoop["roundStartHole"] as? Int)
            XCTAssertEqual(loop.holeCount, rawLoop["holeCount"] as? Int)
        }
        // Every round hole belongs to a loop and keeps its course presentation number.
        for hole in package.holes {
            XCTAssertNotNil(package.loop(containingRoundHole: hole.number), "hole \(hole.number)")
            XCTAssertEqual(package.courseHoleNumber(forRoundHole: hole.number), hole.courseHoleNumber)
        }
    }

    // goals: I-03
    func testSharedPackageFixtureDownloadsAndInstallsAsTheCurrentRound() async throws {
        let data = try Data(contentsOf: ContractFixtureFile.url("live_round_package.fixture.json"))
        let decoded = try JSONDecoder().decode(LiveRoundPackage.self, from: data)
        let scope = CapturingURLProtocolScope { request in
            let url = try XCTUnwrap(request.url)
            let isPackage = url.path.hasSuffix("/courses/\(decoded.course.globalId)/package")
            return (
                HTTPURLResponse(url: url, statusCode: isPackage ? 200 : 404, httpVersion: nil,
                                headerFields: ["Content-Type": "application/json"])!,
                isPackage ? data : Data("{}".utf8)
            )
        }
        let urlSession = URLSession(configuration: scope.configuration())
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://contract-goal.example.test")),
            clientId: "ios-phone", session: urlSession, retrySleep: { _ in }
        )

        let fetched = try await client.fetchCoursePackage(
            globalId: decoded.course.globalId,
            roundId: decoded.roundId,
            teeBox: decoded.course.teeBox,
            loops: decoded.roundLoops.map(\.entry)
        )
        XCTAssertEqual(fetched, decoded)

        let store = makeStore()
        let installed = try store.saveRoundPackage(fetched)
        XCTAssertEqual(installed, decoded)
        XCTAssertEqual(try store.loadCurrentRoundPackage(), decoded)
        XCTAssertEqual(try store.loadRoundPackage(roundId: decoded.roundId), decoded)

        client.invalidateForTesting()
        urlSession.invalidateAndCancel()
        withExtendedLifetime(scope) {}
    }

    // MARK: - helpers

    private func makeStore() -> OfflineStore {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        directories.append(directory)
        return OfflineStore(directoryURL: directory)
    }
}

/// Reads the shared fixtures in place; nothing is copied into the test bundle.
private enum ContractFixtureFile {
    static func url(_ name: String) -> URL {
        var root = URL(fileURLWithPath: #filePath)
        // file -> Goals -> AICaddieTests -> ios -> mobile
        for _ in 0..<4 { root.deleteLastPathComponent() }
        return root.appendingPathComponent("contracts/fixtures/\(name)")
    }

    static func object(_ data: Data) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}

/// Request bodies seen by the stub server, written from URLProtocol's thread.
private final class ContractBodyLog {
    private let lock = NSLock()
    private var bodies: [Data] = []

    func append(_ body: Data) {
        lock.lock()
        bodies.append(body)
        lock.unlock()
    }

    var values: [Data] {
        lock.lock()
        defer { lock.unlock() }
        return bodies
    }
}
