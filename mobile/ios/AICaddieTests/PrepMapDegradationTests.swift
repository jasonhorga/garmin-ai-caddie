import CoreGraphics
import XCTest
@testable import AICaddie

/// B4c: 备战 and the README 地图降级契约 — which state each hole shows (precise / factual route /
/// the one waiting page), the faded hole strip, and that a background precise map replacing a
/// factual one keeps the player's hole, plan, zoom and pan.
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

    func testPreciseReplacementKeepsHolePlanZoomAndPan() throws {
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
        session.selectPlan(0, planCount: factualRows[1].plans.count)
        session.viewport = HoleMapViewportState(zoomScale: 2.5, offset: CGSize(width: -40, height: 18))
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
            planCount: preciseRows[1].plans.count
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

    // MARK: - Plans (方案), landings and club order

    private let planSteps = #"[{"club":"1D","note":"开球","targetCarry_m":210,"routeOffset_m":210,"role":"tee"},{"club":"8I","note":"攻果岭","targetCarry_m":150,"routeOffset_m":300,"expectedRemaining_m":0,"role":"approach"}]"#

    /// The fixture package with a real bag on its caddie seeds and package profiles, as a course
    /// template installed for a player with club history.
    private func bagPackage() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        var root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let bag: [(String, Double)] = [("1D", 210), ("7I", 156), ("8I", 144), ("9I", 132)]
        root["clubProfiles"] = bag.map { name, carry -> [String: Any] in
            ["clubName": name, "sampleSize": 20, "median_m": carry, "p10_m": carry - 10, "p90_m": carry + 10]
        }
        var profiles: [String: Any] = [:]
        for (name, carry) in bag {
            profiles[name] = ["clubName": name, "median": carry, "p10": carry - 10, "p90": carry + 10, "sampleSize": 20]
        }
        var seeds = try XCTUnwrap(root["caddieContextSeeds"] as? [[String: Any]])
        for index in seeds.indices {
            var context = seeds[index]["context"] as? [String: Any] ?? [:]
            context["clubProfiles"] = profiles
            seeds[index]["context"] = context
        }
        root["caddieContextSeeds"] = seeds
        return try JSONDecoder().decode(LiveRoundPackage.self, from: JSONSerialization.data(withJSONObject: root))
    }

    private func bagRows() throws -> (rows: [PrepHoleRow], prep: CoursePrepHole, template: LiveRoundPackage, hole: Hole) {
        let package = try bagPackage()
        let first = try XCTUnwrap(package.holes.min { $0.number < $1.number })
        let hole = try prep(hole: first.number, coverage: "ready", withMap: true, steps: planSteps)
        let template = package.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: package.course.globalId,
            holes: [hole],
            missingData: nil
        ))
        let rows = PrepHoleRows.build(
            template: template, fallbackHoleCount: 9, downloadActive: false,
            requiredRevisions: nil, topoURL: { _, _ in URL(fileURLWithPath: "/tmp/topo.png") }
        )
        return (rows, hole, template, first)
    }

    /// A precise prep row of `lengthM` straight metres (1 px = 1 m) with its installed chain.
    private func routePrep(hole: Int, par: Int, lengthM: Int, steps: String) throws -> CoursePrepHole {
        let json = #"""
        {"hole":\#(hole),"par":\#(par),"par_source":"courseview","blue_yards":\#(Int((Double(lengthM) * 1.09361).rounded())),\#
        "route_len_m":\#(lengthM),"route":[[120,\#(lengthM + 30)],[120,30]],"cautions":[],\#
        "hazards":{"water_carry":[],"bunkers":[]},"steps":\#(steps),"geometryCoverage":"ready","geometryRevision":"r1",\#
        "map":{"overlay":{"w":240,"h":\#(lengthM + 60),"ppm":1,"ln":\#(lengthM),"route":[[120,\#(lengthM + 30),0],[120,30,\#(lengthM)]]}}}
        """#
        return try JSONDecoder().decode(CoursePrepHole.self, from: Data(json.utf8))
    }

    /// What `CurrentHoleView` shows first on a fresh tee with no GPS fix, manual distance, map
    /// target, online response or player choice — built only from the functions live play calls:
    /// `caddieContextSeed`, `effectiveDistanceToPinMetres`, `makeCaddieDecisionRequest`,
    /// `makeOfflineCaddieDecision`, `resolvedCaddieRoutes` and `reconcileCaddieRoutes`.
    private func liveNoGPSTeeDefault(
        template: LiveRoundPackage,
        hole: Hole,
        prep: CoursePrepHole
    ) throws -> (route: CaddiePlanSequence, routes: [CaddiePlanSequence]) {
        let seed = try XCTUnwrap(LiveCaddieSeedFactory.resolve(package: template, hole: hole, prep: prep))
        let green = prep.greenDistances
        let distance = LiveCaddieDistance.resolve(
            manualM: nil,
            liveMiddleM: nil,
            staticMiddleM: green?.available == true ? green?.middleM : nil,
            holeYards: hole.yards
        )
        let base = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(
                shotType: "tee",
                distanceToPinM: distance,
                lie: "fairway",
                strategyMode: nil,
                requestedOptionId: caddieOptionId(forStrategyMode: nil)
            )
        )
        let request = CaddieDecisionRequestBuilder.addingCanonicalPlan(to: base, prep: prep)
        let offline = OfflineCaddieDecisionEvaluator().makeDecision(seed: seed, request: request, strategyMode: nil)
        let installed = LiveCaddieRouteAuthority.installedRoute(
            prep: prep,
            par: hole.par,
            shotType: "tee",
            fallbackRouteEndM: distance
        )
        let incoming = LiveCaddieRouteAuthority.resolve(
            installed: installed,
            online: nil,
            offline: offline,
            par: hole.par,
            shotType: "tee"
        )
        XCTAssertFalse(incoming.isEmpty, "live resolves a route for hole \(hole.number)")
        // reconcileCaddieRoutes on a fresh hole: nothing retained or explicitly chosen, and no
        // decision token yet (offline only), so the default is the first merged route.
        let first = LiveCaddieRouteAuthority.leadingRoute(
            incoming: incoming,
            existing: [],
            installed: installed,
            retained: nil,
            explicitSelectionKey: nil
        )
        let merged = LiveCaddieRouteAuthority.mergedRoutes(first: first, existing: [], incoming: incoming)
        let selected = try XCTUnwrap(
            LiveCaddieRouteAuthority.selected(routes: merged, preferredToken: nil, fallbackToken: nil)
        )
        return (selected, merged)
    }

    func testPrepDefaultPlanIsLivePlaysNoGPSTeeDefaultOnParThreeFourAndFive() throws {
        let package = try bagPackage()
        let holes = Dictionary(uniqueKeysWithValues: package.holes.map { ($0.number, $0) })
        let cases: [(par: Int, lengthM: Int, steps: String)] = [
            (3, 150, #"[{"club":"8I","note":"上果岭","targetCarry_m":150,"routeOffset_m":150,"expectedRemaining_m":0,"role":"scoring"}]"#),
            (4, 300, planSteps),
            (5, 475, #"[{"club":"1D","note":"开球","targetCarry_m":210,"routeOffset_m":210,"role":"tee"},{"club":"7I","note":"铺垫","targetCarry_m":156,"routeOffset_m":366,"role":"position"},{"club":"8I","note":"攻果岭","targetCarry_m":144,"routeOffset_m":475,"expectedRemaining_m":0,"role":"approach"}]"#),
        ]
        for testCase in cases {
            let hole = try XCTUnwrap(
                package.holes.sorted { $0.number < $1.number }.first { $0.par == testCase.par },
                "fixture: a Par \(testCase.par) hole"
            )
            XCTAssertNotNil(holes[hole.number])
            let prep = try routePrep(hole: hole.number, par: hole.par, lengthM: testCase.lengthM, steps: testCase.steps)
            let template = package.replacingCoursePrep(CoursePrepPackage(
                schema: "ai-caddie-course-prep-v1",
                globalId: package.course.globalId,
                holes: [prep],
                missingData: nil
            ))
            let live = try liveNoGPSTeeDefault(template: template, hole: hole, prep: prep)
            let plans = PrepPlanOption.options(template: template, hole: hole, prep: prep)
            let prepDefault = try XCTUnwrap(plans.first, "Par \(hole.par): prep has a default plan")

            // The same route, the same complete club chain, in the same plan order as live.
            XCTAssertEqual(prepDefault.id, live.route.id, "Par \(hole.par)")
            XCTAssertEqual(prepDefault.shots.map(\.clubName), live.route.steps.map(\.clubName), "Par \(hole.par)")
            XCTAssertEqual(plans.map(\.id), live.routes.map(\.id), "Par \(hole.par): plan order")
            // With an installed CoursePrep chain the default is that chain, named 推荐.
            XCTAssertEqual(prepDefault.id, LiveCaddieRouteAuthority.installedRouteId, "Par \(hole.par)")
            XCTAssertEqual(prepDefault.title, "推荐", "Par \(hole.par)")

            // 稳妥 and 进攻 are physically distinct alternatives (from the default and each other).
            let routesByID = Dictionary(uniqueKeysWithValues: live.routes.map { ($0.id, $0) })
            var alternatives: [CaddiePlanSequence] = []
            for title in ["稳妥", "进攻"] {
                let plan = try XCTUnwrap(plans.first { $0.title == title }, "Par \(hole.par) offers \(title)")
                alternatives.append(try XCTUnwrap(routesByID[plan.id]))
            }
            let signatures = ([live.route] + alternatives).map(LiveCaddieRouteAuthority.physicalSignature)
            XCTAssertEqual(Set(signatures).count, 3, "Par \(hole.par): 推荐 / 稳妥 / 进攻 are different routes")
        }
    }

    func testPlansComeFromTheLiveDecisionAuthorityAsDifferentCompleteRoutes() throws {
        let (rows, hole, template, first) = try bagRows()
        let plans = rows[0].plans
        XCTAssertGreaterThanOrEqual(plans.count, 2, "备战 offers at least two caddie plans")
        // The first plan is the installed CoursePrep chain (the decision engine's stock route).
        XCTAssertEqual(plans[0].title, "推荐")
        XCTAssertEqual(plans[0].steps.map(\.label), ["一号木 230", "八号铁 164"])
        XCTAssertEqual(Set(plans.map(\.title)).count, plans.count, "every plan has its own name")
        XCTAssertEqual(Set(plans.map { $0.steps.map(\.label) }).count, plans.count, "no two plans share a club order")
        // Exactly the routes live play resolves for this hole before any network or GPS.
        let authority = PrepPlanOption.decisionRoutes(template: template, hole: first, prep: hole)
        XCTAssertEqual(plans.map(\.id), authority.map(\.id))
        for (plan, route) in zip(plans, authority) {
            XCTAssertEqual(plan.shots.map(\.clubName), route.steps.map(\.clubName), "the complete stroke sequence")
        }
    }

    func testSelectingAnotherPlanDrawsAVisiblyDifferentPathWithLabelledLandings() throws {
        let (rows, hole, _, _) = try bagRows()
        let plans = rows[0].plans
        XCTAssertGreaterThanOrEqual(plans.count, 2)
        let overlay = try XCTUnwrap(hole.resolvedMapOverlay)
        let legSets = plans.prefix(2).map { plan in
            HoleImageMapView(hole: hole, showsCardChrome: false, plannedShots: plan.shots, drawsPlannedRouteInMap: false)
                .plannedLegs()
        }
        for (plan, legs) in zip(plans.prefix(2), legSets) {
            XCTAssertEqual(legs.count, plan.steps.count, "one leg per planned stroke")
            // Every landing on the map is labelled 球杆 + 码数, and reads exactly as the club order.
            let labels = PrepHoleMapHero.landingLabels(legs: legs, overlay: overlay)
            XCTAssertEqual(labels, plan.steps.map(\.label))
            for label in labels {
                XCTAssertNotNil(
                    label.range(of: #"^[^ ]+( [^ ]+)* \d+$"#, options: .regularExpression),
                    "\(label) is 球杆 + 码数"
                )
            }
        }
        let firstPath = legSets[0].map(\.destination)
        let secondPath = legSets[1].map(\.destination)
        XCTAssertNotEqual(firstPath, secondPath, "the second plan's landings are elsewhere on the hole")
        let firstLanding = try XCTUnwrap(firstPath.first)
        let secondLanding = try XCTUnwrap(secondPath.first)
        XCTAssertGreaterThan(
            hypot(firstLanding.x - secondLanding.x, firstLanding.y - secondLanding.y),
            10,
            "the tee shots land visibly apart"
        )
    }

    func testAPackageWithoutACaddieDecisionStillShowsTheInstalledChain() throws {
        let package = try fixturePackage()
        let first = try XCTUnwrap(package.holes.min { $0.number < $1.number })
        let hole = try prep(hole: first.number, coverage: "ready", withMap: true, steps: planSteps)
        let installed = try XCTUnwrap(PrepPlanOption.installedOption(prep: hole, par: 4))
        XCTAssertEqual(installed.steps.map(\.label), ["一号木 230", "八号铁 164"])
        XCTAssertEqual(installed.shots.map(\.clubName), ["1D", "8I"])
        XCTAssertNil(PrepPlanOption.installedOption(prep: try prep(coverage: "ready", withMap: true), par: 4))
        XCTAssertTrue(PrepPlanOption.options(template: package, hole: first, prep: nil).isEmpty)
    }

    func testSessionPlanFollowsTheSelectionAndIsClampedForDisplay() throws {
        let plans = try bagRows().rows[0].plans
        var session = PrepHoleMapSession()
        session.select(hole: 1)
        XCTAssertEqual(session.plan(in: plans), plans.first)
        session.selectPlan(1, planCount: plans.count)
        XCTAssertEqual(session.plan(in: plans), plans[1])
        XCTAssertEqual(session.plan(in: Array(plans.prefix(1))), plans[0])
        XCTAssertNil(session.plan(in: []))
    }

    // MARK: - Full-screen map surface

    /// The CI fixture's real prep hole (`server_v2/ci_fixture.py`): a 64 x 64 px square topo with
    /// the route running corner to corner, the shape Codex saw cropped in the real screenshots.
    private func squareDiagonalPrep(par: Int) throws -> CoursePrepHole {
        let json = """
        {"hole":1,"par":\(par),"par_source":"garmin","blue_yards":410,"route_len_m":375,\
        "route":[[0,0,0],[64,64,375]],"steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},\
        "geometryCoverage":"ready","geometryRevision":"fixture-r1",\
        "map":{"overlay":{"w":64,"h":64,"ppm":0.17,"ln":375,"route":[[0,0,0],[64,64,375]]}}}
        """
        return try JSONDecoder().decode(CoursePrepHole.self, from: Data(json.utf8))
    }

    /// An iPhone 16-sized 备战 layout: the viewport, its chrome insets and the chrome rects.
    private func iPhoneChrome() -> (viewport: CGSize, insets: PrepChromeLayout.Insets, chrome: [CGRect], contentFrame: CGRect) {
        let viewport = CGSize(width: 393, height: 852)
        let heroFrame = CGRect(origin: .zero, size: viewport)
        let contentFrame = CGRect(x: 0, y: 103, width: 393, height: 852 - 103 - 34)
        let insets = PrepChromeLayout.mapInsets(contentFrame: contentFrame, in: heroFrame)
        let chrome = PrepChromeLayout.exclusions(
            viewport: viewport,
            insets: insets,
            contentFrame: contentFrame,
            heroFrame: heroFrame,
            badgeNumber: 1,
            badgeSubtitle: "Par 4 · 410 码",
            measured: [],
            showsResetControl: false
        )
        return (viewport, insets, chrome, contentFrame)
    }

    private func legs(_ hole: CoursePrepHole, _ plan: PrepPlanOption) -> [MapPlannedLeg] {
        HoleImageMapView(
            hole: hole,
            showsCardChrome: false,
            plannedShots: plan.shots,
            drawsPlannedRouteInMap: false
        ).plannedLegs()
    }

    /// Fitted, every planned landing and its "球杆 码数" label are on screen and clear of the chrome
    /// — for the square diagonal fixture (two- and three-shot plans), a tall topo and a wide one.
    /// The previous whole-screen cover frame demonstrably cropped the square diagonal plan.
    func testFittedPrepMapShowsEveryLandingAndLabelForSquareTallAndWideTopos() throws {
        let layout = iPhoneChrome()
        let screen = CGRect(origin: .zero, size: layout.viewport)
        let content = CGRect(
            x: 0, y: layout.insets.top,
            width: layout.viewport.width,
            height: layout.viewport.height - layout.insets.top - layout.insets.bottom
        )
        var cases: [(name: String, hole: CoursePrepHole, plan: PrepPlanOption)] = []
        for par in [4, 5] {
            let hole = try squareDiagonalPrep(par: par)
            let plans = PrepRouteFixtures.routes(par: par, routeLengthM: 375).enumerated().compactMap { index, route in
                PrepPlanOption.option(route: route, index: index, par: par)
            }
            XCTAssertGreaterThanOrEqual(plans.count, 2)
            for plan in plans { cases.append(("square Par \(par) \(plan.title)", hole, plan)) }
        }
        let tall = try snapshotPrep(coverage: "ready")
        let wide = try JSONDecoder().decode(CoursePrepHole.self, from: Data("""
        {"hole":1,"par":5,"par_source":"courseview","blue_yards":543,"route_len_m":480,\
        "route":[[40,260],[520,240]],"steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},\
        "geometryCoverage":"ready","geometryRevision":"wide-r1",\
        "map":{"overlay":{"w":560,"h":300,"ppm":1.0,"ln":480,"route":[[40,260,0],[280,90,300],[520,240,480]]}}}
        """.utf8))
        for (name, hole) in [("tall", tall), ("wide diagonal", wide)] {
            let length: Double = name == "tall" ? 375 : 480
            let plans = PrepRouteFixtures.routes(par: 5, routeLengthM: length).enumerated().compactMap { index, route in
                PrepPlanOption.option(route: route, index: index, par: 5)
            }
            for plan in plans { cases.append(("\(name) \(plan.title)", hole, plan)) }
        }
        var sawThreeShots = false
        for testCase in cases {
            let overlay = try XCTUnwrap(testCase.hole.resolvedMapOverlay)
            let planLegs = legs(testCase.hole, testCase.plan)
            XCTAssertEqual(planLegs.count, testCase.plan.steps.count, "\(testCase.name): one leg per stroke")
            sawThreeShots = sawThreeShots || planLegs.count == 3
            let rest = try XCTUnwrap(PrepMapLayout.fittedRestFrame(
                overlay: overlay,
                legs: planLegs,
                viewport: layout.viewport,
                insets: layout.insets,
                chrome: layout.chrome
            ))
            XCTAssertEqual(rest.width / CGFloat(overlay.w), rest.height / CGFloat(overlay.h), accuracy: 0.0001)
            let landings = PrepHoleMapHero.screenLandings(
                legs: planLegs, overlay: overlay, size: layout.viewport,
                scale: 1, offset: .zero, topInset: layout.insets.top, rest: rest
            )
            XCTAssertEqual(landings.count, planLegs.count)
            for (index, point) in landings.enumerated() {
                XCTAssertTrue(content.contains(point), "\(testCase.name): landing \(index + 1) at \(point) is between the chrome")
            }
            if let tee = planLegs.first.flatMap({
                LivePlannedRouteRenderer.transformedPoint(
                    $0.origin, size: layout.viewport, overlay: overlay, scale: 1, offset: .zero,
                    topInset: layout.insets.top, fittedFrame: rest
                )
            }) {
                XCTAssertTrue(content.contains(tee), "\(testCase.name): the tee at \(tee) is between the chrome")
            }
            let labels = LivePlannedRouteRenderer.placedRouteLabels(
                size: layout.viewport,
                legs: planLegs,
                overlay: overlay,
                scale: 1,
                offset: .zero,
                topInset: layout.insets.top,
                fittedFrame: rest,
                exclusions: layout.chrome
            )
            XCTAssertEqual(labels.map(\.text), PrepHoleMapHero.landingLabels(legs: planLegs, overlay: overlay))
            for label in labels {
                let rect = try XCTUnwrap(label.rect, "\(testCase.name): \(label.text) is placed at rest")
                XCTAssertTrue(screen.contains(rect), "\(testCase.name): \(label.text) at \(rect) is on screen")
                for excluded in layout.chrome {
                    XCTAssertFalse(rect.intersects(excluded), "\(testCase.name): \(label.text) under chrome \(excluded)")
                }
            }
        }
        XCTAssertTrue(sawThreeShots, "a three-shot plan is covered")

        // The old fitted frame (the whole-screen cover) cropped the square diagonal plan: at least
        // one landing fell outside the space between the chrome.
        let square = try squareDiagonalPrep(par: 4)
        let squareOverlay = try XCTUnwrap(square.resolvedMapOverlay)
        let squarePlan = try XCTUnwrap(PrepRouteFixtures.routes(par: 4, routeLengthM: 375).enumerated().compactMap { index, route in
            PrepPlanOption.option(route: route, index: index, par: 4)
        }.first)
        let oldFrame = try XCTUnwrap(PrepMapLayout.coverFrame(
            overlayWidth: 64, overlayHeight: 64, route: squareOverlay.route,
            viewport: layout.viewport, topInset: layout.insets.top, bottomInset: layout.insets.bottom
        ))
        let oldLandings = PrepHoleMapHero.screenLandings(
            legs: legs(square, squarePlan), overlay: squareOverlay, size: layout.viewport,
            scale: 1, offset: .zero, topInset: layout.insets.top, rest: oldFrame
        )
        XCTAssertTrue(oldLandings.contains { !content.contains($0) }, "the cover frame crops the diagonal plan: \(oldLandings)")
    }

    func testFittedPrepMapCoversTheScreenItselfWhenThePlanAllowsIt() throws {
        let viewport = CGSize(width: 390, height: 844)
        // A tall topo with a short straight route: the aspect fill already shows it all.
        let frame = try XCTUnwrap(PrepMapLayout.restFrame(
            overlayWidth: 240,
            overlayHeight: 360,
            route: [[120, 250, 0], [120, 160, 90]],
            viewport: viewport,
            topInset: 150,
            bottomInset: 210
        ))
        XCTAssertTrue(PrepMapLayout.covers(frame, viewport: viewport), "\(frame)")
        XCTAssertEqual(frame.width / 240, max(390 / 240, 844 / 360), accuracy: 0.0001)
        // Its route sits between the chrome.
        let scale = frame.width / 240
        for y in [250.0, 160.0] {
            let screenY = frame.minY + CGFloat(y) * scale
            XCTAssertGreaterThanOrEqual(screenY, 150 + PrepMapLayout.routeMargin - 0.5)
            XCTAssertLessThanOrEqual(screenY, 844 - 210 - PrepMapLayout.routeMargin + 0.5)
        }
        // The same topo with a route longer than the space between the chrome shrinks to show it all.
        let long = try XCTUnwrap(PrepMapLayout.restFrame(
            overlayWidth: 240,
            overlayHeight: 360,
            route: [[120, 350, 0], [120, 10, 340]],
            viewport: viewport,
            topInset: 150,
            bottomInset: 210
        ))
        let longScale = long.width / 240
        XCTAssertLessThan(longScale, max(390 / 240, 844 / 360))
        XCTAssertGreaterThanOrEqual(long.minY + 10 * longScale, 150 + PrepMapLayout.routeMargin - 0.5)
        XCTAssertLessThanOrEqual(long.minY + 350 * longScale, 844 - 210 - PrepMapLayout.routeMargin + 0.5)
    }

    // MARK: - Route labels vs the chrome

    /// The design-snapshot hole: a 240 x 360 px Par 5 map, 1 px = 1 m, 375 m from tee to green.
    private func snapshotPrep(coverage: String) throws -> CoursePrepHole {
        let json = """
        {"hole":1,"par":5,"par_source":"courseview","blue_yards":543,"route_len_m":375,\
        "route":[[120,330],[118,180],[120,55]],"steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},\
        "geometryCoverage":"\(coverage)","geometryRevision":"snapshot-r1",\
        "map":{"overlay":{"w":240,"h":360,"ppm":1.0,"ln":375,"route":[[120,330,0],[118,180,150],[120,55,375]]}}}
        """
        return try JSONDecoder().decode(CoursePrepHole.self, from: Data(json.utf8))
    }

    func testRouteLabelsStayWhollyClearOfThePrepChromeFittedAndZoomed() throws {
        let viewport = CGSize(width: 390, height: 844)
        // An iPhone-sized layout: status bar + navigation bar above the content, home indicator below.
        let safeTop: CGFloat = 103
        let safeBottom: CGFloat = 34
        let heroFrame = CGRect(origin: .zero, size: viewport)
        let contentFrame = CGRect(x: 0, y: safeTop, width: viewport.width, height: viewport.height - safeTop - safeBottom)
        let insets = PrepChromeLayout.mapInsets(contentFrame: contentFrame, in: heroFrame)
        XCTAssertEqual(insets, PrepChromeLayout.Insets(
            top: safeTop + PrepChromeLayout.badgeRowHeight,
            bottom: safeBottom + PrepChromeLayout.bottomPanelHeight
        ))
        // The badge and panel as the screen lays them out (badge text "1 Par 5 · 543 码").
        let badgeWidth = PrepChromeLayout.badgeWidth(number: 1, subtitle: "Par 5 · 543 码")
        XCTAssertGreaterThan(badgeWidth, 110, "the badge text is measured, not guessed")
        XCTAssertLessThan(badgeWidth, 220)
        let badge = CGRect(x: 16, y: safeTop + PrepChromeLayout.badgeTopPadding, width: badgeWidth, height: 40)
        let panel = CGRect(x: 12, y: viewport.height - safeBottom - 8 - 156, width: viewport.width - 24, height: 156)
        // The first frame: nothing measured yet, and the badge and panel are already excluded.
        let firstFrame = PrepChromeLayout.exclusions(
            viewport: viewport,
            insets: insets,
            contentFrame: contentFrame,
            heroFrame: heroFrame,
            badgeNumber: 1,
            badgeSubtitle: "Par 5 · 543 码",
            measured: [],
            showsResetControl: false
        )
        for chromeRect in [badge, panel] {
            XCTAssertTrue(
                firstFrame.contains { $0.contains(chromeRect) },
                "unmeasured first frame already excludes \(chromeRect)"
            )
        }
        let chrome = PrepChromeLayout.exclusions(
            viewport: viewport,
            insets: insets,
            contentFrame: contentFrame,
            heroFrame: heroFrame,
            badgeNumber: 1,
            badgeSubtitle: "Par 5 · 543 码",
            measured: [badge, panel],
            showsResetControl: false
        )
        XCTAssertTrue(chrome.contains(badge) && chrome.contains(panel), "measured rects only extend the set")

        let precise = try snapshotPrep(coverage: "ready")
        let factual = try snapshotPrep(coverage: "partial")
        let plans = PrepRouteFixtures.routes(par: 5, routeLengthM: 375).enumerated().compactMap { index, route in
            PrepPlanOption.option(route: route, index: index, par: 5)
        }
        XCTAssertEqual(plans.map(\.title), ["推荐", "稳妥", "进攻"])
        let overlay = try XCTUnwrap(precise.resolvedMapOverlay)

        let cases: [(name: String, hole: CoursePrepHole, plan: PrepPlanOption, scale: CGFloat, offset: CGSize)] = [
            ("plan 1", precise, plans[0], 1, .zero),
            ("plan 2", precise, plans[1], 1, .zero),
            ("factual", factual, plans[0], 1, .zero),
            ("zoomed", precise, plans[0], 2, CGSize(width: -30, height: 40)),
            ("zoomed far", precise, plans[1], 3, CGSize(width: 120, height: 400)),
        ]
        let screen = CGRect(origin: .zero, size: viewport)
        for testCase in cases {
            let fitted = testCase.scale <= 1.01
            let planLegs = legs(testCase.hole, testCase.plan)
            // The fitted frame is laid out against the chrome at rest (no reset control).
            let rest = try XCTUnwrap(PrepMapLayout.fittedRestFrame(
                overlay: overlay,
                legs: planLegs,
                viewport: viewport,
                insets: insets,
                chrome: chrome
            ))
            let offset = LivePlayMapOverlayLayout.clampedOffset(
                testCase.offset,
                mapFrame: rest,
                viewportSize: viewport,
                scale: testCase.scale
            )
            var exclusions = chrome
            if !fitted {
                exclusions.append(PrepChromeLayout.resetControl(viewport: viewport, topInset: insets.top))
                XCTAssertEqual(exclusions, PrepChromeLayout.exclusions(
                    viewport: viewport,
                    insets: insets,
                    contentFrame: contentFrame,
                    heroFrame: heroFrame,
                    badgeNumber: 1,
                    badgeSubtitle: "Par 5 · 543 码",
                    measured: [badge, panel],
                    showsResetControl: true
                ))
            }
            let labels = LivePlannedRouteRenderer.placedRouteLabels(
                size: viewport,
                legs: planLegs,
                overlay: overlay,
                scale: testCase.scale,
                offset: offset,
                topInset: insets.top,
                fittedFrame: rest,
                exclusions: exclusions
            )
            XCTAssertEqual(labels.count, testCase.plan.steps.count, "\(testCase.name): one label per stroke")
            // The rects are laid out with the renderer's own label measurement.
            for label in labels {
                guard let rect = label.rect else {
                    XCTAssertFalse(fitted, "\(testCase.name): at rest every stroke's label is placed (\(label.text))")
                    continue
                }
                XCTAssertEqual(rect.size, LivePlannedRouteRenderer.routeLabelSize(for: label.text, isTeeLabel: false))
                XCTAssertTrue(screen.contains(rect), "\(testCase.name): \(label.text) at \(rect) is on screen")
                for excluded in exclusions {
                    XCTAssertFalse(
                        rect.intersects(excluded),
                        "\(testCase.name): \(label.text) at \(rect) is partly under chrome \(excluded)"
                    )
                }
            }
        }
    }

    /// Root cause of the first-render overlap: the full-screen map read the content area's
    /// (near-zero) safe-area insets as its own, so the fallback band ended above the hole badge.
    /// The insets now come from the content frame in the map's own coordinates.
    func testPrepChromeInsetsComeFromTheContentFrameInTheMapsCoordinates() {
        let heroFrame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let contentFrame = CGRect(x: 0, y: 103, width: 390, height: 707)
        let insets = PrepChromeLayout.mapInsets(contentFrame: contentFrame, in: heroFrame)
        XCTAssertEqual(insets.top, 103 + PrepChromeLayout.badgeRowHeight)
        XCTAssertEqual(insets.bottom, 34 + PrepChromeLayout.bottomPanelHeight)
        // The badge (content top + 12, 40 pt tall) lies wholly inside the top band, and the
        // computed badge sits there, below the header (never at the map's own y = 12).
        let badgeBottom = contentFrame.minY + PrepChromeLayout.badgeTopPadding + 40
        XCTAssertLessThanOrEqual(badgeBottom, insets.top)
        let badge = PrepChromeLayout.badge(contentFrame: contentFrame, in: heroFrame, number: 1, subtitle: "Par 5 · 543 码")
        XCTAssertEqual(badge.minY, 103 + PrepChromeLayout.badgeTopPadding - PrepChromeLayout.badgeSlack)
        XCTAssertEqual(badge.minX, PrepChromeLayout.badgeLeadingPadding - PrepChromeLayout.badgeSlack)
        XCTAssertEqual(
            PrepChromeLayout.header(contentFrame: contentFrame, in: heroFrame),
            CGRect(x: 0, y: 0, width: 390, height: 103)
        )
        // An unmeasured content frame still reserves the badge row and panel.
        XCTAssertEqual(
            PrepChromeLayout.mapInsets(contentFrame: .zero, in: heroFrame),
            PrepChromeLayout.Insets(top: PrepChromeLayout.badgeRowHeight, bottom: PrepChromeLayout.bottomPanelHeight)
        )
    }

    func testLiveLabelLayoutHasNoExclusionsByDefault() {
        let request = LivePlannedRouteRenderer.LabelRequest(
            size: CGSize(width: 90, height: 24),
            candidates: [CGPoint(x: 100, y: 50)]
        )
        let viewportRect = CGRect(x: 4, y: 4, width: 382, height: 836)
        XCTAssertEqual(
            LivePlannedRouteRenderer.layoutLabels([request], viewport: viewportRect, obstacles: [], samples: []),
            [CGRect(x: 55, y: 38, width: 90, height: 24)]
        )
        // The same label under a chrome rect with no other candidate is omitted, not covered.
        let omitted = LivePlannedRouteRenderer.layoutLabelsAvoiding(
            [request],
            viewport: viewportRect,
            obstacles: [],
            samples: [],
            exclusions: [CGRect(x: 0, y: 0, width: 390, height: 120)]
        )
        XCTAssertEqual(omitted.count, 1)
        XCTAssertNil(omitted[0])
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
