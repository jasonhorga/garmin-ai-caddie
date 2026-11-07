import CoreLocation
import XCTest
@testable import AICaddie

final class CaddieDecisionRequestBuilderTests: XCTestCase {
    func testOffCourseDistanceIsNotSentToCaddieBackend() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: url))
        let seed = try XCTUnwrap(package.caddieContextSeeds.first)

        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: 20_000)
        )

        XCTAssertNil(request.context["distanceToPin_m"])
    }

    func testLiveLocationCarriesItsCaptureTimeIntoTheDecisionContext() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: url))
        let seed = try XCTUnwrap(package.caddieContextSeeds.first)

        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(
                shotType: "tee",
                coordinate: CLLocationCoordinate2D(latitude: 40.0455, longitude: 116.5462),
                horizontalAccuracyM: 5,
                capturedAt: "2026-06-20T00:00:00Z",
                strategyMode: "attack",
                requestedOptionId: "attack"
            )
        )

        guard case .object(let location) = request.context["currentLocation"] else {
            return XCTFail("currentLocation missing")
        }
        XCTAssertEqual(location["capturedAt"], .string("2026-06-20T00:00:00Z"))
        XCTAssertEqual(request.context["strategyMode"], .string("attack"))
        XCTAssertEqual(request.context["requestedOptionId"], .string("attack"))
    }

    func testAutomaticDecisionLeavesStrategyOverrideUnset() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: url))
        let seed = try XCTUnwrap(package.caddieContextSeeds.first)

        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee", distanceToPinM: 374)
        )

        XCTAssertNil(request.context["strategyMode"])
        XCTAssertNil(request.context["requestedOptionId"])
    }

    func testDistanceSourceIsForwardedWithoutChangingTheNumericDistance() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: url))
        let seed = try XCTUnwrap(package.caddieContextSeeds.first)

        let request = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(
                shotType: "approach",
                distanceToPinM: 142,
                distanceToPinSource: "gps_auto"
            )
        )

        XCTAssertEqual(request.context["distanceToPin_m"], .number(142))
        XCTAssertEqual(request.context["distanceToPinSource"], .string("gps_auto"))
    }

    func testFirstFrameTeeMarksStaticDistanceAsFallback() throws {
        let distances = try JSONDecoder().decode(
            CoursePrepGreenDistances.self,
            from: Data(#"{"available":true,"middleM":170}"#.utf8)
        )
        let input = LiveCaddieInput.firstFrameTee(greenDistances: distances, holeYards: 190)

        XCTAssertEqual(input.distanceToPinSource, "fallback")
        XCTAssertEqual(input.distanceToPinM, 170)
    }
}
