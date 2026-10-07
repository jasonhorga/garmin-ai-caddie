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
        "cautions":[],"hazards":{"water_carry":[],"bunkers":[],"details":[\
        {"kind":"water","frontM":175,"backM":195,"frontRouteM":175,"backRouteM":195,"frontPx":[112,175],"backPx":[110,155],\
        "outlinePx":[[96,178],[124,176],[128,160],[112,150],[94,158]],"sideM":null}]},\
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

    /// The snapshot's selected water hazard: its 后 edge sits right under the 220-yard tee arc.
    func testHazardEdgeLabelsJoinTheSharedLayoutAndStayOutsideTheOutline() throws {
        let map = try fixtureMap()
        let overlay = try XCTUnwrap(map.hole.resolvedMapOverlay)
        let row = try XCTUnwrap(LiveHazardDisplayItem.rows(for: map.hole, liveReadouts: nil).first)
        for scale in [CGFloat(1), 2] {
            let geometry = LivePlannedRouteRenderer.screenGeometry(
                size: viewport,
                legs: map.plannedLegs(),
                teeArc: map.teeDistanceArcPixels(),
                teeArcYards: 220,
                overlay: overlay,
                scale: scale,
                offset: .zero,
                topInset: LivePlayMapOverlayLayout.liveMapTopInset
            )
            let hazard = try XCTUnwrap(LiveHazardOverlayRenderer.screenGeometry(
                size: viewport,
                hole: map.hole,
                row: row,
                scale: scale,
                offset: .zero,
                topInset: LivePlayMapOverlayLayout.liveMapTopInset
            ))
            XCTAssertEqual(hazard.edges.map(\.text), ["前 191", "后 213"])
            let texts = LivePlannedRouteRenderer.labelTexts(geometry, pixelsPerMetre: overlay.ppm)
            let sizes = texts.enumerated().map { estimatedSize($0.element, isTeeLabel: $0.offset == 2) }
            // 10 pt heavy: ~10 pt per CJK glyph, ~6.5 pt per digit, plus 12 pt padding (≈ 52 pt).
            let hazardSizes = hazard.edges.map { _ in CGSize(width: 52, height: LiveHazardAnnotationLayout.labelHeight) }
            let placed = LivePlannedRouteRenderer.layout(
                geometry,
                labelSizes: sizes,
                flagScale: scale,
                viewportSize: viewport,
                hazard: hazard,
                hazardLabelSizes: hazardSizes
            )
            let all = (placed.hazard + placed.route).compactMap { $0 }
            XCTAssertEqual(all.count, 5, "a label was dropped at \(scale)x")
            for (index, rect) in all.enumerated() {
                for other in all[(index + 1)...] {
                    XCTAssertFalse(rect.intersects(other), "labels overlap at \(scale)x: \(rect) / \(other)")
                }
            }
            for rect in placed.hazard.compactMap({ $0 }) {
                let probes = [
                    CGPoint(x: rect.midX, y: rect.midY),
                    CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY),
                    CGPoint(x: rect.minX, y: rect.maxY), CGPoint(x: rect.maxX, y: rect.maxY),
                ]
                XCTAssertFalse(
                    probes.contains { LivePolygonGeometry.contains($0, polygon: hazard.outline) },
                    "a hazard label sits on the obstacle at \(scale)x"
                )
            }
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

    // MARK: - Lightweight map framing (Codex review #389, 09d / b4b2-02 / b4b2-04)

    /// The CourseView canvas of a lightweight hole is the whole bounding box: this par 5 runs down
    /// its left tenth, the way the real screenshots hug the left edge.
    private func edgeHuggingLightweightMap() throws -> HoleImageMapView {
        let json = """
        {"hole":1,"par":5,"par_source":"courseview","blue_yards":514,"route_len_m":470,"route":[],"steps":[],\
        "cautions":[],"hazards":{"water_carry":[],"bunkers":[],"details":[]},\
        "map":{"overlay":{"w":600,"h":940,"ppm":1.9,"ln":470,\
        "route":[[50,900,0],[85,620,150],[95,380,280],[55,60,470]]}}}
        """
        let hole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(json.utf8))
        return HoleImageMapView(
            hole: hole,
            showsCardChrome: false,
            showsPrepClubLabel: false,
            showsClubLabel: false,
            plannedShots: [
                MapPlannedShot(id: "tee", clubName: "一号木", carryM: 195, routeOffsetM: 195, role: "tee",
                               expectedRemainingM: 275, targetsPin: false, planIndex: 0),
                MapPlannedShot(id: "second", clubName: "三号木", carryM: 160, routeOffsetM: 355, role: "layup",
                               expectedRemainingM: 115, targetsPin: false, planIndex: 1),
                MapPlannedShot(id: "approach", clubName: "九号铁", carryM: 115, routeOffsetM: 470, role: "scoring",
                               expectedRemainingM: 0, targetsPin: true, planIndex: 2),
            ],
            drawsPlannedRouteInMap: false
        )
    }

    /// The live chrome on a 393 x 852 phone, in hero coordinates: title, round buttons, 洞位图 and
    /// the green ladder on top; 记分 and 记一杆 at the bottom; 障碍 on the left edge.
    private let liveChrome: [CGRect] = [
        CGRect(x: 14, y: 59, width: 240, height: 56),
        CGRect(x: 66, y: 125, width: 230, height: 36),
        CGRect(x: 66, y: 171, width: 112, height: 36),
        CGRect(x: 287, y: 59, width: 92, height: 132),
        CGRect(x: 14, y: 400, width: 56, height: 72),
        CGRect(x: 20, y: 735, width: 72, height: 90),
        CGRect(x: 297, y: 735, width: 76, height: 90),
    ]
    private let phone = CGSize(width: 393, height: 852)

    func testLightweightMapIsFramedOnThePlanNotTheCanvas() throws {
        let map = try edgeHuggingLightweightMap()
        let overlay = try XCTUnwrap(map.hole.resolvedMapOverlay)
        let legs = map.plannedLegs()
        XCTAssertEqual(legs.count, 3)
        func screenRoute(_ frame: CGRect?) -> [CGPoint] {
            overlay.route.compactMap {
                LivePlayMapOverlayLayout.project(
                    overlayPoint: $0,
                    overlayWidth: overlay.w,
                    overlayHeight: overlay.h,
                    into: phone,
                    topInset: LivePlayMapOverlayLayout.liveMapTopInset,
                    fittedFrame: frame
                )
            }
        }
        // The aspect fit reproduces the review: the whole hole in the left quarter of the screen.
        let aspectFit = screenRoute(nil)
        XCTAssertLessThan(try XCTUnwrap(aspectFit.map(\.x).max()), phone.width * 0.25)

        let frame = try XCTUnwrap(LivePlayMapOverlayLayout.lightweightFittedFrame(
            overlay: overlay,
            viewport: phone,
            chrome: liveChrome
        ))
        XCTAssertEqual(frame.width / frame.height, CGFloat(overlay.w) / CGFloat(overlay.h), accuracy: 0.001)
        let framed = screenRoute(frame)
        XCTAssertEqual(framed.count, overlay.route.count)
        let xs = framed.map(\.x)
        let middle = ((xs.min() ?? 0) + (xs.max() ?? 0)) / 2
        XCTAssertEqual(middle, phone.width / 2, accuracy: phone.width * 0.12, "the hole is centred")
        // Tee to green sits between the top chrome (洞位图 ends at 207) and 记分 / 记一杆 (735).
        for point in framed {
            XCTAssertGreaterThan(point.y, 207)
            XCTAssertLessThan(point.y, 735)
        }
        // The framed hole uses the screen: taller than the aspect fit's run is not required, but
        // it is never shrunk below half of the room between the chrome.
        let ys = framed.map(\.y)
        XCTAssertGreaterThan((ys.max() ?? 0) - (ys.min() ?? 0), (735 - 207) * 0.5)
    }

    func testAShortLightweightHoleAtTheCoverScaleIsStillCentred() throws {
        // A par 3 down the canvas' left edge reaches the cover scale long before it fills the room
        // between the chrome; keeping the screen edges covered would pin it back to the left.
        let overlay = CoursePrepOverlay(w: 600, h: 940, ppm: 1.9, ln: 150,
                                        route: [[60, 520, 0], [70, 240, 150]])
        let frame = try XCTUnwrap(LivePlayMapOverlayLayout.lightweightFittedFrame(
            overlay: overlay,
            viewport: phone,
            chrome: liveChrome
        ))
        let tee = try XCTUnwrap(LivePlayMapOverlayLayout.project(
            overlayPoint: [60, 520], overlayWidth: 600, overlayHeight: 940, into: phone, fittedFrame: frame
        ))
        let green = try XCTUnwrap(LivePlayMapOverlayLayout.project(
            overlayPoint: [70, 240], overlayWidth: 600, overlayHeight: 940, into: phone, fittedFrame: frame
        ))
        XCTAssertEqual((tee.x + green.x) / 2, phone.width / 2, accuracy: 1)
    }

    func testLightweightRouteLabelsAreAllShownAndClearOfTheLiveChrome() throws {
        let map = try edgeHuggingLightweightMap()
        let overlay = try XCTUnwrap(map.hole.resolvedMapOverlay)
        let legs = map.plannedLegs()
        let frame = try XCTUnwrap(LivePlayMapOverlayLayout.lightweightFittedFrame(
            overlay: overlay,
            viewport: phone,
            chrome: liveChrome
        ))
        let placed = LivePlannedRouteRenderer.placedRouteLabels(
            size: phone,
            legs: legs,
            overlay: overlay,
            scale: 1,
            offset: .zero,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset,
            fittedFrame: frame,
            exclusions: liveChrome
        )
        XCTAssertEqual(placed.count, 3)
        for label in placed {
            let rect = try XCTUnwrap(label.rect, "\(label.text) was omitted at rest")
            for chrome in liveChrome {
                XCTAssertFalse(rect.intersects(chrome), "\(label.text) \(rect) is under the chrome \(chrome)")
            }
        }
    }

    func testFittedFrameDrivesProjectionUnprojectionAndThePanClamp() throws {
        let frame = CGRect(x: -40, y: 120, width: 480, height: 752)
        XCTAssertEqual(
            LivePlayMapOverlayLayout.mapFrame(overlayWidth: 600, overlayHeight: 940, in: phone,
                                              topInset: 80, fittedFrame: frame),
            frame
        )
        let point = try XCTUnwrap(LivePlayMapOverlayLayout.project(
            overlayPoint: [300, 470], overlayWidth: 600, overlayHeight: 940, into: phone,
            topInset: 80, fittedFrame: frame
        ))
        XCTAssertEqual(point.x, frame.midX, accuracy: 0.001)
        XCTAssertEqual(point.y, frame.midY, accuracy: 0.001)
        let back = try XCTUnwrap(LivePlayMapOverlayLayout.unproject(
            screenPoint: point, overlayWidth: 600, overlayHeight: 940, from: phone,
            topInset: 80, fittedFrame: frame
        ))
        XCTAssertEqual(back[0], 300, accuracy: 0.001)
        XCTAssertEqual(back[1], 470, accuracy: 0.001)
        // A tap outside the framed bitmap is not on the map.
        XCTAssertNil(LivePlayMapOverlayLayout.unproject(
            screenPoint: CGPoint(x: 10, y: 60), overlayWidth: 600, overlayHeight: 940, from: phone,
            topInset: 80, fittedFrame: frame
        ))
    }

    func testSelectedHazardFollowsTheFittedFrame() throws {
        let map = try fixtureMap()
        let overlay = try XCTUnwrap(map.hole.resolvedMapOverlay)
        let row = try XCTUnwrap(LiveHazardDisplayItem.rows(for: map.hole, liveReadouts: nil).first)
        let frame = CGRect(x: 20, y: 150, width: 400, height: 600)
        let hazard = try XCTUnwrap(LiveHazardOverlayRenderer.screenGeometry(
            size: viewport,
            hole: map.hole,
            row: row,
            scale: 1,
            offset: .zero,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset,
            fittedFrame: frame
        ))
        let front = try XCTUnwrap(hazard.edges.first { $0.isFront })
        let expected = try XCTUnwrap(LivePlannedRouteRenderer.transformedPoint(
            CGPoint(x: 112, y: 175),
            size: viewport,
            overlay: overlay,
            scale: 1,
            offset: .zero,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset,
            fittedFrame: frame
        ))
        XCTAssertEqual(front.point.x, expected.x, accuracy: 0.001)
        XCTAssertEqual(front.point.y, expected.y, accuracy: 0.001)
    }
}
