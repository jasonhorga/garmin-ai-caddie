import XCTest
@testable import AICaddie

final class LiveScoreConfirmationTests: XCTestCase {
    func testRecommendationUsesRecordedShotsPlusTwo() {
        let draft = LiveScoreDraft(
            hole: 7, par: 4, recordedShotCount: 2,
            currentScore: 7, currentPutts: 2, currentPenalty: 0
        )

        XCTAssertEqual(draft.step, .recommendation)
        XCTAssertEqual(draft.score, 4)
        XCTAssertEqual(draft.putts, 2)
    }

    func testParFourManualEntryRequiresFairwayBeforePenalty() {
        var draft = LiveScoreDraft(
            hole: 7, par: 4, recordedShotCount: 0,
            currentScore: 5, currentPutts: 2, currentPenalty: 0
        )

        draft.startManualEntry()
        XCTAssertEqual(draft.step, .score)
        draft.advanceManualEntry()
        XCTAssertEqual(draft.step, .putts)
        draft.advanceManualEntry()
        XCTAssertEqual(draft.step, .fairway)
        draft.advanceManualEntry()
        XCTAssertEqual(draft.step, .fairway)
        draft.selectFairway(.left)
        XCTAssertEqual(draft.step, .penalty)
        XCTAssertEqual(draft.fairway, .left)
    }

    func testParThreeManualEntrySkipsFairway() {
        var draft = LiveScoreDraft(
            hole: 2, par: 3, recordedShotCount: 1,
            currentScore: 3, currentPutts: 2, currentPenalty: 0
        )

        draft.startManualEntry()
        draft.advanceManualEntry()
        draft.advanceManualEntry()

        XCTAssertEqual(draft.step, .penalty)
        XCTAssertNil(draft.fairway)
    }

    func testScoreSubmissionCarriesFairwayButNeverFabricatesShotEvents() {
        var draft = LiveScoreDraft(
            hole: 7, par: 4, recordedShotCount: 2,
            currentScore: 4, currentPutts: 2, currentPenalty: 1
        )
        draft.selectFairway(.right)
        var nextId = 0

        let events = LiveScoreSubmission.events(
            roundId: "round-1",
            draft: draft,
            note: "  recovered well  ",
            timestamp: "2026-07-28T00:00:00Z",
            makeEventId: {
                nextId += 1
                return "event-\(nextId)"
            }
        )

        XCTAssertEqual(events.map(\.kind), [.score, .putt, .penalty, .note])
        XCTAssertFalse(events.contains { $0.kind == .location || $0.kind == .club })
        XCTAssertEqual(events[0].payload["fairway"], .string("right"))
        XCTAssertEqual(events[1].payload["putts"], .number(2))
        XCTAssertEqual(events[2].payload["penalties"], .number(1))
        XCTAssertEqual(events[3].payload["note"], .string("recovered well"))
    }
}
