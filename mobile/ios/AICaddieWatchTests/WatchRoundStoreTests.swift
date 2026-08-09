import XCTest
@testable import AICaddieWatch

final class WatchRoundStoreTests: XCTestCase {
    private func tempStore() -> (WatchRoundStore, URL) {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        return (WatchRoundStore(directoryURL: dir), dir)
    }

    private func holeState(roundId: String = "r1", hole: Int, score: Int = 0) -> WatchRoundState {
        WatchRoundState(
            roundId: roundId, hole: hole, par: 4, distanceM: nil,
            selectedClub: nil, score: score, putts: 0, penaltyCount: 0, caddieConfidence: "low"
        )
    }

    private func event(_ eventId: String, roundId: String = "r1", hole: Int = 1, kind: WatchInputKind = .score, value: String = "4") -> WatchInputEvent {
        WatchInputEvent(eventId: eventId, roundId: roundId, hole: hole, kind: kind, value: value, createdAt: "2026-06-20T00:00:00Z")
    }

    func testRecordAppliesToHoleStateAndQueuesEvent() throws {
        let (store, _) = tempStore()
        try store.upsertHoleState(holeState(hole: 1, score: 0))
        let round = try store.record(event("e1", hole: 1, kind: .score, value: "4"))

        XCTAssertEqual(store.holeState(hole: 1)?.score, 4)        // applied to the snapshot
        XCTAssertEqual(round.pendingEvents.map(\.eventId), ["e1"]) // queued for upload
        XCTAssertEqual(round.activeHole, 1)
    }

    func testMarkPostedRemovesConfirmedEventsFromQueue() throws {
        let (store, _) = tempStore()
        try store.upsertHoleState(holeState(hole: 1))
        try store.record(event("e1", kind: .score, value: "4"))
        try store.record(event("e2", kind: .putt, value: "2"))

        let round = try XCTUnwrap(try store.markPosted(eventIds: ["e1"]))
        XCTAssertEqual(round.pendingEvents.map(\.eventId), ["e2"])
    }

    func testPersistsAcrossStoreInstances() throws {
        let (store, dir) = tempStore()
        try store.upsertHoleState(holeState(hole: 3, score: 5))
        try store.record(event("e1", hole: 3, kind: .putt, value: "2"))

        let reopened = WatchRoundStore(directoryURL: dir)
        let loaded = try XCTUnwrap(reopened.load())
        XCTAssertEqual(loaded.roundId, "r1")
        XCTAssertEqual(loaded.activeHole, 3)
        XCTAssertEqual(reopened.holeState(hole: 3)?.putts, 2)
        XCTAssertEqual(loaded.pendingEvents.map(\.eventId), ["e1"])
    }

    func testLoadsRoundWrittenBeforeInteractionStateFieldsExisted() throws {
        let (store, directory) = tempStore()
        let legacy = Data(
            """
            {
              "roundId": "legacy-round",
              "activeHole": 1,
              "holeStates": [],
              "pendingEvents": [],
              "courseName": "Legacy Course"
            }
            """.utf8
        )
        try legacy.write(to: directory.appendingPathComponent("round.json"))

        let loaded = try XCTUnwrap(store.load())

        XCTAssertEqual(loaded.roundId, "legacy-round")
        XCTAssertNil(loaded.pendingManualShot)
        XCTAssertNil(loaded.pendingAutoShotCandidate)
        XCTAssertNil(loaded.scoreDraft)
    }

    func testNewRoundReplacesPreviousPersistedRound() throws {
        let (store, _) = tempStore()
        try store.upsertHoleState(holeState(roundId: "r1", hole: 1))
        try store.record(event("e1", roundId: "r1", hole: 1))

        let round = try store.record(event("e2", roundId: "r2", hole: 1))
        XCTAssertEqual(round.roundId, "r2")
        XCTAssertEqual(round.pendingEvents.map(\.eventId), ["e2"])  // r1's queue dropped with the round
        XCTAssertTrue(round.holeStates.allSatisfy { $0.roundId == "r2" })
    }

    func testUpsertHoleStateSetsActiveHoleAndSorts() throws {
        let (store, _) = tempStore()
        try store.upsertHoleState(holeState(hole: 5))
        try store.upsertHoleState(holeState(hole: 2))
        let round = try XCTUnwrap(store.load())
        XCTAssertEqual(round.activeHole, 2)                       // last upsert is active
        XCTAssertEqual(round.holeStates.map(\.hole), [2, 5])      // kept sorted by hole
    }

    func testPhoneStateCanRefreshAHoleWithoutMovingTheWatchCursor() throws {
        let (store, _) = tempStore()
        try store.upsertHoleState(holeState(hole: 1))
        try store.upsertHoleState(holeState(hole: 2))

        let round = try store.upsertHoleState(holeState(hole: 1, score: 4), makeActive: false)

        XCTAssertEqual(round.activeHole, 2)
        XCTAssertEqual(round.holeStates.first { $0.hole == 1 }?.score, 4)
    }

    func testClosedRoundCannotBeResurrectedByItsStaleRoundFile() throws {
        let (store, directory) = tempStore()
        try store.upsertHoleState(holeState(hole: 1))

        let closure = try store.closeActiveRound(
            roundId: "r1",
            disposition: .abandoned,
            closedAt: "2026-08-09T00:00:00Z"
        )

        XCTAssertNil(store.load())
        XCTAssertEqual(store.closure(roundId: "r1"), closure)
        let relaunched = WatchRoundStore(directoryURL: directory)
        XCTAssertTrue(relaunched.isClosed(roundId: "r1"))
        XCTAssertNil(relaunched.load())
    }

    func testDeferredFinishRetainsUnresolvedEventsButLeavesNoActiveRound() throws {
        let (store, directory) = tempStore()
        try store.upsertHoleState(holeState(hole: 1))
        try store.record(event("e1"))
        let active = try XCTUnwrap(store.load())

        let closure = try store.deferFinish(active, savedAt: "2026-08-09T00:00:00Z")

        XCTAssertEqual(closure.disposition, .savedLocally)
        XCTAssertNil(store.load())
        XCTAssertEqual(store.loadDeferredFinishes().first?.round.pendingEvents.map(\.eventId), ["e1"])

        let relaunched = WatchRoundStore(directoryURL: directory)
        XCTAssertNil(relaunched.load())
        XCTAssertEqual(relaunched.loadDeferredFinishes().first?.round.roundId, "r1")
    }
}
