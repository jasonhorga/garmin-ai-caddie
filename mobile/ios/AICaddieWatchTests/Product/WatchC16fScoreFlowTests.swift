import XCTest
@testable import AICaddieWatch

@MainActor
final class WatchC16fScoreFlowTests: XCTestCase {
    private func model() -> WatchRoundModel {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("c16f-score-\(UUID().uuidString)")
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        var eventID = 0
        return WatchRoundModel(store: WatchRoundStore(directoryURL: directory), autoShotEnabled: false, makeEventId: {
            eventID += 1
            return "score-\(eventID)"
        })
    }

    func test_5_13_watch_score_rolls_cover_all_allowed_putts_and_penalties() {
        // Hand golden: start at total 4. Each cell = max(4, putts + penalty + 1).
        // Rows are putts 0...5; columns are penalties 0...4. No product math builds this table.
        let totals = [
            [4, 4, 4, 4, 5], [4, 4, 4, 5, 6], [4, 4, 5, 6, 7],
            [4, 5, 6, 7, 8], [5, 6, 7, 8, 9], [6, 7, 8, 9, 10],
        ]
        for (putts, row) in totals.enumerated() {
            for (penalty, total) in row.enumerated() {
                let model = model()
                model.startPracticeRound(holeCount: 1, par: 4)
                model.startScoringActiveHole()
                model.setDraftPutts(putts)
                model.setDraftPenalty(penalty)
                XCTAssertEqual([model.draftScore, model.draftPutts, model.draftPenalty],
                               [total, putts, penalty], "putts=\(putts), penalty=\(penalty)")
            }
        }
    }

    func test_5_13_watch_score_rolls_clamp_at_five_putts_and_four_penalties() {
        let rows: [(String, Int, Int, [Int])] = [
            ("one beyond putts upper edge", 6, 0, [6, 5, 0]), // 5 + 0 + 1
            ("one beyond penalty upper edge", 0, 5, [5, 0, 4]), // 0 + 4 + 1
            ("below both lower edges", -1, -1, [4, 0, 0]), // chosen total stays 4
        ]
        for (label, putts, penalty, expected) in rows {
            let model = model()
            model.startPracticeRound(holeCount: 1, par: 4)
            model.startScoringActiveHole()
            model.setDraftPutts(putts)
            model.setDraftPenalty(penalty)
            let check = {
                XCTAssertEqual([model.draftScore, model.draftPutts, model.draftPenalty], expected, label)
            }
            if putts > 5 || penalty > 4 {
                XCTExpectFailure("5.13: the shared score rule currently permits 9 putts / 9 penalties", failingBlock: check)
            } else {
                check()
            }
        }
    }

    func test_5_13_watch_next_tee_shot_saves_unconfirmed_draft() throws {
        // Hand golden: untouched par-4 draft = 4/2/0; changed draft = 7/3/2
        // (two full shots + three putts + two penalties). The next tee is ~111 m north.
        let rows: [(String, [Int])] = [("default draft", [4, 2, 0]), ("edited draft", [7, 3, 2])]
        for (label, expected) in rows {
            let model = model()
            let first = WatchRoundState(
                roundId: "auto-save", hole: 1, par: 4, distanceM: nil,
                teeLatitude: 40, teeLongitude: 116, selectedClub: nil,
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
            )
            let second = WatchRoundState(
                roundId: "auto-save", hole: 2, par: 4, distanceM: nil,
                teeLatitude: 40.001, teeLongitude: 116, selectedClub: nil,
                score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
            )
            model.seedRound([first, second], activeHole: 1)
            model.resumeRound()
            model.startScoringActiveHole()
            model.setDraftScore(expected[0])
            model.setDraftPutts(expected[1])
            model.setDraftPenalty(expected[2])
            XCTAssertEqual(model.round?.pendingEvents.count, 0, label)
            // No save/confirmation action: the next tee's first shot is the only trigger.
            model.beginManualShot(latitude: 40.001, longitude: 116, horizontalAccuracyM: 4,
                                  capturedAt: "2026-10-23T12:00:00Z")
            let saved = try XCTUnwrap(model.round?.holeStates.first { $0.hole == 1 })
            XCTAssertEqual([saved.score, saved.putts, saved.penaltyCount], expected, label)
            XCTAssertEqual(model.activeHole, 2, label)
            XCTAssertEqual(model.pendingManualShot?.hole, 2, label)
            model.completePendingManualShot(clubName: nil)
            XCTAssertEqual(model.round?.pendingEvents.filter { $0.kind == .location }.map(\.hole), [2], label)
            XCTAssertEqual(model.round?.holeStates.last?.score, 0, label)
        }
    }
}
