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
}
