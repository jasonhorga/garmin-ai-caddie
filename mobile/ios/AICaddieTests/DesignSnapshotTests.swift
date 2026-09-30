import SwiftUI
import UIKit
import AICaddieDomain
import CoreLocation
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
            LivePlayFlagMarker().offset(x: 30, y: 96)
            LiveMapGreenDistanceOverlay(
                frontYards: 205, middleYards: 219, backYards: 231,
                toPinYards: 245, isLive: false
            )
            .position(x: 104, y: 137)
            LiveMapHazardRangeOverlay(
                kind: "water",
                label: "右侧水障碍",
                toYards: 213,
                overYards: 235,
                front: CGPoint(x: 224, y: 292),
                back: CGPoint(x: 250, y: 266),
                index: 0,
                viewportSize: CGSize(width: 390, height: 480)
            )
            VStack(spacing: 0) {
                LivePlayHeader(holeNumber: 1, par: 5, yards: 543, teeLabel: "蓝T", roundToParText: "本场 +4")
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
                Spacer(minLength: 0)
                LivePlayPanel {
                    LiveCaddieStrip(
                        clubs: [
                            .init(name: "3W", sub: "238 码", on: true),
                            .init(name: "5W", sub: "215 码", on: false),
                            .init(name: "4i", sub: "198 码", on: false),
                        ],
                        playsText: "实打约 +8 码(上坡)· 打球道左中,避右侧水"
                    )
                    LiveHoleActionDock(canRecordShot: true, recordedShotCount: 1)
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

    func testHeroMapTapConvertsInteractionLaneToFullHeroCoordinates() {
        XCTAssertEqual(
            LivePlayMapOverlayLayout.heroCoordinate(
                fromInteractionLocation: CGPoint(x: 196, y: 124)
            ),
            CGPoint(x: 196, y: 204)
        )
        XCTAssertEqual(
            LivePlayMapOverlayLayout.heroCoordinate(
                fromInteractionLocation: CGPoint(x: 196, y: 124),
                topInset: 0
            ),
            CGPoint(x: 196, y: 124)
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
            Text("球杆 · 打法 · 球位 · 距离 · 罚杆 · 备注")
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
        // README §8 home main card, all three states: in progress, a known course, no course.
        let deltas: [Int] = [0, 1, 0, -1, 1, 0, 1, 2, 0, 0, 1, 0, -1, 1, 0, 1, 0, 3]
        let strip: [HistoryScoreCell] = deltas.enumerated().map { index, delta in
            HistoryScoreCell(hole: index + 1, par: 4, score: 4 + delta, toPar: delta, className: nil)
        }
        let view = VStack(spacing: 14) {
            HubInProgressCard(courseName: "北京丽宫", activeHole: 7, recorded: 6, toPar: 2)
            HubSuggestedCourseCard(courseName: "北京天竺黑骑士球员俱乐部", startTitle: "从 B 场 开始 · 蓝 T") {
                HubPrimaryPill(title: "开始")
                HubSecondaryLinkLabel(title: "换球场或组合")
            }
            HubSearchHeroCard()
            HubReplayLastCard(courseName: "北京天竺黑骑士球员俱乐部", startTitle: "从 B 场 开始 · 蓝 T")
            HStack(spacing: 11) {
                HubTile(icon: "scope", title: "备战", subtitle: "搜索 · 球童试算")
                HubTile(icon: "chart.line.uptrend.xyaxis", title: "成绩", subtitle: "球局 · 统计")
            }
            VStack(alignment: .leading, spacing: 9) {
                HubSectionLabel("上一场")
                HubLastRoundCard(courseName: "Cypress Point Club", date: "2026-07-30", score: 82, toPar: 10,
                                 holesCompleted: 18, par: 72,
                                 topoURL: SyncClient.topoImageURL(
                                     baseURL: URL(string: "https://caddie.example")!, globalId: 3881, localHole: 1),
                                 scoreStrip: strip)
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
        // The selected chain is primary; only physically different club sequences appear below it.
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
            selectedSequenceId: "stock"
        )
        .padding(14)
        .frame(width: 390)
        .background(Color.white)
        try render(view, named: "caddie-plan")
    }

    /// B2 记分三屏 (`score.html`): the one-screen hole score, the scorecard mid-round and the round
    /// summary, from a fixed 18-hole fixture (Par 72, the prototype's example scores).
    @MainActor
    func testCaptureScoringScreens() throws {
        let pars = [5, 4, 3, 4, 4, 5, 3, 4, 4, 4, 4, 3, 5, 4, 4, 3, 5, 4]
        let toPar = [0, 1, 0, -1, 1, 0, 1, 2, 0, 0, 1, 0, -1, 1, 0, 1, 0, 0]
        let putts = [2, 2, 1, 1, 2, 2, 2, 2, 2, 2, 2, 1, 1, 2, 2, 2, 2, 2]
        let fairways: [String?] = ["hit", "left", nil, "hit", "hit", "left", nil, "left", "hit",
                                   "hit", "hit", nil, "hit", "left", "hit", nil, "left", "hit"]
        let holes = pars.enumerated().map { index, par in
            // 黑骑士 B (31795) then C (31796): two nine-hole loops, shown by round number.
            Hole(
                number: index + 1,
                par: par,
                yards: nil,
                geometryCoverage: .ready,
                sourceGlobalId: index < 9 ? 31795 : 31796,
                sourceLocalHole: index % 9 + 1,
                courseHoleNumber: index + 1
            )
        }
        func state(recorded: Int) -> LiveRoundStateSnapshot {
            LiveRoundStateSnapshot(
                roundId: "snapshot-round",
                activeHole: min(recorded + 1, 18),
                holes: holes.map { hole in
                    let index = hole.number - 1
                    var snapshot = LiveHoleStateSnapshot(
                        roundId: "snapshot-round", hole: hole.number, par: hole.par,
                        score: hole.par + toPar[index], putts: putts[index], penaltyCount: index == 7 ? 1 : 0,
                        fairwayResult: fairways[index], selectedClub: "", selectedShotType: "tee",
                        selectedStrategyMode: "stock", distanceToPinM: nil, lie: "fairway",
                        latitude: nil, longitude: nil, horizontalAccuracyM: nil,
                        targetLatitude: nil, targetLongitude: nil, targetKind: nil, updatedAt: nil
                    )
                    snapshot.scoreSource = "manual_edit"
                    return snapshot
                },
                scoredHoles: Array(1...recorded)
            )
        }

        // 1. 本洞记分: nothing recorded (default par), the tee result preselected from the fairway check.
        try captureScreen(
            LiveScoreConfirmationView(
                draft: .constant(LiveScoreDraft(hole: 1, par: 5, phoneShotCount: 0, teeResult: .right)),
                nextHole: 2,
                onAccept: { _ in },
                onCancel: {}
            ),
            named: "score-hole",
            dark: true
        )
        // The phone recorded one shot (1 + 2 putts); Par 3 hides the tee tiles.
        try captureScreen(
            LiveScoreConfirmationView(
                draft: .constant(LiveScoreDraft(hole: 3, par: 3, phoneShotCount: 1)),
                nextHole: 4,
                onAccept: { _ in },
                onCancel: {}
            ),
            named: "score-hole-par3",
            dark: true
        )
        // 4+ putts: five putts keep their real count beside the 4+ segment; the total follows
        // putts + penalty + 1.
        var fourPlus = LiveScoreDraft(hole: 6, par: 4, phoneShotCount: 2, teeResult: .hit)
        fourPlus.selectPutts(5)
        fourPlus.adjustPenalty(by: 1)
        XCTAssertEqual(fourPlus.score, 7)
        try captureScreen(
            LiveScoreConfirmationView(
                draft: .constant(fourPlus),
                nextHole: 7,
                onAccept: { _ in },
                onCancel: {}
            ),
            named: "score-hole-4plus",
            dark: true
        )

        // 2. 计分卡 after nine holes, the tenth being played.
        let midRound = state(recorded: 9)
        try captureScreen(
            LiveRoundScorecardView(
                courseName: "黑骑士球员俱乐部 B/C",
                holes: holes,
                liveRoundState: midRound,
                recordedScoreHoles: Set(1...9),
                onEdit: { _ in },
                onFinishRound: {},
                onLeaveToHome: {}
            ),
            named: "score-scorecard",
            dark: true
        )

        // 3. 本场汇总 after 18 holes.
        let finished = state(recorded: 18)
        let scores = Dictionary(uniqueKeysWithValues: holes.compactMap { hole -> (Int, LiveHoleScore)? in
            guard let state = finished.holeState(for: hole.number) else { return nil }
            return (hole.number, LiveHoleScore(
                hole: hole.number, par: hole.par, score: state.score, putts: state.putts,
                penalties: state.penaltyCount, fairway: state.fairwayResult, source: state.scoreSource
            ))
        })
        try captureScreen(
            LiveRoundFinishSummaryView(
                courseName: "黑骑士球员俱乐部 B/C",
                holes: holes,
                scores: scores,
                isFinishingRound: false,
                finishErrorMessage: nil,
                onFinish: {},
                onContinue: {},
                onDiscard: {}
            ),
            named: "score-summary",
            dark: true
        )
        // 本场汇总 after only the front nine of an 18-hole package: Par of the nine played.
        let frontNine = scores.filter { $0.key <= 9 }
        let nineSummary = LiveRoundScoreSummary(holes: holes.compactMap { frontNine[$0.number] })
        XCTAssertEqual(
            LiveRoundFinishSummaryView.parLine(summary: nineSummary, holes: holes),
            "Par \(holes.prefix(9).reduce(0) { $0 + $1.par }) · 9/18 洞"
        )
        try captureScreen(
            LiveRoundFinishSummaryView(
                courseName: "黑骑士球员俱乐部 B/C",
                holes: holes,
                scores: frontNine,
                isFinishingRound: false,
                finishErrorMessage: nil,
                onFinish: {},
                onContinue: {},
                onDiscard: {}
            ),
            named: "score-summary-nine",
            dark: true
        )

        // B4 turn: "B 场打完了 — 接着打哪个 9 洞", the usual pairing preselected.
        // The labels are typed `String`: an untyped literal here is inferred as `[String?]` from the
        // optional `segmentLabel` parameter, and the interpolated name then reads `Optional("B")`.
        let turnLabels: [String] = ["A", "B", "C"]
        let turnLoops = turnLabels.enumerated().map { index, label in
            MobileCourseOption(globalId: 100 + index, name: "黑骑士 ~ \(label)", holes: 9, venueName: "黑骑士", segmentLabel: label, segmentHoles: 9)
        }
        let turn = try XCTUnwrap(NineLoopTurn.plan(front: turnLoops[1], siblings: turnLoops, remembered: ["101:all": "102:all"], history: []))
        XCTAssertEqual(turn.turnTitle, "B 场打完了")
        XCTAssertEqual(turn.course.loops.map(\.displayName), ["A 场", "B 场", "C 场"])
        XCTAssertEqual(turn.turnActionTitle, "接着打 C 场")
        for text in [turn.turnTitle, turn.turnActionTitle] + turn.course.loops.map(\.displayName) {
            XCTAssertFalse(text.contains("Optional("), text)
        }
        try captureScreen(
            LiveRoundTurnSheet(plan: turn, isPreparing: false, onContinue: { _ in }, onStop: {}, onLater: {}),
            named: "turn-sheet",
            dark: true
        )
        // While the chosen loop is being added: spinner on the CTA, every control disabled.
        try captureScreen(
            LiveRoundTurnSheet(plan: turn, isPreparing: true, onContinue: { _ in }, onStop: {}, onLater: {}),
            named: "turn-sheet-preparing",
            dark: true
        )
    }

    /// B1 旗位界面: no green outline, four edge guides with yardage capsules, the four-cell card and
    /// the flag-position line. Synthetic 240 x 360 hole at 1 px = 1 m, flag behind-right of centre.
    @MainActor
    func testCaptureGreenFlagScreen() throws {
        let mapW = 240, mapH = 360
        let holeImage = UIGraphicsImageRenderer(size: CGSize(width: mapW, height: mapH)).image { ctx in
            UIColor(red: 0.46, green: 0.66, blue: 0.40, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: mapW, height: mapH))
            UIColor(red: 0.50, green: 0.80, blue: 0.43, alpha: 1).setFill()
            ctx.cgContext.fillEllipse(in: CGRect(x: 96, y: 28, width: 48, height: 42))
        }
        let b64 = "data:image/jpeg;base64," + (holeImage.jpegData(compressionQuality: 0.85)?.base64EncodedString() ?? "")
        let outline = (0..<24).map { index -> String in
            let angle = Double(index) / 24 * 2 * Double.pi
            return String(format: "[%.1f,%.1f]", 120 + 24 * cos(angle), 49 + 21 * sin(angle))
        }.joined(separator: ",")
        let prepJSON = """
        {"hole":7,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,\
        "route":[[120,330],[118,180],[120,49]],"steps":[],"cautions":[],\
        "hazards":{"water_carry":[],"bunkers":[]},"landing_m":150,"tee_club":"D",\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":375,\
        "route":[[120,330,0],[118,180,150],[120,49,375]]}},\
        "holeImageProjection":{"available":true,"widthPx":\(mapW),"heightPx":\(mapH)},\
        "greenOutline":{"available":true,"source":"fixture","pointsPx":[\(outline)]}}
        """
        let hole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(prepJSON.utf8))
        try captureScreen(
            LiveGreenDetailView(
                hole: hole,
                detailURL: nil,
                topoURL: nil,
                targetCoordinate: .constant(nil),
                targetPixel: .constant(CGPoint(x: 128, y: 42)),
                referenceCoordinate: nil,
                referenceIsLive: false,
                pinCoordinate: nil
            ),
            named: "full-green-flag",
            dark: true
        )
        // B1 旗位缩放: the same flag editor opened at 2.5x (edge lines and numbers stay screen size).
        try captureScreen(
            LiveGreenDetailView(
                hole: hole,
                detailURL: nil,
                topoURL: nil,
                targetCoordinate: .constant(nil),
                targetPixel: .constant(CGPoint(x: 128, y: 42)),
                referenceCoordinate: nil,
                referenceIsLive: false,
                pinCoordinate: nil,
                initialScale: 2.5
            ),
            named: "full-green-flag-zoomed",
            dark: true
        )
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
        // No course here and no last course → "今天去哪打？" + search (the package course is not 上次).
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses), named: "full-home")
        let recentBlackKnightB = MobileCourseOption(globalId: 31795, name: "北京天竺黑骑士球员俱乐部 ~ B", holes: 9, teeBox: "blue", venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "B", segmentHoles: 9, tees: ["blue"])
        // README §8 "在球场附近": an authorised fix at 黑骑士 and the provider-nearby A/B/C loops,
        // resolved through the production fix → onNearbyCourses → current venue path → the
        // course card with its loop/Tee, 开始 and 换球场或组合.
        let atBlackKnight = LocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.1203, longitude: 116.5791),
            horizontalAccuracyM: 5,
            altitudeM: nil,
            capturedAt: "2026-09-29T08:00:00Z"
        )
        // Typed: an untyped literal here infers as [String?] (segmentLabel is optional) and the
        // name interpolates as "~ Optional(\"B\")".
        let loopLabels: [String] = ["A", "B", "C"]
        let nearbyBlackKnight = loopLabels.enumerated().map { index, label in
            MobileCourseSearchMatch(
                globalId: 31794 + index,
                name: "北京天竺黑骑士球员俱乐部 ~ \(label)",
                holes: 9,
                city: "北京",
                province: nil,
                ratio: 1,
                latitude: 40.1203 + Double(index) * 0.001,
                longitude: 116.5791,
                distanceKm: 0.1,
                venueName: "北京天竺黑骑士球员俱乐部",
                segmentLabel: label
            )
        }
        // The first render is seeded with the rows `HubNearby.options` builds from those matches
        // (the same mapping refreshHeroNearby applies), so the capture never races the task.
        let nearbyRows = HubNearby.options(from: nearbyBlackKnight, catalogue: courses, downloaded: [])
        let nearState = HubHeroState.resolve(
            hasActiveRound: false,
            hasPendingWatchRound: false,
            fix: (latitude: atBlackKnight.coordinate.latitude, longitude: atBlackKnight.coordinate.longitude),
            nearbyOptions: nearbyRows,
            history: [],
            recent: recentBlackKnightB,
            catalogue: courses,
            downloaded: []
        )
        guard case .nearby(let here) = nearState else {
            return XCTFail("full-home-near inputs must resolve to the course-here card, got \(nearState)")
        }
        XCTAssertEqual(here.courseName, "北京天竺黑骑士球员俱乐部")
        XCTAssertEqual(here.startTitle, "从 B 场 开始 · 蓝 T")
        let nearPNG = try captureScreen(
            RoundHomeView(
                package: package,
                apiBaseURL: apiBaseURL,
                courseOptions: courses,
                recentCourseOption: recentBlackKnightB,
                onNearbyCourses: { _, _, _ in nearbyBlackKnight },
                heroLocationProvider: LocationProvider(fixedFix: atBlackKnight),
                initialHeroNearbyOptions: nearbyRows
            ),
            named: "full-home-near"
        )
        // Not at a course: "今天去哪打？" + search, and the last course as a separate 再打上次那个.
        let replayPNG = try captureScreen(
            RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses, recentCourseOption: recentBlackKnightB),
            named: "full-home-replay"
        )
        XCTAssertNotEqual(nearPNG, replayPNG, "the course-here card and the search + replay state are different screens")
        // No known course → "今天去哪打？" + search.
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL), named: "full-home-search")
        // Hub WITH an in-progress round → shows the 进行中 card + 「结束本场」(cancel) button.
        let activeState = LiveRoundStateSnapshot(roundId: package.roundId, activeHole: package.holes.first?.number ?? 1, holes: [])
        try captureScreen(
            RoundHomeView(package: package, apiBaseURL: apiBaseURL, liveRoundState: activeState, courseOptions: courses),
            named: "full-home-active"
        )
        try captureScreen(NavigationStack { StartRoundView(courseOptions: courses) }, named: "full-start")
        // 开始一场 with 黑骑士 B preselected (the home "开始"): one list row, A/B/C tiles, tee dots,
        // "从 B 场 开始 · 蓝 T".
        // 换球场或组合 from the 黑骑士 card: B preselected, the row carries all three loops (27 洞),
        // and each tee shows this 9-hole loop's own yards. Tee rows: the yards / holeCount of
        // production GET /api/v2/courses/31795/tees?ensure_release=false (loop B, 2026-09-29).
        let loopBTeesJSON = #"""
        [
          {"teeBox": "gold", "name": "Gold", "yards": 3585, "holeCount": 9, "default": false},
          {"teeBox": "blue", "name": "Blue", "yards": 3393, "holeCount": 9, "default": true},
          {"teeBox": "white", "name": "White", "yards": 3019, "holeCount": 9, "default": false},
          {"teeBox": "red", "name": "Red", "yards": 2533, "holeCount": 9, "default": false}
        ]
        """#
        let loopBTees = try JSONDecoder().decode([CourseTee].self, from: Data(loopBTeesJSON.utf8))
        // The chips show exactly these loop yards (a 9-hole total over the 9 holes started).
        XCTAssertEqual(
            loopBTees.map {
                StartRoundPresentation.teeYards(total: $0.yards, teeHoleCount: $0.holeCount, playedHoles: 9)
            },
            [3585, 3393, 3019, 2533]
        )
        try captureScreen(
            NavigationStack {
                StartRoundView(
                    defaultCourseGlobalId: 31795,
                    defaultTeeBox: "blue",
                    initialCourseTees: loopBTees,
                    courseOptions: courses,
                    onLoadCourseTees: { _ in loopBTees }
                )
            },
            named: "full-start-selected"
        )
        try captureScreen(NavigationStack { PrepCoursePickerView(courseOptions: courses, apiBaseURL: apiBaseURL, adminToken: nil) }, named: "full-prep-picker")
        // 开始一场's catalogue sheet: no positioning / download status copy (README §8).
        try captureScreen(
            NavigationStack {
                MobileCourseSearchView(
                    locationProvider: LocationProvider(),
                    presentation: .startRound,
                    onSearch: { _, _ in [] },
                    onNearby: { _, _, _ in [] },
                    onSelect: { _, _ in }
                )
            },
            named: "full-course-search"
        )
        // 备战's catalogue sheet keeps its positioning progress and download state.
        try captureScreen(
            NavigationStack {
                MobileCourseSearchView(
                    locationProvider: LocationProvider(),
                    presentation: .prep,
                    onSearch: { _, _ in [] },
                    onNearby: { _, _, _ in [] },
                    onSelect: { _, _ in }
                )
            },
            named: "full-prep-course-search"
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

        // B1 live main screen: the same synthetic map attached to the fixture's first hole, so the
        // full-screen map, the corner controls, the top-right ladder and the labelled caddie route
        // ("杆名 码数" at every landing) are reviewable together. Each state is injected up front
        // so the captures are deterministic: default (no obstacle), one obstacle selected, the
        // second of two plans, and a zoomed map with 回到.
        if let firstHole = package.holes.first {
            let livePrepJSON = """
            {"hole":\(firstHole.number),"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,\
            "route":[[120,330],[118,180],[120,55]],"steps":[{"club":"D","note":"开球"}],"cautions":[],\
            "hazards":{"water_carry":[],"bunkers":[],"details":[\
            {"kind":"water","frontM":175,"backM":195,"frontRouteM":175,"backRouteM":195,"frontPx":[112,175],"backPx":[110,155],\
            "outlinePx":[[96,178],[124,176],[128,160],[112,150],[94,158]],"sideM":null},\
            {"kind":"bunker","frontM":330,"backM":342,"frontRouteM":330,"backRouteM":342,"frontPx":[150,92],"backPx":[152,80],\
            "outlinePx":[[144,94],[158,92],[160,80],[146,78]],"sideM":18}]},\
            "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":375,\
            "route":[[120,330,0],[118,180,150],[120,55,375]]}},\
            "greenDistances":{"available":true,"frontM":360,"middleM":375,"backM":390}}
            """
            let livePrepHole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(livePrepJSON.utf8))
            let mappedPackage = package.replacingCoursePrep(
                CoursePrepPackage(
                    schema: "ai-caddie-course-prep-v1",
                    globalId: package.course.globalId,
                    holes: [livePrepHole],
                    missingData: nil
                )
            )
            let routes = Self.snapshotCaddieRoutes(par: firstHole.par, routeLengthM: 375)
            let states: [(String, CurrentHoleView.SnapshotState)] = [
                ("full-hole-map", .init(caddieRoutes: routes)),
                ("full-hole-map-hazard", .init(selectsFirstHazard: true, caddieRoutes: routes)),
                ("full-hole-map-plan-2", .init(caddieRoutes: routes, selectedRouteIndex: 1)),
                ("full-hole-map-zoomed", .init(caddieRoutes: routes, mapScale: 2)),
                // B1c: a Touch Target placed on the main map, and the same target being dragged
                // (the finger at its on-screen position) with the loupe up.
                ("full-hole-map-target", .init(caddieRoutes: routes, targetPixel: CGPoint(x: 150, y: 210))),
                ("full-hole-map-target-drag", .init(
                    caddieRoutes: routes,
                    targetPixel: CGPoint(x: 150, y: 210),
                    targetDragFocus: CGPoint(x: 243.75, y: 510.75)
                )),
            ]
            for (name, state) in states {
                try captureScreen(
                    NavigationStack { CurrentHoleView(package: mappedPackage, hole: firstHole, snapshotState: state) },
                    named: name,
                    dark: true
                )
            }
            // README 地图降级契约: without the precise topo the live hole draws the factual route and
            // the geometry it already has (green outline, obstacle facts), immediately.
            let greenOutlineJSON = (0..<24).map { index -> String in
                let angle = Double(index) / 24 * 2 * Double.pi
                return String(format: "[%.1f,%.1f]", 120 + 22 * cos(angle), 52 + 18 * sin(angle))
            }.joined(separator: ",")
            let partialPrepJSON = livePrepJSON.replacingOccurrences(
                of: "\"map\":{\"image\":\"\(b64)\",",
                with: "\"geometryCoverage\":\"partial\","
                    + "\"greenOutline\":{\"available\":true,\"source\":\"fixture\",\"pointsPx\":[\(greenOutlineJSON)]},"
                    + "\"map\":{"
            )
            XCTAssertNotEqual(partialPrepJSON, livePrepJSON, "fixture: the topo image must be removed")
            let partialPrep = try JSONDecoder().decode(CoursePrepHole.self, from: Data(partialPrepJSON.utf8))
            XCTAssertEqual(partialPrep.geometryCoverage, "partial")
            XCTAssertEqual(partialPrep.greenOutline?.available, true)
            XCTAssertFalse(LiveHazardDisplayItem.rows(for: partialPrep, liveReadouts: nil).isEmpty)
            let partialPackage = package.replacingCoursePrep(CoursePrepPackage(
                schema: "ai-caddie-course-prep-v1",
                globalId: package.course.globalId,
                holes: [partialPrep],
                missingData: nil
            ))
            // Pending: the precise topo is still expected online (a service URL, nothing cached).
            // Factual route + green outline + the obstacle facts it already has draw at once; one
            // obstacle is selected through the 障碍 control, with its 前 / 后 labels. The unreachable
            // host keeps it pending.
            XCTAssertEqual(
                LiveMapDisplayState.resolve(
                    prep: partialPrep,
                    pending: LiveMapDisplayState.isPrecisePending(
                        geometryCoverage: partialPrep.geometryCoverage,
                        timedOut: false,
                        hasBaseURL: true,
                        hasCachedTopo: false
                    )
                ),
                .factualPending
            )
            try captureScreen(
                NavigationStack {
                    CurrentHoleView(
                        package: partialPackage,
                        hole: firstHole,
                        snapshotState: .init(selectsFirstHazard: true, caddieRoutes: routes),
                        caddieBaseURL: URL(string: "http://127.0.0.1:9")
                    )
                },
                named: "full-hole-map-partial-pending",
                dark: true
            )
            // Pending without a selection: the 障碍 control is offered for the existing facts.
            try captureScreen(
                NavigationStack {
                    CurrentHoleView(
                        package: partialPackage,
                        hole: firstHole,
                        snapshotState: .init(caddieRoutes: routes),
                        caddieBaseURL: URL(string: "http://127.0.0.1:9")
                    )
                },
                named: "full-hole-map-partial-pending-default",
                dark: true
            )
            // Partial facts with nothing better coming (offline / no service): the same map, and the
            // obstacle facts it has are browsable (one selected here).
            try captureScreen(
                NavigationStack {
                    CurrentHoleView(
                        package: partialPackage,
                        hole: firstHole,
                        snapshotState: .init(selectsFirstHazard: true, caddieRoutes: routes)
                    )
                },
                named: "full-hole-map-partial",
                dark: true
            )
            // ... and with no drawable route at all it shows the one full-screen waiting page
            // (hole · Par · yards), never an empty hole.
            let noMapPrepJSON = """
            {"hole":\(firstHole.number),"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,\
            "route":[],"steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]}}
            """
            let noMapPrep = try JSONDecoder().decode(CoursePrepHole.self, from: Data(noMapPrepJSON.utf8))
            XCTAssertNil(noMapPrep.resolvedMapOverlay)
            try captureScreen(
                NavigationStack {
                    CurrentHoleView(
                        package: package.replacingCoursePrep(CoursePrepPackage(
                            schema: "ai-caddie-course-prep-v1",
                            globalId: package.course.globalId,
                            holes: [noMapPrep],
                            missingData: nil
                        )),
                        hole: firstHole
                    )
                },
                named: "full-hole-map-waiting",
                dark: true
            )

            // Each injected state must actually render: identical PNGs mean the state was dropped.
            let snapshotDir = try FileManager.default
                .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
                .appendingPathComponent("design-snapshots", isDirectory: true)
            let rendered = try states.map { try Data(contentsOf: snapshotDir.appendingPathComponent("\($0.0).png")) }
            XCTAssertEqual(Set(rendered).count, states.count, "live-map snapshot states rendered identically")
        }

        // No-network topo fallback: pass a topoURL (as production does for a real course) but CI has
        // NO network, so the AsyncImage never resolves → the base layer must degrade to the flat
        // render + overlay, never a broken/empty box. Unreachable host guarantees no load.
        let unreachableTopo = URL(string: "http://127.0.0.1:9/api/v2/courses/1/holes/7/topo.png")
        try captureScreen(
            VStack { HoleImageMapView(hole: prepHole, topoURL: unreachableTopo).frame(height: 460) }.padding(24),
            named: "hole-map-topo-fallback"
        )

        // B4c 备战 (README §8, pre-round.html 第三台): the full-screen map with the caddie route and
        // landings, the plan and this hole's club order, the 18-hole strip and the Tee top right.
        // Every hole follows the map degradation contract: holes 1-4 have their precise topo, holes
        // 5-12 only the factual route (+ green outline + obstacle spans) while the precise map is on
        // its way, and holes 13-18 nothing drawable yet (the one waiting page). Not-ready holes are
        // faded in the strip.
        let prepCardJSON = """
        {"hole":7,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,\
        "geometryCoverage":"ready","geometryRevision":"snapshot-r1",\
        "route":[[120,330],[118,180],[120,55]],"tee_club":"D","landing_m":150,\
        "steps":[{"club":"D","note":"开球打球道左中,避右侧沙坑","targetCarry_m":205,"routeOffset_m":205,"role":"tee"},\
        {"club":"8I","note":"攻果岭中心,后方无碍","targetCarry_m":150,"routeOffset_m":375,"role":"approach"}],\
        "cautions":["果岭前缘有陡坡,落点宁长勿短"],\
        "hazards":{"water_carry":[[175,195]],"bunkers":[[210,18],[138,12]],"details":[\
        {"kind":"water","frontM":175,"backM":195,"frontRouteM":175,"backRouteM":195,"frontPx":[112,170],"backPx":[126,155],"sideM":null},\
        {"kind":"bunker","frontM":210,"backM":225,"frontRouteM":210,"backRouteM":225,"frontPx":[145,130],"backPx":[152,116],"sideM":18}]},\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":375,\
        "route":[[120,330,0],[118,180,150],[120,55,375]]}},\
        "greenDistances":{"available":true,"frontM":128,"middleM":135,"backM":142},\
        "playsLike":{"available":true,"deltaM":7.3,"deltaYd":8}}
        """
        let prepCardHole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(prepCardJSON.utf8))
        let prepGreenOutline = (0..<24).map { index -> String in
            let angle = Double(index) / 24 * 2 * Double.pi
            return String(format: "[%.1f,%.1f]", 120 + 22 * cos(angle), 52 + 18 * sin(angle))
        }.joined(separator: ",")
        let factualPrepJSON = prepCardJSON
            .replacingOccurrences(of: "\"geometryCoverage\":\"ready\"", with: "\"geometryCoverage\":\"partial\"")
            .replacingOccurrences(
                of: "\"map\":{\"image\":\"\(b64)\",",
                with: "\"greenOutline\":{\"available\":true,\"source\":\"fixture\",\"pointsPx\":[\(prepGreenOutline)]},\"map\":{"
            )
        XCTAssertNotEqual(factualPrepJSON, prepCardJSON, "fixture: the factual row has no raster")
        let factualPrepHole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(factualPrepJSON.utf8))
        XCTAssertEqual(factualPrepHole.geometryCoverage, "partial")
        XCTAssertNil(factualPrepHole.map?.image)
        // The installed topo is a local file, as the download writes it.
        let prepTopoURL = FileManager.default.temporaryDirectory.appendingPathComponent("prep-snapshot-topo.png")
        try XCTUnwrap(holeImage.pngData()).write(to: prepTopoURL, options: [.atomic])
        let prepPars = [5, 4, 3, 4, 4, 5, 3, 4, 4, 4, 4, 3, 5, 4, 4, 3, 5, 4]
        let prepYards = [543, 410, 178, 395, 402, 528, 165, 388, 420, 415, 398, 172, 535, 405, 390, 188, 520, 430]
        let prepRows: [PrepHoleRow] = (1...18).map { number -> PrepHoleRow in
            let state: LiveMapDisplayState = number <= 4 ? .precise : (number <= 12 ? .factualPending : .waiting)
            let prep: CoursePrepHole? = state == .waiting
                ? nil
                : (state == .precise ? prepCardHole : factualPrepHole).renumbered(to: number)
            // The three real strategy routes (推荐 / 稳妥 / 进攻), each with its own carries and
            // landings, through the production route -> plan mapping.
            let plans: [PrepPlanOption] = state == .waiting
                ? []
                : PrepRouteFixtures.routes(par: prepPars[number - 1], routeLengthM: 375)
                    .enumerated()
                    .compactMap { index, route in
                        PrepPlanOption.option(route: route, index: index, par: prepPars[number - 1])
                    }
            return PrepHoleRow(
                number: number,
                displayNumber: number,
                par: prepPars[number - 1],
                yards: prepYards[number - 1],
                prep: prep,
                topoURL: state == .precise ? prepTopoURL : nil,
                state: state,
                plans: plans
            )
        }
        XCTAssertEqual(prepRows[0].plans.map(\.title), ["推荐", "稳妥", "进攻"])
        // Every stroke of the Par 5 plan is in the club order: tee shot, second shot, approach.
        XCTAssertEqual(prepRows[0].plans[0].steps.count, 3)
        XCTAssertNotEqual(
            prepRows[0].plans[0].steps.map(\.label),
            prepRows[0].plans[1].steps.map(\.label)
        )
        // 方案 2 is a visibly different path: its landings are elsewhere on the hole.
        if let firstPrep = prepRows[0].prep {
            let paths = prepRows[0].plans.prefix(2).map { plan in
                HoleImageMapView(
                    hole: firstPrep,
                    showsCardChrome: false,
                    plannedShots: plan.shots,
                    drawsPlannedRouteInMap: false
                ).plannedLegs().map(\.destination)
            }
            XCTAssertEqual(paths.count, 2)
            for (lhs, rhs) in zip(paths[0].dropLast(), paths[1].dropLast()) {
                XCTAssertGreaterThan(
                    hypot(lhs.x - rhs.x, lhs.y - rhs.y),
                    30,
                    "each landing of plan 2 is at least 30 topo px from plan 1's"
                )
            }
        }
        // Default-none obstacles: the prep map requests neither obstacle spans nor measured labels,
        // and each landing reads 球杆 + 码数.
        if let firstPrep = prepRows[0].prep, let overlay = firstPrep.resolvedMapOverlay {
            let legs = HoleImageMapView(
                hole: firstPrep,
                showsCardChrome: false,
                plannedShots: prepRows[0].plans[0].shots,
                drawsPlannedRouteInMap: false
            ).plannedLegs()
            XCTAssertEqual(
                PrepHoleMapHero.landingLabels(legs: legs, overlay: overlay),
                prepRows[0].plans[0].steps.map(\.label)
            )
            XCTAssertEqual(PrepHoleMapHero.landingLabels(legs: legs, overlay: overlay).count, 3)
        } else {
            XCTFail("fixture: the precise prep row has a map")
        }
        func prepSession(
            hole: Int,
            plan: Int = 0,
            viewport: HoleMapViewportState = HoleMapViewportState()
        ) -> PrepHoleMapSession {
            var session = PrepHoleMapSession()
            session.select(hole: hole)
            session.selectPlan(plan, planCount: 3)
            session.viewport = viewport
            return session
        }
        let prepStates: [(String, PrepHoleMapSession)] = [
            ("prep-hole", prepSession(hole: 1)),
            // 方案 2: its own route, landings ("球杆 码数") and club order.
            ("prep-hole-plan-2", prepSession(hole: 1, plan: 1)),
            ("prep-hole-factual", prepSession(hole: 5)),
            ("prep-hole-waiting", prepSession(hole: 14)),
            // The same precise hole with the zoom and pan the player set on its factual route: the
            // replacement keeps them (the reset control shows the view is not the fitted one).
            ("prep-hole-zoomed", prepSession(
                hole: 1,
                viewport: HoleMapViewportState(zoomScale: 2, offset: CGSize(width: -30, height: 40))
            )),
        ]
        var prepPNGs: [Data] = []
        for (name, session) in prepStates {
            PrepRouteLabelAudit.latest = nil
            prepPNGs.append(try captureScreen(
                NavigationStack {
                    CoursePrepStrategyScreen(
                        rows: prepRows,
                        session: .constant(session),
                        teeOptions: ["blue", "white"],
                        selectedTee: "blue",
                        onSelectTee: { _ in }
                    )
                },
                named: name,
                dark: true,
                settle: 2.0
            ))
            // The labels actually drawn in this render never touch the chrome actually laid out
            // (header, hole badge, bottom panel, reset control); at rest every stroke is labelled.
            guard name != "prep-hole-waiting" else { continue }
            let audit = try XCTUnwrap(PrepRouteLabelAudit.latest, "\(name): the route layer was drawn")
            XCTAssertEqual(audit.hole, session.holeNumber)
            XCTAssertGreaterThanOrEqual(audit.chrome.count, 3, "\(name): header, badge and panel, before any measuring")
            let row = try XCTUnwrap(prepRows.first { $0.number == audit.hole })
            let plan = try XCTUnwrap(session.plan(in: row.plans))
            XCTAssertEqual(audit.labels.count, plan.steps.count, "\(name): one label per stroke")
            let screen = CGRect(origin: .zero, size: audit.viewport)
            for label in audit.labels {
                guard let label else {
                    XCTAssertFalse(session.viewport.isFitted, "\(name): a fitted map labels every stroke")
                    continue
                }
                XCTAssertTrue(screen.contains(label), "\(name): \(label) is on screen")
                for chrome in audit.chrome {
                    XCTAssertFalse(label.intersects(chrome), "\(name): label \(label) under chrome \(chrome)")
                }
            }
        }
        XCTAssertEqual(Set(prepPNGs).count, prepStates.count, "prep snapshot states rendered identically")
        // Independent of the layout's own bookkeeping: render each state again with the header,
        // hole badge and bottom panel painted flat magenta and only the route layer drawn above
        // them, then look for label-pill pixels (the pill's black over magenta) in the image. The
        // detector is first proven on a pill drawn over magenta.
        XCTAssertGreaterThan(
            try Self.pillOverChromePixels(in: Self.syntheticPillOverChrome()).count,
            100,
            "the detector finds a label pill drawn over the chrome"
        )
        for (name, session) in prepStates where name != "prep-hole-waiting" {
            let png = try captureScreen(
                NavigationStack {
                    CoursePrepStrategyScreen(
                        rows: prepRows,
                        session: .constant(session),
                        teeOptions: ["blue", "white"],
                        selectedTee: "blue",
                        onSelectTee: { _ in },
                        chromeAudit: true
                    )
                },
                named: "\(name)-chrome-audit",
                dark: true,
                settle: 2.0
            )
            let scan = try Self.pillOverChromePixels(in: png)
            XCTAssertGreaterThan(scan.chromeFraction, 0.2, "\(name): the audit painted the chrome")
            XCTAssertEqual(
                scan.count,
                0,
                "\(name): a route label is drawn over the header, badge or panel near \(scan.first.map { "\($0)" } ?? "-")"
            )
        }
        // Full screen, not a framed rectangle: near every edge of the viewport (below the navigation
        // bar and above the bottom panel) the map surface is drawn, never the black screen base.
        let prepNames: [String] = prepStates.map { $0.0 }
        for (name, png) in zip(prepNames, prepPNGs) where name != "prep-hole-waiting" {
            let samples: [CGPoint] = [
                CGPoint(x: 0.03, y: 0.2), CGPoint(x: 0.97, y: 0.2), CGPoint(x: 0.5, y: 0.2),
                CGPoint(x: 0.03, y: 0.72), CGPoint(x: 0.97, y: 0.72),
            ]
            for point in samples {
                let pixel = try Self.pixel(in: png, at: point)
                let fromBase = abs(pixel.red - 5) + abs(pixel.green - 7) + abs(pixel.blue - 12)
                XCTAssertGreaterThan(fromBase, 24, "\(name): the map covers (\(point.x), \(point.y)), got \(pixel)")
            }
        }

        // 单场复盘: a representative 18-hole Garmin-style scorecard before the compact metrics,
        // rendered from a round-detail fixture (mirrors /api/v2/history/rounds/{ref}).
        let roundJSON = """
        {"roundRef":"r1","found":true,"title":"Fixture Links",\
        "round":{"courseName":"Fixture Links","date":"2026-05-20","score":80,"par":72,"toPar":8,"holesCompleted":18,"confidence":"high"},\
        "scorecard":[\
        {"hole":1,"par":4,"score":5,"toPar":1,"className":"bogey","putts":2,"penalties":1,"gir":false,"status":"complete"},\
        {"hole":2,"par":3,"score":3,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"status":"complete"},\
        {"hole":3,"par":5,"score":4,"toPar":-1,"className":"birdie","putts":1,"penalties":0,"gir":false,"status":"complete"},\
        {"hole":4,"par":4,"score":6,"toPar":2,"className":"double","putts":3,"penalties":0,"gir":false,"fairway":"left","status":"complete"},\
        {"hole":5,"par":4,"score":4,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":false,"status":"complete"},\
        {"hole":6,"par":4,"score":4,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"fairway":"hit","status":"complete"},\
        {"hole":7,"par":3,"score":4,"toPar":1,"className":"bogey","putts":2,"penalties":0,"gir":false,"status":"complete"},\
        {"hole":8,"par":4,"score":5,"toPar":1,"className":"bogey","putts":2,"penalties":0,"gir":false,"fairway":"right","status":"complete"},\
        {"hole":9,"par":5,"score":5,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"fairway":"hit","status":"complete"},\
        {"hole":10,"par":4,"score":4,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"fairway":"hit","status":"complete"},\
        {"hole":11,"par":4,"score":5,"toPar":1,"className":"bogey","putts":2,"penalties":0,"gir":false,"fairway":"left","status":"complete"},\
        {"hole":12,"par":3,"score":3,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"status":"complete"},\
        {"hole":13,"par":5,"score":6,"toPar":1,"className":"bogey","putts":2,"penalties":0,"gir":false,"fairway":"hit","status":"complete"},\
        {"hole":14,"par":4,"score":4,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"fairway":"hit","status":"complete"},\
        {"hole":15,"par":4,"score":5,"toPar":1,"className":"bogey","putts":2,"penalties":0,"gir":false,"fairway":"right","status":"complete"},\
        {"hole":16,"par":3,"score":4,"toPar":1,"className":"bogey","putts":2,"penalties":0,"gir":false,"status":"complete"},\
        {"hole":17,"par":5,"score":5,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":true,"fairway":"hit","status":"complete"},\
        {"hole":18,"par":4,"score":4,"toPar":0,"className":"par","putts":2,"penalties":0,"gir":false,"fairway":"hit","status":"complete"}],\
        "phaseSummary":[\
        {"phase":"Tee","state":"ready","primary":"7/11 球道命中","metrics":{"fairwaysHit":7,"fairwaysRecorded":11}},\
        {"phase":"Approach","state":"ready","primary":"7/18 标准杆上果岭(GIR)","metrics":{"gir":7,"girRecorded":18}},\
        {"phase":"Short Game","state":"ready","primary":"2 次短杆","metrics":{"shots":2}},\
        {"phase":"Putting","state":"ready","primary":"36 推","metrics":{"totalPutts":36}},\
        {"phase":"Penalty / Damage","state":"ready","primary":"1 罚杆","metrics":{"totalPenalties":1}}],\
        "missingData":[{"label":"shot rows","state":"missing","reason":"no normalized Garmin shot rows for this round"}]}
        """
        let roundDetail = try JSONDecoder().decode(RoundDetail.self, from: Data(roundJSON.utf8))
        try captureScreen(
            ScrollView {
                RoundReviewContent(detail: roundDetail, isLoading: false, errorText: nil, fallbackCourseName: "Fixture Links")
            }
            .background(LivePlayStyle.base),
            named: "round-review",
            dark: true
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
        "phaseStats":[{"phase":"Tee","fairwaysRecorded":180,"fairwaysHit":102,"fairwayMissLeft":46,"fairwayMissRight":32,"coverage":{"ready":180,"total":240,"pct":75}},\
        {"phase":"Approach","girRecorded":300,"gir":99,"missedGir":201,"girPct":33,"coverage":{"ready":300,"total":360,"pct":83.3}},\
        {"phase":"Short Game","roughOrBunkerShots":74,"coverage":{"ready":74,"total":520,"pct":14.2}},\
        {"phase":"Putting","totalPutts":3900,"holesWithPutts":2160,"averagePutts":1.9,"threePutts":240,"coverage":{"ready":2160,"total":2400,"pct":90}}],\
        "teeDirection":{"recorded":180,"hit":102,"left":46,"right":32,"hitPct":57,"dominantMiss":"left"},\
        "approachMiss":{"recorded":300,"gir":99,"missed":201,"short":82,"long":31,"left":51,"right":37,"girPct":33,"dominantMiss":"short"},\
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
        let archiveJSON = """
        {"total":423,"groups":[{"key":"2026-06","label":"2026 年 6 月","count":3,"average18":88.7,"bestScore":86,"rounds":[
        {"id":"r-901","date":"2026-06-11","courseName":"北京天竺黑骑士球员俱乐部 ~ C/A","holesCompleted":18,"score":89,"par":72,"toPar":17,"scoreStrip":[
        {"hole":1,"score":5,"par":4,"toPar":1},{"hole":2,"score":3,"par":3,"toPar":0},{"hole":3,"score":4,"par":5,"toPar":-1},{"hole":4,"score":6,"par":4,"toPar":2},{"hole":5,"score":4,"par":4,"toPar":0}]},
        {"id":"r-880","date":"2026-05-28","courseName":"北京北湖九号国际高尔夫俱乐部","holesCompleted":18,"score":86,"par":72,"toPar":14,"scoreStrip":[
        {"hole":1,"score":4,"par":4,"toPar":0},{"hole":2,"score":4,"par":3,"toPar":1},{"hole":3,"score":5,"par":5,"toPar":0}]},
        {"id":"r-855","date":"2026-05-12","courseName":"Cypress Point Club","holesCompleted":18,"score":91,"par":72,"toPar":19,"scoreStrip":[
        {"hole":1,"score":5,"par":4,"toPar":1},{"hole":2,"score":3,"par":3,"toPar":0},{"hole":3,"score":6,"par":5,"toPar":1}]}]}],
        "availableYears":["2026"],"availableCourses":[]}
        """
        let historyArchive = try JSONDecoder().decode(HistoryRoundsArchive.self, from: Data(archiveJSON.utf8))
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
                    ResultsLandingContent(stats: mobileStats, archive: historyArchive, errorText: nil)
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
                .background(Color.white)
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
        {"found":true,"hole":1,"par":4,"geometryRevision":"snapshot-r1",\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":360,\
        "route":[[120,330,0],[118,180,180],[120,55,360]]}},\
        "shots":[\
        {"id":"s1","start":[120,330],"end":[122,200],"club":"Driver","lie":"TeeBox","endLie":"Fairway","shotType":"TEE","order":1,"synthetic":false},\
        {"id":"s2","start":[122,200],"end":[110,120],"club":"7I","lie":"Fairway","endLie":"Bunker","shotType":"APPROACH","order":2,"synthetic":false},\
        {"id":"s3","start":[110,120],"end":[119,60],"club":"SW","lie":"Bunker","endLie":"Green","shotType":"APPROACH","order":3,"synthetic":false}]}
        """
        let shotMap = try JSONDecoder().decode(RoundHoleShotMap.self, from: Data(shotMapJSON.utf8))
        let reviewScorecard = roundDetail.scorecard
        // B3 每洞落点: score box on top, numbered landings coloured by lie with "一号木 200" labels and
        // "推 ×2", the 18-hole score strip at the bottom.
        try captureScreen(
            VStack(spacing: 10) {
                HStack {
                    RoundHoleScoreBox(hole: 1, par: 4, row: reviewScorecard.first, putts: 2, penalties: 0)
                    Spacer()
                }
                .padding(.horizontal, 14)
                RoundShotMapView(shotMap: shotMap, putts: 2)
                Spacer(minLength: 0)
                RoundHoleScoreStrip(holes: reviewScorecard.map(\.hole), current: 1, scorecard: reviewScorecard, onSelect: { _ in })
            }
            .padding(.top, 12)
            .background(RoundHoleMapStyle.base),
            named: "round-shot-map",
            dark: true
        )

        // B3 9-of-18 round: the strip keeps holes 10–18 visible; unplayed holes are dimmed and cannot
        // be opened.
        let partialRows = (1...18).map { hole -> String in
            hole <= 9 ? #"{"hole":\#(hole),"par":4,"score":\#(hole % 3 + 3)}"# : #"{"hole":\#(hole),"par":4}"#
        }
        let partialScorecard = try JSONDecoder().decode(
            [RoundDetailHole].self, from: Data("[\(partialRows.joined(separator: ","))]".utf8)
        )
        let partialHoles = RoundReviewHoles(partialScorecard)
        XCTAssertEqual(partialHoles.strip, Array(1...18))
        XCTAssertEqual(partialHoles.played, Array(1...9))
        try captureScreen(
            VStack(spacing: 12) {
                Spacer(minLength: 0)
                LiveNineCard(
                    label: "IN",
                    holes: Array(RoundReviewScorecard(partialScorecard).holes.dropFirst(9)),
                    scores: RoundReviewScorecard(partialScorecard).scores,
                    onSelect: { _ in },
                    cellIdentifier: { "round-review-hole-\($0)" },
                    canSelect: partialHoles.canOpen
                )
                .padding(.horizontal, 20)
                RoundHoleScoreStrip(
                    holes: partialHoles.strip, current: 9, scorecard: partialScorecard,
                    onSelect: { _ in }, canSelect: partialHoles.canOpen
                )
            }
            .padding(.bottom, 12)
            .background(RoundHoleMapStyle.base),
            named: "round-hole-strip-partial",
            dark: true
        )

        // B3 mapless fallback: full shots numbered like the map, putts as one "推 ×N" line.
        let factShots = [
            RoundShot(shotId: "f1", start: nil, end: nil, club: "Driver", lie: "teebox", endLie: "fairway", order: 1),
            RoundShot(shotId: "f2", start: nil, end: nil, club: "7I", lie: "fairway", endLie: "green", order: 2),
            RoundShot(shotId: "f3", start: nil, end: nil, lie: "Green", shotType: "PENALTY_PUTT", order: 3),
            RoundShot(shotId: "f4", start: nil, end: nil, club: "Putter", lie: "green", shotType: "PUTT", order: 4),
        ]
        try captureScreen(
            VStack {
                RoundShotFactList(shots: factShots, ppm: nil, recordedPutts: 2)
                Spacer(minLength: 0)
            }
            .padding(16)
            .background(RoundHoleMapStyle.base),
            named: "round-shot-facts",
            dark: true
        )

        // B3 同屏改杆: the same map as drag handles. With a shot selected the bar shows ‹ 第 N 杆 · D 码 ›
        // + 删除, the club pills (guess first) and the lie grid; with none selected 推杆 / 罚杆 −/+.
        let editModel = RoundEditModel(
            map: shotMap,
            sync: SyncClient(baseURL: URL(string: "https://caddie.example")!),
            roundRef: "r1",
            putts: 2
        )
        editModel.enterEdit()
        try captureScreen(
            VStack(spacing: 0) {
                RoundShotMapView(shotMap: editModel.map, editModel: editModel).frame(height: 460)
                Spacer(minLength: 0)
                RoundShotEditBar(editModel: editModel)
            }
            .background(RoundHoleMapStyle.base),
            named: "review-edit-counters",
            dark: true
        )
        // A precise overlay + revision and stable shot ids keep every recorded shot editable.
        XCTAssertTrue(editModel.canEditPositions)
        XCTAssertEqual(editModel.map.shots.map(\.id), ["s1", "s2", "s3"])
        editModel.selectedShotId = "s2"
        try captureScreen(
            VStack(spacing: 0) {
                RoundShotMapView(shotMap: editModel.map, editModel: editModel).frame(height: 460)
                Spacer(minLength: 0)
                RoundShotEditBar(editModel: editModel)
            }
            .background(RoundHoleMapStyle.base),
            named: "review-edit-handles",
            dark: true
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
    /// Two physically different complete routes for the live-map snapshots: Par - 2 legs each
    /// (at least one), the last a scoring leg to the flag, carries summing to the route length.
    /// One RGB pixel (0-255) of a PNG at a fractional position (0...1, from the top-left).
    private static func pixel(in png: Data, at point: CGPoint) throws -> (red: Int, green: Int, blue: Int) {
        let image = try XCTUnwrap(UIImage(data: png)?.cgImage)
        let x = min(image.width - 1, max(0, Int(point.x * CGFloat(image.width))))
        let y = min(image.height - 1, max(0, Int(point.y * CGFloat(image.height))))
        var bytes = [UInt8](repeating: 0, count: 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress,
                width: 1,
                height: 1,
                bitsPerComponent: 8,
                bytesPerRow: 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            // CoreGraphics draws from the bottom-left: shift the wanted pixel onto (0, 0).
            context.draw(image, in: CGRect(
                x: -CGFloat(x),
                y: -CGFloat(image.height - 1 - y),
                width: CGFloat(image.width),
                height: CGFloat(image.height)
            ))
            return true
        }
        XCTAssertTrue(drawn, "pixel sampling context")
        return (Int(bytes[0]), Int(bytes[1]), Int(bytes[2]))
    }

    /// Pixels of a route-label pill composited over the magenta audit chrome: dark magenta
    /// (the pill's translucent black over magenta, gamma or linear blended) filling a solid
    /// 3 x 3 pt block. Route strokes' black edge is only 1.5 pt wide under their white core, and
    /// label text is white, so neither can form such a block. Positions are in points from the
    /// top-left; `chromeFraction` is the share of the image painted magenta.
    private static func pillOverChromePixels(
        in png: Data
    ) throws -> (count: Int, first: CGPoint?, chromeFraction: Double) {
        let image = try XCTUnwrap(UIImage(data: png)?.cgImage)
        let width = image.width
        let height = image.height
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        XCTAssertTrue(drawn, "pixel scan context")
        let pointsPerPixel = 390 / CGFloat(max(width, 1))
        // Summed-area table of candidate (dark magenta) pixels; row 0 of the buffer is the top.
        var sums = [Int](repeating: 0, count: (width + 1) * (height + 1))
        var magenta = 0
        for y in 0..<height {
            var rowSum = 0
            for x in 0..<width {
                let index = (y * width + x) * 4
                let red = Int(bytes[index])
                let green = Int(bytes[index + 1])
                let blue = Int(bytes[index + 2])
                if red > 235, green < 20, blue > 235 { magenta += 1 }
                let candidate = green <= 24 && abs(red - blue) <= 16 && (45...160).contains(red)
                rowSum += candidate ? 1 : 0
                sums[(y + 1) * (width + 1) + x + 1] = sums[y * (width + 1) + x + 1] + rowSum
            }
        }
        let block = max(Int((3 / pointsPerPixel).rounded(.up)), 2)
        var count = 0
        var first: CGPoint?
        if width >= block, height >= block {
            for y in 0...(height - block) {
                for x in 0...(width - block) {
                    let total = sums[(y + block) * (width + 1) + x + block]
                        - sums[y * (width + 1) + x + block]
                        - sums[(y + block) * (width + 1) + x]
                        + sums[y * (width + 1) + x]
                    guard total == block * block else { continue }
                    count += 1
                    if first == nil {
                        first = CGPoint(x: CGFloat(x) * pointsPerPixel, y: CGFloat(y) * pointsPerPixel)
                    }
                }
            }
        }
        return (count, first, Double(magenta) / Double(max(width * height, 1)))
    }

    /// A 390 x 120 pt image: magenta chrome with one route-label pill drawn over it exactly as
    /// `LivePlannedRouteRenderer` fills it.
    private static func syntheticPillOverChrome() throws -> Data {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 390, height: 120)).image { ctx in
            UIColor(red: 1, green: 0, blue: 1, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 390, height: 120))
            UIColor.black.withAlphaComponent(0.74).setFill()
            UIBezierPath(roundedRect: CGRect(x: 40, y: 40, width: 72, height: 24), cornerRadius: 12).fill()
        }
        return try XCTUnwrap(image.pngData())
    }

    private static func snapshotCaddieRoutes(par: Int, routeLengthM: Double) -> [CaddiePlanSequence] {
        let legCount = max(1, par - 2)
        let plans: [(id: String, label: String, clubs: [String], weights: [Double])] = [
            ("snapshot-stock", "稳健", ["1W", "8I", "9I"], [0.6, 0.4]),
            ("snapshot-layup", "保守", ["3H", "6I", "PW"], [0.5, 0.5]),
        ]
        return plans.map { plan in
            let weights: [Double] = {
                switch legCount {
                case 1: return [1]
                case 2: return plan.weights
                default:
                    let head = Array(repeating: 0.7 / Double(legCount - 1), count: legCount - 1)
                    return head + [0.3]
                }
            }()
            var offset = 0.0
            let steps = weights.enumerated().map { index, weight -> CaddiePlanSequenceStep in
                let carry = (routeLengthM * weight).rounded()
                offset += carry
                let isLast = index == weights.count - 1
                return CaddiePlanSequenceStep(
                    id: "\(plan.id)-\(index)",
                    role: isLast ? "scoring" : (index == 0 ? "tee" : "position"),
                    clubName: plan.clubs[min(index, plan.clubs.count - 1)],
                    targetCarryM: carry,
                    expectedRemainingM: isLast ? 0 : routeLengthM - offset,
                    sampleSize: 12,
                    confidence: "medium",
                    sourceRefs: [],
                    routeOffsetM: isLast ? routeLengthM : offset,
                    planIndex: index
                )
            }
            return CaddiePlanSequence(
                id: plan.id,
                label: plan.label,
                expectedRemainingM: 0,
                riskScore: nil,
                confidence: "medium",
                coverageText: nil,
                sourceRefs: [],
                steps: steps
            )
        }
    }

    @discardableResult
    private func captureScreen(
        _ view: some View,
        named name: String,
        dark: Bool = false,
        settle: TimeInterval = 1.0
    ) throws -> Data {
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
        RunLoop.main.run(until: Date(timeIntervalSinceNow: settle))
        host.view.layoutIfNeeded()
        let renderer = UIGraphicsImageRenderer(size: size)
        let image = renderer.image { ctx in
            window.layer.render(in: ctx.cgContext)
        }
        guard let data = image.pngData() else {
            XCTFail("no png for \(name)")
            return Data()
        }
        let dir = try FileManager.default
            .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("design-snapshots", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try data.write(to: dir.appendingPathComponent("\(name).png"))
        print("WROTE_SCREEN \(name)")
        return data
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
