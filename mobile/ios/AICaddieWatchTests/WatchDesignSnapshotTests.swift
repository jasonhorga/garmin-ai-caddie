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

    @MainActor
    func testRenderWatchRoundContainerHoleMap() throws {
        // Phase 1b: the full .holeMap screen through the container — geometry built the REAL way
        // (WatchHoleMapGeometry.from(pushed WatchHoleMap + cached topo)), hole data mapped from the seeded
        // WatchRoundState (greens→码, suggestedClub), NO scoring ring, + the bottom-leading back-to-hub button.
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("wsnap-\(UUID().uuidString)", isDirectory: true)
        let model = WatchRoundModel(store: WatchRoundStore(directoryURL: dir))
        let hm = WatchHoleMap(
            w: Int(WatchHoleMapSample.imageSize.width), h: Int(WatchHoleMapSample.imageSize.height),
            you: [504, 702], pin: [435, 279], layup: [506, 403], apex: [556, 562], greenCtrl: [498, 375]
        )
        let state = WatchRoundState(
            roundId: "r1", hole: 4, par: 5, distanceM: 262,
            suggestedClub: "3号木", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            globalId: 31669, holeMap: hm,
            elevationDeltaM: 7,   // real mesh slope ⇒ 实打 shown
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        // A few scored holes so the KEPT scoring ring has real pips (owner 2026-07-08).
        let holes = [
            WatchRoundState(roundId: "r1", hole: 1, par: 4, distanceM: 0, selectedClub: nil,
                            score: 4, putts: 2, penaltyCount: 0, caddieConfidence: "offline"),
            WatchRoundState(roundId: "r1", hole: 2, par: 3, distanceM: 0, selectedClub: nil,
                            score: 2, putts: 1, penaltyCount: 0, caddieConfidence: "offline"),
            WatchRoundState(roundId: "r1", hole: 3, par: 5, distanceM: 0, selectedClub: nil,
                            score: 6, putts: 2, penaltyCount: 0, caddieConfidence: "offline"),
            state,
        ]
        model.seedRound(holes, activeHole: 4, courseName: "测试球场")
        model.openHoleMap()
        let geometry = try XCTUnwrap(WatchHoleMapGeometry.from(holeMap: hm, image: WatchHoleMapSample.image))
        let view = WatchRoundContainerView(model: model, holeGeometry: geometry)
            .frame(width: 198, height: 242)
            .background(Color.black)
        try render(view, named: "watch-container-holemap")
    }

    @MainActor
    func testRenderWatchDistanceHero() throws {
        // watch P1f: the no-geometry FALLBACK for the hole view — F/M/B hero (center biggest, Garmin S70).
        let view = WatchDistanceHero(frontYd: 248, centerYd: 262, backYd: 274, caddieLine: "3号木 · 稳妥")
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-distance-hero")
    }

    @MainActor
    func testRenderWatchDistanceHeroBig() throws {
        // watch P1f (spec D1 大字模式): tapping the hole view blows the center number up for arm's-length.
        let view = WatchDistanceHero(frontYd: 248, centerYd: 262, backYd: 274, caddieLine: "3号木 · 稳妥", bigText: true)
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-distance-hero-big")
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
    func testRenderWatchHoleMap() throws {
        // watch P1 (consensus 主打球屏 = watch-holeview.png): real-topo hole map (left data column +
        // right map on the baked sample geometry) + F/M/B + caddie chip + edge scoring ring. Uses the
        // default `WatchHoleMapSample.geometry`; the real playing view feeds a fetched image + projection.
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
        try render(view, named: "watch-holemap")
    }

    @MainActor
    func testRenderWatchHoleMapPlaysLike() throws {
        // 实打 TOGGLE: 后/中/前 flip to slope-adjusted values with a ↑ arrow (+8 uphill → plays longer).
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
        try render(view, named: "watch-holemap-pl")
    }

    @MainActor
    func testRenderWatchHoleMapMeasured() throws {
        // watch P2 选点测距: a tapped point → crosshair + distance-from-you pill (derived from 中 yardage).
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5, frontGreen: 273, centerGreen: 287, backGreen: 300,
            lastShot: 0, ringPips: [],
            measuredPxOverride: CGPoint(x: 470, y: 470)
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-holemap-measured")
    }

    @MainActor
    func testRenderWatchHoleMapPinDrag() throws {
        // watch P2 拖旗: dragging the flag previews 到旗 from the moved pin.
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5, frontGreen: 273, centerGreen: 287, backGreen: 300,
            lastShot: 0, ringPips: [],
            pinDragOverride: CGSize(width: 16, height: 20)
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-holemap-pindrag")
    }

    // MARK: - design-system unification batch (2026-07-10): the missing / new screens

    @MainActor
    func testRenderWatchHoleMapZoom() throws {
        // #6 放大态: full-map (data column hidden, map fills + zooms, ring gone).
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5, frontGreen: 273, centerGreen: 287, backGreen: 300,
            lastShot: 200, caddieClub: "3号木", caddieNote: "推进 · 留100",
            ringPips: [], fullMap: true
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-holemap-zoom")
    }

    @MainActor
    func testRenderWatchHoleMapHazard() throws {
        // #7 障碍上图: a sand bunker on the play line → amber near/far dots + 进/过 carry pills, on the
        // REAL baked sample geometry (placed at 42%/52% along the actual you→pin line).
        let base = WatchHoleMapSample.geometry
        func lerp(_ t: CGFloat) -> CGPoint {
            CGPoint(x: base.youPx.x + t * (base.pinPx.x - base.youPx.x),
                    y: base.youPx.y + t * (base.pinPx.y - base.youPx.y))
        }
        let g = WatchHoleMapGeometry(
            image: base.image, imageSize: base.imageSize, youPx: base.youPx, pinPx: base.pinPx,
            layupPx: base.layupPx, apexPx: base.apexPx, greenCtrlPx: base.greenCtrlPx,
            hazards: [WatchMapHazard(kind: "bunker", nearPx: lerp(0.42), farPx: lerp(0.52))]
        )
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5, frontGreen: 273, centerGreen: 287, backGreen: 300,
            lastShot: 0, ringPips: [], fullMap: true, geometry: g
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-holemap-hazard")
    }

    @MainActor
    func testRenderWatchClubPicker() throws {
        // #17 选杆浮层 — the face of shot detection.
        let view = WatchClubPickerView(
            hole: 7, toPinYd: 135,
            clubs: [
                WatchClubPickerView.Club(name: "七号铁", carryYd: 152),
                WatchClubPickerView.Club(name: "八号铁", carryYd: 140),
                WatchClubPickerView.Club(name: "六号铁", carryYd: 165),
                WatchClubPickerView.Club(name: "挖起杆", carryYd: 95),
            ],
            recommended: "七号铁"
        )
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-club-picker")
    }

    @MainActor
    func testRenderWatchConfirm() throws {
        // #18 确认页 — irreversible only.
        let view = WatchConfirmView(title: "结束本场?", detail: "9 洞 · +5 · 保存并上传")
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-confirm")
    }

    @MainActor
    func testRenderWatchPinPointer() throws {
        // #5 旗向指引.
        let view = WatchPinPointerView(bearingDeg: -22, distanceYd: 152)
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-pinpointer")
    }

    @MainActor
    func testRenderWatchClubStats() throws {
        // #14 球杆统计 (no ± band).
        let view = WatchClubStatsView(rows: [
            .init(club: "一号木", carryYd: 245),
            .init(club: "三号木", carryYd: 218),
            .init(club: "五号铁", carryYd: 178),
            .init(club: "七号铁", carryYd: 152),
            .init(club: "挖起杆", carryYd: 95),
        ])
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-club-stats")
    }

    @MainActor
    func testRenderWatchHoleDetail() throws {
        // #12 洞详情 + 击球列表.
        let view = WatchHoleDetailView(hole: 7, par: 4, score: 5, shots: [
            .init(order: 1, club: "开球 一号木", yards: 245),
            .init(order: 2, club: "七号铁", yards: 152),
            .init(order: 3, club: "挖起杆", yards: 42),
            .init(order: 4, club: "推杆", yards: nil),
            .init(order: 5, club: "推杆", yards: nil),
        ])
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-hole-detail")
    }

    @MainActor
    func testRenderWatchCourseSelect() throws {
        // #19 选球场.
        let view = WatchCourseSelectView(courses: [
            .init(name: "北京丽宫 · 山景", par: 72, km: 0.4),
            .init(name: "华彬庄园", par: 72, km: 3.1),
            .init(name: "九华山庄", par: 71, km: 8.6),
        ])
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-course-select")
    }

    @MainActor
    func testRenderWatchNineSelect() throws {
        // #20 选 9/18.
        let view = WatchNineSelectView()
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-nine-select")
    }

    @MainActor
    func testRenderWatchTeeSelect() throws {
        // #21 选发球台 (slope/rating).
        let view = WatchTeeSelectView(tees: [
            .init(name: "蓝 T", color: Color(red: 0.24, green: 0.61, blue: 1.0), yards: 6821, slope: 132),
            .init(name: "白 T", color: .white, yards: 6200, slope: 126),
            .init(name: "金 T", color: Color(red: 1.0, green: 0.83, blue: 0.28), yards: 5750, slope: 121),
            .init(name: "红 T", color: Color(red: 1.0, green: 0.27, blue: 0.23), yards: 5210, slope: 118),
        ], selected: "白 T")
        .frame(width: 198)
        .background(Color.black)
        try render(view, named: "watch-tee-select")
    }

    @MainActor
    func testRenderWatchSettings() throws {
        // #15 设置.
        let view = WatchSettingsView(gpsPrewarm: true, bigText: false, wristRight: false)
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-settings")
    }

    @MainActor
    func testRenderWatchAOD() throws {
        // #22 AOD 息屏大字.
        let view = WatchAODView(centerYd: 262, hole: 4, par: 5)
            .frame(width: 198, height: 198)
        try render(view, named: "watch-aod")
    }

    @MainActor
    func testRenderWatchStatusSearching() throws {
        // #25 GPS 异常.
        let view = WatchStatusView(kind: .searching)
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-status-searching")
    }

    @MainActor
    func testRenderWatchStatusLowBattery() throws {
        // #25 低电.
        let view = WatchStatusView(kind: .lowBattery)
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-status-lowbattery")
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
