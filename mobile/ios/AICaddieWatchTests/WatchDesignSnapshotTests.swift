import CoreLocation
import ImageIO
import SwiftUI
import XCTest
@testable import AICaddieWatch

/// round-12 P3 (Watch standalone): render watch SwiftUI surfaces to PNGs in the watchOS SIMULATOR so
/// the UI can be reviewed from CI without a physical Apple Watch — the same idea as the iOS
/// DesignSnapshotTests. The native-mobile and focused watch-runtime workflows collect
/// `Documents/watch-snapshots/*.png` after the Watch test. (Only real GPS / HealthKit / motion need a
/// physical watch — the UI/scoring layout is fully reviewable here.)
final class WatchDesignSnapshotTests: XCTestCase {
    func testWatchClubDisplayNamesMatchApprovedChineseCopy() {
        XCTAssertEqual(WatchClubDisplay.name("1W"), "一号木")
        XCTAssertEqual(WatchClubDisplay.name("3W"), "三号木")
        XCTAssertEqual(WatchClubDisplay.name("9I"), "九号铁")
        XCTAssertEqual(WatchClubDisplay.name("PW"), "P 杆")
        XCTAssertEqual(WatchClubDisplay.name("putter"), "推杆")
        XCTAssertEqual(WatchClubDisplay.name("自定义杆"), "自定义杆")
    }

    @MainActor
    func testRenderAutoShotCandidateConfirmation() throws {
        let view = WatchAutoShotCandidateView()
            .frame(width: 198, height: 242)
            .background(Color.black)
        try render(view, named: "watch-autoshot-candidate")
    }

    func testCaddieGlancePrefersLiveWatchGreenDistances() {
        let state = WatchRoundState(
            roundId: "r1", hole: 4, par: 5, distanceM: 480,
            selectedClub: nil,
            frontGreenM: 200, centerGreenM: 210, backGreenM: 220,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )

        let view = WatchCaddieGlanceView(
            state: state,
            frontYd: 201,
            centerYd: 211,
            backYd: 221
        )

        XCTAssertEqual(view.displayFrontYd, 201)
        XCTAssertEqual(view.displayCenterYd, 211)
        XCTAssertEqual(view.displayBackYd, 221)
    }

    func testCaddieGlanceDoesNotInventMissingTargetActionForPreparedCourseData() {
        let state = WatchRoundState(
            roundId: "r1", hole: 4, par: 5, distanceM: 480,
            suggestedClub: "3号木", selectedClub: nil,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )

        XCTAssertFalse(WatchCaddieGlanceView(state: state).showsTargetStatus)
    }

    @MainActor
    func testRenderWatchCaddieGlance() throws {
        let state = WatchRoundState(
            roundId: "r1", hole: 7, par: 4, distanceM: 139,
            targetNote: "右沙坑 138–150 码,避开",
            targetLatitude: 22.28, targetLongitude: 114.16, targetKind: "pin",
            suggestedClub: "7号铁", selectedClub: "7号铁",
            availableClubs: [WatchClubOption(clubName: "7号铁", medianM: 139), WatchClubOption(clubName: "6号铁", medianM: 150)],
            shotType: "approach", strategyMode: "stock", lie: "fairway",
            nextShotPrompt: "上果岭中心偏左", holePlanSummary: "3W → 8I · 上果岭",
            expectedRemainingM: 8,
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
        // The Hole Root already shows the current-shot call. Opening it must make the complete
        // 稳妥/标准/进攻 plans primary instead of repeating another full screen of single-shot facts.
        let state = WatchRoundState(
            roundId: "r1", hole: 4, par: 5, distanceM: 262,
            suggestedClub: "3号木", selectedClub: nil,
            offlineOptionId: "stock",
            caddieOptions: [
                WatchCaddieOption(optionId: "safe", label: "稳妥", clubName: "9号铁", carryM: 128, plan: [WatchCaddiePlanStep(clubName: "3W", carryM: 172), WatchCaddiePlanStep(clubName: "9I", carryM: 128)], confidence: "high"),
                WatchCaddieOption(optionId: "stock", label: "标准", clubName: "8号铁", carryM: 142, plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 192), WatchCaddiePlanStep(clubName: "8I", carryM: 142)], confidence: "high"),
                WatchCaddieOption(optionId: "attack", label: "进攻", clubName: "7号铁", carryM: 156, plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 192), WatchCaddiePlanStep(clubName: "PW", carryM: 118)], confidence: "medium"),
            ],
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high"
        )
        let screen = WatchCaddieScreen(state: state)
        XCTAssertTrue(screen.showsPlanOptionsFirst)

        // ImageRenderer does not materialize ScrollView contents on watchOS. Render the exact primary
        // content used by WatchCaddieScreen; the assertion above separately locks the production order.
        let view = WatchCaddieOptionsView(
            options: state.caddieOptions,
            recommendedId: state.offlineOptionId,
            onBack: {}
        )
        .padding(8)
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-caddie-options")
    }

    @MainActor
    func testRenderWatchHazards() throws {
        // Both sand and water use the locked S70-facing 到/过 front/back semantics.
        let view = WatchHazardView(
            hazards: [
                WatchHazard(
                    kind: "bunker", label: "沙坑 1", startM: 116, endM: 132,
                    frontDistanceM: 120, backDistanceM: 136
                ),
                WatchHazard(
                    kind: "bunker", label: "沙坑 2", startM: 160, endM: 178,
                    frontDistanceM: 165, backDistanceM: 183
                ),
                WatchHazard(
                    kind: "water", label: "水域", startM: 210, endM: 235,
                    frontDistanceM: 210, backDistanceM: 235
                ),
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
            ringPips: pips,
            canRecordShot: true
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
    func testRenderWatchCurrentHoleShots() throws {
        let shots = [
            WatchRecordedShot(
                eventId: "shot-1", hole: 7, number: 1, clubName: "一号木", shotType: "tee",
                location: WatchShotLocationValue(latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 4)!,
                capturedAt: "2026-07-26T08:00:00Z", distanceToNextM: 224
            ),
            WatchRecordedShot(
                eventId: "shot-2", hole: 7, number: 2, clubName: "七号铁", shotType: "approach",
                location: WatchShotLocationValue(latitude: 40.001, longitude: 116.0, horizontalAccuracyM: 4)!,
                capturedAt: "2026-07-26T08:05:00Z", distanceToNextM: 139
            ),
            WatchRecordedShot(
                eventId: "shot-3", hole: 7, number: 3, clubName: nil, shotType: "recovery",
                location: WatchShotLocationValue(latitude: 40.002, longitude: 116.0, horizontalAccuracyM: 4)!,
                capturedAt: "2026-07-26T08:10:00Z", distanceToNextM: nil
            ),
        ]
        let view = WatchCurrentHoleShotsView(
            hole: 7,
            par: 4,
            shots: shots,
            latestShotDistanceM: 38,
            canAddShot: true
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-current-hole-shots")
    }

    @MainActor
    func testRenderWatchMenu() throws {
        let view = WatchMenuView(hasCaddie: true, hasHazards: true)
            .frame(width: 198)
            .background(Color.black)
        try render(view, named: "watch-menu")
    }

    @MainActor
    func testRenderWatchScoreHole() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-score-hole")
    }

    @MainActor
    func testManualScoreStepLabelsFollowTheConfirmedParFlow() {
        XCTAssertEqual(
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                step: .score
            ).stepLabel,
            "1/4 · 总杆"
        )
        XCTAssertEqual(
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                step: .putts
            ).stepLabel,
            "2/4 · 推杆"
        )
        XCTAssertEqual(
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                step: .fairway
            ).stepLabel,
            "3/4 · 开球结果"
        )
        XCTAssertEqual(
            WatchScoreHoleView(
                hole: 7, par: 3, score: 3, putts: 2, penalty: 0,
                step: .penalty
            ).stepLabel,
            "3/3 · 罚杆"
        )
    }

    @MainActor
    func testRenderWatchScoreTotalStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            step: .score
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-score-total")
    }

    @MainActor
    func testRenderWatchScorePuttsStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            step: .putts
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-score-putts")
    }

    @MainActor
    func testRenderWatchScoreFairwayStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            step: .fairway
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-score-fairway")
    }

    @MainActor
    func testRenderWatchScorePenaltyStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            step: .penalty
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-score-penalty")
    }

    @MainActor
    func testRenderWatchScoreWithNextTeeCandidate() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            candidateNextHole: 8
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-score-next-tee-candidate")
    }

    @MainActor
    func testClubPromptKeepsMeasuredCarryWhenRecommendationMovesFirst() {
        let choices = WatchClubPromptPresentation.choices(
            recommendedClub: "7号铁",
            clubs: [
                WatchClubOption(clubName: "6号铁", medianM: 150),
                WatchClubOption(clubName: "7号铁", medianM: 139),
            ]
        )

        XCTAssertEqual(choices.map(\.clubName), ["7号铁", "6号铁"])
        XCTAssertEqual(WatchClubPromptPresentation.distanceText(for: choices[0]), "152")
    }

    @MainActor
    func testClubPromptKeepsFourApprovedClubChoicesOnTheFirst45mmScreen() {
        XCTAssertGreaterThanOrEqual(
            WatchClubPromptLayout.firstScreenClubRows(viewportHeight: 160),
            4
        )
    }

    @MainActor
    func testRenderWatchClubPrompt() throws {
        let view = WatchClubPromptView(
            hole: 8,
            shotNumber: 1,
            recommendedClub: "一号木",
            clubs: [
                WatchClubOption(clubName: "一号木", medianM: 201),
                WatchClubOption(clubName: "三号木", medianM: 183),
                WatchClubOption(clubName: "5号铁", medianM: 165),
                WatchClubOption(clubName: "7号铁", medianM: 139),
            ]
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-club-prompt")
    }

    @MainActor
    func testFinishSummaryUsesTheApprovedCompactFactsAndActions() {
        let view = WatchFinishRoundView(
            courseName: "北京丽宫 · 前九",
            holesPlayed: 9, holeCount: 9,
            totalStrokes: 41, toPar: 5, totalPutts: 16,
            fairwaySummary: WatchOutcomeSummary(hits: 5, recorded: 7),
            girSummary: WatchOutcomeSummary(hits: 4, recorded: 9),
            pendingUploads: 2
        )

        XCTAssertEqual(view.scoreText, "+5")
        XCTAssertEqual(view.totalStrokesText, "41 杆")
        XCTAssertEqual(view.holesText, "9/9 洞")
        XCTAssertEqual(view.puttsText, "推杆 16")
        XCTAssertEqual(view.pendingUploadText, "稍后同步 2")
        XCTAssertEqual(view.primaryActionLabel, "保存并结束")
        XCTAssertEqual(view.secondaryActionLabel, "继续打球")
    }

    @MainActor
    func testRenderWatchFinishRound() throws {
        let view = WatchFinishRoundView(
            courseName: "北京丽宫 · 前九",
            holesPlayed: 9, holeCount: 9,
            totalStrokes: 41, toPar: 5, totalPutts: 16,
            fairwaySummary: WatchOutcomeSummary(hits: 5, recorded: 7),
            girSummary: WatchOutcomeSummary(hits: 4, recorded: 9),
            pendingUploads: 2
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-finish-round")
    }

    @MainActor
    func testFinishConfirmationUsesTheApprovedQuestionAndSummary() {
        let view = WatchFinishConfirmationView(
            holesPlayed: 9,
            toPar: 5,
            pendingUploads: 2
        )

        XCTAssertEqual(view.titleText, "结束本场?")
        XCTAssertEqual(view.summaryText, "9 洞 · +5 · 保存并上传")
        XCTAssertEqual(view.cancelLabel, "返回")
        XCTAssertEqual(view.confirmLabel, "确认")
    }

    @MainActor
    func testRenderWatchFinishConfirmation() throws {
        let view = WatchFinishConfirmationView(
            holesPlayed: 9,
            toPar: 5,
            pendingUploads: 2
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-finish-confirmation")
    }

    @MainActor
    func testCoursePickerPresentationKeepsNearbyDistanceAndOfflineStatus() {
        let nearby = WatchCourseOption(
            globalId: 101,
            name: "附近球场",
            holes: 18,
            teeBox: "Blue",
            latitude: 40.0,
            longitude: 116.0
        )
        let known = WatchCourseOption(
            globalId: 202,
            name: "远方球场",
            holes: 18,
            teeBox: "White",
            latitude: 31.2,
            longitude: 121.5
        )
        let view = WatchStartView(
            phoneReachable: false,
            courses: [known, nearby],
            cachedCourseIds: [nearby.globalId],
            currentLatitude: 40.0,
            currentLongitude: 116.0
        )

        XCTAssertEqual(view.courseGroups.map(\.title), ["附近球场", "已知球场"])
        XCTAssertEqual(view.courseGroups[0].rows.map(\.course.globalId), [nearby.globalId])
        XCTAssertEqual(view.courseGroups[0].rows.first?.subtitle, "18 洞 · 0.0 km")
        XCTAssertEqual(view.courseGroups[0].rows.first?.isCached, true)
        XCTAssertEqual(view.courseGroups[1].rows.map(\.course.globalId), [known.globalId])
        XCTAssertEqual(view.courseGroups[1].rows.first?.subtitle, "18 洞 · White")
        XCTAssertEqual(view.courseGroups[1].rows.first?.isCached, false)
    }

    @MainActor
    func testCoursePickerHidesContradictoryEmptyKnownSectionWhenRemoteResultsExist() {
        let view = WatchStartView(
            phoneReachable: false,
            searchMatches: [
                WatchCourseSearchMatch(
                    globalId: 31870,
                    name: "Mission Hills ~ A",
                    holes: 9,
                    city: "深圳",
                    province: "广东",
                    ratio: 0.96
                )
            ]
        )

        XCTAssertTrue(view.courseGroups.isEmpty)
    }

    @MainActor
    func testRoundSetupPresentsPlayableLoopsInStableCompactOrder() {
        let front = WatchCourseOption(
            globalId: 301,
            name: "黑骑士 ~ A",
            holes: 9,
            teeBox: "Blue",
            venueName: "黑骑士",
            segmentLabel: "A",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        let backB = WatchCourseOption(
            globalId: 302,
            name: "黑骑士 ~ B",
            holes: 9,
            teeBox: "Blue",
            venueName: "黑骑士",
            segmentLabel: "B",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        let backC = WatchCourseOption(
            globalId: 303,
            name: "黑骑士 ~ C",
            holes: 9,
            teeBox: "Blue",
            venueName: "黑骑士",
            segmentLabel: "C",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        let view = WatchRoundSetupView(
            front: front,
            courses: [backC, front, backB],
            hasCachedVersion: true
        )

        XCTAssertEqual(view.loopChoices.map(\.title), ["只打 A", "A + B", "A + C"])
        XCTAssertEqual(view.loopChoices.map(\.detail), ["9 洞", "18 洞", "18 洞"])
        XCTAssertEqual(view.loopChoices.map(\.isSelected), [true, false, false])
        XCTAssertEqual(view.initialStage, .holes)
    }

    @MainActor
    func testRoundSetupKeepsRealTeeNameAndHonestYardage() {
        let front = WatchCourseOption(
            globalId: 301,
            name: "黑骑士 ~ A",
            holes: 9,
            teeBox: "Blue",
            venueName: "黑骑士",
            segmentLabel: "A",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        let view = WatchRoundSetupView(front: front, courses: [front])

        XCTAssertEqual(view.initialStage, .tees)
        XCTAssertEqual(view.teeChoices.map(\.title), ["蓝 T", "白 T"])
        XCTAssertEqual(view.teeChoices.map(\.detail), ["码数未知", "码数未知"])
        XCTAssertEqual(view.teeChoices.map(\.isSelected), [true, false])

        let downloaded = WatchCourseTee(
            teeBox: "blue",
            name: "Blue",
            geometrySet: 2,
            yards: 3210,
            holeCount: 9,
            isDefault: true
        )
        XCTAssertEqual(
            WatchRoundSetupView.teeChoice(for: downloaded, isSelected: true),
            WatchRoundSetupChoicePresentation(
                id: "tee:blue",
                title: "蓝 T",
                detail: "3210 码",
                isSelected: true
            )
        )
    }

    @MainActor
    func testRoundSetupExplainsCachedAndFirstDownloadStatesWithoutChangingStartSemantics() {
        let front = WatchCourseOption(
            globalId: 301,
            name: "黑骑士 ~ A",
            holes: 9,
            teeBox: "Blue",
            tees: ["Blue"]
        )

        let cached = WatchRoundSetupView(
            front: front,
            courses: [front],
            hasCachedVersion: true
        )
        XCTAssertEqual(cached.availabilityText, "已有离线版本")
        XCTAssertEqual(cached.availabilityDetail, "更换洞组或发球台时需要联网更新")
        XCTAssertEqual(cached.startActionLabel, "准备并开始")

        let firstDownload = WatchRoundSetupView(
            front: front,
            courses: [front],
            ensureGeometry: true
        )
        XCTAssertEqual(firstDownload.availabilityText, "首次开局需下载")
        XCTAssertEqual(firstDownload.availabilityDetail, "将获取真实球场与地图数据")
        XCTAssertEqual(firstDownload.startActionLabel, "下载并开始")
    }

    @MainActor
    func testClubStatsUsesOnlyUniqueMeasuredDistancesInBagOrder() {
        let view = WatchClubStatsView(clubs: [
            WatchClubOption(clubName: "一号木", medianM: 224),
            WatchClubOption(clubName: "一号木", medianM: 999),
            WatchClubOption(clubName: "七号铁", medianM: nil),
            WatchClubOption(clubName: "七号铁", medianM: 139),
            WatchClubOption(clubName: "未知", medianM: nil),
            WatchClubOption(clubName: "坏数据", medianM: -1),
        ])

        XCTAssertEqual(view.rows, [
            WatchClubStatRow(name: "一号木", yards: 245),
            WatchClubStatRow(name: "七号铁", yards: 152),
        ])
    }

    @MainActor
    func testSettingsUsesTheSystemWristFact() {
        let view = WatchSettingsView(
            gpsPreheatEnabled: .constant(true),
            bigTextMode: .constant(false),
            wristLabel: "左手"
        )

        XCTAssertEqual(view.wristLabel, "左手")
    }

    @MainActor
    func testRenderWatchFlagDirection() throws {
        let view = WatchFlagDirectionView(
            state: .ready(relativeDegrees: -20, distanceYards: 152)
        )
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-flag-direction")
    }

    // WatchStartView keeps real NavigationStack/search behavior. The workflow therefore captures its
    // compact course rows from the running simulator rather than treating ImageRenderer as final proof.

    @MainActor
    func testRenderWatchRoundContainerHome() throws {
        let model = makeSeededModel(scoring: false)   // hold a strong ref through render
        let view = WatchRoundContainerView(
            model: model,
            watchGreenYards: (front: 164, center: 173, back: 181),
            shotLocation: Self.snapshotWatchFix
        )
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
        // The full .holeMap screen through the container — geometry built the REAL way
        // (WatchHoleMapGeometry.from(pushed WatchHoleMap + cached topo)), hole facts mapped from the seeded
        // state. Caddie freshness/dispersion is not contracted, so the root is intentionally facts-only.
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
        let view = WatchRoundContainerView(
            model: model,
            holeGeometry: geometry,
            watchGreenYards: (front: 248, center: 262, back: 274),
            shotLocation: Self.snapshotWatchFix
        )
            .frame(width: 198, height: 242)
            .background(Color.black)
        try render(view, named: "watch-container-holemap")
    }

    @MainActor
    func testRenderWatchGPSAcquiring() throws {
        let view = WatchGPSAcquiringView()
            .frame(width: 198, height: 198)
            .background(Color.black)
        try render(view, named: "watch-gps-acquiring")
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

    @MainActor
    func testRenderWatchAlwaysOnDistance() throws {
        let view = WatchAlwaysOnDistanceView(hole: 4, par: 5, centerYd: 262)
            .frame(width: 198, height: 242)
            .background(Color.black)
        try render(view, named: "watch-always-on-distance")
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

    private static let snapshotWatchFix = WatchLocationFix(
        coordinate: CLLocationCoordinate2D(latitude: 40.0, longitude: 116.0),
        horizontalAccuracyM: 5,
        capturedAt: "2026-07-31T00:00:00Z"
    )

    @MainActor
    func testRenderWatchHoleMap() throws {
        // watch P1: real-topo fact map (left data column + right map on the baked sample geometry) +
        // F/M/B + edge scoring ring. Uses the
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
    func testRenderWatchHoleMapCurrentShotCaddie() throws {
        let route = [
            [435.0, 981.0, 0.0],
            [504.0, 702.0, 200.0],
            [556.0, 562.0, 303.0],
            [506.0, 403.0, 419.0],
            [435.0, 279.0, 518.8],
        ]
        let layout = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: WatchHoleMapSample.youPx,
            aimCarryM: 205,
            carryP10M: 188,
            carryP90M: 220
        ))
        let toPars: [Int: Int] = [1: 0, 2: 1, 3: -1]
        let pips = (1...18).map {
            WatchRingPip(hole: $0, toPar: toPars[$0], isCurrent: $0 == 4)
        }
        let view = WatchHoleMapView(
            holeNumber: 4,
            par: 5,
            frontGreen: 273,
            centerGreen: 287,
            backGreen: 300,
            playsLikeDelta: 8,
            lastShot: 200,
            caddieClub: "3号木",
            caddieNote: "推进 · 留100",
            showCaddieRecommendation: true,
            currentShotLayout: layout,
            ringPips: pips
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-holemap-current-shot")
    }

    @MainActor
    func testRenderWatchHoleMapPreparedTeePlan() throws {
        let view = WatchHoleMapView(
            holeNumber: 4,
            par: 5,
            frontGreen: 273,
            centerGreen: 287,
            backGreen: 300,
            playsLikeDelta: 8,
            lastShot: 0,
            caddieClub: "3号木",
            caddieNote: "推进 · 留100",
            showCaddieRecommendation: true,
            showPreparedPlan: true
        )
        .frame(width: 198, height: 242)
        .background(Color.black)
        try render(view, named: "watch-holemap-prepared-plan")
    }

    func testMapZoomExpandsOnlyAfterCrownLeavesItsRestingPosition() {
        XCTAssertFalse(WatchHoleMapView.isFullMap(crownScale: WatchHoleMapView.restingCrownScale))
        XCTAssertTrue(WatchHoleMapView.isFullMap(crownScale: WatchHoleMapView.restingCrownScale + 0.02))
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
