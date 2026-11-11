// size: medium
// goals: W-05, W-06, W-07
import Foundation
import XCTest
import AICaddieDomain
import AICaddieCore
@testable import AICaddieWatch

/// Recording on the Watch: the hole score (crown, the score ≥ putts + penalty + 1 rule, autosave
/// of the draft, the order of events when a hole changes), manual shots with their club and undo,
/// and the scorecard. Everything is checked through the durable store and its event queue.
@MainActor
final class WatchScoringGoalTests: XCTestCase {
    private static let fixedNow = "2026-06-20T00:00:00Z"

    // MARK: - helpers

    private func tempDirectory() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("wgoal-\(UUID().uuidString)", isDirectory: true)
    }

    private func makeModel(_ dir: URL, ids: @escaping () -> String) -> WatchRoundModel {
        WatchRoundModel(
            store: WatchRoundStore(directoryURL: dir),
            autoShotEnabled: false,
            persistAutoShotEnabled: { _ in },
            makeEventId: ids,
            now: { Self.fixedNow }
        )
    }

    private func sequentialIds(_ prefix: String = "evt") -> () -> String {
        var counter = 0
        return {
            counter += 1
            return "\(prefix)-\(counter)"
        }
    }

    /// Open the score entry for the active hole (draft par/2/0 on an unscored par-4 hole).
    private func openActiveHoleScore(_ model: WatchRoundModel) {
        model.startScoringActiveHole()
        model.startManualScoreEntry()
    }

    private func scoreActiveHole(_ model: WatchRoundModel, score: Int? = nil) {
        openActiveHoleScore(model)
        if let score { model.setDraftScore(score) }
        model.saveManualScore()
    }

    private func draft(_ model: WatchRoundModel) -> [Int] {
        [model.draftScore, model.draftPutts, model.draftPenalty]
    }

    private func summary(_ events: [WatchInputEvent]) -> [String] {
        events.map { "\($0.hole):\($0.kind.rawValue)=\($0.value)" }
    }

    private func beginShot(_ model: WatchRoundModel, at capturedAt: String) {
        model.beginManualShot(
            latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 5.0, capturedAt: capturedAt
        )
    }

    // MARK: - W-05 hole score

    /// The crown moves score, putts and penalty under the shared rule, and Save records only what
    /// changed — total first, then the raised putts and penalty — and moves to the next hole.
    // goals: W-05 [main]
    func testCrownEntrySavesTheHoleScoreAsEvents() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        openActiveHoleScore(model)
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertEqual(draft(model), [4, 2, 0], "an unscored par 4 opens at par, two putts")

        model.adjustDraftPenalty(1)
        XCTAssertEqual(draft(model), [4, 2, 1])
        model.adjustDraftPutts(1)
        XCTAssertEqual(draft(model), [5, 3, 1], "a third putt raises the total only because it must")
        model.adjustDraftScore(-1)
        XCTAssertEqual(draft(model), [4, 2, 1], "a lower total gives way by lowering putts")
        model.adjustDraftScore(1)
        XCTAssertEqual(draft(model), [5, 2, 1], "a higher total never raises putts")
        XCTAssertTrue(WatchRoundStore(directoryURL: dir).pendingEvents().isEmpty, "nothing recorded before Save")

        model.saveManualScore()

        let store = WatchRoundStore(directoryURL: dir)
        let events = store.pendingEvents()
        XCTAssertEqual(summary(events), ["1:score=5", "1:putt=2", "1:penalty=1"])
        XCTAssertEqual(events.map(\.eventId), ["evt-2", "evt-3", "evt-4"])
        XCTAssertTrue(events.allSatisfy { $0.roundId == "watch-evt-1" && $0.createdAt == Self.fixedNow })
        let hole = try XCTUnwrap(store.holeState(hole: 1))
        XCTAssertEqual([hole.score, hole.putts, hole.penaltyCount], [5, 2, 1])
        XCTAssertEqual(model.round?.holeStates.first { $0.hole == 1 }?.score, 5)
        XCTAssertEqual(model.activeHole, 2)
        XCTAssertEqual(model.screen, .home)
        XCTAssertNil(store.load()?.scoreDraft)
    }

    /// Whatever is entered, the draft keeps score ≥ putts + penalty + 1, putts ≤ 5, penalty ≤ 4 and
    /// score ≥ 1, with no wrap-around.
    // goals: W-05
    func testDraftAlwaysKeepsScoreAbovePuttsPlusPenalty() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        openActiveHoleScore(model)

        let steps: [(String, () -> Void, [Int])] = [
            ("putts 9", { model.setDraftPutts(9) }, [6, 5, 0]),
            ("penalty 9", { model.setDraftPenalty(9) }, [10, 5, 4]),
            ("score 3", { model.setDraftScore(3) }, [3, 0, 2]),
            ("score 0", { model.setDraftScore(0) }, [1, 0, 0]),
            ("putts -1", { model.adjustDraftPutts(-1) }, [1, 0, 0]),
            ("penalty +1", { model.adjustDraftPenalty(1) }, [2, 0, 1]),
        ]
        for (label, step, expected) in steps {
            step()
            XCTAssertEqual(draft(model), expected, label)
            XCTAssertGreaterThanOrEqual(model.draftScore, model.draftPutts + model.draftPenalty + 1, label)
            XCTAssertLessThanOrEqual(model.draftPutts, 5, label)
            XCTAssertLessThanOrEqual(model.draftPenalty, 4, label)
        }

        model.saveManualScore()
        let hole = WatchRoundStore(directoryURL: dir).holeState(hole: 1)
        XCTAssertEqual(hole.map { [$0.score, $0.putts, $0.penaltyCount] }, [2, 0, 1])
    }

    /// A hole in one is 1 / 0 / 0: picking 1 drops the default putts, and only the score is recorded.
    // goals: W-05
    func testHoleInOneRecordsOneZeroZero() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound(par: 3)
        openActiveHoleScore(model)
        XCTAssertEqual(draft(model), [3, 2, 0])

        model.setDraftScore(1)
        XCTAssertEqual(draft(model), [1, 0, 0])
        model.saveManualScore()

        let store = WatchRoundStore(directoryURL: dir)
        let events = store.pendingEvents()
        XCTAssertEqual(summary(events), ["1:score=1"])
        XCTAssertNil(events.first?.fairwayResult, "a par 3 has no fairway")
        let hole = try XCTUnwrap(store.holeState(hole: 1))
        XCTAssertEqual([hole.score, hole.putts, hole.penaltyCount], [1, 0, 0])
        XCTAssertEqual(model.activeHole, 2)
    }

    /// Every draft change is written to the round file at once, so a process kill loses nothing;
    /// after Resume the same draft saves with its fairway.
    // goals: W-05
    func testDraftAutosavesAndSurvivesARelaunch() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        openActiveHoleScore(model)
        model.setDraftScore(5)
        model.setDraftPutts(1)
        model.setDraftPenalty(1)
        model.setDraftFairway(.left)
        XCTAssertEqual(draft(model), [5, 1, 1])

        let stored = try XCTUnwrap(WatchRoundStore(directoryURL: dir).load()?.scoreDraft)
        XCTAssertEqual(stored.hole, 1)
        XCTAssertEqual([stored.score, stored.putts, stored.penalty], [5, 1, 1])
        XCTAssertEqual(stored.fairway, .left)
        XCTAssertEqual(stored.step, .score)
        XCTAssertTrue(stored.advanceAfterSave)
        XCTAssertTrue(WatchRoundStore(directoryURL: dir).pendingEvents().isEmpty, "a draft is not an event")

        let relaunched = makeModel(dir, ids: sequentialIds("relaunch"))
        relaunched.resumeRound()
        XCTAssertEqual(relaunched.screen, .scoring)
        XCTAssertEqual(draft(relaunched), [5, 1, 1])
        XCTAssertEqual(relaunched.draftFairway, .left)
        relaunched.saveManualScore()

        let store = WatchRoundStore(directoryURL: dir)
        let events = store.pendingEvents()
        XCTAssertEqual(summary(events), ["1:score=5", "1:putt=1", "1:penalty=1"])
        XCTAssertEqual(events.first?.fairwayResult, "LEFT")
        XCTAssertEqual(store.holeState(hole: 1)?.fairwayResult?.uppercased(), "LEFT")
        XCTAssertNil(store.load()?.scoreDraft)
        XCTAssertEqual(relaunched.activeHole, 2)
    }

    /// Changing a recorded hole emits lowered putts/penalty first, then the total, then raised
    /// putts/penalty, so no prefix of the queue ever breaks the score rule; an unchanged edit emits
    /// nothing and does not move the cursor.
    // goals: W-05
    func testChangingARecordedHoleNeverQueuesAnImpossibleCard() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        openActiveHoleScore(model)
        model.setDraftScore(7)
        model.setDraftPutts(4)
        model.setDraftPenalty(1)
        model.saveManualScore()
        let store = WatchRoundStore(directoryURL: dir)
        XCTAssertEqual(summary(store.pendingEvents()), ["1:score=7", "1:putt=4", "1:penalty=1"])
        XCTAssertEqual(model.activeHole, 2)

        model.startEditingHole(1)
        XCTAssertEqual(draft(model), [7, 4, 1])
        model.setDraftScore(5)
        model.setDraftPutts(2)
        model.setDraftPenalty(2)
        XCTAssertEqual(draft(model), [5, 2, 2])
        model.saveManualScore()
        XCTAssertEqual(Array(summary(store.pendingEvents()).dropFirst(3)), ["1:putt=2", "1:score=5", "1:penalty=2"])

        model.startEditingHole(1)
        model.setDraftPenalty(1)
        model.setDraftScore(7)
        model.setDraftPutts(4)
        XCTAssertEqual(draft(model), [7, 4, 1])
        model.saveManualScore()
        XCTAssertEqual(Array(summary(store.pendingEvents()).dropFirst(6)), ["1:penalty=1", "1:score=7", "1:putt=4"])

        model.startEditingHole(1)
        model.saveManualScore()
        XCTAssertEqual(store.pendingEvents().count, 9, "an unchanged edit records nothing")

        // Replay the queue: every prefix is a possible card.
        var card = (score: 0, putts: 0, penalty: 0)
        for event in store.pendingEvents() {
            let value = try XCTUnwrap(Int(event.value))
            switch event.kind {
            case .score: card.score = value
            case .putt: card.putts = value
            case .penalty: card.penalty = value
            default: XCTFail("unexpected \(event.kind)")
            }
            if card.score > 0 {
                XCTAssertGreaterThanOrEqual(card.score, card.putts + card.penalty + 1, event.eventId)
            }
        }
        let hole = try XCTUnwrap(store.holeState(hole: 1))
        XCTAssertEqual([hole.score, hole.putts, hole.penaltyCount], [7, 4, 1])
        XCTAssertEqual(model.activeHole, 2, "editing a hole never moves the live-play cursor")
    }

    // MARK: - W-06 manual shots

    /// A manual shot stays undoable as 第 N 杆; with its club it records a club and a location event,
    /// and the next shot ends the previous shot's undo window with its location only.
    // goals: W-06 [main]
    func testManualShotsRecordClubAndLocationInShotOrder() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        let store = WatchRoundStore(directoryURL: dir)

        beginShot(model, at: "2026-06-20T00:01:00Z")
        XCTAssertEqual(model.undoableShotText, "第 1 杆")
        XCTAssertEqual(model.pendingManualShot?.shotType, "tee")
        XCTAssertEqual(model.pendingManualShot?.hole, 1)
        XCTAssertEqual(store.load()?.pendingManualShot?.shotNumber, 1, "the staged shot is durable")
        XCTAssertTrue(store.pendingEvents().isEmpty)

        model.completePendingManualShot(clubName: "Driver")
        XCTAssertNil(model.pendingManualShot)
        XCTAssertNil(model.undoableShotText)
        var events = store.pendingEvents()
        XCTAssertEqual(summary(events), ["1:club=Driver", "1:location=40.0,116.0,5.0"])
        XCTAssertEqual(events.first?.contextClub, "Driver")
        XCTAssertTrue(events.allSatisfy { $0.createdAt == "2026-06-20T00:01:00Z" && $0.shotType == "tee" })

        beginShot(model, at: "2026-06-20T00:02:00Z")
        XCTAssertEqual(model.undoableShotText, "第 2 杆")
        XCTAssertEqual(model.pendingManualShot?.shotType, "approach")

        beginShot(model, at: "2026-06-20T00:03:00Z")
        XCTAssertEqual(model.undoableShotText, "第 3 杆")
        events = store.pendingEvents()
        XCTAssertEqual(summary(events).count, 3)
        let second = try XCTUnwrap(events.last)
        XCTAssertEqual(second.kind, .location)
        XCTAssertEqual(second.createdAt, "2026-06-20T00:02:00Z")
        XCTAssertEqual(second.shotType, "approach")
        XCTAssertNil(second.contextClub)
        XCTAssertEqual(store.load()?.pendingManualShot?.shotNumber, 3)
    }

    /// Undo drops the staged shot without any event, so the next shot is again shot 1, the tee shot.
    // goals: W-06
    func testUndoDropsTheShotWithoutAnyEvent() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        let store = WatchRoundStore(directoryURL: dir)

        beginShot(model, at: "2026-06-20T00:01:00Z")
        model.undoPendingManualShot()

        XCTAssertNil(model.pendingManualShot)
        XCTAssertNil(store.load()?.pendingManualShot)
        XCTAssertTrue(store.pendingEvents().isEmpty)

        model.undoPendingManualShot()
        model.completePendingManualShot(clubName: "Driver")
        XCTAssertTrue(store.pendingEvents().isEmpty, "with nothing staged, undo and club do nothing")

        beginShot(model, at: "2026-06-20T00:02:00Z")
        XCTAssertEqual(model.undoableShotText, "第 1 杆")
        XCTAssertEqual(model.pendingManualShot?.shotType, "tee")
    }

    /// Finish is refused while a shot waits in its undo window; once it is undone the round can go
    /// to the finish confirmation.
    // goals: W-06
    func testPendingShotBlocksFinishUntilResolved() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        scoreActiveHole(model, score: 4)
        beginShot(model, at: "2026-06-20T00:05:00Z")
        XCTAssertEqual(model.pendingManualShot?.hole, 2)

        model.requestFinish()
        model.requestFinishConfirmation()
        XCTAssertEqual(model.uploadError, "请先确认或撤销未完成的一杆")
        XCTAssertEqual(model.screen, .finishing)

        model.undoPendingManualShot()
        model.requestFinishConfirmation()
        XCTAssertNil(model.uploadError)
        XCTAssertEqual(model.screen, .finishConfirmation)
        XCTAssertEqual(summary(WatchRoundStore(directoryURL: dir).pendingEvents()), ["1:score=4", "1:putt=2"])
    }

    /// The club name is trimmed, a blank club records the location only, and the recorded shots
    /// prefill the hole score (shots + two putts).
    // goals: W-06
    func testClubNameIsTrimmedAndBlankClubRecordsLocationOnly() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound(par: 5)
        let store = WatchRoundStore(directoryURL: dir)

        beginShot(model, at: "2026-06-20T00:01:00Z")
        model.completePendingManualShot(clubName: "  7 Iron \n")
        beginShot(model, at: "2026-06-20T00:02:00Z")
        model.completePendingManualShot(clubName: "   ")

        let events = store.pendingEvents()
        XCTAssertEqual(summary(events), [
            "1:club=7 Iron", "1:location=40.0,116.0,5.0", "1:location=40.0,116.0,5.0",
        ])
        XCTAssertEqual(events.first?.contextClub, "7 Iron")
        XCTAssertEqual(events.map(\.shotType), ["tee", "tee", "approach"])

        openActiveHoleScore(model)
        XCTAssertEqual(draft(model), [4, 2, 0], "two recorded shots plus two putts, not par")
    }

    // MARK: - W-07 scorecard

    /// The scorecard opens from the menu and returns there, showing exactly what the store holds.
    // goals: W-07 [main]
    func testScorecardShowsTheRecordedHolesAndReturnsToTheMenu() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        openActiveHoleScore(model)
        model.setDraftScore(6)
        model.setDraftPenalty(1)
        model.saveManualScore()
        scoreActiveHole(model, score: 3)

        model.openScorecard()
        XCTAssertEqual(model.screen, .scorecard)

        let store = WatchRoundStore(directoryURL: dir)
        let one = try XCTUnwrap(store.holeState(hole: 1))
        let two = try XCTUnwrap(store.holeState(hole: 2))
        XCTAssertEqual([one.score, one.putts, one.penaltyCount], [6, 2, 1])
        XCTAssertEqual([two.score, two.putts, two.penaltyCount], [3, 2, 0])
        XCTAssertEqual(store.holeState(hole: 3)?.score, 0)
        for hole in 1...3 {
            let shown = model.round?.holeStates.first { $0.hole == hole }
            let stored = store.holeState(hole: hole)
            XCTAssertEqual(shown?.score, stored?.score)
            XCTAssertEqual(shown?.putts, stored?.putts)
            XCTAssertEqual(shown?.penaltyCount, stored?.penaltyCount)
        }

        model.closeScorecard()
        XCTAssertEqual(model.screen, .menu)
        model.closeScorecard()
        XCTAssertEqual(model.screen, .menu, "close is ignored off the scorecard")
    }

    /// From the finish page the scorecard returns to finishing; from elsewhere that entry is ignored.
    // goals: W-07
    func testScorecardFromFinishReturnsToFinishing() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        scoreActiveHole(model, score: 5)

        model.openScorecardFromFinish()
        XCTAssertEqual(model.screen, .home)

        model.requestFinish()
        model.openScorecardFromFinish()
        XCTAssertEqual(model.screen, .scorecard)
        model.closeScorecard()
        XCTAssertEqual(model.screen, .finishing)
        model.requestFinishConfirmation()
        XCTAssertEqual(model.screen, .finishConfirmation)
    }

    /// Editing a hole from the scorecard saves it, returns to the scorecard and leaves the live-play
    /// cursor where it was.
    // goals: W-07
    func testEditingFromTheScorecardReturnsThereWithoutMovingTheCursor() throws {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound()
        scoreActiveHole(model, score: 4)
        scoreActiveHole(model, score: 5)
        XCTAssertEqual(model.activeHole, 3)

        model.openScorecard()
        model.startEditingHole(1)
        XCTAssertEqual(model.screen, .scoring)
        XCTAssertEqual(model.scoringHole, 1)
        XCTAssertEqual(draft(model), [4, 2, 0])
        model.setDraftScore(6)
        model.saveManualScore()

        XCTAssertEqual(model.screen, .scorecard)
        XCTAssertEqual(model.activeHole, 3)
        let store = WatchRoundStore(directoryURL: dir)
        XCTAssertEqual(store.holeState(hole: 1)?.score, 6)
        XCTAssertEqual(store.load()?.activeHole, 3)
        XCTAssertEqual(store.pendingEvents().last.map { "\($0.hole):\($0.kind.rawValue)=\($0.value)" }, "1:score=6")
    }

    /// Cancelling an edit from the scorecard records nothing; a hole the round does not have cannot
    /// be opened.
    // goals: W-07
    func testCancelledEditAndUnknownHoleLeaveTheScorecardUnchanged() {
        let dir = tempDirectory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let model = makeModel(dir, ids: sequentialIds())
        model.startPracticeRound(holeCount: 9)
        scoreActiveHole(model, score: 5)
        let store = WatchRoundStore(directoryURL: dir)
        let before = store.pendingEvents().count

        model.openScorecard()
        model.startEditingHole(1)
        model.setDraftScore(8)
        model.cancelScoring()

        XCTAssertEqual(model.screen, .scorecard)
        XCTAssertNil(model.scoringHole)
        XCTAssertEqual(store.pendingEvents().count, before)
        XCTAssertEqual(store.holeState(hole: 1)?.score, 5)
        XCTAssertNil(store.load()?.scoreDraft)

        model.startEditingHole(10)
        XCTAssertEqual(model.screen, .scorecard)
        XCTAssertNil(model.scoringHole)
    }
}
