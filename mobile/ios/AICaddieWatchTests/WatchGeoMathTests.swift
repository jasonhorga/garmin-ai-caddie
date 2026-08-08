import CoreGraphics
import XCTest
@testable import AICaddieWatch

final class WatchGeoMathTests: XCTestCase {
    func testProjectToTopoPxMapsRefsAndMidpoint() {
        // Unit square: (lon,lat) → (px,py) with lon→x×100, lat→y×100.
        let refs = [
            WatchProjectionRef(lat: 0, lon: 0, px: 0, py: 0),
            WatchProjectionRef(lat: 0, lon: 1, px: 100, py: 0),
            WatchProjectionRef(lat: 1, lon: 0, px: 0, py: 100),
        ]
        let mid = WatchGeoMath.projectToTopoPx(lat: 0.5, lon: 0.5, refs: refs)
        XCTAssertEqual(mid?.x ?? -1, 50, accuracy: 0.001)
        XCTAssertEqual(mid?.y ?? -1, 50, accuracy: 0.001)
        let r1 = WatchGeoMath.projectToTopoPx(lat: 0, lon: 1, refs: refs)
        XCTAssertEqual(r1?.x ?? -1, 100, accuracy: 0.001)
        XCTAssertEqual(r1?.y ?? -1, 0, accuracy: 0.001)
        // Degenerate (collinear) refs → nil.
        let bad = [
            WatchProjectionRef(lat: 0, lon: 0, px: 0, py: 0),
            WatchProjectionRef(lat: 0, lon: 1, px: 100, py: 0),
            WatchProjectionRef(lat: 0, lon: 2, px: 200, py: 0),
        ]
        XCTAssertNil(WatchGeoMath.projectToTopoPx(lat: 0.5, lon: 0.5, refs: bad))
    }

    func testHaversineAndYards() {
        // 0.001° of latitude ≈ 111.2 m at the equator.
        XCTAssertEqual(WatchGeoMath.metres(0, 0, 0.001, 0), 111.2, accuracy: 1.0)
        XCTAssertEqual(WatchGeoMath.yards(from: 0, 0, toLat: 0.001, 0), 122)
        XCTAssertNil(WatchGeoMath.yards(from: 0, 0, toLat: nil, 0))
    }

    func testGreenRangePresentationRejectsOffCourseValuesWithoutClampingMath() {
        XCTAssertEqual(WatchGeoMath.greenRangeText(nil), "—")
        XCTAssertEqual(WatchGeoMath.greenRangeText(999), "999")
        XCTAssertEqual(WatchGeoMath.greenRangeText(1_000), "—")
        XCTAssertEqual(WatchGeoMath.greenRangeText(18_383), "—")
        XCTAssertTrue(WatchGeoMath.isBeyondUsefulGreenRange(1_000))
        XCTAssertFalse(WatchGeoMath.isBeyondUsefulGreenRange(485))
        XCTAssertGreaterThan(
            WatchGeoMath.yards(from: 40, 116, toLat: 40.2, 116) ?? 0,
            WatchGeoMath.maximumUsefulGreenYards
        )
    }

    func testInitialBearingUsesTrueNorthAndRejectsAnUndefinedDirection() {
        XCTAssertEqual(
            WatchGeoMath.initialBearingDegrees(from: 0, 0, to: 0, 1) ?? -1,
            90,
            accuracy: 0.001
        )
        XCTAssertEqual(
            WatchGeoMath.initialBearingDegrees(from: 0, 0, to: 1, 0) ?? -1,
            0,
            accuracy: 0.001
        )
        XCTAssertNil(WatchGeoMath.initialBearingDegrees(from: 0, 0, to: 0, 0))
    }
}
