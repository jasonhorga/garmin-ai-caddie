import XCTest
@testable import AICaddie

final class RoundPlayOrderTests: XCTestCase {
    func testFrontNineStartingAtFiveWrapsAtNine() {
        XCTAssertEqual(RoundPlayOrder.holes(Array(1...9), startingAt: 5), [5, 6, 7, 8, 9, 1, 2, 3, 4])
    }

    func testTwentySevenHolePackageUsesItsTableOrder() {
        let table = [1, 2, 3, 10, 11, 12, 4, 5, 6]
        XCTAssertEqual(RoundPlayOrder.holes(table, startingAt: 10), [10, 11, 12, 4, 5, 6, 1, 2, 3])
    }

    func testFrontAndBackLoopsStartingAtFiveRotateTheWholeRound() {
        let loops = RoundLoopEntry.table([
            RoundLoopEntry(globalId: 1, half: "front"),
            RoundLoopEntry(globalId: 1, half: "back")
        ])
        let order = RoundPlayOrder.holes(Array(1...18), startingAt: 5, loops: loops)
        XCTAssertEqual(order, [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 1, 2, 3, 4])
        XCTAssertEqual(order.count, 18)
        XCTAssertEqual(Set(order).count, 18)
        XCTAssertEqual(RoundPlayOrder.next(after: 18, in: Array(1...18), startingAt: 5, loops: loops), 1)
        XCTAssertNil(RoundPlayOrder.next(after: 4, in: Array(1...18), startingAt: 5, loops: loops))
    }

    func testSecondNineAfterFirstNineEndsAfterHole18() {
        let loops = RoundLoopEntry.table([
            RoundLoopEntry(globalId: 1, half: "all"),
            RoundLoopEntry(globalId: 1, half: "all")
        ])
        let order = RoundPlayOrder.holes(Array(1...18), startingAt: 5, loops: loops)
        XCTAssertEqual(order, [5, 6, 7, 8, 9, 1, 2, 3, 4, 10, 11, 12, 13, 14, 15, 16, 17, 18])
        XCTAssertEqual(order.count, 18)
        XCTAssertEqual(Set(order).count, 18)
        XCTAssertNil(
            RoundPlayOrder.next(after: 18, in: Array(1...18), startingAt: 5, loops: loops),
            "the second nine completes at round hole 18 and must not revisit hole 1"
        )
        XCTAssertEqual(
            RoundPlayOrder.next(after: 9, in: Array(1...18), startingAt: 5, loops: loops),
            1
        )
        XCTAssertEqual(
            RoundPlayOrder.next(after: 4, in: Array(1...18), startingAt: 5, loops: loops),
            10
        )
    }

    func testPrepPathKeepsPickerWhileAdvancingAndLivePathDropsItAfterStart() {
        XCTAssertEqual(
            LiveHoleRoutePath.afterAdvance(current: [.prep, .hole(5)], nextHole: 6, isPrepMode: true),
            [.prep, .hole(6)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.afterAdvance(current: [.prep, .hole(5)], nextHole: 6, isPrepMode: false),
            [.hole(6)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.afterPrepPackageRefresh(current: [.prep], pendingHole: nil),
            [.prep]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.forPendingHole(current: [.prep], hole: 5, isPrepMode: true),
            [.prep, .hole(5)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.forPendingHole(current: [.prep, .hole(5)], hole: 5, isPrepMode: false),
            [.hole(5)]
        )
    }

    func testHoleNavigationLockDropsFastSecondAdvanceAndStaleSource() {
        var lock = LiveHoleNavigationLock(currentHole: 3)
        XCTAssertTrue(lock.begin(from: 3, to: 2))
        XCTAssertFalse(lock.begin(from: 3, to: 1), "the first transition is still in flight")
        XCTAssertFalse(lock.begin(from: 9, to: 1), "a stale page cannot advance the current page")
        lock.finish(at: 2)
        XCTAssertTrue(lock.begin(from: 2, to: 1))
    }

    func testGarminDescriptorNeedsDecodedImageBeforeRasterState() {
        let descriptor = GarminRasterResponse(available: true, imageUrl: "/raster.webp")
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(.init(
                coverage: "partial", preciseTopoImageReady: false, garminRaster: descriptor,
                garminImageReady: false, garminImageFailed: false, hasCachedPreciseTopo: false
            )),
            .numericPlaceholder
        )
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(.init(
                coverage: "partial", preciseTopoImageReady: false, garminRaster: descriptor,
                garminImageReady: true, garminImageFailed: false, hasCachedPreciseTopo: false
            )),
            .garminRaster
        )
    }

    func testBannerRejectsPracticeAreaStroke() {
        XCTAssertEqual(
            HoleScreenRoundBanner.notStartedNotice(.atCourse),
            "练习场、会所里记杆不算开打，这一杆没有记录"
        )
    }
}
