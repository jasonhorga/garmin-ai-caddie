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

    // MARK: total ≥ putts + penalty + 1 (README §3)

    func testMorePuttsThanTheTotalAllowsRaisesTheTotal() {
        var draft = LiveScoreDraft(hole: 1, par: 3, phoneShotCount: 1)
        XCTAssertEqual(draft.score, 3)
        draft.selectPutts(3)
        XCTAssertEqual(draft.putts, 3)
        XCTAssertEqual(draft.score, 4, "three putts need at least one full shot before them")
    }

    func testTotalEqualToPuttsIsImpossible() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 2)
        draft.selectScore(4)
        draft.selectPutts(4)
        XCTAssertEqual(draft.score, 5)
        XCTAssertFalse(LiveHoleScore(hole: 1, par: 4, score: draft.score, putts: draft.putts, penalties: 0, fairway: nil, source: nil).estimatedGIR)
    }

    func testAddingPenaltiesRaisesTheTotal() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 2)
        XCTAssertEqual(draft.score, 4)
        XCTAssertEqual(draft.putts, 2)
        for _ in 0..<3 { draft.adjustPenalty(by: 1) }
        XCTAssertEqual(draft.penalty, 3)
        XCTAssertEqual(draft.score, 6, "2 putts + 3 penalties + 1 full shot")
    }

    func testLoweringPuttsOrPenaltiesNeverLowersTheTotal() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 2)
        draft.adjustPenalty(by: 2)
        draft.selectPutts(3)
        XCTAssertEqual(draft.score, 6)
        draft.adjustPenalty(by: -2)
        draft.selectPutts(1)
        XCTAssertEqual(draft.score, 6)
        XCTAssertEqual(draft.putts, 1)
        XCTAssertEqual(draft.penalty, 0)
    }

    func testLoweringTheTotalGivesWayWithPuttsThenPenalties() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 2)
        draft.adjustPenalty(by: 2)
        XCTAssertEqual(draft.score, 5)
        draft.selectScore(4)
        XCTAssertEqual(draft.putts, 1)
        XCTAssertEqual(draft.penalty, 2)
        draft.selectScore(2)
        XCTAssertEqual(draft.putts, 0)
        XCTAssertEqual(draft.penalty, 1)
        draft.selectScore(1)
        XCTAssertEqual(draft.putts, 0)
        XCTAssertEqual(draft.penalty, 0)
        XCTAssertGreaterThanOrEqual(draft.score, draft.minimumScore)
    }

    func testEveryReachableDraftKeepsTheInvariant() {
        var draft = LiveScoreDraft(hole: 1, par: 5, phoneShotCount: 0)
        let steps: [(inout LiveScoreDraft) -> Void] = [
            { $0.selectScore(2) }, { $0.selectPutts(4) }, { $0.adjustPenalty(by: 3) },
            { $0.selectScore(3) }, { $0.adjustFourPlusPutts(by: 1) }, { $0.selectPuttSegment(1) },
            { $0.adjustPenalty(by: -1) }, { $0.selectScore(1) }, { $0.selectPuttSegment(4) },
        ]
        for step in steps {
            step(&draft)
            XCTAssertGreaterThanOrEqual(draft.score, draft.putts + draft.penalty + 1)
        }
    }

    func testSavedRowBreakingTheInvariantOpensCorrected() {
        let draft = LiveScoreDraft(
            hole: 5, par: 4, savedScore: 4, savedPutts: 4, savedPenalty: 1,
            savedFairway: nil, savedSource: .manualEdit
        )
        XCTAssertEqual(draft.score, 6)
    }

    // MARK: putts 0 / 1 / 2 / 3 / 4+

    func testFourPlusSegmentKeepsTheRealCount() {
        XCTAssertEqual(LiveScoreDraft.puttSegments, [0, 1, 2, 3, 4])
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 2)
        draft.selectPuttSegment(LiveScoreDraft.fourPlusSegment)
        XCTAssertEqual(draft.putts, 4)
        XCTAssertEqual(draft.puttSegment, 4)
        draft.adjustFourPlusPutts(by: 1)
        draft.adjustFourPlusPutts(by: 1)
        XCTAssertEqual(draft.putts, 6)
        XCTAssertEqual(draft.puttSegment, 4, "five and more still show as 4+")
        XCTAssertEqual(draft.score, 7)
        draft.selectPuttSegment(LiveScoreDraft.fourPlusSegment)
        XCTAssertEqual(draft.putts, 6, "tapping 4+ again keeps the chosen count")
        for _ in 0..<10 { draft.adjustFourPlusPutts(by: 1) }
        XCTAssertEqual(draft.putts, LiveScoreDraft.maximumPutts)
        for _ in 0..<10 { draft.adjustFourPlusPutts(by: -1) }
        XCTAssertEqual(draft.putts, 4, "the 4+ stepper stays within 4…9")
        draft.selectPuttSegment(2)
        XCTAssertEqual(draft.putts, 2)
        draft.adjustFourPlusPutts(by: 1)
        XCTAssertEqual(draft.putts, 2, "the 4+ stepper only acts on 4+")
    }

    func testSixPuttsAreSubmittedAsSix() {
        var draft = LiveScoreDraft(hole: 1, par: 4, phoneShotCount: 2)
        draft.selectPutts(6)
        let events = LiveScoreSubmission.events(roundId: "r", draft: draft, note: "", timestamp: "t")
        XCTAssertEqual(events[1].payload["putts"], .number(6))
        XCTAssertEqual(events[0].payload["strokes"], .number(7))
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

    /// README §2 / §6: GIR = the first putt is stroke ≤ Par − 1, i.e. strokes − putts ≤ Par − 2.
    func testGIRIsEstimatedFromStrokesAndPutts() {
        XCTAssertTrue(hole(1, par: 4, score: 4, putts: 2).estimatedGIR)
        XCTAssertTrue(hole(2, par: 4, score: 3, putts: 1).estimatedGIR)
        XCTAssertFalse(hole(3, par: 4, score: 5, putts: 2).estimatedGIR)
        XCTAssertFalse(hole(4, par: 3, score: 3, putts: 1).estimatedGIR)
        // Boundary: on in regulation, then three putts — still a GIR (first putt is stroke 3 on a par 4).
        XCTAssertTrue(hole(5, par: 4, score: 5, putts: 3).estimatedGIR)
        XCTAssertTrue(hole(6, par: 5, score: 6, putts: 3).estimatedGIR)
        XCTAssertTrue(hole(7, par: 3, score: 3, putts: 2).estimatedGIR)
        // One stroke later to the green is a miss, however many putts follow.
        XCTAssertFalse(hole(8, par: 4, score: 6, putts: 3).estimatedGIR)
        XCTAssertFalse(hole(9, par: 5, score: 5, putts: 1).estimatedGIR)
    }

    func testUntouchedDefaultHolesAreSkippedForPuttsAndGIR() {
        let summary = LiveRoundScoreSummary(holes: [
            hole(1, par: 4, score: 4, putts: 2, fairway: "hit", source: "default"),
            hole(2, par: 4, score: 6, putts: 3, fairway: "left", source: "phone_shots"),
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

/// Marked shots ("记一杆") from the phone and from the watch count the same; other holes, other
/// rounds and non-location events never do.
final class LiveMarkedShotsTests: XCTestCase {
    private func event(_ id: String, round: String = "r1", hole: Int = 3, kind: LiveRoundEventKind = .location, client: String? = "ios-phone") -> LiveRoundEvent {
        LiveRoundEvent(
            eventId: id,
            roundId: round,
            clientId: client,
            timestamp: "2026-09-28T00:00:00Z",
            hole: hole,
            kind: kind,
            payload: ["latitude": .number(40), "longitude": .number(116)]
        )
    }

    func testWatchMarksCountLikePhoneMarksInMarkOrder() {
        let events = [
            event("a", client: "apple-watch"),
            event("b"),
            event("c", hole: 4),
            event("d", round: "r2"),
            event("e", kind: .club),
            event("f", client: "apple-watch"),
        ]
        let marked = LiveMarkedShots.locations(in: events, roundId: "r1", hole: 3)
        XCTAssertEqual(marked.map(\.eventId), ["a", "b", "f"])
        let draft = LiveScoreDraft(hole: 3, par: 4, watchSwingCount: nil, phoneShotCount: marked.count)
        XCTAssertEqual(draft.score, 5)
        XCTAssertEqual(draft.source, .phoneShots, "marks are never reported as automatic watch detection")
    }
}
