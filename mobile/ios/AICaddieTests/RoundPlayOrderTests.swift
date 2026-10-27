import XCTest
@testable import AICaddie

final class RoundPlayOrderTests: XCTestCase {
    func testQuickCourseShortcutUsesStartCourseRoute() {
        let option = MobileCourseOption(globalId: 31795, name: "北京丽宫", teeBox: "White")
        XCTAssertEqual(
            RoundHomeView.quickCourseRoute(for: option),
            .startCourse(globalId: 31795, teeBox: "White")
        )
    }

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
            LiveHoleRoutePath.afterAdvance(current: [.startCourse(globalId: 1, teeBox: nil), .hole(5)], nextHole: 6, isPrepMode: true),
            [.startCourse(globalId: 1, teeBox: nil), .hole(6)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.afterAdvance(current: [.startCourse(globalId: 1, teeBox: nil), .hole(5)], nextHole: 6, isPrepMode: false),
            [.hole(6)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.afterPrepPackageRefresh(current: [.startCourse(globalId: 1, teeBox: nil)], pendingHole: nil),
            [.startCourse(globalId: 1, teeBox: nil)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.forPendingHole(current: [.startCourse(globalId: 1, teeBox: nil)], hole: 5, isPrepMode: true),
            [.startCourse(globalId: 1, teeBox: nil), .hole(5)]
        )
        XCTAssertEqual(
            LiveHoleRoutePath.forPendingHole(current: [.startCourse(globalId: 1, teeBox: nil), .hole(5)], hole: 5, isPrepMode: false),
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
