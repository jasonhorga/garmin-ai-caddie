import XCTest
@testable import AICaddie

final class RoundReviewMetricsTests: XCTestCase {
    func testFairwayDenominatorExcludesUnknownAndMissingValues() {
        XCTAssertEqual(roundReviewFairwayOutcome("hit"), true)
        XCTAssertEqual(roundReviewFairwayOutcome("left"), false)
        XCTAssertNil(roundReviewFairwayOutcome("unknown"))
        XCTAssertNil(roundReviewFairwayOutcome("future-token"))
        XCTAssertNil(roundReviewFairwayOutcome(""))
        XCTAssertNil(roundReviewFairwayOutcome(nil))

        let counts = roundReviewFairwayCounts(["hit", "unknown", nil, "0"])
        XCTAssertEqual(counts.hit, 1)
        XCTAssertEqual(counts.recorded, 2)
    }

    func testFairwayLabelsDistinguishRecordedZeroFromUnknown() {
        XCTAssertEqual(roundReviewFairwayLabel("0"), "球道✗")
        XCTAssertEqual(roundReviewFairwayLabel("unknown"), "未记录")
        XCTAssertEqual(roundReviewFairwayLabel(nil), "未记录")
    }
}
