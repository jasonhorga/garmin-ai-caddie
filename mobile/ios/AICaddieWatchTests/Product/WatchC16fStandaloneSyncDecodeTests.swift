import XCTest
@testable import AICaddieWatch

/// C16f 6.1/6.2/8.3: independent Watch persistence, phone refresh ordering and old payload decode.
@MainActor
final class WatchC16fStandaloneSyncDecodeTests: XCTestCase {
    private func directory() -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("c16f-\(UUID().uuidString)", isDirectory: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    func test_6_1_watch_standalone_round_scores_offline_and_restores_after_relaunch() throws {
        let store = WatchRoundStore(directoryURL: directory())
        let model = WatchRoundModel(store: store, autoShotEnabled: false, makeEventId: { "offline-round" })
        model.startPracticeRound(holeCount: 9, par: 4, courseName: "离线九洞")
        model.resumeRound()
        model.startScoringActiveHole()
        model.startManualScoreEntry()
        model.setDraftScore(5)
        model.setDraftPutts(2)
        model.setDraftPenalty(0)
        model.saveManualScore()

        let relaunched = WatchRoundModel(store: store, autoShotEnabled: false)
        XCTAssertEqual(relaunched.round?.holeStates.first?.score, 5)
        XCTAssertEqual(relaunched.round?.holeStates.first?.putts, 2)
        XCTAssertEqual(relaunched.round?.holeStates.first?.penaltyCount, 0)
        XCTAssertEqual(relaunched.round?.pendingEvents.filter { $0.kind == .score }.count, 1)
        XCTAssertEqual(relaunched.courseName, "离线九洞")
    }

    func test_6_1_watch_standalone_round_keeps_each_ordered_loop_identity_across_restart() {
        let loopKeys = [
            "81001:front", "81001:back", "81001:front+81001:back", "81001:back+81001:front",
        ]
        for key in loopKeys {
            let rows = try! XCTUnwrap(WatchCourseSelection.roundRows(loopKey: key))
            let states = rows.map { row in
                WatchRoundState(
                    roundId: "loop-\(key)", hole: row.number, par: 4, distanceM: nil,
                    selectedClub: nil, globalId: row.globalId,
                    sourceLocalHole: row.sourceLocalHole, courseHoleNumber: row.courseHoleNumber,
                    score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
                )
            }
            let store = WatchRoundStore(directoryURL: directory())
            let model = WatchRoundModel(store: store)
            model.seedRound(states, activeHole: 1, courseName: "loop", loopKey: key)
            let relaunched = WatchRoundModel(store: store)
            XCTAssertEqual(relaunched.round?.loopKey, key)
            XCTAssertEqual(relaunched.round?.holeStates.map(\.sourceLocalHole), rows.map(\.sourceLocalHole))
        }
    }

    func test_6_2_watch_phone_facts_refresh_and_stale_snapshot_is_ignored_when_disconnected() {
        let store = WatchRoundStore(directoryURL: directory())
        let model = WatchRoundModel(store: store)
        let base = WatchRoundState(
            roundId: "sync-round", hole: 1, par: 4, distanceM: 200,
            selectedClub: nil, score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        model.seedRound([base], activeHole: 1, courseName: "同步")
        let fresh = WatchRoundState(
            roundId: "sync-round", hole: 1, par: 4, distanceM: 150,
            selectedClub: nil,
            centerGreenM: 140, score: 0, putts: 0, penaltyCount: 0,
            caddieConfidence: "high", snapshotRevision: 2
        )
        model.receivePhoneState(fresh)
        XCTAssertEqual(model.activeHoleState?.distanceM, 150)
        XCTAssertEqual(model.activeHoleState?.centerGreenM, 140)

        let stale = WatchRoundState(
            roundId: "sync-round", hole: 1, par: 4, distanceM: 999,
            selectedClub: nil,
            centerGreenM: 999, score: 0, putts: 0, penaltyCount: 0,
            caddieConfidence: "offline", snapshotRevision: 1
        )
        model.receivePhoneState(stale)
        XCTAssertEqual(model.activeHoleState?.distanceM, 150)
        XCTAssertEqual(model.activeHoleState?.centerGreenM, 140)
    }

    func test_8_3_watch_old_state_payload_ignores_unknown_fields_and_fills_optional_facts() throws {
        let data = #"{"schema":"ai-caddie-watch-round-state-v1","roundId":"legacy","hole":7,"par":4,"distanceM":142,"score":4,"putts":2,"penaltyCount":0,"caddieConfidence":"medium","futureField":{"x":1}}"#.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(WatchRoundState.self, from: data)
        XCTAssertEqual(decoded.roundId, "legacy")
        XCTAssertEqual(decoded.hole, 7)
        XCTAssertEqual(decoded.score, 4)
        XCTAssertNil(decoded.centerGreenM)
        XCTAssertEqual(decoded.availableClubs, [])
        XCTAssertEqual(decoded.caddieOptions, [])
    }

    func test_8_3_watch_old_caddie_cache_without_dispersion_or_origin_still_decodes() throws {
        let data = #"{"optionId":"stock","label":"推荐","clubName":"6I","carryM":150,"confidence":"offline","futureVersion":4}"#.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(WatchCaddieOption.self, from: data)
        XCTAssertEqual(decoded.optionId, "stock")
        XCTAssertEqual(decoded.clubName, "6I")
        XCTAssertEqual(decoded.carryM, 150)
        XCTAssertNil(decoded.carryP10M)
        XCTAssertNil(decoded.originShotEventIds)
    }
}
