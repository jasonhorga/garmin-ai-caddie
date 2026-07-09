#if DEBUG
import SwiftUI

/// Real-runtime watch screenshots: launched with `-uitest-screen <name>` (via `simctl launch`), the watch
/// app renders the REAL target view with demo data at its root so `simctl io screenshot` captures it in
/// the actual watchOS simulator runtime — including List/ScrollView content that ImageRenderer design
/// snapshots cannot render. DEBUG-only: never compiled into the Release/TestFlight binary. watchOS has no
/// XCUITest, so this direct-render-by-arg harness is how the watch surfaces get genuine running-app shots.
public struct WatchUITestRoot: View {
    public let screen: String

    public init(screen: String) {
        self.screen = screen
    }

    /// Reads `-uitest-screen <name>` from the launch arguments; nil when not a UI-test launch.
    public static func requestedScreen() -> String? {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "-uitest-screen"), index + 1 < args.count else {
            return nil
        }
        return args[index + 1]
    }

    public var body: some View {
        switch screen {
        case "home":
            WatchRoundHomeView(
                courseName: "北京丽宫 · 前九", hole: 7, par: 4, holeCount: 9,
                scoredHoles: 6, toPar: 3, distanceText: "152 码", pendingUploads: 2,
                ringPips: (1...18).map { WatchRingPip(hole: $0, toPar: Self.demoToPars[$0], isCurrent: $0 == 7) }
            )
        case "caddie-options":
            WatchCaddieOptionsView(options: Self.demoOptions, recommendedId: "stock")
                .padding(8)
        case "hazards":
            WatchHazardView(hazards: Self.demoHazards)
                .padding(8)
        case "glance":
            WatchCaddieGlanceView(state: Self.demoState)
                .padding(8)
        case "scorecard":
            WatchScorecardView(holes: Self.demoScorecard, totalToPar: 2)
        case "hole-select":
            WatchHoleSelectView(holes: Array(1...18), activeHole: 7)
        case "menu":
            WatchMenuView()
        case "score":
            WatchScoreHoleView(hole: 7, par: 4, score: 5, putts: 2, penalty: 0)
        case "finish":
            WatchFinishRoundView(
                courseName: "北京丽宫 · 前九", holesPlayed: 9, holeCount: 9,
                totalStrokes: 41, toPar: 5, totalPutts: 16, pendingUploads: 2
            )
        case "start":
            WatchStartView(phoneReachable: false)
        case "hole-map":
            // Real hole map on the baked sample topo — for touch/XCUITest + screenshots.
            WatchHoleMapView(
                holeNumber: 4, par: 5, frontGreen: 273, centerGreen: 287, backGreen: 300,
                playsLikeDelta: 8, lastShot: 200, caddieClub: "3号木", caddieNote: "推进 · 留100",
                ringPips: (1...18).map { WatchRingPip(hole: $0, toPar: Self.demoToPars[$0], isCurrent: $0 == 4) },
                geometry: WatchHoleMapSample.geometry
            )
        case "distance-hero":
            WatchDistanceHero(frontYd: 248, centerYd: 262, backYd: 274, caddieLine: "3号木 · 稳妥")
        case "live-gps":
            // The moving-fix video lane: real WatchLocationProvider fed by `simctl location`.
            WatchLiveGpsDemoView()
        default:
            Text("unknown uitest screen: \(screen)")
        }
    }

    // MARK: - demo data (mirrors the design-snapshot fixtures)

    private static let demoToPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 2, 5: 0, 6: 1]

    static let demoOptions: [WatchCaddieOption] = [
        WatchCaddieOption(optionId: "safe", label: "稳妥", clubName: "9号铁", carryM: 128, expectedStrokes: 3.1, confidence: "high"),
        WatchCaddieOption(optionId: "stock", label: "标准", clubName: "8号铁", carryM: 142, expectedStrokes: 3.0, confidence: "high"),
        WatchCaddieOption(optionId: "attack", label: "进攻", clubName: "7号铁", carryM: 156, expectedStrokes: 3.2, confidence: "medium"),
    ]

    static let demoHazards: [WatchHazard] = [
        WatchHazard(kind: "bunker", label: "沙坑 1", startM: 120, endM: 140),
        WatchHazard(kind: "bunker", label: "沙坑 2", startM: 165, endM: 178),
        WatchHazard(kind: "water", label: "水域", startM: 210, endM: 235),
    ]

    static let demoScorecard: [WatchScorecardRow] = [
        WatchScorecardRow(hole: 1, par: 4, score: 4),
        WatchScorecardRow(hole: 2, par: 5, score: 6),
        WatchScorecardRow(hole: 3, par: 3, score: 2),
        WatchScorecardRow(hole: 4, par: 4, score: 5),
        WatchScorecardRow(hole: 5, par: 4, score: 0),
    ]

    static let demoState = WatchRoundState(
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
        caddieOptions: demoOptions, hazards: demoHazards,
        score: 4, putts: 2, penaltyCount: 0, caddieConfidence: "high"
    )
}

/// The moving-GPS demo hole map for the `live-gps` video lane: a real `WatchLocationProvider` (fed by
/// `xcrun simctl location start`) drives you-pixel (projected through demo refs onto the sample topo) and
/// live F/M/B green yardage, exactly like the shipping App does — so `recordVideo` captures "you" walking
/// down the fairway with the distances counting down. DEBUG/uitest only.
struct WatchLiveGpsDemoView: View {
    @StateObject private var loc = WatchLocationProvider()
    // Demo refs map a small lat/lon region onto the sample topo px: tee→green up the fairway (+ one east
    // point to fix the affine shear). The `simctl location` route below walks tee→green.
    private let refs = [
        WatchProjectionRef(lat: 40.0000, lon: 116.00000, px: 504, py: 702),  // tee
        WatchProjectionRef(lat: 40.0036, lon: 116.00000, px: 435, py: 279),  // green (~400 m north)
        WatchProjectionRef(lat: 40.0000, lon: 116.00117, px: 612, py: 716),  // ~100 m east
    ]
    private let greenLat = 40.0036, greenLon = 116.00000

    var body: some View {
        WatchHoleMapView(
            holeNumber: 4, par: 5,
            frontGreen: fmb(-6), centerGreen: fmb(0), backGreen: fmb(6),
            lastShot: 0, caddieClub: "3号木", caddieNote: "推进",
            ringPips: [], geometry: geo()
        )
        .onAppear {
            loc.requestAuthorization()
            loc.startUpdatingLocation()
        }
    }

    private func geo() -> WatchHoleMapGeometry {
        let base = WatchHoleMapSample.geometry
        guard let fix = loc.latestFix,
              let px = WatchGeoMath.projectToTopoPx(lat: fix.coordinate.latitude, lon: fix.coordinate.longitude, refs: refs)
        else { return base }
        return base.withYou(px)
    }

    private func fmb(_ deltaM: Double) -> Int {
        guard let fix = loc.latestFix else { return 0 }
        let c = fix.coordinate
        return WatchGeoMath.yards(max(0, WatchGeoMath.metres(c.latitude, c.longitude, greenLat, greenLon) + deltaM))
    }
}
#endif
