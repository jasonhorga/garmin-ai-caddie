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
                strategyMode: "stock"
            )
        )

        guard case .object(let location) = request.context["currentLocation"] else {
            return XCTFail("currentLocation missing")
        }
        XCTAssertEqual(location["capturedAt"], .string("2026-06-20T00:00:00Z"))
    }
}
