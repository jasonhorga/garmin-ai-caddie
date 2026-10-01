@testable import AICaddie
import XCTest

/// B4c 方案 (Codex 5925193109): the CI fixture's degraded course (`Fixtures/b4c_degraded_plan_inputs.json`,
/// kept in lock-step with `server_v2/ci_fixture.py` by `tests/test_prep_render_shapes_fixture.py`)
/// is the course `PrepDegradationUITests` switches plans on. Fed to the production plan authority,
/// its factual hole 2 must offer exactly the installed Driver chain and one genuinely 稳妥
/// whole-hole alternative — never a cosmetic duplicate.
final class PrepDegradedPlansTests: XCTestCase {
    private struct Inputs: Decodable {
        let package: LiveRoundPackage
        let prep: CoursePrepResponse
    }

    private func inputs() throws -> Inputs {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: PrepDegradedPlansTests.self)
        #endif
        let url = try XCTUnwrap(
            bundle.url(forResource: "b4c_degraded_plan_inputs", withExtension: "json", subdirectory: "Fixtures")
                ?? bundle.url(forResource: "b4c_degraded_plan_inputs", withExtension: "json")
        )
        return try JSONDecoder().decode(Inputs.self, from: Data(contentsOf: url))
    }

    func testTheDegradedFactualHoleOffersTheDriverChainAndAGenuinelySaferThreeWoodChain() throws {
        let inputs = try inputs()
        let prep = try XCTUnwrap(inputs.prep.holes.first { $0.hole == 2 })
        XCTAssertEqual(prep.geometryCoverage, "partial", "hole 2 starts as the factual route")
        let hole = try XCTUnwrap(inputs.package.holes.first { $0.number == 2 })
        let template = inputs.package.replacingCoursePrep(CoursePrepPackage(
            schema: "ai-caddie-course-prep-v1",
            globalId: inputs.package.course.globalId,
            holes: [prep],
            missingData: nil
        ))

        let plans = PrepPlanOption.options(template: template, hole: hole, prep: prep)
        XCTAssertEqual(plans.map(\.title), ["推荐", "稳妥"])
        XCTAssertEqual(plans.first?.id, LiveCaddieRouteAuthority.installedRouteId)
        XCTAssertEqual(plans.map { $0.shots.map(\.clubName) }, [["1D", "8I"], ["3W", "9I"]])

        // A different physical route: the 稳妥 tee shot lands well short of the Driver's, and
        // every planned stroke of both chains stays on the hole.
        let routeLength = prep.routeLenM
        let driverLanding = try XCTUnwrap(plans[0].shots.first?.routeOffsetM)
        let safeLanding = try XCTUnwrap(plans[1].shots.first?.routeOffsetM)
        XCTAssertGreaterThanOrEqual(driverLanding - safeLanding, 15)
        for plan in plans {
            for shot in plan.shots {
                let offset = try XCTUnwrap(shot.routeOffsetM, "\(plan.title) \(shot.clubName)")
                XCTAssertGreaterThan(offset, 0)
                XCTAssertLessThanOrEqual(offset, routeLength + 0.5)
            }
        }
        // The 稳妥 tee shot carries the factual water (105-135 m) with its whole measured window.
        let waterBack = try XCTUnwrap(prep.hazards.waterCarry.compactMap { $0.max() }.max())
        let threeWood = try XCTUnwrap(inputs.package.clubProfiles.first { $0.clubName == "3W" })
        XCTAssertGreaterThanOrEqual(threeWood.p10M, waterBack + 8)
    }
}
