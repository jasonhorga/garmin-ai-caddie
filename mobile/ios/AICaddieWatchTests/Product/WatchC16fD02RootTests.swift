import CoreLocation
import XCTest
@testable import AICaddieWatch

/// C16f 5.12: D02's root may show one current-shot recommendation only when every
/// trust, freshness, movement and measured-carry fact is present.
@MainActor
final class WatchC16fD02RootTests: XCTestCase {
    private let now = "2026-10-23T12:00:00Z"
    private let fix = WatchLocationFix(
        coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
        horizontalAccuracyM: 5,
        capturedAt: "2026-10-23T11:59:55Z"
    )

    private func model(with recommendation: WatchRootCaddieRecommendation?) -> WatchRoundModel {
        let state = WatchRoundState(
            roundId: "d02-round", hole: 1, par: 4, distanceM: 300,
            suggestedClub: "6I", selectedClub: "6I", decisionId: recommendation?.decisionId,
            holeMap: WatchHoleMap(
                w: 400, h: 400,
                you: [0, 0], pin: [300, 0], layup: [150, 0], apex: [100, 0], greenCtrl: [280, 0],
                route: [[0, 0, 0], [100, 0, 100], [300, 0, 300]]
            ),
            rootCaddieRecommendation: recommendation,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let store = WatchRoundStore(directoryURL: FileManager.default.temporaryDirectory
            .appendingPathComponent("c16f-d02-\(UUID().uuidString)", isDirectory: true))
        let model = WatchRoundModel(store: store, now: { self.now })
        model.seedRound([state], activeHole: 1, courseName: "D02")
        return model
    }

    private func recommendation(
        source: String = "live", mode: String = "manual", confidence: String = "high",
        generatedAt: String = "2026-10-23T11:50:00Z", validUntil: String = "2026-10-23T12:10:00Z",
        sampleSize: Int = 20, carryP10M: Double = 140, aimCarryM: Double = 150,
        carryP90M: Double = 160, movementM: Double = 20
    ) -> WatchRootCaddieRecommendation {
        WatchRootCaddieRecommendation(
            decisionId: "decision-d02", clubName: "6I", aimCarryM: aimCarryM,
            carryP10M: carryP10M, carryP90M: carryP90M, sampleSize: sampleSize,
            confidence: confidence, source: source, mode: mode, generatedAt: generatedAt,
            validUntil: validUntil, originLatitude: 40, originLongitude: 116,
            originAccuracyM: 5, maximumMovementM: movementM, evidenceCount: 2
        )
    }

    func test_5_12_watch_only_a_fresh_trusted_measured_recommendation_can_open_root() {
        XCTAssertTrue(model(with: recommendation()).rootCaddieLayerAvailable(at: fix))
        XCTAssertFalse(model(with: recommendation(source: "offline")).rootCaddieLayerAvailable(at: fix))
        XCTAssertFalse(model(with: recommendation(mode: "automatic", confidence: "low")).rootCaddieLayerAvailable(at: fix))
        XCTAssertFalse(model(with: recommendation(sampleSize: 9)).rootCaddieLayerAvailable(at: fix))
        XCTAssertFalse(model(with: recommendation(validUntil: "2026-10-23T11:59:00Z")).rootCaddieLayerAvailable(at: fix))
        XCTAssertFalse(model(with: recommendation()).rootCaddieLayerAvailable(at: nil))
    }

    func test_5_12_watch_root_rejects_movement_beyond_origin_window() {
        let moved = WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0003, longitude: 116),
            horizontalAccuracyM: 5,
            capturedAt: "2026-10-23T11:59:55Z"
        )
        XCTAssertFalse(model(with: recommendation(movementM: 20)).rootCaddieLayerAvailable(at: moved))
    }

    func test_5_12_watch_measured_carry_depth_projects_to_handwritten_route_and_yards() throws {
        let route = [[0.0, 0.0, 0.0], [100.0, 0.0, 100.0], [300.0, 0.0, 300.0]]
        let layout = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: CGPoint(x: 0, y: 0),
            aimCarryM: 150,
            carryP10M: 140,
            carryP90M: 160
        ))
        XCTAssertEqual(layout.target.x, 150, accuracy: 0.001)
        XCTAssertEqual(layout.carryP10.x, 140, accuracy: 0.001)
        XCTAssertEqual(layout.carryP90.x, 160, accuracy: 0.001)
        XCTAssertEqual(WatchUnits.yards(layout.target.x), 164, "the Watch displays the measured carry in yards")
        XCTAssertNil(WatchCurrentShotLayout.resolve(
            route: route, playerImagePoint: CGPoint(x: 0, y: 0),
            aimCarryM: 150, carryP10M: 170, carryP90M: 160
        ))
    }
}
