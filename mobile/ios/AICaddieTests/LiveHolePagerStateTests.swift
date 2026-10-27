import XCTest
@testable import AICaddie

final class LiveHolePagerStateTests: XCTestCase {
    func testFrontNineTurnRejectsLateRoundHoleNineFromTheReusedPager() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...9), activeHole: 9))
        pager.send(.bindingReported(9))
        // Saving 9 closes the score sheet, then turn-go publishes the enlarged package and cursor.
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 9))
        pager.send(.programmaticHole(10))
        let late = pager.send(.bindingReported(9))
        XCTAssertEqual(pager.activeHole, 10)
        XCTAssertEqual(pager.selection, 10)
        XCTAssertEqual(pager.pendingTarget, 10)
        XCTAssertEqual(late.forceScrollTo, 10)
        XCTAssertNil(late.activeHoleToPersist)
        pager.send(.bindingReported(10))
        XCTAssertNil(pager.pendingTarget)
        // Even after acknowledgement, a report without a user intent cannot move the cursor.
        let later = pager.send(.bindingReported(9))
        XCTAssertEqual(pager.activeHole, 10)
        XCTAssertEqual(later.forceScrollTo, 10)
        XCTAssertNil(later.activeHoleToPersist)
    }

    func testBackNineTurnUsesRoundHoleTenWhichIsCourseHoleOne() {
        var pager = LiveHolePagerState()
        // Round holes 1...9 display course holes 10...18; after the turn 10...18 display 1...9.
        let courseHoles = Array(10...18) + Array(1...9)
        pager.send(.pageSetChanged(ordered: Array(1...9), activeHole: 9))
        pager.send(.bindingReported(9))
        XCTAssertEqual(courseHoles[pager.activeHole! - 1], 18)
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 9))
        pager.send(.programmaticHole(10))
        let late = pager.send(.bindingReported(9))
        XCTAssertEqual(pager.activeHole, 10)
        XCTAssertEqual(pager.selection, 10)
        XCTAssertEqual(courseHoles[pager.activeHole! - 1], 1)
        XCTAssertEqual(late.forceScrollTo, 10)
        XCTAssertNil(late.activeHoleToPersist)
    }

    func testAddChangeAndRemoveSecondLoopRetainHoleSix() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...9), activeHole: 6))
        // Add, change physical second loop (same round-hole table), then remove it.
        for holes in [Array(1...18), Array(1...18), Array(1...9)] {
            let update = pager.send(.pageSetChanged(ordered: holes, activeHole: 6))
            XCTAssertEqual(pager.activeHole, 6)
            XCTAssertEqual(pager.selection, 6)
            XCTAssertNil(update.activeHoleToPersist)
            let lateEntryPage = pager.send(.bindingReported(1))
            XCTAssertEqual(pager.activeHole, 6)
            XCTAssertEqual(pager.selection, 6)
            XCTAssertEqual(lateEntryPage.forceScrollTo, 6)
        }
    }

    func testOnlyCompletedUserSwipePersistsHoleSeven() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 6))
        pager.send(.bindingReported(6))
        pager.send(.touchBegan)
        // UIKit may report the destination before our simultaneous DragGesture ends.
        let report = pager.send(.bindingReported(7))
        XCTAssertNil(report.activeHoleToPersist)
        XCTAssertEqual(pager.activeHole, 6)
        let swipe = pager.send(.touchEnded(step: 1))
        XCTAssertEqual(swipe.activeHoleToPersist, 7)
        XCTAssertEqual(pager.activeHole, 7)
        XCTAssertEqual(pager.selection, 7)
        pager.send(.bindingReported(7))
        XCTAssertNil(pager.pendingTarget)
        pager.send(.touchBegan)
        let back = pager.send(.touchEnded(step: -1))
        XCTAssertEqual(pager.activeHole, 6)
        XCTAssertEqual(back.activeHoleToPersist, 6)
    }

    func testUserSwipeCanCommitWhileAnEarlierProgrammaticDisplayIsAwaitingAcknowledgement() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 6))
        pager.send(.touchBegan)
        // A pending target still rejects the report; the explicit finger-up intent can replace it.
        let report = pager.send(.bindingReported(7))
        XCTAssertEqual(pager.activeHole, 6)
        XCTAssertEqual(pager.selection, 6)
        XCTAssertEqual(report.forceScrollTo, 6)
        XCTAssertNil(report.activeHoleToPersist)
        let end = pager.send(.touchEnded(step: 1))
        XCTAssertEqual(pager.activeHole, 7)
        XCTAssertEqual(pager.selection, 7)
        XCTAssertEqual(end.activeHoleToPersist, 7)
        XCTAssertNil(pager.pendingTarget)
    }

    func testMapTakingOwnershipBeforeAnyPagerReportDoesNotRebuildItsDragSurface() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 6))
        pager.send(.touchBegan)
        let mapOwnsTouch = pager.send(.touchEnded(step: 0))
        XCTAssertNil(mapOwnsTouch.activeHoleToPersist)
        XCTAssertNil(mapOwnsTouch.forceScrollTo)
        XCTAssertEqual(pager.activeHole, 6)
        XCTAssertNil(pager.touchOrigin)
    }

    func testCancelledSwipeAndProgrammaticMoveInvalidateAnOldTouch() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 6))
        pager.send(.bindingReported(6))
        pager.send(.touchBegan)
        pager.send(.bindingReported(7))
        let cancelled = pager.send(.touchEnded(step: 0))
        XCTAssertEqual(pager.activeHole, 6)
        XCTAssertEqual(cancelled.forceScrollTo, 6)
        XCTAssertNil(cancelled.activeHoleToPersist)
        pager.send(.touchBegan)
        let advance = pager.send(.advance(10))
        XCTAssertEqual(advance.activeHoleToPersist, 10)
        XCTAssertNil(pager.send(.touchEnded(step: -1)).activeHoleToPersist)
        XCTAssertEqual(pager.activeHole, 10)
    }
    func testProgrammaticTargetCannotReuseAReportFromBeforeTheTouch() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 7))
        pager.send(.bindingReported(7))
        pager.send(.programmaticHole(6))
        XCTAssertNil(pager.reportedSelection, "the report belongs to the previous programmatic target")
        pager.send(.touchBegan)
        pager.send(.touchEnded(step: 1))
        XCTAssertEqual(pager.activeHole, 7)
        XCTAssertEqual(pager.pendingTarget, 7, "no report from this touch acknowledged the new target")
    }

    func testPageSetRejectsAnActiveHoleThatWasRemoved() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 15))
        pager.send(.pageSetChanged(ordered: Array(1...9), activeHole: 15))
        XCTAssertEqual(pager.activeHole, 1)
        XCTAssertEqual(pager.selection, 1)
        XCTAssertEqual(pager.pendingTarget, 1)
        pager.send(.pageSetChanged(ordered: [], activeHole: 1))
        XCTAssertNil(pager.activeHole)
        XCTAssertNil(pager.selection)
        XCTAssertNil(pager.pendingTarget)
    }

    func testThreeCorrectionsAtTheSameTargetThenStopUntilAcknowledged() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 10))
        for _ in 1...3 {
            XCTAssertEqual(pager.send(.bindingReported(9)).forceScrollTo, 10)
            // A repeat publication of the same target must not reset the safety budget.
            pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 10))
        }
        XCTAssertNil(pager.send(.bindingReported(9)).forceScrollTo)
        XCTAssertEqual(pager.activeHole, 10)
        pager.send(.bindingReported(10))
        XCTAssertEqual(pager.send(.bindingReported(9)).forceScrollTo, 10)
    }

    func testSheetDefersCorrectionsAcrossScoreTurnAndSummaryHandoffs() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...9), activeHole: 9))
        pager.send(.presentationChanged(true))
        for _ in 1...5 {
            XCTAssertNil(pager.send(.bindingReported(8)).forceScrollTo)
        }
        XCTAssertEqual(pager.activeHole, 9)
        XCTAssertEqual(pager.send(.presentationChanged(false)).forceScrollTo, 9)
        XCTAssertNil(pager.send(.presentationChanged(false)).forceScrollTo, "one dismissal, one retry")
    }

    func testReversedPredictionCancelsEvenALongDragAndMapOwnershipAlwaysWins() {
        XCTAssertEqual(LiveHolePagerState.swipeStep(
            translationX: -80, translationY: 5, predictedX: 120, scrollDisabled: false
        ), 0)
        XCTAssertEqual(LiveHolePagerState.swipeStep(
            translationX: -20, translationY: 5, predictedX: -120, scrollDisabled: false
        ), 1)
        XCTAssertEqual(LiveHolePagerState.swipeStep(
            translationX: 80, translationY: 5, predictedX: 120, scrollDisabled: false
        ), -1)
        XCTAssertEqual(LiveHolePagerState.swipeStep(
            translationX: -80, translationY: 5, predictedX: -120, scrollDisabled: true
        ), 0)
    }

    func testClosingASheetWithoutAMismatchingReportDoesNotBounceTheDisplay() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...18), activeHole: 10))
        pager.send(.presentationChanged(true))
        XCTAssertNil(pager.send(.presentationChanged(false)).forceScrollTo)
        XCTAssertEqual(pager.correctionAttempts, 0)
    }

    func testPageSetRotationWaitsForPresentedSheetThenCorrectsToTheActiveHole() {
        var pager = LiveHolePagerState()
        pager.send(.pageSetChanged(ordered: Array(1...9), activeHole: 9))
        pager.send(.bindingReported(9))
        pager.send(.presentationChanged(true))

        let deferred = pager.send(.pageSetChanged(ordered: Array(10...18) + Array(1...9), activeHole: 10))
        XCTAssertEqual(pager.ordered, Array(1...9))
        XCTAssertEqual(pager.activeHole, 10)
        XCTAssertEqual(pager.deferredOrdered, Array(10...18) + Array(1...9))
        XCTAssertNil(deferred.forceScrollTo)

        pager.send(.bindingReported(9))
        let applied = pager.send(.presentationChanged(false))
        XCTAssertEqual(pager.ordered, Array(10...18) + Array(1...9))
        XCTAssertEqual(pager.activeHole, 10)
        XCTAssertEqual(applied.forceScrollTo, 10)
        XCTAssertNil(pager.deferredOrdered)
    }

    func testScorecardJumpWhilePageSetIsCachedPersistsAndSurvivesDismissal() {
        // Add a loop from the open scorecard, then jump to a hole that only exists in the new set.
        var added = LiveHolePagerState()
        added.send(.pageSetChanged(ordered: Array(1...9), activeHole: 6))
        added.send(.presentationChanged(true))
        added.send(.pageSetChanged(ordered: Array(1...18), activeHole: 6))
        XCTAssertEqual(added.send(.advance(12)).activeHoleToPersist, 12)
        added.send(.presentationChanged(false))
        XCTAssertEqual(added.ordered, Array(1...18))
        XCTAssertEqual(added.activeHole, 12)

        // Remove a nine from the open scorecard, then jump back: dismissal keeps the jump.
        var removed = LiveHolePagerState()
        removed.send(.pageSetChanged(ordered: Array(1...18), activeHole: 6))
        removed.send(.presentationChanged(true))
        removed.send(.pageSetChanged(ordered: Array(1...9), activeHole: 6))
        XCTAssertEqual(removed.send(.advance(3)).activeHoleToPersist, 3)
        removed.send(.presentationChanged(false))
        XCTAssertEqual(removed.ordered, Array(1...9))
        XCTAssertEqual(removed.activeHole, 3)
    }

    func testRestoredTargetAcknowledgesAReportsAfterInitialSelectionWasUnset() {
        var pager = LiveHolePagerState()
        pager.send(.programmaticHole(10))
        XCTAssertNil(pager.reportedSelection)
        XCTAssertEqual(pager.pendingTarget, 10)
        let acknowledgement = pager.send(.bindingReported(10))
        XCTAssertNil(acknowledgement.forceScrollTo)
        XCTAssertEqual(pager.activeHole, 10)
        XCTAssertEqual(pager.selection, 10)
        XCTAssertNil(pager.pendingTarget)
    }

}
