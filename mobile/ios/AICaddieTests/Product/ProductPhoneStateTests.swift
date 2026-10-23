import CoreLocation
import XCTest
@testable import AICaddie

@MainActor
final class ProductPhoneStateTests: XCTestCase {
    func test_j2_7_distance_ladder_flags_only_abnormal_gaps() throws {
        // Metres are exactly yards * .9144; the 150/142 gap is legal,
        // 142/135 overlaps, 135/115 is legal, 115/94 leaves a hole.
        let rows: [(String, Int, Int, Int, Bool)] = [
            ("lower-bound", 150, 142, 8, false), ("overlap", 142, 135, 7, true),
            ("upper-bound", 135, 115, 20, false), ("hole", 115, 94, 21, true),
        ]
        for (id, high, low, expectedGap, flagged) in rows {
            func row(_ yards: Int) -> BagPresentation.Row {
                .init(name: id, p10: yards - 5, historyMedian: yards, p90: yards + 5, samples: 20, manual: nil)
            }
            let gap = try XCTUnwrap(BagPresentation.gap(row(high), row(low)), id)
            XCTAssertEqual(gap.yards, expectedGap, id)
            XCTAssertEqual(gap.isFlagged, flagged, id)
        }
        let profile = ClubProfile(clubName: "7I", sampleSize: 20, medianM: 137.16, p10M: 128.016, p90M: 146.304)
        let ladder = BagPresentation.rows(bag: ["七号铁", "八号铁", "推杆"], profiles: [profile], manual: ["七号铁": 155])
        XCTAssertEqual(ladder.map(\.name), ["七号铁", "八号铁"])
        XCTAssertEqual(ladder[0].historyMedian, 150)
        XCTAssertEqual(ladder[0].median, 155)
        XCTAssertEqual(ladder[0].p10, 140)
        XCTAssertEqual(ladder[0].p90, 160)
        XCTAssertNil(ladder[1].median)
    }

    func test_j3_2_insert_guess_reorder_delete_keeps_continuous_shots() throws {
        let model = RoundEditModel(map: try ProductInputs.shotMap(),
                                   sync: SyncClient(baseURL: URL(string: "https://example.invalid")!), roundRef: "synthetic")
        model.enterEdit()
        let added = model.addShot(px: [100, 108.56], afterShotId: "s1")
        // 200 - 108.56 = 91.44 m = 100 yd -> gap wedge; insert immediately after s1.
        XCTAssertFalse(added.isEmpty)
        XCTAssertEqual(model.map.shots.map(\.id), ["s1", added, "s2"], "insert")
        XCTAssertEqual(model.map.shots[1].club, "GW", "distance-based guess")
        XCTAssertEqual(model.map.shots.map(\.order), [1, 2, 3], "insert numbering")
        model.reorder(["s2", added, "s1"])
        XCTAssertEqual(model.map.shots.map(\.id), ["s2", added, "s1"], "reorder")
        XCTAssertEqual(model.map.shots.map(\.order), [1, 2, 3], "reorder numbering")
        model.delete(shotId: added)
        XCTAssertEqual(model.map.shots.map(\.id), ["s2", "s1"], "delete")
        XCTAssertEqual(model.map.shots.map(\.order), [1, 2], "delete numbering")
        model.cancelEdit()
        XCTAssertEqual(model.map.shots.map(\.id), ["s1", "s2"], "cancel restores original")
    }

    func test_j4_1_course_sources_merge_into_one_list() {
        let a = ProductInputs.course(82001, venue: "Example")
        let b = ProductInputs.course(82002, venue: "Example")
        let other = ProductInputs.course(81001, venue: "Other", holes: 18)
        // With location, nearby owns Example's two nines. Without it, search owns them.
        for located in [false, true] {
            let rows = StartRoundPresentation.mergedCourseRows(
                nearby: located ? [a, b, a] : [], search: [a, b], recent: [a], downloaded: [a, other, other]
            )
            XCTAssertEqual(rows.map(\.venue), ["Example", "Other"], "located=\(located)")
            XCTAssertEqual(rows.map(\.holes), [18, 18], "coverage=\(located)")
            XCTAssertEqual(rows.map { $0.segments.map(\.globalId) }, [[82001, 82002], [81001]])
            XCTAssertEqual(rows[0].source, located ? .nearby : .search)
            XCTAssertEqual(rows[1].source, .downloaded)
        }
    }

    func test_j5_1_phone_defaults_and_every_hole_ten_event_lock() throws {
        let history: HistoryRoundCard = try ProductSharedVectors.decode([
            "id": "synthetic-pair", "courseName": "Example", "globalId": 82001, "backGlobalId": 82002,
        ])
        let ids: Set<String> = ["82001:all", "82002:all", "82003:all"]
        for (name, local, expected) in [
            ("history", [String: String](), "82002:all"),
            ("local-over-history", ["82001:all": "82003:all"], "82003:all"),
            ("invalid-local-ignored", ["82001:all": "99999:all"], "82002:all"),
        ] {
            XCTAssertEqual(NineLoopTurn.usualPairs(remembered: local, history: [history], loopIds: ids)["82001:all"], expected, name)
        }
        let template = try ProductInputs.package()
        for (name, entries, expectedFirst) in [
            ("front-back", [RoundLoopEntry(globalId: 81001, half: "front"), .init(globalId: 81001, half: "back")], 1),
            ("back-front", [RoundLoopEntry(globalId: 81001, half: "back"), .init(globalId: 81001, half: "front")], 10),
            ("back-back", [RoundLoopEntry(globalId: 81001, half: "back"), .init(globalId: 81001, half: "back")], 10),
            ("front-front", [RoundLoopEntry(globalId: 81001, half: "front"), .init(globalId: 81001, half: "front")], 1),
        ] {
            let package = try XCTUnwrap(LiveRoundPackage.projecting(entries, templates: [81001: template], roundId: name))
            XCTAssertEqual(package.courseHoleNumber(forRoundHole: 1), expectedFirst, name)
            for kind in LiveRoundEventKind.allCases where kind != .syncMarker {
                func event(_ round: String, _ hole: Int) -> LiveRoundEvent {
                    LiveRoundEvent(eventId: "example", roundId: round, timestamp: "2026-10-23T00:00:00Z", hole: hole, kind: kind, payload: [:])
                }
                XCTAssertFalse(package.isSecondLoopLocked(by: [event(name, 9)]), name + kind.rawValue)
                XCTAssertFalse(package.isSecondLoopLocked(by: [event("another", 10)]), name + kind.rawValue)
                XCTAssertTrue(package.isSecondLoopLocked(by: [event(name, 10)]), name + kind.rawValue)
            }
        }
    }

    func test_j5_2_home_hero_priorities_with_and_without_downloads() {
        let suggestion = HubCourseSuggestion(globalId: 81001, courseName: "Example", startTitle: "", teeBox: "blue")
        let rows: [(String, Bool, HubCourseSuggestion?, HubCourseSuggestion?, HubHeroState)] = [
            ("active", true, suggestion, suggestion, .inProgress),
            ("nearby", false, suggestion, suggestion, .nearby(suggestion)),
            ("search-replay", false, nil, suggestion, .search(replay: suggestion)),
            ("first-use", false, nil, nil, .search(replay: nil)),
        ]
        for (id, active, nearby, replay, expected) in rows {
            XCTAssertEqual(HubHeroState.resolve(hasActiveRound: active, hasPendingWatchRound: false, nearby: nearby, replay: replay), expected, id)
        }
        for downloaded in [[], [ProductInputs.course(81001, venue: "Example", holes: 18)]] {
            XCTAssertEqual(HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, fix: nil,
                nearbyOptions: [], history: [], recent: nil, catalogue: [], downloaded: downloaded), .search(replay: nil))
        }
    }

    func test_j5_3_home_weather_and_latest_round_strip_are_factual() throws {
        // Missing, failed or non-finite temperatures cannot produce a weather tile.
        for (id, state, temperature) in [("missing", "missing", Optional(23.0)), ("no-temperature", "ready", nil), ("invalid", "ready", Double.nan)] {
            XCTAssertNil(HomeWeather(state: state, temperatureC: temperature, windSpeedMps: nil,
                windDirectionDeg: nil, condition: nil, precipitationProbabilityPct: nil).presentation, id)
        }
        let weather = HomeWeather(temperatureC: 18.4, windSpeedMps: 3, windDirectionDeg: 90,
                                  condition: "clear", precipitationProbabilityPct: 40)
        XCTAssertNotNil(weather.presentation)
        XCTAssertEqual(weather.temperatureC, 18.4, "provider temperature fact")
        let renderedTemperature = weather.presentation?.temperatureText.split(whereSeparator: { !$0.isNumber }).first.flatMap { Int($0) }
        XCTAssertEqual(renderedTemperature, 18, "rounded temperature value, independent of suffix copy")
        XCTAssertEqual(HomeWeather.beaufortForce(3), 2)
        let recent: [HistoryRoundCard] = try (80...88).map { score in
            try ProductSharedVectors.decode(["id": "r\(score)", "courseName": "Example", "holesCompleted": 18, "score": score])
        }
        // Input newest-first 80...88; take eight, then draw oldest-first, excluding the ninth.
        XCTAssertEqual(HubScoresTile.recentScores(history: recent), [87, 86, 85, 84, 83, 82, 81, 80])
        let carries = HubBagTile.carries(from: [
            ClubProfile(clubName: "7I", sampleSize: 20, medianM: 137.16, p10M: 128.016, p90M: 146.304),
            ClubProfile(clubName: "3W", sampleSize: 20, medianM: 182.88, p10M: 173.736, p90M: 192.024),
        ])
        XCTAssertEqual(carries.map { $0.yards }, [200, 150], "longest club leads the home tile")
        let latest = try ProductInputs.card("newest")
        XCTAssertEqual(HubHeroState.lastRoundStrip(lastRoundId: "newest", newest: latest).map(\.score), [5])
        XCTAssertTrue(HubHeroState.lastRoundStrip(lastRoundId: "older", newest: latest).isEmpty)
        XCTAssertTrue(HubHeroState.lastRoundStrip(lastRoundId: "newest", newest: nil).isEmpty)
    }

    func test_j5_6_score_preselection_and_edit_sequence() {
        let rows: [(String, Int?, Int?, Int, Int, Int, LiveScoreSource)] = [
            ("watch-first", 3, 1, 8, 4, 1, .watchDetected),
            ("phone", nil, nil, 3, 5, 2, .phoneShots),
            ("zero-watch", 0, 0, 2, 4, 2, .phoneShots),
            ("default", nil, nil, 0, 4, 2, .default),
        ]
        for (id, watch, watchPutts, phone, total, putts, source) in rows {
            var draft = LiveScoreDraft(hole: 1, par: 4, watchSwingCount: watch, watchPuttCount: watchPutts, phoneShotCount: phone)
            XCTAssertEqual(draft.score, total, id)
            XCTAssertEqual(draft.putts, putts, id)
            XCTAssertEqual(draft.source, source, id)
            draft.selectPutts(5)
            XCTAssertEqual(draft.score, 6, id + " five putts require at least six")
            draft.adjustPenalty(by: 2)
            XCTAssertEqual(draft.score, 8, id + " five putts + two penalties + one shot")
            XCTAssertEqual(draft.source, .manualEdit, id)
            draft.selectScore(3)
            XCTAssertEqual(draft.score, 3, id)
            XCTAssertEqual(draft.putts, 0, id)
            XCTAssertEqual(draft.penalty, 2, id)
            let events = LiveScoreSubmission.events(roundId: "synthetic", draft: draft, note: "", timestamp: "2026-10-23T00:00:00Z")
            XCTAssertEqual(events.map(\.kind), [.score, .putt, .penalty], id)
            XCTAssertTrue(events.allSatisfy { $0.payload["source"] == .string("manual_edit") }, id)
        }
    }

    func test_j5_9_queue_survives_restart_replay_and_round_discard() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let a = LiveRoundEventBuilder(roundId: "a", idFactory: { "a1" }).makeScoreEvent(hole: 1, strokes: 5)
        let b = LiveRoundEventBuilder(roundId: "b", idFactory: { "b1" }).makeScoreEvent(hole: 1, strokes: 4)
        try store.appendEvent(a)
        try store.appendEvent(b)
        let restarted = OfflineStore(directoryURL: directory)
        XCTAssertEqual(try restarted.loadPendingEvents().map(\.eventId), ["a1", "b1"], "offline restart")
        _ = try restarted.applyReplayEvents([a, b, a])
        XCTAssertEqual(try restarted.loadPendingEvents().map(\.eventId), ["a1", "b1"], "repeated delivery")
        try restarted.appendSyncMarker(roundId: "a", timestamp: "2026-10-23T00:00:00Z")
        XCTAssertTrue(try restarted.loadPendingEvents(roundId: "a").isEmpty, "acknowledged a")
        XCTAssertEqual(try restarted.loadPendingEvents(roundId: "b").map(\.eventId), ["b1"], "b still queued")
        try restarted.discardRound(roundId: "a")
        XCTAssertEqual(try restarted.loadEvents().filter { $0.roundId == "b" }.map(\.eventId), ["b1"], "discard one round")
    }

    func test_j5_10_summary_uses_recorded_holes_and_updates_edits() throws {
        let template = try ProductInputs.package()
        let reversed = try XCTUnwrap(LiveRoundPackage.projecting([
            RoundLoopEntry(globalId: 81001, half: "back"), RoundLoopEntry(globalId: 81001, half: "front"),
        ], templates: [81001: template], roundId: "back-front"))
        let card = LiveRoundScorecardView(courseName: "Example", holes: reversed.holes,
            liveRoundState: nil, recordedScoreHoles: [], onEdit: { _ in })
        XCTAssertEqual(Array(card.holes.prefix(9)).map(\.courseHoleNumber), [10, 11, 12, 13, 14, 15, 16, 17, 18])
        XCTAssertEqual(Array(card.holes.suffix(9)).map(\.courseHoleNumber), [1, 2, 3, 4, 5, 6, 7, 8, 9])
        // Nine par fours: scores 5,4,4,4,4,4,4,4,4 -> 37/36, +1.
        // A full round repeats that half -> 74/72, +2. Back-first keeps play order.
        for (id, count, expectedStrokes, expectedPar) in [("nine", 9, 37, 36), ("eighteen", 18, 74, 72), ("back-front", 18, 74, 72)] {
            var holes = (1...count).map { n in LiveHoleScore(hole: n, par: 4, score: (n == 1 || n == 10) ? 5 : 4,
                putts: 2, penalties: 0, fairway: nil, source: "manual_edit") }
            let summary = LiveRoundScoreSummary(holes: holes)
            XCTAssertEqual(summary.strokes, expectedStrokes, id)
            XCTAssertEqual(summary.par, expectedPar, id)
            XCTAssertEqual(Array(summary.cumulativeToPar.prefix(9)), [1, 1, 1, 1, 1, 1, 1, 1, 1], id)
            holes[0] = LiveHoleScore(hole: 1, par: 4, score: 3, putts: 1, penalties: 0, fairway: nil, source: "manual_edit")
            XCTAssertEqual(LiveRoundScoreSummary(holes: holes).strokes, expectedStrokes - 2, id + " historical edit")
            XCTAssertEqual(LiveRoundScoreSummary(holes: holes).par, expectedPar, id)
        }
    }
}
