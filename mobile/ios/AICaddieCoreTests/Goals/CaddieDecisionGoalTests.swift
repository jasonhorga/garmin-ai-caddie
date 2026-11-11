// size: small
// goals: I-07

import AICaddieCore
import XCTest

final class CaddieDecisionGoalTests: XCTestCase {
    private let now = "2026-11-08T10:01:00Z"

    private func recommendation(
        aim: Double = 150, p10: Double = 140, p90: Double = 160,
        sample: Int = 12, confidence: String = "high", source: String = "live",
        mode: String = "automatic", generated: String = "2026-11-08T10:00:00Z",
        valid: String = "2026-11-08T10:05:00Z", accuracy: Double = 5,
        movement: Double = 20, evidence: Int = 3
    ) -> WatchRootCaddieRecommendation {
        WatchRootCaddieRecommendation(decisionId: "d", clubName: "7I", aimCarryM: aim, carryP10M: p10, carryP90M: p90, sampleSize: sample, confidence: confidence, source: source, mode: mode, generatedAt: generated, validUntil: valid, originLatitude: 31.25, originLongitude: 121.5, originAccuracyM: 5, maximumMovementM: movement, evidenceCount: evidence)
    }

    private func trusted(_ r: WatchRootCaddieRecommendation, lat: Double = 31.25, accuracy: Double = 5, captured: String = "2026-11-08T10:00:50Z") -> Bool {
        RootCaddieAdviceTrust.isTrusted(r, fixLatitude: lat, fixLongitude: 121.5, fixAccuracyM: accuracy, fixCapturedAt: captured, now: now)
    }

    // goals: I-07 [main]
    func testFreshMeasuredRecommendationIsTrusted() {
        XCTAssertTrue(trusted(recommendation()))
    }

    // goals: I-07
    func testUnmeasuredRecommendationIsHidden() {
        XCTAssertFalse(trusted(recommendation(source: "fallback")))
        XCTAssertFalse(trusted(recommendation(confidence: "low")))
        XCTAssertFalse(trusted(recommendation(sample: 9)))
        XCTAssertFalse(trusted(recommendation(evidence: 0)))
    }

    // goals: I-07
    func testInvalidCarryRangeIsHidden() {
        XCTAssertFalse(trusted(recommendation(aim: 170)))
        XCTAssertFalse(trusted(recommendation(p10: 160, p90: 140)))
        XCTAssertFalse(trusted(recommendation(aim: .nan)))
        XCTAssertFalse(trusted(recommendation(movement: 0)))
    }

    // goals: I-07
    func testExpiredOrFutureRecommendationIsHidden() {
        XCTAssertFalse(trusted(recommendation(valid: "2026-11-08T10:01:00Z")))
        XCTAssertFalse(trusted(recommendation(generated: "2026-11-08T10:01:10Z")))
        XCTAssertFalse(trusted(recommendation(valid: "not-a-date")))
    }

    // goals: I-07
    func testStaleInaccurateOrMovedFixIsHidden() {
        XCTAssertFalse(trusted(recommendation(), accuracy: 15.1))
        XCTAssertFalse(trusted(recommendation(), captured: "2026-11-08T10:00:44Z"))
        XCTAssertFalse(trusted(recommendation(), lat: 31.2503))
    }
}
