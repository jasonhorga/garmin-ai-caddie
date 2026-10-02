import XCTest
@testable import AICaddieWatch

/// B6 本洞 page rules (Codex review on #367): the whole plan, plan cycling, the green's Crown that
/// only zooms, and the hazard page's real outline and edge ranges.
final class WatchHolePagesTests: XCTestCase {
    private let route: [[Double]] = [
        [435, 981, 0],
        [504, 702, 200],
        [556, 562, 303],
        [506, 403, 419],
        [435, 279, 518.8],
    ]

    func testThePlanPageDrawsEveryLegWithItsLandingAndLabel() {
        let tee = CGPoint(x: 435, y: 981)
        let legs = WatchPlanLegs.resolve(
            plan: [
                WatchCaddiePlanStep(clubName: "1W", carryM: 205),
                WatchCaddiePlanStep(clubName: "3W", carryM: 187.5),
                WatchCaddiePlanStep(clubName: "9I", carryM: 140),
            ],
            route: route,
            origin: tee
        )
        XCTAssertEqual(legs.map(\.label), ["D 224", "3W 205", "9i 153"])
        XCTAssertEqual(legs.count, 3, "not just the first shot")
        XCTAssertEqual(legs[0].start, tee)
        XCTAssertEqual(legs[1].start, legs[0].landing, "each leg starts where the previous one lands")
        XCTAssertEqual(legs[2].start, legs[1].landing)
        // The last leg is clamped to the route end (the green), not past it.
        XCTAssertEqual(legs[2].landing, CGPoint(x: 435, y: 279))
    }

    func testAPlanStepsRouteOffsetPlacesItsLandingAndTheChainStopsAtTheGreen() {
        let legs = WatchPlanLegs.resolve(
            plan: [
                WatchCaddiePlanStep(clubName: "1W", carryM: 205, routeOffsetM: 200),
                WatchCaddiePlanStep(clubName: "5W", carryM: 400),
                WatchCaddiePlanStep(clubName: "PW", carryM: 90),
            ],
            route: route,
            origin: CGPoint(x: 435, y: 981)
        )
        XCTAssertEqual(legs.first?.landing, CGPoint(x: 504, y: 702), "routeOffsetM wins over the carry")
        XCTAssertEqual(legs.count, 2, "nothing is drawn beyond the green")
        XCTAssertTrue(WatchPlanLegs.resolve(plan: [], route: route, origin: .zero).isEmpty)
    }

    func testARouteOffsetCountsFromTheDecisionOriginNotTheTee() {
        // decision.py starts travelled_m at 0 for every decision, so a 200 m offset from a player
        // already 50 m down the route lands at 250 m, and the drawn leg is as long as its label.
        guard let origin = WatchHazardMapLayout.imagePoint(on: route, atMetres: 50),
              let expected = WatchHazardMapLayout.imagePoint(on: route, atMetres: 250) else {
            return XCTFail("route points")
        }
        let legs = WatchPlanLegs.resolve(
            plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 200, routeOffsetM: 200)],
            route: route,
            origin: origin
        )
        XCTAssertEqual(legs.count, 1)
        XCTAssertEqual(legs.first?.label, "D 219")
        XCTAssertEqual(Double(legs.first?.landing.x ?? 0), Double(expected.x), accuracy: 0.01)
        XCTAssertEqual(Double(legs.first?.landing.y ?? 0), Double(expected.y), accuracy: 0.01)
        let landed = WatchHazardMapLayout.playerProgressMetres(on: route, playerImagePoint: legs[0].landing) ?? 0
        let started = WatchHazardMapLayout.playerProgressMetres(on: route, playerImagePoint: legs[0].start) ?? 0
        XCTAssertEqual(landed - started, 200, accuracy: 0.5, "drawn length matches the 219-yard label")
    }

    func testAFlagDraggedPastTheGreenSlidesAlongItsEdge() {
        // A round green (centre 100,100, radius 50). The finger leaves it to the right, then keeps
        // moving up: the flag follows the arc upwards instead of freezing at the exit point.
        let outline = (0..<48).map { index -> CGPoint in
            let angle = Double(index) / 48 * 2 * .pi
            return CGPoint(x: 100 + 50 * cos(angle), y: 100 + 50 * sin(angle))
        }
        let inside = CGPoint(x: 120, y: 90)
        XCTAssertEqual(WatchGreenPreviewLayout.flagPoint(inside, outline: outline), inside)
        var previousY = CGFloat.greatestFiniteMagnitude
        for fingerY in stride(from: 100, through: 40, by: -15) as StrideThrough<CGFloat> {
            guard let flag = WatchGreenPreviewLayout.flagPoint(CGPoint(x: 175, y: fingerY), outline: outline) else {
                return XCTFail("no flag for \(fingerY)")
            }
            XCTAssertEqual(Double(hypot(flag.x - 100, flag.y - 100)), 50, accuracy: 1.5, "on the edge")
            XCTAssertLessThan(flag.y, previousY, "the flag slides up with the finger")
            XCTAssertGreaterThan(flag.x, 100, "it stays on the right-hand arc")
            previousY = flag.y
        }
        XCTAssertNil(WatchGreenPreviewLayout.flagPoint(inside, outline: Array(outline.prefix(2))))
    }

    func testThePageMarkerNamesEachHolePage() {
        XCTAssertEqual((0...2).map(WatchRoundContainerView.holePageName), ["方案", "障碍", "果岭"])
    }

    func testTappingTheClubTagCyclesEveryPlan() {
        let ids = ["stock", "safe", "attack"]
        XCTAssertEqual(WatchRoundContainerView.nextPlanId(after: "stock", in: ids), "safe")
        XCTAssertEqual(WatchRoundContainerView.nextPlanId(after: "attack", in: ids), "stock")
        XCTAssertEqual(WatchRoundContainerView.nextPlanId(after: nil, in: ids), "stock")
        XCTAssertNil(WatchRoundContainerView.nextPlanId(after: "stock", in: ["stock"]))
    }

    func testTheGreenRotatesInStepsSoTheCrownOnlyZooms() {
        XCTAssertEqual(WatchGreenRotationStep.next(0), 15)
        XCTAssertEqual(WatchGreenRotationStep.next(165), 180)
        XCTAssertEqual(WatchGreenRotationStep.next(180), -165)
    }

    func testTheHazardPageUsesTheRealOutlineAndRangesBothEdges() {
        let hazard = WatchHazard(
            kind: "water", label: "前方水障碍", startM: 330, endM: 372,
            frontDistanceM: 330, backDistanceM: 372,
            frontPx: [522, 528], backPx: [508, 468],
            outlinePx: [[522, 528], [531, 516], [528, 494], [519, 474], [508, 468], [499, 478], [501, 503]]
        )
        XCTAssertEqual(WatchHazardMapLayout.outline(hazard).count, 7)
        XCTAssertTrue(WatchHazardMapLayout.outline(WatchHazard(kind: "bunker", label: "沙坑")).isEmpty)
        let tee = CGPoint(x: 435, y: 981)
        let front = WatchHazardMapLayout.edgeYards(
            hazard: hazard, edge: CGPoint(x: 522, y: 528), metres: 330,
            player: tee, progress: 0, route: route
        )
        let back = WatchHazardMapLayout.edgeYards(
            hazard: hazard, edge: CGPoint(x: 508, y: 468), metres: 372,
            player: tee, progress: 0, route: route
        )
        XCTAssertNotNil(front)
        XCTAssertNotNil(back)
        XCTAssertLessThan(front ?? 0, back ?? 0, "前 is nearer than 后")
    }

    func testOutlinesAreThinnedForTheWatchPayload() {
        let circle = (0..<120).map { index -> [Double] in
            let angle = Double(index) / 120 * 2 * .pi
            return [500 + 20 * cos(angle), 500 + 20 * sin(angle)]
        }
        let thinned = WatchHazard.watchOutline(circle)
        XCTAssertNotNil(thinned)
        XCTAssertLessThanOrEqual(thinned?.count ?? 0, 40)
        XCTAssertGreaterThanOrEqual(thinned?.count ?? 0, 3)
        XCTAssertNil(WatchHazard.watchOutline([[1, 2], [3, 4]]))
    }
}
