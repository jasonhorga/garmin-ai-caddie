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

    func testBannerRejectsPracticeAreaStroke() {
        XCTAssertEqual(
            HoleScreenRoundBanner.notStartedNotice(.atCourse),
            "练习场、会所里记杆不算开打，这一杆没有记录"
        )
    }
}
