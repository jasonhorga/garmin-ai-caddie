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

    /// Before the hole's first shot the caddie plans from the tee unless the player is on it; a
    /// player 308 y from hole 1's green in the car park is not on the 397 y tee.
    func testTheTeeShotIsPlannedFromTheTeeUntilThePlayerIsThere() {
        let tee = CLLocationCoordinate2D(latitude: 45.5140, longitude: 10.4770)
        let carPark = CLLocationCoordinate2D(latitude: 45.5146, longitude: 10.4770)   // ~67 m away
        let teeBox = CLLocationCoordinate2D(latitude: 45.5142, longitude: 10.4770)    // ~22 m away
        XCTAssertTrue(CurrentHoleView.isTeeShotAwayFromTee(shotsRecorded: 0, fix: carPark, tee: tee))
        XCTAssertFalse(CurrentHoleView.isTeeShotAwayFromTee(shotsRecorded: 0, fix: teeBox, tee: tee))
        XCTAssertFalse(CurrentHoleView.isTeeShotAwayFromTee(shotsRecorded: 1, fix: carPark, tee: tee),
                       "after the first shot the live position plans wherever it is")
        XCTAssertFalse(CurrentHoleView.isTeeShotAwayFromTee(shotsRecorded: 0, fix: nil, tee: tee))
        XCTAssertFalse(CurrentHoleView.isTeeShotAwayFromTee(shotsRecorded: 0, fix: carPark, tee: nil),
                       "no tee anchor: the live position keeps its role")
    }
}
