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

    /// Owner feedback 2026-10-11: the in-chip wheel could not be operated on the wrist. The picker
    /// is full screen, a step is a deliberate 30 pt, and it stays open long enough to keep rolling.
    func testThePickerStepsDeliberatelyAndStaysOpenWhileTheGolferWorks() {
        // Rolling up brings the next number in.
        XCTAssertEqual(WatchScoreHoleLayout.wheelSteps(-60), 2)
        XCTAssertEqual(WatchScoreHoleLayout.wheelSteps(30), -1)
        XCTAssertEqual(WatchScoreHoleLayout.wheelSteps(10), 0, "a jitter is not a step")
        let limit = WatchScoreHoleLayout.wheelStepPoints * 0.6
        XCTAssertEqual(WatchScoreHoleLayout.wheelPeek(-400), -limit)
        XCTAssertEqual(WatchScoreHoleLayout.wheelPeek(400), limit)
        XCTAssertEqual(WatchScoreHoleLayout.wheelPeek(4), 2)
        XCTAssertLessThan(
            WatchScoreHoleLayout.wheelCloseDelayNanoseconds(settled: true),
            WatchScoreHoleLayout.wheelCloseDelayNanoseconds(settled: false)
        )
        XCTAssertGreaterThanOrEqual(WatchScoreHoleLayout.wheelCloseDelayNanoseconds(settled: true), 2_000_000_000,
                                    "never folds while the golfer is still between rolls")
        // The closed chips are a real tap target on every face.
        XCTAssertGreaterThanOrEqual(WatchScoreHoleLayout.Metrics.compact.chip, 36)
        XCTAssertGreaterThanOrEqual(WatchScoreHoleLayout.Metrics.regular.chip, 40)
    }
}
