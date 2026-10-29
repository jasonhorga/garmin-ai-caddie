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

    private func offlineDecision(selected route: CaddiePlanSequence?) -> CaddieDecisionResponse {
        let base = decision(selected: route)
        return CaddieDecisionResponse(
            schema: base.schema, decisionId: "offline-seed", sourceRef: base.sourceRef,
            evidenceRefs: base.evidenceRefs, shotType: base.shotType, phase: base.phase,
            context: base.context, options: base.options, selected: base.selected,
            selectedOptionId: base.selectedOptionId, selectedOption: base.selectedOption,
            sequences: base.sequences, selectedSequence: base.selectedSequence,
            avoidZones: base.avoidZones, forbiddenZones: base.forbiddenZones,
            acceptableMiss: base.acceptableMiss, evidence: base.evidence,
            confidence: ["source": .string("offline_package_seed")],
            missingData: base.missingData, auditCriteria: base.auditCriteria
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

    /// J5.11: the live hole publishes one selected route while 备战 keeps the same decision's
    /// materially different complete alternatives for pre-round comparison.
    func testLiveHoleUsesOneRouteWhilePrepRetainsAlternatives() {
        XCTAssertEqual(CurrentHoleView.caddieRouteScope(isPrepMode: false), .liveHole)
        XCTAssertEqual(CurrentHoleView.caddieRouteScope(isPrepMode: true), .prep)
        let online = decision(selected: safe)
        let offline = decision(selected: layup)
        let liveRoutes = LiveCaddieRouteAuthority.resolve(
            installed: driver,
            online: online,
            offline: offline,
            par: 4,
            shotType: "tee",
            scope: .liveHole
        )
        let prepRoutes = LiveCaddieRouteAuthority.resolve(
            installed: driver,
            online: online,
            offline: offline,
            par: 4,
            shotType: "tee",
            scope: .prep
        )
        XCTAssertEqual(liveRoutes.map(\.id), ["safe"])
        XCTAssertGreaterThanOrEqual(prepRoutes.count, 2)
        XCTAssertEqual(prepRoutes.first?.id, LiveCaddieRouteAuthority.installedRouteId)
        XCTAssertTrue(prepRoutes.contains { $0.id == "safe" })
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

    /// B1: a response carrying the offline provenance must never occupy the online priority slot.
    /// This is the same object shape used by CurrentHoleView after an empty/error response.
    func testOfflineFallbackInDecisionSlotCannotDisplaceInstalledRoute() {
        let routes = LiveCaddieRouteAuthority.resolve(
            installed: driver,
            online: offlineDecision(selected: layup),
            offline: offlineDecision(selected: layup),
            par: 4,
            shotType: "tee"
        )
        XCTAssertEqual(routes.map(\.id), ["installed-course-plan"])
    }

    /// B1: once an authoritative route is visible, a later offline refresh keeps its physical
    /// chain stable even when the local fallback proposes a different strategy.
    func testOfflineRefreshRetainsAuthoritativeRoute() {
        let retained = LiveCaddieRouteAuthority.reconciled(
            incoming: [safe], existing: [], installed: driver, retained: nil,
            explicitSelectionKey: nil, vetoInstalled: false, incomingSource: .online
        )
        let refreshed = LiveCaddieRouteAuthority.reconciled(
            incoming: [layup], existing: retained.map { [$0.first] } ?? [], installed: driver,
            retained: retained?.first, explicitSelectionKey: nil, vetoInstalled: false,
            incomingSource: .offline, retainedSource: .online
        )
        XCTAssertEqual(refreshed?.merged.map(\.id), ["safe"])
    }

    /// J5.11: the page's provenance rule must distinguish transport state from cached route id.
    func testPageRouteSourceUsesDecisionAndTransportState() {
        XCTAssertEqual(CurrentHoleView.caddieRouteSource(
            isOnline: true, isOfflineFallback: false, hasDecision: true,
            retainedSource: .offline, incomingIsInstalled: false
        ), .online)
        XCTAssertEqual(CurrentHoleView.caddieRouteSource(
            isOnline: false, isOfflineFallback: true, hasDecision: true,
            retainedSource: .online, incomingIsInstalled: true
        ), .offline)
        XCTAssertEqual(CurrentHoleView.caddieRouteSource(
            isOnline: false, isOfflineFallback: false, hasDecision: false,
            retainedSource: .online, incomingIsInstalled: true
        ), .offline)
        XCTAssertEqual(CurrentHoleView.caddieRouteSource(
            isOnline: false, isOfflineFallback: false, hasDecision: false,
            retainedSource: .offline, incomingIsInstalled: true
        ), .installed)
        XCTAssertEqual(CurrentHoleView.caddieRouteSource(
            isOnline: false, isOfflineFallback: false, hasDecision: true,
            retainedSource: nil, incomingIsInstalled: false
        ), .offline)
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
            manualM: nil, mapTargetM: nil, isTeeShotOffTheHole: false,
            routeRemainingM: 320.9,
            liveMiddleM: 284.3, staticMiddleM: 284.3, holeYards: 351
        )
        let after = CurrentHoleView.caddiePlanningDistanceMetres(
            manualM: nil, mapTargetM: 169, isTeeShotOffTheHole: false,
            routeRemainingM: 320.9,
            liveMiddleM: 284.3, staticMiddleM: 284.3, holeYards: 351
        )
        XCTAssertEqual(before ?? -1, 320.9, accuracy: 0.001)
        XCTAssertEqual(after ?? -1, 320.9, accuracy: 0.001)
    }

    /// B5: a moved flag remains a planning input after the tee shot; a Touch Target is not.
    func testMovedFlagChangesApproachPlanningDistance() {
        let distance = CurrentHoleView.caddiePlanningDistanceMetres(
            manualM: nil, isTeeShotOffTheHole: false,
            routeRemainingM: 140, liveMiddleM: 140, staticMiddleM: 140,
            holeYards: 351, pinM: 155, shotType: "approach"
        )
        XCTAssertEqual(distance ?? -1, 155, accuracy: 0.001)
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
