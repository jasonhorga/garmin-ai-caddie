import Foundation
import XCTest
@testable import AICaddie

@MainActor
final class SessionStoreTests: XCTestCase {
    func testSaveThenReadRoundTrips() {
        let store = SessionStore(persisting: InMemorySessionPersisting())
        XCTAssertNil(store.currentSession)
        let session = AppSession(token: "t1", playerId: "p_1", expiresAt: nil)
        store.save(session)
        XCTAssertEqual(store.currentSession, session)
    }

    func testReadsPersistedSessionOnInit() {
        let persisting = InMemorySessionPersisting(AppSession(token: "t2", playerId: "me"))
        let store = SessionStore(persisting: persisting)
        XCTAssertEqual(store.currentSession?.playerId, "me")
        XCTAssertEqual(store.currentSession?.token, "t2")
    }

    func testClearRemovesSessionEverywhere() {
        let persisting = InMemorySessionPersisting(AppSession(token: "t3", playerId: "p_3"))
        let store = SessionStore(persisting: persisting)
        store.clear()
        XCTAssertNil(store.currentSession)
        XCTAssertNil(persisting.read())
    }

    func testIsExpiredReflectsExpiry() {
        XCTAssertFalse(AppSession(token: "t", playerId: "me", expiresAt: nil).isExpired)
        XCTAssertFalse(AppSession(token: "t", playerId: "me", expiresAt: Date().addingTimeInterval(3600)).isExpired)
        XCTAssertTrue(AppSession(token: "t", playerId: "me", expiresAt: Date().addingTimeInterval(-3600)).isExpired)
    }

    func testSessionCodableRoundTrips() throws {
        let session = AppSession(token: "abc", playerId: "p_9", expiresAt: Date(timeIntervalSince1970: 1_800_000_000))
        let data = try JSONEncoder().encode(session)
        let decoded = try JSONDecoder().decode(AppSession.self, from: data)
        XCTAssertEqual(decoded, session)
    }

    func testExpiredStoredSessionIsNotVendedOnLoad() {
        let expired = AppSession(token: "old", playerId: "me", expiresAt: Date().addingTimeInterval(-60))
        let persisting = InMemorySessionPersisting(expired)
        let store = SessionStore(persisting: persisting)
        XCTAssertNil(store.currentSession)          // never vend a stale session
        XCTAssertNil(store.liveToken)
        XCTAssertNil(persisting.read())             // and drop it from storage
    }

    func testLiveTokenTracksSaveAndSignOut() {
        let store = SessionStore(persisting: InMemorySessionPersisting())
        XCTAssertNil(store.liveToken)
        store.save(AppSession(token: "live", playerId: "me", expiresAt: Date().addingTimeInterval(3600)))
        XCTAssertEqual(store.liveToken, "live")
        store.signOut()
        XCTAssertNil(store.liveToken)
        XCTAssertNil(store.currentSession)
    }

    func testLiveTokenNilWhenExpiredAfterSave() {
        let store = SessionStore(persisting: InMemorySessionPersisting())
        store.save(AppSession(token: "soon", playerId: "me", expiresAt: Date().addingTimeInterval(-1)))
        XCTAssertNil(store.liveToken)  // an already-expired token never authenticates
    }

    func testReloadPreservesSessionWhenKeychainReadIsTemporarilyUnavailable() {
        let persisting = FlakySessionPersisting(AppSession(token: "live", playerId: "me"))
        let store = SessionStore(persisting: persisting)
        persisting.returnNilOnRead = true

        store.reload()

        XCTAssertEqual(store.currentSession?.token, "live")
        XCTAssertEqual(store.liveToken, "live")
        XCTAssertEqual(persisting.stored?.token, "live")
    }
}

private final class FlakySessionPersisting: SessionPersisting {
    var stored: AppSession?
    var returnNilOnRead = false

    init(_ stored: AppSession?) {
        self.stored = stored
    }

    func read() -> AppSession? {
        return returnNilOnRead ? nil : stored
    }

    func write(_ session: AppSession) {
        stored = session
    }

    func clear() {
        stored = nil
    }
}
