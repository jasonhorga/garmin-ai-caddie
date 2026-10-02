import XCTest
@testable import AICaddieWatch

/// B6 本洞成绩 must fit every supported Watch, the 40 mm / 41 mm cases included (Codex review on
/// #367: the 41 mm capture cut 保存 off).
final class WatchScoreHoleLayoutTests: XCTestCase {
    func testTheOneScreenScoreFitsEverySupportedWatchHeight() {
        // Content heights in points: 40 mm, 41 mm, 44 mm, 45 mm, 49 mm.
        for height in [197.0, 215.0, 224.0, 242.0, 251.0] as [CGFloat] {
            let metrics = WatchScoreHoleLayout.metrics(forHeight: height)
            for showsFairway in [true, false] {
                XCTAssertLessThanOrEqual(
                    WatchScoreHoleLayout.requiredHeight(metrics, showsFairway: showsFairway), height,
                    "\(height) pt, fairway \(showsFairway)"
                )
            }
        }
        XCTAssertEqual(WatchScoreHoleLayout.metrics(forHeight: 215), .compact)
        XCTAssertEqual(WatchScoreHoleLayout.metrics(forHeight: 242), .regular)
    }

    func testTheTotalBandFollowsHorizontalAndVerticalDrags() {
        // Drag left or up brings bigger numbers to the middle.
        XCTAssertEqual(WatchScoreHoleLayout.bandSteps(CGSize(width: -56, height: 4)), 2)
        XCTAssertEqual(WatchScoreHoleLayout.bandSteps(CGSize(width: 28, height: -3)), -1)
        XCTAssertEqual(WatchScoreHoleLayout.bandSteps(CGSize(width: 2, height: -56)), 2, "上下拖也可")
        XCTAssertEqual(WatchScoreHoleLayout.bandSteps(CGSize(width: -4, height: 28)), -1)
    }

    func testTheInlineWheelStaysInsideItsChipAndFoldsBackOnceSettled() {
        // Rolling up brings the next number in.
        XCTAssertEqual(WatchScoreHoleLayout.wheelSteps(-44), 2)
        XCTAssertEqual(WatchScoreHoleLayout.wheelSteps(22), -1)
        XCTAssertEqual(WatchScoreHoleLayout.wheelSteps(5), 0)
        // The digits only peek: never past the chip's own edge on any face.
        for metrics in [WatchScoreHoleLayout.Metrics.regular, .compact] {
            let limit = metrics.chip * 0.22
            XCTAssertEqual(WatchScoreHoleLayout.wheelPeek(-400, chip: metrics.chip), -limit)
            XCTAssertEqual(WatchScoreHoleLayout.wheelPeek(400, chip: metrics.chip), limit)
            XCTAssertEqual(WatchScoreHoleLayout.wheelPeek(3, chip: metrics.chip), 1)
        }
        // 停手即选定并收起: a settled roll folds back sooner than a merely open wheel.
        XCTAssertLessThan(
            WatchScoreHoleLayout.wheelCloseDelayNanoseconds(settled: true),
            WatchScoreHoleLayout.wheelCloseDelayNanoseconds(settled: false)
        )
        XCTAssertLessThanOrEqual(WatchScoreHoleLayout.wheelCloseDelayNanoseconds(settled: true), 500_000_000)
    }
}
