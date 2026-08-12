import SwiftUI
import UIKit
import XCTest
@testable import AICaddie

/// Renders the redesigned SwiftUI surfaces to PNGs in the simulator so the design
/// can be reviewed from CI without a physical device / TestFlight. The workflow
/// collects `Documents/design-snapshots/*.png` from the simulator container and
/// uploads them as the `design-snapshots` artifact.
final class DesignSnapshotTests: XCTestCase {
    func testLiveCaddieClubIdentityIsStableAcrossRenderPasses() {
        let first = LiveCaddieStrip.Club(name: "三号木", sub: "192 码", on: true)
        let second = LiveCaddieStrip.Club(name: "三号木", sub: "192 码", on: true)

        XCTAssertEqual(
            first.id,
            second.id,
            "recomputing CurrentHoleView must not replace every club chip with a new SwiftUI identity"
        )
    }

    @MainActor
    func testRenderLiveHoleRedesign() throws {
        let view = VStack(spacing: 12) {
            HoleDistanceHeader(
                course: "北京丽宫 · 前九", holeNumber: 7, holeCount: 9, par: 4,
                toPinYards: 152, carryFrontYards: nil, toParText: "+1",
                greenFrontYards: 140, greenCenterYards: 148, greenBackYards: 155, slopeYards: 3,
                isGreenLive: true  // round-13 B1: capture the LIVE GPS rangefinder badge
            )
            CaddieRecCard(
                modeTitle: "球童建议 · 保守(护分)",
                recommendation: "7 号铁 · 上果岭中心偏左",
                rationale: "右侧沙坑 138–150 码,落点避开;球道偏窄,优先保帕。",
                chips: [(text: "期望失分最低", warn: false), (text: "命中 64%", warn: false), (text: "右沙坑", warn: true)]
            )
            VStack(alignment: .leading, spacing: 10) {
                Text("选球杆").font(.caption).foregroundStyle(.secondary)
                ClubStripView(clubs: ["5i", "6i", "7i", "8i", "9i", "PW"], selected: "7i")
                RecordShotButton(title: "📍 保存本洞 · 含定位", lastShotText: "已定位 · 精度 ±4m · 球杆 7i")
            }
            .liveCard()
            VStack(alignment: .leading, spacing: 10) {
                Text("本洞成绩").font(.caption).foregroundStyle(.secondary)
                HoleScoreSteppers(score: .constant(4), putts: .constant(2))
            }
            .liveCard()
        }
        .padding(14)
        .frame(width: 390)
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))

        try render(view, named: "live-hole")
    }

    /// 打球屏 v2 reskin: DARK map-backdrop + Apple-Maps-style glass data panel (distance hero →
    /// caddie strip → shot/score actions → scorecard action). Rendered as a fixed non-scroll composition
    /// (ImageRenderer does not render ScrollView content) so it captures cleanly in CI.
    @MainActor
    func testRenderLivePlayReskin() throws {
        let view = ZStack(alignment: .top) {
            LivePlayStyle.base
            LinearGradient(
                colors: [Color(red: 26 / 255, green: 46 / 255, blue: 30 / 255), LivePlayStyle.base],
                startPoint: .top, endPoint: .bottom
            )
            .frame(height: 360)
            .frame(maxWidth: .infinity, alignment: .top)
            LivePlayStyle.topScrim
                .frame(height: 176)
                .frame(maxWidth: .infinity, alignment: .top)
            LivePlayReticle().offset(x: 30, y: 96)
            LiveHazardPill(text: "水域 · 到 213 · 过 235 码").offset(x: 54, y: 150)
            VStack(spacing: 0) {
                LivePlayHeader(holeNumber: 1, par: 5, yards: 543, teeLabel: "蓝T", roundToParText: "本场 +4")
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
                Spacer(minLength: 0)
                LivePlayPanel {
                    LiveDistanceReadout(
                        greenFrontYards: 205, greenCenterYards: 219, greenBackYards: 231,
                        toPinYards: 245, isGreenLive: false
                    )
                    Rectangle().fill(LivePlayStyle.hair).frame(height: 1).padding(.horizontal, 2)
                    LiveCaddieStrip(
                        clubs: [
                            .init(name: "3W", sub: "238 码", on: true),
                            .init(name: "5W", sub: "215 码", on: false),
                            .init(name: "4i", sub: "198 码", on: false),
                        ],
                        playsText: "实打约 +8 码(上坡)· 打球道左中,避右侧水"
                    )
                    LiveHolePrimaryActions(canRecordShot: true, recordedShotCount: 1)
                    LiveScorecardButton()
                }
                .padding(.horizontal, 10)
                .padding(.bottom, 10)
            }
        }
        .frame(width: 390, height: 780)
        .background(LivePlayStyle.base)

        try render(view, named: "live-play")
    }

    /// A restored round can briefly retain the previous hole's fix, or be opened miles from the
    /// course. The rangefinder must stay a three-digit golf instrument instead of wrapping 1527 / 1553
    /// / 1579 across two lines while the next qualified fix arrives.
    @MainActor
    func testRenderLiveDistanceOffCourseBoundary() throws {
        let view = LivePlayPanel {
            LiveDistanceReadout(
                greenFrontYards: 1_527,
                greenCenterYards: 1_553,
                greenBackYards: 1_579,
                toPinYards: nil,
                isGreenLive: true
            )
        }
        .padding(16)
        .frame(width: 390, height: 240)
        .background(LivePlayStyle.base)

        try render(view, named: "live-distance-off-course")
    }

    func testLivePlayAuxiliaryCardTokenStaysDark() {
        let color = UIColor(LivePlayStyle.auxiliaryFill)
        var red: CGFloat = 0
        var green: CGFloat = 0
        var blue: CGFloat = 0
        var alpha: CGFloat = 0

        XCTAssertTrue(color.getRed(&red, green: &green, blue: &blue, alpha: &alpha))
        XCTAssertLessThan(max(red, green, blue), 0.20)
        XCTAssertEqual(alpha, 1, accuracy: 0.001)
    }

    func testLiveHazardPillUsesTheLaneOppositeTheClubLandingLabel() {
        let heroHeight: CGFloat = 360
        let upperLanding = LivePlayMapOverlayLayout.hazardPillCenterY(
            heroHeight: heroHeight,
            landingCenterY: heroHeight * 0.42
        )
        let lowerLanding = LivePlayMapOverlayLayout.hazardPillCenterY(
            heroHeight: heroHeight,
            landingCenterY: heroHeight * 0.78
        )
        let unknownLanding = LivePlayMapOverlayLayout.hazardPillCenterY(
            heroHeight: heroHeight,
            landingCenterY: nil
        )

        XCTAssertEqual(upperLanding, 252, accuracy: 0.001)
        XCTAssertEqual(lowerLanding, 172.8, accuracy: 0.001)
        XCTAssertEqual(unknownLanding, upperLanding, accuracy: 0.001)
        XCTAssertGreaterThan(abs(upperLanding - heroHeight * 0.42 + 18), 80)
        XCTAssertGreaterThan(abs(lowerLanding - heroHeight * 0.78 + 18), 80)
    }

    func testLiveGreenTargetUsesTheSameAspectFitProjectionAsTheHoleMap() throws {
        let hero = CGSize(width: 390, height: 360)
        let topLeft = try XCTUnwrap(LivePlayMapOverlayLayout.project(
            overlayPoint: [0, 0],
            overlayWidth: 780,
            overlayHeight: 1_400,
            into: hero
        ))
        let green = try XCTUnwrap(LivePlayMapOverlayLayout.project(
            overlayPoint: [390, 140],
            overlayWidth: 780,
            overlayHeight: 1_400,
            into: hero
        ))

        XCTAssertEqual(topLeft.x, 94.714, accuracy: 0.001)
        XCTAssertEqual(topLeft.y, 0, accuracy: 0.001)
        XCTAssertEqual(green.x, 195, accuracy: 0.001)
        XCTAssertEqual(green.y, 36, accuracy: 0.001)
        XCTAssertNotEqual(green, LivePlayMapOverlayLayout.fallbackGreenTarget(in: hero))
    }

    func testLiveMapHeaderInsetKeepsAFactualTopGreenAndReticleBelowTheTitle() throws {
        let hero = CGSize(width: 390, height: 360)
        let green = try XCTUnwrap(LivePlayMapOverlayLayout.project(
            overlayPoint: [390, 140],
            overlayWidth: 780,
            overlayHeight: 1_400,
            into: hero,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        ))

        XCTAssertEqual(green.x, 195, accuracy: 0.001)
        XCTAssertEqual(green.y, 108, accuracy: 0.001)
        XCTAssertGreaterThanOrEqual(
            green.y - 30,
            LivePlayMapOverlayLayout.liveMapTopInset - 2,
            "the 60-point reticle must not cross back into the fixed header lane"
        )
    }

    func testParThreeClubLabelMovesOutsideTheGreenTargetReticle() {
        let pin = CGPoint(x: 180, y: 90)

        XCTAssertEqual(
            HoleImageMapView.clubLabelPoint(landing: CGPoint(x: 182, y: 92), pin: pin),
            CGPoint(x: 180, y: 134)
        )
        XCTAssertEqual(
            HoleImageMapView.clubLabelPoint(landing: CGPoint(x: 180, y: 220), pin: pin),
            CGPoint(x: 180, y: 202)
        )
    }

    func testMediaCaptureCustomerCopyIsChinese() {
        XCTAssertEqual(MediaCaptureCopy.empty, "尚未添加照片或视频")
        XCTAssertEqual(MediaCaptureCopy.unavailable, "无法读取所选媒体")
        XCTAssertEqual(MediaCaptureCopy.savedOffline(kind: "photo"), "照片已离线保存，待联网后上传")
        XCTAssertEqual(MediaCaptureCopy.attached(kind: "video"), "视频已添加")
        XCTAssertEqual(MediaCaptureCopy.confirmed, "识别结果已确认，可用于球童建议")
    }

    @MainActor
    func testRenderLivePlayAuxiliaryCard() throws {
        let view = VStack(alignment: .leading, spacing: 8) {
            Label("更多调整", systemImage: "slider.horizontal.3")
                .font(.headline)
            Text("球杆 · 打法 · 球位 · 距离 · 目标 · 备注")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .livePlayAuxiliaryCard()
        .padding(14)
        .frame(width: 390)
        .background(LivePlayStyle.base)

        try render(view, named: "live-play-auxiliary-card")
    }

    @MainActor
    func testRenderRecentReview() throws {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: fixtureURL))
        let view = RecentReviewContent(package: package)
            .frame(width: 390)
            .background(HubStyle.grouped)
        try render(view, named: "recent-review")
    }

    @MainActor
    func testRenderSignIn() throws {
        let view = SignInView(apiBaseURL: URL(string: "https://example.test")) { _ in }
        try render(view, named: "sign-in")
    }

    @MainActor
    func testRenderRoundHome() throws {
        let view = VStack(spacing: 14) {
            HubInProgressCard(courseName: "北京丽宫 · 前九", activeHole: 8, recorded: 7, total: 9)
            HubPlayTile()
            HStack(spacing: 11) {
                HubTile(icon: "scope", title: "备战", subtitle: "搜索 · 球童试算")
                HubTile(icon: "chart.line.uptrend.xyaxis", title: "成绩", subtitle: "球局 · 统计")
            }
            VStack(alignment: .leading, spacing: 9) {
                HubSectionLabel("上一场")
                HubLastRoundCard(courseName: "Cypress Point Club", date: "2026-07-30", score: 55, toPar: -20,
                                 holesCompleted: 18, par: 75,
                                 topoURL: SyncClient.topoImageURL(
                                     baseURL: URL(string: "https://caddie.example")!, globalId: 3881, localHole: 1))
            }
        }
        .padding(16)
        .frame(width: 390)
        .background(HubStyle.grouped)
        try render(view, named: "round-home")
    }

    @MainActor
    func testLastRoundCardKeepsLongCourseNameWithinTwoLineCardHeight() {
        let card = HubLastRoundCard(
            courseName: "北京北湖九号国际高尔夫俱乐部",
            date: "2026-07-30",
            score: 98,
            toPar: 26,
            holesCompleted: 18,
            par: 75,
            topoURL: SyncClient.topoImageURL(
                baseURL: URL(string: "https://caddie.example")!,
                globalId: 3881,
                localHole: 1
            )
        )
        .frame(width: 358)
        let host = UIHostingController(rootView: card)
        let measured = host.sizeThatFits(in: CGSize(width: 358, height: 1_000))

        XCTAssertLessThanOrEqual(
            measured.height,
            112,
            "the last-round card must not grow into a four-line course-name tower"
        )
    }

    @MainActor
    func testRenderCaddiePlan() throws {
        func option(_ id: String, _ label: String, _ club: String, _ carry: Double, _ risk: Double) -> CaddiePlanOption {
            CaddiePlanOption(
                id: id, label: label, carryM: carry, riskScore: risk, clubName: club,
                p10M: nil, p90M: nil, sampleSize: 42, confidence: "high", coverageText: "8/10",
                expectedStrokes: 4.0, expectedStrokesDelta: -0.2, scoreImpactModel: nil,
                sourceRefs: ["geometry:31795:7"], missingDataLabels: []
            )
        }
        func step(_ role: String, _ club: String, _ carry: Double, _ remaining: Double) -> CaddiePlanSequenceStep {
            CaddiePlanSequenceStep(id: "\(role)-\(club)", role: role, clubName: club, targetCarryM: carry,
                                   expectedRemainingM: remaining, sampleSize: 42, confidence: "high", sourceRefs: [])
        }
        func sequence(_ id: String, _ confidence: String, _ steps: [CaddiePlanSequenceStep]) -> CaddiePlanSequence {
            CaddiePlanSequence(id: id, label: steps.map(\.clubName).joined(separator: "-"),
                               expectedRemainingM: steps.last?.expectedRemainingM, riskScore: nil, confidence: confidence,
                               coverageText: nil, sourceRefs: [], steps: steps)
        }
        // round-11: 整洞序列为主 — three 打法 each a 开球→攻果岭 chain (user-approved direction).
        let view = CaddiePlanView(
            options: [
                option("stock", "稳妥", "7i", 150, 1),
                option("attack", "进攻搏鸟", "6i", 165, 3),
                option("layup", "放置短切", "9i", 120, 1),
            ],
            selectedOptionId: "stock",
            sequences: [
                sequence("safe", "high", [step("advance", "3W", 160, 155), step("scoring", "6I", 150, 5)]),
                sequence("stock", "medium", [step("advance", "Driver", 180, 133), step("scoring", "PW", 130, 3)]),
                sequence("attack", "low", [step("advance", "Driver", 180, 133), step("scoring", "SW", 125, 8)]),
            ],
            selectedSequenceId: "stock",
            // Multiple mapped hazards are named by side/area and sorted near→far. Build via .from
            // to exercise the same player-facing logic as prep and live play.
            hazards: CaddiePlanHazard.from(
                CoursePrepHazards(
                    waterCarry: [[175, 195]],
                    bunkers: [[210, 18], [138, 12]],
                    details: [
                        CoursePrepHazardDetail(
                            kind: "water", frontM: 175, backM: 195,
                            frontRouteM: 175, backRouteM: 195,
                            frontPx: [100, 300], backPx: [100, 280], sideM: nil
                        ),
                        CoursePrepHazardDetail(
                            kind: "bunker", frontM: 207, backM: 224,
                            frontRouteM: 205, backRouteM: 225,
                            frontPx: [130, 260], backPx: [132, 240], sideM: 18
                        ),
                        CoursePrepHazardDetail(
                            kind: "bunker", frontM: 134, backM: 149,
                            frontRouteM: 132, backRouteM: 151,
                            frontPx: [112, 390], backPx: [114, 371], sideM: 12
                        ),
                    ]
                )
            )
        )
        .padding(14)
        .frame(width: 390)
        .background(Color.white)
        try render(view, named: "caddie-plan")
    }

    /// Full-screen capture of a REAL screen (NavigationStack + ScrollView render fully here,
    /// unlike SwiftUI ImageRenderer). Hosts the view in an on-screen UIWindow and snapshots
    /// the rendered hierarchy — what the running app actually draws (top viewport).
    @MainActor
    func testCaptureLiveScreens() throws {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: fixtureURL))

        // 黑骑士 = A/B/C 三个 9 洞环 + 北湖 = 单一 18 洞,验证按球场列环的选场 UI。
        let blackKnightTees = ["Gold", "Blue", "White", "Red"]
        let courses = [
            MobileCourseOption(globalId: 31794, name: "北京天竺黑骑士球员俱乐部 ~ A", roundCount: 40, suggestedLiveRoundId: "live-31794", holes: 9, teeBox: "blue", geometryCoverage: "ready", venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "A", segmentHoles: 9, tees: blackKnightTees),
            MobileCourseOption(globalId: 31795, name: "北京天竺黑骑士球员俱乐部 ~ B", roundCount: 30, suggestedLiveRoundId: "live-31795", holes: 9, teeBox: "blue", geometryCoverage: "ready", venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "B", segmentHoles: 9, tees: blackKnightTees),
            MobileCourseOption(globalId: 31796, name: "北京天竺黑骑士球员俱乐部 ~ C", roundCount: 58, suggestedLiveRoundId: "live-31796", holes: 9, teeBox: "blue", geometryCoverage: "ready", venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "C", segmentHoles: 9, tees: blackKnightTees),
            MobileCourseOption(globalId: 41825, name: "北京北湖九号国际高尔夫俱乐部", roundCount: 40, suggestedLiveRoundId: "live-41825", holes: 18, teeBox: "blue", geometryCoverage: "ready", venueName: "北京北湖九号国际高尔夫俱乐部", segmentLabel: nil, segmentHoles: 18, tees: ["Black", "Blue", "White", "Red"]),
        ]

        // Pass a non-nil apiBaseURL so the 备战 tile (gated on apiBaseURL) renders — without it
        // the snapshot hides 备战 and misrepresents the real app.
        let apiBaseURL = URL(string: "https://caddie.example")
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses), named: "full-home")
        // Hub WITH an in-progress round → shows the 进行中 card + 「结束本场」(cancel) button.
        let activeState = LiveRoundStateSnapshot(roundId: package.roundId, activeHole: package.holes.first?.number ?? 1, holes: [])
        try captureScreen(
            RoundHomeView(package: package, apiBaseURL: apiBaseURL, liveRoundState: activeState, courseOptions: courses, startingNine: "front"),
            named: "full-home-active"
        )
        try captureScreen(NavigationStack { StartRoundView(courseOptions: courses) }, named: "full-start")
        try captureScreen(NavigationStack { PrepCoursePickerView(courseOptions: courses, apiBaseURL: apiBaseURL, adminToken: nil) }, named: "full-prep-picker")
        try captureScreen(
            NavigationStack {
                MobileCourseSearchView(
                    locationProvider: LocationProvider(),
                    onSearch: { _, _ in [] },
                    onNearby: { _, _, _ in [] },
                    onSelect: { _, _ in }
                )
            },
            named: "full-course-search"
        )
        if let hole = package.holes.first {
            try captureScreen(NavigationStack { CurrentHoleView(package: package, hole: hole) }, named: "full-hole")
        }
        try captureScreen(RecentRoundReviewView(package: package), named: "full-review")

        // Dark Mode regression guard. WITHOUT the app's fix, the light-themed screens render
        // white-on-white in Dark Mode (cards Color.white, text semantic .primary → white).
        // WITH the app-root fix (.preferredColorScheme(.light)) the hierarchy renders light even
        // in a Dark window — these two captures document the bug and prove the fix.
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses), named: "dark-broken", dark: true)
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses).preferredColorScheme(.light), named: "dark-fixed", dark: true)

        // 2D hole map = server-rendered hole image + recommended route/landing/club overlay.
        // Synthesise a green hole image + overlay route so the overlay rendering is verifiable.
        let mapW = 240, mapH = 360
        let holeImage = UIGraphicsImageRenderer(size: CGSize(width: mapW, height: mapH)).image { ctx in
            UIColor(red: 0.46, green: 0.66, blue: 0.40, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: mapW, height: mapH))
            UIColor(red: 0.60, green: 0.78, blue: 0.45, alpha: 1).setFill()
            ctx.fill(CGRect(x: 92, y: 40, width: 56, height: 280))
            UIColor(red: 0.50, green: 0.80, blue: 0.43, alpha: 1).setFill()
            ctx.cgContext.fillEllipse(in: CGRect(x: 96, y: 28, width: 48, height: 42))
        }
        let b64 = "data:image/jpeg;base64," + (holeImage.jpegData(compressionQuality: 0.85)?.base64EncodedString() ?? "")
        let prepJSON = """
        {"hole":7,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,\
        "route":[[120,330],[118,180],[120,55]],"steps":[{"club":"D","note":"开球"}],\
        "cautions":[],"hazards":{"water_carry":[],"bunkers":[]},"landing_m":150,"tee_club":"D",\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":375,\
        "route":[[120,330,0],[118,180,150],[120,55,375]]}}}
        """
        let prepHole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(prepJSON.utf8))
        try captureScreen(VStack { HoleImageMapView(hole: prepHole).frame(height: 460) }.padding(24), named: "hole-map")

        // No-network topo fallback: pass a topoURL (as production does for a real course) but CI has
        // NO network, so the AsyncImage never resolves → the base layer must degrade to the flat
        // render + overlay, never a broken/empty box. Unreachable host guarantees no load.
        let unreachableTopo = URL(string: "http://127.0.0.1:9/api/v2/courses/1/holes/7/topo.png")
        try captureScreen(
            VStack { HoleImageMapView(hole: prepHole, topoURL: unreachableTopo).frame(height: 460) }.padding(24),
            named: "hole-map-topo-fallback"
        )

        // 备战逐洞卡 (reskin): 浅色 hubCard — 洞号 / Par / 蓝T / 实打坡度 + 真实球场图 + 球童试算(推荐球杆
        // 绿胶囊 + 果岭前/中/后码) + 逐步打法 + 障碍提示。渲染真实 HolePrepCard(整套 prep 数据)以验证浅色。
        let prepCardJSON = """
        {"hole":7,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,\
        "route":[[120,330],[118,180],[120,55]],"tee_club":"D","landing_m":150,\
        "steps":[{"club":"D","note":"开球打球道左中,避右侧沙坑"},{"club":"8I","note":"攻果岭中心,后方无碍"}],\
        "cautions":["果岭前缘有陡坡,落点宁长勿短"],\
        "hazards":{"water_carry":[[175,195]],"bunkers":[[210,18],[138,12]]},\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":375,\
        "route":[[120,330,0],[118,180,150],[120,55,375]]}},\
        "greenDistances":{"available":true,"frontM":128,"middleM":135,"backM":142},\
        "playsLike":{"available":true,"deltaM":7.3,"deltaYd":8}}
        """
        let prepCardHole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(prepCardJSON.utf8))
        try captureScreen(
            ScrollView { HolePrepCard(hole: prepCardHole).padding(14) }.background(HubStyle.grouped),
            named: "prep-hole"
        )

        // 单场复盘: compact KPIs + tappable score grid + graceful missing-data,
        // rendered from a round-detail fixture (mirrors /api/v2/history/rounds/{ref}).
        let roundJSON = """
        {"roundRef":"r1","found":true,"title":"Fixture Links",\
        "round":{"courseName":"Fixture Links","date":"2026-05-20","score":22,"par":20,"toPar":2,"holesCompleted":5,"confidence":"high"},\
        "scorecard":[\
        {"hole":1,"par":4,"score":5,"toPar":1,"className":"bogey","putts":2,"penalties":1,"status":"complete"},\
        {"hole":2,"par":3,"score":3,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"status":"complete"},\
        {"hole":3,"par":5,"score":4,"toPar":-1,"className":"birdie","putts":1,"penalties":0,"status":"complete"},\
        {"hole":4,"par":4,"score":6,"toPar":2,"className":"double","putts":3,"penalties":0,"fairway":"left","status":"complete"},\
        {"hole":5,"par":4,"score":4,"toPar":0,"className":"par","putts":2,"penalties":0,"status":"complete"}],\
        "phaseSummary":[\
        {"phase":"Tee","state":"ready","primary":"0/1 球道命中","metrics":{"fairwaysHit":0,"fairwaysRecorded":1}},\
        {"phase":"Approach","state":"ready","primary":"1/1 标准杆上果岭(GIR)","metrics":{"gir":1,"girRecorded":1}},\
        {"phase":"Short Game","state":"ready","primary":"2 次短杆","metrics":{"shots":2}},\
        {"phase":"Putting","state":"ready","primary":"10 推","metrics":{"totalPutts":10}},\
        {"phase":"Penalty / Damage","state":"ready","primary":"1 罚杆","metrics":{"totalPenalties":1}}],\
        "missingData":[{"label":"shot rows","state":"missing","reason":"no normalized Garmin shot rows for this round"}]}
        """
        let roundDetail = try JSONDecoder().decode(RoundDetail.self, from: Data(roundJSON.utf8))
        try captureScreen(
            ScrollView {
                RoundReviewContent(detail: roundDetail, isLoading: false, errorText: nil, fallbackCourseName: "Fixture Links")
            }
            .background(HubStyle.grouped),
            named: "round-review"
        )

        // 数据统计: overview KPIs + 近场折线图 + 成绩分布 + by-par(3/4/5) + putting + trends + quarter +
        // courses(按球场聚合,可钻取各九洞) + clubs (距离按码), from a compact mobile-stats fixture.
        let statsJSON = """
        {"summary":{"totalRounds":423,"average18":92.4,"median18":92,"recent10Average":94.6,"bestScore":82,"worstScore":106,"handicapEstimate":18.2},\
        "trend":{"points":[\
        {"date":"2026-05-01","score":95,"toPar":23,"birdies":1,"pars":6,"bogeys":7,"doublesPlus":4},\
        {"date":"2026-05-10","score":91,"toPar":19,"birdies":2,"pars":7,"bogeys":7,"doublesPlus":2},\
        {"date":"2026-05-20","score":89,"toPar":17,"birdies":1,"pars":9,"bogeys":6,"doublesPlus":2},\
        {"date":"2026-06-01","score":86,"toPar":14,"birdies":3,"pars":9,"bogeys":5,"doublesPlus":1}]},\
        "scoring":{"outcomes":{"eagleOrBetter":1,"birdie":40,"par":300,"bogey":250,"doubleOrWorse":120},\
        "outcomeDistribution":[{"key":"eagleOrBetter","label":"Eagle+","count":1,"pct":0.5},{"key":"birdie","label":"Birdie","count":40,"pct":6.5},{"key":"par","label":"Par","count":300,"pct":43.5},{"key":"bogey","label":"Bogey","count":250,"pct":35.2},{"key":"double","label":"Double","count":70,"pct":10.2},{"key":"triple","label":"Triple","count":20,"pct":2.8},{"key":"quadPlus","label":"+4 or worse","count":10,"pct":1.4}],\
        "scoreBands":[{"label":"80s","count":42},{"label":"90s","count":171},{"label":"100+","count":93}],\
        "byPar":[{"par":3,"averageToPar":0.62,"parOrBetterPct":38},{"par":4,"averageToPar":0.44,"parOrBetterPct":42},{"par":5,"averageToPar":0.21,"parOrBetterPct":55},{"par":6,"averageToPar":1.1,"parOrBetterPct":10}],\
        "phaseStats":[{"phase":"Tee","fairwaysRecorded":180,"fairwaysHit":102,"fairwayMissLeft":46,"fairwayMissRight":32},{"phase":"Approach","girRecorded":300,"gir":99,"girPct":33},{"phase":"Putting","averagePutts":1.9,"threePutts":40}],\
        "teeDirection":{"recorded":180,"hit":102,"left":46,"right":32,"hitPct":57,"dominantMiss":"left"},\
        "putting":{"averagePutts":1.9,"averagePuttsPerRound":32.5,"roundsWithPutts":120,"threePutts":240}},\
        "time":{"byQuarter":[{"key":"2026-Q2","roundCount":12,"average18":92.4,"bestScore":84,"outcomes":{"birdie":14,"doubleOrWorse":31}}]},\
        "courses":[{"courseKey":"bk","courseName":"北京天竺黑骑士","roundCount":128,"average18":91.0,"bestScore":82,"worstScore":99,\
        "rounds":[{"roundId":"r-901","date":"2026-06-11","score":89,"toPar":17,"holesCompleted":18,"nine":"北京天竺黑骑士 ~ C/A"},\
        {"roundId":"r-880","date":"2026-05-28","score":86,"toPar":14,"holesCompleted":18,"nine":"北京天竺黑骑士 ~ B/C"},\
        {"roundId":"r-855","date":"2026-05-12","score":94,"toPar":22,"holesCompleted":18,"nine":"北京天竺黑骑士 ~ A/B"}],\
        "nineBreakdown":[{"label":"北京天竺黑骑士 ~ C/A","roundCount":58,"average":89.0,"bestScore":82},{"label":"北京天竺黑骑士 ~ B/C","roundCount":40,"average":92.0,"bestScore":85},{"label":"北京天竺黑骑士 ~ A/B","roundCount":30,"average":93.0,"bestScore":88}]}],\
        "clubs":[{"club":"Driver","sampleCount":120,"median":210,"p10":195,"p90":225,"consistency":"high","distanceTrend":"stable"},\
        {"club":"7I","sampleCount":90,"median":138,"p10":130,"p90":146,"consistency":"high","distanceTrend":"up"}],\
        "diagnosis":{"topIssue":"double_or_worse","issueTrends":[{"issue":"tee_miss","direction":"worsening","estimatedStrokesLost":1.2},{"issue":"three_putt","direction":"improving","estimatedStrokesLost":-0.6}]}}
        """
        let mobileStats = try JSONDecoder().decode(MobileStats.self, from: Data(statsJSON.utf8))
        try captureScreen(
            NavigationStack {
                ScrollView {
                    StatsContent(stats: mobileStats, isLoading: false, errorText: nil)
                }
                .background(HubStyle.grouped)
                .navigationTitle("成绩统计")
            },
            named: "stats"
        )
        try captureScreen(
            NavigationStack {
                ScrollView {
                    ResultsLandingContent(stats: mobileStats, archive: nil, errorText: nil)
                }
                .background(HubStyle.grouped)
                .navigationTitle("成绩")
            },
            named: "results-landing"
        )
        try captureScreen(
            NavigationStack {
                ScrollView {
                    StatsContent(stats: mobileStats, isLoading: false, errorText: nil, mode: .analysis)
                }
                .background(HubStyle.grouped)
                .navigationTitle("表现分析")
            },
            named: "results-analysis"
        )
        // 球场钻取(round-10):各九洞组合 + 所有比赛(时间·成绩,点单场看复盘)。
        if let course = mobileStats.courses.first {
            try captureScreen(NavigationStack { CourseStatsDetailView(course: course) }, named: "course-detail")
        }

        // 球杆设置: defaults to the player's REAL Garmin bag (real names, incl 自定义 50/54/58 挖起杆)
        // resolved from /club/player + /club/types, with history distances (码).
        let bagProfiles = [
            ClubProfile(clubName: "Driver", sampleSize: 120, medianM: 210, p10M: 195, p90M: 225),
            ClubProfile(clubName: "5I", sampleSize: 60, medianM: 165, p10M: 158, p90M: 172),
            ClubProfile(clubName: "7I", sampleSize: 90, medianM: 140, p10M: 132, p90M: 148),
            ClubProfile(clubName: "PW", sampleSize: 70, medianM: 110, p10M: 102, p90M: 118),
        ]
        // The owner's actual 14-club bag resolved from Garmin (clubTypeId map + custom 50/54/58 wedges).
        let bag: Set<String> = [
            "一号木", "三号木", "三号小鸡腿", "五号铁", "六号铁", "七号铁", "八号铁", "九号铁",
            "P 杆", "A 杆", "50° 挖起杆", "54° 挖起杆", "58° 挖起杆", "推杆",
        ]
        try captureScreen(
            ClubSettingsContent(selected: bag, clubProfiles: bagProfiles, distancesYd: .constant(["七号铁": 140, "P 杆": 110])),
            named: "club-settings"
        )

        // 各杆距离阶梯图 (ClubGappingLadder): the whole bag ordered by distance (long→short) with a
        // proportional bar, so the gaps between clubs read at a glance; clubs without a recorded
        // distance still list (showing 留空, no bar). Same club + distance data the bag screen loads.
        // The bag screen is forced light (app root .preferredColorScheme(.light)), so it's captured
        // light. Rendered standalone as a pure VStack (ImageRenderer/window: no ScrollView needed).
        try captureScreen(
            VStack {
                ClubGappingLadder(entries: [
                    .init(name: "一号木", yards: 232),
                    .init(name: "三号木", yards: 214),
                    .init(name: "三号小鸡腿", yards: 203),
                    .init(name: "五号铁", yards: 181),
                    .init(name: "六号铁", yards: 170),
                    .init(name: "七号铁", yards: 158),
                    .init(name: "八号铁", yards: 146),
                    .init(name: "九号铁", yards: 133),
                    .init(name: "P 杆", yards: 118),
                    .init(name: "A 杆", yards: 104),
                    .init(name: "54° 挖起杆", yards: 88),
                    .init(name: "50° 挖起杆", yards: nil),
                    .init(name: "58° 挖起杆", yards: nil),
                    .init(name: "推杆", yards: nil),
                ])
                .padding(14)
                Spacer(minLength: 0)
            }
            .background(HubStyle.grouped),
            named: "club-ladder"
        )

        // 复盘逐洞落点图: this round's actual shots (tee→landing→green) on the hole, dots by lie.
        let shotMapJSON = """
        {"found":true,"hole":1,"par":4,\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":360,\
        "route":[[120,330,0],[118,180,180],[120,55,360]]}},\
        "shots":[\
        {"start":[120,330],"end":[122,200],"club":"Driver","lie":"TeeBox","endLie":"Fairway","shotType":"TEE","order":1,"synthetic":false},\
        {"start":[122,200],"end":[110,120],"club":"7I","lie":"Fairway","endLie":"Bunker","shotType":"APPROACH","order":2,"synthetic":false},\
        {"start":[110,120],"end":[119,60],"club":"SW","lie":"Bunker","endLie":"Green","shotType":"APPROACH","order":3,"synthetic":false}]}
        """
        let shotMap = try JSONDecoder().decode(RoundHoleShotMap.self, from: Data(shotMapJSON.utf8))
        try captureScreen(
            VStack(spacing: 12) { RoundShotMapView(shotMap: shotMap).frame(height: 420); RoundShotMapLegend() }
                .padding(24)
                .background(HubStyle.grouped),
            named: "round-shot-map"
        )

        // 复盘编辑态 (PR2): same shot map with the edit layer → a drag-handle ring on every landing +
        // the per-hole 罚杆 stepper. (Non-nil editModel = editing; the reorder List is empty in the
        // snapshot because ImageRenderer/window doesn't render List content — verified on device/XCUITest.)
        let editModel = RoundEditModel(map: shotMap, sync: SyncClient(baseURL: URL(string: "https://caddie.example")!), roundRef: "r1")
        editModel.enterEdit()
        try captureScreen(
            VStack(spacing: 12) {
                RoundShotMapView(shotMap: shotMap, editModel: editModel).frame(height: 420)
                PenaltyStepper(value: 1) { _ in }.hubCard()
            }
            .padding(24)
            .background(HubStyle.grouped),
            named: "review-edit-handles"
        )

        // 拖动放大镜 loupe (PR2, 设计 §5): the circular magnifier that floats above the finger while
        // dragging a landing — same base map + shots, magnified around the focus point, with a crosshair.
        try captureScreen(
            VStack {
                Text("拖动放大镜").font(.caption).foregroundStyle(.secondary)
                MagnifierLoupe(
                    overlay: shotMap.map!.overlay, shots: shotMap.shots, baseImage: holeImage, topoURL: nil,
                    mapSize: CGSize(width: CGFloat(mapW), height: CGFloat(mapH)),
                    focus: CGPoint(x: 110, y: 120), diameter: 150, magnification: 2.4
                )
            }
            .padding(40)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(HubStyle.grouped),
            named: "review-edit-magnifier"
        )
    }

    @MainActor
    private func captureScreen(_ view: some View, named name: String, dark: Bool = false) throws {
        let size = CGSize(width: 390, height: 844)
        let style: UIUserInterfaceStyle = dark ? .dark : .light
        let host = UIHostingController(rootView: view)
        host.overrideUserInterfaceStyle = style
        host.view.frame = CGRect(origin: .zero, size: size)
        let window = UIWindow(frame: host.view.frame)
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.makeKeyAndVisible()
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        // Pump the runloop so SwiftUI commits its first render, then capture the layer tree
        // (synchronous; works headless, unlike drawHierarchy(afterScreenUpdates:) which needs
        // a live display and renders blank in CI).
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 1.0))
        host.view.layoutIfNeeded()
        let renderer = UIGraphicsImageRenderer(size: size)
        let image = renderer.image { ctx in
            window.layer.render(in: ctx.cgContext)
        }
        guard let data = image.pngData() else {
            XCTFail("no png for \(name)")
            return
        }
        let dir = try FileManager.default
            .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("design-snapshots", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try data.write(to: dir.appendingPathComponent("\(name).png"))
        print("WROTE_SCREEN \(name)")
    }

    @MainActor
    private func render(_ view: some View, named name: String) throws {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        guard let image = renderer.uiImage, let data = image.pngData() else {
            XCTFail("ImageRenderer produced no image for \(name)")
            return
        }
        let dir = try FileManager.default
            .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("design-snapshots", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try data.write(to: dir.appendingPathComponent("\(name).png"))

        let attachment = XCTAttachment(image: image)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_SNAPSHOT \(name)")
    }
}
