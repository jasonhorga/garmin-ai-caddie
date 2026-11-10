// size: medium
// goals: I-13
//
// I-13: club-bag distance edits are queued for sync, can be made while offline, and the bag is
// restored from the server after a reinstall. Entry points: ClubBagEditorModel (the 球包 screen
// intents) and ClubBagSyncCoordinator (the durable outbox + cloud restore) talking to a real
// SyncClient. Only the HTTP edge (URLProtocol), UserDefaults suites and the backoff pause are faked.

import Foundation
import XCTest
@testable import AICaddie

private let clubBagGoalPlayer = "p_goal_bag"
private let clubBagGoalSuite = "ClubBagGoalTests"
private let clubBagGoalReinstallSuite = "ClubBagGoalTests.reinstall"

/// The cloud bag a previous phone saved: 七号铁 with a typed 139 m (152 yd) carry, 一号木 without one.
private let clubBagGoalCloud = [
    ManualClubInput(token: "iron7", distanceM: 139),
    ManualClubInput(token: "driver"),
]

private struct ClubBagGoalPutBody: Decodable {
    let clubs: [ManualClubInput]
}

/// Fake `/api/v2/players/{id}/clubs/bag`: an unversioned last-write-wins store that can be
/// offline (transport error) and records every PUT attempt, every committed PUT and every GET.
private final class ClubBagGoalServer: @unchecked Sendable {
    private let lock = NSLock()
    private var online: Bool
    private var stored: [ManualClubInput]?
    private var attempts: [[ManualClubInput]] = []
    private var commits: [[ManualClubInput]] = []
    private var paths: [String] = []
    private var fetches = 0

    init(online: Bool, stored: [ManualClubInput]?) {
        self.online = online
        self.stored = stored
    }

    func setOnline(_ value: Bool) {
        lock.withLock { online = value }
    }

    var putAttempts: [[ManualClubInput]] { lock.withLock { attempts } }
    var committed: [[ManualClubInput]] { lock.withLock { commits } }
    var requestPaths: [String] { lock.withLock { paths } }
    var fetchCount: Int { lock.withLock { fetches } }

    func handle(_ request: URLRequest) throws -> (HTTPURLResponse, Data) {
        let url = try XCTUnwrap(request.url)
        guard url.path.hasPrefix("/api/v2/players/"), url.path.hasSuffix("/clubs/bag") else {
            throw URLError(.unsupportedURL)
        }
        if request.httpMethod == "PUT" {
            let body = try JSONDecoder().decode(
                ClubBagGoalPutBody.self,
                from: CapturingURLProtocol.requestBodyData(from: request)
            )
            let accepted: Bool = lock.withLock {
                attempts.append(body.clubs)
                paths.append(url.path)
                guard online else { return false }
                stored = body.clubs
                commits.append(body.clubs)
                return true
            }
            guard accepted else { throw URLError(.notConnectedToInternet) }
            return try reply(url, clubs: body.clubs)
        }
        let (isOnline, current): (Bool, [ManualClubInput]?) = lock.withLock {
            fetches += 1
            paths.append(url.path)
            return (online, stored)
        }
        guard isOnline else { throw URLError(.notConnectedToInternet) }
        return try reply(url, clubs: current)
    }

    private func reply(_ url: URL, clubs: [ManualClubInput]?) throws -> (HTTPURLResponse, Data) {
        let effective = EffectiveClubBagResponse(
            schema: nil,
            source: clubs == nil ? "none" : "manual",
            found: clubs != nil,
            clubs: (clubs ?? []).map { club in
                EffectiveClubBagClub(
                    token: club.token,
                    zhName: nil,
                    customName: club.customName,
                    clubTypeId: nil,
                    distanceM: club.distanceM,
                    distanceSource: club.distanceM == nil ? "default" : "manual"
                )
            }
        )
        let response = try XCTUnwrap(HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil))
        return (response, try JSONEncoder().encode(effective))
    }
}

/// Replaces the coordinator's pauses: the debounce returns at once; each retry backoff runs the
/// test's hook (where the network comes back) and either returns at once or is held until released.
@MainActor
private final class ClubBagGoalNaps {
    private(set) var retryNaps: [UInt64] = []
    var onRetry: (@MainActor (Int) async -> Void)?
    var holdRetries = false
    var onHold: XCTestExpectation?
    private var held: [CheckedContinuation<Void, Never>] = []

    func nap(_ nanoseconds: UInt64) async {
        guard nanoseconds != ClubBagSyncCoordinator.debounceNanoseconds else { return }
        retryNaps.append(nanoseconds)
        if let onRetry {
            await onRetry(retryNaps.count)
        }
        guard holdRetries else { return }
        await withCheckedContinuation { continuation in
            held.append(continuation)
            onHold?.fulfill()
            onHold = nil
        }
    }

    func releaseHeld() {
        let waiting = held
        held = []
        waiting.forEach { $0.resume() }
    }
}

final class ClubBagGoalTests: XCTestCase {
    override func setUpWithError() throws {
        try super.setUpWithError()
        UserDefaults().removePersistentDomain(forName: clubBagGoalSuite)
        UserDefaults().removePersistentDomain(forName: clubBagGoalReinstallSuite)
        ClubBagStore.defaults = try XCTUnwrap(UserDefaults(suiteName: clubBagGoalSuite))
        ClubBagStore.bind(playerId: nil, migrateLegacy: false)
    }

    override func tearDown() {
        ClubBagStore.bind(playerId: nil, migrateLegacy: false)
        ClubBagStore.defaults = .standard
        UserDefaults().removePersistentDomain(forName: clubBagGoalSuite)
        UserDefaults().removePersistentDomain(forName: clubBagGoalReinstallSuite)
        super.tearDown()
    }

    /// One app launch: a coordinator bound to the player and wired to a real SyncClient whose
    /// only fake is the URLProtocol edge.
    @MainActor
    private func makeCoordinator(
        server: ClubBagGoalServer,
        naps: ClubBagGoalNaps
    ) throws -> (ClubBagSyncCoordinator, URLSession, CapturingURLProtocolScope) {
        let scope = CapturingURLProtocolScope(handler: { try server.handle($0) })
        let session = URLSession(configuration: scope.configuration())
        let client = SyncClient(
            baseURL: try XCTUnwrap(URL(string: "https://example.test")),
            session: session,
            retrySleep: { _ in }
        )
        let coordinator = ClubBagSyncCoordinator(sleep: { await naps.nap($0) })
        coordinator.activate(playerId: clubBagGoalPlayer, migrateLegacy: false)
        coordinator.configure(
            sender: { playerId, clubs in
                _ = try await client.putManualClubBag(playerId: playerId, clubs: clubs)
            },
            fetcher: { playerId in
                try await client.fetchEffectiveClubBag(playerId: playerId)
            }
        )
        return (coordinator, session, scope)
    }

    // goals: I-13 [main]
    @MainActor
    func testOfflineBagEditIsQueuedAndSentOnReconnect() async throws {
        let server = ClubBagGoalServer(online: true, stored: clubBagGoalCloud)
        let naps = ClubBagGoalNaps()
        let (coordinator, session, scope) = try makeCoordinator(server: server, naps: naps)
        defer {
            naps.onRetry = nil
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        let restored = await coordinator.restoreFromServer()
        XCTAssertTrue(restored)
        XCTAssertTrue(coordinator.canEdit)

        // The phone loses the network; the player keeps editing the bag.
        server.setOnline(false)
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        var statuses: [ClubBagSyncCoordinator.Status] = []
        var queued: [[ManualClubInput]?] = []
        naps.onRetry = { retry in
            statuses.append(coordinator.status)
            queued.append(coordinator.pendingClubs)
            if retry == 1 {
                // Still offline: a further edit while the queue waits is accepted locally.
                XCTAssertTrue(model.canEdit, "an offline phone that matched the cloud stays editable")
                model.setDistance("七号铁", 165)
            } else {
                server.setOnline(true)
            }
        }
        model.setDistance("七号铁", 160)
        model.add("八号铁")
        // Every edit lands on the device first, before any network round trip.
        XCTAssertEqual(ClubBagStore.manualDistancesYd()["七号铁"], 160)
        XCTAssertEqual(ClubBagStore.bag(), Set(["七号铁", "一号木", "八号铁"]))
        XCTAssertNotNil(coordinator.pendingClubs, "the edit is queued for sync")

        await coordinator.flush()

        let first = [
            ManualClubInput(token: "driver"),
            ManualClubInput(token: "iron7", distanceM: 146),
            ManualClubInput(token: "iron8"),
        ]
        let latest = [
            ManualClubInput(token: "driver"),
            ManualClubInput(token: "iron7", distanceM: 151),
            ManualClubInput(token: "iron8"),
        ]
        XCTAssertEqual(statuses, [.failed, .failed], "the queue shows the failed offline sends")
        XCTAssertEqual(queued, [first, latest], "the queued edit is kept across offline failures")
        XCTAssertEqual(server.putAttempts, [first, latest, latest])
        XCTAssertEqual(server.committed, [latest], "after reconnect the server holds exactly the last edit")
        XCTAssertEqual(coordinator.failedAttempts, 2)
        XCTAssertNil(coordinator.pendingClubs, "the queue is empty once the server has the edit")
        XCTAssertEqual(coordinator.status, .idle)
        XCTAssertEqual(ClubBagStore.manualDistancesYd()["七号铁"], 165)
        XCTAssertTrue(server.requestPaths.allSatisfy { $0 == "/api/v2/players/\(clubBagGoalPlayer)/clubs/bag" })
    }

    // goals: I-13
    @MainActor
    func testQueuedOfflineEditSurvivesRelaunchAndIsSentOnce() async throws {
        let server = ClubBagGoalServer(online: true, stored: clubBagGoalCloud)
        let heldNaps = ClubBagGoalNaps()
        heldNaps.holdRetries = true
        let firstBackoff = expectation(description: "the offline send backs off")
        heldNaps.onHold = firstBackoff
        let (killed, killedSession, killedScope) = try makeCoordinator(server: server, naps: heldNaps)
        defer {
            heldNaps.releaseHeld()
            killedSession.invalidateAndCancel()
            withExtendedLifetime(killedScope) {}
        }
        let restored = await killed.restoreFromServer()
        XCTAssertTrue(restored)

        server.setOnline(false)
        let model = ClubBagEditorModel(clubProfiles: [], sync: killed)
        model.add("八号铁")
        model.setDistance("七号铁", 165)
        await fulfillment(of: [firstBackoff], timeout: 10)
        let latest = [
            ManualClubInput(token: "driver"),
            ManualClubInput(token: "iron7", distanceM: 151),
            ManualClubInput(token: "iron8"),
        ]
        XCTAssertEqual(killed.status, .failed)
        XCTAssertEqual(killed.pendingClubs, latest, "only the latest whole bag is queued")
        XCTAssertEqual(server.committed, [])

        // Relaunch with the network back: the new launch resumes the durable queue by itself.
        server.setOnline(true)
        let relaunchNaps = ClubBagGoalNaps()
        let (relaunched, session, scope) = try makeCoordinator(server: server, naps: relaunchNaps)
        defer {
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        await relaunched.flush()
        XCTAssertEqual(server.committed, [latest])
        XCTAssertNil(relaunched.pendingClubs)
        XCTAssertEqual(relaunched.status, .idle)
        XCTAssertTrue(relaunched.canEdit)

        // The killed launch's worker wakes up afterwards and finds nothing left to send.
        heldNaps.releaseHeld()
        await killed.flush()
        XCTAssertEqual(server.committed, [latest], "no duplicate PUT")
        XCTAssertEqual(server.putAttempts.count, 2)
    }

    // goals: I-13
    @MainActor
    func testReinstallRestoresBagAndDistancesFromServer() async throws {
        let server = ClubBagGoalServer(online: true, stored: nil)
        let naps = ClubBagGoalNaps()
        let (phone, session, scope) = try makeCoordinator(server: server, naps: naps)
        defer {
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        let firstRestore = await phone.restoreFromServer()
        XCTAssertTrue(firstRestore)
        let model = ClubBagEditorModel(clubProfiles: [], sync: phone)
        model.add("七号铁")
        model.setDistance("七号铁", 160)
        model.add("八号铁")
        await phone.flush()
        let saved = [ManualClubInput(token: "iron7", distanceM: 146), ManualClubInput(token: "iron8")]
        XCTAssertEqual(server.committed, [saved])

        // Reinstall: a fresh process with empty local storage signs in as the same player.
        ClubBagStore.bind(playerId: nil, migrateLegacy: false)
        ClubBagStore.defaults = try XCTUnwrap(UserDefaults(suiteName: clubBagGoalReinstallSuite))
        let reinstallNaps = ClubBagGoalNaps()
        let (reinstalled, reinstalledSession, reinstalledScope) = try makeCoordinator(server: server, naps: reinstallNaps)
        defer {
            reinstalledSession.invalidateAndCancel()
            withExtendedLifetime(reinstalledScope) {}
        }
        XCTAssertNil(ClubBagStore.bag())
        XCTAssertFalse(reinstalled.canEdit, "no whole-bag edit before the cloud bag is restored")
        let early = ClubBagEditorModel(clubProfiles: [], sync: reinstalled)
        early.add("九号铁")
        XCTAssertNil(reinstalled.pendingClubs, "an edit on the empty reinstalled bag is not queued over the cloud bag")

        let restored = await reinstalled.restoreFromServer()
        XCTAssertTrue(restored)
        XCTAssertEqual(reinstalled.restoreState, .restored)
        XCTAssertTrue(reinstalled.canEdit)
        XCTAssertEqual(ClubBagStore.bag(), Set(["七号铁", "八号铁"]))
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), ["七号铁": 160], "the typed carry comes back in yards")
        XCTAssertEqual(server.requestPaths.last, "/api/v2/players/\(clubBagGoalPlayer)/clubs/bag")

        // The next edit builds on the restored bag instead of overwriting it.
        let restoredModel = ClubBagEditorModel(clubProfiles: [], sync: reinstalled)
        XCTAssertEqual(restoredModel.row(named: "七号铁")?.median, 160)
        restoredModel.setDistance("八号铁", 150)
        await reinstalled.flush()
        XCTAssertEqual(server.committed.last, [
            ManualClubInput(token: "iron7", distanceM: 146),
            ManualClubInput(token: "iron8", distanceM: 137),
        ])
    }

    // goals: I-13
    @MainActor
    func testRestoreNeverOverwritesAnEditQueuedOffline() async throws {
        let server = ClubBagGoalServer(online: true, stored: clubBagGoalCloud)
        let naps = ClubBagGoalNaps()
        let (coordinator, session, scope) = try makeCoordinator(server: server, naps: naps)
        defer {
            naps.onRetry = nil
            session.invalidateAndCancel()
            withExtendedLifetime(scope) {}
        }
        let restored = await coordinator.restoreFromServer()
        XCTAssertTrue(restored)
        XCTAssertEqual(server.fetchCount, 1)

        server.setOnline(false)
        var restoreWhileQueued: [Bool] = []
        var distanceAfterRestore: [Int?] = []
        naps.onRetry = { _ in
            // A foreground restore while the offline edit is still queued must not replace it.
            let result = await coordinator.restoreFromServer()
            restoreWhileQueued.append(result)
            distanceAfterRestore.append(ClubBagStore.manualDistancesYd()["七号铁"])
            server.setOnline(true)
        }
        let model = ClubBagEditorModel(clubProfiles: [], sync: coordinator)
        model.setDistance("七号铁", 165)
        await coordinator.flush()

        XCTAssertEqual(restoreWhileQueued, [false])
        XCTAssertEqual(distanceAfterRestore, [165])
        XCTAssertEqual(server.fetchCount, 1, "the queued edit is newer than the cloud copy; it is not fetched over")
        let edited = [ManualClubInput(token: "driver"), ManualClubInput(token: "iron7", distanceM: 151)]
        XCTAssertEqual(server.committed, [edited])

        // Once synced, a later restore reads back the same bag and keeps the typed yards.
        let again = await coordinator.restoreFromServer()
        XCTAssertTrue(again)
        XCTAssertEqual(ClubBagStore.manualDistancesYd(), ["七号铁": 165])
        XCTAssertEqual(ClubBagStore.bag(), Set(["七号铁", "一号木"]))
    }
}
