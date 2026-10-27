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

    /// 设置 → 离线球场 (the only place download progress and storage use appear). ImageRenderer cannot draw a
    /// List, so the section is laid out in a plain stack at the settings width.
    @MainActor
    func testRenderSettingsOfflineCourses() throws {
        func record(_ id: Int, _ name: String, _ phase: PrepCourseDownloadPhase, _ downloaded: Int) -> PrepCourseDownloadRecord {
            PrepCourseDownloadRecord(
                course: MobileCourseOption(globalId: id, name: name, holes: 18, teeBox: "blue"),
                teeBox: "blue",
                phase: phase,
                downloadedHoles: downloaded,
                totalHoles: 18
            )
        }
        let rows = OfflineCourseDownloadRow.rows(
            live: LiveCourseDownloadProgress(
                identity: .init(roundId: "r", loopKey: "1:front+1:back", teeBox: "blue"),
                courseName: "北京丽宫",
                readyHoles: 7,
                totalHoles: 18
            ),
            current: .init(roundId: "r", loopKey: "1:front+1:back", teeBox: "blue"),
            downloads: [
                record(2, "华彬庄园", .downloading, 12),
                record(3, "北京高尔夫俱乐部", .queued, 0),
                record(4, "北湖九号", .ready, 18),
            ]
        )
        let view = VStack(alignment: .leading, spacing: 12) {
            OfflineCourseDownloadsSection(
                rows: rows,
                usage: OfflineStorageUsage(topoBytes: 152_000_000, templateBytes: 2_600_000)
            )
        }
        .padding(16)
        .frame(width: 390, alignment: .leading)
        .background(Color(.systemBackground))
        try render(view, named: "settings-offline-courses")
    }

    /// 设置 → 离线球场 with the 可能会打 toggle, in a real system List hosted in a window (ImageRenderer
    /// cannot draw a List or a Toggle): the switch, its label and the footer as the app shows them.
    @MainActor
    func testCaptureSettingsSpeculativePrefetch() throws {
        let key = SpeculativePrefetchSettings.cellularKey
        let previous = UserDefaults.standard.object(forKey: key)
        UserDefaults.standard.removeObject(forKey: key)
        defer { UserDefaults.standard.set(previous, forKey: key) }
        let view = NavigationStack {
            List {
                OfflineCourseDownloadsSection(
                    rows: [],
                    usage: OfflineStorageUsage(topoBytes: 152_000_000, templateBytes: 2_600_000)
                )
                SpeculativePrefetchSettingsSection()
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
        }
        try captureScreen(view, named: "settings-prefetch-cellular")
    }

    @MainActor
    func testRenderRoundHome() throws {
        // README §8 home main card, all three states: in progress, a known course, no course.
        let deltas: [Int] = [0, 1, 0, -1, 1, 0, 1, 2, 0, 0, 1, 0, -1, 1, 0, 1, 0, 3]
        let strip: [HistoryScoreCell] = deltas.enumerated().map { index, delta in
            HistoryScoreCell(hole: index + 1, par: 4, score: 4 + delta, toPar: delta, className: nil)
        }
        // C99 首页：单一「打一场球」入口、快捷球场、上一场与最近走势。
        let playedToPar: [Int] = [0, 1, 0, -1, 1, 1]
        var dots: [HubHoleDot] = []
        for hole in 1...9 {
            let toPar: Int? = hole <= playedToPar.count ? playedToPar[hole - 1] : nil
            dots.append(HubHoleDot(hole: hole, toPar: toPar, isCurrent: hole == 7))
        }
        let scores: [Int] = [92, 89, 91, 88, 90, 86, 87, 85]
        let topoURL = SyncClient.topoImageURL(
            baseURL: URL(string: "https://caddie.example")!, globalId: 3881, localHole: 1)
        let heroes = VStack(spacing: 10) {
            HubInProgressCard(courseName: "北京丽宫", activeHole: 7, recorded: 6, toPar: 2, dots: dots)
            HubStartPlayCard()
            HStack(spacing: 8) {
                HubQuickCourseChip(title: "北京天竺黑骑士", isNearby: true)
                HubQuickCourseChip(title: "丽宫", isNearby: false)
            }
        }
        let tiles = HubRecentTrendRow(scores: scores)
        let lastRound = VStack(alignment: .leading, spacing: 9) {
            HubSectionLabel("上一场")
            HubLastRoundCard(courseName: "Cypress Point Club", date: "2026-07-30", score: 82, toPar: 10,
                             holesCompleted: 18, par: 72, topoURL: topoURL, scoreStrip: strip)
        }
        let view = VStack(spacing: 10) {
            heroes
            tiles
            lastRound
        }
        .padding(16)
        .frame(width: 390)
        .background(HubBentoStyle.ground)
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
        // First launch / slow backend: no home package yet. The same Hub (今天去哪打？ + 备战 · 成绩)
        // shows, never the legacy 打球 / 备战 / 成绩 list.
        try captureScreen(RoundHomeView(package: nil, apiBaseURL: apiBaseURL), named: "full-home-no-package")
        // Hub WITH an in-progress round → shows the 进行中 card + 「结束本场」(cancel) button.
        let activeState = LiveRoundStateSnapshot(roundId: package.roundId, activeHole: package.holes.first?.number ?? 1, holes: [])
        try captureScreen(
            RoundHomeView(package: package, apiBaseURL: apiBaseURL, liveRoundState: activeState, courseOptions: courses),
            named: "full-home-active"
        )
        // An active round before its package has loaded: the 进行中 loading card, never a blank top.
        try captureScreen(
            RoundHomeView(package: nil, apiBaseURL: apiBaseURL, liveRoundState: activeState),
            named: "full-home-active-no-package"
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
        try captureScreen(
            NavigationStack {
                StartRoundView(
                    defaultCourseGlobalId: 31795,
                    courseOptions: courses,
                    initialPage: .course
                )
            },
            named: "full-start-page-course"
        )
        try captureScreen(
            NavigationStack {
                StartRoundView(
                    defaultCourseGlobalId: 31795,
                    defaultTeeBox: "blue",
                    initialCourseTees: loopBTees,
                    courseOptions: courses,
                    onLoadCourseTees: { _ in loopBTees },
                    initialPage: .setup
                )
            },
            named: "full-start-page-setup"
        )
        // Field report 2026-10-10 (Arzaga Golf Club): an 18-hole Jack Nicklaus II beside a 9-hole
        // Gary Player. Both course tiles show whichever is selected; the selected 18-hole course
        // still offers 前九 / 后九. Provider labels and tee rows as production GET
        // /api/v2/courses/{26807,26808}/tees?ensure_release=false (2026-10-10).
        let arzaga = [
            MobileCourseOption(
                globalId: 26807, name: "Arzaga Golf Club", holes: 18,
                venueName: "Arzaga Golf Club", segmentLabel: "Jack Nicklaus II", segmentHoles: 18
            ),
            MobileCourseOption(
                globalId: 26808, name: "Arzaga Golf Club", holes: 9,
                venueName: "Arzaga Golf Club", segmentLabel: "Gary Player", segmentHoles: 9
            ),
        ]
        let nicklausTees = try JSONDecoder().decode([CourseTee].self, from: Data(#"""
        [
          {"teeBox": "white", "name": "White", "yards": 6825, "holeCount": 18, "default": true},
          {"teeBox": "yellow", "name": "Yellow", "yards": 6432, "holeCount": 18, "default": false}
        ]
        """#.utf8))
        let playerTees = try JSONDecoder().decode([CourseTee].self, from: Data(#"""
        [
          {"teeBox": "white", "name": "White", "yards": 3111, "holeCount": 9, "default": true},
          {"teeBox": "yellow", "name": "Yellow", "yards": 2953, "holeCount": 9, "default": false}
        ]
        """#.utf8))
        // An 18-hole tee total is never shown as the total of the nine being started.
        XCTAssertNil(StartRoundPresentation.teeYards(total: 6825, teeHoleCount: 18, playedHoles: 9))
        XCTAssertEqual(StartRoundPresentation.teeYards(total: 3111, teeHoleCount: 9, playedHoles: 9), 3111)
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: arzaga[1], loops: arzaga, teeBox: "white"),
            StartRoundPresentation.startActionTitle(selected: arzaga[1], loops: [arzaga[1]], teeBox: "white"),
            "the nine's start action is unchanged by the 18-hole course beside it"
        )
        for (selectedId, tees, name) in [
            (26808, playerTees, "full-start-mixed-venue-nine"),
            (26807, nicklausTees, "full-start-mixed-venue-eighteen"),
        ] {
            try captureScreen(
                NavigationStack {
                    StartRoundView(
                        defaultCourseGlobalId: selectedId,
                        defaultTeeBox: "white",
                        initialCourseTees: tees,
                        courseOptions: arzaga,
                        onLoadCourseTees: { globalId in globalId == 26807 ? nicklausTees : playerTees }
                    )
                },
                named: name
            )
        }
        // Owner feedback (#392): a slow nearby answer. 黑骑士 A/B are downloaded (with their provider
        // coordinates); they stay tappable under one waiting line, captioned "已下载 18 洞" (what the
        // phone holds), and nearby's arrival replaces the line with the venue row ("27 洞"). The
        // in-process host renders before the discovery task runs, so each phase is seeded with the
        // state that task reaches; the live TeeSelection journey drives the real slow request.
        let downloadedBlackKnight = HubNearby.options(
            from: Array(nearbyBlackKnight.prefix(2)),
            catalogue: [],
            downloaded: []
        )
        let nearbyNeverAnswers: (Double, Double, Int) async throws -> [MobileCourseSearchMatch] = { _, _, _ in
            try await Task.sleep(nanoseconds: 600_000_000_000)
            return []
        }
        // No fix yet: "正在等待定位…" above the downloaded rows.
        try captureScreen(
            NavigationStack {
                StartRoundView(
                    downloadedCourseOptions: downloadedBlackKnight,
                    onNearbyCourses: nearbyNeverAnswers,
                    locationProvider: LocationProvider(),
                    initialNearby: .waiting
                )
            },
            named: "full-start-nearby-waiting-gps"
        )
        // A fix, nearby still in flight: "正在找附近球场…".
        try captureScreen(
            NavigationStack {
                StartRoundView(
                    downloadedCourseOptions: downloadedBlackKnight,
                    onNearbyCourses: nearbyNeverAnswers,
                    locationProvider: LocationProvider(fixedFix: atBlackKnight),
                    initialNearby: .waiting
                )
            },
            named: "full-start-nearby-waiting"
        )
        // Nearby answered: the line is gone, the venue row has its distance and 27 洞, and loop A
        // (picked from the downloaded rows before the answer) is still the selection.
        try captureScreen(
            NavigationStack {
                StartRoundView(
                    defaultCourseGlobalId: 31794,
                    defaultTeeBox: "blue",
                    downloadedCourseOptions: downloadedBlackKnight,
                    onNearbyCourses: { _, _, _ in nearbyBlackKnight },
                    locationProvider: LocationProvider(fixedFix: atBlackKnight),
                    initialNearby: .answered(
                        HubNearby.options(from: nearbyBlackKnight, catalogue: [], downloaded: downloadedBlackKnight)
                    )
                )
            },
            named: "full-start-nearby-arrived"
        )
        // Nearby failed: the retry icon instead of the line; the downloaded rows remain.
        try captureScreen(
            NavigationStack {
                StartRoundView(
                    downloadedCourseOptions: downloadedBlackKnight,
                    onNearbyCourses: { _, _, _ in throw URLError(.notConnectedToInternet) },
                    locationProvider: LocationProvider(fixedFix: atBlackKnight),
                    initialNearby: .failed
                )
            },
            named: "full-start-nearby-failed"
        )
        // 开始一场's catalogue sheet: no positioning / download status copy (README §8).
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

        // B1 live main screen: the same synthetic map attached to the fixture's first hole, so the
        // full-screen map, the corner controls, the top-right ladder and the labelled caddie route
        // ("杆名 码数" at every landing) are reviewable together. Each state is injected up front
        // so the captures are deterministic: default (no obstacle), one obstacle selected, the
        // second of two plans, and a zoomed map with 回到.
        if let firstHole = package.holes.first {
            let livePrepJSON = """
            {"hole":\(firstHole.number),"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,"geometryCoverage":"ready",\
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
            XCTAssertEqual(
                LiveMapDisplayState.resolveLive(
                    .init(
                        coverage: livePrepHole.geometryCoverage,
                        preciseTopoImageReady: CoursePrepHole.hasDecodableEmbeddedTopo(livePrepHole.map?.image),
                        garminRaster: nil,
                        garminImageFailed: true,
                        hasCachedPreciseTopo: false
                    )
                ),
                .precise,
                "ready embedded map must remain precise when Garmin fails"
            )
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
            let partialPrepJSON = livePrepJSON
                .replacingOccurrences(
                    of: "\"geometryCoverage\":\"ready\",",
                    with: "\"geometryCoverage\":\"partial\","
                )
                .replacingOccurrences(
                    of: "\"map\":{\"image\":\"\(b64)\",",
                    with: "\"greenOutline\":{\"available\":true,\"source\":\"fixture\",\"pointsPx\":[\(greenOutlineJSON)]},\"holeImageProjection\":{\"available\":true,\"widthPx\":240,\"heightPx\":360,\"refs\":[{\"lat\":40,\"lon\":116,\"px\":15.458937,\"py\":26.25},{\"lat\":40,\"lon\":116.001,\"px\":15.458937,\"py\":326.25},{\"lat\":40.001,\"lon\":116,\"px\":135.265700,\"py\":26.25}]},\"map\":{"
                )
            XCTAssertNotEqual(partialPrepJSON, livePrepJSON, "fixture: the topo image must be removed")
            XCTAssertTrue(partialPrepJSON.contains("\"holeImageProjection\""), "fixture: partial projection must be injected")
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
            // Partial snapshots use a deterministic Garmin fixture so the pending/factual states
            // exercise the real raster path instead of falling through to the numeric placeholder.
            let partialRasterBaseURL = URL(string: "https://caddie.example")!
            let partialRasterDescriptor = GarminRasterResponse(
                available: true,
                imageUrl: "/api/v2/courses/\(firstHole.sourceGlobalId)/holes/\(firstHole.sourceLocalHole)/garmin-raster.jpg?v=snapshot-partial-454",
                projection: GarminRasterProjection(
                    widthPx: 1242,
                    heightPx: 1920,
                    refs: [
                        CoursePrepProjectionRef(lat: 40, lon: 116, px: 80, py: 140),
                        CoursePrepProjectionRef(lat: 40, lon: 116.001, px: 80, py: 1740),
                        CoursePrepProjectionRef(lat: 40.001, lon: 116, px: 700, py: 140),
                    ]
                ),
                mode: "H"
            )
            let partialRasterURL = try XCTUnwrap(
                partialRasterDescriptor.resolvedImageURL(relativeTo: partialRasterBaseURL)
            )
            GarminRasterImageStore.preload(holeImage, for: partialRasterURL)
            // Pending: Garmin 图 + 按投影 remap 的路线、果岭、障碍 are visible while the precise
            // topo is still expected online (a service URL, nothing cached).
            XCTAssertEqual(
                LiveMapDisplayState.resolveLive(
                    .init(
                        coverage: partialPrep.geometryCoverage,
                        preciseTopoImageReady: false,
                        garminRaster: partialRasterDescriptor,
                        garminImageFailed: false,
                        hasCachedPreciseTopo: false
                    )
                ),
                .garminRaster
            )
            let garminProjection = try XCTUnwrap(partialRasterDescriptor.projection?.coursePrepProjection)
            let remapped = try XCTUnwrap(LiveMapDisplaySelection.overlay(for: .garminRaster, precise: partialPrep.resolvedMapOverlay, preciseProjection: partialPrep.holeImageProjection, garminProjection: garminProjection))
            XCTAssertEqual(remapped.w, 1242)
            XCTAssertEqual(remapped.h, 1920)
            let firstRemappedPoint = try XCTUnwrap(remapped.route.first)
            XCTAssertGreaterThanOrEqual(firstRemappedPoint.count, 2)
            XCTAssertEqual(firstRemappedPoint[0], 621, accuracy: 1)
            XCTAssertEqual(firstRemappedPoint[1], 1760, accuracy: 1)
            for point in remapped.route {
                XCTAssertGreaterThanOrEqual(point.count, 2)
                XCTAssertGreaterThanOrEqual(point[0], 0)
                XCTAssertLessThanOrEqual(point[0], 1242)
                XCTAssertGreaterThanOrEqual(point[1], 0)
                XCTAssertLessThanOrEqual(point[1], 1920)
            }
            try captureScreen(
                NavigationStack {
                    CurrentHoleView(
                        package: partialPackage,
                        hole: firstHole,
                        snapshotState: .init(
                            selectsFirstHazard: true,
                            caddieRoutes: routes,
                            garminRaster: partialRasterDescriptor
                        ),
                        caddieBaseURL: partialRasterBaseURL
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
                        snapshotState: .init(
                            caddieRoutes: routes,
                            garminRaster: partialRasterDescriptor
                        ),
                        caddieBaseURL: partialRasterBaseURL
                    )
                },
                named: "full-hole-map-partial-pending-default",
                dark: true
            )
            // ... and with no drawable route at all it shows the numeric placeholder and download
            // copy instead of the retired full-screen waiting page.
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
                named: "full-hole-map-numeric-placeholder",
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

        // B5 成绩 / 表现分析 / 成绩分布 (README §9) + course drill-in, from a compact mobile-stats
        // fixture: 21 scored 18-hole rounds (the landing shows the newest 20 with the 10-round
        // average), the B0 putting buckets and scrambling, and a whole-history analysis baseline.
        let statsJSON = """
        {"summary":{"totalRounds":423,"courseCount":11,"average18":92.4,"median18":92,"recent10Average":88.4,"bestScore":82,"worstScore":106,"handicapEstimate":18.2,"handicapTrend":-0.8,"handicapChangeRecent20":-1.4},\
        "trend":{"points":[\
        {"date":"2026-04-01","score":95,"toPar":23,"roundId":"t-00"},\
        {"date":"2026-04-06","score":91,"toPar":19,"roundId":"t-01"},\
        {"date":"2026-04-11","score":97,"toPar":25,"roundId":"t-02"},\
        {"date":"2026-04-16","score":89,"toPar":17,"roundId":"t-03"},\
        {"date":"2026-04-21","score":93,"toPar":21,"roundId":"t-04"},\
        {"date":"2026-04-26","score":90,"toPar":18,"roundId":"t-05"},\
        {"date":"2026-05-01","score":94,"toPar":22,"roundId":"t-06"},\
        {"date":"2026-05-06","score":88,"toPar":16,"roundId":"t-07"},\
        {"date":"2026-05-11","score":92,"toPar":20,"roundId":"t-08"},\
        {"date":"2026-05-16","score":96,"toPar":24,"roundId":"t-09"},\
        {"date":"2026-05-21","score":86,"toPar":14,"roundId":"t-10"},\
        {"date":"2026-05-26","score":90,"toPar":18,"roundId":"t-11"},\
        {"date":"2026-06-01","score":87,"toPar":15,"roundId":"t-12"},\
        {"date":"2026-06-06","score":91,"toPar":19,"roundId":"t-13"},\
        {"date":"2026-06-11","score":85,"toPar":13,"roundId":"t-14"},\
        {"date":"2026-06-16","score":88,"toPar":16,"roundId":"t-15"},\
        {"date":"2026-06-21","score":84,"toPar":12,"roundId":"t-16"},\
        {"date":"2026-06-26","score":89,"toPar":17,"roundId":"t-17"},\
        {"date":"2026-07-01","score":86,"toPar":14,"roundId":"t-18"},\
        {"date":"2026-07-06","score":83,"toPar":11,"roundId":"t-19"},\
        {"date":"2026-07-11","score":82,"toPar":10,"roundId":"t-20"}]},\
        "scoring":{"outcomes":{"eagleOrBetter":1,"birdie":40,"par":300,"bogey":250,"doubleOrWorse":120},\
        "outcomeDistribution":[{"key":"eagleOrBetter","label":"Eagle+","count":1,"pct":0.5},{"key":"birdie","label":"Birdie","count":40,"pct":6.5},{"key":"par","label":"Par","count":300,"pct":43.5},{"key":"bogey","label":"Bogey","count":250,"pct":35.2},{"key":"double","label":"Double","count":70,"pct":10.2},{"key":"triple","label":"Triple","count":20,"pct":2.8},{"key":"quadPlus","label":"+4 or worse","count":10,"pct":1.4}],\
        "scoreBands":[{"label":"80s","count":42},{"label":"90s","count":171},{"label":"100+","count":93}],\
        "byPar":[{"par":3,"holeCount":4,"averageToPar":0.62,"parOrBetterPct":38},{"par":4,"holeCount":10,"averageToPar":0.44,"parOrBetterPct":42},{"par":5,"holeCount":4,"averageToPar":0.21,"parOrBetterPct":55},{"par":6,"averageToPar":1.1,"parOrBetterPct":10}],\
        "phaseStats":[{"phase":"Tee","fairwaysRecorded":180,"fairwaysHit":102,"fairwayMissLeft":46,"fairwayMissRight":32,"coverage":{"ready":180,"total":240,"pct":75}},\
        {"phase":"Approach","girRecorded":300,"gir":99,"missedGir":201,"girPct":33,"coverage":{"ready":300,"total":360,"pct":83.3}},\
        {"phase":"Short Game","roughOrBunkerShots":74,"coverage":{"ready":74,"total":520,"pct":14.2}},\
        {"phase":"Putting","totalPutts":3900,"holesWithPutts":2160,"averagePutts":1.9,"threePutts":240,"coverage":{"ready":2160,"total":2400,"pct":90}}],\
        "teeDirection":{"recorded":180,"hit":102,"left":46,"right":32,"hitPct":57,"dominantMiss":"left"},\
        "approachMiss":{"recorded":300,"gir":99,"missed":201,"short":82,"long":31,"left":51,"right":37,"girPct":33,"dominantMiss":"short"},\
        "putting":{"averagePutts":1.92,"averagePuttsPerRound":32.5,"roundsWithPutts":120,"threePutts":240,"holesWithPutts":2160,"zeroPutts":43,"onePutts":410,"twoPutts":1426,"threePlusPutts":281,"zeroPuttPct":2.0,"onePuttPct":19.0,"twoPuttPct":66.0,"threePlusPuttPct":13.0},\
        "scrambling":{"chances":1340,"saves":322,"pct":24.0},"penalties":{"total":96,"holesRecorded":1800,"roundsRecorded":100,"averagePerRound":0.96}},\
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
        // 表现分析 compares a window with the whole history (↑ 绿 better, ↓ 黄 worse).
        let baselineJSON = """
        {"scoring":{"teeDirection":{"recorded":400,"hit":196,"left":104,"right":100},\
        "approachMiss":{"recorded":600,"gir":234,"missed":366,"short":160,"long":60,"left":70,"right":76},\
        "scrambling":{"chances":2600,"saves":572,"pct":22.0},\
        "putting":{"averagePutts":1.86,"holesWithPutts":4000,"onePuttPct":24,"twoPuttPct":66,"threePlusPuttPct":10}}}
        """
        let baselineStats = try JSONDecoder().decode(MobileStats.self, from: Data(baselineJSON.utf8))
        try captureScreen(
            NavigationStack {
                ScrollView {
                    ScoreDistributionContent(stats: mobileStats)
                }
                .background(HubStyle.grouped)
                .navigationTitle("成绩分布")
            },
            named: "results-distribution"
        )
        // 成绩 in its four load states (Codex review of #364): loaded, first load with nothing
        // cached (no "暂无成绩", no invented 0), a cached page refreshing, a failed archive
        // beside loaded stats, and a genuinely empty history.
        let emptyStats = try JSONDecoder().decode(MobileStats.self, from: Data(#"{"summary":{"totalRounds":0}}"#.utf8))
        let emptyArchive = try JSONDecoder().decode(HistoryRoundsArchive.self, from: Data(#"{"total":0,"groups":[]}"#.utf8))
        let landingStates: [(String, MobileStats?, HistoryRoundsArchive?, String?, Bool)] = [
            ("results-landing", mobileStats, historyArchive, nil, false),
            ("results-landing-loading", nil, nil, nil, true),
            ("results-landing-refreshing", mobileStats, historyArchive, nil, true),
            ("results-landing-partial-error", mobileStats, nil, "球局档案暂时取不到", false),
            ("results-landing-empty", emptyStats, emptyArchive, nil, false),
        ]
        for (name, stats, archive, error, loading) in landingStates {
            try captureScreen(
                NavigationStack {
                    ScrollView {
                        ResultsLandingContent(stats: stats, archive: archive, errorText: error, isLoading: loading)
                    }
                    .background(HubStyle.grouped)
                    .navigationTitle("成绩")
                },
                named: name
            )
        }
        // 表现分析: the real page with its window picker. Default 20 场 (↑ ↓ against the 20 before),
        // then switched to 10 场 with that window's own numbers and comparison.
        let analysisStats = MobileStats(
            summary: mobileStats.summary, scoring: mobileStats.scoring,
            previous: MobileStatsPrevious(window: "prev20", roundCount: 20, scoring: baselineStats.scoring)
        )
        var analysisState = AnalysisLoadState()
        analysisState.complete(analysisState.currentRequest, stats: analysisStats)
        XCTAssertEqual(analysisState.window, "last20")
        let tenJSON = """
        {"summary":{"totalRounds":10},"scoring":{"teeDirection":{"recorded":140,"hit":71,"left":40,"right":29},\
        "approachMiss":{"recorded":180,"gir":50,"short":64,"long":20,"left":24,"right":22},\
        "scrambling":{"chances":130,"saves":34,"pct":26.2},\
        "putting":{"averagePutts":1.95,"holesWithPutts":180,"onePuttPct":18,"twoPuttPct":64,"threePlusPuttPct":18}},\
        "previous":{"window":"prev10","roundCount":10,"scoring":{"teeDirection":{"recorded":140,"hit":66},\
        "approachMiss":{"recorded":180,"gir":54},"scrambling":{"chances":130,"saves":31,"pct":23.8},\
        "putting":{"averagePutts":1.9,"holesWithPutts":180}}}}
        """
        var tenState = analysisState
        let tenRequest = tenState.select("last10")
        tenState.complete(tenRequest, stats: try JSONDecoder().decode(MobileStats.self, from: Data(tenJSON.utf8)))
        for (name, state) in [("results-analysis", analysisState), ("results-analysis-10", tenState)] {
            try captureScreen(
                NavigationStack {
                    ScrollView {
                        AnalysisPageContent(window: .constant(state.window), state: state)
                    }
                    .background(Color.white)
                    .navigationTitle("表现分析")
                },
                named: name
            )
        }
        // B5b 球场详情 (stats.html 6): average + best, one dot per round (best green), the three
        // hardest holes of this course's own loops, the most played combinations with the rest folded,
        // then 所有比赛. No server in snapshots, so the topo cards show their ground colour.
        let courseJSON = """
        {"courseKey":"bk","courseName":"北京天竺黑骑士","roundCount":12,"average18":86.9,"bestScore":78,\
        "loopKeys":["gid:7:1-9","gid:7:10-18","gid:8:1-9"],"nineOnlyRounds":3,\
        "rounds":[{"roundId":"c-12","date":"2026-09-21","score":85,"toPar":13,"holesCompleted":18,"nine":"B/C"},\
        {"roundId":"c-11","date":"2026-09-02","score":88,"toPar":16,"holesCompleted":18,"nine":"C/A"},\
        {"roundId":"c-10","date":"2026-08-15","score":44,"toPar":8,"holesCompleted":9,"nine":"A"},\
        {"roundId":"c-09","date":"2026-08-01","score":78,"toPar":6,"holesCompleted":18,"nine":"B/C"},\
        {"roundId":"c-08","date":"2026-07-12","score":91,"toPar":19,"holesCompleted":18,"nine":"A/B"},\
        {"roundId":"c-07","date":"2026-06-28","score":86,"toPar":14,"holesCompleted":18,"nine":"B/C"},\
        {"roundId":"c-06","date":"2026-06-01","score":89,"toPar":17,"holesCompleted":18,"nine":"C/A"},\
        {"roundId":"c-05","date":"2026-05-17","score":84,"toPar":12,"holesCompleted":18,"nine":"B/C"},\
        {"roundId":"c-04","date":"2026-05-02","score":92,"toPar":20,"holesCompleted":18,"nine":"A/B"},\
        {"roundId":"c-03","date":"2026-04-12","score":87,"toPar":15,"holesCompleted":18,"nine":"B/C"},\
        {"roundId":"c-02","date":"2026-03-30","score":90,"toPar":18,"holesCompleted":18,"nine":"C/B"},\
        {"roundId":"c-01","date":"2026-03-15","score":86,"toPar":14,"holesCompleted":18,"nine":"B/C"}]}
        """
        let courseScoringJSON = """
        {"loops":[{"loopKey":"gid:7:1-9","label":"北京天竺黑骑士 A","holes":[{"hole":4,"par":4,"averageToPar":0.88,"samples":5},{"hole":7,"par":3,"averageToPar":0.4,"samples":5}]},\
        {"loopKey":"gid:7:10-18","label":"北京天竺黑骑士 B","holes":[{"hole":13,"par":4,"averageToPar":1.12,"samples":8},{"hole":16,"par":5,"averageToPar":0.6,"samples":8}]},\
        {"loopKey":"gid:8:1-9","label":"北京天竺黑骑士 C","holes":[{"hole":6,"par":4,"averageToPar":0.95,"samples":9}]}],\
        "nineCombos":[{"frontKey":"gid:7:10-18","backKey":"gid:8:1-9","front":"北京天竺黑骑士 B","back":"北京天竺黑骑士 C","rounds":6,"average":85.8},\
        {"frontKey":"gid:8:1-9","backKey":"gid:7:1-9","front":"北京天竺黑骑士 C","back":"北京天竺黑骑士 A","rounds":2,"average":88.5},\
        {"frontKey":"gid:7:1-9","backKey":"gid:7:10-18","front":"北京天竺黑骑士 A","back":"北京天竺黑骑士 B","rounds":2,"average":91.5},\
        {"frontKey":"gid:8:1-9","backKey":"gid:7:10-18","front":"北京天竺黑骑士 C","back":"北京天竺黑骑士 B","rounds":1,"average":90.0}]}
        """
        let course = try JSONDecoder().decode(StatsCourse.self, from: Data(courseJSON.utf8))
        let courseScoring = try JSONDecoder().decode(StatsScoring.self, from: Data(courseScoringJSON.utf8))
        XCTAssertEqual(ResultsCoursePresentation.hardestHoles(course, loops: courseScoring.loops).map(\.overPar), ["+1.12", "+0.95", "+0.88"])
        XCTAssertEqual(ResultsCoursePresentation.combos(course, combos: courseScoring.nineCombos).count, 4)
        // The topo backdrop (hole 1 of loop gid:7) and each hard hole's map come from local topo
        // files, as the server renders them; a distinct ground per hole tells the cards apart.
        let topoDir = FileManager.default.temporaryDirectory.appendingPathComponent("course-detail-topo", isDirectory: true)
        try FileManager.default.createDirectory(at: topoDir, withIntermediateDirectories: true)
        let grounds: [UIColor?] = [nil, UIColor(red: 0.80, green: 0.88, blue: 0.74, alpha: 1),
                                   UIColor(red: 0.74, green: 0.84, blue: 0.70, alpha: 1)]
        var topoFiles: [String: URL] = [:]
        for (index, ref) in [(7, 1), (7, 13), (8, 6), (7, 4)].enumerated() {
            let file = topoDir.appendingPathComponent("\(ref.0)-\(ref.1).png")
            let image = Self.courseImage(ground: grounds[index % grounds.count], noisyRough: false)
            try XCTUnwrap(image.pngData()).write(to: file, options: [.atomic])
            // Decoded up front so the first rendered frame already draws each map (no loader race).
            TopoHoleImageStore.preload(image, for: file)
            topoFiles["\(ref.0)-\(ref.1)"] = file
        }
        for file in topoFiles.values {
            XCTAssertNotNil(TopoHoleImageStore.cachedImage(for: file), "every topo is ready before capture")
        }
        XCTAssertEqual(ResultsCoursePresentation.backdrop(course), ResultsCoursePresentation.HoleRef(globalId: 7, localHole: 1))
        let courseView = CourseStatsDetailView(
            course: course,
            scoring: courseScoring,
            topoURL: { ref in topoFiles["\(ref.globalId)-\(ref.localHole)"] }
        )
        try captureScreen(NavigationStack { courseView }, named: "course-detail", settle: 2.0)
        // Degradation: a course without any topo keeps the ground-coloured cards and no backdrop.
        try captureScreen(
            NavigationStack { CourseStatsDetailView(course: course, scoring: courseScoring) },
            named: "course-detail-no-topo"
        )

        // B5b 时间与频率 (stats.html 4): the grain picker on 季, the chart, quarter cards, then the
        // calendar with its 场数 / 月均 / 最活跃月 line.
        let timeJSON = """
        {"trend":{"points":[]},"time":{\
        "byYear":[{"key":"2026","roundCount":32,"average18":88.6,"bestScore":78,"worstScore":99,"outcomes":{"birdie":30,"doubleOrWorse":96}},\
        {"key":"2025","roundCount":41,"average18":91.2,"bestScore":82,"worstScore":104,"outcomes":{"birdie":28,"doubleOrWorse":160}}],\
        "byQuarter":[{"key":"2026-Q3","roundCount":9,"average18":87.1,"bestScore":78,"worstScore":95,"outcomes":{"birdie":10,"doubleOrWorse":22}},\
        {"key":"2026-Q2","roundCount":14,"average18":88.4,"bestScore":82,"worstScore":96,"outcomes":{"birdie":13,"doubleOrWorse":41}},\
        {"key":"2026-Q1","roundCount":9,"average18":90.6,"bestScore":84,"worstScore":99,"outcomes":{"birdie":7,"doubleOrWorse":33}},\
        {"key":"2025-Q4","roundCount":10,"average18":91.8,"bestScore":85,"worstScore":101,"outcomes":{"birdie":6,"doubleOrWorse":41}},\
        {"key":"2025-Q3","roundCount":12,"average18":90.2,"bestScore":82,"worstScore":98,"outcomes":{"birdie":9,"doubleOrWorse":44}}],\
        "byMonth":[],\
        "byDay":[{"key":"2026-01-11","roundCount":1},{"key":"2026-02-08","roundCount":1},{"key":"2026-02-22","roundCount":1},\
        {"key":"2026-03-07","roundCount":2},{"key":"2026-03-28","roundCount":1},{"key":"2026-04-04","roundCount":1},{"key":"2026-04-18","roundCount":2},\
        {"key":"2026-05-02","roundCount":1},{"key":"2026-05-09","roundCount":2},{"key":"2026-05-16","roundCount":1},{"key":"2026-05-23","roundCount":2},\
        {"key":"2026-05-30","roundCount":1},{"key":"2026-06-13","roundCount":2},{"key":"2026-06-27","roundCount":2},{"key":"2026-07-11","roundCount":3},\
        {"key":"2026-08-08","roundCount":2},{"key":"2026-08-22","roundCount":2},{"key":"2026-09-05","roundCount":2},{"key":"2026-09-20","roundCount":3}]}}
        """
        let timeStats = try JSONDecoder().decode(MobileStats.self, from: Data(timeJSON.utf8))
        XCTAssertEqual(ResultsTimePresentation.calendarSummary(timeStats.time)?.text, "32 场 · 月均 3.6 · 5 月最多")
        try captureScreen(
            NavigationStack {
                ScrollView {
                    ResultsTimeContent(stats: timeStats, grain: .constant(.quarter))
                }
                .background(HubStyle.grouped)
                .navigationTitle("时间与频率")
            },
            named: "results-time"
        )
        // The same page scrolled to its end: the play calendar with 场数 · 月均 · 最活跃月.
        try captureScreen(
            NavigationStack {
                ScrollView {
                    ResultsTimeContent(stats: timeStats, grain: .constant(.quarter))
                }
                .defaultScrollAnchor(.bottom)
                .background(HubStyle.grouped)
                .navigationTitle("时间与频率")
            },
            named: "results-time-calendar"
        )

        // B5c 球包 (stats.html 3): the bag's distance ladder long to short — p10–p90 bars, the median
        // line (a typed distance is a dot), 差 N 码 between clubs with < 8 / > 20 flagged, and a club
        // without shots last. Same club + distance data the bag screen loads; captured light.
        let bagProfiles = [
            ClubProfile(clubName: "Driver", sampleSize: 86, medianM: 211, p10M: 187, p90M: 227),
            ClubProfile(clubName: "3W", sampleSize: 41, medianM: 192, p10M: 172, p90M: 206),
            ClubProfile(clubName: "3H", sampleSize: 18, medianM: 166, p10M: 151, p90M: 178),
            ClubProfile(clubName: "5I", sampleSize: 35, medianM: 155, p10M: 139, p90M: 166),
            ClubProfile(clubName: "6I", sampleSize: 44, medianM: 146, p10M: 133, p90M: 156),
            ClubProfile(clubName: "7I", sampleSize: 58, medianM: 137, p10M: 124, p90M: 146),
            ClubProfile(clubName: "8I", sampleSize: 51, medianM: 128, p10M: 116, p90M: 136),
            ClubProfile(clubName: "9I", sampleSize: 47, medianM: 117, p10M: 105, p90M: 125),
            ClubProfile(clubName: "PW", sampleSize: 39, medianM: 105, p10M: 93, p90M: 113),
            ClubProfile(clubName: "Aw", sampleSize: 20, medianM: 91, p10M: 80, p90M: 99),
            ClubProfile(clubName: "54", sampleSize: 26, medianM: 78, p10M: 64, p90M: 87),
        ]
        // The owner's actual 14-club bag resolved from Garmin (clubTypeId map + custom 50/54/58 wedges).
        let bag: Set<String> = [
            "一号木", "三号木", "三号小鸡腿", "五号铁", "六号铁", "七号铁", "八号铁", "九号铁",
            "P 杆", "A 杆", "50° 挖起杆", "54° 挖起杆", "58° 挖起杆", "推杆",
        ]
        let bagRows = BagPresentation.rows(bag: bag, profiles: bagProfiles, manual: ["七号铁": 152])
        XCTAssertEqual(bagRows.count, 13, "the putter is not on the ladder")
        XCTAssertEqual(bagRows.suffix(2).map(\.name), ["50° 挖起杆", "58° 挖起杆"], "clubs without shots last")
        // The REAL 球包 destination (toolbar ＋ 球杆, reset row) and its real sheets, with the bag in an
        // isolated store and a sync coordinator that has no backend, so nothing leaves the test.
        do {
            let bagSuiteName = "DesignSnapshotBag"
            UserDefaults().removePersistentDomain(forName: bagSuiteName)
            ClubBagStore.defaults = try XCTUnwrap(UserDefaults(suiteName: bagSuiteName))
            defer {
                ClubBagStore.defaults = .standard
                UserDefaults().removePersistentDomain(forName: bagSuiteName)
            }
            ClubBagStore.saveRealBag(bag)
            ClubBagStore.save(bag)
            ClubBagStore.saveManualDistancesYd(["七号铁": 152])
            let bagSync = ClubBagSyncCoordinator(sleep: { _ in })
            func bagScreen(editing: String? = nil, adding: Bool = false) -> AnyView {
                AnyView(NavigationStack {
                    ClubSettingsView(
                        clubProfiles: bagProfiles, apiBaseURL: nil, adminToken: nil, sync: bagSync,
                        editing: editing, adding: adding, fetchesRealBag: false
                    )
                })
            }
            try captureScreen(bagScreen(), named: "bag")
            try captureScreen(bagScreen(editing: "七号铁"), named: "bag-edit", expectsPresentation: true)
            try captureScreen(bagScreen(adding: true), named: "bag-add", expectsPresentation: true)

            // A reinstall / second phone while the player's cloud bag is still being read: the
            // same ladder, read-only (no ＋ 球杆, no reset, rows do not open the editor) and no
            // process text on the screen — that lives in 设置 → 球包同步.
            let restoringSync = ClubBagSyncCoordinator(sleep: { _ in })
            restoringSync.activate(playerId: "p_snapshot", migrateLegacy: false)
            ClubBagStore.saveRealBag(bag)
            restoringSync.configure(sender: { _, _ in }, fetcher: { _ in
                try await Task.sleep(nanoseconds: 3_600_000_000_000)
                throw CancellationError()
            })
            let restore = Task { await restoringSync.restoreFromServer() }
            defer {
                restore.cancel()
                restoringSync.activate(playerId: nil, migrateLegacy: false)
            }
            while restoringSync.restoreState != .restoring { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.01)) }
            XCTAssertFalse(restoringSync.canEdit)
            try captureScreen(
                NavigationStack {
                    ClubSettingsView(
                        clubProfiles: bagProfiles, apiBaseURL: nil, adminToken: nil, sync: restoringSync,
                        fetchesRealBag: false
                    )
                },
                named: "bag-restoring"
            )
            try captureScreen(
                NavigationStack {
                    List { Section("账号与球包") { ClubBagSyncSettingsRow(sync: restoringSync) } }
                        .navigationTitle("设置")
                        .navigationBarTitleDisplayMode(.inline)
                },
                named: "settings-bag-sync"
            )

            // The first cloud read failed on a phone that never had this player's bag: 球包 stays
            // view-only with its 重新读取 action; 设置 says what happened and offers the retry.
            let failedSync = ClubBagSyncCoordinator(sleep: { _ in })
            failedSync.activate(playerId: "p_snapshot_failed", migrateLegacy: false)
            ClubBagStore.saveRealBag(bag)
            failedSync.configure(sender: { _, _ in }, fetcher: { _ in throw URLError(.notConnectedToInternet) })
            let failedRestore = Task { await failedSync.restoreFromServer() }
            while failedSync.restoreState != .failed { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.01)) }
            _ = failedRestore
            XCTAssertFalse(failedSync.canEdit)
            try captureScreen(
                NavigationStack {
                    ClubSettingsView(
                        clubProfiles: bagProfiles, apiBaseURL: nil, adminToken: nil, sync: failedSync,
                        fetchesRealBag: false
                    )
                },
                named: "bag-restore-failed"
            )
            try captureScreen(
                NavigationStack {
                    List { Section("账号与球包") { ClubBagSyncSettingsRow(sync: failedSync) } }
                        .navigationTitle("设置")
                        .navigationBarTitleDisplayMode(.inline)
                },
                named: "settings-bag-sync-failed"
            )
            failedSync.activate(playerId: nil, migrateLegacy: false)
        }

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

    /// Card 454: Garmin's 1242×1920 fallback and a current-position marker share the same raster
    /// projection while the precise CourseView image is still pending.
    @MainActor
    func testCaptureGarminRasterWithPosition() throws {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(
            LiveRoundPackage.self,
            from: Data(contentsOf: fixtureURL)
        )
        let firstHole = try XCTUnwrap(package.holes.first)
        let prepJSON = #"{"hole":\#(firstHole.number),"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":300,"geometryCoverage":"partial","geometryRevision":"snapshot-r1","route":[[120,330],[120,30]],"steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},"map":{"overlay":{"w":240,"h":360,"ppm":1,"ln":300,"route":[[120,330,0],[120,30,300]]}},"holeImageProjection":{"available":true,"widthPx":240,"heightPx":360,"refs":[{"lat":40.0,"lon":116.0,"px":120,"py":330},{"lat":40.0,"lon":116.001,"px":120,"py":30},{"lat":40.001,"lon":116.0,"px":240,"py":330}]}}"#
        let prepHole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(prepJSON.utf8))
        let mappedPackage = package.replacingCoursePrep(
            CoursePrepPackage(
                schema: "ai-caddie-course-prep-v1",
                globalId: package.course.globalId,
                holes: [prepHole],
                missingData: nil
            )
        )
        let size = CGSize(width: 1242, height: 1920)
        let image = UIGraphicsImageRenderer(size: size).image { context in
            UIColor(red: 0.16, green: 0.35, blue: 0.19, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
            UIColor(red: 0.28, green: 0.53, blue: 0.30, alpha: 1).setFill()
            context.cgContext.fill(CGRect(x: 270, y: 0, width: 360, height: 1920))
            UIColor(red: 0.58, green: 0.72, blue: 0.35, alpha: 1).setFill()
            context.cgContext.fillEllipse(in: CGRect(x: 430, y: 120, width: 380, height: 260))
        }
        let baseURL = URL(string: "https://caddie.example")!
        let rasterProjection = CoursePrepHoleImageProjection(
            available: true,
            widthPx: 1242,
            heightPx: 1920,
            refs: [
                CoursePrepProjectionRef(lat: 40, lon: 116, px: 80, py: 140),
                CoursePrepProjectionRef(lat: 40, lon: 116.001, px: 80, py: 1740),
                CoursePrepProjectionRef(lat: 40.001, lon: 116, px: 700, py: 140),
            ]
        )
        let descriptor = GarminRasterResponse(
            available: true,
            imageUrl: "/api/v2/courses/\(firstHole.sourceGlobalId)/holes/\(firstHole.sourceLocalHole)/garmin-raster.jpg?v=snapshot-454",
            projection: GarminRasterProjection(widthPx: 1242, heightPx: 1920, refs: rasterProjection.refs ?? []),
            mode: "H"
        )
        let rasterURL = try XCTUnwrap(descriptor.resolvedImageURL(relativeTo: baseURL))
        GarminRasterImageStore.preload(image, for: rasterURL)
        let state = CurrentHoleView.SnapshotState(
            garminRaster: descriptor,
            currentCoordinate: CLLocationCoordinate2D(latitude: 40.0005, longitude: 116.0005)
        )
        try captureScreen(
            NavigationStack {
                CurrentHoleView(
                    package: mappedPackage,
                    hole: firstHole,
                    snapshotState: state,
                    caddieBaseURL: baseURL
                )
            },
            named: "live-garmin-raster-position",
            dark: true
        )
    }

    /// Card 454: when neither raster is available the same space contains only numeric facts and
    /// the explicit “正在下载” status.
    @MainActor
    func testCaptureLiveNumericMapPlaceholder() throws {
        try captureScreen(
            LiveMapNumericPlaceholder(
                holeNumber: 7,
                par: 4,
                yards: 410,
                frontYards: 142,
                middleYards: 151,
                backYards: 160
            )
            .frame(width: 390, height: 600),
            named: "live-numeric-placeholder",
            dark: true
        )
    }

    /// C88: while Garmin's raster loads, the frame is the hole screen's own black ground
    /// (`LivePlayStyle.base`) carrying the hole's number and yards. Formerly this standard snapshot
    /// was the dark-green ground (26, 46, 30) with only a corner spinner, and asserted nothing.
    @MainActor
    func testCaptureGarminRasterLoading() throws {
        // A reserved .test host never answers, so the capture stays on the loading frame.
        let url = URL(string: "https://garmin-loading.example.test/api/v2/courses/1/holes/1/garmin-raster.webp?v=asset-loading-sky1")!
        let png = try captureScreen(
            GarminRasterStandaloneView(
                url: url,
                onReady: nil,
                onFailed: nil,
                onVersionConflict: nil,
                placeholder: LiveMapNumericPlaceholder(
                    holeNumber: 6,
                    par: 4,
                    yards: 402,
                    frontYards: nil,
                    middleYards: nil,
                    backYards: nil
                )
            )
            .frame(width: 390, height: 600)
            .background(LivePlayStyle.base),
            named: "live-garmin-raster-loading",
            dark: true
        )
        let pixels = try Self.screenPixels(png)
        // The 390×600 frame is centred in the 844-pt screen (y 122…722). This ground point lies inside
        // the raster's frame, clear of the centred facts and the top-trailing spinner.
        let ground = pixels.rgb(at: CGPoint(x: 40, y: 200))
        XCTAssertLessThanOrEqual(
            abs(ground[0] - 5) + abs(ground[1] - 7) + abs(ground[2] - 12), 6,
            "loading ground \(ground) must be LivePlayStyle.base #05070c, not the green 26/46/30"
        )
        // The placeholder's white figures sit in the middle of the frame (the spinner is not there).
        var brightPixels = 0
        for y in stride(from: 300, to: 560, by: 1) {
            for x in stride(from: 40, to: 350, by: 1) {
                let rgb = pixels.rgb(at: CGPoint(x: x, y: y))
                if rgb.allSatisfy({ $0 > 200 }) { brightPixels += 1 }
            }
        }
        XCTAssertGreaterThan(brightPixels, 50, "the loading frame shows the hole's number and yards")
    }

    private struct ScreenPixels {
        let width: Int
        let scale: CGFloat
        let bytes: [UInt8]

        /// The 0-255 RGB at a point in the 390-pt screen's coordinates.
        func rgb(at point: CGPoint) -> [Int] {
            let index = (Int(point.y * scale) * width + Int(point.x * scale)) * 4
            return [Int(bytes[index]), Int(bytes[index + 1]), Int(bytes[index + 2])]
        }
    }

    private static func screenPixels(_ png: Data) throws -> ScreenPixels {
        let cgImage = try XCTUnwrap(UIImage(data: png)?.cgImage)
        let width = cgImage.width
        let height = cgImage.height
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: width, height: height, bitsPerComponent: 8,
                bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        XCTAssertTrue(drawn)
        return ScreenPixels(width: width, scale: CGFloat(width) / 390, bytes: bytes)
    }

    /// A production-shaped 256 x 256 hole raster: an irregular rough footprint with a fairway from
    /// the tee (48, 48) to a green at (208, 208), on `ground` (the flat render) or a transparent
    /// off-course canvas (topo-v12) when nil. Like production it keeps a margin on every side, so
    /// no course pixel touches the raster's edge; `reachesEdge` instead runs the course out to the
    /// corners (the hard-clipped shape the clipping detector must catch). `noisyRough` makes the
    /// rough vivid 4 px noise.
    static func courseImage(ground: UIColor?, noisyRough: Bool, reachesEdge: Bool = false) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        format.preferredRange = .standard
        var seed: UInt32 = 20_260_930
        func noise() -> CGFloat {
            seed = seed &* 1_664_525 &+ 1_013_904_223
            return CGFloat(seed >> 24) / 255
        }
        let start = reachesEdge ? CGPoint(x: -40, y: -40) : CGPoint(x: 48, y: 48)
        let end = reachesEdge ? CGPoint(x: 296, y: 296) : CGPoint(x: 208, y: 208)
        return UIGraphicsImageRenderer(size: CGSize(width: 256, height: 256), format: format).image { ctx in
            if let ground {
                ground.setFill()
                ctx.fill(CGRect(x: 0, y: 0, width: 256, height: 256))
            }
            for row in 0..<64 {
                for column in 0..<64 {
                    let centre = CGPoint(x: CGFloat(column) * 4 + 2, y: CGFloat(row) * 4 + 2)
                    let along = ((centre.x - start.x) + (centre.y - start.y)) / (2 * (end.x - start.x))
                    let t = max(0, min(1, along))
                    let nearest = CGPoint(x: start.x + t * (end.x - start.x), y: start.y + t * (end.y - start.y))
                    // The rough's edge wanders along the hole.
                    let radius = 24 + 6 * sin(t * 9) + 3.5 * sin(t * 23 + 1)
                    guard hypot(centre.x - nearest.x, centre.y - nearest.y) <= radius else { continue }
                    if noisyRough {
                        UIColor(red: noise(), green: noise(), blue: noise(), alpha: 1).setFill()
                    } else {
                        UIColor(red: 96 / 255, green: 140 / 255, blue: 86 / 255, alpha: 1).setFill()
                    }
                    ctx.fill(CGRect(x: column * 4, y: row * 4, width: 4, height: 4))
                }
            }
            let fairway = UIBezierPath()
            fairway.move(to: CGPoint(x: start.x + 8, y: start.y + 8))
            fairway.addLine(to: CGPoint(x: end.x - 22, y: end.y - 22))
            fairway.lineWidth = 22
            fairway.lineCapStyle = .round
            UIColor(red: 0.60, green: 0.78, blue: 0.45, alpha: 1).setStroke()
            fairway.stroke()
            UIColor(red: 0.50, green: 0.80, blue: 0.43, alpha: 1).setFill()
            ctx.cgContext.fillEllipse(in: CGRect(x: end.x - 20, y: end.y - 20, width: 40, height: 40))
        }
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
    func testTheHomeGreetingFollowsTheHourAndSnapshotsUseAFixedMorning() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        func at(_ hour: Int) -> Date {
            calendar.date(from: DateComponents(year: 2026, month: 9, day: 25, hour: hour))!
        }
        XCTAssertEqual(RoundHomeView.greeting(at: at(9), calendar: calendar), "早上好")
        XCTAssertEqual(RoundHomeView.greeting(at: at(12), calendar: calendar), "中午好")
        XCTAssertEqual(RoundHomeView.greeting(at: at(15), calendar: calendar), "下午好")
        XCTAssertEqual(RoundHomeView.greeting(at: at(21), calendar: calendar), "晚上好")
        XCTAssertEqual(RoundHomeView.greeting(at: Self.snapshotMorning), "早上好")
    }

    /// 09:00 local time on a fixed day, whatever the runner's time zone.
    static let snapshotMorning: Date = {
        var components = DateComponents()
        components.year = 2026
        components.month = 9
        components.day = 25
        components.hour = 9
        return Calendar.current.date(from: components) ?? Date(timeIntervalSince1970: 0)
    }()

    private func captureScreen(
        _ view: some View,
        named name: String,
        dark: Bool = false,
        settle: TimeInterval = 1.0,
        expectsPresentation: Bool = false
    ) throws -> Data {
        let size = CGSize(width: 390, height: 844)
        let style: UIUserInterfaceStyle = dark ? .dark : .light
        // A fixed morning, so the home greeting (早上好 …) never depends on when CI ran.
        let host = UIHostingController(rootView: view.environment(\.homeGreetingDate, Self.snapshotMorning))
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
        if expectsPresentation {
            // The capture must contain the screen's own sheet, not a standalone copy of its content.
            XCTAssertNotNil(host.presentedViewController, "\(name) presents the real sheet")
        }
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
