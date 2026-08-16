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

    func testWatchClubDisplayNormalizesCanonicalBackendTokens() {
        XCTAssertEqual(WatchClubDisplay.name("wood3"), "三号木")
        XCTAssertEqual(WatchClubDisplay.name("wood5"), "五号木")
        XCTAssertEqual(WatchClubDisplay.name("wood7"), "七号木")
        XCTAssertEqual(WatchClubDisplay.name("hybrid4"), "四号小鸡腿")
        XCTAssertEqual(WatchClubDisplay.name("iron5"), "五号铁")
        XCTAssertEqual(WatchClubDisplay.name("iron9"), "九号铁")
        XCTAssertEqual(WatchClubDisplay.name("wedge50"), "50° 挖起杆")
        XCTAssertEqual(WatchClubDisplay.name("wedge60"), "60° 挖起杆")
    }

    func testWatchHoleMapUsesCompactButUnambiguousLoftWedgeNames() {
        XCTAssertEqual(WatchClubDisplay.compactMapName("wedge50"), "50°")
        XCTAssertEqual(WatchClubDisplay.compactMapName("50° 挖起杆"), "50°")
        XCTAssertEqual(WatchClubDisplay.compactMapName("50°挖起杆"), "50°")
        XCTAssertEqual(WatchClubDisplay.compactMapName("3W"), "三号木")
        XCTAssertEqual(WatchClubDisplay.compactMapName("自定义杆"), "自定义杆")
    }

    func testWatchHoleMapUsesGarminStyleShortClubCodes() {
        XCTAssertEqual(WatchClubDisplay.shortCode("Driver"), "D")
        XCTAssertEqual(WatchClubDisplay.shortCode("3号木"), "3W")
        XCTAssertEqual(WatchClubDisplay.shortCode("hybrid4"), "4H")
        XCTAssertEqual(WatchClubDisplay.shortCode("五号铁"), "5i")
        XCTAssertEqual(WatchClubDisplay.shortCode("PW"), "PW")
        XCTAssertEqual(WatchClubDisplay.shortCode("wedge50"), "50°")
        XCTAssertEqual(WatchClubDisplay.shortCode("putter"), "PT")
    }

    func testCaddieOrderStaysRecommendationSafeAttackRegardlessOfPayloadOrder() {
        let options = [
            WatchCaddieOption(optionId: "attack", label: "进攻"),
            WatchCaddieOption(optionId: "safe", label: "保守"),
            WatchCaddieOption(optionId: "stock", label: "推荐"),
        ]

        XCTAssertEqual(
            WatchCaddieOptionsView.ordered(options).map(\.optionId),
            ["stock", "safe", "attack"]
        )
    }

    func testGolfMenuKeepsOnlyPrimaryInPlayChoicesAtTheFirstLevel() {
        let items = WatchMenuView.visibleItems(
            hasViewGreen: true,
            hasCaddie: true,
            hasHazards: true,
            hasClubStats: true,
            hasFlagDirection: true
        )

        XCTAssertEqual(Array(items.prefix(4)), [.viewGreen, .caddie, .holeSelect, .scorecard])
        XCTAssertEqual(items[4], .hazards)
        XCTAssertFalse(items.contains(.recordShot))
        XCTAssertFalse(items.contains(.scoreHole))
        XCTAssertFalse(items.map(\.rawValue).contains("本洞击球"))
        XCTAssertEqual(items[items.count - 2], .moreTools)
        XCTAssertEqual(items.last, .finish)
        XCTAssertFalse(items.map(\.rawValue).contains("继续打球"))
        XCTAssertFalse(items.map(\.rawValue).contains("放弃本场"))

        XCTAssertEqual(
            WatchMenuView.moreToolItems(hasClubStats: true, hasFlagDirection: true),
            [.flagDirection, .clubStats, .settings]
        )
    }

    @MainActor
    func testRenderAutoShotCandidateConfirmation() throws {
        let view = WatchAutoShotCandidateView()
            .watchSnapshotFrame(width: 198, height: 242)
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
                WatchCaddieOption(optionId: "stock", label: "推荐", clubName: "8号铁", carryM: 192, carryP10M: 176, carryP90M: 208, sampleSize: 28, plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 192), WatchCaddiePlanStep(clubName: "8I", carryM: 142)], confidence: "high"),
                WatchCaddieOption(optionId: "safe", label: "保守", clubName: "9号铁", carryM: 172, carryP10M: 160, carryP90M: 184, sampleSize: 31, plan: [WatchCaddiePlanStep(clubName: "3W", carryM: 172), WatchCaddiePlanStep(clubName: "9I", carryM: 128)], confidence: "high"),
                WatchCaddieOption(optionId: "attack", label: "进攻", clubName: "7号铁", carryM: 205, carryP10M: 181, carryP90M: 224, sampleSize: 24, plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 205), WatchCaddiePlanStep(clubName: "PW", carryM: 118)], confidence: "medium"),
            ],
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high"
        )
        let screen = WatchCaddieScreen(state: state)
        XCTAssertTrue(screen.showsPlanOptionsFirst)

        // ImageRenderer does not materialize ScrollView contents on watchOS. Render the exact primary
        // content used by WatchCaddieScreen; the assertion above separately locks the production order.
        let view = WatchCaddieOptionsView(
            hole: 4,
            par: 5,
            options: state.caddieOptions,
            recommendedId: state.offlineOptionId,
            geometry: WatchHoleMapSample.geometry,
            route: [
                [504, 702, 0],
                [506, 403, 210],
                [435, 279, 400],
            ],
            onBack: {}
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-caddie-options")
    }

    @MainActor
    func testRenderWatchHazards() throws {
        // Both sand and water use the locked S70-facing 到/过 front/back semantics.
        let view = WatchHazardView(
            hazards: [
                WatchHazard(
                    kind: "bunker", label: "右侧球道沙坑", startM: 116, endM: 132,
                    frontDistanceM: 120, backDistanceM: 136
                ),
                WatchHazard(
                    kind: "bunker", label: "右侧果岭沙坑", startM: 160, endM: 178,
                    frontDistanceM: 165, backDistanceM: 183
                ),
                WatchHazard(
                    kind: "water", label: "前方水障碍", startM: 210, endM: 235,
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
        // The score-only/home fallback deliberately has no perimeter ring. The ring belongs only to
        // the outermost Hole Map root, where its clock-clear geometry is tested separately.
        let view = WatchRoundHomeView(
            courseName: "北京丽宫 · 前九",
            hole: 7, par: 4, holeCount: 9,
            scoredHoles: 6, toPar: 3,
            distanceText: "152 码", pendingUploads: 2,
            canRecordShot: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
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
        .watchSnapshotFrame(width: 198, height: 242)
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
    func testRenderWatchScoreHole() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0
        )
        .watchSnapshotFrame(width: 198, height: 242)
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
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-total")
    }

    @MainActor
    func testRenderWatchScorePuttsStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            step: .putts
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-putts")
    }

    @MainActor
    func testRenderWatchScoreFairwayStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            step: .fairway
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-fairway")
    }

    @MainActor
    func testRenderWatchScorePenaltyStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            step: .penalty
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-penalty")
    }

    @MainActor
    func testRenderWatchScoreWithNextTeeCandidate() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            candidateNextHole: 8
        )
        .watchSnapshotFrame(width: 198, height: 242)
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
    func testClubPromptKeepsThreeClubsAndAUsableSkipTargetOnTheFirst45mmScreen() {
        XCTAssertGreaterThanOrEqual(
            WatchClubPromptLayout.firstScreenClubRows(viewportHeight: 210),
            3
        )
        XCTAssertGreaterThanOrEqual(WatchClubPromptLayout.footerHeight, 40)
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
        XCTAssertEqual(view.completionText, "9/9 洞 · 16 推")
        XCTAssertEqual(view.primaryActionLabel, "保存并结束")
        XCTAssertEqual(view.editScoreActionLabel, "编辑成绩")
        XCTAssertEqual(view.secondaryActionLabel, "继续打球")
        XCTAssertFalse(view.initiallyShowSecondaryAction)
        XCTAssertGreaterThanOrEqual(
            WatchFinishRoundLayout.systemTimeTrailingClearance,
            WatchScoreHoleLayout.systemTimeTrailingClearance
        )
        XCTAssertLessThan(
            WatchFinishRoundLayout.secondaryActionHeight,
            WatchFinishRoundLayout.primaryActionHeight
        )
    }

    @MainActor
    func testFinishConfirmationUsesTheApprovedQuestionAndSummary() {
        let view = WatchFinishConfirmationView(
            holesPlayed: 9,
            toPar: 5,
            pendingUploads: 2
        )

        XCTAssertEqual(view.titleText, "结束本场?")
        XCTAssertEqual(view.summaryText, "9 洞 · +5 · 保存并结束")
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
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-finish-confirmation")
    }

    @MainActor
    func testCoursePickerPresentationShowsOnlyProviderNearbyRows() {
        let nearby = WatchCourseOption(
            globalId: 101,
            name: "附近球场",
            holes: 18,
            teeBox: "Blue",
            latitude: 40.0,
            longitude: 116.0
        )
        let view = WatchStartView(
            phoneReachable: false,
            courses: [nearby],
            cachedCourseIds: [nearby.globalId],
            currentLatitude: 40.0,
            currentLongitude: 116.0
        )

        XCTAssertEqual(view.courseGroups.map(\.title), ["附近球场"])
        XCTAssertEqual(view.courseGroups[0].rows.map(\.course.globalId), [nearby.globalId])
        XCTAssertEqual(view.courseGroups[0].rows.first?.title, "附近球场")
        XCTAssertEqual(view.courseGroups[0].rows.first?.subtitle, "18 洞 · 0.0 km")
        XCTAssertEqual(view.courseGroups[0].rows.first?.isCached, true)
        XCTAssertEqual(view.singleNearbyVenue?.course.globalId, nearby.globalId)
    }

    @MainActor
    func testCoursePickerGroupsThreeNineHoleSegmentsAsOneNearbyVenue() {
        let loops = ["A", "B", "C"].enumerated().map { index, label in
            WatchCourseOption(
                globalId: 201 + index,
                name: "北京黑骑士 ~ \(label)",
                holes: 9,
                teeBox: "Blue",
                venueName: "北京黑骑士",
                segmentLabel: label,
                segmentHoles: 9,
                latitude: 40.0 + Double(index) * 0.000_01,
                longitude: 116.0
            )
        }
        let view = WatchStartView(
            phoneReachable: true,
            courses: loops,
            currentLatitude: 40.0,
            currentLongitude: 116.0
        )

        XCTAssertEqual(view.courseGroups[0].rows.count, 1)
        XCTAssertEqual(view.courseGroups[0].rows.first?.title, "北京黑骑士")
        XCTAssertEqual(view.courseGroups[0].rows.first?.subtitle, "3 个 9 洞组 · 0.0 km")
        XCTAssertEqual(view.singleNearbyVenue?.course.globalId, 201)
    }

    @MainActor
    func testCoursePickerDoesNotAutoOpenWhenTwoPhysicalVenuesAreNearby() {
        let first = WatchCourseOption(
            globalId: 301,
            name: "近场",
            holes: 18,
            latitude: 40.0,
            longitude: 116.0
        )
        let second = WatchCourseOption(
            globalId: 302,
            name: "远场",
            holes: 18,
            latitude: 40.01,
            longitude: 116.0
        )
        let view = WatchStartView(
            phoneReachable: true,
            courses: [second, first],
            currentLatitude: 40.0,
            currentLongitude: 116.0
        )

        XCTAssertEqual(view.courseGroups[0].rows.map(\.course.globalId), [301, 302])
        XCTAssertNil(view.singleNearbyVenue)
    }

    @MainActor
    func testCoursePickerNeverTurnsCachedHistoryIntoNearbyWithoutAQualifiedFix() {
        let historical = WatchCourseOption(
            globalId: 401,
            name: "过去打过的球场",
            holes: 18,
            latitude: 22.0,
            longitude: 114.0,
            roundCount: 9
        )
        let view = WatchStartView(
            phoneReachable: false,
            courses: [historical],
            cachedCourseIds: [historical.globalId]
        )

        XCTAssertTrue(view.courseGroups[0].rows.isEmpty)
        XCTAssertNil(view.singleNearbyVenue)
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

        XCTAssertEqual(view.courseGroups.map(\.title), ["附近球场"])
        XCTAssertTrue(view.courseGroups[0].rows.isEmpty)
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

        XCTAssertEqual(
            view.loopChoices.map(\.title),
            ["A + A", "A + B", "A + C", "只打 A", "只打 B", "只打 C"]
        )
        XCTAssertEqual(view.loopChoices.map(\.detail), ["18 洞", "18 洞", "18 洞", "9 洞", "9 洞", "9 洞"])
        XCTAssertEqual(view.loopChoices.map(\.isSelected), [false, false, false, true, false, false])
        XCTAssertEqual(view.initialStage, .holes)
    }

    @MainActor
    func testRoundSetupOffersApprovedFullFrontAndBackChoicesForACompletePair() {
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
        let back = WatchCourseOption(
            globalId: 302,
            name: "黑骑士 ~ B",
            holes: 9,
            teeBox: "Blue",
            venueName: "黑骑士",
            segmentLabel: "B",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        let view = WatchRoundSetupView(front: front, courses: [front, back])

        XCTAssertEqual(view.loopChoices.map(\.title), ["A + A", "A + B", "只打 A", "只打 B"])
        XCTAssertEqual(view.loopChoices.map(\.detail), ["18 洞", "18 洞", "9 洞", "9 洞"])
        XCTAssertEqual(view.loopChoices.map(\.isSelected), [false, false, true, false])
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

        XCTAssertEqual(view.initialStage, .holes)
        XCTAssertEqual(view.loopChoices.map(\.title), ["全 18 洞", "只打 9 洞"])
        XCTAssertEqual(view.loopChoices.map(\.detail), ["同一球场打两轮", "A"])
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
                detail: "3,210 码",
                isSelected: true
            )
        )
    }

    func testRoundSetupTranslatesProviderPositionTeesConsistently() {
        let cases = [
            ("back", "Back", "后 T"),
            ("middle", "Middle", "中 T"),
            ("forward", "Forward", "前 T"),
        ]

        for (teeBox, name, expected) in cases {
            let choice = WatchRoundSetupView.teeChoice(
                for: WatchCourseTee(
                    teeBox: teeBox,
                    name: name,
                    yards: nil,
                    isDefault: false
                ),
                isSelected: false
            )
            XCTAssertEqual(choice.title, expected)
        }
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
            .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-flag-direction")
    }

    // The workflow captures WatchStartView's scroll/search and shallow setup transition in the running
    // simulator; ImageRenderer remains useful only for compact component geometry.

    @MainActor
    func testRenderWatchRoundContainerHome() throws {
        let model = makeSeededModel(scoring: false)   // hold a strong ref through render
        let view = WatchRoundContainerView(
            model: model,
            watchGreenYards: (front: 164, center: 173, back: 181),
            shotLocation: Self.snapshotWatchFix
        )
            .watchSnapshotFrame(width: 198, height: 242)
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
            .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-container-holemap")
    }

    @MainActor
    func testRenderWatchGPSAcquiring() throws {
        let view = WatchGPSAcquiringView()
            .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-gps-acquiring")
    }

    @MainActor
    func testRenderWatchDistanceHero() throws {
        // watch P1f: the no-geometry FALLBACK for the hole view — F/M/B hero (center biggest, Garmin S70).
        let view = WatchDistanceHero(frontYd: 248, centerYd: 262, backYd: 274, caddieLine: "3号木 · 稳妥")
            .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-distance-hero")
    }

    @MainActor
    func testRenderWatchDistanceHeroBig() throws {
        // watch P1f (spec D1 大字模式): tapping the hole view blows the center number up for arm's-length.
        let view = WatchDistanceHero(frontYd: 248, centerYd: 262, backYd: 274, caddieLine: "3号木 · 稳妥", bigText: true)
            .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-distance-hero-big")
    }

    @MainActor
    func testRenderWatchDistanceHeroOffCourseBoundary() throws {
        let view = WatchDistanceHero(
            frontYd: 18_369,
            centerYd: 18_383,
            backYd: 18_393,
            caddieLine: nil
        )
        .watchSnapshotFrame(width: 176, height: 215)
        try render(view, named: "watch-distance-hero-off-course")
    }

    @MainActor
    func testRenderWatchOffCourseSecondarySurfaces() throws {
        try render(
            WatchFlagDirectionView(state: .blocked(.tooFarFromHole))
                .watchSnapshotFrame(width: 176, height: 215),
            named: "watch-flag-direction-off-course"
        )

        let glanceState = WatchRoundState(
            roundId: "off-course", hole: 7, par: 4, distanceM: 360,
            suggestedClub: "3W", selectedClub: nil,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        try render(
            WatchCaddieGlanceView(
                state: glanceState,
                frontYd: 18_369,
                centerYd: 18_383,
                backYd: 18_393,
                lastShotDistanceM: 16_800
            )
            .padding(8)
            .watchSnapshotFrame(width: 176, height: 215, alignment: .top),
            named: "watch-caddie-glance-off-course"
        )

        try render(
            WatchHoleMapView(
                holeNumber: 7,
                par: 4,
                frontGreen: 18_369,
                centerGreen: 18_383,
                backGreen: 18_393,
                lastShot: 18_300,
                ringPips: [],
                fullMap: true
            )
            .watchSnapshotFrame(width: 198, height: 242),
            named: "watch-hole-map-off-course"
        )

        let route = [
            [435.0, 981.0, 0.0],
            [504.0, 702.0, 200.0],
            [556.0, 562.0, 303.0],
            [506.0, 403.0, 419.0],
            [435.0, 279.0, 518.8],
        ]
        let hazards = [
            WatchHazard(
                kind: "bunker",
                label: "沙坑",
                startM: 270,
                endM: 292,
                frontPx: [540, 608],
                backPx: [550, 578]
            ),
        ]
        try render(
            WatchHazardMapView(
                geometry: WatchHoleMapSample.geometry,
                route: route,
                hazards: hazards,
                centerGreenYards: 18_383
            )
            .watchSnapshotFrame(width: 198, height: 242),
            named: "watch-hazard-map-off-course"
        )
    }

    @MainActor
    func testRenderWatchAlwaysOnDistance() throws {
        let view = WatchAlwaysOnDistanceView(hole: 4, par: 5, centerYd: 262)
            .watchSnapshotFrame(width: 198, height: 242)
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
            caddieClub: "3号木", caddieNote: "留100码",
            ringPips: pips
        )
        .watchSnapshotFrame(width: 198, height: 242)   // 45 mm Apple Watch logical size
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
            caddieNote: "留100码",
            showCaddieRecommendation: true,
            currentShotLayout: layout,
            ringPips: pips
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-holemap-current-shot")
    }

    @MainActor
    func testRenderWatchHoleMapKeepsLongRecommendationInsideDataColumn() throws {
        let view = WatchHoleMapView(
            holeNumber: 18,
            par: 5,
            frontGreen: 248,
            centerGreen: 262,
            backGreen: 274,
            caddieClub: "50° 挖起杆",
            caddieNote: "推进 · 后接九号铁并避开右沙坑",
            showCaddieRecommendation: true,
            showPreparedPlan: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-holemap-long-copy")
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
            caddieNote: "留100码",
            showCaddieRecommendation: true,
            showPreparedPlan: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
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
            caddieClub: "3号木", caddieNote: "留100码",
            showCaddieRecommendation: true,
            showPreparedPlan: true,
            ringPips: pips,
            showPlaysLike: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-holemap-pl")
    }

    @MainActor
    func testRenderWatchHoleMapMeasured() throws {
        // Touch Target owns a focused map and shows both current→target and target→flag ranges.
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5, frontGreen: 273, centerGreen: 287, backGreen: 300,
            lastShot: 0,
            showCaddieRecommendation: true,
            showPreparedPlan: true,
            ringPips: [],
            measuredPxOverride: CGPoint(x: 470, y: 470),
            interactionMode: .touchTarget
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-holemap-measured")
    }

    @MainActor
    func testRenderWatchGreenPreview() throws {
        let base = WatchHoleMapSample.geometry
        let geometry = WatchHoleMapGeometry(
            image: base.image,
            imageSize: base.imageSize,
            youPx: base.youPx,
            pinPx: base.pinPx,
            layupPx: base.layupPx,
            apexPx: base.apexPx,
            greenCtrlPx: base.greenCtrlPx,
            greenOutlinePx: [
                CGPoint(x: 410, y: 256),
                CGPoint(x: 458, y: 252),
                CGPoint(x: 472, y: 289),
                CGPoint(x: 428, y: 307),
                CGPoint(x: 399, y: 283),
            ]
        )
        let view = WatchGreenPreviewView(geometry: geometry, centerGreenYards: 287)
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-green-preview")
    }

    /// Deterministic compact geometry checks. ScrollView-backed club/finish screens are deliberately
    /// absent: watchOS ImageRenderer does not lay out their scroll content and produces misleading
    /// blank PNGs. The workflow launches those screens in a real 41mm simulator instead.
    @MainActor
    func testRenderCompactWatchCriticalSurfaces() throws {
        let pips = (1...18).map {
            WatchRingPip(hole: $0, toPar: $0 < 8 ? ($0 % 3) - 1 : nil, isCurrent: $0 == 8)
        }
        try render(
            WatchHoleMapView(
                holeNumber: 18,
                par: 5,
                frontGreen: 248,
                centerGreen: 262,
                backGreen: 274,
                playsLikeDelta: 8,
                lastShot: 201,
                caddieClub: "50° 挖起杆",
                caddieNote: "推进 · 后接九号铁并避开右沙坑",
                showCaddieRecommendation: true,
                showPreparedPlan: true,
                ringPips: pips
            )
            .watchSnapshotFrame(width: 176, height: 215),
            named: "watch-compact-holemap-long-copy"
        )
        try render(
            WatchScoreHoleView(
                hole: 18,
                par: 5,
                score: 7,
                putts: 3,
                penalty: 2,
                step: .fairway,
                candidateNextHole: 1
            )
            .watchSnapshotFrame(width: 176, height: 215),
            named: "watch-compact-score-fairway"
        )
        try render(
            WatchRoundHomeView(
                courseName: "北京黑骑士国际高尔夫俱乐部 · C 场",
                hole: 18,
                par: 5,
                holeCount: 18,
                scoredHoles: 17,
                toPar: 12,
                distanceText: "262 码",
                pendingUploads: 18,
                canRecordShot: true
            )
            .watchSnapshotFrame(width: 176, height: 215),
            named: "watch-compact-long-course-name"
        )
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
        // A non-nil CGImage is not sufficient on watchOS: ScrollView-backed views can produce an
        // all-black bitmap, and a container without an explicit height can collapse to a thin strip.
        // Runtime-only scroll surfaces are captured by watch-runtime.yml; every design snapshot kept
        // here must be a real, reviewable Watch-sized image.
        XCTAssertGreaterThanOrEqual(cgImage.width, 300, "\(name) snapshot collapsed horizontally")
        XCTAssertGreaterThanOrEqual(cgImage.height, 300, "\(name) snapshot collapsed vertically")
        if let provider = cgImage.dataProvider,
           let data = provider.data {
            let bytes = CFDataGetBytePtr(data)
            let count = CFDataGetLength(data)
            var distinct = Set<UInt8>()
            if let bytes {
                let samplingStep = max(1, count / 4_096)
                for offset in stride(from: 0, to: count, by: samplingStep) {
                    distinct.insert(bytes[offset])
                    if distinct.count > 8 { break }
                }
            }
            XCTAssertGreaterThan(
                distinct.count,
                2,
                "\(name) snapshot contains no visible UI; use a real simulator capture for scroll content"
            )
        } else {
            XCTFail("could not inspect rendered pixels for \(name)")
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

private extension View {
    /// ImageRenderer has no physical Watch bezel. Apply the same rounded display mask used by the
    /// product geometry so approval PNGs cannot falsely present corner pixels as visible content.
    func watchSnapshotFrame(
        width: CGFloat,
        height: CGFloat,
        alignment: Alignment = .center
    ) -> some View {
        let size = CGSize(width: width, height: height)
        return frame(width: width, height: height, alignment: alignment)
            .clipShape(
                RoundedRectangle(
                    cornerRadius: WatchDisplayGeometry.cornerRadius(for: size),
                    style: .continuous
                )
            )
            .background(Color.black)
    }
}
