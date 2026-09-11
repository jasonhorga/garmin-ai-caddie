import SwiftUI
import XCTest
@testable import AICaddie

final class HoleMapInteractionTests: XCTestCase {
    func testNearbyClubDistancesInterpolateToDifferentLandingPixels() throws {
        let overlay = CoursePrepOverlay(
            w: 200,
            h: 1_000,
            ppm: 1,
            ln: 200,
            route: [
                [20, 900, 0],
                [100, 500, 100],
                [180, 100, 200],
            ]
        )

        let sixIron = try XCTUnwrap(HoleImageMapView.landingOverlayPoint(overlay, targetMetres: 137))
        let fiveIron = try XCTUnwrap(HoleImageMapView.landingOverlayPoint(overlay, targetMetres: 146))

        XCTAssertEqual(sixIron[0], 129.6, accuracy: 0.001)
        XCTAssertEqual(sixIron[1], 352, accuracy: 0.001)
        XCTAssertEqual(fiveIron[0], 136.8, accuracy: 0.001)
        XCTAssertEqual(fiveIron[1], 316, accuracy: 0.001)
        XCTAssertNotEqual(sixIron[0], fiveIron[0])
        XCTAssertNotEqual(sixIron[1], fiveIron[1])
    }

    func testLandingInterpolationRejectsRoutesWithoutMeasuredPixels() {
        let overlay = CoursePrepOverlay(
            w: 200,
            h: 1_000,
            ppm: 1,
            ln: 200,
            route: [[20, 900], []]
        )

        XCTAssertNil(HoleImageMapView.landingOverlayPoint(overlay, targetMetres: 146))
    }

    func testRecommendationBuildsTwoDirectFlightArcsThroughLanding() {
        let tee = CGPoint(x: 100, y: 500)
        let landing = CGPoint(x: 145, y: 290)
        let pin = CGPoint(x: 120, y: 70)

        let arcs = HoleImageMapView.flightArcs(tee: tee, landing: landing, pin: pin)

        XCTAssertEqual(arcs.count, 2)
        XCTAssertEqual(arcs[0].start, tee)
        XCTAssertEqual(arcs[0].end, landing)
        XCTAssertEqual(arcs[1].start, landing)
        XCTAssertEqual(arcs[1].end, pin)
        XCTAssertNotEqual(arcs[0].control, CGPoint(x: 122.5, y: 395))
        XCTAssertNotEqual(arcs[1].control, CGPoint(x: 132.5, y: 180))
    }

    func testTouchTargetKeepsTeeToTargetArcWhenPinProjectionIsMissing() {
        let reference = CGPoint(x: 40, y: 420)
        let target = CGPoint(x: 130, y: 250)

        let arcs = LivePlayMapDetailView.targetFlightArcs(
            reference: reference,
            target: target,
            pin: nil
        )

        XCTAssertEqual(arcs.count, 1)
        XCTAssertEqual(arcs[0].start, reference)
        XCTAssertEqual(arcs[0].end, target)
    }

    func testCaddieRecommendationCarriesTheSelectedSequenceClubAndDistance() {
        let decision = CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2",
            decisionId: "decision-1",
            sourceRef: nil,
            evidenceRefs: nil,
            shotType: "tee",
            phase: "tee_shot",
            context: [:],
            options: [[
                "id": .string("stock"),
                "carry_m": .number(225),
                "clubName": .string("3W"),
            ]],
            selected: nil,
            selectedOptionId: "stock",
            selectedOption: nil,
            sequences: [[
                "id": .string("stock"),
                "clubs": .array([
                    .object([
                        "clubName": .string("1W"),
                        "targetCarry_m": .number(242),
                    ])
                ]),
            ]],
            selectedSequence: ["id": .string("stock")],
            avoidZones: [],
            forbiddenZones: [],
            acceptableMiss: [:],
            evidence: [],
            confidence: [:],
            missingData: [],
            auditCriteria: []
        )

        XCTAssertEqual(
            LiveClubStripPolicy.recommendation(from: decision),
            LiveClubStripPolicy.Recommendation(name: "一号木", carryMetres: 242)
        )
    }

    func testRecommendationRemainsVisibleWhenBagHasNoMatchingProfile() {
        let names = LiveClubStripPolicy.orderedNames(
            profiles: [
                "三号木": ClubProfile(clubName: "3W", sampleSize: 10, medianM: 200, p10M: 180, p90M: 220),
            ],
            recommended: "一号木",
            selected: "一号木",
            targetMetres: 220
        )

        XCTAssertEqual(names.first, "一号木")
        XCTAssertTrue(names.contains("三号木"))
    }

    func testHazardCalloutNumbersStaySmallAndUseSeparateBoundaryLanes() {
        XCTAssertTrue(CoursePrepLiveHazardReadout.isPlausibleYards(999))
        XCTAssertFalse(CoursePrepLiveHazardReadout.isPlausibleYards(8_809))

        let viewport = CGSize(width: 360, height: 540)
        let front = LiveHazardCalloutLayout.center(
            for: CGPoint(x: 170, y: 260), isFront: true, index: 0, viewportSize: viewport
        )
        let back = LiveHazardCalloutLayout.center(
            for: CGPoint(x: 170, y: 260), isFront: false, index: 0, viewportSize: viewport
        )
        XCTAssertGreaterThanOrEqual(abs(front.y - back.y), LiveHazardCalloutLayout.labelHeight)
        XCTAssertGreaterThanOrEqual(front.x, LiveHazardCalloutLayout.labelWidth / 2)
        XCTAssertLessThanOrEqual(back.x, viewport.width - LiveHazardCalloutLayout.labelWidth / 2)
    }

    func testNearbyHazardsUseDistinctVerticalLanesWhenTheirEdgesCoincide() {
        let viewport = CGSize(width: 360, height: 540)
        let point = CGPoint(x: 170, y: 260)
        let firstFront = LiveHazardCalloutLayout.center(
            for: point, isFront: true, index: 0, viewportSize: viewport
        )
        let secondFront = LiveHazardCalloutLayout.center(
            for: point, isFront: true, index: 1, viewportSize: viewport
        )
        let firstBack = LiveHazardCalloutLayout.center(
            for: point, isFront: false, index: 0, viewportSize: viewport
        )
        let secondBack = LiveHazardCalloutLayout.center(
            for: point, isFront: false, index: 1, viewportSize: viewport
        )

        XCTAssertGreaterThanOrEqual(
            abs(firstFront.y - secondFront.y),
            LiveHazardCalloutLayout.labelHeight
        )
        XCTAssertGreaterThanOrEqual(
            abs(firstBack.y - secondBack.y),
            LiveHazardCalloutLayout.labelHeight
        )
    }

    func testLegacyHazardFocusRingEnclosesBothBoundaryPoints() throws {
        let front = CGPoint(x: 170, y: 260)
        let back = CGPoint(x: 174, y: 282)
        let ring = try XCTUnwrap(
            LiveHazardFocusRingLayout.rect(
                front: front,
                back: back,
                viewportSize: CGSize(width: 360, height: 540)
            )
        )

        XCTAssertTrue(ring.contains(front))
        XCTAssertTrue(ring.contains(back))
        XCTAssertGreaterThanOrEqual(ring.width, LiveHazardFocusRingLayout.minimumWidth)
        XCTAssertGreaterThanOrEqual(ring.height, LiveHazardFocusRingLayout.minimumHeight)
    }

    func testLegacyHazardFocusLabelsSeparateFrontAndBackAtMapCenter() {
        let viewport = CGSize(width: 360, height: 540)
        let point = CGPoint(x: 170, y: 260)
        let front = LiveHazardFocusRingLayout.labelCenter(
            for: point,
            isFront: true,
            viewportSize: viewport
        )
        let back = LiveHazardFocusRingLayout.labelCenter(
            for: point,
            isFront: false,
            viewportSize: viewport
        )

        XCTAssertGreaterThanOrEqual(
            abs(front.y - back.y),
            LiveHazardFocusRingLayout.labelHeight
        )
        XCTAssertGreaterThanOrEqual(front.x, LiveHazardFocusRingLayout.labelWidth / 2)
        XCTAssertLessThanOrEqual(back.x, viewport.width - LiveHazardFocusRingLayout.labelWidth / 2)
    }

    func testHorizontalHoleSwipeChangesOnlyToAnAdjacentHole() {
        let holes = [1, 2, 3]

        XCTAssertEqual(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: -90, height: 8)
            ),
            3
        )
        XCTAssertEqual(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: 90, height: -8)
            ),
            1
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: 45, height: 2)
            )
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: -90, height: 120)
            )
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 2,
                holes: holes,
                translation: CGSize(width: -90, height: 2),
                enabled: false
            )
        )
        XCTAssertNil(
            HoleSwipeNavigation.target(
                current: 3,
                holes: holes,
                translation: CGSize(width: -90, height: 2)
            )
        )
    }

    func testMediaCaptureCardRemainsFeatureFlaggedOffInLivePlay() {
        XCTAssertFalse(CurrentHoleView.showsMediaCaptureCard)
    }
}
