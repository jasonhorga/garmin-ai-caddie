import XCTest
@testable import AICaddie

final class RoundBannerNoticeTests: XCTestCase {
    func testOnHoleNoticeNamesLocatedAndTargetHoles() {
        XCTAssertEqual(
            HoleScreenRoundBanner.notStartedNotice(
                .onHole(9), courseHoleNumber: { $0 }, targetCourseHole: 10
            ),
            "你在第 9 洞，到第 10 洞发球台再记"
        )
    }

    func testAwayAndPracticeNoticesKeepTheirSpecificCopy() {
        XCTAssertEqual(HoleScreenRoundBanner.notStartedNotice(.awayFromCourse), "没到场，备战不记录")
        XCTAssertEqual(
            HoleScreenRoundBanner.notStartedNotice(.atCourse),
            "练习场、会所里记杆不算开打，这一杆没有记录"
        )
    }
}
