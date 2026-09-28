import XCTest
@testable import AICaddie

/// B2 本洞记分 draft: preselection priority, "edited" detection and the source written with it.
final class LiveScoreConfirmationTests: XCTestCase {
    func testWatchSwingsWinOverPhoneShotsAndPar() {
        let draft = LiveScoreDraft(hole: 1, par: 5, watchSwingCount: 3, watchPuttCount: 1, phoneShotCount: 4)
        XCTAssertEqual(draft.score, 4)
        XCTAssertEqual(draft.putts, 1)
        XCTAssertEqual(draft.source, .watchDetected)
    }

    func testWatchSwingsWithoutDetectedPuttsAssumeTwoPutts() {
        let draft = LiveScoreDraft(hole: 1, par: 5, watchSwingCount: 3, phoneShotCount: 0)
        XCTAssertEqual(draft.score, 5)
        XCTAssertEqual(draft.putts, 2)
        XCTAssertEqual(draft.source, .watchDetected)
    }

    func testPhoneShotsPlusTwoPuttsWithoutWatchData() {
        let draft = LiveScoreDraft(hole: 7, par: 4, watchSwingCount: 0, phoneShotCount: 3)
        XCTAssertEqual(draft.score, 5)
        XCTAssertEqual(draft.putts, 2)
        XCTAssertEqual(draft.source, .phoneShots)
    }

    func testNothingRecordedDefaultsToPar() {
        let parFive = LiveScoreDraft(hole: 1, par: 5, phoneShotCount: 0)
        XCTAssertEqual(parFive.score, 5)
        XCTAssertEqual(parFive.putts, 2)
        XCTAssertEqual(parFive.source, .default)
        let parThree = LiveScoreDraft(hole: 2, par: 3, phoneShotCount: 0)
        XCTAssertEqual(parThree.score, 3)
        XCTAssertEqual(parThree.putts, 2)
    }

    func testTeeResultPreselectsExceptOnParThree() {
        XCTAssertEqual(LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 0, teeResult: .right).fairway, .right)
        XCTAssertNil(LiveScoreDraft(hole: 2, par: 3, phoneShotCount: 0, teeResult: .hit).fairway)
    }

    func testMorePuttsThanTotalRaisesTheTotal() {
        var draft = LiveScoreDraft(hole: 1, par: 3, phoneShotCount: 1)
        XCTAssertEqual(draft.score, 3)
        draft.selectPutts(4)
        XCTAssertEqual(draft.putts, 4)
        XCTAssertEqual(draft.score, 4)
    }

    func testLoweringTheTotalKeepsPuttsInside() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 2)
        draft.selectScore(1)
        XCTAssertEqual(draft.score, 1)
        XCTAssertEqual(draft.putts, 1)
    }

    func testAnyChangeMakesItAManualEditAndReselectingIsNotAChange() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 0)
        draft.selectScore(4)
        draft.selectPutts(2)
        draft.adjustPenalty(by: -1)
        XCTAssertFalse(draft.edited)
        XCTAssertEqual(draft.source, .default)
        draft.selectFairway(.left)
        XCTAssertTrue(draft.edited)
        XCTAssertEqual(draft.source, .manualEdit)
    }

    func testPenaltyStaysWithinBounds() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 0)
        draft.adjustPenalty(by: -1)
        XCTAssertEqual(draft.penalty, 0)
        for _ in 0..<20 { draft.adjustPenalty(by: 1) }
        XCTAssertEqual(draft.penalty, LiveScoreDraft.maximumPenalty)
    }

    func testScoreStripAlwaysStartsAtOne() {
        let draft = LiveScoreDraft(hole: 1, par: 5, phoneShotCount: 9)
        XCTAssertEqual(draft.scoreChoices.lowerBound, 1)
        XCTAssertGreaterThanOrEqual(draft.scoreChoices.upperBound, draft.score + 2)
    }

    func testScorecardEditKeepsTheSavedSourceUntilChanged() {
        var draft = LiveScoreDraft(
            hole: 5, par: 4, savedScore: 5, savedPutts: 2, savedPenalty: 0,
            savedFairway: .hit, savedSource: .phoneShots
        )
        XCTAssertFalse(draft.advanceAfterSave)
        XCTAssertEqual(draft.source, .phoneShots)
        draft.selectScore(6)
        XCTAssertEqual(draft.source, .manualEdit)
    }

    func testSubmissionWritesTheSourceOnScorePuttAndPenaltyButNeverFabricatesShots() {
        var draft = LiveScoreDraft(hole: 7, par: 4, phoneShotCount: 2, teeResult: .hit)
        draft.adjustPenalty(by: 1)
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
        XCTAssertEqual(events[0].payload["fairway"], .string("hit"))
        XCTAssertEqual(events[0].payload["strokes"], .number(4))
        XCTAssertEqual(events[1].payload["putts"], .number(2))
        XCTAssertEqual(events[2].payload["penalties"], .number(1))
        for event in events.prefix(3) {
            XCTAssertEqual(event.payload["source"], .string("manual_edit"))
        }
        XCTAssertEqual(events[3].payload["note"], .string("recovered well"))
    }

    func testUntouchedDefaultIsSubmittedAsDefault() {
        let draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 0)
        let events = LiveScoreSubmission.events(roundId: "r", draft: draft, note: "", timestamp: "t")
        XCTAssertEqual(events.count, 3)
        XCTAssertTrue(events.allSatisfy { $0.payload["source"] == .string("default") })
    }

    func testSaveTitleNamesTheNextHole() {
        XCTAssertEqual(LiveScoreConfirmationView.saveTitle(score: 5, nextHole: 2), "保存 5 杆 · 去第 2 洞")
        XCTAssertEqual(LiveScoreConfirmationView.saveTitle(score: 5, nextHole: nil), "保存 5 杆")
    }
}

/// Scorecard / summary totals: GIR estimated from strokes and putts; default holes skipped.
final class LiveRoundScoreSummaryTests: XCTestCase {
    private func hole(_ number: Int, par: Int, score: Int, putts: Int, fairway: String? = nil, source: String? = "manual_edit") -> LiveHoleScore {
        LiveHoleScore(hole: number, par: par, score: score, putts: putts, penalties: 0, fairway: fairway, source: source)
    }

    func testCumulativeToParAndTotals() {
        let summary = LiveRoundScoreSummary(holes: [
            hole(1, par: 5, score: 5, putts: 2),
            hole(2, par: 4, score: 5, putts: 2),
            hole(3, par: 3, score: 2, putts: 1),
        ])
        XCTAssertEqual(summary.strokes, 12)
        XCTAssertEqual(summary.toPar, 0)
        XCTAssertEqual(summary.cumulativeToPar, [0, 1, 0])
    }

    func testGIRIsEstimatedFromStrokesAndPutts() {
        XCTAssertTrue(hole(1, par: 4, score: 4, putts: 2).estimatedGIR)
        XCTAssertTrue(hole(2, par: 4, score: 3, putts: 1).estimatedGIR)
        XCTAssertFalse(hole(3, par: 4, score: 5, putts: 2).estimatedGIR)
        XCTAssertFalse(hole(4, par: 3, score: 3, putts: 1).estimatedGIR)
    }

    func testUntouchedDefaultHolesAreSkippedForPuttsAndGIR() {
        let summary = LiveRoundScoreSummary(holes: [
            hole(1, par: 4, score: 4, putts: 2, fairway: "hit", source: "default"),
            hole(2, par: 4, score: 5, putts: 3, fairway: "left", source: "phone_shots"),
        ])
        XCTAssertEqual(summary.putts, 3)
        XCTAssertEqual(summary.puttHoles, 1)
        XCTAssertEqual(summary.girRecorded, 1)
        XCTAssertEqual(summary.girHit, 0)
        XCTAssertEqual(summary.fairwaysRecorded, 2)
        XCTAssertEqual(summary.fairwaysHit, 1)
        let allDefault = LiveRoundScoreSummary(holes: [hole(1, par: 4, score: 4, putts: 2, source: "default")])
        XCTAssertNil(allDefault.putts)
        XCTAssertNil(LiveRoundScoreSummary.percent(allDefault.girHit, of: allDefault.girRecorded))
    }
}
