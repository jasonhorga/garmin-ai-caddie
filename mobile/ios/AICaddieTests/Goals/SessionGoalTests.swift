// size: medium
// goals: I-01
//
// I-01: the player signs in with Apple, the session is kept in the keychain-backed SessionStore and
// is still there after the app restarts; signing out clears it everywhere (live token, published
// session, keychain) so the next launch asks for Apple sign-in again.

import Foundation
import XCTest
@testable import AICaddie

/// Fake keychain edge: stores the session as opaque bytes, outliving any one SessionStore instance,
/// the same way the real keychain outlives an app process.
private final class GoalFakeKeychain: SessionPersisting {
    private(set) var storedBytes: Data?
    private(set) var clearCount = 0

    init(_ initial: AppSession? = nil) {
        storedBytes = initial.flatMap { try? JSONEncoder().encode($0) }
    }

    func read() -> AppSession? {
        storedBytes.flatMap { try? JSONDecoder().decode(AppSession.self, from: $0) }
    }

    func write(_ session: AppSession) {
        storedBytes = try? JSONEncoder().encode(session)
    }

    func clear() {
        clearCount += 1
        storedBytes = nil
    }
}

private func goalJSONResponse(
    _ request: URLRequest,
    status: Int,
    body: String
) throws -> (HTTPURLResponse, Data) {
    let response = try XCTUnwrap(HTTPURLResponse(
        url: try XCTUnwrap(request.url),
        statusCode: status,
        httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
    ))
    return (response, Data(body.utf8))
}

/// Mirrors what the sign-in screen does with the backend answer.
private func goalAppSession(from response: AppleSignInResponse) -> AppSession {
    AppSession(
        token: response.token,
        playerId: response.playerId ?? "me",
        expiresAt: response.expiresAt.flatMap { ISO8601DateFormatter().date(from: $0) }
    )
}

private func goalFutureExpiry() -> String {
    ISO8601DateFormatter().string(from: Date().addingTimeInterval(30 * 24 * 3600))
}

@MainActor
final class SessionGoalTests: XCTestCase {
    private var temporaryDirectories: [URL] = []
    private var models: [LiveRoundAppModel] = []
    private var bagIsolation: GoalClubBagIsolation?

    override func setUp() async throws {
        try await super.setUp()
        bagIsolation = try GoalClubBagIsolation()
    }

    override func tearDown() async throws {
        for model in models {
            await model.stopRoundBackgroundWorkForTesting()
        }
        models.removeAll()
        await bagIsolation?.restore()
        bagIsolation = nil
        for directory in temporaryDirectories {
            try? FileManager.default.removeItem(at: directory)
        }
        temporaryDirectories.removeAll()
        try await super.tearDown()
    }

    private func makeTemporaryDirectory() -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("session-goal-\(UUID().uuidString)", isDirectory: true)
        temporaryDirectories.append(directory)
        return directory
    }

    private func makeModel(store: OfflineStore) -> LiveRoundAppModel {
        ensureC156TopoBundleStub()
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: URL(string: "https://session-goal.example.test"),
            adminToken: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: nil,
            networkPathObserver: nil
        )
        models.append(model)
        return model
    }

    private func appleClient(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) throws -> (AppleAuthClient, CapturingURLProtocolScope) {
        let scope = CapturingURLProtocolScope(handler: handler)
        let client = AppleAuthClient(
            baseURL: try XCTUnwrap(URL(string: "https://session-goal.example.test")),
            session: URLSession(configuration: scope.configuration())
        )
        return (client, scope)
    }

    // goals: I-01 [main]
    func testSignInPersistSignOut() async throws {
        let expiry = goalFutureExpiry()
        let bodiesLock = NSLock()
        var signInBodies: [Data] = []
        let (client, scope) = try appleClient { request in
            XCTAssertEqual(request.url?.path, "/api/v2/auth/apple")
            XCTAssertEqual(request.httpMethod, "POST")
            let body = try CapturingURLProtocol.requestBodyData(from: request)
            bodiesLock.lock()
            signInBodies.append(body)
            bodiesLock.unlock()
            return try goalJSONResponse(
                request,
                status: 200,
                body: #"{"token":"sess-goal-1","playerId":"p_goal","userId":"u_goal","expiresAt":"\#(expiry)"}"#
            )
        }
        defer { withExtendedLifetime(scope) {} }

        let keychain = GoalFakeKeychain()
        let store = SessionStore(persisting: keychain)
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: store.currentSession))

        let response = try await client.signIn(identityToken: "apple.identity.jwt", displayName: "Goal Player")
        let session = goalAppSession(from: response)
        store.save(session)
        let model = makeModel(store: OfflineStore(directoryURL: makeTemporaryDirectory()))
        model.activateSession(session, migrateLegacyData: false)

        bodiesLock.lock()
        let capturedBodies = signInBodies
        bodiesLock.unlock()
        XCTAssertEqual(capturedBodies.count, 1)
        let sentBody = try XCTUnwrap(
            JSONSerialization.jsonObject(with: try XCTUnwrap(capturedBodies.first)) as? [String: Any]
        )
        XCTAssertEqual(sentBody["identityToken"] as? String, "apple.identity.jwt")
        XCTAssertEqual(store.currentSession, session)
        XCTAssertEqual(store.liveToken, "sess-goal-1")
        XCTAssertEqual(keychain.read(), session, "the session must be written to the keychain")
        XCTAssertNil(model.liveRoundState, "a fresh account has no round to resume")

        // Restart: a brand-new SessionStore over the same keychain, then the app's launch reload.
        let relaunched = SessionStore(persisting: keychain)
        relaunched.reload()
        XCTAssertEqual(relaunched.currentSession, session, "the session survives a restart")
        XCTAssertEqual(relaunched.liveToken, "sess-goal-1")
        XCTAssertFalse(AICaddieApp.requiresAppleSignIn(environment: [:], session: relaunched.currentSession))

        relaunched.signOut()
        XCTAssertNil(relaunched.currentSession)
        XCTAssertNil(relaunched.liveToken)
        XCTAssertNil(keychain.read(), "sign-out must clear the keychain")
        XCTAssertNil(keychain.storedBytes)

        // Next launch after sign-out: nothing to restore, Apple sign-in is required again.
        let afterSignOut = SessionStore(persisting: keychain)
        afterSignOut.reload()
        XCTAssertNil(afterSignOut.currentSession)
        XCTAssertNil(afterSignOut.liveToken)
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: afterSignOut.currentSession))
    }

    // goals: I-01
    func testServerRejectedAppleTokenLeavesPlayerSignedOut() async throws {
        let (client, scope) = try appleClient { request in
            try goalJSONResponse(request, status: 401, body: #"{"detail":"invalid apple identity token"}"#)
        }
        defer { withExtendedLifetime(scope) {} }
        let keychain = GoalFakeKeychain()
        let store = SessionStore(persisting: keychain)

        do {
            let response = try await client.signIn(identityToken: "forged.jwt", displayName: nil)
            XCTFail("a rejected Apple token must not produce a session: \(response)")
            store.save(goalAppSession(from: response))
        } catch let SyncClientError.http(status, _) {
            XCTAssertEqual(status, 401)
        } catch {
            XCTFail("unexpected error \(error)")
        }

        XCTAssertNil(store.currentSession)
        XCTAssertNil(store.liveToken)
        XCTAssertNil(keychain.read())
        let relaunched = SessionStore(persisting: keychain)
        relaunched.reload()
        XCTAssertNil(relaunched.currentSession)
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: relaunched.currentSession))
    }

    // goals: I-01
    func testReloadWithoutStoredSessionRequiresSignIn() {
        let emptyKeychain = GoalFakeKeychain()
        let store = SessionStore(persisting: emptyKeychain)
        store.reload()
        XCTAssertNil(store.currentSession)
        XCTAssertNil(store.liveToken)
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: store.currentSession))
        XCTAssertEqual(emptyKeychain.clearCount, 0, "an empty keychain has nothing to clear")
    }

    // goals: I-01
    func testExpiredOrMalformedStoredSessionIsNotRestoredOnRestart() {
        let expired = AppSession(token: "sess-old", playerId: "p_goal", expiresAt: Date(timeIntervalSince1970: 1_000))
        let expiredKeychain = GoalFakeKeychain(expired)
        let afterExpiry = SessionStore(persisting: expiredKeychain)
        afterExpiry.reload()
        XCTAssertNil(afterExpiry.currentSession)
        XCTAssertNil(afterExpiry.liveToken)
        XCTAssertNil(expiredKeychain.read(), "a stale keychain row is cleared, not vended")
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: afterExpiry.currentSession))

        let malformedKeychain = GoalFakeKeychain(AppSession(token: "  ", playerId: "p_goal"))
        let malformed = SessionStore(persisting: malformedKeychain)
        XCTAssertNil(malformed.currentSession)
        XCTAssertNil(malformed.liveToken)
        XCTAssertNil(malformedKeychain.read())
    }

    // goals: I-01
    func testSignOutAfterActiveRoundClearsSessionAndNextPlayerStartsClean() async throws {
        let root = makeTemporaryDirectory()
        let first = AppSession(token: "sess-first", playerId: "p_first", expiresAt: nil)
        let keychain = GoalFakeKeychain()
        let store = SessionStore(persisting: keychain)
        store.save(first)

        // The first player has a round with a recorded hole in their account scope.
        let offline = OfflineStore(directoryURL: root)
        let model = makeModel(store: offline)
        model.activateSession(first, migrateLegacyData: false)
        let round = try LiveRoundPackageFixture.nineHoleLoop(dataMode: "local")
        try offline.saveRoundPackage(round)
        try offline.appendEvent(LiveRoundEvent(
            eventId: "session-goal-score-1",
            roundId: round.roundId,
            timestamp: "2026-09-29T08:00:00Z",
            hole: 1,
            kind: .score,
            payload: ["strokes": .number(4)]
        ))
        await model.bootstrap()
        XCTAssertEqual(model.liveRoundState?.roundId, round.roundId)

        store.clear()
        XCTAssertNil(store.currentSession)
        XCTAssertNil(store.liveToken)
        XCTAssertNil(keychain.read())
        let relaunched = SessionStore(persisting: keychain)
        relaunched.reload()
        XCTAssertNil(relaunched.currentSession, "a signed-out player is not signed back in on restart")
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: relaunched.currentSession))

        // Another player signs in on the same phone: none of the first player's round leaks in.
        let second = AppSession(token: "sess-second", playerId: "p_second", expiresAt: nil)
        relaunched.save(second)
        model.activateSession(second, migrateLegacyData: true)
        XCTAssertNil(model.liveRoundState)
        XCTAssertNil(model.package)
        XCTAssertEqual(model.pendingEventCount, 0)
        XCTAssertNil(try offline.inProgressRoundId())
        XCTAssertEqual(relaunched.liveToken, "sess-second")
        XCTAssertEqual(keychain.read(), second)
    }
}
