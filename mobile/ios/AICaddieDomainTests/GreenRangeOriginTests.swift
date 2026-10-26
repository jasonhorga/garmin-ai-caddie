import XCTest
import AICaddieDomain

final class GreenRangeOriginTests: XCTestCase {
    // C71 / Jason's decision ⑧: before the first recorded shot, measure F/M/B from
    // the selected tee; preparation is also pre-shot. Only after a shot does GPS win.
    func testBeforeTeeShotUsesTeeEvenWithQualifiedGPS() {
        XCTAssertEqual(GreenRangeOrigin.resolve(
            recordedShotCount: 0, isPreparing: false, hasQualifiedFix: true
        ), .tee)
    }

    func testBeforeTeeShotWithoutGPSStillUsesTee() {
        XCTAssertEqual(GreenRangeOrigin.resolve(
            recordedShotCount: 0, isPreparing: false, hasQualifiedFix: false
        ), .tee)
    }

    func testAfterTeeShotUsesQualifiedGPS() {
        for count in [1, 2, 5] {
            XCTAssertEqual(GreenRangeOrigin.resolve(
                recordedShotCount: count, isPreparing: false, hasQualifiedFix: true
            ), .liveGPS)
        }
    }

    func testAfterTeeShotUnqualifiedOrMissingGPSKeepsExistingFallback() {
        for count in [1, 2, 5] {
            XCTAssertEqual(GreenRangeOrigin.resolve(
                recordedShotCount: count, isPreparing: false, hasQualifiedFix: false
            ), .fallback)
        }
    }

    func testPreparationUsesTeeRegardlessOfGPSOrRecordedShots() {
        for hasFix in [true, false] {
            for count in [0, 1] {
                XCTAssertEqual(GreenRangeOrigin.resolve(
                    recordedShotCount: count, isPreparing: true, hasQualifiedFix: hasFix
                ), .tee)
            }
        }
    }
}
