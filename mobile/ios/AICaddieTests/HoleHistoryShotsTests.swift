import XCTest
@testable import AICaddie

final class HoleHistoryShotsTests: XCTestCase {
    func testHistoryKeepsTeeAndSelectsOnlyShotsInsideTwentyFiveMetres() {
        let shots = [
            HoleHistoryOverlayRenderer.ProjectedShot(id: "tee", start: CGPoint(x: 0, y: 0), end: CGPoint(x: 20, y: 0), distanceM: 20, isTee: true, result: "fairway"),
            HoleHistoryOverlayRenderer.ProjectedShot(id: "near", start: CGPoint(x: 20, y: 0), end: CGPoint(x: 60, y: 0), distanceM: 40, isTee: false, result: "rough"),
            HoleHistoryOverlayRenderer.ProjectedShot(id: "far", start: CGPoint(x: 100, y: 0), end: CGPoint(x: 150, y: 0), distanceM: 50, isTee: false, result: "water"),
        ]

        let selected = HoleHistoryOverlayRenderer.nearby(
            shots,
            player: CGPoint(x: 0, y: 0),
            radiusMetres: 25,
            pixelsPerMetre: 1
        )

        XCTAssertEqual(selected.map(\.id), ["tee", "near"])
    }

    func testHistorySummaryUsesRecordedDistanceBeforePixelFallback() {
        let shots = [
            HoleHistoryOverlayRenderer.ProjectedShot(id: "a", start: CGPoint(x: 0, y: 0), end: CGPoint(x: 10, y: 0), distanceM: 100, isTee: true, result: "fairway"),
            HoleHistoryOverlayRenderer.ProjectedShot(id: "b", start: CGPoint(x: 0, y: 0), end: CGPoint(x: 20, y: 0), distanceM: nil, isTee: false, result: "green"),
        ]

        let summary = HoleHistoryOverlayRenderer.summary(shots, pixelsPerMetre: 1)
        XCTAssertEqual(summary.count, 2)
        XCTAssertEqual(summary.averageYards, 66)
    }

    func testDistanceOnlyShotRemainsVisibleWhenGeometryIsMissing() {
        let shots = [
            HoleHistoryOverlayRenderer.ProjectedShot(
                id: "distance-only", start: nil, end: nil, distanceM: 38,
                isTee: false, result: "unknown"
            )
        ]

        let selected = HoleHistoryOverlayRenderer.nearby(
            shots, player: CGPoint(x: 0, y: 0), radiusMetres: 25, pixelsPerMetre: 1
        )

        XCTAssertEqual(selected.map(\.id), ["distance-only"])
        XCTAssertEqual(HoleHistoryOverlayRenderer.summary(selected, pixelsPerMetre: 1).averageYards, 42)
    }

    func testHistoryResponseDecodesGreenAndMissingData() throws {
        let data = Data(#"{"schema":"ai-caddie-hole-history-shots-v1","globalId":12,"localHole":4,"days":730,"since":"2024-01-01","roundCount":2,"shots":[],"green":{"available":true,"lat":31.2,"lon":121.4,"source":"garmin"},"missingData":[{"label":"落点","reason":"无坐标"}]}"#.utf8)
        let response = try JSONDecoder().decode(HoleHistoryShotsResponse.self, from: data)
        XCTAssertEqual(response.roundCount, 2)
        XCTAssertEqual(response.green.source, "garmin")
        XCTAssertEqual(response.missingData.first?["reason"], "无坐标")
    }
}

extension HoleHistoryShotsTests {
    func testDistanceLabelsUseTheNearbySelection() {
        let shots = [
            HoleHistoryOverlayRenderer.ProjectedShot(
                id: "far", start: CGPoint(x: 100, y: 0), end: nil, distanceM: 44,
                isTee: false, result: "rough"
            )
        ]
        let selected = HoleHistoryOverlayRenderer.nearby(
            shots, player: CGPoint(x: 0, y: 0), radiusMetres: 25, pixelsPerMetre: 1
        )
        XCTAssertNil(HoleHistoryOverlayRenderer.distanceOnlyText(selected))
    }

    func testPlayerPixelCarriesAcrossSameOverlayWhenMapUpgrades() {
        let hole = CoursePrepHole(
            hole: 1, par: 4, parSource: "test", blueYards: 400,
            routeLenM: 200,
            route: [[0, 200, 0], [0, 0, 200]],
            map: CoursePrepMap(
                image: nil,
                overlay: CoursePrepOverlay(w: 200, h: 200, ppm: 1, ln: 200,
                                           route: [[0, 200, 0], [0, 0, 200]])
            )
        )
        XCTAssertEqual(
            HoleHistoryOverlayRenderer.carryPlayer(CGPoint(x: 40, y: 80), from: hole, to: hole),
            CGPoint(x: 40, y: 80)
        )
    }
}
