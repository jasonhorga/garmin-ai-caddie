@testable import AICaddie
import XCTest

/// A fake `PUT /players/me/clubs/bag`: records every payload, can fail a number of times, and can
/// hold one request in flight until the test releases it.
@MainActor
private final class FakeBagServer {
    var received: [[ManualClubInput]] = []
    var players: [String] = []
    var failuresLeft = 0
    /// An HTTP status every request is refused with (401 / 403 / 422 …).
    var rejectWith: Int?
    var holdNext = false
    private var gate: CheckedContinuation<Void, Never>?
    var isHolding: Bool { gate != nil }

    func send(_ player: String, _ clubs: [ManualClubInput]) async throws {
        received.append(clubs)
        players.append(player)
        if holdNext {
            holdNext = false
            await withCheckedContinuation { gate = $0 }
        }
        if let rejectWith {
            throw SyncClientError.http(status: rejectWith, body: nil)
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

/// Holds a cloud GET in flight until the test releases it.
@MainActor
private final class FetchGate {
    private var waiter: CheckedContinuation<Void, Never>?
    private var released = false

    func wait() async {
        guard !released else { return }
        await withCheckedContinuation { waiter = $0 }
    }

    func release() {
        released = true
        waiter?.resume()
        waiter = nil
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
        ClubBagStore.bind(playerId: nil, migrateLegacy: false)
    }

    override func tearDown() {
        ClubBagStore.bind(playerId: nil, migrateLegacy: false)
        ClubBagStore.defaults = .standard
        UserDefaults().removePersistentDomain(forName: suiteName)
        super.tearDown()
    }

    @MainActor
    private func makeCoordinator(_ server: FakeBagServer, sleeper: FakeSleeper? = nil) -> ClubBagSyncCoordinator {
        let sleeper = sleeper ?? FakeSleeper()
        let coordinator = ClubBagSyncCoordinator(sleep: { await sleeper.nap($0) })
        coordinator.configure(sender: { try await server.send($0, $1) })
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
        relaunched.configure(sender: { try await server.send($0, $1) })
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
        model.add("八号铁")
        XCTAssertEqual(Set(model.rows.map(\.name)), ["七号铁", "八号铁"])
        XCTAssertFalse(model.addable.map(\.zhName).contains("七号铁"))
        model.setDistance("七号铁", 150)
        model.remove("七号铁")
        XCTAssertEqual(model.rows.map(\.name), ["八号铁"])
        XCTAssertNil(model.distancesYd["七号铁"], "a removed club drops its typed distance")
        XCTAssertTrue(model.addable.map(\.zhName).contains("七号铁"))
        // The last club to hit with stays: an empty list would mean "no manual bag" on the server.
        XCTAssertFalse(model.canRemove("八号铁"))
        model.remove("八号铁")
        XCTAssertEqual(model.bag, ["八号铁"])
        await coordinator.flush()
        XCTAssertEqual(server.received.last, [ManualClubInput(token: "iron8")])
        // A putter does not count as a club to hit with.
        ClubBagStore.save(["八号铁", "推杆"])
        let withPutter = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        XCTAssertFalse(withPutter.canRemove("八号铁"))
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
        let authority = ClubBagAuthority(roster: nil, carriesM: carries)
        let projected = ClubBagStore.effectiveProfiles(profiles, authority: authority)
        XCTAssertEqual(projected[0], ClubProfile(clubName: "7I", sampleSize: 40, medianM: 155, p10M: 145, p90M: 163))
        XCTAssertEqual(projected[1], ClubProfile(clubName: "7 Iron", sampleSize: 3, medianM: 155, p10M: 150, p90M: 160))
        XCTAssertEqual(projected[2], profiles[2])
        XCTAssertEqual(projected[3], ClubProfile(clubName: "九号铁", sampleSize: 0, medianM: 110, p10M: 110, p90M: 110),
                       "a typed club without history still reaches the caddie")
        XCTAssertEqual(ClubBagStore.effectiveProfiles(projected, authority: authority), projected, "idempotent")
        XCTAssertEqual(ClubBagStore.effectiveProfiles(profiles, authority: ClubBagAuthority(roster: nil, carriesM: [:])), profiles)
        // A manual roster is authoritative: Driver taken out of 球包 is gone, aliases of a kept club stay.
        let roster = ClubBagAuthority(roster: ["七号铁", "九号铁"], carriesM: carries)
        XCTAssertEqual(ClubBagStore.effectiveProfiles(profiles, authority: roster).map(\.clubName), ["7I", "7 Iron", "九号铁"])
        // The same rule over a seed/request value, as the server's apply_manual_carries.
        let value = JSONValue.object([
            "7I": .object(["clubName": .string("7I"), "sampleSize": .number(40),
                           "median_m": .number(128), "p10_m": .number(118), "p90_m": .number(136)]),
        ])
        guard case .object(let rows)? = ClubBagStore.effectiveProfileValue(value, authority: authority),
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

    // MARK: - Per-account storage and target (Codex review 5947487991)

    @MainActor
    func testEachPlayerSavesToTheirOwnIdAndTheOwnerBuildToMe() async {
        let server = FakeBagServer()
        let coordinator = makeCoordinator(server)
        ClubBagEditorModel(clubProfiles: [], sync: coordinator).add("七号铁")
        await coordinator.flush()
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        ClubBagEditorModel(clubProfiles: [], sync: coordinator).add("八号铁")
        await coordinator.flush()
        XCTAssertEqual(server.players, ["me", "p_alice"], "a member never PUTs to the owner's /players/me")
        XCTAssertEqual(server.received.map(tokens), [["iron7"], ["iron8"]], "Alice starts from her own empty bag")
    }

    @MainActor
    func testAnAccountSwitchNeitherSendsNorShowsTheOtherPlayersBag() async {
        let server = FakeBagServer()
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in await Task.yield() })
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        // Alice edits with no backend yet: the PUT waits in HER outbox.
        ClubBagEditorModel(clubProfiles: [], sync: coordinator).add("七号铁")
        ClubBagStore.saveManualDistancesYd(["七号铁": 152])
        await coordinator.flush()
        // Bob signs in on the same phone.
        coordinator.activate(playerId: "p_bob", migrateLegacy: false)
        XCTAssertNil(ClubBagStore.bag(), "Bob's caddie never consumes Alice's roster")
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), [:])
        XCTAssertEqual(ClubBagAuthority.current, ClubBagAuthority(roster: nil, carriesM: [:]))
        XCTAssertNil(coordinator.pendingClubs)
        coordinator.configure(sender: { try await server.send($0, $1) })
        await coordinator.flush()
        XCTAssertTrue(server.received.isEmpty, "Alice's pending PUT is not sent with Bob's credentials")
        ClubBagEditorModel(clubProfiles: [], sync: coordinator).add("八号铁")
        await coordinator.flush()
        // Alice again (relaunch or switch back): her pending edit resumes for her id only.
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        await coordinator.flush()
        XCTAssertEqual(server.players, ["p_bob", "p_alice"])
        XCTAssertEqual(server.received.map(tokens), [["iron8"], ["iron7"]])
        XCTAssertEqual(ClubBagStore.bag(), ["七号铁"])
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), ["七号铁": 152])
    }

    @MainActor
    func testAnInFlightPutIsNotRetriedUnderTheNextAccount() async {
        let server = FakeBagServer()
        let coordinator = makeCoordinator(server)
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        server.holdNext = true
        server.failuresLeft = 1
        ClubBagEditorModel(clubProfiles: [], sync: coordinator).add("七号铁")
        while !server.isHolding { await Task.yield() }
        coordinator.activate(playerId: "p_bob", migrateLegacy: false)
        server.release()
        await coordinator.flush()
        for _ in 0..<5 { await Task.yield() }
        XCTAssertEqual(server.players, ["p_alice"], "the failed Alice PUT waits for Alice")
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        await coordinator.flush()
        XCTAssertEqual(server.players, ["p_alice", "p_alice"])
        XCTAssertNil(coordinator.pendingClubs)
    }

    @MainActor
    func testLegacyUnscopedBagMovesToTheFirstSignedInPlayerOnly() {
        ClubBagStore.save(["七号铁"])  // written before per-account storage
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in })
        coordinator.activate(playerId: "p_alice", migrateLegacy: true)
        XCTAssertEqual(ClubBagStore.bag(), ["七号铁"])
        coordinator.activate(playerId: "p_bob", migrateLegacy: true)
        XCTAssertNil(ClubBagStore.bag())
    }

    @MainActor
    func testASecondPhoneRestoresTheCloudBagBeforeEditing() async {
        let server = FakeBagServer()
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in })
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        var fetched: [String] = []
        let cloud = EffectiveClubBagResponse(schema: nil, source: "manual", found: true, clubs: [
            EffectiveClubBagClub(token: "iron7", zhName: "七号铁", customName: nil, clubTypeId: 16, distanceM: 139, distanceSource: "manual"),
            EffectiveClubBagClub(token: "driver", zhName: "一号木", customName: nil, clubTypeId: 1, distanceM: 200, distanceSource: "default"),
        ])
        coordinator.configure(sender: { try await server.send($0, $1) }, fetcher: { player in
            fetched.append(player)
            return cloud
        })
        let restored = await coordinator.restoreFromServer()
        XCTAssertTrue(restored)
        XCTAssertEqual(fetched, ["p_alice"])
        XCTAssertEqual(ClubBagStore.bag(), ["七号铁", "一号木"])
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), ["七号铁": 152], "only typed carries; a catalog default is not one")
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        XCTAssertEqual(model.row(named: "七号铁")?.median, 152)
        // The first edit on this phone keeps the restored roster instead of overwriting it.
        model.add("八号铁")
        await coordinator.flush()
        XCTAssertEqual(server.received.last, [
            ManualClubInput(token: "driver"), ManualClubInput(token: "iron7", distanceM: 139), ManualClubInput(token: "iron8"),
        ])
        // A queued local edit is newer than the cloud copy: no restore over it.
        coordinator.enqueue([ManualClubInput(token: "iron9")])
        let skipped = await coordinator.restoreFromServer()
        XCTAssertFalse(skipped)
        // The cloud has no manual bag (reset on another phone): the local override goes too.
        await coordinator.flush()
        coordinator.configure(sender: { try await server.send($0, $1) }, fetcher: { _ in
            EffectiveClubBagResponse(schema: nil, source: "garmin", found: true, clubs: [])
        })
        let cleared = await coordinator.restoreFromServer()
        XCTAssertTrue(cleared)
        XCTAssertNil(ClubBagStore.bag())
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), [:])
    }

    @MainActor
    func testPermanentRejectionsStopAndAreKeptUntilTheNextEdit() async {
        for code in [401, 403, 422] {
            UserDefaults().removePersistentDomain(forName: suiteName)
            let server = FakeBagServer()
            server.rejectWith = code
            let sleeper = FakeSleeper()
            let coordinator = makeCoordinator(server, sleeper: sleeper)
            coordinator.activate(playerId: "p_alice", migrateLegacy: false)
            let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
            model.add("七号铁")
            await coordinator.flush()
            XCTAssertEqual(server.received.count, 1, "\(code) is not retried")
            XCTAssertEqual(coordinator.status, .rejected(code))
            XCTAssertEqual(coordinator.pendingOutbox?.rejectedStatus, code, "the intent is kept")
            XCTAssertEqual(sleeper.naps, [ClubBagSyncCoordinator.debounceNanoseconds], "no retry backoff")
            XCTAssertNotNil(ClubSettingsView.syncNotice(coordinator.status))
            // A relaunch does not resend a rejected intent by itself…
            let relaunched = ClubBagSyncCoordinator(sleep: { _ in })
            relaunched.configure(sender: { try await server.send($0, $1) })
            await relaunched.flush()
            XCTAssertEqual(server.received.count, 1)
            XCTAssertEqual(relaunched.status, .rejected(code))
            // …a new edit does (after re-login, for example).
            server.rejectWith = nil
            model.add("八号铁")
            await coordinator.flush()
            XCTAssertEqual(server.received.count, 2)
            XCTAssertNil(coordinator.pendingClubs)
            XCTAssertEqual(coordinator.status, .idle)
            coordinator.activate(playerId: nil, migrateLegacy: false)
        }
        XCTAssertNil(ClubBagSyncCoordinator.permanentStatus(SyncClientError.http(status: 503, body: nil)))
        XCTAssertNil(ClubBagSyncCoordinator.permanentStatus(SyncClientError.http(status: 429, body: nil)))
        XCTAssertNil(ClubBagSyncCoordinator.permanentStatus(URLError(.timedOut)))
    }

    // MARK: - Route authority: removed clubs and changed carries reach the final consumers

    private func stalePrep() -> CoursePrepHole {
        // Prepared before the edit: 1W 210 m, then 8I at its old 128 m carry.
        CoursePrepHole(
            hole: 1, par: 4, parSource: "test", blueYards: 400, routeLenM: 360,
            geometryCoverage: "ready",
            candidateRoutes: [CoursePrepCandidateRoute(id: "alt", club: "1W", carryM: 210, riskScore: 1)],
            steps: [
                CoursePrepStep(club: "1W", note: "", clubName: "1W", targetCarryM: 210, routeOffsetM: 210, role: "tee", planIndex: 0),
                CoursePrepStep(club: "8I", note: "", clubName: "8I", targetCarryM: 128, routeOffsetM: 338, expectedRemainingM: 22, role: "scoring", planIndex: 1),
            ],
            teeClub: "1W"
        )
    }

    private func clubs(_ route: CaddiePlanSequence) -> [String] {
        route.steps.map { zhClubName($0.clubName) }
    }

    func testTheInstalledChainIsDroppedWhenItsClubOrCarryChanged() {
        let prep = stalePrep()
        func installed(_ authority: ClubBagAuthority) -> CaddiePlanSequence? {
            LiveCaddieRouteAuthority.installedRoute(prep: prep, par: 4, shotType: "tee", fallbackRouteEndM: nil, authority: authority)
        }
        XCTAssertNotNil(installed(ClubBagAuthority(roster: nil, carriesM: [:])), "unchanged bag: the chain stays")
        XCTAssertNotNil(installed(ClubBagAuthority(roster: ["一号木", "八号铁"], carriesM: ["八号铁": 128])))
        XCTAssertNil(installed(ClubBagAuthority(roster: nil, carriesM: ["八号铁": 155])), "8I is now 155 m: no 128 m landing")
        XCTAssertNil(installed(ClubBagAuthority(roster: ["八号铁", "九号铁"], carriesM: [:])), "Driver was taken out")
    }

    @MainActor
    func testRemovingDriverAndRetypingEightIronReachEveryFinalConsumer() throws {
        let package = try fixturePackage()
        let hole = try XCTUnwrap(package.holes.first)
        let prep = stalePrep()
        // 球包: Driver and 9I taken out, 8I typed at 170 yd (155 m).
        ClubBagStore.save(["八号铁", "七号铁"])
        ClubBagStore.saveManualDistancesYd(["八号铁": 170])
        let carry = ClubBagStore.carryMetres(yards: 170)
        let authority = ClubBagAuthority.current
        XCTAssertEqual(authority.carriesM, ["八号铁": carry])
        let removed: Set<String> = ["一号木", "九号铁"]

        // Map / route strip: the stale installed chain is gone.
        XCTAssertNil(LiveCaddieRouteAuthority.installedRoute(prep: prep, par: 4, shotType: "tee", fallbackRouteEndM: nil))

        // Synthesized seed (no installed seed for this hole) and the installed server seed.
        let synthesized = try XCTUnwrap(LiveCaddieSeedFactory.synthesize(package: package, hole: hole, prep: prep))
        let installed = try XCTUnwrap(LiveCaddieSeedFactory.resolve(package: package, hole: hole, prep: prep))
        for seed in [synthesized, installed] {
            XCTAssertNil(seed.context["canonicalShotPlan"], "the 1W→8I@128 chain is not replayed")
            if case .array(let routes)? = seed.context["candidateRoutes"] {
                for leg in routes.flatMap({ ClubBagAuthority.legs(of: $0) }) {
                    XCTAssertFalse(removed.contains(zhClubName(leg.club)), leg.club)
                }
            }
            XCTAssertFalse(seed.offlineOptions.isEmpty)
            for option in seed.offlineOptions {
                let name = zhClubName(option.clubName)
                XCTAssertFalse(removed.contains(name), "\(option.clubName) was taken out")
                if name == "八号铁" { XCTAssertEqual(option.carryM, carry) }
            }
            XCTAssertEqual(median(of: "八号铁", in: seed.context["clubProfiles"]), carry)
            XCTAssertNil(median(of: "一号木", in: seed.context["clubProfiles"]))

            // Online request, composed exactly like CurrentHoleView / 备战: the prep chain is added
            // back only if the 球包 authority still accepts it.
            let base = CaddieDecisionRequestBuilder().makeDecisionRequest(
                seed: seed, input: LiveCaddieInput(shotType: "tee", distanceToPinM: 300)
            )
            let request = CaddieDecisionRequestBuilder.addingCanonicalPlan(to: base, prep: prep)
            XCTAssertNil(request.context["canonicalShotPlan"], "the dropped 1W→8I@128 chain is not re-inserted")
            XCTAssertNotNil(
                CaddieDecisionRequestBuilder.addingCanonicalPlan(
                    to: base, prep: prep, authority: ClubBagAuthority(roster: nil, carriesM: [:])
                ).context["canonicalShotPlan"],
                "with an unchanged bag the same composition keeps the chain"
            )
            XCTAssertEqual(median(of: "八号铁", in: request.context["clubProfiles"]), carry)
            XCTAssertNil(median(of: "一号木", in: request.context["clubProfiles"]))

            // Offline decision: its selected option and every sequence leg use the new bag.
            let offline = try XCTUnwrap(OfflineCaddieDecisionEvaluator().makeDecision(seed: seed, request: request, strategyMode: nil))
            for route in CaddiePlanSequence.sequences(from: offline) {
                XCTAssertTrue(Set(clubs(route)).isDisjoint(with: removed), "\(clubs(route))")
                // A full tee leg with the 8I carries the typed distance (later legs may be trimmed
                // to the green window).
                if let first = route.steps.first, zhClubName(first.clubName) == "八号铁" {
                    XCTAssertEqual(first.targetCarryM ?? carry, carry, accuracy: 0.5)
                }
            }

            // The route set the map and the club strip draw from: a decision made before the edit
            // (Driver first) is not offered next to the fresh one.
            let staleOnline = driverDecision()
            let routes = LiveCaddieRouteAuthority.resolve(
                installed: LiveCaddieRouteAuthority.installedRoute(prep: prep, par: 4, shotType: "tee", fallbackRouteEndM: nil),
                online: staleOnline, offline: offline, par: 4, shotType: "tee"
            )
            for route in routes {
                XCTAssertTrue(Set(clubs(route)).isDisjoint(with: removed), "\(clubs(route))")
            }

            // The live screen's reconciliation keeps a retained route across refreshes. A route
            // retained before the edit (the old installed chain, or a Driver decision) is not kept.
            let staleInstalled = try XCTUnwrap(LiveCaddieRouteAuthority.installedRoute(
                prep: prep, par: 4, shotType: "tee", fallbackRouteEndM: nil,
                authority: ClubBagAuthority(roster: nil, carriesM: [:])
            ))
            let fresh = CaddiePlanSequence.sequences(from: freshDecision(carry: carry))
            XCTAssertFalse(fresh.isEmpty)
            for retained in [staleInstalled] + CaddiePlanSequence.sequences(from: staleOnline) {
                let reconciled = try XCTUnwrap(LiveCaddieRouteAuthority.reconciled(
                    incoming: fresh, existing: [retained], installed: staleInstalled, retained: retained,
                    explicitSelectionKey: nil, vetoInstalled: false
                ))
                // The map legs are drawn from these routes.
                for route in [reconciled.first] + reconciled.merged {
                    XCTAssertTrue(Set(clubs(route)).isDisjoint(with: removed), "\(clubs(route))")
                    for step in route.steps where zhClubName(step.clubName) == "八号铁" {
                        XCTAssertNotEqual(step.targetCarryM, 128, "no leg keeps the old 8I carry")
                    }
                }
            }

            // Watch: club list and route summary.
            let watch = WatchEventBridge().makeWatchRoundStatePayload(
                package: package, hole: hole, score: 0, putts: 0, penaltyCount: 0,
                selectedClub: nil, decision: offline
            )
            XCTAssertFalse(watch.availableClubs.contains { removed.contains(zhClubName($0.clubName)) })
            XCTAssertTrue(watch.availableClubs.contains { zhClubName($0.clubName) == "八号铁" })
            for club in watch.availableClubs where zhClubName(club.clubName) == "八号铁" {
                if let medianM = club.medianM { XCTAssertEqual(medianM, carry, accuracy: 0.5) }
            }
            let summary = watch.holePlanSummary ?? ""
            XCTAssertFalse(summary.contains("一号木") || summary.contains("1W") || summary.contains("九号铁"), summary)
        }
    }

    @MainActor
    func testABagChangeTellsTheLiveScreenToReplan() {
        final class Counter: @unchecked Sendable { var value = 0 }
        let counter = Counter()
        let token = NotificationCenter.default.addObserver(forName: ClubBagStore.didChange, object: nil, queue: nil) { _ in
            counter.value += 1
        }
        defer { NotificationCenter.default.removeObserver(token) }
        let before = ClubBagStore.revision
        let model = ClubBagEditorModel(clubProfiles: [], sync: ClubBagSyncCoordinator(sleep: { _ in }))
        model.add("七号铁")
        model.setDistance("七号铁", 150)
        model.setDistance("七号铁", 150)  // unchanged: no replan
        XCTAssertEqual(counter.value, 2)
        XCTAssertEqual(ClubBagStore.revision, before + 2)
    }

    /// A decision made after the edit: 7I then 8I at the typed carry.
    private func freshDecision(carry: Double) -> CaddieDecisionResponse {
        let sequence: [String: JSONValue] = [
            "id": .string("stock"),
            "clubs": .array([
                .object(["clubName": .string("7I"), "role": .string("tee"), "targetCarry_m": .number(128), "routeOffset_m": .number(128)]),
                .object([
                    "clubName": .string("8I"), "role": .string("scoring"), "targetCarry_m": .number(carry),
                    "routeOffset_m": .number(128 + carry), "expectedRemaining_m": .number(0),
                ]),
            ]),
            "completion": .string("scoring_window"),
        ]
        return CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2", decisionId: "after-the-edit", sourceRef: nil,
            evidenceRefs: nil, shotType: "tee", phase: "Tee", context: [:],
            options: [["id": .string("stock"), "clubName": .string("7I")]], selected: nil,
            selectedOptionId: "stock", selectedOption: nil,
            sequences: [sequence], selectedSequence: sequence,
            avoidZones: [], forbiddenZones: [], acceptableMiss: [:],
            evidence: [], confidence: [:], missingData: [], auditCriteria: []
        )
    }

    private func driverDecision() -> CaddieDecisionResponse {
        let sequence: [String: JSONValue] = [
            "id": .string("stock"),
            "clubs": .array([
                .object(["clubName": .string("1W"), "role": .string("tee"), "targetCarry_m": .number(210), "routeOffset_m": .number(210)]),
                .object([
                    "clubName": .string("8I"), "role": .string("scoring"), "targetCarry_m": .number(128),
                    "routeOffset_m": .number(338), "expectedRemaining_m": .number(0),
                ]),
            ]),
            "completion": .string("scoring_window"),
        ]
        return CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2", decisionId: "before-the-edit", sourceRef: nil,
            evidenceRefs: nil, shotType: "tee", phase: "Tee", context: [:],
            options: [["id": .string("stock"), "clubName": .string("1W")]], selected: nil,
            selectedOptionId: "stock", selectedOption: nil,
            sequences: [sequence], selectedSequence: sequence,
            avoidZones: [], forbiddenZones: [], acceptableMiss: [:],
            evidence: [], confidence: [:], missingData: [], auditCriteria: []
        )
    }

    // MARK: - Restore before the first edit (Codex review 5947998710)

    @MainActor
    func testEditsWaitForAHeldCloudRestoreAndThenBuildOnIt() async {
        let server = FakeBagServer()
        let gate = FetchGate()
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in })
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        var fetches = 0
        coordinator.configure(sender: { try await server.send($0, $1) }, fetcher: { _ in
            fetches += 1
            await gate.wait()
            return EffectiveClubBagResponse(schema: nil, source: "manual", found: true, clubs: [
                EffectiveClubBagClub(token: "wedge58", zhName: "58°", customName: nil, clubTypeId: nil, distanceM: 80, distanceSource: "manual"),
                EffectiveClubBagClub(token: "iron7", zhName: "七号铁", customName: nil, clubTypeId: 16, distanceM: 139, distanceSource: "manual"),
            ])
        })
        // A fresh phone: the screen opens on its local history bag while the GET is held.
        let model = ClubBagEditorModel(
            clubProfiles: [ClubProfile(clubName: "8I", sampleSize: 20, medianM: 122, p10M: 112, p90M: 130)],
            sync: coordinator
        )
        let launch = Task { await coordinator.restoreFromServer() }
        let screen = Task { await coordinator.restoreFromServer() }
        while coordinator.restoreState != .restoring { await Task.yield() }
        XCTAssertFalse(model.canEdit)
        XCTAssertNotNil(ClubSettingsView.restoreNotice(coordinator))
        model.add("九号铁")
        model.setDistance("八号铁", 140)
        model.resetToGarminBag()
        XCTAssertNil(coordinator.pendingClubs, "nothing built on the partial bag is queued")
        XCTAssertEqual(model.bag, ["八号铁"])
        gate.release()
        let restoredByLaunch = await launch.value
        let restoredByScreen = await screen.value
        XCTAssertTrue(restoredByLaunch && restoredByScreen)
        XCTAssertEqual(fetches, 1, "launch and the screen share one restore")
        model.reloadFromStore()
        XCTAssertTrue(model.canEdit)
        XCTAssertEqual(model.bag, ["七号铁", "58° 挖起杆"])
        model.add("九号铁")
        await coordinator.flush()
        XCTAssertEqual(server.received, [[
            ManualClubInput(token: "iron7", distanceM: 139), ManualClubInput(token: "iron9"),
            ManualClubInput(token: "wedge58", distanceM: 80),
        ]], "the first edit keeps the cloud-only clubs and carries")
    }

    @MainActor
    func testAFailedRestoreBlocksEditsOnlyOnAPhoneThatNeverMatchedTheCloud() async {
        let coordinator = ClubBagSyncCoordinator(sleep: { _ in })
        coordinator.activate(playerId: "p_alice", migrateLegacy: false)
        XCTAssertTrue(coordinator.canEdit, "no backend: local-only bag")
        coordinator.configure(sender: { _, _ in }, fetcher: { _ in throw URLError(.notConnectedToInternet) })
        let restored = await coordinator.restoreFromServer()
        XCTAssertFalse(restored)
        XCTAssertEqual(coordinator.restoreState, .failed)
        XCTAssertFalse(coordinator.canEdit)
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        model.add("七号铁")
        XCTAssertNil(coordinator.pendingClubs)
        // Once this phone has matched the cloud (an earlier restore or accepted PUT), offline
        // edits are safe: the durable outbox sends them later.
        ClubBagStore.hasSyncedWithCloud = true
        XCTAssertTrue(coordinator.canEdit)
        model.add("七号铁")
        XCTAssertEqual(tokens(coordinator.pendingClubs), ["iron7"])
        // Bob has never synced on this phone.
        coordinator.activate(playerId: "p_bob", migrateLegacy: false)
        XCTAssertEqual(coordinator.restoreState, .unknown)
        XCTAssertFalse(coordinator.canEdit)
    }

    // MARK: - Total roster projection (Codex review 5947998710)

    func testEverySelectedClubIsProjectedAndAnEmptyOrPutterOnlyRosterHasNoHittingClub() {
        let history = [ClubProfile(clubName: "5I", sampleSize: 30, medianM: 150, p10M: 140, p90M: 160)]
        func names(_ roster: Set<String>?, carries: [String: Double] = [:]) -> [String] {
            ClubBagStore.effectiveProfiles(history, authority: ClubBagAuthority(roster: roster, carriesM: carries))
                .map { "\($0.clubName)@\(Int($0.medianM))/\($0.sampleSize)" }
        }
        // Mixed roster: 5I from history, 7I from the catalog default, 7 wood has no default.
        XCTAssertEqual(names(["五号铁", "七号铁", "七号木", "推杆"]), ["5I@150/30", "七号铁@128/0"])
        XCTAssertEqual(names(["五号铁", "七号铁"], carries: ["七号铁": 140]), ["5I@150/30", "七号铁@140/0"])
        XCTAssertEqual(names(["推杆"]), [], "putter only: nothing to hit with")
        XCTAssertEqual(names([]), [], "an explicit empty roster is not the unknown bag")
        XCTAssertEqual(names(nil), ["5I@150/30"], "no manual bag: history as is")
        // The same over a seed/request value.
        let value = JSONValue.object(["5I": .object(["clubName": .string("5I"), "median_m": .number(150)])])
        guard case .object(let rows)? = ClubBagStore.effectiveProfileValue(
            value, authority: ClubBagAuthority(roster: ["五号铁", "七号铁"], carriesM: [:])
        ) else { return XCTFail("projected value") }
        XCTAssertEqual(Set(rows.keys), ["5I", "七号铁"])
        guard case .object(let empty)? = ClubBagStore.effectiveProfileValue(
            value, authority: ClubBagAuthority(roster: ["推杆"], carriesM: [:])
        ) else { return XCTFail("projected value") }
        XCTAssertTrue(empty.isEmpty)
        // Storage keeps an explicit empty roster explicit.
        ClubBagStore.save([])
        XCTAssertEqual(ClubBagStore.bag(), [])
        ClubBagStore.clearManual()
        XCTAssertNil(ClubBagStore.bag())
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
