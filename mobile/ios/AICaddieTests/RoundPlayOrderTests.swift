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
        XCTAssertEqual(
            RoundPlayOrder.holes(Array(1...18), startingAt: 5, loops: loops),
            [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
        )
    }

    func testSecondNineAfterFirstNineEndsAfterHole18() {
        let loops = RoundLoopEntry.table([
            RoundLoopEntry(globalId: 1, half: "all"),
            RoundLoopEntry(globalId: 1, half: "all")
        ])
        XCTAssertEqual(
            RoundPlayOrder.holes(Array(1...18), startingAt: 5, loops: loops),
            [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 1, 2, 3, 4]
        )
        XCTAssertNil(
            RoundPlayOrder.next(after: 18, in: Array(1...18), startingAt: 5, loops: loops),
            "the second nine completes at round hole 18 and must not revisit hole 1"
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
            LiveHoleRoutePath.forPendingHole(current: [.prep], hole: 5, isPrepMode: true),
            [.prep, .hole(5)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.forPendingHole(current: [.prep, .hole(5)], hole: 5, isPrepMode: false),
            [.hole(5)]
        )
    }

    func testBannerRejectsPracticeAreaStroke() {
        XCTAssertEqual(
            HoleScreenRoundBanner.notStartedNotice(.atCourse),
            "练习场、会所里记杆不算开打，这一杆没有记录"
        )
    }
}
