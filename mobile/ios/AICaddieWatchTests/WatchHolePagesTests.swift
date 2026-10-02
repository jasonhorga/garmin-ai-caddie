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

    func testALiveDecisionOffsetCountsFromThePlayer() {
        // decision.py starts travelled_m at 0 for every decision, so a 200 m offset from a player
        // already 50 m down the route lands at 250 m, and the drawn leg is as long as its label.
        guard let origin = WatchHazardMapLayout.imagePoint(on: route, atMetres: 50),
              let expected = WatchHazardMapLayout.imagePoint(on: route, atMetres: 250) else {
            return XCTFail("route points")
        }
        let live = WatchCaddieOption(
            optionId: "stock", label: "标准",
            plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 200, routeOffsetM: 200)],
            routeOffsetBasis: .shot,
            originShotIndex: 1  // made for this shot, from this spot
        )
        let legs = WatchPlanLegs.resolve(option: live, route: route, origin: origin, playedShots: 1)
        XCTAssertEqual(legs.count, 1)
        XCTAssertEqual(legs.first?.label, "D 219")
        assertPoint(legs.first?.landing, expected)
        let landed = WatchHazardMapLayout.playerProgressMetres(on: route, playerImagePoint: legs[0].landing) ?? 0
        let started = WatchHazardMapLayout.playerProgressMetres(on: route, playerImagePoint: legs[0].start) ?? 0
        XCTAssertEqual(landed - started, 200, accuracy: 0.5, "drawn length matches the 219-yard label")
    }

    func testAPreparedTeePlanDrawsOnlyTheRemainingShotsAtTheirOriginalStations() throws {
        let options = WatchCourseTemplateBuilder.preparedCaddieOptions(
            clubs: [
                WatchClubOption(clubName: "1W", medianM: 220, source: "course-prep"),
                WatchClubOption(clubName: "3W", medianM: 190, source: "course-prep"),
                WatchClubOption(clubName: "5I", medianM: 160, source: "course-prep"),
                WatchClubOption(clubName: "8I", medianM: 125, source: "course-prep"),
            ],
            suggestedClub: "1W",
            routeDistanceM: 518.8,
            landingM: nil
        )
        let stock = try XCTUnwrap(options.first { $0.optionId == "stock" })
        XCTAssertTrue(options.allSatisfy { $0.routeOffsetBasis == .tee })
        let stations = (stock.plan ?? []).compactMap(\.routeOffsetM)
        XCTAssertEqual(stations, [220, 410, 518.8])

        // At the tee the whole plan is drawn from the tee.
        let tee = CGPoint(x: 435, y: 981)
        let atTee = WatchPlanLegs.resolve(option: stock, route: route, origin: tee, playedShots: 0)
        XCTAssertEqual(atTee.map(\.label), ["D 241", "3W 208", "8i 137"])
        assertPoint(atTee.first?.landing, WatchHazardMapLayout.imagePoint(on: route, atMetres: 220))

        // After the tee shot, standing on its landing: the tee shot is not replayed from here, and
        // the next landing stays at its original 410 m station (not 220 + 410).
        let firstLanding = try XCTUnwrap(WatchHazardMapLayout.imagePoint(on: route, atMetres: 220))
        let afterTee = WatchPlanLegs.resolve(option: stock, route: route, origin: firstLanding, playedShots: 1)
        XCTAssertEqual(afterTee.map(\.label), ["3W 208", "8i 137"])
        XCTAssertEqual(afterTee.first?.start, firstLanding)
        assertPoint(afterTee.first?.landing, WatchHazardMapLayout.imagePoint(on: route, atMetres: 410))
        assertPoint(afterTee.last?.landing, WatchHazardMapLayout.imagePoint(on: route, atMetres: 518.8))

        // Older payloads without a basis: the Watch's offline plans were tee-based.
        let legacy = WatchCaddieOption(optionId: "stock", label: "标准", plan: stock.plan, confidence: "offline")
        XCTAssertEqual(legacy.resolvedRouteOffsetBasis, .tee)
        XCTAssertEqual(WatchCaddieOption(optionId: "stock", label: "标准").resolvedRouteOffsetBasis, .shot)
    }

    private func assertPoint(_ actual: CGPoint?, _ expected: CGPoint?, file: StaticString = #filePath, line: UInt = #line) {
        guard let actual, let expected else { return XCTFail("missing point", file: file, line: line) }
        XCTAssertEqual(Double(actual.x), Double(expected.x), accuracy: 0.01, file: file, line: line)
        XCTAssertEqual(Double(actual.y), Double(expected.y), accuracy: 0.01, file: file, line: line)
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
