import Foundation
import SwiftUI
import XCTest
@testable import AICaddie

final class CoursePrepTests: XCTestCase {
    func testDecodesPrepResponse() throws {
        let json = """
        {"schema":"ai-caddie-course-prep-v1","globalId":31870,"holeCount":1,
         "clubs":[{"name":"1W","m":200,"yd":219},{"name":"7I","m":128,"yd":140}],
         "holes":[{"hole":1,"par":5,"par_source":"played","blue_yards":523,"route_len_m":478.4,
           "route":[[100.0,1000.0,0.0],[200.0,100.0,478.4]],
           "geometryCoverage":"ready","geometryRevision":"0123456789abcdef",
           "sourceRefs":["course:31870","geometry:31870:1"],
           "missingData":[],
           "candidateRoutes":[{"id":"stock","club":"1W","carryM":200.0,"riskScore":1.0}],
           "carryTargets":[{"kind":"landing","distanceM":200.0}],
           "steps":[{"club":"1W","note":"开球落点约 219y"},{"club":"7I","note":"剩约 140y 上果岭"}],
           "cautions":["果岭边沙坑（约 480y）——别短别偏"],
           "landing_m":200.0,"tee_club":"1W",
           "hazards":{"water_carry":[],"bunkers":[[440.0,12.0]]},
           "map":{"image":"data:image/jpeg;base64,AAAA","overlay":{"w":720,"h":1120,"ppm":1.2,"ln":478.4,"route":[[100.0,1000.0,0.0],[200.0,100.0,478.4]]}}}]}
        """
        let response = try JSONDecoder().decode(CoursePrepResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.globalId, 31870)
        XCTAssertEqual(response.holeCount, 1)
        XCTAssertEqual(response.clubs.first?.name, "1W")
        XCTAssertEqual(response.clubs.first?.yd, 219)

        let hole = try XCTUnwrap(response.holes.first)
        XCTAssertEqual(hole.par, 5)
        XCTAssertEqual(hole.parSource, "played")
        XCTAssertEqual(hole.blueYards, 523)
        XCTAssertEqual(hole.teeClub, "1W")
        XCTAssertEqual(hole.steps.count, 2)
        XCTAssertEqual(hole.hazards.bunkers.first, [440.0, 12.0])
        XCTAssertEqual(hole.geometryCoverage, "ready")
        XCTAssertEqual(hole.geometryRevision, "0123456789abcdef")
        XCTAssertEqual(hole.sourceRefs, ["course:31870", "geometry:31870:1"])
        XCTAssertEqual(hole.candidateRoutes.first?.id, "stock")
        XCTAssertEqual(hole.carryTargets.first?.kind, "landing")
        let map = try XCTUnwrap(hole.map)
        XCTAssertEqual(map.overlay.route.count, 2)
        XCTAssertEqual(map.overlay.ln, 478.4, accuracy: 0.01)
    }

    func testOptionalFieldsTolerateAbsence() throws {
        // map/landing_m/tee_club absent (e.g. render=false or a par-3 with no landing)
        let json = """
        {"schema":"ai-caddie-course-prep-v1","globalId":1,"holeCount":1,"clubs":[],
         "holes":[{"hole":3,"par":3,"par_source":"estimate","blue_yards":167,"route_len_m":153.5,
           "steps":[{"club":"7I","note":"约 167y 到果岭中心"}],"cautions":[],
           "landing_m":null,"tee_club":"7I","hazards":{"water_carry":[[40.0,90.0]],"bunkers":[]}}]}
        """
        let response = try JSONDecoder().decode(CoursePrepResponse.self, from: Data(json.utf8))
        let hole = try XCTUnwrap(response.holes.first)
        XCTAssertNil(hole.landingM)
        XCTAssertNil(hole.map)
        XCTAssertEqual(hole.hazards.waterCarry.first, [40.0, 90.0])
    }

    func testResolvesTopoOverlayFromLightweightRouteAndAffineProjection() throws {
        let json = """
        {"schema":"ai-caddie-course-prep-v1","globalId":3881,"holeCount":1,"clubs":[],
         "holes":[{"hole":4,"par":4,"par_source":"courseview","blue_yards":197,"route_len_m":180,
           "route":[[0,0,0],[60,0,60],[60,120,180]],
           "steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},
           "holeImageProjection":{"available":true,"widthPx":720,"heightPx":1120,"refs":[
             {"lat":36.58,"lon":-121.97,"px":300,"py":900},
             {"lat":36.58,"lon":-121.96865,"px":420,"py":780},
             {"lat":36.58108,"lon":-121.97,"px":180,"py":720}
           ]}}]}
        """
        let response = try JSONDecoder().decode(CoursePrepResponse.self, from: Data(json.utf8))
        let hole = try XCTUnwrap(response.holes.first)

        XCTAssertNil(hole.map, "render=false must not require an embedded bitmap")
        let overlay = try XCTUnwrap(hole.resolvedMapOverlay)
        XCTAssertEqual(overlay.w, 720)
        XCTAssertEqual(overlay.h, 1120)
        XCTAssertEqual(overlay.ln, 180, accuracy: 0.01)
        XCTAssertEqual(overlay.route, [
            [300, 900, 0],
            [360, 840, 60],
            [240, 660, 180],
        ])
        XCTAssertTrue(
            CourseReviewMapPolicy.requiresPreciseUpgrade(hole),
            "a drawable lightweight overlay is still a preparation state, never the accepted prep topo"
        )
        XCTAssertFalse(CourseReviewMapPolicy.hasPreciseFacts(hole))
    }

    func testPrepMapFinalStateRequiresReadyAuthorityAndAnOverlay() throws {
        let json = """
        {"schema":"ai-caddie-course-prep-v1","globalId":3881,"holeCount":1,"clubs":[],
         "holes":[{"hole":4,"par":4,"par_source":"courseview","blue_yards":197,"route_len_m":180,
           "route":[[0,0,0],[60,0,60],[60,120,180]],"geometryCoverage":"ready",
           "steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},
           "holeImageProjection":{"available":true,"widthPx":720,"heightPx":1120,"refs":[
             {"lat":36.58,"lon":-121.97,"px":300,"py":900},
             {"lat":36.58,"lon":-121.96865,"px":420,"py":780},
             {"lat":36.58108,"lon":-121.97,"px":180,"py":720}
           ]}}]}
        """
        let response = try JSONDecoder().decode(CoursePrepResponse.self, from: Data(json.utf8))
        let hole = try XCTUnwrap(response.holes.first)

        XCTAssertTrue(CourseReviewMapPolicy.hasPreciseFacts(hole))
        XCTAssertFalse(CourseReviewMapPolicy.requiresPreciseUpgrade(hole))
    }

    func testParSourceLabelsCourseViewWithoutMarkingAsEstimate() throws {
        XCTAssertEqual(coursePrepParSourceLabel("played"), "记分卡")
        XCTAssertEqual(coursePrepParSourceLabel("courseview"), "CourseView")
        XCTAssertEqual(coursePrepParSourceLabel("unknown"), "推算")
    }

    func testRotatedPrepMapScalesInsideItsOriginalViewport() throws {
        XCTAssertEqual(
            RotatableMapViewport<EmptyView>.displayScale(
                fitScale: 0.566,
                zoomScale: 1,
                pinchScale: 7
            ),
            2.264,
            accuracy: 0.0001
        )
        XCTAssertEqual(
            RotatableMapViewport<EmptyView>.displayScale(
                fitScale: 0.566,
                zoomScale: 4,
                pinchScale: 1
            ),
            2.264,
            accuracy: 0.0001,
            "a committed pinch must use the same relative zoom scale as the live gesture"
        )
        XCTAssertEqual(
            RotatableMapViewport<EmptyView>.fitScale(
                width: 360,
                height: 560,
                angle: .zero
            ),
            1,
            accuracy: 0.0001
        )
        XCTAssertEqual(
            RotatableMapViewport<EmptyView>.fitScale(
                width: 360,
                height: 560,
                angle: .degrees(90)
            ),
            360.0 / 560.0,
            accuracy: 0.0001
        )
        let diagonal = RotatableMapViewport<EmptyView>.fitScale(
            width: 360,
            height: 560,
            angle: .degrees(45)
        )
        XCTAssertGreaterThan(diagonal, 0)
        XCTAssertLessThan(diagonal, 1)

        let rotatedBounds = RotatableMapViewport<EmptyView>.clampedOffset(
            CGSize(width: 10_000, height: -10_000),
            width: 360,
            height: 560,
            scale: 1,
            angle: .degrees(90)
        )
        XCTAssertEqual(rotatedBounds.width, 100, accuracy: 0.0001)
        XCTAssertEqual(rotatedBounds.height, 0, accuracy: 0.0001)
    }

    func testCoursePrepRouteIntervalReadoutUsesYards() throws {
        XCTAssertEqual(CoursePrepRoute.yards(fromMetres: 100), 109)

        let before = CoursePrepRoute.intervalReadout(currentMetres: 70, startMetres: 100, endMetres: 130)
        XCTAssertEqual(before, CoursePrepHazardIntervalReadout(toStartYards: 33, toClearYards: 66, isBehind: true, isInside: false, isCleared: false))

        let inside = CoursePrepRoute.intervalReadout(currentMetres: 110, startMetres: 100, endMetres: 130)
        XCTAssertEqual(inside, CoursePrepHazardIntervalReadout(toStartYards: 0, toClearYards: 22, isBehind: false, isInside: true, isCleared: false))

        let cleared = CoursePrepRoute.intervalReadout(currentMetres: 150, startMetres: 100, endMetres: 130)
        XCTAssertEqual(cleared, CoursePrepHazardIntervalReadout(toStartYards: 0, toClearYards: 0, isBehind: false, isInside: false, isCleared: true))
    }

    func testLiveHazardsRangeFromCurrentPositionToSandAndWaterEdges() throws {
        let refs = affineProjectionRefs()
        let hazards = measuredHazards()

        let upcoming = try XCTUnwrap(
            CoursePrepLiveHazardReadout.upcoming(
                hazards: hazards,
                route: straightRoute(),
                projectionRefs: refs,
                playerLatitude: 0,
                playerLongitude: 0.0005
            ),
            "valid topo geometry must produce live hazard ranges"
        )

        XCTAssertEqual(upcoming.map(\.label), ["球道沙坑", "前方水障碍"])
        XCTAssertEqual(upcoming.map(\.detail), [
            "到 61 · 过 97 码",
            "到 158 · 过 182 码",
        ])
        XCTAssertEqual(upcoming.map(\.frontPx), [[100, 0], [180, 0]])
        XCTAssertEqual(upcoming.map(\.backPx), [[130, 0], [200, 0]])
    }

    func testLiveHazardsRemoveAnObstacleOnlyAfterItsFarEdgeIsPassed() throws {
        let upcoming = try XCTUnwrap(
            CoursePrepLiveHazardReadout.upcoming(
                hazards: measuredHazards(),
                route: straightRoute(),
                projectionRefs: affineProjectionRefs(),
                playerLatitude: 0,
                playerLongitude: 0.0015
            )
        )

        XCTAssertEqual(upcoming.map(\.label), ["前方水障碍"])
        XCTAssertEqual(upcoming.first?.detail, "到 36 · 过 61 码")
    }

    private func measuredHazards() -> CoursePrepHazards {
        CoursePrepHazards(
            details: [
                CoursePrepHazardDetail(
                    kind: "bunker",
                    frontM: 1_000,
                    backM: 1_100,
                    frontRouteM: 100,
                    backRouteM: 130,
                    frontPx: [100, 0],
                    backPx: [130, 0],
                    sideM: 9_999
                ),
                CoursePrepHazardDetail(
                    kind: "water",
                    frontM: 2_000,
                    backM: 2_100,
                    frontRouteM: 180,
                    backRouteM: 200,
                    frontPx: [180, 0],
                    backPx: [200, 0],
                    sideM: nil
                ),
            ]
        )
    }

    private func affineProjectionRefs() -> [CoursePrepProjectionRef] {
        [
            CoursePrepProjectionRef(lat: 0, lon: 0, px: 0, py: 0),
            CoursePrepProjectionRef(lat: 0, lon: 0.001, px: 100, py: 0),
            CoursePrepProjectionRef(lat: 0.001, lon: 0, px: 0, py: 100),
        ]
    }

    private func straightRoute() -> [[Double]] {
        [
            [0, 0, 0],
            [100, 0, 100],
            [200, 0, 200],
            [300, 0, 300],
        ]
    }
}
