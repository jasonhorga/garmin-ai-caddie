import CoreLocation
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
        let storeDirectory = directory()
        let store = WatchRoundStore(directoryURL: storeDirectory)
        var nextID = 0
        let model = WatchRoundModel(store: store, autoShotEnabled: false, makeEventId: {
            nextID += 1
            return "offline-\(nextID)"
        })
        model.startPracticeRound(holeCount: 9, par: 4, courseName: "离线九洞")
        model.resumeRound()
        model.startScoringActiveHole()
        model.startManualScoreEntry()
        model.setDraftScore(5)
        model.setDraftPutts(2)
        model.setDraftPenalty(1)
        model.saveManualScore()

        // Hand golden: 5 total = 2 full shots + 2 putts + 1 penalty; three changed fields
        // enqueue three distinct events. Reopen through a fresh store as well as a fresh model.
        let relaunched = WatchRoundModel(store: WatchRoundStore(directoryURL: storeDirectory), autoShotEnabled: false)
        XCTAssertEqual(relaunched.round?.holeStates.first?.score, 5)
        XCTAssertEqual(relaunched.round?.holeStates.first?.putts, 2)
        XCTAssertEqual(relaunched.round?.holeStates.first?.penaltyCount, 1)
        XCTAssertEqual(relaunched.round?.pendingEvents.filter { $0.kind == .score }.count, 1)
        XCTAssertEqual(relaunched.round?.pendingEvents.map(\.kind), [.score, .putt, .penalty])
        XCTAssertEqual(relaunched.round?.pendingEvents.map(\.value), ["5", "2", "1"])
        XCTAssertEqual(Set(relaunched.round?.pendingEvents.map(\.eventId) ?? []).count, 3)
        XCTAssertEqual(relaunched.courseName, "离线九洞")
    }

    func test_6_1_watch_standalone_round_keeps_each_ordered_loop_identity_across_restart() throws {
        // Hand golden: each nine contributes physical 1...9 or 10...18; a repeated
        // half restarts physical numbering while round slots continue 1...18.
        let rows: [(String, [Int], Int)] = [
            ("81001:front", Array(1...9), 5),
            ("81001:back", Array(10...18), 6),
            ("81001:front+81001:front", Array(1...9) + Array(1...9), 7),
            ("81001:front+81001:back", Array(1...9) + Array(10...18), 8),
            ("81001:back+81001:front", Array(10...18) + Array(1...9), 9),
            ("81001:back+81001:back", Array(10...18) + Array(10...18), 10),
        ]
        // Reuse one directory: replacing one ordered round must not resurrect its predecessor.
        let storeDirectory = directory()
        for (key, physical, score) in rows {
            let roundID = "loop-\(key)"
            let states = physical.enumerated().map { index, hole in
                WatchRoundState(
                    roundId: roundID, hole: index + 1, par: 4, distanceM: nil,
                    selectedClub: nil, globalId: 81001,
                    sourceLocalHole: hole, courseHoleNumber: hole,
                    score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
                )
            }
            let model = WatchRoundModel(store: WatchRoundStore(directoryURL: storeDirectory), autoShotEnabled: false)
            model.seedRound(states, activeHole: 1, courseName: "loop", loopKey: key)
            XCTAssertEqual(model.activeHoleState?.score, 0, key)
            model.startScoringActiveHole()
            model.setDraftScore(score)
            model.saveManualScore()
            let relaunched = WatchRoundModel(store: WatchRoundStore(directoryURL: storeDirectory), autoShotEnabled: false)
            XCTAssertEqual(relaunched.round?.roundId, roundID, key)
            XCTAssertEqual(relaunched.round?.loopKey, key, key)
            XCTAssertEqual(relaunched.round?.holeStates.map(\.sourceLocalHole), physical.map { Optional($0) }, key)
            XCTAssertEqual(relaunched.round?.holeStates.map(\.courseHoleNumber), physical.map { Optional($0) }, key)
            XCTAssertEqual(relaunched.round?.holeStates.first?.score, score, key)
            XCTAssertEqual(relaunched.round?.pendingEvents.count, 2, key) // total and default two putts
            XCTAssertEqual(relaunched.activeHole, 2, key)
        }
    }

    func test_6_2_watch_phone_facts_refresh_and_stale_snapshot_is_ignored() {
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

    func test_6_2_watch_disconnect_uses_wrist_ranges_expires_advice_and_reconnects_same_hole() throws {
        var clock = "2026-10-23T12:00:00Z"
        let model = WatchRoundModel(store: WatchRoundStore(directoryURL: directory()), autoShotEnabled: false, now: { clock })
        func snapshot(hole: Int, phoneRange: Double, revision: Int64, decision: String,
                      generated: String, expires: String) -> WatchRoundState {
            // Synthetic equator green: centre is 0.001 deg north per hole, edges ±0.0001.
            let centre = Double(hole) * 0.001
            return WatchRoundState(
                roundId: "link-round", hole: hole, par: 4, distanceM: phoneRange,
                suggestedClub: "6I", selectedClub: nil, decisionId: decision,
                frontGreenM: phoneRange - 10, centerGreenM: phoneRange, backGreenM: phoneRange + 10,
                frontGreenLat: centre - 0.0001, frontGreenLon: 0,
                centerGreenLat: centre, centerGreenLon: 0,
                backGreenLat: centre + 0.0001, backGreenLon: 0,
                holeMap: WatchHoleMap(w: 400, h: 400, you: [0, 0], pin: [300, 0],
                                     layup: [150, 0], apex: [100, 0], greenCtrl: [280, 0],
                                     route: [[0, 0, 0], [300, 0, 300]]),
                rootCaddieRecommendation: WatchRootCaddieRecommendation(
                    decisionId: decision, clubName: "6I", aimCarryM: 150, carryP10M: 140,
                    carryP90M: 160, sampleSize: 20, confidence: "high", source: "live", mode: "manual",
                    generatedAt: generated, validUntil: expires, originLatitude: hole == 1 ? 0 : 0.001,
                    originLongitude: 0, originAccuracyM: 4, maximumMovementM: 20, evidenceCount: 2),
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high", snapshotRevision: revision
            )
        }
        let first = snapshot(hole: 1, phoneRange: 333, revision: 1, decision: "first",
                             generated: "2026-10-23T11:59:00Z", expires: "2026-10-23T12:01:00Z")
        let second = snapshot(hole: 2, phoneRange: 444, revision: 1, decision: "old-second",
                              generated: "2026-10-23T11:59:00Z", expires: "2026-10-23T12:01:00Z")
        model.seedRound([first, second], activeHole: 1)
        model.receivePhoneState(first) // Fake connected phone delivers a snapshot.
        let firstFix = WatchLocationFix(coordinate: CLLocationCoordinate2D(latitude: 0, longitude: 0),
                                       horizontalAccuracyM: 4, capturedAt: clock)
        XCTAssertTrue(model.rootCaddieLayerAvailable(at: firstFix))
        XCTAssertEqual(model.activeHoleState?.centerGreenM, 333)

        // Fake phone disconnects: deliver no snapshots; advance time and the wrist position.
        clock = "2026-10-23T12:02:00Z"
        let rows: [(String, Double, [Int])] = [
            ("disconnected, at first tee", 0, [109, 122, 134]),
            ("disconnected, walked north", 0.0001, [97, 109, 122]),
        ]
        // Hand arithmetic: 0.001 deg = 111.195 m; ×1.09361, round to yards.
        // At 0: edges/centre 100.0755/111.195/122.3145 m -> 109/122/134 yd.
        // At 0.0001: 88.956/100.0755/111.195 m -> 97/109/122 yd.
        for (label, latitude, expected) in rows {
            let state = try XCTUnwrap(model.activeHoleState)
            let fix = WatchLocationFix(coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: 0),
                                      horizontalAccuracyM: 4, capturedAt: clock)
            let live = [
                WatchGeoMath.yards(from: latitude, 0, toLat: state.frontGreenLat, state.frontGreenLon),
                WatchGeoMath.yards(from: latitude, 0, toLat: state.centerGreenLat, state.centerGreenLon),
                WatchGeoMath.yards(from: latitude, 0, toLat: state.backGreenLat, state.backGreenLon),
            ]
            XCTAssertEqual(live, expected.map { Optional($0) }, label)
            let qualified = WatchRoundContainerView.rangeFixIsQualified(
                shotLocation: fix, watchGreenYards: nil, now: try XCTUnwrap(ISO8601DateFormatter().date(from: clock)))
            XCTAssertTrue(qualified, label)
            XCTAssertEqual(WatchRoundContainerView.canonicalCenterYards(
                live: live[1], fallbackMetres: state.centerGreenM, hasQualifiedRangeFix: qualified), expected[1], label)
            XCTAssertFalse(model.rootCaddieLayerAvailable(at: fix), label)
            XCTAssertEqual(model.activeHole, 1, label)
        }
        model.startScoringActiveHole()
        model.saveManualScore() // Watch advances to hole 2 while phone remains disconnected.
        XCTAssertEqual(model.activeHole, 2)
        model.receivePhoneState(snapshot(hole: 1, phoneRange: 888, revision: 2, decision: "late-first",
                                        generated: clock, expires: "2026-10-23T12:03:00Z"))
        XCTAssertEqual(model.activeHole, 2, "late reconnection payload for hole 1 must not move wrist cursor")
        XCTAssertEqual(model.activeHoleState?.decisionId, "old-second")
        model.receivePhoneState(snapshot(hole: 2, phoneRange: 222, revision: 2, decision: "fresh-second",
                                        generated: clock, expires: "2026-10-23T12:03:00Z"))
        XCTAssertEqual(model.round?.roundId, "link-round")
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.activeHoleState?.centerGreenM, 222)
        XCTAssertEqual(model.activeHoleState?.decisionId, "fresh-second")
        let secondFix = WatchLocationFix(coordinate: CLLocationCoordinate2D(latitude: 0.001, longitude: 0),
                                        horizontalAccuracyM: 4, capturedAt: clock)
        XCTAssertTrue(model.rootCaddieLayerAvailable(at: secondFix))
        XCTAssertEqual(model.round?.holeStates.first?.score, 4, "local first-hole score survives reconnection")
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
