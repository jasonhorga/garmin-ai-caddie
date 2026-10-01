@testable import AICaddie
import XCTest

/// B4c 方案 (Codex 5925193109 / 5925370774): the CI fixture's journey courses
/// (`Fixtures/b4c_journey_plan_inputs.json`, kept in lock-step with `server_v2/ci_fixture.py` by
/// `tests/test_prep_render_shapes_fixture.py`), fed to the production plan authority exactly as the
/// phone does: the degraded course's factual hole 2 (`PrepDegradationUITests` switches plans on it),
/// the Palace's hole 1 (RealFlow's 备战 card and the fully offline start) and Black Knight's hole 1.
/// Each must offer the installed Driver chain as a complete route and one genuinely 稳妥 whole-hole
/// alternative — never an incomplete prefix and never a cosmetic duplicate.
final class PrepJourneyPlansTests: XCTestCase {
    private struct CourseInputs: Decodable {
        let hole: Int
        let package: LiveRoundPackage
        let prep: CoursePrepResponse
    }

    private struct Inputs: Decodable {
        let degraded: CourseInputs
        let palace: CourseInputs
        let blackKnight: CourseInputs
    }

    private func inputs() throws -> Inputs {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: PrepJourneyPlansTests.self)
        #endif
        let url = try XCTUnwrap(
            bundle.url(forResource: "b4c_journey_plan_inputs", withExtension: "json", subdirectory: "Fixtures")
                ?? bundle.url(forResource: "b4c_journey_plan_inputs", withExtension: "json")
        )
        return try JSONDecoder().decode(Inputs.self, from: Data(contentsOf: url))
    }

    func testEveryJourneyHoleOffersTheCompleteDriverChainAndAGenuinelySaferThreeWoodChain() throws {
        let inputs = try inputs()
        for (name, course, coverage) in [
            ("degraded", inputs.degraded, "partial"),
            ("palace", inputs.palace, "ready"),
            ("blackKnight", inputs.blackKnight, "ready"),
        ] {
            try assertJourneyPlans(name, course, coverage: coverage)
        }
    }

    private func assertJourneyPlans(_ name: String, _ course: CourseInputs, coverage: String) throws {
        let prep = try XCTUnwrap(course.prep.holes.first { $0.hole == course.hole }, name)
        XCTAssertEqual(prep.geometryCoverage, coverage, name)
        // Coverage describes the bag truthfully (the prep panel's 球杆 count; the offline start).
        XCTAssertEqual(course.package.sourceCoverage.clubProfileCount, course.package.clubProfiles.count, name)
        let hole = try XCTUnwrap(course.package.holes.first { $0.number == course.hole }, name)
        let template = course.package.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: course.package.course.globalId,
            holes: [prep],
            missingData: nil
        ))

        // The phone's local decision (prep and the downloaded/offline live round) completes the
        // installed chain: it is the selected route, and it ends in the scoring window.
        let decision = try XCTUnwrap(
            PrepPlanOption.offlineDecision(template: template, hole: hole, prep: prep), name
        )
        XCTAssertFalse(decision.isLocalNoRoute, name)
        let selected = try XCTUnwrap(decision.selectedSequence, name)
        guard case .array(let clubs)? = selected["clubs"] else {
            return XCTFail("\(name): the selected sequence lists its clubs")
        }
        let clubNames: [String] = clubs.compactMap {
            guard case .object(let row) = $0, case .string(let club)? = row["clubName"] else { return nil }
            return club
        }
        XCTAssertEqual(clubNames, ["1D", "8I"], name)
        XCTAssertEqual(selected["completion"], .string("scoring_window"), name)

        let plans = PrepPlanOption.options(template: template, hole: hole, prep: prep)
        XCTAssertEqual(plans.map(\.title), ["推荐", "稳妥"], name)
        XCTAssertEqual(plans.first?.id, LiveCaddieRouteAuthority.installedRouteId, name)
        XCTAssertEqual(plans.map { $0.shots.map(\.clubName) }, [["1D", "8I"], ["3W", "9I"]], name)

        // Both are complete routes on this hole: every stroke lands on it and the last one in the
        // scoring window of the green.
        let routeLength = prep.routeLenM
        for plan in plans {
            let offsets = try plan.shots.map { try XCTUnwrap($0.routeOffsetM, "\(name) \(plan.title) \($0.clubName)") }
            XCTAssertTrue(offsets.allSatisfy { $0 > 0 && $0 <= routeLength + 0.5 }, "\(name) \(plan.title)")
            let carried = plan.shots.compactMap(\.carryM).reduce(0, +)
            XCTAssertLessThanOrEqual(abs(routeLength - carried), 20, "\(name) \(plan.title) closes on the green")
        }
        // A different physical route: the 稳妥 tee shot lands well short of the Driver's.
        let driverLanding = try XCTUnwrap(plans[0].shots.first?.routeOffsetM, name)
        let safeLanding = try XCTUnwrap(plans[1].shots.first?.routeOffsetM, name)
        XCTAssertGreaterThanOrEqual(driverLanding - safeLanding, 15, name)
        // The 稳妥 tee shot carries the factual water (105-135 m) with its whole measured window.
        let waterBack = try XCTUnwrap(prep.hazards.waterCarry.compactMap { $0.max() }.max(), name)
        let threeWood = try XCTUnwrap(course.package.clubProfiles.first { $0.clubName == "3W" }, name)
        XCTAssertGreaterThanOrEqual(threeWood.p10M, waterBack + 8, name)
    }
}
