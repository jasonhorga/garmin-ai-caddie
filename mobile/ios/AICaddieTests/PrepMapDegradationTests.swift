import CoreGraphics
import XCTest
@testable import AICaddie

/// B4c: 备战 and the README 地图降级契约 — which state each hole shows (precise / factual route /
/// the one waiting page), the faded hole strip, and that a background precise map replacing a
/// factual one keeps the player's hole, plan, zoom, pan and rotation.
final class PrepMapDegradationTests: XCTestCase {
    private let overlayJSON = #""map":{"overlay":{"w":240,"h":360,"ppm":1,"ln":300,"route":[[120,330,0],[120,30,300]]}}"#

    private func prep(
        hole: Int = 1,
        coverage: String?,
        withMap: Bool,
        revision: String? = "r1",
        steps: String = "[]"
    ) throws -> CoursePrepHole {
        var fields = [
            #""hole":\#(hole),"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":300"#,
            #""route":[[120,330],[120,30]],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]}"#,
            "\"steps\":\(steps)",
        ]
        if let coverage { fields.append("\"geometryCoverage\":\"\(coverage)\"") }
        if let revision { fields.append("\"geometryRevision\":\"\(revision)\"") }
        if withMap { fields.append(overlayJSON) }
        return try JSONDecoder().decode(CoursePrepHole.self, from: Data("{\(fields.joined(separator: ","))}".utf8))
    }

    private func fixturePackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        return try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: url))
    }

    // MARK: - Which state a hole shows

    func testPrepHoleStatesFollowTheOneDegradationContract() throws {
        // Nothing drawable (no facts, or facts without a route projection): the waiting page.
        XCTAssertEqual(
            LiveMapDisplayState.resolvePrep(prep: nil, hasLocalTopo: false, isStale: false, downloadActive: true),
            .waiting
        )
        XCTAssertEqual(
            LiveMapDisplayState.resolvePrep(
                prep: try prep(coverage: "missing", withMap: false), hasLocalTopo: false, isStale: false, downloadActive: true
            ),
            .waiting
        )
        // A drawable factual route shows at once, whether or not the precise map is still coming.
        let partial = try prep(coverage: "partial", withMap: true)
        XCTAssertEqual(
            LiveMapDisplayState.resolvePrep(prep: partial, hasLocalTopo: false, isStale: false, downloadActive: true),
            .factualPending
        )
        XCTAssertEqual(
            LiveMapDisplayState.resolvePrep(prep: partial, hasLocalTopo: false, isStale: false, downloadActive: false),
            .factual
        )
        // Precise facts are not the precise map until the revision-bound topo is installed.
        let ready = try prep(coverage: "ready", withMap: true)
        XCTAssertEqual(
            LiveMapDisplayState.resolvePrep(prep: ready, hasLocalTopo: false, isStale: false, downloadActive: true),
            .factualPending
        )
        XCTAssertEqual(
            LiveMapDisplayState.resolvePrep(prep: ready, hasLocalTopo: true, isStale: false, downloadActive: false),
            .precise
        )
        // A local topo the server has positively replaced is withheld until the new one lands.
        XCTAssertEqual(
            LiveMapDisplayState.resolvePrep(prep: ready, hasLocalTopo: true, isStale: true, downloadActive: true),
            .factualPending
        )
    }

    func testOnlyThePreciseMapIsUnfadedInTheHoleStrip() {
        XCTAssertFalse(LiveMapDisplayState.precise.fadesInHoleStrip)
        for state in [LiveMapDisplayState.factual, .factualPending, .waiting] {
            XCTAssertTrue(state.fadesInHoleStrip, "\(state) is not ready and is faded")
        }
    }

    func testWaitingPageNamesTheHoleParAndYardsWithoutDownloadWording() {
        let page = HoleMapWaitingPage(holeNumber: 14, par: 4, yards: 405)
        XCTAssertEqual(page.title, "第 14 洞 · Par 4")
        XCTAssertEqual(page.subtitle, "405 码 · 图到了自动出来")
        let unknown = HoleMapWaitingPage(holeNumber: 3, par: nil, yards: nil)
        XCTAssertEqual(unknown.title, "第 3 洞")
        XCTAssertEqual(unknown.subtitle, "图到了自动出来")
        for text in [page.title, page.subtitle, unknown.subtitle] {
            XCTAssertFalse(text.contains("下载"))
        }
    }

    // MARK: - Rows from the installed template

    func testSelectedCourseWithoutATemplateOpensOnWaitingRows() {
        let rows = PrepHoleRows.build(
            template: nil,
            fallbackHoleCount: 18,
            downloadActive: true,
            requiredRevisions: nil,
            topoURL: { _, _ in XCTFail("no template, no topo lookup"); return nil }
        )
        XCTAssertEqual(rows.map(\.number), Array(1...18))
        XCTAssertTrue(rows.allSatisfy { $0.state == .waiting })
        XCTAssertTrue(rows.allSatisfy { $0.par == nil && $0.prep == nil })
    }

    func testRowsResolveEachInstalledHoleIndependently() throws {
        let package = try fixturePackage()
        let holes = package.holes.sorted { $0.number < $1.number }
        XCTAssertGreaterThanOrEqual(holes.count, 3)
        let template = package.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: package.course.globalId,
            holes: [
                try prep(hole: holes[0].number, coverage: "ready", withMap: true),
                try prep(hole: holes[1].number, coverage: "partial", withMap: true),
                try prep(hole: holes[2].number, coverage: "missing", withMap: false),
            ],
            missingData: nil
        ))
        let topo = URL(fileURLWithPath: "/tmp/topo-1.png")
        var lookups: [Int] = []
        let rows = PrepHoleRows.build(
            template: template,
            fallbackHoleCount: 18,
            downloadActive: true,
            requiredRevisions: nil,
            topoURL: { hole, revision in
                lookups.append(hole.number)
                XCTAssertEqual(revision, "r1", "the topo is bound to the prep row's geometry revision")
                return hole.number == holes[0].number ? topo : nil
            }
        )
        XCTAssertEqual(rows.map(\.number), holes.map(\.number))
        XCTAssertEqual(rows[0].state, .precise)
        XCTAssertEqual(rows[0].topoURL, topo)
        XCTAssertEqual(rows[1].state, .factualPending)
        XCTAssertNil(rows[1].topoURL)
        XCTAssertEqual(rows[2].state, .waiting)
        // A hole the download has not reached yet has no facts: the waiting page, no topo lookup.
        XCTAssertTrue(rows.dropFirst(3).allSatisfy { $0.state == .waiting && $0.prep == nil })
        XCTAssertEqual(lookups, holes.prefix(3).map(\.number))
        // B4b-2: the player sees the course's own hole number, and the package's Par/yards when the
        // facts have not arrived.
        for (row, hole) in zip(rows, holes) {
            XCTAssertEqual(row.displayNumber, hole.courseHoleNumber)
        }
        XCTAssertEqual(rows[3].par, holes[3].par)
        XCTAssertEqual(rows[3].yards, holes[3].yards)
    }

    func testPositivelyReplacedRevisionShowsTheFactualRouteUntilTheNewMapInstalls() throws {
        let package = try fixturePackage()
        let first = try XCTUnwrap(package.holes.min { $0.number < $1.number })
        let template = package.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: package.course.globalId,
            holes: [try prep(hole: first.number, coverage: "ready", withMap: true, revision: "r1")],
            missingData: nil
        ))
        let key = "\(first.sourceGlobalId):\(first.sourceLocalHole)"
        let topo = URL(fileURLWithPath: "/tmp/topo-1.png")
        let stale = PrepHoleRows.build(
            template: template, fallbackHoleCount: 9, downloadActive: true,
            requiredRevisions: [key: " R2 "], topoURL: { _, _ in topo }
        )
        XCTAssertEqual(stale[0].state, .factualPending)
        XCTAssertNil(stale[0].topoURL, "the replaced topo is never presented as current")
        let current = PrepHoleRows.build(
            template: template, fallbackHoleCount: 9, downloadActive: false,
            requiredRevisions: [key: " R1 "], topoURL: { _, _ in topo }
        )
        XCTAssertEqual(current[0].state, .precise)
    }

    // MARK: - The screen state survives a map replacement

    func testPreciseReplacementKeepsHolePlanZoomPanAndRotation() throws {
        let package = try fixturePackage()
        let holes = package.holes.sorted { $0.number < $1.number }
        let second = holes[1]
        let steps = #"[{"club":"1D","note":"开球","targetCarry_m":210},{"club":"8I","note":"攻果岭","targetCarry_m":150}]"#
        func template(_ coverage: String) throws -> LiveRoundPackage {
            package.replacingCoursePrep(CoursePrepPackage(
                schema: "ai-caddie-course-prep-v1",
                globalId: package.course.globalId,
                holes: [try prep(hole: second.number, coverage: coverage, withMap: true, steps: steps)],
                missingData: nil
            ))
        }
        let topo = URL(fileURLWithPath: "/tmp/topo-2.png")
        let factualRows = PrepHoleRows.build(
            template: try template("partial"), fallbackHoleCount: 9, downloadActive: true,
            requiredRevisions: nil, topoURL: { _, _ in nil }
        )
        var session = PrepHoleMapSession()
        session.adopt(holeNumbers: factualRows.map(\.number), planCount: 0)
        XCTAssertEqual(session.holeNumber, holes[0].number, "nothing shown yet: the first hole")
        session.select(hole: second.number)
        let plans = PrepPlanOption.options(for: factualRows[1].prep)
        session.selectPlan(0, planCount: plans.count)
        session.viewport = HoleMapViewportState(rotationDegrees: 32, zoomScale: 2.5, offset: CGSize(width: -40, height: 18))
        let before = session

        // The background download installs hole 2's precise facts and topo.
        let preciseRows = PrepHoleRows.build(
            template: try template("ready"), fallbackHoleCount: 9, downloadActive: false,
            requiredRevisions: nil, topoURL: { hole, _ in hole.number == second.number ? topo : nil }
        )
        XCTAssertEqual(factualRows[1].state, .factualPending)
        XCTAssertEqual(preciseRows[1].state, .precise)
        session.adopt(
            holeNumbers: preciseRows.map(\.number),
            planCount: PrepPlanOption.options(for: preciseRows[1].prep).count
        )
        XCTAssertEqual(session, before, "a precise map replacing the factual one resets nothing")
        XCTAssertFalse(session.viewport.isFitted)

        // Only an explicit hole change starts the next hole fitted.
        session.select(hole: second.number)
        XCTAssertEqual(session, before, "re-selecting the shown hole keeps it as it is")
        session.select(hole: holes[2].number)
        XCTAssertEqual(session.viewport, HoleMapViewportState())
        XCTAssertTrue(session.viewport.isFitted)
        XCTAssertEqual(session.selectedPlanIndex, 0)
    }

    func testFactsForAnotherHoleSetMoveTheSessionOnlyWhenItsHoleIsGone() {
        var session = PrepHoleMapSession()
        session.select(hole: 5)
        session.viewport.zoomScale = 3
        session.adopt(holeNumbers: Array(1...18), planCount: 2)
        XCTAssertEqual(session.holeNumber, 5)
        XCTAssertEqual(session.viewport.zoomScale, 3)
        // A Tee with a 9-hole template: hole 5 still exists, nothing moves.
        session.adopt(holeNumbers: Array(1...9), planCount: 1)
        XCTAssertEqual(session.holeNumber, 5)
        XCTAssertEqual(session.viewport.zoomScale, 3)
        // The shown hole no longer exists: start at the first hole, fitted.
        session.adopt(holeNumbers: [10, 11], planCount: 1)
        XCTAssertEqual(session.holeNumber, 10)
        XCTAssertTrue(session.viewport.isFitted)
    }

    func testPlanIndexIsClampedOnlyWhenTheHoleHasFewerPlans() {
        var session = PrepHoleMapSession()
        session.select(hole: 1)
        session.selectPlan(1, planCount: 2)
        XCTAssertEqual(session.selectedPlanIndex, 1)
        session.selectPlan(4, planCount: 2)
        XCTAssertEqual(session.selectedPlanIndex, 1, "an index outside the plans is ignored")
        session.adopt(holeNumbers: [1], planCount: 0)
        XCTAssertEqual(session.selectedPlanIndex, 1, "a hole with no plan yet keeps the choice")
        session.adopt(holeNumbers: [1], planCount: 1)
        XCTAssertEqual(session.selectedPlanIndex, 0)
    }

    func testFactualToPreciseReplacementOnTheSameFrameKeepsTargetAndFlag() {
        // Target and flag carry-over is the shared live rule (LiveMapCarryOver); the same hole's
        // factual and precise rows share their overlay frame in the degraded fixture as in production.
        let frame = CoursePrepOverlay(w: 240, h: 360, ppm: 1, ln: 300, route: [[120, 330, 0], [120, 30, 300]])
        for point in [CGPoint(x: 101, y: 207), CGPoint(x: 120, y: 40)] {
            XCTAssertEqual(LiveMapCarryOver.transfer(point, from: frame, to: frame), point)
        }
    }

    // MARK: - Plan and club order

    func testClubOrderUsesEachStepsOwnCarryInYards() throws {
        let steps = #"[{"club":"1D","note":"开球","targetCarry_m":210},{"clubName":"8I","note":"攻果岭","targetCarry_m":150},{"club":"","note":"推杆"}]"#
        let options = PrepPlanOption.options(for: try prep(coverage: "ready", withMap: true, steps: steps))
        XCTAssertEqual(options.count, 1)
        XCTAssertEqual(options[0].title, "球童建议")
        XCTAssertEqual(options[0].steps.map(\.label), ["一号木 230", "八号铁 164"])
        XCTAssertTrue(PrepPlanOption.options(for: try prep(coverage: "ready", withMap: true)).isEmpty)
        XCTAssertTrue(PrepPlanOption.options(for: nil).isEmpty)
    }

    func testHeaderSubtitleAndStateDescriptionNeverNameTheDownload() {
        XCTAssertEqual(CoursePrepStrategyScreen.holeSubtitle(par: 5, yards: 543), "Par 5 · 543 码")
        XCTAssertEqual(CoursePrepStrategyScreen.holeSubtitle(par: 4, yards: nil), "Par 4")
        XCTAssertNil(CoursePrepStrategyScreen.holeSubtitle(par: nil, yards: nil))
        for state in [LiveMapDisplayState.precise, .factual, .factualPending, .waiting] {
            XCTAssertFalse(CoursePrepStrategyScreen.mapStateDescription(state).contains("下载"))
        }
    }
}
