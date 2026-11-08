// size: small
// goals: W-04, W-10
import AICaddieCore
import XCTest

/// W-04: Hole Root draws only a live, measured, internally consistent recommendation;
/// W-10: an expired window, a stale or inaccurate fix, or a player who has walked away hides it.
final class RootAdviceTrustTests: XCTestCase {
    private let now = "2026-11-08T10:01:00Z"
    private let originLatitude = 31.25
    private let originLongitude = 121.5

    private func recommendation(
        aimCarryM: Double = 150,
        carryP10M: Double = 140,
        carryP90M: Double = 160,
        sampleSize: Int = 12,
        confidence: String = "high",
        source: String = "live",
        mode: String = "automatic",
        generatedAt: String = "2026-11-08T10:00:00Z",
        validUntil: String = "2026-11-08T10:05:00Z",
        originAccuracyM: Double = 5,
        maximumMovementM: Double = 20,
        evidenceCount: Int = 3
    ) -> WatchRootCaddieRecommendation {
        WatchRootCaddieRecommendation(
            decisionId: "d-1",
            clubName: "7I",
            aimCarryM: aimCarryM,
            carryP10M: carryP10M,
            carryP90M: carryP90M,
            sampleSize: sampleSize,
            confidence: confidence,
            source: source,
            mode: mode,
            generatedAt: generatedAt,
            validUntil: validUntil,
            originLatitude: originLatitude,
            originLongitude: originLongitude,
            originAccuracyM: originAccuracyM,
            maximumMovementM: maximumMovementM,
            evidenceCount: evidenceCount
        )
    }

    private func trusted(
        _ recommendation: WatchRootCaddieRecommendation,
        fixLatitude: Double? = nil,
        fixLongitude: Double? = nil,
        fixAccuracyM: Double = 5,
        fixCapturedAt: String = "2026-11-08T10:00:50Z",
        now: String? = nil
    ) -> Bool {
        RootCaddieAdviceTrust.isTrusted(
            recommendation,
            fixLatitude: fixLatitude ?? originLatitude,
            fixLongitude: fixLongitude ?? originLongitude,
            fixAccuracyM: fixAccuracyM,
            fixCapturedAt: fixCapturedAt,
            now: now ?? self.now
        )
    }

    // goals: W-04
    func testFreshMeasuredLiveRecommendationIsTrusted() {
        XCTAssertTrue(trusted(recommendation()))
        XCTAssertTrue(trusted(recommendation(sampleSize: 10, confidence: "medium", mode: "manual")))
    }

    // goals: W-04
    func testUnmeasuredOrNonLiveRecommendationIsHidden() {
        XCTAssertFalse(trusted(recommendation(source: "fallback")))
        XCTAssertFalse(trusted(recommendation(mode: "preview")))
        XCTAssertFalse(trusted(recommendation(confidence: "low")))
        XCTAssertFalse(trusted(recommendation(sampleSize: 9)))
        XCTAssertFalse(trusted(recommendation(evidenceCount: 0)))
    }

    // goals: W-04
    func testInconsistentCarryRangeIsHidden() {
        XCTAssertFalse(trusted(recommendation(aimCarryM: 170)), "aim beyond p90")
        XCTAssertFalse(trusted(recommendation(aimCarryM: 130)), "aim short of p10")
        XCTAssertFalse(trusted(recommendation(carryP10M: 0)))
        XCTAssertFalse(trusted(recommendation(aimCarryM: .nan)))
        XCTAssertFalse(trusted(recommendation(carryP10M: 160, carryP90M: 140)))
    }

    // goals: W-10
    func testRecommendationOutsideItsWindowIsHidden() {
        XCTAssertFalse(trusted(recommendation(validUntil: "2026-11-08T10:01:00Z")), "window closes at now")
        XCTAssertFalse(trusted(recommendation(generatedAt: "2026-11-08T10:01:10Z")), "generated in the future")
        XCTAssertFalse(
            trusted(recommendation(generatedAt: "2026-11-08T10:05:00Z", validUntil: "2026-11-08T10:05:00Z"))
        )
        XCTAssertFalse(trusted(recommendation(validUntil: "not-a-date")))
    }

    // goals: W-10
    func testStaleFutureOrInaccurateFixIsHidden() {
        XCTAssertTrue(trusted(recommendation(), fixCapturedAt: "2026-11-08T10:00:45Z"), "15 s old is still fresh")
        XCTAssertFalse(trusted(recommendation(), fixCapturedAt: "2026-11-08T10:00:44Z"), "16 s old is stale")
        XCTAssertFalse(trusted(recommendation(), fixCapturedAt: "2026-11-08T10:01:01Z"), "fix from the future")
        XCTAssertTrue(trusted(recommendation(), fixAccuracyM: 15))
        XCTAssertFalse(trusted(recommendation(), fixAccuracyM: 15.5))
        XCTAssertFalse(trusted(recommendation(), fixAccuracyM: -1))
        XCTAssertFalse(trusted(recommendation(), fixLatitude: 95))
        XCTAssertFalse(trusted(recommendation(originAccuracyM: 16)))
    }

    // goals: W-10
    func testPlayerWhoMovedBeyondTheOriginWindowLosesTheAdvice() {
        // 0.0001° of latitude is about 11.1 m.
        XCTAssertTrue(trusted(recommendation(), fixLatitude: originLatitude + 0.0001))
        XCTAssertFalse(trusted(recommendation(), fixLatitude: originLatitude + 0.0003))
        XCTAssertFalse(trusted(recommendation(maximumMovementM: 0)))
    }

    // goals: W-10
    func testDistanceIsGreatCircleMetres() {
        XCTAssertEqual(WatchGeoDistance.metres(0, 0, 0, 0), 0)
        XCTAssertEqual(WatchGeoDistance.metres(0, 0, 1, 0), 111_195, accuracy: 1)
    }
}
