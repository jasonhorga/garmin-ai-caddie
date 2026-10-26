#if !SWIFT_PACKAGE && canImport(UIKit)
import CoreGraphics
import XCTest
@testable import AICaddie

/// C89 (build 96, hole 1 screenshot): over the precise topo the live map drew a dark-green bar from
/// a white tee dot to a small green and flag, unrelated to the bitmap. The hole's prep was still the
/// CourseView lightweight row in its own 360x560 frame; and 障碍 then drew nothing at all.
@MainActor
final class C89HoleMapFrameTests: XCTestCase {
    /// The real `_lightweight_prep_hole` shape (course_prep.py `_course_data_frame`): partial, no
    /// geometry revision, the route in local metres with the three affine anchors of the fixed
    /// 360x560 portrait frame (local (0,0), (120,0), (0,120)), a CourseView green outline and one
    /// two-point bunker span in that frame. 1.3 px/m, tee at (180, 532), green straight up.
    private func courseViewRow() throws -> CoursePrepHole {
        let json = #"""
        {"hole":1,"par":4,"par_source":"courseData","blue_yards":421,"route_len_m":384.9,
         "route":[[0,0,0],[-8,384.8,384.9]],"geometryCoverage":"partial",
         "sourceRefs":["course:32850","courseData:32850:1:default"],
         "missingData":[{"label":"geometry","reason":"precise prodgeometry is pending; factual CourseView courseData is active"}],
         "candidateRoutes":[],"carryTargets":[],
         "steps":[{"club":"1D","note":"开球","targetCarry_m":230,"routeOffset_m":230,"role":"tee"},{"club":"8I","note":"攻果岭","targetCarry_m":150,"routeOffset_m":384.9,"expectedRemaining_m":0,"role":"approach"}],
         "cautions":[],
         "hazards":{"water_carry":[],"bunkers":[[200.0,12.0]],"details":[{"kind":"bunker","frontM":200.0,"backM":215.0,"frontRouteM":200.0,"backRouteM":215.0,"sideM":12.0,"frontPx":[195.6,272.0],"backPx":[195.6,252.5],"outlinePx":[]}]},
         "holeImageProjection":{"available":true,"widthPx":360,"heightPx":560,"refs":[
           {"lat":39.1643074,"lon":116.9942553,"px":180.0,"py":532.0},
           {"lat":39.1643074,"lon":116.9956464,"px":336.0,"py":532.0},
           {"lat":39.1653854,"lon":116.9942553,"px":180.0,"py":376.0}]},
         "greenOutline":{"available":true,"source":"courseData.GreenRadii","pointsPx":[[160,40],[180,28],[200,40],[180,52]]}}
        """#
        return try JSONDecoder().decode(CoursePrepHole.self, from: Data(json.utf8))
    }

    /// The captured C33 hole 1 row: partial but in the topo's 678x1060 frame and revision (the shape
    /// `/prep` now returns while only the obstacle export is pending), plus one mapped bunker.
    private func sameFrameRow(coverage: String = "partial") throws -> CoursePrepHole {
        let prep = try XCTUnwrap(c33Package().coursePrep?.holes.first)
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(prep)) as? [String: Any])
        json["geometryCoverage"] = coverage
        let bunker: [String: Any] = [
            "kind": "bunker", "frontM": 200.0, "backM": 215.0, "frontRouteM": 200.0, "backRouteM": 215.0,
            "sideM": 8.0, "frontPx": [360.0, 510.0], "backPx": [362.0, 480.0], "outlinePx": [] as [Any],
        ]
        let hazards: [String: Any] = [
            "water_carry": [] as [Any],
            "bunkers": [] as [Any],
            "details": [bunker],
        ]
        json["hazards"] = hazards
        return try JSONDecoder().decode(CoursePrepHole.self, from: JSONSerialization.data(withJSONObject: json))
    }

    private func c33Hole() throws -> Hole {
        try XCTUnwrap(c33Package().holes.first)
    }

    private let topoURL = URL(fileURLWithPath: "/tmp/c89-topo-32850-1.png")

    // MARK: - The inner map obeys the frame check (图 A)

    func testCourseViewRowIsNotDrawnOverThePreciseTopo() throws {
        let hole = try c33Hole()
        let lightweight = try courseViewRow()
        XCTAssertFalse(
            LiveTopoAvailability.overlayCompatible(hole: hole, prep: lightweight),
            "fixture: the 360x560 CourseView frame is not the topo frame"
        )
        let shots = [
            MapPlannedShot(id: "tee", clubName: "1D", carryM: 230, routeOffsetM: 230, role: "tee", planIndex: 0),
            MapPlannedShot(id: "approach", clubName: "8I", carryM: 150, routeOffsetM: 384.9, role: "approach",
                           expectedRemainingM: 0, targetsPin: true, planIndex: 1),
        ]
        let overTopo = HoleImageMapView(
            hole: lightweight,
            topoURL: topoURL,
            partialOverlayMatchesTopo: LiveTopoAvailability.overlayCompatible(hole: hole, prep: lightweight),
            showsCardChrome: false,
            teeDistanceArcYards: 230,
            plannedShots: shots,
            drawsPlannedRouteInMap: false
        )
        // README 地图降级契约: the factual route is shown only until the precise map arrives.
        XCTAssertFalse(overTopo.drawsLightweightFacts, "no CourseView fairway band over the topo")
        XCTAssertFalse(overTopo.drawsFactLayer, "no tee dot, route or flag in the CourseView frame")
        XCTAssertTrue(overTopo.plannedLegs().isEmpty, "the viewport route layer gets no CourseView legs")
        XCTAssertNil(overTopo.teeDistanceArcPixels())

        // Without a bitmap the same row is the factual map, drawn at once.
        let factual = HoleImageMapView(hole: lightweight, showsCardChrome: false, plannedShots: shots,
                                       drawsPlannedRouteInMap: false)
        XCTAssertTrue(factual.drawsLightweightFacts)
        XCTAssertTrue(factual.drawsFactLayer)
        XCTAssertEqual(factual.plannedLegs().count, 2)
    }

    func testSameFrameRowKeepsItsRouteOverTheTopoWithoutTheCourseViewBand() throws {
        let hole = try c33Hole()
        let sameFrame = try sameFrameRow()
        XCTAssertTrue(LiveTopoAvailability.overlayCompatible(hole: hole, prep: sameFrame))
        let map = HoleImageMapView(
            hole: sameFrame,
            topoURL: topoURL,
            partialOverlayMatchesTopo: true,
            showsCardChrome: false
        )
        XCTAssertTrue(map.drawsFactLayer, "tee, plan and flag share the topo frame")
        XCTAssertFalse(map.drawsLightweightFacts, "the bitmap itself shows the fairway and green")
    }

    // MARK: - A cached topo does not stop the row upgrade

    func testAHoleWithACachedTopoStillUpgradesItsRowToTheTopoFrame() throws {
        let hole = try c33Hole()
        let lightweight = try courseViewRow()
        let sameFrame = try sameFrameRow()
        // Whether the topo bitmap is cached or not, the row drawn over it is still in another frame.
        XCTAssertTrue(LiveHolePrepUpgradePolicy.shouldWaitForPreciseHoleMap(prep: lightweight))
        let ready = try sameFrameRow(coverage: "ready")
        XCTAssertFalse(LiveHolePrepUpgradePolicy.shouldWaitForPreciseHoleMap(prep: ready))
        // A same-frame partial row replaces the CourseView row at once; the probe goes on for ready.
        XCTAssertTrue(LiveHolePrepUpgradePolicy.adoptsInterimRow(sameFrame, current: lightweight, hole: hole))
        XCTAssertTrue(LiveHolePrepUpgradePolicy.adoptsInterimRow(sameFrame, current: nil, hole: hole))
        XCTAssertFalse(LiveHolePrepUpgradePolicy.adoptsInterimRow(lightweight, current: sameFrame, hole: hole))
        XCTAssertFalse(LiveHolePrepUpgradePolicy.adoptsInterimRow(sameFrame, current: sameFrame, hole: hole))
    }

    // MARK: - 障碍: drawn in the displayed frame, or an explicit notice

    func testSelectedHazardOverPreciseTopoWaitsForTheSameFrameRowWithANotice() throws {
        let hole = try c33Hole()
        let lightweight = try courseViewRow()
        let row = try XCTUnwrap(LiveHazardDisplayItem.rows(for: lightweight, liveReadouts: nil).first)
        let pending = LiveHazardMapFrame.resolve(
            state: .precise, hole: hole, prep: lightweight, row: row, garminProjection: nil
        )
        XCTAssertEqual(pending, .needsMapping(.sameFramePrep))
        XCTAssertNotNil(LiveHazardMapFrame.notice(for: pending, requestInFlight: true))
        XCTAssertNotNil(LiveHazardMapFrame.notice(for: pending, requestInFlight: false), "never a silent blank")

        let sameFrame = try sameFrameRow()
        let sameFrameHazard = try XCTUnwrap(LiveHazardDisplayItem.rows(for: sameFrame, liveReadouts: nil).first)
        let drawable = LiveHazardMapFrame.resolve(
            state: .precise, hole: hole, prep: sameFrame, row: sameFrameHazard, garminProjection: nil
        )
        XCTAssertEqual(drawable, .drawable(hole: sameFrame, row: sameFrameHazard))
        XCTAssertNil(LiveHazardMapFrame.notice(for: drawable, requestInFlight: false))
    }

    func testSelectedHazardOverGarminRasterUsesTheRegistrationOrSaysWhy() throws {
        let hole = try c33Hole()
        let sameFrame = try sameFrameRow()
        let row = try XCTUnwrap(LiveHazardDisplayItem.rows(for: sameFrame, liveReadouts: nil).first)

        // 图 B/C: the package's Garmin descriptor has no registration yet.
        let unregistered = LiveHazardMapFrame.resolve(
            state: .garminRaster, hole: hole, prep: sameFrame, row: row, garminProjection: nil
        )
        XCTAssertEqual(unregistered, .needsMapping(.garminRegistration))
        XCTAssertNotNil(LiveHazardMapFrame.notice(for: unregistered, requestInFlight: false))

        // The metadata endpoint's registration: the same three geographic anchors on Garmin's
        // 1242x1920 bitmap, i.e. every topo pixel scaled by 1242/678 and 1920/1060.
        let refs = try XCTUnwrap(sameFrame.holeImageProjection?.refs)
        let garmin = CoursePrepHoleImageProjection(
            available: true, widthPx: 1242, heightPx: 1920,
            refs: refs.map {
                CoursePrepProjectionRef(lat: $0.lat, lon: $0.lon, px: $0.px * 1242 / 678, py: $0.py * 1920 / 1060)
            }
        )
        let registered = LiveHazardMapFrame.resolve(
            state: .garminRaster, hole: hole, prep: sameFrame, row: row, garminProjection: garmin
        )
        guard case let .drawable(mappedHole, mappedRow) = registered else {
            return XCTFail("a registered Garmin raster draws the obstacle: \(registered)")
        }
        let overlay = try XCTUnwrap(mappedHole.resolvedMapOverlay)
        XCTAssertEqual(overlay.w, 1242)
        XCTAssertEqual(overlay.h, 1920)
        // frontPx (360, 510) x (1242/678, 1920/1060) = (659.5, 923.8); backPx (362, 480) = (663.1, 869.4).
        XCTAssertEqual(mappedRow.frontPx[0], 659.5, accuracy: 0.5)
        XCTAssertEqual(mappedRow.frontPx[1], 923.8, accuracy: 0.5)
        XCTAssertEqual(mappedRow.backPx[0], 663.1, accuracy: 0.5)
        XCTAssertEqual(mappedRow.backPx[1], 869.4, accuracy: 0.5)
        XCTAssertEqual(mappedRow.frontYards, row.frontYards, "distances are unchanged facts")
        XCTAssertNil(LiveHazardMapFrame.notice(for: registered, requestInFlight: false))

        // The numeric placeholder has no map: the bar's distances stay, with a notice.
        let mapless = LiveHazardMapFrame.resolve(
            state: .numericPlaceholder, hole: hole, prep: sameFrame, row: row, garminProjection: garmin
        )
        XCTAssertEqual(mapless, .needsMapping(.noMap))
        XCTAssertNotNil(LiveHazardMapFrame.notice(for: mapless, requestInFlight: false))
    }
}
#endif
