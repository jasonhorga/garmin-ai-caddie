import ImageIO
import SwiftUI
import XCTest
@testable import AICaddieWatch

/// round-12 P3 (Watch standalone): render watch SwiftUI surfaces to PNGs in the watchOS SIMULATOR so
/// the UI can be reviewed from CI without a physical Apple Watch — the same idea as the iOS
/// DesignSnapshotTests. native-mobile.yml collects `Documents/watch-snapshots/*.png` after the Watch
/// test and uploads them as the `watch-snapshots` artifact. (Only real GPS / HealthKit / motion need a
/// physical watch — the UI/scoring layout is fully reviewable here.)
final class WatchDesignSnapshotTests: XCTestCase {
    @MainActor
    func testRenderWatchCaddieGlance() throws {
        let state = WatchRoundState(
            roundId: "r1", hole: 7, par: 4, distanceM: 139,
            targetNote: "右沙坑 138–150 码,避开",
            targetLatitude: 22.28, targetLongitude: 114.16, targetKind: "pin",
            suggestedClub: "7号铁", selectedClub: "7号铁",
            availableClubs: [WatchClubOption(clubName: "7号铁", medianM: 139), WatchClubOption(clubName: "6号铁", medianM: 150)],
            shotType: "approach", strategyMode: "stock", lie: "fairway",
            nextShotPrompt: "上果岭中心偏左", holePlanSummary: "开球 → 攻果岭",
            expectedStrokes: 4.1, expectedRemainingM: 8,
            frontGreenM: 128, centerGreenM: 135, backGreenM: 142,
            playsLikeDistanceM: 138, elevationDeltaM: 3,
            score: 4, putts: 2, penaltyCount: 0, caddieConfidence: "high"
        )
        let view = WatchCaddieGlanceView(state: state)
            .padding(8)
            .frame(width: 198)  // ≈ 46mm watch logical width
            .background(Color.black)
        try render(view, named: "watch-caddie-glance")
    }

    @MainActor
    func testRenderWatchCaddieOptions() throws {
        // round-13 spec ②: 激进/推荐/保守 options pushed from the phone; 标准 (stock) highlighted.
        let view = WatchCaddieOptionsView(
            options: [
                WatchCaddieOption(optionId: "safe", label: "稳妥", clubName: "9号铁", carryM: 128, expectedStrokes: 3.1, confidence: "high"),
                WatchCaddieOption(optionId: "stock", label: "标准", clubName: "8号铁", carryM: 142, expectedStrokes: 3.0, confidence: "high"),
                WatchCaddieOption(optionId: "attack", label: "进攻", clubName: "7号铁", carryM: 156, expectedStrokes: 3.2, confidence: "medium"),
            ],
            recommendedId: "stock"
        )
        .padding(8)
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-caddie-options")
    }

    @MainActor
    func testRenderWatchHazards() throws {
        // round-13 spec ⑤: bunkers then water, near→far, carry interval in 码.
        let view = WatchHazardView(
            hazards: [
                WatchHazard(kind: "bunker", label: "沙坑 1", startM: 120, endM: 140),
                WatchHazard(kind: "bunker", label: "沙坑 2", startM: 165, endM: 178),
                WatchHazard(kind: "water", label: "水域", startM: 210, endM: 235),
            ]
        )
        .padding(8)
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-hazards")
    }

    @MainActor
    func testRenderWatchRoundHome() throws {
        // round-13: home now carries the 18-hole edge ring; current hole 7 highlighted, holes 1–6
        // scored (colored by to-par), 8–18 not yet played (grey).
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 2, 5: 0, 6: 1]
        let pips = (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 7) }
        let view = WatchRoundHomeView(
            courseName: "北京丽宫 · 前九",
            hole: 7, par: 4, holeCount: 9,
            scoredHoles: 6, toPar: 3,
            distanceText: "152 码", pendingUploads: 2,
            ringPips: pips
        )
        .frame(width: 198, height: 198)
        .background(Color.black)
        try render(view, named: "watch-round-home")
    }

    @MainActor
    func testRenderWatchHoleRing() throws {
        // round-13 refinement: the edge ring is drawn as thin RADIAL TICK marks (短横线), not filled
        // dots, so it hugs the rim without covering the centre. Isolated here (ring + a minimal centre)
        // so the tick thickness / length / radial rotation is unmistakable in the snapshot. Holes 1–6
        // scored — par(0)/bogey(+1)/birdie(−1)/double(+2)/par(0)/eagle(−2) to exercise every score
        // colour; hole 7 current (brighter + longer white tick); 8–18 not yet played (dim grey).
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 2, 5: 0, 6: -2]
        let pips = (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 7) }
        let view = WatchHoleRingView(pips: pips) {
            VStack(spacing: 1) {
                Text("第 7 洞 · Par 4").font(.caption2).foregroundStyle(.secondary)
                Text("152").font(.system(size: 42, weight: .bold)).foregroundStyle(.white)
                Text("码 · 到旗杆").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .frame(width: 198, height: 198)
        .background(Color.black)
        try render(view, named: "watch-hole-ring")
    }

    @MainActor
    func testRenderWatchHoleMap() throws {
        // round-14 DESIGN REVIEW: Garmin-S70-style SPLIT hole view on the REAL backend render (gid31669
        // h4, Par 5) — a par-5 SECOND shot that can't reach: LEFT column (第4洞·P5, 前/中/后果岭 = distance
        // to the green, 实打 hero, 球童 lay-up club) | RIGHT map (YOU + heading arrow, two-segment caddie
        // line you→lay-up→green, pin, reach arc, 距上一杆), gradient vignette into black, and the 12→9
        // scoring ring whose corner segments curve along the rounded bezel. 46mm size.
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1]
        let pips = (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 4) }
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5,
            frontGreen: 273, centerGreen: 287, backGreen: 300,
            playsLikeDelta: 8, lastShot: 200,
            caddieClub: "3号木", caddieNote: "推进 · 留100",
            ringPips: pips
        )
        .frame(width: 198, height: 242)   // ≈ 46mm Apple Watch logical size
        .background(Color.black)
        try render(view, named: "watch-holeview")
    }

    @MainActor
    func testRenderWatchHoleMapPlaysLike() throws {
        // The 实打 TOGGLE state: tapping the distance block flips 后/中/前 to the slope-adjusted values with
        // a ↑ arrow (here +8 uphill → plays longer). Everything else stays put — same decluttered layout.
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1]
        let pips = (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 4) }
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5,
            frontGreen: 273, centerGreen: 287, backGreen: 300,
            playsLikeDelta: 8, lastShot: 200,
            caddieClub: "3号木", caddieNote: "推进 · 留100",
            ringPips: pips,
            showPlaysLike: true
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-holeview-pl")
    }

    @MainActor
    func testRenderWatchHoleImageInCanvas() throws {
        // De-risk: does the baked hole image render at all when drawn INSIDE a Canvas via context.draw
        // under watchOS ImageRenderer? (This is exactly how WatchHoleMapView draws the map.) Image only,
        // no overlays — if this is blank/nil the image path is the culprit, not the overlay geometry.
        let view = Canvas { context, size in
            #if canImport(UIKit)
            if let ui = WatchHoleMapSample.image {
                context.draw(context.resolve(Image(uiImage: ui)), in: CGRect(origin: .zero, size: size))
            }
            #endif
        }
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-img-canvas")
    }

    @MainActor
    func testRenderWatchClipImage() throws {
        // De-risk: the split map panel draws the image inside a CLIPPED `drawLayer` (so the zoomed image
        // doesn't bleed over the data column). Exercise exactly that — clip a rounded panel, draw the image
        // in it — to confirm drawLayer+clip+image renders under watchOS ImageRenderer. If watch-holeview is
        // blank but this is not, the culprit is elsewhere; if this is blank too, drawLayer/clip is the cause.
        let view = Canvas { context, size in
            let panel = CGRect(x: size.width * 0.38, y: 20, width: size.width * 0.58, height: size.height - 40)
            let panelPath = Path(roundedRect: panel, cornerRadius: 10)
            context.drawLayer { layer in
                layer.clip(to: panelPath)
                layer.fill(panelPath, with: .color(.green.opacity(0.3)))
                #if canImport(UIKit)
                if let ui = WatchHoleMapSample.image {
                    layer.draw(layer.resolve(Image(uiImage: ui)),
                               in: CGRect(x: panel.minX - 60, y: panel.minY - 40, width: panel.width + 200, height: panel.height + 200))
                }
                #endif
            }
        }
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-clip-image")
    }

    @MainActor
    func testRenderWatchHoleMapCanvasOnly() throws {
        // Bisect: the Canvas layer ONLY (no Text overlay). If this renders but watch-holeview does not,
        // the culprit is the Text overlay; if both render, the Canvas rewrite fixed the nil cgImage.
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1]
        let pips = (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 4) }
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5,
            ringPips: pips,
            showTextOverlay: false
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-hv-canvasonly")
    }

    // MARK: - Round-start flow screens (course → nine → tee → scorecard → hole grid)

    @MainActor
    func testRenderFlowCourse() throws {
        let view = WatchCourseSelectView(rows: [
            ("北京丽宫 · 山景", "Par 72 · 0.4 km", true),
            ("华彬庄园", "Par 72 · 3.1 km", false),
            ("九华山庄", "Par 71 · 8.6 km", false),
        ])
        try render(view, named: "flow-course")
    }

    @MainActor
    func testRenderFlowNine() throws {
        let view = WatchNineSelectView(title: "打几洞", options: [
            (label: "全 18 洞", sub: "前九 + 后九", primary: true),
            (label: "前 9 洞", sub: "1–9", primary: false),
            (label: "后 9 洞", sub: "10–18", primary: false),
        ])
        try render(view, named: "flow-nine")
    }

    @MainActor
    func testRenderFlowTee() throws {
        let gold = Color(red: 1.0, green: 0.84, blue: 0.2)
        let view = WatchTeeSelectView(title: "发球台", tees: [
            (name: "蓝 T", yards: 6821, color: .blue, selected: false),
            (name: "白 T", yards: 6200, color: .white, selected: true),
            (name: "金 T", yards: 5750, color: gold, selected: false),
            (name: "红 T", yards: 5210, color: .red, selected: false),
        ])
        try render(view, named: "flow-tee")
    }

    @MainActor
    func testRenderFlowScorecard() throws {
        let sc: [Int: Int] = [1: 4, 2: 6, 3: 2]
        let pars: [Int: Int] = [1: 4, 2: 5, 3: 3, 4: 4, 5: 4, 6: 3, 7: 5, 8: 4, 9: 4]
        let holes: [(hole: Int, par: Int, score: Int?)] = (1...9).map { (hole: $0, par: pars[$0] ?? 4, score: sc[$0]) }
        let view = WatchRoundScorecardView(holes: holes, toPar: 2)
        try render(view, named: "flow-scorecard")
    }

    @MainActor
    func testRenderFlowHoleGrid() throws {
        let sc: [Int: Int] = [1: 0, 2: 1, 3: -1]
        let holes: [(hole: Int, toPar: Int?, current: Bool)] = (1...18).map { (hole: $0, toPar: sc[$0], current: $0 == 4) }
        let view = WatchHoleGridView(holes: holes)
        try render(view, named: "flow-holes")
    }

    @MainActor
    func testRenderWatchHoleMapZoom() throws {
        // Zoomed full-map state (tap the map): data column hidden, map fills the width + zooms in, with a
        // top-centre distance + zoom hints.
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1]
        let pips = (1...18).map { WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 4) }
        let view = WatchHoleMapView(holeNumber: 4, par: 5, centerGreen: 287, ringPips: pips, fullMap: true)
            .frame(width: 198, height: 242)
            .background(Color.black)
        try render(view, named: "watch-holeview-zoom")
    }

    @MainActor
    func testRenderFlowHub() throws {
        let view = WatchRoundHubView(course: "北京丽宫 · 山景", hole: 4, par: 5, toPar: 2)
        try render(view, named: "flow-hub")
    }

    @MainActor
    func testRenderFlowGreen() throws {
        let view = WatchGreenPreviewView(front: 273, center: 287, back: 300)
        try render(view, named: "flow-green")
    }

    @MainActor
    func testRenderFlowTarget() throws {
        let view = WatchTargetView(title: "触碰测距 · 障碍", toTarget: 205, targetToGreen: 100, carryFront: 215, carryBack: 232)
        try render(view, named: "flow-target")
    }

    @MainActor
    func testRenderFlowNine9() throws {
        let view = WatchNineSelectView(title: "先打哪个9", options: [
            (label: "前九", sub: "1–9 · 3220 码", primary: true),
            (label: "中九", sub: "10–18 · 3180 码", primary: false),
            (label: "后九", sub: "19–27 · 3300 码", primary: false),
        ])
        try render(view, named: "flow-nine9")
    }

    @MainActor
    func testRenderWatchScorecard() throws {
        let view = WatchScorecardView(
            holes: [
                WatchScorecardRow(hole: 1, par: 4, score: 4),
                WatchScorecardRow(hole: 2, par: 5, score: 6),
                WatchScorecardRow(hole: 3, par: 3, score: 2),
                WatchScorecardRow(hole: 4, par: 4, score: 5),
                WatchScorecardRow(hole: 5, par: 4, score: 0),
            ],
            totalToPar: 2
        )
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-scorecard")
    }

    @MainActor
    func testRenderWatchHoleSelect() throws {
        let view = WatchHoleSelectView(holes: Array(1...18), activeHole: 7)
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-hole-select")
    }

    @MainActor
    func testRenderWatchMenu() throws {
        let view = WatchMenuView()
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-menu")
    }

    @MainActor
    func testRenderWatchScoreHole() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0
        )
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-score-hole")
    }

    @MainActor
    func testRenderWatchFinishRound() throws {
        let view = WatchFinishRoundView(
            courseName: "北京丽宫 · 前九",
            holesPlayed: 9, holeCount: 9,
            totalStrokes: 41, toPar: 5, totalPutts: 16, pendingUploads: 2
        )
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-finish-round")
    }

    @MainActor
    func testRenderWatchStart() throws {
        let view = WatchStartView(phoneReachable: false)
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-start")
    }

    @MainActor
    func testRenderWatchRoundContainerHome() throws {
        let model = makeSeededModel(scoring: false)   // hold a strong ref through render
        let view = WatchRoundContainerView(model: model)
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-container-home")
    }

    @MainActor
    func testRenderWatchRoundContainerScoring() throws {
        let model = makeSeededModel(scoring: true)     // hold a strong ref through render
        let view = WatchRoundContainerView(model: model)
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-container-scoring")
    }

    /// A standalone round seeded into a real (temp-dir) store, so the container snapshot exercises the
    /// full `WatchRoundModel` → view wiring rather than hand-built props.
    @MainActor
    private func makeSeededModel(scoring: Bool) -> WatchRoundModel {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("wsnap-\(UUID().uuidString)", isDirectory: true)
        let model = WatchRoundModel(store: WatchRoundStore(directoryURL: dir))
        let holes = [
            WatchRoundState(roundId: "r1", hole: 1, par: 4, distanceM: 320, selectedClub: nil,
                            score: 4, putts: 2, penaltyCount: 0, caddieConfidence: "offline"),
            WatchRoundState(roundId: "r1", hole: 2, par: 3, distanceM: 158, selectedClub: nil,
                            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"),
            WatchRoundState(roundId: "r1", hole: 3, par: 5, distanceM: 480, selectedClub: nil,
                            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"),
        ]
        model.seedRound(holes, activeHole: 2, courseName: "北京丽宫 · 前九")
        if scoring { model.startScoringActiveHole() }
        return model
    }

    @MainActor
    private func render(_ view: some View, named name: String) throws {
        // watchOS UI is dark; render in dark mode so `.primary` text is white (not black-on-black).
        let renderer = ImageRenderer(content: view.environment(\.colorScheme, .dark))
        renderer.scale = 2
        // Use cgImage + ImageIO (UIImage/pngData isn't reliably available on watchOS).
        guard let cgImage = renderer.cgImage else {
            XCTFail("ImageRenderer produced no image for \(name)")
            return
        }
        let dir = try FileManager.default
            .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("watch-snapshots", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("\(name).png")
        guard let destination = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) else {
            XCTFail("could not create PNG destination for \(name)")
            return
        }
        CGImageDestinationAddImage(destination, cgImage, nil)
        guard CGImageDestinationFinalize(destination) else {
            XCTFail("could not finalize PNG for \(name)")
            return
        }
        print("WROTE_WATCH_SNAPSHOT \(name)")
    }
}
