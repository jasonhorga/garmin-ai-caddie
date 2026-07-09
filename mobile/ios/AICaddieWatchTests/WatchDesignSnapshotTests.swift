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
