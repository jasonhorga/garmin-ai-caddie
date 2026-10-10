import CoreLocation
import XCTest
@testable import AICaddie

/// 打法 pager on the live hole (2026-10-10 field report: "1/3" and "2/3" but never "3/3"), and the
/// tee shot planned from the tee rather than from a player still walking up to it.
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

    /// Selecting a route already shown keeps every route's place.
    func testSelectingALaterRouteKeepsThePagerOrder() {
        let shown = [driver, safe, layup]
        let merged = LiveCaddieRouteAuthority.mergedRoutes(first: safe, existing: shown, incoming: shown)
        XCTAssertEqual(merged.map(\.id), ["installed-course-plan", "safe", "layup"])
    }

    /// Paging the way the live view does (select next, reconcile with the explicit selection
    /// leading) reaches every route and comes back round. Moving the selection to the front
    /// alternated between the first two and never reached the third.
    func testPagingReachesEveryRoute() {
        var routes = [driver, safe, layup]
        var selected = LiveCaddieRouteAuthority.routeSignature(driver)
        var visited: [String] = []
        for _ in 0..<3 {
            let index = routes.firstIndex { LiveCaddieRouteAuthority.routeSignature($0) == selected } ?? 0
            let next = routes[(index + 1) % routes.count]
            selected = LiveCaddieRouteAuthority.routeSignature(next)
            let first = LiveCaddieRouteAuthority.leadingRoute(
                incoming: routes, existing: routes, installed: driver, retained: driver,
                explicitSelectionKey: selected
            )
            routes = LiveCaddieRouteAuthority.mergedRoutes(first: first, existing: routes, incoming: routes)
            let position = routes.firstIndex { LiveCaddieRouteAuthority.routeSignature($0) == selected }
            visited.append("\((position ?? -1) + 1)/\(routes.count)")
        }
        XCTAssertEqual(visited, ["2/3", "3/3", "1/3"])
    }

    /// A new leading route (a fresh hole, or a route not shown before) still comes first.
    func testANewLeadingRouteStillComesFirst() {
        XCTAssertEqual(
            LiveCaddieRouteAuthority.mergedRoutes(first: safe, existing: [], incoming: [driver, safe]).map(\.id),
            ["safe", "installed-course-plan"]
        )
        XCTAssertEqual(
            LiveCaddieRouteAuthority.mergedRoutes(first: layup, existing: [driver], incoming: [layup, safe]).map(\.id),
            ["layup", "installed-course-plan", "safe"]
        )
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
