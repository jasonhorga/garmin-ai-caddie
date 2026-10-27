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
}
