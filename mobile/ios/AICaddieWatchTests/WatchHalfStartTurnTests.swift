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
    private nonisolated static func physicalPar(_ local: Int) -> Int { [4, 5, 3][local % 3] }

    private final class RequestLog {
        var requests: [URLRequest] = []

        var packageRequests: [URLRequest] {
            requests.filter { $0.url?.path.hasSuffix("/package") == true }
        }
    }

    private nonisolated static func query(_ request: URLRequest?, _ name: String) -> String? {
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
        roundId: String = "watch-half-round"
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
                              let round = Self.query(request, "round_id") else {
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
        XCTAssertNil(WatchCourseStore(directoryURL: directory).course(loopKey: "31795:front+31795:back", teeBox: "blue"))

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
            holes: (1...9).map { WatchRoundSeedHole(hole: $0, par: Self.physicalPar(9 + $0), distanceM: nil, globalId: Self.courseId) },
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
        let library = makeLibrary(directory: directory, log: RequestLog())
        let selection = WatchCourseSelection(front: Self.blackKnight, teeBox: "blue", firstHalf: "back")
        let started = await library.startCourse(selection, config: Self.config)
        let prepared = try XCTUnwrap(started)

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

    func testRoundPersistedWithoutCourseHoleNumbersResolvesThemFromItsLoopKey() throws {
        let directory = makeDirectory("watch-legacy-display")
        let states = (1...18).map { hole in
            WatchRoundState(
                roundId: "legacy", hole: hole, par: 4, distanceM: nil, selectedClub: nil,
                globalId: Self.courseId,
                sourceLocalHole: hole <= 9 ? hole + 9 : hole - 9,
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
            )
        }
        try WatchRoundStore(directoryURL: directory).save(WatchRoundStore.PersistedRound(
            roundId: "legacy",
            activeHole: 10,
            holeStates: states,
            courseGlobalId: Self.courseId,
            teeBox: "blue",
            loopKey: "31795:back+31795:front"
        ))
        let model = makeModel(directory: directory)
        XCTAssertEqual(model.allHoleStates.map(\.displayHoleNumber), Array(10...18) + Array(1...9))

        // Without a loop key only provable numbers are derived; the rest shows the round number.
        let decoded = try JSONDecoder().decode(
            WatchRoundState.self,
            from: JSONEncoder().encode(states[9])
        )
        XCTAssertNil(decoded.courseHoleNumber, "decoding never invents the field")
        XCTAssertEqual(decoded.displayHoleNumber, 10, "round 10 / local 1 is 前九 1 or B:all 10 — not provable")
        let back = try JSONDecoder().decode(WatchRoundState.self, from: JSONEncoder().encode(states[0]))
        XCTAssertEqual(back.displayHoleNumber, 10, "a physical 10–18 hole is always printed as itself")
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
