import Foundation
import XCTest
import AICaddieDomain
@testable import AICaddieWatch

/// B4b-2 §7 on the Watch (owner P1): an ordinary 18-hole course (`segmentHoles: 18`, no loop label)
/// starts on one ordered half and chooses the second half at the turn, online (`loops=G:a,G:b`) or
/// offline (projected from an installed template). Also covers the load-boundary validation of
/// durable templates (Codex P2).
@MainActor
final class WatchHalfStartTurnTests: XCTestCase {
    private static let courseId = 31795

    /// The CI fixture's Black Knight row from `/api/v2/mobile/courses/options`.
    private static let blackKnight = WatchCourseOption(
        globalId: courseId,
        name: "Black Knight B/C",
        holes: 18,
        teeBox: "blue",
        venueName: "Black Knight",
        segmentLabel: nil,
        segmentHoles: 18,
        latitude: 39.9,
        longitude: 116.4,
        tees: ["blue", "white"],
        roundCount: 1
    )

    private static let config = WatchRoundConfig(
        baseURL: URL(string: "https://caddie.example")!,
        adminToken: nil,
        sessionToken: "player-token"
    )

    /// A deterministic physical Par per physical hole, so a renumbered table is checkable.
    nonisolated static func isTemplateRequest(_ request: URLRequest) -> Bool {
        query(request, "round_id")?.hasPrefix("watch-template-") == true
    }

    private nonisolated static func physicalPar(_ local: Int) -> Int { [4, 5, 3][local % 3] }

    private final class RequestLog {
        var requests: [URLRequest] = []

        private var allPackageRequests: [URLRequest] {
            requests.filter { $0.url?.path.hasSuffix("/package") == true }
        }

        /// The active round's own package requests.
        var packageRequests: [URLRequest] {
            allPackageRequests.filter { !WatchHalfStartTurnTests.isTemplateRequest($0) }
        }

        /// Background whole-course template installs (their own `watch-template-…` request id).
        var templateRequests: [URLRequest] {
            allPackageRequests.filter { WatchHalfStartTurnTests.isTemplateRequest($0) }
        }
    }

    nonisolated static func query(_ request: URLRequest?, _ name: String) -> String? {
        guard let url = request?.url else { return nil }
        return URLComponents(url: url, resolvingAgainstBaseURL: false)?
            .queryItems?.first(where: { $0.name == name })?.value
    }

    /// A contract-valid package for `loops` (e.g. `31795:back,31795:front`), physical Par per hole.
    private nonisolated static func packageData(loops raw: String, roundId: String) -> Data {
        let loops = raw.split(separator: ",").compactMap { entry -> WatchPackageFixture.Loop? in
            let parts = entry.split(separator: ":")
            guard parts.count == 2, let id = Int(parts[0]) else { return nil }
            return WatchPackageFixture.Loop(id, String(parts[1]))
        }
        var overrides: [Int: String] = [:]
        for (index, loop) in loops.enumerated() {
            for offset in 0..<9 {
                let number = 1 + index * 9 + offset
                let local = loop.sourceStartHole + offset
                let courseHole = loop.half == "all" ? number : local
                overrides[number] = "{\"number\":\(number),\"par\":\(physicalPar(local)),"
                    + "\"yards\":\(300 + local),\"sourceGlobalId\":\(loop.globalId),"
                    + "\"sourceLocalHole\":\(local),\"courseHoleNumber\":\(courseHole)}"
            }
        }
        return WatchPackageFixture.packageData(
            roundId: roundId,
            course: #"{"globalId":31795,"name":"Black Knight","teeBox":"blue"}"#,
            loops: loops,
            overrides: overrides
        )
    }

    private func makeDirectory(_ label: String) -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(label)-\(UUID().uuidString)", isDirectory: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        return directory
    }

    /// The production library with the real `WatchBackendClient` request builder behind a stubbed
    /// transport that serves the ordered package the request names.
    private func makeLibrary(
        directory: URL,
        log: RequestLog,
        roundId: String = "watch-half-round",
        wholeTemplateAvailable: Bool = true
    ) -> WatchCourseLibrary {
        WatchCourseLibrary(
            store: WatchCourseStore(directoryURL: directory),
            imageStore: WatchHoleImageStore(directoryURL: directory),
            makeRoundId: { roundId },
            now: { "2026-09-29T00:00:00Z" },
            clientFactory: { config in
                WatchBackendClient(
                    baseURL: config.baseURL,
                    sessionToken: config.sessionToken,
                    dataLoader: { request in
                        log.requests.append(request)
                        let url = try XCTUnwrap(request.url)
                        guard url.path.hasSuffix("/package"),
                              let loops = Self.query(request, "loops"),
                              let round = Self.query(request, "round_id"),
                              wholeTemplateAvailable || !Self.isTemplateRequest(request) else {
                            return (Data(), HTTPURLResponse(
                                url: url, statusCode: 404, httpVersion: nil, headerFields: nil
                            )!)
                        }
                        return (Self.packageData(loops: loops, roundId: round), HTTPURLResponse(
                            url: url,
                            statusCode: 200,
                            httpVersion: nil,
                            headerFields: ["Content-Type": "application/json"]
                        )!)
                    },
                    retrySleep: { _ in }
                )
            }
        )
    }

    private func makeModel(directory: URL) -> WatchRoundModel {
        var counter = 0
        return WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            autoShotEnabled: false,
            persistAutoShotEnabled: { _ in },
            makeEventId: {
                counter += 1
                return "evt-\(counter)"
            },
            now: { "2026-09-29T00:00:00Z" }
        )
    }

    /// Score round hole 9 through the production flow; saving it reaches the turn.
    private func finishFirstNine(_ model: WatchRoundModel) {
        model.selectHole(9)
        model.startScoringActiveHole()
        model.startManualScoreEntry()
        model.saveManualScore()
    }

    private func table(_ states: [WatchRoundState]) -> [[Int]] {
        states.sorted { $0.hole < $1.hole }.map {
            [$0.hole, $0.globalId ?? -1, $0.sourceLocalHole ?? -1, $0.par]
        }
    }

    /// The server's `number → (sourceGlobalId, sourceLocalHole)` table (courseHoleNumber equals
    /// sourceLocalHole for a half) plus physical Par, from the decoded v2 package.
    private func serverTable(_ loops: String) throws -> [[Int]] {
        let package = try WatchBackendClient(baseURL: Self.config.baseURL)
            .decodeCoursePackage(Self.packageData(loops: loops, roundId: "server"))
        return package.holes.sorted { $0.number < $1.number }.map { hole -> [Int] in
            XCTAssertEqual(hole.courseHoleNumber, hole.sourceLocalHole)
            return [hole.number, hole.sourceGlobalId, hole.sourceLocalHole, hole.par]
        }
    }

    // MARK: - selection

    func testSelectionLoopKeysForAllSixEighteenHoleOrdersAndUnchangedNineHoleLoops() {
        let option = Self.blackKnight
        let cases: [(String?, String?, String, Int)] = [
            ("front", nil, "31795:front", 9),
            ("back", nil, "31795:back", 9),
            ("front", "back", "31795:front+31795:back", 18),
            ("back", "front", "31795:back+31795:front", 18),
            ("front", "front", "31795:front+31795:front", 18),
            ("back", "back", "31795:back+31795:back", 18),
        ]
        var keys = Set<String>()
        for (first, second, key, holes) in cases {
            let selection = WatchCourseSelection(
                front: option, teeBox: "blue", firstHalf: first, secondHalf: second
            )
            XCTAssertEqual(selection.loopKey, key)
            XCTAssertEqual(selection.loopsQuery, key.replacingOccurrences(of: "+", with: ","))
            XCTAssertEqual(selection.holeCount, holes)
            keys.insert(WatchCourseTemplate.cacheKey(loopKey: selection.loopKey, teeBox: "blue"))
        }
        XCTAssertEqual(keys.count, 6, "every ordered half keeps its own template cache key")

        // Without a half an 18-hole selection is the canonical whole-course template.
        let whole = WatchCourseSelection(front: option, teeBox: "blue")
        XCTAssertNil(whole.firstHalf)
        XCTAssertEqual(whole.loopKey, "31795:front+31795:back")

        // Nine-hole loops are unchanged, and a half never applies to them.
        let loopA = WatchCourseOption(globalId: 7001, name: "组合 ~ A", holes: 18, teeBox: "Blue", segmentHoles: 9)
        let loopB = WatchCourseOption(globalId: 7002, name: "组合 ~ B", holes: 9, teeBox: "Blue", segmentHoles: 9)
        XCTAssertEqual(WatchCourseSelection(front: loopA, teeBox: "Blue", firstHalf: "back").loopKey, "7001:all")
        XCTAssertEqual(WatchCourseSelection(front: loopA, back: loopB, teeBox: "Blue").loopsQuery, "7001:all,7002:all")
        XCTAssertEqual(WatchCourseSelection(front: loopA, back: loopA, teeBox: "Blue").loopKey, "7001:all+7001:all")

        XCTAssertEqual(WatchCourseSelection.halfLoop(loopKey: "31795:back+31795:front")?.halves, ["back", "front"])
        XCTAssertNil(WatchCourseSelection.halfLoop(loopKey: "7001:all"))
        XCTAssertNil(WatchCourseSelection.halfLoop(loopKey: "31795:back+7002:front"))
    }

    // MARK: - start one half

    func testBackNineStartRequestsOnlyTheBackHalfAndRestoresItsLoopKey() async throws {
        let directory = makeDirectory("watch-back-start")
        let log = RequestLog()
        let library = makeLibrary(directory: directory, log: log)
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")

        // The request the production client builds for this selection.
        let built = try WatchBackendClient(baseURL: Self.config.baseURL).makeCoursePackageRequest(
            globalId: selection.front.globalId,
            roundId: "r",
            teeBox: selection.teeBox,
            loops: selection.loopsQuery
        )
        XCTAssertEqual(Self.query(built, "loops"), "31795:back")

        let started = await library.startCourse(selection, config: Self.config)
        let prepared = try XCTUnwrap(started)
        XCTAssertEqual(log.packageRequests.count, 1)
        XCTAssertEqual(log.packageRequests.first?.url?.path, "/api/v2/mobile/courses/31795/package")
        XCTAssertEqual(Self.query(log.packageRequests.first, "loops"), "31795:back")
        XCTAssertEqual(Self.query(log.packageRequests.first, "tee_box"), "blue")
        XCTAssertEqual(prepared.holeStates.map(\.hole), Array(1...9))
        XCTAssertEqual(prepared.holeStates.map(\.sourceLocalHole), Array(10...18).map { Optional($0) })
        XCTAssertEqual(table(prepared.holeStates), try serverTable("31795:back"))

        let cached = try XCTUnwrap(WatchCourseStore(directoryURL: directory).course(loopKey: "31795:back", teeBox: "blue"))
        XCTAssertEqual(cached.loopKey, "31795:back")
        XCTAssertEqual(WatchCourseSelection(template: cached).loopsQuery, "31795:back",
                       "the restore/upgrade path re-requests the same half")
        // The active start requested only its half; the whole-course template for an offline turn
        // arrives separately in the background under its own request id and cache key.
        await library.waitForWholeCourseTemplateInstalls()
        XCTAssertEqual(log.packageRequests.map { Self.query($0, "loops") }, ["31795:back"])
        XCTAssertFalse(log.templateRequests.isEmpty)
        XCTAssertTrue(log.templateRequests.allSatisfy { Self.query($0, "loops") == "31795:front,31795:back" })
        XCTAssertNotNil(WatchCourseStore(directoryURL: directory).course(loopKey: "31795:front+31795:back", teeBox: "blue"))
        XCTAssertEqual(WatchCourseStore(directoryURL: directory).course(loopKey: "31795:back", teeBox: "blue")?.loopKey, "31795:back")

        // Starting 后九 persists round loopKey `G:back`; a relaunch restores it.
        let roundDirectory = makeDirectory("watch-back-round")
        let model = makeModel(directory: roundDirectory)
        model.seedRound(
            prepared.holeStates,
            activeHole: prepared.holeStates.first?.hole,
            courseName: prepared.courseName,
            courseGlobalId: selection.front.globalId,
            teeBox: selection.teeBox,
            loopKey: selection.loopKey
        )
        let relaunched = makeModel(directory: roundDirectory)
        XCTAssertEqual(relaunched.round?.loopKey, "31795:back")
        XCTAssertEqual(relaunched.holeCount, 9)
        XCTAssertEqual(relaunched.round?.holeStates.map(\.sourceLocalHole), Array(10...18).map { Optional($0) })
    }

    func testImmediateBackNineStartIsProvisionalOnThePhysicalBackHalf() throws {
        let directory = makeDirectory("watch-back-immediate")
        let library = makeLibrary(directory: directory, log: RequestLog())
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")

        let prepared = try XCTUnwrap(library.startCourseImmediately(selection))

        XCTAssertEqual(prepared.holeStates.map(\.hole), Array(1...9))
        XCTAssertEqual(prepared.holeStates.map(\.sourceLocalHole), Array(10...18).map { Optional($0) })
        XCTAssertTrue(prepared.holeStates.allSatisfy { $0.geometryCoverage == "pending" })
        let template = try XCTUnwrap(
            WatchCourseStore(directoryURL: directory).course(loopKey: "31795:back", teeBox: "blue"),
            "the provisional half survives a relaunch and passes load validation"
        )
        XCTAssertEqual(template.expectedHoleCount, 9)
    }

    // MARK: - the turn

    func testOnlineTurnFromBackToFrontRequestsBothHalvesAndKeepsTheRound() async throws {
        let directory = makeDirectory("watch-turn-online")
        let log = RequestLog()
        let library = makeLibrary(directory: directory, log: log)
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let started = await library.startCourse(selection, config: Self.config)
        let prepared = try XCTUnwrap(started)

        let roundDirectory = makeDirectory("watch-turn-online-round")
        let model = makeModel(directory: roundDirectory)
        model.secondLoopLoader = { request in
            await library.secondLoop(request, config: Self.config)
        }
        model.seedRound(
            prepared.holeStates,
            activeHole: 1,
            courseName: prepared.courseName,
            courseGlobalId: Self.courseId,
            teeBox: "blue",
            loopKey: selection.loopKey
        )
        finishFirstNine(model)

        XCTAssertEqual(model.screen, .turn, "saving round hole 9 of a half reaches the turn")
        XCTAssertEqual(model.turnPlan?.second, .loop("31795:front"), "the other half is preselected")
        let eventsBefore = try XCTUnwrap(model.round?.pendingEvents)
        XCTAssertFalse(eventsBefore.isEmpty)
        let roundId = try XCTUnwrap(model.round?.roundId)

        await model.confirmTurn()

        XCTAssertEqual(Self.query(log.packageRequests.last, "loops"), "31795:back,31795:front")
        XCTAssertEqual(Self.query(log.packageRequests.last, "round_id"), roundId)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.turnPlan)
        XCTAssertEqual(model.activeHole, 10)
        // The round coordinate is 10–18; the Watch shows the physical 前九 numbers 1–9.
        XCTAssertEqual(model.activeDisplayHoleNumber, 1)
        XCTAssertEqual(model.displayHoleNumber(10), 1)
        XCTAssertEqual(model.displayHoleNumber(18), 9)
        XCTAssertEqual(model.displayHoleNumber(1), 10)
        let round = try XCTUnwrap(model.round)
        XCTAssertEqual(round.roundId, roundId)
        XCTAssertEqual(round.loopKey, "31795:back+31795:front")
        XCTAssertEqual(round.pendingEvents, eventsBefore, "no pending event is lost at the turn")
        XCTAssertTrue(round.holeStates.allSatisfy { $0.roundId == roundId })
        XCTAssertGreaterThan(round.holeStates.first { $0.hole == 9 }?.score ?? 0, 0)
        XCTAssertEqual(table(round.holeStates), try serverTable("31795:back,31795:front"))
        XCTAssertEqual(round.holeStates.filter { $0.hole >= 10 }.map(\.sourceLocalHole), Array(1...9).map { Optional($0) })

        let relaunched = makeModel(directory: roundDirectory)
        XCTAssertEqual(relaunched.round?.loopKey, "31795:back+31795:front")
        XCTAssertEqual(relaunched.holeCount, 18)
        XCTAssertEqual(table(relaunched.round?.holeStates ?? []), try serverTable("31795:back,31795:front"))

        // A stale one-half phone seed for the same round cannot drop holes 10–18.
        relaunched.applyRoundSeed(WatchRoundSeed(
            roundId: roundId,
            courseName: "Black Knight",
            activeHole: 1,
            holes: (1...9).map {
                WatchRoundSeedHole(
                    hole: $0, par: Self.physicalPar(9 + $0), distanceM: nil,
                    globalId: Self.courseId, localHole: 9 + $0, courseHoleNumber: 9 + $0
                )
            },
            globalId: Self.courseId,
            teeBox: "blue",
            loopKey: "31795:back"
        ))
        XCTAssertEqual(relaunched.round?.loopKey, "31795:back+31795:front")
        XCTAssertEqual(table(relaunched.round?.holeStates ?? []), try serverTable("31795:back,31795:front"))
    }

    func testOfflineSameHalfTurnComposesFromTheInstalledHalf() async throws {
        let directory = makeDirectory("watch-turn-same-half")
        let library = makeLibrary(directory: directory, log: RequestLog())
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let started = await library.startCourse(selection, config: Self.config)
        let prepared = try XCTUnwrap(started)

        let roundDirectory = makeDirectory("watch-turn-same-half-round")
        let model = makeModel(directory: roundDirectory)
        // Offline: no config, so only installed physical holes may be used.
        model.secondLoopLoader = { request in await library.secondLoop(request, config: nil) }
        model.seedRound(prepared.holeStates, activeHole: 1, courseGlobalId: Self.courseId,
                        teeBox: "blue", loopKey: selection.loopKey)
        finishFirstNine(model)
        model.chooseTurnSecond(.loop("31795:back"))
        await model.confirmTurn()

        XCTAssertEqual(model.round?.loopKey, "31795:back+31795:back")
        XCTAssertEqual(table(model.round?.holeStates ?? []), try serverTable("31795:back,31795:back"))
        let relaunched = makeModel(directory: roundDirectory)
        XCTAssertEqual(relaunched.round?.loopKey, "31795:back+31795:back")
        XCTAssertEqual(table(relaunched.round?.holeStates ?? []), try serverTable("31795:back,31795:back"))
    }

    func testOfflineTurnFromBackToFrontProjectsTheInstalledWholeCourseTemplate() async throws {
        let directory = makeDirectory("watch-turn-offline")
        let store = WatchCourseStore(directoryURL: directory)
        // An earlier `G:front+G:back` download of the same course and Tee.
        let whole = try WatchBackendClient(baseURL: Self.config.baseURL)
            .decodeCoursePackage(Self.packageData(loops: "31795:front,31795:back", roundId: "download"))
        try store.save(WatchCourseTemplateBuilder.build(
            option: Self.blackKnight,
            package: whole,
            prepsByGlobalId: [:],
            selectedTee: "blue",
            cachedAt: "2026-09-28T00:00:00Z"
        ).template)
        let library = makeLibrary(directory: directory, log: RequestLog(), roundId: "watch-offline-back")

        // Offline start on 后九 composes the half from the whole-course template.
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let prepared = try XCTUnwrap(library.startCourseImmediately(selection))
        XCTAssertEqual(table(prepared.holeStates), try serverTable("31795:back"))

        let roundDirectory = makeDirectory("watch-turn-offline-round")
        let model = makeModel(directory: roundDirectory)
        model.secondLoopLoader = { request in await library.secondLoop(request, config: nil) }
        model.seedRound(prepared.holeStates, activeHole: 1, courseGlobalId: Self.courseId,
                        teeBox: "blue", loopKey: selection.loopKey)
        finishFirstNine(model)
        XCTAssertEqual(model.screen, .turn)
        await model.confirmTurn()

        XCTAssertEqual(model.round?.loopKey, "31795:back+31795:front")
        XCTAssertEqual(model.activeHole, 10)
        // The round coordinate is 10–18; the Watch shows the physical 前九 numbers 1–9.
        XCTAssertEqual(model.activeDisplayHoleNumber, 1)
        XCTAssertEqual(model.displayHoleNumber(10), 1)
        XCTAssertEqual(model.displayHoleNumber(18), 9)
        XCTAssertEqual(model.displayHoleNumber(1), 10)
        XCTAssertEqual(table(model.round?.holeStates ?? []), try serverTable("31795:back,31795:front"),
                       "the offline turn equals the server's ordered table")
        XCTAssertNotNil(
            WatchCourseStore(directoryURL: directory).course(loopKey: "31795:back+31795:front", teeBox: "blue"),
            "the composed ordered template is cached under its own key for upgrade/restore"
        )
        XCTAssertNotNil(
            WatchCourseStore(directoryURL: directory).course(loopKey: "31795:front+31795:back", teeBox: "blue"),
            "the canonical whole-course template stays separate"
        )
        let relaunched = makeModel(directory: roundDirectory)
        XCTAssertEqual(relaunched.round?.loopKey, "31795:back+31795:front")
        XCTAssertEqual(table(relaunched.round?.holeStates ?? []), try serverTable("31795:back,31795:front"))
    }

    func testOfflineTurnWithoutInstalledHolesStaysAtTheTurnWithAClearMessage() async throws {
        let directory = makeDirectory("watch-turn-unavailable")
        // The background whole-course template install fails, so nothing but 后九 is installed.
        let library = makeLibrary(directory: directory, log: RequestLog(), wholeTemplateAvailable: false)
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let started = await library.startCourse(selection, config: Self.config)
        let prepared = try XCTUnwrap(started)
        await library.waitForWholeCourseTemplateInstalls()
        XCTAssertNil(WatchCourseStore(directoryURL: directory).course(loopKey: "31795:front+31795:back", teeBox: "blue"))

        let model = makeModel(directory: makeDirectory("watch-turn-unavailable-round"))
        model.secondLoopLoader = { request in await library.secondLoop(request, config: nil) }
        model.seedRound(prepared.holeStates, activeHole: 1, courseGlobalId: Self.courseId,
                        teeBox: "blue", loopKey: selection.loopKey)
        finishFirstNine(model)
        await model.confirmTurn()

        XCTAssertEqual(model.screen, .turn)
        XCTAssertEqual(model.turnMessage, "离线：本机没有这座球场的整场下载，暂时无法接着打前九。联网后重试。")
        XCTAssertEqual(model.round?.loopKey, "31795:back")
        XCTAssertEqual(model.holeCount, 9, "holes are never invented")

        model.chooseTurnSecond(.stopAfterNine)
        await model.confirmTurn()
        XCTAssertEqual(model.screen, .finishing, "只打 9 洞 ends the round")
        XCTAssertEqual(model.round?.loopKey, "31795:back")
    }

    // MARK: - whole-course template acquisition against the server oracle (no pre-seed)

    /// `b4b2_server_loop_tables.json`: the real package route's output (a copy of
    /// `AICaddieTests/Fixtures`, regenerated by `tests/test_b4b2_loop_tables_fixture.py`).
    private nonisolated static func oracle() throws -> [String: Any] {
        let url = Bundle(for: WatchHalfStartTurnTests.self)
            .url(forResource: "b4b2_server_loop_tables", withExtension: "json")
            ?? URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .appendingPathComponent("b4b2_server_loop_tables.json")
        return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    /// The oracle's `number → (sourceGlobalId, sourceLocalHole, courseHoleNumber, par)` table.
    private func oracleTable(_ loopKey: String) throws -> [[Int]] {
        let tables = try XCTUnwrap(try Self.oracle()["tables"] as? [String: Any])
        let entry = try XCTUnwrap(tables[loopKey] as? [String: Any], loopKey)
        let holes = try XCTUnwrap(entry["holes"] as? [[String: Any]])
        return holes.map { hole in
            ["number", "sourceGlobalId", "sourceLocalHole", "courseHoleNumber", "par"].map {
                (hole[$0] as? Int) ?? -1
            }
        }.sorted { $0[0] < $1[0] }
    }

    private func roundTable(_ states: [WatchRoundState]) -> [[Int]] {
        states.sorted { $0.hole < $1.hole }.map {
            [$0.hole, $0.globalId ?? -1, $0.sourceLocalHole ?? -1, $0.courseHoleNumber ?? -1, $0.par]
        }
    }

    private static let oracleCourse = WatchCourseOption(
        globalId: 55555,
        name: "Course 55555",
        holes: 18,
        teeBox: "blue",
        venueName: "Course 55555",
        segmentLabel: nil,
        segmentHoles: 18,
        tees: ["blue"]
    )

    /// The production library behind a transport that answers exactly the oracle's `loops=`
    /// packages — or, `offline`, fails every request as the Watch does without a network.
    /// A controllable stand-in for the server: offline, prep served or not, and a gate that holds
    /// whole-course template requests until the test opens it.
    private final class OracleServer {
        var offline = false
        var servePrep = true
        var gateTemplates = false
        private(set) var waiting: CheckedContinuation<Void, Never>?

        init(offline: Bool = false) {
            self.offline = offline
        }

        func passGate() async {
            guard gateTemplates else { return }
            await withCheckedContinuation { continuation in
                waiting = continuation
            }
        }

        func openGate() {
            gateTemplates = false
            waiting?.resume()
            waiting = nil
        }

        /// Holds the next `/prep` request (the active half's priority prep) until opened.
        var gatePrep = false
        private(set) var prepWaiting: CheckedContinuation<Void, Never>?

        func passPrepGate() async {
            guard gatePrep else { return }
            await withCheckedContinuation { continuation in
                prepWaiting = continuation
            }
        }

        func openPrepGate() {
            gatePrep = false
            prepWaiting?.resume()
            prepWaiting = nil
        }
    }

    private func makeOracleLibrary(
        directory: URL,
        log: RequestLog,
        offline: Bool = false,
        server: OracleServer? = nil
    ) throws -> WatchCourseLibrary {
        let server = server ?? OracleServer(offline: offline)
        let oracle = try Self.oracle()
        let packages: [String: Data] = try [
            "55555:front,55555:back": "wholeCourseTemplate",
            "55555:front": "frontHalf",
            "55555:back": "backHalf",
        ].mapValues { key in
            try JSONSerialization.data(withJSONObject: try XCTUnwrap(oracle[key] as? [String: Any]))
        }
        return WatchCourseLibrary(
            store: WatchCourseStore(directoryURL: directory),
            imageStore: WatchHoleImageStore(directoryURL: directory),
            makeRoundId: { "watch-oracle-round" },
            now: { "2026-09-30T00:00:00Z" },
            clientFactory: { config in
                WatchBackendClient(
                    baseURL: config.baseURL,
                    sessionToken: config.sessionToken,
                    dataLoader: { request in
                        log.requests.append(request)
                        if server.offline { throw URLError(.notConnectedToInternet) }
                        if Self.isTemplateRequest(request) {
                            await server.passGate()
                        }
                        let url = try XCTUnwrap(request.url)
                        if url.path.hasSuffix("/prep") {
                            await server.passPrepGate()
                        }
                        if url.path.hasSuffix("/prep"), server.servePrep {
                            // The server's prep for a course without rendered geometry.
                            return (Data(#"{"globalId":55555,"clubs":[],"holes":[]}"#.utf8), HTTPURLResponse(
                                url: url,
                                statusCode: 200,
                                httpVersion: nil,
                                headerFields: ["Content-Type": "application/json"]
                            )!)
                        }
                        guard url.path.hasSuffix("/package"),
                              let loops = Self.query(request, "loops"),
                              let body = packages[loops] else {
                            return (Data(), HTTPURLResponse(
                                url: url, statusCode: 404, httpVersion: nil, headerFields: nil
                            )!)
                        }
                        return (body, HTTPURLResponse(
                            url: url,
                            statusCode: 200,
                            httpVersion: nil,
                            headerFields: ["Content-Type": "application/json"]
                        )!)
                    },
                    retrySleep: { _ in }
                )
            },
            retrySleep: { _ in }
        )
    }

    /// From an empty store: start 后九 online, let the background whole-course install finish,
    /// then relaunch offline and reach the turn after round hole 9.
    private func oracleRoundAtTheTurn(_ label: String) async throws -> WatchRoundModel {
        let courseDirectory = makeDirectory("\(label)-courses")
        let roundDirectory = makeDirectory("\(label)-round")
        XCTAssertTrue(WatchCourseStore(directoryURL: courseDirectory).loadCourses().isEmpty, "no pre-seed")

        let log = RequestLog()
        let online = try makeOracleLibrary(directory: courseDirectory, log: log)
        let selection = WatchCourseSelection(front: Self.oracleCourse, teeBox: "blue", firstHalf: "back")
        let started = await online.startCourse(selection, config: Self.config)
        let prepared = try XCTUnwrap(started)
        let model = makeModel(directory: roundDirectory)
        model.seedRound(prepared.holeStates, activeHole: 1, courseName: prepared.courseName,
                        courseGlobalId: 55555, teeBox: "blue", loopKey: selection.loopKey)
        XCTAssertEqual(roundTable(prepared.holeStates), try oracleTable("55555:back"))

        await online.waitForWholeCourseTemplateInstalls()
        XCTAssertEqual(log.packageRequests.map { Self.query($0, "loops") }, ["55555:back"],
                       "the active start requests only its half")
        XCTAssertTrue(log.templateRequests.contains { Self.query($0, "loops") == "55555:front,55555:back" })
        XCTAssertNotNil(
            WatchCourseStore(directoryURL: courseDirectory).course(loopKey: "55555:front+55555:back", teeBox: "blue"),
            "the canonical whole-course template is durable"
        )
        let persisted = try XCTUnwrap(WatchRoundStore(directoryURL: roundDirectory).load())
        XCTAssertEqual(persisted.loopKey, "55555:back", "the template never replaces the active round")
        XCTAssertEqual(persisted.roundId, prepared.roundId)
        XCTAssertEqual(persisted.holeStates.count, 9)

        // Relaunch without a network.
        let offline = try makeOracleLibrary(directory: courseDirectory, log: RequestLog(), offline: true)
        let relaunched = makeModel(directory: roundDirectory)
        relaunched.secondLoopLoader = { request in
            await offline.secondLoop(request, config: Self.config)
        }
        XCTAssertEqual(relaunched.round?.roundId, prepared.roundId)
        finishFirstNine(relaunched)
        XCTAssertEqual(relaunched.screen, .turn)
        return relaunched
    }

    func testFreshBackNineStartAcquiresTheWholeTemplateAndTurnsBackToFrontOffline() async throws {
        let model = try await oracleRoundAtTheTurn("oracle-back-front")
        let roundId = try XCTUnwrap(model.round?.roundId)
        XCTAssertEqual(model.turnPlan?.second, .loop("55555:front"))
        await model.confirmTurn()

        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.round?.roundId, roundId)
        XCTAssertEqual(model.round?.loopKey, "55555:back+55555:front")
        XCTAssertEqual(roundTable(model.round?.holeStates ?? []), try oracleTable("55555:back+55555:front"))
    }

    func testFreshBackNineStartAcquiresTheWholeTemplateAndRepeatsTheBackNineOffline() async throws {
        let model = try await oracleRoundAtTheTurn("oracle-back-back")
        model.chooseTurnSecond(.loop("55555:back"))
        await model.confirmTurn()

        XCTAssertEqual(model.round?.loopKey, "55555:back+55555:back")
        XCTAssertEqual(roundTable(model.round?.holeStates ?? []), try oracleTable("55555:back+55555:back"))
    }

    // MARK: - the production start sequence (AICaddieWatchApp onStartCourse + activeCourseUpgradeKey)

    private func identityTable(_ rows: [[Int]]) -> [[Int]] {
        rows.map { Array($0.prefix(4)) }
    }

    private nonisolated static func prepHoles(_ request: URLRequest) -> [Int] {
        guard let url = request.url else { return [] }
        return (URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? [])
            .filter { $0.name == "holes" }
            .compactMap { $0.value.flatMap(Int.init) }
    }

    /// Exactly the app: `startCourseImmediately`, `seedRound`, then the `activeCourseUpgradeKey`
    /// task's `upgradeCachedCourseWhenReady(globalId:roundId:config:loopKey:teeBox:…)`. No pre-seed.
    /// Waits for the background whole-course install, then relaunches offline at the turn.
    private func productionRoundAtTheTurn(_ label: String) async throws -> WatchRoundModel {
        let courseDirectory = makeDirectory("\(label)-courses")
        let roundDirectory = makeDirectory("\(label)-round")
        XCTAssertTrue(WatchCourseStore(directoryURL: courseDirectory).loadCourses().isEmpty, "no pre-seed")
        let log = RequestLog()
        let library = try makeOracleLibrary(directory: courseDirectory, log: log)
        let selection = WatchCourseSelection(front: Self.oracleCourse, teeBox: "blue", firstHalf: "back")

        let prepared = try XCTUnwrap(library.startCourseImmediately(selection))
        let model = makeModel(directory: roundDirectory)
        model.seedRound(
            prepared.holeStates,
            activeHole: prepared.holeStates.first?.hole,
            courseName: prepared.courseName,
            courseGlobalId: selection.front.globalId,
            teeBox: selection.teeBox,
            loopKey: selection.loopKey
        )
        let round = try XCTUnwrap(model.round)
        _ = await library.upgradeCachedCourseWhenReady(
            globalId: try XCTUnwrap(round.courseGlobalId),
            roundId: round.roundId,
            config: Self.config,
            loopKey: round.loopKey,
            teeBox: round.teeBox,
            priorityHole: model.activeHole,
            onProgress: { states in
                guard model.round?.roundId == round.roundId else { return }
                model.applyCourseMapUpgrade(states)
            }
        )
        await library.waitForWholeCourseTemplateInstalls()

        // The active half's own priority work runs first; the whole-course template only after.
        let requests = log.requests
        let firstTemplate = try XCTUnwrap(requests.firstIndex(where: Self.isTemplateRequest))
        let firstActivePackage = try XCTUnwrap(requests.firstIndex {
            $0.url?.path.hasSuffix("/package") == true && !Self.isTemplateRequest($0)
        })
        let priorityPrep = try XCTUnwrap(requests.firstIndex {
            $0.url?.path.hasSuffix("/prep") == true && Self.prepHoles($0).contains(10)
        }, "the active 后九 priority hole (round 1 = physical 10) is prepared")
        XCTAssertLessThan(firstActivePackage, firstTemplate)
        XCTAssertLessThan(priorityPrep, firstTemplate, "whole-course work never precedes the active hole")
        XCTAssertFalse(requests.prefix(firstTemplate).contains { request in
            request.url?.path.hasSuffix("/prep") == true
                && Self.prepHoles(request).contains(where: { hole in hole < 10 })
        }, "no 前九 (template-only) prep before the template install starts")
        XCTAssertTrue(log.templateRequests.allSatisfy { Self.query($0, "loops") == "55555:front,55555:back" })

        XCTAssertNotNil(
            WatchCourseStore(directoryURL: courseDirectory).course(loopKey: "55555:front+55555:back", teeBox: "blue"),
            "the whole-course template is durable"
        )
        let persisted = try XCTUnwrap(WatchRoundStore(directoryURL: roundDirectory).load())
        XCTAssertEqual(persisted.loopKey, "55555:back")
        XCTAssertEqual(persisted.roundId, prepared.roundId)

        // Offline relaunch.
        let offline = try makeOracleLibrary(directory: courseDirectory, log: RequestLog(), offline: true)
        let relaunched = makeModel(directory: roundDirectory)
        relaunched.secondLoopLoader = { request in
            await offline.secondLoop(request, config: Self.config)
        }
        XCTAssertEqual(relaunched.round?.roundId, prepared.roundId)
        finishFirstNine(relaunched)
        XCTAssertEqual(relaunched.screen, .turn)
        return relaunched
    }

    func testProductionStartSequenceTurnsBackToFrontOfflineFromTheAcquiredTemplate() async throws {
        let model = try await productionRoundAtTheTurn("production-back-front")
        let roundId = try XCTUnwrap(model.round?.roundId)
        await model.confirmTurn()

        XCTAssertEqual(model.round?.roundId, roundId)
        XCTAssertEqual(model.round?.loopKey, "55555:back+55555:front")
        let oracle = try oracleTable("55555:back+55555:front")
        let table = roundTable(model.round?.holeStates ?? [])
        // Round holes 1–9 keep the provisional Par until precise maps arrive (unchanged behaviour);
        // the physical table is the oracle's, and the projected second nine carries its real Par.
        XCTAssertEqual(identityTable(table), identityTable(oracle))
        XCTAssertEqual(Array(table.suffix(9)), Array(oracle.suffix(9)))
    }

    func testProductionStartSequenceRepeatsTheBackNineOfflineFromTheAcquiredTemplate() async throws {
        let model = try await productionRoundAtTheTurn("production-back-back")
        model.chooseTurnSecond(.loop("55555:back"))
        await model.confirmTurn()

        XCTAssertEqual(model.round?.loopKey, "55555:back+55555:back")
        let oracle = try oracleTable("55555:back+55555:back")
        let table = roundTable(model.round?.holeStates ?? [])
        XCTAssertEqual(identityTable(table), identityTable(oracle))
        XCTAssertEqual(Array(table.suffix(9)), Array(oracle.suffix(9)))
    }

    // MARK: - a cancelled active upgrade never downloads the abandoned course

    func testCancelledActiveUpgradeNeverQueuesTheAbandonedCourseTemplate() async throws {
        let directory = makeDirectory("watch-cancelled-upgrade")
        let log = RequestLog()
        let server = OracleServer()
        server.gatePrep = true
        let library = try makeOracleLibrary(directory: directory, log: log, server: server)
        let back = WatchCourseSelection(front: Self.oracleCourse, teeBox: "blue", firstHalf: "back")
        let prepared = try XCTUnwrap(library.startCourseImmediately(back))

        // The app's `.task(id: activeCourseUpgradeKey)`, suspended in its priority prep.
        let upgrade = Task { @MainActor in
            await library.upgradeCachedCourseWhenReady(
                globalId: 55555,
                roundId: prepared.roundId,
                config: Self.config,
                loopKey: "55555:back",
                teeBox: "blue",
                priorityHole: 1
            )
        }
        for _ in 0..<10_000 where server.prepWaiting == nil {
            await Task.yield()
        }
        XCTAssertNotNil(server.prepWaiting, "the active upgrade is suspended before its first prep completes")

        // The round ends / is replaced: SwiftUI cancels the keyed task.
        upgrade.cancel()
        server.openPrepGate()
        _ = await upgrade.value
        for _ in 0..<200 {
            await Task.yield()
        }
        await library.waitForWholeCourseTemplateInstalls()
        XCTAssertTrue(log.templateRequests.isEmpty, "no template request for the abandoned upgrade")
        XCTAssertNil(
            WatchCourseStore(directoryURL: directory).course(loopKey: "55555:front+55555:back", teeBox: "blue")
        )

        // A replacement round (the same course, the other half) keeps active-first ordering: its
        // priority prep goes out before the template that its own first pass makes eligible.
        let replacementStart = log.requests.count
        let front = WatchCourseSelection(front: Self.oracleCourse, teeBox: "blue", firstHalf: "front")
        let replacement = try XCTUnwrap(library.startCourseImmediately(front))
        _ = await library.upgradeCachedCourseWhenReady(
            globalId: 55555,
            roundId: replacement.roundId,
            config: Self.config,
            loopKey: "55555:front",
            teeBox: "blue",
            priorityHole: 1
        )
        await library.waitForWholeCourseTemplateInstalls()
        let requests = Array(log.requests[replacementStart...])
        let priorityPrep = try XCTUnwrap(requests.firstIndex { request in
            request.url?.path.hasSuffix("/prep") == true && Self.prepHoles(request).contains(1)
        })
        let firstTemplate = try XCTUnwrap(
            requests.firstIndex(where: Self.isTemplateRequest),
            "the replacement's own first pass makes the whole template eligible"
        )
        XCTAssertLessThan(priorityPrep, firstTemplate)
        XCTAssertNotNil(
            WatchCourseStore(directoryURL: directory).course(loopKey: "55555:front+55555:back", teeBox: "blue")
        )
    }

    /// A template install already running waits for a new active upgrade's first pass: the active
    /// priority prep goes out before any further template request.
    func testRunningTemplateInstallYieldsToANewActiveUpgradesPriorityPrep() async throws {
        let directory = makeDirectory("watch-template-yields")
        let log = RequestLog()
        let server = OracleServer()
        server.gateTemplates = true
        let library = try makeOracleLibrary(directory: directory, log: log, server: server)
        let back = WatchCourseSelection(front: Self.oracleCourse, teeBox: "blue", firstHalf: "back")

        // A template install is in flight (suspended in its package request).
        library.enqueueWholeCourseTemplate(for: back, config: Self.config)
        for _ in 0..<10_000 where server.waiting == nil {
            await Task.yield()
        }
        XCTAssertNotNil(server.waiting)

        // A new active round starts upgrading; hold its priority prep.
        server.gatePrep = true
        let prepared = try XCTUnwrap(library.startCourseImmediately(back))
        let upgrade = Task { @MainActor in
            await library.upgradeCachedCourseWhenReady(
                globalId: 55555,
                roundId: prepared.roundId,
                config: Self.config,
                loopKey: "55555:back",
                teeBox: "blue",
                priorityHole: 1
            )
        }
        for _ in 0..<10_000 where server.prepWaiting == nil {
            await Task.yield()
        }
        XCTAssertNotNil(server.prepWaiting)

        // Let the template's package through: its next request must wait for the active first pass.
        let templateRequestsBefore = log.templateRequests.count
        server.openGate()
        for _ in 0..<500 {
            await Task.yield()
        }
        XCTAssertEqual(log.templateRequests.count, templateRequestsBefore,
                       "no further template request while the active priority prep is pending")
        XCTAssertFalse(log.requests.contains { request in
            request.url?.path.hasSuffix("/prep") == true && Self.prepHoles(request).contains(where: { hole in hole < 10 })
        }, "no 前九 (template-only) prep ahead of the active priority prep")

        server.openPrepGate()
        _ = await upgrade.value
        await library.waitForWholeCourseTemplateInstalls()
        XCTAssertNotNil(
            WatchCourseStore(directoryURL: directory).course(loopKey: "55555:front+55555:back", teeBox: "blue")
        )
    }

    // MARK: - background template diagnostics (never the active round's)

    func testWholeTemplateInstallNeverOverwritesTheActiveRoundDiagnostic() async throws {
        let directory = makeDirectory("watch-template-diagnostics")
        let server = OracleServer()
        server.gateTemplates = true
        let library = try makeOracleLibrary(directory: directory, log: RequestLog(), server: server)
        let selection = WatchCourseSelection(front: Self.oracleCourse, teeBox: "blue", firstHalf: "back")
        XCTAssertNil(library.diagnosticErrorMessage)

        library.enqueueWholeCourseTemplate(for: selection, config: Self.config)
        for _ in 0..<10_000 where server.waiting == nil {
            await Task.yield()
        }
        XCTAssertNotNil(server.waiting, "the template install is suspended in its request")

        // While it is suspended, the active path writes its own diagnostic.
        _ = library.startCourseImmediately(selection)
        let active = library.diagnosticErrorMessage
        XCTAssertNotNil(active)

        server.openGate()
        await library.waitForWholeCourseTemplateInstalls()
        XCTAssertNotNil(
            WatchCourseStore(directoryURL: directory).course(loopKey: "55555:front+55555:back", teeBox: "blue")
        )
        XCTAssertEqual(library.diagnosticErrorMessage, active, "the active path's latest diagnostic stands")
    }

    // MARK: - precise assets retry after a package-only install

    /// A synthetic 18-hole course whose holes have ready geometry: prep carries a projected route
    /// and every topo raster is valid, so a complete install is `preciseTemplateReady`.
    private final class AssetServer {
        var assetsAvailable = false
    }

    private nonisolated static func readyPackageData(loops raw: String, roundId: String) -> Data {
        let loops = raw.split(separator: ",").compactMap { entry -> WatchPackageFixture.Loop? in
            let parts = entry.split(separator: ":")
            guard parts.count == 2, let id = Int(parts[0]) else { return nil }
            return WatchPackageFixture.Loop(id, String(parts[1]))
        }
        var overrides: [Int: String] = [:]
        for (index, loop) in loops.enumerated() {
            for offset in 0..<9 {
                let number = 1 + index * 9 + offset
                let local = loop.sourceStartHole + offset
                let courseHole = loop.half == "all" ? number : local
                overrides[number] = "{\"number\":\(number),\"par\":\(physicalPar(local)),"
                    + "\"yards\":\(300 + local),\"geometryCoverage\":\"ready\","
                    + "\"geometryRevision\":\"rev-\(local)\",\"sourceGlobalId\":\(loop.globalId),"
                    + "\"sourceLocalHole\":\(local),\"courseHoleNumber\":\(courseHole)}"
            }
        }
        return WatchPackageFixture.packageData(
            roundId: roundId,
            course: #"{"globalId":31795,"name":"Black Knight","teeBox":"blue"}"#,
            loops: loops,
            overrides: overrides
        )
    }

    private nonisolated static func readyPrepData(localHoles: [Int]) -> Data {
        let holes = localHoles.map { local in
            "{\"hole\":\(local),\"par\":\(physicalPar(local)),\"geometryCoverage\":\"ready\","
                + "\"geometryRevision\":\"rev-\(local)\",\"route\":[[0.0,0.0,0.0],[0.0,120.0,120.0]],"
                + "\"holeImageProjection\":{\"available\":true,\"widthPx\":500,\"heightPx\":700,"
                + "\"refs\":[{\"lat\":40.0,\"lon\":116.0,\"px\":100.0,\"py\":600.0},"
                + "{\"lat\":40.0,\"lon\":116.001,\"px\":220.0,\"py\":600.0},"
                + "{\"lat\":40.001,\"lon\":116.0,\"px\":100.0,\"py\":480.0}]}}"
        }
        return Data(("{\"globalId\":31795,\"clubs\":[],\"holes\":[" + holes.joined(separator: ",") + "]}").utf8)
    }

    private func makeAssetLibrary(directory: URL, log: RequestLog, server: AssetServer) -> WatchCourseLibrary {
        WatchCourseLibrary(
            store: WatchCourseStore(directoryURL: directory),
            imageStore: WatchHoleImageStore(directoryURL: directory),
            makeRoundId: { "watch-asset-round" },
            now: { "2026-09-30T00:00:00Z" },
            clientFactory: { config in
                WatchBackendClient(
                    baseURL: config.baseURL,
                    sessionToken: config.sessionToken,
                    dataLoader: { request in
                        log.requests.append(request)
                        let url = try XCTUnwrap(request.url)
                        func ok(_ body: Data) -> (Data, URLResponse) {
                            (body, HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!)
                        }
                        if url.path.hasSuffix("/package"),
                           let loops = Self.query(request, "loops"),
                           let round = Self.query(request, "round_id") {
                            return ok(Self.readyPackageData(loops: loops, roundId: round))
                        }
                        if server.assetsAvailable, url.path.hasSuffix("/prep") {
                            return ok(Self.readyPrepData(localHoles: Self.prepHoles(request)))
                        }
                        if server.assetsAvailable, url.path.hasSuffix("/topo.png"),
                           let topo = Data(base64Encoded: WatchHoleMapSample.jpegBase64) {
                            return ok(topo)
                        }
                        return (Data(), HTTPURLResponse(url: url, statusCode: 404, httpVersion: nil, headerFields: nil)!)
                    },
                    retrySleep: { _ in }
                )
            },
            retrySleep: { _ in }
        )
    }

    func testPackageOnlyWholeTemplateRetriesItsPreciseAssetsAfterARelaunch() async throws {
        let directory = makeDirectory("watch-template-assets")
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let whole = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue")

        // 1. The package installs, but every prep / topo request fails.
        let server = AssetServer()
        let first = makeAssetLibrary(directory: directory, log: RequestLog(), server: server)
        first.enqueueWholeCourseTemplate(for: selection, config: Self.config)
        await first.waitForWholeCourseTemplateInstalls()
        XCTAssertEqual(first.wholeTemplateInstallState(whole), .packageInstalled)
        let packageOnly = try XCTUnwrap(
            WatchCourseStore(directoryURL: directory).course(loopKey: "31795:front+31795:back", teeBox: "blue")
        )
        XCTAssertFalse(packageOnly.holeStates.contains { $0.geometryCoverage == "pending" })
        XCTAssertTrue(packageOnly.holeStates.allSatisfy { $0.geometryCoverage == "partial" },
                      "server-ready holes without rasters are partial, not installed")

        // 2. Relaunch with assets available: the package-only template is not "installed", so the
        //    install runs again and completes the precise assets.
        server.assetsAvailable = true
        let log = RequestLog()
        let relaunched = makeAssetLibrary(directory: directory, log: log, server: server)
        relaunched.enqueueWholeCourseTemplate(for: selection, config: Self.config)
        await relaunched.waitForWholeCourseTemplateInstalls()
        XCTAssertFalse(log.templateRequests.isEmpty, "the precise install was retried")
        XCTAssertEqual(relaunched.wholeTemplateInstallState(whole), .assetsInstalled)
        let precise = try XCTUnwrap(
            WatchCourseStore(directoryURL: directory).course(loopKey: "31795:front+31795:back", teeBox: "blue")
        )
        XCTAssertTrue(precise.holeStates.allSatisfy { $0.geometryCoverage == "ready" && $0.holeMap != nil })
        let images = WatchHoleImageStore(directoryURL: directory)
        XCTAssertTrue(precise.holeStates.allSatisfy {
            images.hasImage(globalId: 31795, hole: $0.hole, geometryRevision: $0.geometryRevision)
        })

        // 3. A complete install is skipped.
        let skipLog = RequestLog()
        let third = makeAssetLibrary(directory: directory, log: skipLog, server: server)
        third.enqueueWholeCourseTemplate(for: selection, config: Self.config)
        await third.waitForWholeCourseTemplateInstalls()
        XCTAssertTrue(skipLog.requests.isEmpty)
    }

    // MARK: - durable template validation (load boundary)

    func testInvalidDurableTemplatesAreDroppedAtLoadAndRemovedFromDisk() async throws {
        let directory = makeDirectory("watch-template-validation")
        let client = WatchBackendClient(baseURL: Self.config.baseURL)
        let valid = try WatchCourseTemplateBuilder.build(
            option: Self.blackKnight,
            package: client.decodeCoursePackage(Self.packageData(loops: "31795:front,31795:back", roundId: "d")),
            prepsByGlobalId: [:],
            selectedTee: "blue",
            cachedAt: "2026-09-28T00:00:00Z"
        ).template
        let backHalf = try WatchCourseTemplateBuilder.build(
            option: Self.blackKnight,
            loopKey: "31795:back",
            package: client.decodeCoursePackage(Self.packageData(loops: "31795:back", roundId: "d")),
            prepsByGlobalId: [:],
            selectedTee: "white",
            cachedAt: "2026-09-28T00:00:00Z"
        ).template
        XCTAssertNoThrow(try valid.validateIdentity())
        XCTAssertNoThrow(try backHalf.validateIdentity())

        func mutated(_ template: WatchCourseTemplate, _ change: (inout [String: Any]) -> Void) throws -> Any {
            var object = try XCTUnwrap(
                JSONSerialization.jsonObject(with: JSONEncoder().encode(template)) as? [String: Any]
            )
            change(&object)
            return object
        }
        // (a) a valid-looking loop key over the back half's physical table
        let wrongKey = try mutated(backHalf) { $0["loopKey"] = "31795:front" }
        // (b) a hole moved off its round position
        let wrongNumber = try mutated(backHalf) { object in
            var holes = object["holeStates"] as? [[String: Any]] ?? []
            holes[0]["hole"] = 10
            object["holeStates"] = holes
            object["teeBox"] = "red"
        }
        // (c) a hole whose source course is another course
        let wrongSource = try mutated(backHalf) { object in
            var holes = object["holeStates"] as? [[String: Any]] ?? []
            holes[3]["globalId"] = 99_999
            object["holeStates"] = holes
            object["teeBox"] = "gold"
        }
        let validObject = try mutated(valid) { _ in }
        let fileURL = directory.appendingPathComponent("courses.json")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: [validObject, wrongKey, wrongNumber, wrongSource])
            .write(to: fileURL)

        let store = WatchCourseStore(directoryURL: directory)
        XCTAssertEqual(store.loadCourses().map(\.loopKey), ["31795:front+31795:back"], "the valid sibling survives")
        XCTAssertNil(store.course(loopKey: "31795:front", teeBox: "white"))
        XCTAssertNil(store.course(loopKey: "31795:back", teeBox: "red"))
        XCTAssertNil(store.course(loopKey: "31795:back", teeBox: "gold"))
        XCTAssertNil(store.compositeCourse(containingGlobalId: 99_999))
        let onDisk = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: fileURL)) as? [[String: Any]]
        )
        XCTAssertEqual(onDisk.count, 1, "invalid entries are rewritten out so they are re-downloaded")
        XCTAssertEqual(onDisk.first?["loopKey"] as? String, "31795:front+31795:back")

        // None of them can be restored or upgraded offline.
        let library = WatchCourseLibrary(store: store, imageStore: WatchHoleImageStore(directoryURL: directory))
        let restored = await library.startCourse(
            WatchCourseSelection(front: Self.blackKnight, teeBox: "red", firstHalf: "back"),
            config: nil
        )
        XCTAssertNil(restored)

        // save refuses an invalid template.
        let invalid = WatchCourseTemplate(
            option: Self.blackKnight,
            loopKey: "31795:front",
            courseName: "Black Knight",
            teeBox: "blue",
            holeStates: backHalf.holeStates,
            cachedAt: "2026-09-28T00:00:00Z"
        )
        XCTAssertThrowsError(try store.save(invalid))
    }

    /// Contract §6 (Codex P2 5902271213): a durable template entry must carry `sourceLocalHole` and
    /// `courseHoleNumber` on every hole — a pending/legacy row is no exception.
    func testTemplatesMissingPhysicalOrPrintedIdentityAreDroppedAndRefused() async throws {
        let directory = makeDirectory("watch-template-identity")
        let client = WatchBackendClient(baseURL: Self.config.baseURL)
        let sibling = try WatchCourseTemplateBuilder.build(
            option: Self.blackKnight,
            package: client.decodeCoursePackage(Self.packageData(loops: "31795:front,31795:back", roundId: "d")),
            prepsByGlobalId: [:],
            selectedTee: "blue",
            cachedAt: "2026-09-30T00:00:00Z"
        ).template
        let backHalf = try WatchCourseTemplateBuilder.build(
            option: Self.blackKnight,
            loopKey: "31795:back",
            package: client.decodeCoursePackage(Self.packageData(loops: "31795:back", roundId: "d")),
            prepsByGlobalId: [:],
            selectedTee: "white",
            cachedAt: "2026-09-30T00:00:00Z"
        ).template
        XCTAssertEqual(backHalf.holeStates.map(\.courseHoleNumber), Array(10...18).map { Optional($0) })

        func object(_ template: WatchCourseTemplate) throws -> [String: Any] {
            try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(template)) as? [String: Any])
        }
        func mutatingHoles(
            tee: String,
            _ change: (inout [String: Any]) -> Void
        ) throws -> [String: Any] {
            var entry = try object(backHalf)
            var holes = entry["holeStates"] as? [[String: Any]] ?? []
            for index in holes.indices { change(&holes[index]) }
            entry["holeStates"] = holes
            entry["teeBox"] = tee
            return entry
        }
        // every hole without its printed number
        let noPrinted = try mutatingHoles(tee: "red") { $0.removeValue(forKey: "courseHoleNumber") }
        // provisional rows without their physical hole
        let pendingNoLocal = try mutatingHoles(tee: "gold") { hole in
            hole["geometryCoverage"] = "pending"
            hole.removeValue(forKey: "sourceLocalHole")
        }
        // loop key and every hole, but no physical or presentation identity at all
        let noIdentity = try mutatingHoles(tee: "green") { hole in
            hole["geometryCoverage"] = "pending"
            hole.removeValue(forKey: "sourceLocalHole")
            hole.removeValue(forKey: "courseHoleNumber")
        }
        let malformed: [(tee: String, entry: [String: Any])] = [
            (tee: "red", entry: noPrinted),
            (tee: "gold", entry: pendingNoLocal),
            (tee: "green", entry: noIdentity),
        ]
        let siblingObject = try object(sibling)
        let fileURL = directory.appendingPathComponent("courses.json")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: [siblingObject] + malformed.map(\.entry))
            .write(to: fileURL)

        let store = WatchCourseStore(directoryURL: directory)
        XCTAssertEqual(store.loadCourses().map(\.cacheKey), [sibling.cacheKey], "only the malformed entries are dropped")
        let onDisk = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: fileURL)) as? [[String: Any]]
        )
        XCTAssertEqual(onDisk.count, 1)
        XCTAssertEqual(onDisk.first?["loopKey"] as? String, "31795:front+31795:back")

        let library = WatchCourseLibrary(store: store, imageStore: WatchHoleImageStore(directoryURL: directory))
        for (tee, entry) in malformed {
            XCTAssertNil(store.course(loopKey: "31795:back", teeBox: tee), tee)
            let started = await library.startCourse(
                WatchCourseSelection(front: Self.blackKnight, teeBox: tee, firstHalf: "back"),
                config: nil
            )
            XCTAssertNil(started, "\(tee): a malformed entry cannot be started")
            let decoded = try JSONDecoder().decode(
                WatchCourseTemplate.self,
                from: JSONSerialization.data(withJSONObject: entry)
            )
            XCTAssertThrowsError(try store.save(decoded), "\(tee): save refuses it")
        }
        XCTAssertEqual(store.loadCourses().map(\.cacheKey), [sibling.cacheKey], "the sibling survives")
    }

    // MARK: - printed hole numbers (courseHoleNumber)

    func testBackNineStartShowsPhysicalHoleTenAndSurvivesRelaunch() throws {
        let directory = makeDirectory("watch-back-display")
        let library = makeLibrary(directory: directory, log: RequestLog())
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let prepared = try XCTUnwrap(library.startCourseImmediately(selection))
        XCTAssertEqual(prepared.holeStates.map(\.courseHoleNumber), Array(10...18).map { Optional($0) })

        let roundDirectory = makeDirectory("watch-back-display-round")
        let model = makeModel(directory: roundDirectory)
        model.seedRound(prepared.holeStates, activeHole: 1, courseGlobalId: Self.courseId,
                        teeBox: "blue", loopKey: selection.loopKey)
        XCTAssertEqual(model.activeHole, 1, "events and navigation keep the round coordinate")
        XCTAssertEqual(model.activeDisplayHoleNumber, 10)

        let relaunched = makeModel(directory: roundDirectory)
        XCTAssertEqual(relaunched.activeHole, 1)
        XCTAssertEqual(relaunched.activeHoleState?.displayHoleNumber, 10, "first UI identity after relaunch")
        XCTAssertEqual(relaunched.allHoleStates.map(\.displayHoleNumber), Array(10...18))
    }

    /// A valid persisted `G:back` round: round 1–9 = physical 10–18, printed 10–18.
    private func backNineRound() -> WatchRoundStore.PersistedRound {
        WatchRoundStore.PersistedRound(
            roundId: "persisted-back",
            activeHole: 1,
            holeStates: (1...9).map { hole in
                WatchRoundState(
                    roundId: "persisted-back", hole: hole, par: Self.physicalPar(hole + 9),
                    distanceM: nil, selectedClub: nil,
                    globalId: Self.courseId, sourceLocalHole: hole + 9, courseHoleNumber: hole + 9,
                    score: hole == 1 ? 4 : 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
                )
            },
            courseGlobalId: Self.courseId,
            teeBox: "blue",
            loopKey: "31795:back"
        )
    }

    func testValidPersistedBackNineRoundRestoresWithItsPhysicalNumbers() throws {
        let directory = makeDirectory("watch-round-valid")
        try WatchRoundStore(directoryURL: directory).save(backNineRound())
        let model = makeModel(directory: directory)
        XCTAssertEqual(model.round?.loopKey, "31795:back")
        XCTAssertEqual(model.activeDisplayHoleNumber, 10)
        XCTAssertEqual(model.allHoleStates.map(\.displayHoleNumber), Array(10...18))
    }

    /// Contradictory or legacy active-round bytes are rejected at the load boundary: not restored,
    /// removed from disk, and never rendered as round-number holes (e.g. H1 for physical 10).
    func testContradictoryPersistedActiveRoundsAreRejectedAndRemoved() throws {
        let mutations: [(String, (inout [String: Any]) -> Void)] = [
            ("contradictory loopKey", { $0["loopKey"] = "31795:front" }),
            ("missing loopKey", { $0.removeValue(forKey: "loopKey") }),
            ("non-canonical loopKey", { $0["loopKey"] = "31795:back+7002:all" }),
            ("round number off the table", { round in
                Self.mutateHole(&round, 0) { $0["hole"] = 10 }
            }),
            ("duplicate round number", { round in
                Self.mutateHole(&round, 1) { $0["hole"] = 1 }
            }),
            ("source course", { round in
                Self.mutateHole(&round, 0) { $0["globalId"] = 99_999 }
            }),
            ("sourceLocalHole = round hole", { round in
                Self.mutateHole(&round, 0) { $0["sourceLocalHole"] = 1 }
            }),
            ("missing sourceLocalHole", { round in
                Self.mutateHole(&round, 0) { $0.removeValue(forKey: "sourceLocalHole") }
            }),
            ("missing courseHoleNumber", { round in
                Self.mutateHole(&round, 0) { $0.removeValue(forKey: "courseHoleNumber") }
            }),
            ("contradictory courseHoleNumber", { round in
                Self.mutateHole(&round, 0) { $0["courseHoleNumber"] = 1 }
            }),
            // The complete table (Codex P2 5901834965).
            ("partial course round (one state)", { round in
                let holes = round["holeStates"] as? [[String: Any]] ?? []
                round["holeStates"] = Array(holes.prefix(1))
            }),
            ("empty course round", { $0["holeStates"] = [[String: Any]]() }),
            ("activeHole 99", { $0["activeHole"] = 99 }),
            ("activeHole missing from the table", { $0["activeHole"] = 0 }),
            ("mismatched state roundId", { round in
                Self.mutateHole(&round, 2) { $0["roundId"] = "another-round" }
            }),
        ]
        for (label, mutate) in mutations {
            let directory = makeDirectory("watch-round-invalid")
            try WatchRoundStore(directoryURL: directory).save(backNineRound())
            let fileURL = directory.appendingPathComponent("round.json")
            var object = try XCTUnwrap(
                JSONSerialization.jsonObject(with: Data(contentsOf: fileURL)) as? [String: Any]
            )
            mutate(&object)
            try JSONSerialization.data(withJSONObject: object).write(to: fileURL)

            let model = makeModel(directory: directory)
            XCTAssertNil(model.round, "\(label): must not be restored")
            XCTAssertNotEqual(model.screen, .resume, label)
            XCTAssertFalse(FileManager.default.fileExists(atPath: fileURL.path), "\(label): removed from disk")
            XCTAssertNil(WatchRoundStore(directoryURL: directory).load(), label)
        }
    }

    private static func mutateHole(
        _ round: inout [String: Any],
        _ index: Int,
        _ change: (inout [String: Any]) -> Void
    ) {
        var holes = round["holeStates"] as? [[String: Any]] ?? []
        guard index < holes.count else { return }
        change(&holes[index])
        round["holeStates"] = holes
    }

    func testActiveRoundWritesRefuseContradictoryIdentity() throws {
        let directory = makeDirectory("watch-round-write-guard")
        let store = WatchRoundStore(directoryURL: directory)
        var invalid = backNineRound()
        invalid.holeStates[0] = invalid.holeStates[0].replacingRoundId(
            "persisted-back", hole: 1, sourceLocalHole: 10, courseHoleNumber: 1
        )
        XCTAssertThrowsError(try store.save(invalid))
        XCTAssertNil(store.load())

        // Writes also refuse an incomplete table, an active hole off the table and a foreign
        // snapshot roundId.
        var partial = backNineRound()
        partial.holeStates = Array(partial.holeStates.prefix(1))
        XCTAssertThrowsError(try store.save(partial))
        var empty = backNineRound()
        empty.holeStates = []
        XCTAssertThrowsError(try store.save(empty))
        var offTable = backNineRound()
        offTable.activeHole = 99
        XCTAssertThrowsError(try store.save(offTable))
        var foreign = backNineRound()
        foreign.holeStates[2] = foreign.holeStates[2].replacingRoundId("another-round")
        XCTAssertThrowsError(try store.save(foreign))
        XCTAssertNil(store.load())

        try store.save(backNineRound())
        let contradictory = backNineRound().holeStates[1].replacingRoundId(
            "persisted-back", hole: 2, sourceLocalHole: 2, courseHoleNumber: 2
        )
        XCTAssertThrowsError(try store.upsertHoleState(contradictory))
        XCTAssertEqual(store.load()?.holeStates[1].courseHoleNumber, 11, "the valid round is untouched")

        // The model's seed paths use the same gate.
        let model = makeModel(directory: makeDirectory("watch-round-write-guard-model"))
        model.seedRound(invalid.holeStates, activeHole: 1, courseGlobalId: Self.courseId,
                        teeBox: "blue", loopKey: "31795:back")
        XCTAssertNil(model.round)
        model.applyRoundSeed(WatchRoundSeed(
            roundId: "legacy-seed",
            courseName: "Black Knight",
            activeHole: 1,
            holes: [WatchRoundSeedHole(hole: 1, par: 4, distanceM: nil, globalId: Self.courseId)],
            loopKey: "31795:back"
        ))
        XCTAssertNil(model.round, "a seed without physical identity is not adopted")

        // A score-only practice round has no course identity and stays valid.
        model.startPracticeRound(holeCount: 9)
        XCTAssertEqual(model.holeCount, 9)
        XCTAssertNil(model.round?.loopKey)
    }

    func testReverseStartPayloadCarriesTheCompletePhysicalTable() async throws {
        let directory = makeDirectory("watch-reverse-start")
        let library = makeLibrary(directory: directory, log: RequestLog())
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let started = await library.startCourse(selection, config: Self.config)
        let prepared = try XCTUnwrap(started)

        let payload = WatchRoundStart.watchStarted(prepared, selection: selection)
        let relayed = try JSONDecoder().decode(WatchRoundStart.self, from: JSONEncoder().encode(payload))

        XCTAssertEqual(relayed.loopKey, "31795:back")
        XCTAssertEqual(relayed.activeHole, 1)
        let package = try WatchBackendClient(baseURL: Self.config.baseURL)
            .decodeCoursePackage(Self.packageData(loops: "31795:back", roundId: "server"))
        XCTAssertEqual(
            relayed.holes.map { [$0.hole, $0.globalId ?? -1, $0.localHole ?? -1, $0.courseHoleNumber ?? -1] },
            package.holes.sorted { $0.number < $1.number }.map {
                [$0.number, $0.sourceGlobalId, $0.sourceLocalHole, $0.courseHoleNumber]
            }
        )

        // The provisional (offline) start relays the same table.
        let offline = try XCTUnwrap(
            makeLibrary(directory: makeDirectory("watch-reverse-offline"), log: RequestLog())
                .startCourseImmediately(selection)
        )
        XCTAssertEqual(
            WatchRoundStart.watchStarted(offline, selection: selection).holes.map {
                [$0.hole, $0.globalId ?? -1, $0.localHole ?? -1, $0.courseHoleNumber ?? -1]
            },
            relayed.holes.map { [$0.hole, $0.globalId ?? -1, $0.localHole ?? -1, $0.courseHoleNumber ?? -1] }
        )
    }

    // MARK: - fail closed

    func testMalformedSelectionDoesNotStartOrPersistAProvisionalRound() throws {
        let directory = makeDirectory("watch-malformed-start")
        let library = makeLibrary(directory: directory, log: RequestLog())
        let strayBack = WatchCourseOption(globalId: 7002, name: "组合 ~ B", holes: 9, teeBox: "Blue", segmentHoles: 9)
        // An 18-hole course has no back loop; its rows cannot be built.
        let malformed = WatchCourseSelection(front: Self.blackKnight, back: strayBack, teeBox: "blue")
        XCTAssertNil(library.startCourseImmediately(malformed))
        XCTAssertEqual(library.errorMessage, WatchCourseLibrary.malformedSelectionMessage)

        // A course without playable holes has no hole table either.
        let empty = WatchCourseOption(globalId: 7009, name: "无球洞", holes: 0, teeBox: "Blue")
        XCTAssertNil(library.startCourseImmediately(WatchCourseSelection(front: empty, teeBox: "Blue")))
        XCTAssertEqual(library.errorMessage, WatchCourseLibrary.malformedSelectionMessage)

        XCTAssertTrue(WatchCourseStore(directoryURL: directory).loadCourses().isEmpty,
                      "no pending template is persisted for a round that did not start")
    }

    func testTemplateWithAMisprintedHoleNumberIsRejected() throws {
        let rows = (1...9).map { hole in
            WatchRoundState(
                roundId: "t", hole: hole, par: 4, distanceM: nil, selectedClub: nil,
                globalId: Self.courseId, sourceLocalHole: hole + 9,
                courseHoleNumber: hole == 1 ? 1 : hole + 9,
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
            )
        }
        let template = WatchCourseTemplate(
            option: Self.blackKnight, loopKey: "31795:back", courseName: "Black Knight",
            teeBox: "blue", holeStates: rows, cachedAt: "2026-09-30T00:00:00Z"
        )
        XCTAssertThrowsError(try template.validateIdentity())
    }
}
