import CoreGraphics
import XCTest
@testable import AICaddieWatch

final class WatchCurrentShotLayoutTests: XCTestCase {
    func testMapsOnlyTheCurrentShotTargetAndMeasuredCarryDepthsOntoTheRealRoute() throws {
        let route = [
            [100.0, 700.0, 0.0],
            [500.0, 400.0, 200.0],
            [600.0, 100.0, 400.0],
        ]

        let layout = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: CGPoint(x: 300, y: 550),
            aimCarryM: 100,
            carryP10M: 80,
            carryP90M: 120
        ))

        XCTAssertEqual(layout.player.x, 300, accuracy: 0.0001)
        XCTAssertEqual(layout.player.y, 550, accuracy: 0.0001)
        XCTAssertEqual(layout.target.x, 500, accuracy: 0.0001)
        XCTAssertEqual(layout.target.y, 400, accuracy: 0.0001)
        XCTAssertEqual(layout.carryP10.x, 460, accuracy: 0.0001)
        XCTAssertEqual(layout.carryP10.y, 430, accuracy: 0.0001)
        XCTAssertEqual(layout.carryP90.x, 510, accuracy: 0.0001)
        XCTAssertEqual(layout.carryP90.y, 370, accuracy: 0.0001)
        XCTAssertTrue(layout.continuation.isEmpty)
    }

    func testCaddieDetailContinuesAMultiClubPlanToTheRealPin() throws {
        let route = [
            [504.0, 702.0, 0.0],
            [506.0, 403.0, 210.0],
            [435.0, 279.0, 400.0],
        ]
        let geometry = WatchHoleMapSample.geometry
        let option = WatchCaddieOption(
            optionId: "stock",
            label: "推荐",
            plan: [
                WatchCaddiePlanStep(clubName: "1W", carryM: 192),
                WatchCaddiePlanStep(clubName: "8I", carryM: 142),
            ]
        )

        let continuation = WatchCaddieOptionsView.continuationTargets(
            for: option,
            route: route,
            geometry: geometry
        )

        XCTAssertEqual(continuation, [geometry.pinPx])
        let layout = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: geometry.youPx,
            aimCarryM: 192,
            carryP10M: 176,
            carryP90M: 208,
            continuation: continuation
        ))
        XCTAssertEqual(layout.continuation.last, geometry.pinPx)
    }

    func testCurrentHoleShotListBeginsBelowTheSystemClockLane() {
        XCTAssertGreaterThanOrEqual(
            WatchCurrentHoleShotsLayout.systemTimeTopClearance,
            CGFloat(28)
        )
    }
}
