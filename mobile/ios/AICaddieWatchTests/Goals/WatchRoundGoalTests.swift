// size: medium
// goals: W-01, W-02, W-03
import Foundation
import XCTest
import AICaddieDomain
import AICaddieCore
@testable import AICaddieWatch

/// The Watch round lifecycle: what the phone pushes (config, session, seed), the ways a round
/// starts and survives a process kill, and hole navigation through the turn. The round-start state
/// machine runs idle → active → (hole 9 saved) turn → second loop active → locked → finish
/// confirmation; each state is also shown rejecting at least one event that is illegal there.
@MainActor
final class WatchRoundGoalTests: XCTestCase {
    private static let fixedNow = "2026-06-20T00:00:00Z"

    /// Records what the turn asked the second-loop loader for.
    private final class LoaderCalls: @unchecked Sendable {
        var requests: [WatchSecondLoopRequest] = []
    }

    // MARK: - helpers

    private func tempDirectory() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("wgoal-\(UUID().uuidString)", isDirectory: true)
    }

    private func makeModel(_ dir: URL, ids: @escaping () -> String) -> WatchRoundModel {
        WatchRoundModel(
            store: WatchRoundStore(directoryURL: dir),
            autoShotEnabled: false,
            persistAutoShotEnabled: { _ in },
            makeEventId: ids,
            now: { Self.fixedNow }
        )
    }

    private func sequentialIds(_ prefix: String = "evt") -> () -> String {
        var counter = 0
        return {
            counter += 1
            return "\(prefix)-\(counter)"
        }
    }

    private func courseHoles(_ loopKey: String, roundId: String = "r1") -> [WatchRoundState] {
        (WatchCourseSelection.roundRows(loopKey: loopKey) ?? []).map { row in
            WatchRoundState(
                roundId: roundId, hole: row.number, par: 4, distanceM: nil, selectedClub: nil,
                globalId: row.globalId, sourceLocalHole: row.sourceLocalHole,
                courseHoleNumber: row.courseHoleNumber,
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
            )
        }
    }

    private func courseSeedHoles(_ loopKey: String) -> [WatchRoundSeedHole] {
        (WatchCourseSelection.roundRows(loopKey: loopKey) ?? []).map { row in
            WatchRoundSeedHole(
                hole: row.number, par: 4, distanceM: nil, globalId: row.globalId,
                localHole: row.sourceLocalHole, courseHoleNumber: row.courseHoleNumber
            )
        }
    }

    private func frontSeed(roundId: String, courseName: String = "Phone Course") -> WatchRoundSeed {
        WatchRoundSeed(
            roundId: roundId,
            courseName: courseName,
            activeHole: 1,
            holes: courseSeedHoles("81001:front"),
            globalId: 81001,
            teeBox: "blue",
            loopKey: "81001:front"
        )
    }

    /// A sync client that only touches a temporary directory and never activates WCSession.
    private func makeClient(_ dir: URL) -> WatchSyncClient {
        WatchSyncClient(
            queueURL: dir.appendingPathComponent("queued_events.json"),
            holeImageStore: WatchHoleImageStore(directoryURL: dir.appendingPathComponent("images")),
            courseStore: WatchCourseStore(directoryURL: dir.appendingPathComponent("courses")),
            session: nil
        )
    }

    private func seedPayload(_ seed: WatchRoundSeed) throws -> [String: Any] {
        let data = try JSONEncoder().encode(seed)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    /// Score the active hole at its drafted value (par unless `score` is given) through the UI path.
    private func scoreActiveHole(_ model: WatchRoundModel, score: Int? = nil) {
        model.startScoringActiveHole()
        model.startManualScoreEntry()
        if let score { model.setDraftScore(score) }
        model.saveManualScore()
    }

    /// A course round on `81001:front` (round id `turn-r`) at its turn: hole 9 scored and saved.
    private func reachTurn(_ model: WatchRoundModel) {
        model.seedRound(
            courseHoles("81001:front", roundId: "turn-r"),
            activeHole: 1,
            courseName: "Turn Course",
            courseGlobalId: 81001,
            teeBox: "blue",
            loopKey: "81001:front"
        )
        model.selectHole(9)
        scoreActiveHole(model)
    }

    private func installReadyLoader(_ model: WatchRoundModel, calls: LoaderCalls) {
        let second = courseHoles("81001:front+81001:front", roundId: "turn-r").filter { $0.hole >= 10 }
        model.secondLoopLoader = { request in
            calls.requests.append(request)
            return .ready(loopKey: "81001:front+81001:front", holeStates: second)
        }
    }

    // MARK: - W-01 phone push

    /// One application context carries the backend config, the signed-in session and the round seed;
    /// the seed then opens the round on the model behind an explicit Resume.
    // goals: W-01 [main]
    func testPhonePushOfConfigSessionAndSeedMakesTheWatchReadyToPlay() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let client = makeClient(dir)
        let seed = frontSeed(roundId: "phone-round-1")

        client.applyApplicationContext([
            "config": [
                "apiBaseURL": "https://caddie.example",
                "adminToken": "admin-1",
                "sessionToken": "session-1",
                "sessionTokenExpiresAt": "2026-06-21T00:00:00Z",
            ],
            "roundSeed": try seedPayload(seed),
        ])

        let config = try XCTUnwrap(client.config)
        XCTAssertEqual(config.baseURL, URL(string: "https://caddie.example"))
        XCTAssertEqual(config.adminToken, "admin-1")
        XCTAssertEqual(config.sessionToken, "session-1")
        XCTAssertEqual(config.sessionTokenExpiresAt, ISO8601DateFormatter().date(from: "2026-06-21T00:00:00Z"))
        XCTAssertEqual(client.roundSeed, seed)

        let model = makeModel(dir.appendingPathComponent("round"), ids: sequentialIds())
        model.config = client.config
        let delivered = try XCTUnwrap(client.roundSeed)
        model.applyRoundSeed(delivered)

        XCTAssertEqual(model.screen, .resume, "a phone round never starts without an explicit Resume")
        XCTAssertEqual(model.round?.roundId, "phone-round-1")
        XCTAssertEqual(model.holeCount, 9)
        XCTAssertEqual(model.round?.loopKey, "81001:front")
        XCTAssertEqual(model.round?.courseGlobalId, 81001)
        XCTAssertEqual(model.round?.teeBox, "blue")
        XCTAssertEqual(model.config?.sessionToken, "session-1")

        model.resumeRound()
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.activeHoleState?.sourceLocalHole, 1)
    }

    /// `configStatus: unavailable` clears the config, durably, while a seed in the same context is
    /// still delivered.
    // goals: W-01
    func testUnavailableConfigStatusClearsConfigDurablyButStillDeliversTheSeed() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let client = makeClient(dir)
        client.applyApplicationContext(["config": ["apiBaseURL": "https://caddie.example"]])
        XCTAssertNotNil(client.config)
        XCTAssertNotNil(makeClient(dir).config, "the pushed config survives a relaunch")

        let seed = frontSeed(roundId: "phone-round-2")
        client.applyApplicationContext([
            "configStatus": "unavailable",
            "roundSeed": try seedPayload(seed),
        ])

        XCTAssertNil(client.config)
        XCTAssertEqual(client.roundSeed, seed)
        XCTAssertNil(makeClient(dir).config, "the cleared config stays cleared after a relaunch")
    }

    /// A later context without a seed retracts the client's seed; the round the model already
    /// started is the Watch's own data and survives a relaunch behind Resume.
    // goals: W-01
    func testLaterSeedlessContextClearsTheSeedButNotTheStartedRound() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let client = makeClient(dir)
        let roundDir = dir.appendingPathComponent("round")
        let model = makeModel(roundDir, ids: sequentialIds())

        client.applyApplicationContext(["roundSeed": try seedPayload(frontSeed(roundId: "phone-round-3"))])
        let delivered = try XCTUnwrap(client.roundSeed)
        model.applyRoundSeed(delivered)
        model.resumeRound()
        scoreActiveHole(model, score: 5)

        client.applyApplicationContext(["config": ["apiBaseURL": "https://caddie.example"]])

        XCTAssertNil(client.roundSeed, "a config-only context is an explicit seed retraction")
        XCTAssertNotNil(client.config)
        XCTAssertEqual(model.round?.roundId, "phone-round-3")

        let relaunched = makeModel(roundDir, ids: sequentialIds("relaunch"))
        XCTAssertEqual(relaunched.screen, .resume)
        XCTAssertEqual(relaunched.round?.roundId, "phone-round-3")
        XCTAssertEqual(relaunched.round?.holeStates.first { $0.hole == 1 }?.score, 5)
    }

    /// A signed-out phone pushes its config without a session: the Bearer and its expiry go away,
    /// the backend address stays.
    // goals: W-01
    func testSignedOutConfigDropsTheSessionAndKeepsTheBackend() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let client = makeClient(dir)
        client.applyApplicationContext(["config": [
            "apiBaseURL": "https://caddie.example",
            "adminToken": "admin-1",
            "sessionToken": "session-1",
            "sessionTokenExpiresAt": "2026-06-21T00:00:00Z",
        ]])
        XCTAssertEqual(client.config?.sessionToken, "session-1")

        client.applyApplicationContext(["config": [
            "apiBaseURL": "https://caddie.example",
            "adminToken": "admin-1",
        ]])

        let config = try XCTUnwrap(client.config)
        XCTAssertNil(config.sessionToken)
        XCTAssertNil(config.sessionTokenExpiresAt)
        XCTAssertEqual(config.baseURL, URL(string: "https://caddie.example"))
        XCTAssertEqual(config.adminToken, "admin-1")
    }

    /// A seed whose holes lack their physical identity is published by the client but never becomes
    /// a round on the Watch.
    // goals: W-01
    func testSeedWithoutCourseIdentityNeverStartsARound() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let client = makeClient(dir)
        let legacy = WatchRoundSeed(
            roundId: "legacy-round",
            courseName: "Legacy",
            activeHole: 1,
            holes: (1...9).map { WatchRoundSeedHole(hole: $0, par: 4, distanceM: 350) },
            loopKey: "81001:front"
        )

        client.applyApplicationContext(["roundSeed": try seedPayload(legacy)])
        XCTAssertEqual(client.roundSeed, legacy)

        let roundDir = dir.appendingPathComponent("round")
        let model = makeModel(roundDir, ids: sequentialIds())
        model.applyRoundSeed(legacy)

        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(WatchRoundStore(directoryURL: roundDir).load())
    }

    // MARK: - W-02 round start and recovery

    /// A cancelled course download leaves the Watch idle and clears its preparation lock; retrying
    /// the same selection then installs the package. No provisional course is persisted by the
    /// failed attempt, so cancelling after the error cannot leave a half-started round behind.
    // goals: W-02
    func testFailedCourseStartCanRetryWithoutLeavingAProvisionalRound() async throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let option = WatchCourseOption(
            globalId: 31795, name: "Black Knight B/C", holes: 18, teeBox: "blue",
            segmentHoles: 18, tees: ["blue"]
        )
        let selection = WatchCourseSelection(front: option, teeBox: "blue")
        let config = WatchRoundConfig(
            baseURL: URL(string: "https://caddie.example")!,
            adminToken: nil,
            sessionToken: "player-token"
        )
        var attempts = 0
        let library = WatchCourseLibrary(
            store: WatchCourseStore(directoryURL: dir.appendingPathComponent("courses")),
            imageStore: WatchHoleImageStore(directoryURL: dir.appendingPathComponent("images")),
            makeRoundId: { "retry-round" },
            now: { Self.fixedNow },
            clientFactory: { clientConfig in
                WatchBackendClient(
                    baseURL: clientConfig.baseURL,
                    sessionToken: clientConfig.sessionToken,
                    dataLoader: { request in
                        attempts += 1
                        if attempts == 1 { throw CancellationError() }
                        let data = WatchPackageFixture.packageData(
                            roundId: "retry-round",
                            course: #"{"globalId":31795,"name":"Black Knight","teeBox":"blue"}"#,
                            loops: [WatchPackageFixture.Loop(31795, "front"), WatchPackageFixture.Loop(31795, "back")]
                        )
                        return (data, HTTPURLResponse(
                            url: try XCTUnwrap(request.url), statusCode: 200,
                            httpVersion: nil, headerFields: ["Content-Type": "application/json"]
                        )!)
                    },
                    retrySleep: { _ in }
                )
            }
        )

        let failedStart = await library.startCourse(selection, config: config)
        XCTAssertNil(failedStart)
        XCTAssertEqual(library.errorMessage, "球场下载失败，请保持联网后重试")
        XCTAssertNil(library.preparingCourseId)
        XCTAssertNil(WatchCourseStore(directoryURL: dir.appendingPathComponent("courses")).course(
            loopKey: selection.loopKey, teeBox: selection.teeBox
        ))

        let retriedStart = await library.startCourse(selection, config: config)
        let retried = try XCTUnwrap(retriedStart)
        XCTAssertEqual(attempts, 2)
        XCTAssertEqual(retried.roundId, "retry-round")
        XCTAssertNil(library.errorMessage)
        XCTAssertNil(library.preparingCourseId)
        await library.waitForWholeCourseTemplateInstalls()
    }

    /// A process kill mid-round: a new model on the same directory offers Resume, and resuming
    /// brings back the score draft and the hole; saving continues with unique event ids.
    // goals: W-02 [main]
    func testRoundSurvivesProcessKillAndResumesWhereItStopped() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        let roundId = try XCTUnwrap(model.round?.roundId)
        scoreActiveHole(model, score: 5)
        model.startScoringActiveHole()
        model.startManualScoreEntry()
        model.setDraftScore(6)
        XCTAssertEqual(model.activeHole, 2)

        let relaunched = makeModel(dir, ids: sequentialIds("relaunch"))

        XCTAssertEqual(relaunched.screen, .resume)
        XCTAssertEqual(relaunched.round?.roundId, roundId)
        XCTAssertNil(relaunched.scoringHole, "the draft waits for an explicit Resume")

        relaunched.resumeRound()
        XCTAssertEqual(relaunched.screen, .scoring)
        XCTAssertEqual(relaunched.scoringHole, 2)
        XCTAssertEqual(relaunched.draftScore, 6)
        XCTAssertEqual(relaunched.activeHole, 2)

        relaunched.saveManualScore()
        let store = WatchRoundStore(directoryURL: dir)
        let events = store.pendingEvents()
        XCTAssertEqual(Set(events.map(\.eventId)).count, events.count)
        XCTAssertTrue(events.allSatisfy { $0.roundId == roundId })
        XCTAssertEqual(store.holeState(hole: 1)?.score, 5)
        XCTAssertEqual(store.holeState(hole: 2)?.score, 6)
        XCTAssertEqual(relaunched.activeHole, 3)
        XCTAssertEqual(relaunched.screen, .home)
    }

    /// A standalone practice round starts with no phone and no backend config.
    // goals: W-02
    func testStandalonePracticeRoundStartsWithoutPhoneOrConfig() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)

        model.startPracticeRound()

        XCTAssertNil(model.config)
        XCTAssertEqual(model.round?.roundId, "watch-evt-1")
        XCTAssertEqual(model.holeCount, 18)
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertNil(model.round?.loopKey)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.uploadError)
        let store = WatchRoundStore(directoryURL: dir)
        XCTAssertEqual(store.load()?.roundId, "watch-evt-1")
        XCTAssertTrue(store.pendingEvents().isEmpty)
    }

    /// The four ways a round starts (phone-prepared states, practice, phone seed, course library)
    /// each give one round id on every hole and the expected table.
    // goals: W-02
    func testFourStartOrdersEachPersistOneConsistentRound() throws {
        // seedRound with prepared course states.
        let seededDir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: seededDir) }
        let seeded = makeModel(seededDir, ids: sequentialIds())
        seeded.seedRound(
            courseHoles("81001:front", roundId: "seeded-r"),
            activeHole: 1, courseName: "Seeded", courseGlobalId: 81001, teeBox: "blue",
            loopKey: "81001:front"
        )

        // startPracticeRound.
        let practiceDir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: practiceDir) }
        let practice = makeModel(practiceDir, ids: sequentialIds())
        practice.startPracticeRound(holeCount: 9)

        // applyRoundSeed from the phone.
        let phoneDir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: phoneDir) }
        let phone = makeModel(phoneDir, ids: sequentialIds())
        phone.applyRoundSeed(WatchRoundSeed(
            roundId: "phone-r", courseName: "Back Nine", activeHole: 1,
            holes: courseSeedHoles("81001:back"), globalId: 81001, teeBox: "blue", loopKey: "81001:back"
        ))

        // The course library's immediate start.
        let libraryDir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: libraryDir) }
        let library = WatchCourseLibrary(
            store: WatchCourseStore(directoryURL: libraryDir.appendingPathComponent("courses")),
            imageStore: WatchHoleImageStore(directoryURL: libraryDir.appendingPathComponent("images")),
            makeRoundId: { "lib-c" },
            now: { Self.fixedNow }
        )
        let option = WatchCourseOption(
            globalId: 31795, name: "Black Knight B/C", holes: 18, teeBox: "blue",
            segmentHoles: 18, tees: ["blue"]
        )
        let selection = WatchCourseSelection(front: option, teeBox: "blue")
        let prepared = try XCTUnwrap(library.startCourseImmediately(selection))
        let libraryModel = makeModel(libraryDir.appendingPathComponent("round"), ids: sequentialIds())
        libraryModel.seedRound(
            prepared.holeStates, activeHole: 1, courseName: prepared.courseName,
            courseGlobalId: 31795, teeBox: "blue", loopKey: selection.loopKey
        )

        let cases: [(WatchRoundModel, URL, String, String?, Int)] = [
            (seeded, seededDir, "seeded-r", "81001:front", 9),
            (practice, practiceDir, "watch-evt-1", nil, 9),
            (phone, phoneDir, "phone-r", "81001:back", 9),
            (libraryModel, libraryDir.appendingPathComponent("round"), "lib-c", "31795:front+31795:back", 18),
        ]
        for (model, dir, roundId, loopKey, holes) in cases {
            XCTAssertEqual(model.round?.roundId, roundId)
            XCTAssertEqual(model.round?.loopKey, loopKey, roundId)
            XCTAssertEqual(model.holeCount, holes, roundId)
            XCTAssertEqual(model.activeHole, 1, roundId)
            XCTAssertTrue(model.round?.holeStates.allSatisfy { $0.roundId == roundId } == true, roundId)
            XCTAssertEqual(WatchRoundStore(directoryURL: dir).load()?.roundId, roundId)
        }
        XCTAssertEqual(phone.screen, .resume, "a phone seed waits for Resume")
        XCTAssertEqual(practice.screen, .home)
        XCTAssertEqual(seeded.screen, .home)
        XCTAssertEqual(libraryModel.screen, .home)
    }

    /// Every ordered pair of course halves is a legal second-loop transition. The physical hole
    /// identities remain in the selected order, including when the same half is played twice.
    // goals: W-02
    func testSecondLoopStateMachinePreservesAllFrontBackOrders() async throws {
        let orders = [("front", "front"), ("front", "back"), ("back", "front"), ("back", "back")]
        for (first, second) in orders {
            let dir = tempDirectory()
            defer { try? FileManager.default.removeItem(at: dir) }
            let model = makeModel(dir, ids: sequentialIds("\(first)-\(second)"))
            let firstKey = "81001:\(first)"
            let combinedKey = "81001:\(first)+81001:\(second)"
            let calls = LoaderCalls()
            model.secondLoopLoader = { request in
                calls.requests.append(request)
                let secondStates = self.courseHoles(combinedKey, roundId: "order-\(first)-\(second)")
                    .filter { $0.hole >= 10 }
                return .ready(loopKey: combinedKey, holeStates: secondStates)
            }
            model.seedRound(
                courseHoles(firstKey, roundId: "order-\(first)-\(second)"), activeHole: 1,
                courseName: "Order Course", courseGlobalId: 81001, teeBox: "blue", loopKey: firstKey
            )
            model.selectHole(9)
            scoreActiveHole(model)
            XCTAssertEqual(model.screen, .turn)
            model.chooseTurnSecond(.loop("81001:\(second)"))
            await model.confirmTurn()

            XCTAssertEqual(model.screen, .home)
            XCTAssertEqual(model.round?.loopKey, combinedKey)
            let rows = try XCTUnwrap(WatchCourseSelection.roundRows(loopKey: combinedKey))
            XCTAssertEqual(model.round?.holeStates.map(\.sourceLocalHole), rows.map(\.sourceLocalHole))
            XCTAssertEqual(model.activeHole, 10)
            XCTAssertEqual(calls.requests.count, 1)
            XCTAssertEqual(calls.requests[0].secondHalf, second)
        }
    }

    /// Round B's seed arrives while round A holds scores: it waits, and once A is abandoned B starts
    /// clean, with nothing of A, and A's seed can never come back.
    // goals: W-02
    func testNextRoundSeedCarriesNothingFromThePreviousRound() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        let roundA = try XCTUnwrap(model.round?.roundId)
        scoreActiveHole(model, score: 6)

        let seedB = frontSeed(roundId: "round-b", courseName: "Round B")
        model.applyRoundSeed(seedB)
        XCTAssertEqual(model.round?.roundId, roundA, "a round with scores is never replaced silently")
        XCTAssertEqual(model.pendingPhoneRoundCourseName, "Round B")
        XCTAssertEqual(model.screen, .resume)

        model.requestAbandon()
        XCTAssertEqual(model.screen, .abandonConfirmation)
        model.confirmAbandon()

        let store = WatchRoundStore(directoryURL: dir)
        XCTAssertTrue(store.isClosed(roundId: roundA))
        XCTAssertEqual(model.lastRoundClosure?.roundId, roundA)
        XCTAssertEqual(model.round?.roundId, "round-b")
        XCTAssertNil(model.pendingPhoneRoundCourseName)
        XCTAssertEqual(model.round?.loopKey, "81001:front")
        XCTAssertEqual(model.holeCount, 9)
        XCTAssertTrue(model.round?.holeStates.allSatisfy {
            $0.roundId == "round-b" && $0.score == 0 && $0.putts == 0 && $0.penaltyCount == 0
        } == true)
        XCTAssertNil(model.round?.scoreDraft)
        XCTAssertTrue(store.pendingEvents().isEmpty)

        let staleA = WatchRoundSeed(
            roundId: roundA, courseName: "Round A again", activeHole: 1,
            holes: courseSeedHoles("81001:front"), globalId: 81001, loopKey: "81001:front"
        )
        model.applyRoundSeed(staleA)
        XCTAssertEqual(model.round?.roundId, "round-b", "a closed round's seed is ignored")
    }

    /// Idle (no round) rejects round events; a start whose holes carry an incomplete identity is
    /// refused with a message and leaves the Watch idle.
    // goals: W-02
    func testIdleRejectsRoundEventsAndAnIncompleteStart() async throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())

        model.resumeRound()
        model.startScoringActiveHole()
        model.goToNextHole()
        model.goToPreviousHole()
        model.openTurn()
        model.requestAbandon()
        model.confirmAbandon()
        model.saveManualScore()
        await model.confirmTurn()

        XCTAssertNil(model.round)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.scoringHole)
        XCTAssertNil(model.turnPlan)

        // Course identity on the holes without a loop key is contradictory.
        model.seedRound(courseHoles("81001:front", roundId: "broken"), activeHole: 1)
        XCTAssertNil(model.round)
        XCTAssertEqual(model.uploadError, "球局数据不完整，无法开局")
        XCTAssertNil(WatchRoundStore(directoryURL: dir).load())
    }

    /// Active → finish confirmation, with its cancel paths; an active round without any score goes
    /// to abandon instead, and finish confirmation is rejected from the wrong screen.
    // goals: W-02
    func testActiveRoundReachesFinishConfirmationOnlyThroughFinishing() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()

        // Unscored: finishing offers abandon, which can be cancelled.
        model.requestFinish()
        XCTAssertEqual(model.screen, .finishing)
        model.requestFinishConfirmation()
        XCTAssertEqual(model.screen, .abandonConfirmation)
        model.cancelAbandon()
        XCTAssertEqual(model.screen, .finishing)
        model.keepPlaying()
        XCTAssertEqual(model.screen, .home)

        scoreActiveHole(model, score: 4)
        model.requestFinishConfirmation()
        XCTAssertEqual(model.screen, .home, "finish confirmation is only reachable from finishing")
        model.cancelFinishConfirmation()
        XCTAssertEqual(model.screen, .home)

        model.requestFinish()
        model.requestFinishConfirmation()
        XCTAssertEqual(model.screen, .finishConfirmation)
        XCTAssertNil(model.uploadError)
        model.cancelFinishConfirmation()
        XCTAssertEqual(model.screen, .finishing)
        model.requestFinishConfirmation()
        XCTAssertEqual(model.screen, .finishConfirmation)
        XCTAssertNotNil(model.round, "confirmation alone closes nothing")
        XCTAssertFalse(WatchRoundStore(directoryURL: dir).isClosed(roundId: "watch-evt-1"))
    }

    // MARK: - W-03 navigation and the turn

    /// Saving hole 9 of a half opens the turn; the second nine is chosen, loaded and played as round
    /// holes 10–18 of the same round; it can still be changed until something is recorded on it.
    // goals: W-03 [main]
    func testTurnChoosesLoadsAndStartsTheSecondNine() async throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        let calls = LoaderCalls()
        installReadyLoader(model, calls: calls)

        model.seedRound(
            courseHoles("81001:front", roundId: "turn-r"),
            activeHole: 1, courseName: "Turn Course", courseGlobalId: 81001, teeBox: "blue",
            loopKey: "81001:front"
        )
        model.chooseTurnSecond(.loop("81001:back"))
        await model.confirmTurn()
        XCTAssertNil(model.turnPlan, "no turn choice while the first nine is active")
        XCTAssertTrue(calls.requests.isEmpty)

        model.selectHole(9)
        scoreActiveHole(model)
        XCTAssertEqual(model.screen, .turn)
        XCTAssertEqual(model.turnPlan?.first, "81001:front")
        XCTAssertEqual(model.turnPlan?.second, .loop("81001:back"), "the other half is the default")

        model.chooseTurnSecond(.loop("99999:front"))
        XCTAssertEqual(model.turnPlan?.second, .loop("81001:back"), "an unknown loop is ignored")
        model.chooseTurnSecond(.loop("81001:front"))
        XCTAssertEqual(model.turnPlan?.second, .loop("81001:front"))

        await model.confirmTurn()

        XCTAssertEqual(calls.requests, [WatchSecondLoopRequest(
            roundId: "turn-r", firstLoopKey: "81001:front", secondHalf: "front", teeBox: "blue",
            secondNineLoopGlobalId: nil
        )])
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.turnPlan)
        XCTAssertEqual(model.activeHole, 10)
        XCTAssertEqual(model.holeCount, 18)
        XCTAssertEqual(model.round?.roundId, "turn-r")
        XCTAssertEqual(model.round?.loopKey, "81001:front+81001:front")
        XCTAssertEqual(model.round?.secondNineAddedAtTurn, true)
        XCTAssertEqual(model.activeHoleState?.sourceLocalHole, 1)
        XCTAssertTrue(model.canChangeSecondNine)
        let store = WatchRoundStore(directoryURL: dir)
        XCTAssertEqual(store.load()?.holeStates.count, 18)
        XCTAssertEqual(store.loadNineLoopPairings(), ["81001:front": "81001:front"])

        model.openChangeSecondNine()
        XCTAssertEqual(model.screen, .turn)
        XCTAssertTrue(model.isChangingSecondNine)
        XCTAssertEqual(model.turnPlan?.second, .loop("81001:front"))
        model.leaveTurn()
        XCTAssertEqual(model.screen, .home)
        XCTAssertFalse(model.isChangingSecondNine)
        XCTAssertNil(model.turnPlan)
        XCTAssertEqual(model.activeHole, 10)
    }

    /// At the turn hole 9 is still editable: leave the turn, fix hole 9, and Next offers the turn
    /// again with the earlier choice.
    // goals: W-03
    func testNinthHoleStaysEditableAtTheTurn() async throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        reachTurn(model)
        XCTAssertEqual(model.screen, .turn)
        model.chooseTurnSecond(.loop("81001:front"))

        model.leaveTurn()
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.activeHole, 9)
        model.startEditingHole(9)
        model.setDraftScore(6)
        model.saveManualScore()

        XCTAssertEqual(model.screen, .home, "an edit of hole 9 does not jump to the turn")
        XCTAssertEqual(WatchRoundStore(directoryURL: dir).holeState(hole: 9)?.score, 6)
        XCTAssertEqual(model.holeCount, 9)

        model.goToNextHole()
        XCTAssertEqual(model.screen, .turn)
        XCTAssertEqual(model.turnPlan?.second, .loop("81001:front"), "the choice made before is kept")
    }

    /// Once round hole 10 is scored the second nine is locked: it cannot be changed or the turn
    /// reopened, and turn choices are ignored.
    // goals: W-03
    func testSecondNineLocksOnceHoleTenIsScored() async throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        let calls = LoaderCalls()
        installReadyLoader(model, calls: calls)
        reachTurn(model)
        model.chooseTurnSecond(.loop("81001:front"))
        await model.confirmTurn()
        XCTAssertEqual(model.activeHole, 10)
        XCTAssertTrue(model.canChangeSecondNine)

        scoreActiveHole(model, score: 5)
        XCTAssertEqual(model.activeHole, 11)
        XCTAssertFalse(model.canChangeSecondNine)

        model.openChangeSecondNine()
        XCTAssertEqual(model.screen, .home)
        XCTAssertFalse(model.isChangingSecondNine)
        model.openTurn()
        XCTAssertEqual(model.screen, .home)
        model.chooseTurnSecond(.stopAfterNine)
        await model.confirmTurn()
        XCTAssertNil(model.turnPlan)
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(calls.requests.count, 1)

        model.selectHole(9)
        model.goToNextHole()
        XCTAssertEqual(model.activeHole, 10, "from hole 9 Next just moves on once the turn is taken")
        XCTAssertEqual(model.screen, .home)
        XCTAssertEqual(model.round?.loopKey, "81001:front+81001:front")
    }

    /// Previous on hole 1 and Next on the scored last hole stay put; Next on an unscored hole opens
    /// scoring instead of moving.
    // goals: W-03
    func testFirstAndLastHoleBoundariesHoldTheCursor() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()

        model.goToPreviousHole()
        XCTAssertEqual(model.activeHole, 1)
        XCTAssertEqual(model.screen, .home)

        model.selectHole(18)
        XCTAssertEqual(model.activeHole, 18)
        model.goToNextHole()
        XCTAssertEqual(model.screen, .scoring, "Next on an unscored hole opens its score")
        XCTAssertEqual(model.scoringHole, 18)
        model.startManualScoreEntry()
        model.saveManualScore()
        XCTAssertEqual(model.activeHole, 18)
        XCTAssertEqual(model.screen, .home)

        model.goToNextHole()
        XCTAssertEqual(model.activeHole, 18)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.turnPlan, "an 18-hole round has no turn")

        model.goToPreviousHole()
        XCTAssertEqual(model.activeHole, 17)
        XCTAssertEqual(WatchRoundStore(directoryURL: dir).load()?.activeHole, 17)
    }

    /// A nine-hole round without a loop key has no second loop: saving hole 9 never opens a turn.
    // goals: W-03
    func testNineHolePracticeRoundHasNoSecondLoop() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound(holeCount: 9)

        model.selectHole(9)
        scoreActiveHole(model)

        XCTAssertEqual(model.screen, .home)
        XCTAssertFalse(model.isAtTurn)
        model.openTurn()
        model.goToNextHole()
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(model.turnPlan)
        XCTAssertEqual(model.activeHole, 9)
        XCTAssertEqual(model.holeCount, 9)
    }

    /// A nine-hole loop venue reaches the turn too; a missing or unavailable loader keeps the turn
    /// open with a message, and stopping after nine goes to finishing.
    // goals: W-03
    func testNineLoopVenueTurnReportsUnavailableAndCanStopAfterNine() async throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.seedRound(
            courseHoles("90417:all", roundId: "loop-r"),
            activeHole: 1, courseName: "Loop Venue", courseGlobalId: 90417, teeBox: "blue",
            loopKey: "90417:all"
        )
        model.selectHole(9)
        scoreActiveHole(model)
        XCTAssertEqual(model.screen, .turn)
        XCTAssertEqual(model.turnPlan?.first, "90417:all")

        model.chooseTurnSecond(.loop("90417:all"))
        await model.confirmTurn()
        XCTAssertEqual(model.turnMessage, "暂时无法准备第二个 9 洞，请重试")
        XCTAssertEqual(model.screen, .turn)

        let calls = LoaderCalls()
        model.secondLoopLoader = { request in
            calls.requests.append(request)
            return .unavailable("球场数据暂不可用")
        }
        await model.confirmTurn()
        XCTAssertEqual(calls.requests.first?.secondHalf, "all")
        XCTAssertEqual(calls.requests.first?.secondNineLoopGlobalId, 90417)
        XCTAssertEqual(model.turnMessage, "球场数据暂不可用")
        XCTAssertEqual(model.screen, .turn)
        XCTAssertEqual(model.holeCount, 9)

        model.chooseTurnSecond(.stopAfterNine)
        XCTAssertNil(model.turnMessage)
        await model.confirmTurn()
        XCTAssertEqual(model.screen, .finishing)
        XCTAssertNil(model.turnPlan)
        XCTAssertEqual(model.holeCount, 9)
    }
}
