import XCTest
@testable import AICaddieWatch

/// 本洞成绩 layout B (#422): every row fits between the clock band and the bottom inset.
final class WatchScoreHoleLayoutTests: XCTestCase {
    func testEveryRowFitsBetweenTheClockBandAndTheBottomInsetOnEveryFace() {
        // 40 / 41 / 42 / 45 / 46 / 49 mm window heights.
        for height: CGFloat in [197, 215, 223, 242, 248, 251] {
            let available = height - WatchFaceInsets.top(forHeight: height) - WatchFaceInsets.bottom(forHeight: height)
                - WatchScoreHoleLayout.bottomClearance
            let row = WatchScoreHoleLayout.rowHeight(available: available)
            XCTAssertLessThanOrEqual(row * 4 + WatchScoreHoleLayout.gap * 3, available + 0.5, "\(height)")
            XCTAssertGreaterThanOrEqual(row, 28, "\(height)")
        }
        XCTAssertEqual(WatchScoreHoleLayout.rowHeight(available: 139), 31.75, accuracy: 0.01, "41 mm")
    }
}
