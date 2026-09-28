import SwiftUI
import XCTest
@testable import AICaddie

/// B1b: every label on the live map ("杆名 码数" per leg and the tee-distance "N码") shares one
/// collision layout. These cases reproduce the snapshot fixture, where the 220-yard tee arc crosses
/// the fairway right next to the 1W landing, at the fitted scale and zoomed in.
final class LivePlannedRouteLayoutTests: XCTestCase {
    private let viewport = CGSize(width: 390, height: 844)

    private func fixtureMap() throws -> HoleImageMapView {
        let json = """
        {"hole":1,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,"route":[[120,330],[118,180],[120,55]],"steps":[],\
        "cautions":[],"hazards":{"water_carry":[],"bunkers":[]},\
        "map":{"overlay":{"w":240,"h":360,"ppm":1.0,"ln":375,\
        "route":[[120,330,0],[118,180,150],[120,55,375]]}}}
        """
        let hole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(json.utf8))
        return HoleImageMapView(
            hole: hole,
            showsCardChrome: false,
            showsPrepClubLabel: false,
            showsClubLabel: false,
            teeDistanceArcYards: 220,
            plannedShots: [
                MapPlannedShot(id: "tee", clubName: "1W", carryM: 225, routeOffsetM: 225, role: "tee",
                               expectedRemainingM: 150, targetsPin: false, planIndex: 0),
                MapPlannedShot(id: "approach", clubName: "8I", carryM: 150, routeOffsetM: 375, role: "scoring",
                               expectedRemainingM: 0, targetsPin: true, planIndex: 1),
            ],
            drawsPlannedRouteInMap: false
        )
    }

    /// Conservative text metrics: 13 pt per CJK glyph, 8 pt otherwise (7 / 6 at 11 pt).
    private func estimatedSize(_ text: String, isTeeLabel: Bool) -> CGSize {
        let wide: CGFloat = isTeeLabel ? 11 : 13
        let narrow: CGFloat = isTeeLabel ? 7 : 8
        let width = text.unicodeScalars.reduce(CGFloat(0)) { total, scalar in
            total + (scalar.value > 0x2E80 ? wide : narrow)
        }
        return CGSize(width: ceil(width) + 14, height: isTeeLabel ? 22 : 24)
    }

    func testLegAndTeeArcLabelsNeverOverlapAtAnyZoom() throws {
        let map = try fixtureMap()
        let legs = map.plannedLegs()
        let teeArc = try XCTUnwrap(map.teeDistanceArcPixels())
        let overlay = try XCTUnwrap(map.hole.resolvedMapOverlay)
        XCTAssertEqual(legs.count, 2)

        for scale in [CGFloat(1), 2] {
            let geometry = LivePlannedRouteRenderer.screenGeometry(
                size: viewport,
                legs: legs,
                teeArc: teeArc,
                teeArcYards: 220,
                overlay: overlay,
                scale: scale,
                offset: .zero,
                topInset: LivePlayMapOverlayLayout.liveMapTopInset
            )
            let texts = LivePlannedRouteRenderer.labelTexts(geometry, pixelsPerMetre: overlay.ppm)
            XCTAssertEqual(texts, ["一号木 246", "八号铁 164", "220码"], "scale \(scale)")
            let sizes = texts.enumerated().map { estimatedSize($0.element, isTeeLabel: $0.offset == 2) }
            let placed = LivePlannedRouteRenderer.labelRects(
                geometry,
                labelSizes: sizes,
                flagScale: scale,
                viewportSize: viewport
            )
            // Every label is on screen at the fitted scale and at the snapshot's 2x zoom.
            let rects = placed.compactMap { $0 }
            XCTAssertEqual(rects.count, 3, "a label was dropped at \(scale)x")
            guard rects.count == 3 else { continue }
            let bounds = CGRect(origin: .zero, size: viewport)
            for (index, rect) in rects.enumerated() {
                XCTAssertTrue(bounds.contains(rect), "label \(texts[index]) leaves the screen at \(scale)x")
                for other in rects[(index + 1)...] {
                    XCTAssertFalse(rect.intersects(other), "\(texts[index]) overlaps another label at \(scale)x")
                }
            }
            // The flag (scaled with the map) must stay visible beside its label.
            let pin = try XCTUnwrap(geometry.legs.last?.destination)
            let flag = LivePlannedRouteRenderer.flagRect(foot: pin, scale: scale)
            XCTAssertFalse(rects[1].intersects(flag), "the 8I label covers the flag at \(scale)x")
        }
    }

    func testLayoutNeverStacksLabelsEvenWhenTheyShareAnAnchor() {
        let request = LivePlannedRouteRenderer.LabelRequest(
            size: CGSize(width: 90, height: 24),
            candidates: LivePlannedRouteRenderer.landingCandidates(
                landing: CGPoint(x: 200, y: 400),
                from: CGPoint(x: 200, y: 700),
                labelSize: CGSize(width: 90, height: 24)
            )
        )
        let rects = LivePlannedRouteRenderer.layoutLabels(
            [request, request, request],
            viewport: CGRect(x: 4, y: 4, width: 382, height: 836),
            obstacles: [],
            samples: []
        )
        XCTAssertEqual(rects.count, 3)
        XCTAssertFalse(rects[0].intersects(rects[1]))
        XCTAssertFalse(rects[0].intersects(rects[2]))
        XCTAssertFalse(rects[1].intersects(rects[2]))
    }

    func testLabelOfALandingPannedOffScreenIsOmittedNotClamped() throws {
        let map = try fixtureMap()
        let overlay = try XCTUnwrap(map.hole.resolvedMapOverlay)
        let geometry = LivePlannedRouteRenderer.screenGeometry(
            size: viewport,
            legs: map.plannedLegs(),
            teeArc: nil,
            teeArcYards: nil,
            overlay: overlay,
            scale: 4,
            offset: .zero,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        )
        let pin = try XCTUnwrap(geometry.legs.last?.destination)
        XCTAssertLessThan(pin.y, 0, "fixture: the flag is above the screen at 4x")
        let placed = LivePlannedRouteRenderer.labelRects(
            geometry,
            labelSizes: [CGSize(width: 96, height: 24), CGSize(width: 96, height: 24)],
            flagScale: 4,
            viewportSize: viewport
        )
        XCTAssertNil(placed[1])
    }
}
