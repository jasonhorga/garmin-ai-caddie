import CoreLocation
import XCTest
@testable import AICaddie

/// J5.11 live-hole recommendation: one authoritative route, with the tee shot planned from the
/// tee rather than from a player still walking up to it.
@MainActor
final class LivePlanPagingTests: XCTestCase {
    private func route(_ id: String, _ clubs: [(String, Double)]) -> CaddiePlanSequence {
        var offset = 0.0
        let steps = clubs.enumerated().map { index, club -> CaddiePlanSequenceStep in
            offset += club.1
            return CaddiePlanSequenceStep(
                id: "\(id)-\(index)",
                role: index == clubs.count - 1 ? "scoring" : "advance",
                clubName: club.0,
                targetCarryM: club.1,
                expectedRemainingM: nil,
                sampleSize: nil,
                confidence: nil,
                sourceRefs: [],
                routeOffsetM: offset
            )
        }
        return CaddiePlanSequence(
            id: id, label: id, expectedRemainingM: nil, riskScore: nil, confidence: nil,
            coverageText: nil, sourceRefs: [], steps: steps
        )
    }

    private lazy var driver = route("installed-course-plan", [("Driver", 197), ("3W", 166)])
    private lazy var safe = route("safe", [("3W", 160), ("8I", 125)])
    private lazy var layup = route("layup", [("3H", 150), ("7I", 130), ("54", 45)])

    private func decision(selected route: CaddiePlanSequence?) -> CaddieDecisionResponse {
        let rows = route.map { route in
            [[String: JSONValue](dictionaryLiteral:
                ("id", .string(route.id)),
                ("label", .string(route.label)),
                ("clubs", .array(route.steps.map { step in
                    .object([
                        "clubName": .string(step.clubName),
                        "role": .string(step.role),
                        "targetCarry_m": step.targetCarryM.map(JSONValue.number) ?? .null,
                        "routeOffset_m": step.routeOffsetM.map(JSONValue.number) ?? .null,
                    ])
                }))
            )]
        } ?? []
        return CaddieDecisionResponse(
            schema: "ai-caddie-decision-v2", decisionId: nil, sourceRef: nil,
            evidenceRefs: nil, shotType: "tee", phase: "Tee", context: [:],
            options: [], selected: nil, selectedOptionId: route?.id, selectedOption: nil,
            sequences: rows, selectedSequence: rows.first,
            avoidZones: [], forbiddenZones: [], acceptableMiss: [:], evidence: [], confidence: [:],
            missingData: [], auditCriteria: []
        )
    }

    /// J5.11: a non-empty online selectedSequence is the only visible recommendation.
    func testOnlineSelectedSequenceReplacesInstalledAndOfflineRoutes() {
        let routes = LiveCaddieRouteAuthority.resolve(
            installed: driver,
            online: decision(selected: safe),
            offline: decision(selected: layup),
            par: 4,
            shotType: "tee"
        )
        XCTAssertEqual(routes.map(\.id), ["safe"])
    }

    /// J5.11: an empty online response falls through to the installed CoursePrep chain.
    func testInstalledRouteIsTheOnlyFallbackWhenOnlineIsEmpty() {
        let routes = LiveCaddieRouteAuthority.resolve(
            installed: driver,
            online: decision(selected: nil),
            offline: decision(selected: layup),
            par: 4,
            shotType: "tee"
        )
        XCTAssertEqual(routes.map(\.id), ["installed-course-plan"])
    }

    /// J5.11: when both authoritative sources are empty, local evaluation supplies one route.
    func testLocalRouteIsTheOnlyFinalFallback() {
        let routes = LiveCaddieRouteAuthority.resolve(
            installed: nil,
            online: decision(selected: nil),
            offline: decision(selected: layup),
            par: 4,
            shotType: "tee"
        )
        XCTAssertEqual(routes.map(\.id), ["layup"])
    }

    /// Refreshing the same hole replaces the route in place and never recreates a pager.
    func testRefreshingARecommendationNeverAccumulatesRoutes() {
        let first = LiveCaddieRouteAuthority.reconciled(
            incoming: [driver], existing: [], installed: driver, retained: nil,
            explicitSelectionKey: nil, vetoInstalled: false
        )
        let second = LiveCaddieRouteAuthority.reconciled(
            incoming: [safe], existing: first?.merged ?? [], installed: driver,
            retained: first?.first, explicitSelectionKey: nil, vetoInstalled: false
        )
        XCTAssertEqual(second?.merged.map(\.id), ["safe"])
    }

    /// J5.10/J5.11: an untouched round has no score-to-par fact to display as E.
    func testUnscoredRoundShowsDashInsteadOfEvenPar() {
        XCTAssertEqual(CurrentHoleView.roundToParText(scores: []), "本场 —")
        XCTAssertEqual(CurrentHoleView.roundToParText(scores: [(par: 4, score: 4)]), "本场 E")
    }

    /// J5.11: moving a Touch Target to 169 m changes the readout/current-club input only; the
    /// whole-hole plan still uses the downloaded tee-to-green fact.
    func testMapTargetDoesNotChangeWholeHolePlanningDistance() {
        let before = CurrentHoleView.caddiePlanningDistanceMetres(
            manualM: nil, mapTargetM: nil, isTeeShotOffTheHole: true,
            routeRemainingM: nil,
            liveMiddleM: nil, staticMiddleM: 320.9, holeYards: 351
        )
        let after = CurrentHoleView.caddiePlanningDistanceMetres(
            manualM: nil, mapTargetM: 169, isTeeShotOffTheHole: true,
            routeRemainingM: nil,
            liveMiddleM: nil, staticMiddleM: 320.9, holeYards: 351
        )
        XCTAssertEqual(before ?? -1, 320.9, accuracy: 0.001)
        XCTAssertEqual(after ?? -1, 320.9, accuracy: 0.001)
    }

    /// J5.11 dogleg fixture: the current lie uses the remaining centreline station, not the
    /// straight line to the pin.
    func testDoglegProjectionReturnsRemainingPolylineDistance() {
        let route = [
            [311.8, 89.6, 0.0], [179.2, 118.1, 135.5], [139.9, 121.1, 175.0],
            [101.4, 117.8, 213.7], [33.2, 35.0, 320.9],
        ]
        let remaining = CoursePrepRoute.remainingMetres(route: route, playerPx: [179.2, 118.1])
        XCTAssertEqual(remaining ?? -1, 185.4, accuracy: 0.001)
    }

    /// Before the tee shot the caddie plans from the tee while the player is off the hole: a player
    /// 308 y from hole 1's green in the car park is not on the 397 y hole. On the hole (a forward
    /// tee, or walking down the fairway without recording the tee shot) the live position plans.
    func testTheTeeShotIsPlannedFromTheTeeWhileThePlayerIsOffTheHole() {
        // A straight hole running north for ~360 m.
        let route = [
            CLLocationCoordinate2D(latitude: 45.5100, longitude: 10.4770),
            CLLocationCoordinate2D(latitude: 45.5118, longitude: 10.4770),
            CLLocationCoordinate2D(latitude: 45.5132, longitude: 10.4770),
        ]
        let carPark = CLLocationCoordinate2D(latitude: 45.5110, longitude: 10.4785)      // ~117 m east
        let forwardTee = CLLocationCoordinate2D(latitude: 45.5106, longitude: 10.4771)   // 70 m up the line
        let fairway = CLLocationCoordinate2D(latitude: 45.5120, longitude: 10.4774)      // ~31 m off the line
        XCTAssertTrue(CurrentHoleView.isTeeShotOffTheHole(shotsRecorded: 0, shotType: "tee", fix: carPark, route: route))
        XCTAssertFalse(CurrentHoleView.isTeeShotOffTheHole(shotsRecorded: 0, shotType: "Tee", fix: forwardTee, route: route),
                       "a forward tee is on the hole")
        XCTAssertFalse(CurrentHoleView.isTeeShotOffTheHole(shotsRecorded: 0, shotType: "tee", fix: fairway, route: route),
                       "walking down the fairway without recording the tee shot")
        XCTAssertFalse(CurrentHoleView.isTeeShotOffTheHole(shotsRecorded: 1, shotType: "tee", fix: carPark, route: route))
        XCTAssertFalse(CurrentHoleView.isTeeShotOffTheHole(shotsRecorded: 0, shotType: "approach", fix: carPark, route: route))
        XCTAssertFalse(CurrentHoleView.isTeeShotOffTheHole(shotsRecorded: 0, shotType: "tee", fix: nil, route: route))
        XCTAssertFalse(CurrentHoleView.isTeeShotOffTheHole(shotsRecorded: 0, shotType: "tee", fix: carPark, route: []),
                       "no projected route: the live position keeps its role")
    }
}
