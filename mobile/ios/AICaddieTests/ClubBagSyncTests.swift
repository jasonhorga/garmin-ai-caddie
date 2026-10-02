@testable import AICaddie
import XCTest

/// A fake `PUT /players/me/clubs/bag`: records every payload, can fail a number of times, and can
/// hold one request in flight until the test releases it.
@MainActor
private final class FakeBagServer {
    var received: [[ManualClubInput]] = []
    var failuresLeft = 0
    var holdNext = false
    private var gate: CheckedContinuation<Void, Never>?
    var isHolding: Bool { gate != nil }

    func send(_ clubs: [ManualClubInput]) async throws {
        received.append(clubs)
        if holdNext {
            holdNext = false
            await withCheckedContinuation { gate = $0 }
        }
        if failuresLeft > 0 {
            failuresLeft -= 1
            throw URLError(.notConnectedToInternet)
        }
    }

    func release() {
        gate?.resume()
        gate = nil
    }
}

/// Records the coordinator's pauses (debounce and retry backoff) instead of sleeping.
@MainActor
private final class FakeSleeper {
    var naps: [UInt64] = []
    var onNap: (() -> Void)?

    func nap(_ nanoseconds: UInt64) async {
        naps.append(nanoseconds)
        onNap?()
        await Task.yield()
    }
}

/// B5c 球包 persistence (Codex review on #366): every edit and the reset reach the server through
/// one durable, serialized outbox that a screen cannot cancel.
final class ClubBagSyncTests: XCTestCase {
    private var suite: UserDefaults!
    private let suiteName = "ClubBagSyncTests"

    override func setUp() {
        super.setUp()
        UserDefaults().removePersistentDomain(forName: suiteName)
        suite = UserDefaults(suiteName: suiteName)
        ClubBagStore.defaults = suite
    }

    override func tearDown() {
        ClubBagStore.defaults = .standard
        UserDefaults().removePersistentDomain(forName: suiteName)
        super.tearDown()
    }

    @MainActor
    private func makeCoordinator(_ server: FakeBagServer, sleeper: FakeSleeper = FakeSleeper()) -> ClubBagSyncCoordinator {
        let coordinator = ClubBagSyncCoordinator(sleep: { await sleeper.nap($0) })
        coordinator.configure(sender: { try await server.send($0) })
        return coordinator
    }

    private func tokens(_ clubs: [ManualClubInput]?) -> [String] {
        (clubs ?? []).map(\.token)
    }

    // MARK: - The outbox

    @MainActor
    func testLeavingTheScreenRightAfterAnEditStillSendsIt() async {
        let server = FakeBagServer()
        let sleeper = FakeSleeper()
        let coordinator = makeCoordinator(server, sleeper: sleeper)
        var model: ClubBagEditorModel? = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        model?.add("七号铁")
        // Back / close 球包 inside the 0.8 s pause: the screen and its model are gone.
        model = nil
        XCTAssertTrue(server.received.isEmpty, "nothing is sent before the pause")
        await coordinator.flush()
        XCTAssertEqual(server.received.map(tokens), [["iron7"]])
        XCTAssertEqual(sleeper.naps.first, ClubBagSyncCoordinator.debounceNanoseconds)
        XCTAssertNil(coordinator.pendingClubs, "the outbox is empty once the server has it")
        XCTAssertEqual(coordinator.status, .idle)
    }

    @MainActor
    func testAnUnsentEditSurvivesARelaunch() async {
        // No backend yet (or the app is killed): the edit waits in the durable outbox.
        let first = ClubBagSyncCoordinator(sleep: { _ in })
        first.enqueue([ManualClubInput(token: "iron7", distanceM: 139)])
        await first.flush()
        XCTAssertEqual(first.status, .pending)
        // Next launch: configuring the sender resumes it without another edit.
        let server = FakeBagServer()
        let relaunched = ClubBagSyncCoordinator(sleep: { _ in })
        XCTAssertEqual(relaunched.status, .pending)
        relaunched.configure(sender: { try await server.send($0) })
        await relaunched.flush()
        XCTAssertEqual(server.received, [[ManualClubInput(token: "iron7", distanceM: 139)]])
        XCTAssertNil(relaunched.pendingClubs)
    }

    @MainActor
    func testEditsDuringAnInFlightPutEndWithTheLatestBagOnTheServer() async {
        let server = FakeBagServer()
        let coordinator = makeCoordinator(server)
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        server.holdNext = true
        model.add("七号铁")
        while !server.isHolding { await Task.yield() }
        // Two more edits while the first PUT is still on the wire.
        model.setDistance("七号铁", 152)
        model.add("八号铁")
        server.release()
        await coordinator.flush()
        XCTAssertEqual(server.received.count, 2, "one PUT at a time; the newer edits coalesce")
        XCTAssertEqual(server.received[0], [ManualClubInput(token: "iron7")])
        XCTAssertEqual(server.received[1], [
            ManualClubInput(token: "iron7", distanceM: 139),
            ManualClubInput(token: "iron8"),
        ])
        XCTAssertNil(coordinator.pendingClubs)
    }

    @MainActor
    func testAFailedWriteIsRetriedWithoutAnotherEdit() async {
        let server = FakeBagServer()
        let sleeper = FakeSleeper()
        let coordinator = makeCoordinator(server, sleeper: sleeper)
        var statusWhileWaiting: [ClubBagSyncCoordinator.Status] = []
        sleeper.onNap = { statusWhileWaiting.append(coordinator.status) }
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        server.failuresLeft = 2
        model.add("七号铁")
        await coordinator.flush()
        XCTAssertEqual(server.received.map(tokens), [["iron7"], ["iron7"], ["iron7"]])
        XCTAssertEqual(coordinator.failedAttempts, 2)
        XCTAssertEqual(Array(sleeper.naps.dropFirst()), [
            ClubBagSyncCoordinator.retryDelay(afterFailures: 1),
            ClubBagSyncCoordinator.retryDelay(afterFailures: 2),
        ])
        XCTAssertEqual(Array(statusWhileWaiting.dropFirst()), [.failed, .failed], "the screen shows the retry")
        XCTAssertEqual(coordinator.status, .idle)
        XCTAssertNil(coordinator.pendingClubs)
        XCTAssertEqual(ClubBagSyncCoordinator.retryDelay(afterFailures: 1), 2_000_000_000)
        XCTAssertEqual(ClubBagSyncCoordinator.retryDelay(afterFailures: 20), 60_000_000_000)
    }

    // MARK: - 用 Garmin 球包重置

    @MainActor
    private func seedManualBag() {
        ClubBagStore.saveRealBag(["一号木", "七号铁", "推杆"])
        ClubBagStore.save(["一号木", "七号铁", "八号铁"])
        ClubBagStore.saveManualDistancesYd(["七号铁": 160, "八号铁": 150])
    }

    @MainActor
    func testResetClearsSelectionDistancesAndTheServerManualBag() async {
        seedManualBag()
        let server = FakeBagServer()
        let coordinator = makeCoordinator(server)
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        XCTAssertEqual(model.bag, ["一号木", "七号铁", "八号铁"])
        model.resetToGarminBag()
        XCTAssertEqual(model.bag, ["一号木", "七号铁", "推杆"], "the Garmin roster")
        XCTAssertEqual(model.distancesYd, [:])
        XCTAssertFalse(model.rows.contains { $0.isManual }, "no typed dots remain")
        XCTAssertNil(ClubBagStore.bag())
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), [:])
        XCTAssertEqual(ClubBagStore.manualCarriesM(), [:], "the caddie is back on history")
        await coordinator.flush()
        XCTAssertEqual(server.received, [[]], "PUT {\"clubs\": []} clears the server manual bag")
    }

    @MainActor
    func testAResetMadeOfflineIsRetriedUntilTheServerClears() async {
        seedManualBag()
        let server = FakeBagServer()
        server.failuresLeft = 1
        let coordinator = makeCoordinator(server)
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        model.resetToGarminBag()
        await coordinator.flush()
        XCTAssertEqual(server.received, [[], []])
        XCTAssertNil(coordinator.pendingClubs)
    }

    @MainActor
    func testAnEditRightAfterAResetSupersedesIt() async {
        seedManualBag()
        let server = FakeBagServer()
        let coordinator = makeCoordinator(server)
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        model.resetToGarminBag()
        model.add("八号铁")
        await coordinator.flush()
        XCTAssertEqual(server.received.map(tokens), [["driver", "iron7", "iron8", "putter"]],
                       "only the latest intent is sent; the reset is not resurrected after it")
        XCTAssertEqual(ClubBagStore.bag(), ["一号木", "七号铁", "八号铁", "推杆"])
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), [:], "the reset's cleared distances stay cleared")
    }

    // MARK: - Editing

    @MainActor
    func testAddAndRemoveAClub() async {
        let server = FakeBagServer()
        let coordinator = makeCoordinator(server)
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        model.add("七号铁")
        XCTAssertEqual(model.rows.map(\.name), ["七号铁"])
        XCTAssertFalse(model.addable.map(\.zhName).contains("七号铁"))
        model.setDistance("七号铁", 150)
        model.remove("七号铁")
        XCTAssertTrue(model.rows.isEmpty)
        XCTAssertNil(model.distancesYd["七号铁"], "a removed club drops its typed distance")
        XCTAssertTrue(model.addable.map(\.zhName).contains("七号铁"))
        await coordinator.flush()
        XCTAssertEqual(server.received.last, [])
    }

    @MainActor
    func testThePutterIsNeitherOfferedNorAddedOnTheLadder() {
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in })
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        XCTAssertFalse(model.addable.contains { $0.zhName == "推杆" })
        XCTAssertFalse(BagPresentation.addable(bag: []).contains { $0.category == .putter })
        model.add("推杆")
        XCTAssertTrue(model.bag.isEmpty)
        XCTAssertNil(coordinator.pendingClubs, "nothing invisible is queued")
        // A putter from the Garmin bag is kept (and sent) but has no ladder row.
        ClubBagStore.saveRealBag(["七号铁", "推杆"])
        let garmin = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        XCTAssertEqual(garmin.rows.map(\.name), ["七号铁"])
        garmin.setDistance("七号铁", 150)
        XCTAssertEqual(tokens(coordinator.pendingClubs), ["iron7", "putter"])
    }

    @MainActor
    func testRepeatedPlusAndMinusStepFromTheDistanceInUse() {
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in })
        ClubBagStore.save(["七号铁", "九号铁"])
        let model = ClubBagEditorModel(
            clubProfiles: [ClubProfile(clubName: "7I", sampleSize: 58, medianM: 137, p10M: 124, p90M: 146)],
            sync: coordinator
        )
        XCTAssertEqual(model.row(named: "七号铁")?.median, 150, "history median")
        for _ in 0..<3 { model.step("七号铁", by: 1) }
        model.step("七号铁", by: -1)
        XCTAssertEqual(model.row(named: "七号铁")?.median, 152)
        XCTAssertEqual(model.row(named: "七号铁")?.isManual, true)
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), ["七号铁": 152])
        XCTAssertEqual(coordinator.pendingClubs?.first { $0.token == "iron7" }?.distanceM, 139)
        // A club without shots starts from 100 yards.
        model.step("九号铁", by: -1)
        XCTAssertEqual(model.row(named: "九号铁")?.median, 99)
        // 用历史中位数 drops the typed value.
        model.setDistance("七号铁", nil)
        XCTAssertEqual(model.row(named: "七号铁")?.median, 150)
        XCTAssertEqual(model.row(named: "七号铁")?.isManual, false)
    }

    // MARK: - One effective carry for every consumer

    func testTheProjectionMovesTheBandAndKeepsAliasesTogether() {
        let profiles = [
            ClubProfile(clubName: "7I", sampleSize: 40, medianM: 128, p10M: 118, p90M: 136),
            ClubProfile(clubName: "7 Iron", sampleSize: 3, medianM: 120, p10M: 115, p90M: 125),
            ClubProfile(clubName: "Driver", sampleSize: 50, medianM: 210, p10M: 190, p90M: 225),
        ]
        let carries = ["七号铁": 155.0, "九号铁": 110.0]
        let projected = ClubBagStore.effectiveProfiles(profiles, carries: carries)
        XCTAssertEqual(projected[0], ClubProfile(clubName: "7I", sampleSize: 40, medianM: 155, p10M: 145, p90M: 163))
        XCTAssertEqual(projected[1], ClubProfile(clubName: "7 Iron", sampleSize: 3, medianM: 155, p10M: 150, p90M: 160))
        XCTAssertEqual(projected[2], profiles[2])
        XCTAssertEqual(projected[3], ClubProfile(clubName: "九号铁", sampleSize: 0, medianM: 110, p10M: 110, p90M: 110),
                       "a typed club without history still reaches the caddie")
        XCTAssertEqual(ClubBagStore.effectiveProfiles(projected, carries: carries), projected, "idempotent")
        XCTAssertEqual(ClubBagStore.effectiveProfiles(profiles, carries: [:]), profiles)
        // The same rule over a seed/request value, as the server's apply_manual_carries.
        let value = JSONValue.object([
            "7I": .object(["clubName": .string("7I"), "sampleSize": .number(40),
                           "median_m": .number(128), "p10_m": .number(118), "p90_m": .number(136)]),
        ])
        guard case .object(let rows)? = ClubBagStore.effectiveProfileValue(value, carries: carries),
              case .object(let seven)? = rows["7I"] else {
            return XCTFail("projected value")
        }
        XCTAssertEqual(seven["median_m"], .number(155))
        XCTAssertEqual(seven["p10_m"], .number(145))
        XCTAssertEqual(seven["p90_m"], .number(163))
        XCTAssertNotNil(rows["九号铁"])
    }

    @MainActor
    func testOneTypedCarryReachesEveryCaddieConsumer() throws {
        let package = try fixturePackage()
        let hole = try XCTUnwrap(package.holes.first)
        let historyEight = try XCTUnwrap(package.clubProfiles.first { zhClubName($0.clubName) == "八号铁" })
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in })
        ClubBagStore.save(["一号木", "八号铁"])
        let model = ClubBagEditorModel(clubProfiles: package.clubProfiles, sync: coordinator)

        for yards in [170, 150] {
            model.setDistance("八号铁", yards)
            let carry = ClubBagStore.carryMetres(yards: yards)
            XCTAssertNotEqual(carry, historyEight.medianM)
            // The 球包 row and the PUT payload.
            XCTAssertEqual(model.row(named: "八号铁")?.median, yards)
            XCTAssertEqual(coordinator.pendingClubs?.first { $0.token == "iron8" }?.distanceM, carry)
            // Map distance / club strip (CurrentHoleView) read the package projection.
            let eight = try XCTUnwrap(package.effectiveClubProfiles.first { zhClubName($0.clubName) == "八号铁" })
            XCTAssertEqual(eight.medianM, carry)
            XCTAssertEqual(eight.sampleSize, historyEight.sampleSize, "history stays attached")
            // Local decision seed.
            let seed = try XCTUnwrap(LiveCaddieSeedFactory.resolve(package: package, hole: hole, prep: nil))
            XCTAssertEqual(median(of: "八号铁", in: ClubBagStore.effectiveProfileValue(seed.context["clubProfiles"])), carry)
            // Online request (and the offline evaluator, which reads the request's profiles first).
            let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
                seed: seed,
                input: LiveCaddieInput(shotType: "tee", distanceToPinM: 300)
            )
            XCTAssertEqual(median(of: "八号铁", in: request.context["clubProfiles"]), carry)
            // A seed built without the projection (an installed server seed) is projected too.
            let synthesized = try XCTUnwrap(LiveCaddieSeedFactory.synthesize(package: package, hole: hole, prep: nil))
            XCTAssertEqual(median(of: "八号铁", in: synthesized.context["clubProfiles"]), carry)
            // Watch club list.
            let watch = WatchEventBridge().makeWatchRoundStatePayload(
                package: package, hole: hole, score: 0, putts: 0, penaltyCount: 0,
                selectedClub: nil, decision: nil
            )
            let watchEight = try XCTUnwrap(watch.availableClubs.first { zhClubName($0.clubName) == "八号铁" })
            XCTAssertEqual(watchEight.medianM, carry)
        }
    }

    private func median(of name: String, in value: JSONValue?) -> Double? {
        let rows: [JSONValue]
        switch value {
        case .object(let map)?: rows = Array(map.values)
        case .array(let list)?: rows = list
        default: return nil
        }
        for case .object(let row) in rows {
            guard case .string(let club)? = row["clubName"], zhClubName(club) == name,
                  case .number(let median)? = row["median_m"] else { continue }
            return median
        }
        return nil
    }

    private func fixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        return try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: url))
    }
}
