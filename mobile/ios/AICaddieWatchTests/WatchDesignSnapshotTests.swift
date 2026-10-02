import CoreLocation
import ImageIO
import SwiftUI
import XCTest
import AICaddieDomain
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
            WatchCaddieOption(optionId: "safe", label: "稳妥"),
            WatchCaddieOption(optionId: "stock", label: "标准"),
        ]

        XCTAssertEqual(
            WatchCaddieOptionsView.ordered(options).map(\.optionId),
            ["safe", "stock", "attack"]
        )
    }

    func testCompactCaddieClubChainKeepsEveryPlannedShotVisible() {
        let option = WatchCaddieOption(
            optionId: "stock",
            label: "标准",
            plan: [
                WatchCaddiePlanStep(clubName: "1W", carryM: 201.2),
                WatchCaddiePlanStep(clubName: "3W", carryM: 183),
                WatchCaddiePlanStep(clubName: "8I", carryM: 134.6),
            ]
        )

        XCTAssertEqual(WatchCaddieOptionsView.clubChain(option, compact: true), "D›3W›8i")
        XCTAssertEqual(WatchCaddieOptionsView.clubChain(option, compact: false), "D → 3W → 8i")
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
        XCTAssertFalse(items.map(\.rawValue).contains("本洞击球"))
        XCTAssertFalse(items.map(\.rawValue).contains("记一杆"))
        XCTAssertFalse(items.map(\.rawValue).contains("本洞成绩"))
        XCTAssertEqual(items[items.count - 2], .moreTools)
        XCTAssertEqual(items.last, .finish)
        XCTAssertFalse(items.map(\.rawValue).contains("继续打球"))
        XCTAssertFalse(items.map(\.rawValue).contains("放弃本场"))

        XCTAssertEqual(
            WatchMenuView.moreToolItems(hasClubStats: true, hasFlagDirection: true),
            [.flagDirection, .clubStats, .settings]
        )
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
                WatchCaddieOption(optionId: "stock", label: "标准", clubName: "8号铁", carryM: 192, carryP10M: 176, carryP90M: 208, sampleSize: 28, plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 192), WatchCaddiePlanStep(clubName: "8I", carryM: 142)], confidence: "high"),
                WatchCaddieOption(optionId: "safe", label: "稳妥", clubName: "9号铁", carryM: 172, carryP10M: 160, carryP90M: 184, sampleSize: 31, plan: [WatchCaddiePlanStep(clubName: "3W", carryM: 172), WatchCaddiePlanStep(clubName: "9I", carryM: 128)], confidence: "high"),
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

    /// B6 本洞 pages: the 障碍 page zoomed 2× with its "1 / N" selector, the 果岭 page at 3×, and
    /// the 方案 page's yellow measure ring ranged from the tee before the tee shot.
    @MainActor
    func testRenderHolePagesZoomedAndMeasured() throws {
        let route = [
            [435.0, 981.0, 0.0],
            [504.0, 702.0, 200.0],
            [556.0, 562.0, 303.0],
            [506.0, 403.0, 419.0],
            [435.0, 279.0, 518.8],
        ]
        // Real boundaries: the 障碍 page draws one hazard's outline as a thin red line.
        let hazards = [
            WatchHazard(kind: "bunker", label: "沙坑", startM: 190, endM: 210,
                        frontPx: [520, 760], backPx: [528, 728],
                        outlinePx: [[520, 760], [531, 754], [535, 741], [528, 728], [517, 731], [512, 745]]),
            WatchHazard(kind: "bunker", label: "沙坑", startM: 270, endM: 292,
                        frontPx: [540, 608], backPx: [550, 578],
                        outlinePx: [[540, 608], [553, 600], [557, 586], [550, 578], [538, 582], [534, 597]]),
        ]
        try render(
            WatchHazardMapView(
                geometry: WatchHoleMapSample.geometry,
                route: route,
                hazards: hazards,
                centerGreenYards: 320,
                initialViewport: WatchHoleViewport(zoom: 2, pan: CGSize(width: 12, height: -18))
            )
            .watchSnapshotFrame(width: 198, height: 242),
            named: "watch-hole-page-hazard-zoomed"
        )
        // The green page with the hole's real green outline (no "无果岭轮廓" fallback).
        let sample = WatchHoleMapSample.geometry
        let greenGeometry = WatchHoleMapGeometry(
            image: sample.image, imageSize: sample.imageSize, youPx: sample.youPx, pinPx: sample.pinPx,
            layupPx: sample.layupPx, apexPx: sample.apexPx, greenCtrlPx: sample.greenCtrlPx,
            greenOutlinePx: WatchHoleMapSample.greenOutlinePx
        )
        try render(
            WatchGreenPreviewView(
                geometry: greenGeometry,
                centerGreenYards: 152,
                initialZoomScale: 3
            )
            .watchSnapshotFrame(width: 198, height: 242),
            named: "watch-hole-page-green-3x"
        )
        // 方案: the whole plan from the tee — D 224 → 7i 150 → 9i 126 — with landings and labels.
        let geometry = WatchHoleMapSample.teeGeometry
        let legs = WatchPlanLegs.resolve(
            plan: [
                WatchCaddiePlanStep(clubName: "1W", carryM: 205),
                WatchCaddiePlanStep(clubName: "7I", carryM: 137),
                WatchCaddiePlanStep(clubName: "9I", carryM: 115),
            ],
            route: route,
            origin: geometry.youPx
        )
        XCTAssertEqual(legs.map(\.label), ["D 224", "7i 150", "9i 126"])
        for (name, measured) in [("watch-hole-page-plan", nil), ("watch-hole-page-plan-measure", CGPoint(x: 520, y: 470))] as [(String, CGPoint?)] {
            try render(
                WatchHoleMapView(
                    holeNumber: 7,
                    par: 4,
                    frontGreen: 552,
                    centerGreen: 567,
                    backGreen: 581,
                    lastShot: 0,
                    ringPips: [],
                    geometry: geometry,
                    measuredPxOverride: measured,
                    interactionMode: .measure,
                    measureOriginImagePx: geometry.youPx,
                    planLegs: legs
                )
                .watchSnapshotFrame(width: 198, height: 242),
                named: name
            )
        }
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

    /// B6 本洞成绩 rules: wheels wrap, the total never drops below putts + penalties + 1.
    func testScoreRulesWrapTheWheelsAndRaiseTheTotal() {
        XCTAssertEqual(WatchScoreRules.wrap(6, in: WatchScoreRules.puttRange), 0, "5 rolls over to 0")
        XCTAssertEqual(WatchScoreRules.wrap(-1, in: WatchScoreRules.puttRange), 5, "0 sits under 5")
        XCTAssertEqual(WatchScoreRules.wrap(-1, in: WatchScoreRules.penaltyRange), 4)
        XCTAssertEqual(WatchScoreRules.score(3, putts: 3, penalty: 1), 5, "raised to putts + penalties + 1")
        XCTAssertEqual(WatchScoreRules.score(6, putts: 2, penalty: 0), 6)
        XCTAssertEqual(WatchScoreRules.score(40, putts: 2, penalty: 0), 15)
    }

    @MainActor
    func testRenderWatchScoreTotalStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0, fairway: .hit
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-total")
    }

    @MainActor
    func testRenderWatchScorePuttsStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            openWheel: .putts
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-putts")
    }

    @MainActor
    func testRenderWatchScoreFairwayStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0, fairway: .left
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-fairway")
    }

    @MainActor
    func testRenderWatchScorePenaltyStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            openWheel: .penalty
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

    /// B6: no 刚才用哪支杆？ — a detected shot flashes as 第 N 杆 with an undo over the hole screen.
    @MainActor
    func testRenderDetectedShotUndoStrip() throws {
        let view = WatchRoundHomeView(
            courseName: "北京丽宫 · 前九", hole: 8, par: 4, holeCount: 9,
            scoredHoles: 7, toPar: 3, distanceText: "152 码", pendingUploads: 0,
            canRecordShot: true
        )
        .overlay(alignment: .bottom) { WatchShotUndoStrip(text: "第 2 杆") }
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-shot-undo")
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
        XCTAssertEqual(view.pendingUploadsText, "待同步 2 条记录")
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
    func testCoursePickerDoesNotTurnFullLibraryIntoNearbyFeed() {
        let nearby = WatchCourseOption(
            globalId: 303,
            name: "当前附近球场",
            holes: 18,
            latitude: 40.0,
            longitude: 116.0
        )
        let historical = WatchCourseOption(
            globalId: 304,
            name: "历史球场",
            holes: 18,
            latitude: 40.001,
            longitude: 116.0
        )
        let view = WatchStartView(
            phoneReachable: true,
            courses: [historical, nearby],
            nearbyCourses: [nearby],
            currentLatitude: 40.0,
            currentLongitude: 116.0
        )

        XCTAssertEqual(view.courseGroups[0].rows.map(\.course.globalId), [nearby.globalId])
    }

    @MainActor
    func testCoursePickerKeepsDownloadedFallbackVisibleAlongsideNearbyResults() {
        let nearby = WatchCourseOption(
            globalId: 305,
            name: "当前附近球场",
            holes: 18,
            latitude: 40.0,
            longitude: 116.0
        )
        let downloaded = WatchCourseOption(
            globalId: 306,
            name: "已下载球场",
            holes: 18,
            latitude: 39.0,
            longitude: 116.0
        )
        let view = WatchStartView(
            phoneReachable: true,
            courses: [nearby, downloaded],
            nearbyCourses: [nearby],
            cachedCourseIds: [downloaded.globalId],
            currentLatitude: 40.0,
            currentLongitude: 116.0
        )

        XCTAssertEqual(view.courseGroups.map(\.title), ["附近球场", "已下载球场"])
        XCTAssertEqual(view.courseGroups[1].rows.map(\.course.globalId), [downloaded.globalId])
        XCTAssertTrue(view.courseGroups[1].rows[0].isCached)
    }

    @MainActor
    func testCoursePickerExposesOnlyPreciseOfflineCoursesWithoutAQualifiedFix() {
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
        XCTAssertEqual(view.courseGroups.map(\.title), ["附近球场", "已下载球场"])
        XCTAssertEqual(view.courseGroups[1].rows.map(\.course.globalId), [historical.globalId])
        XCTAssertTrue(view.courseGroups[1].rows[0].isCached)
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
            ["A 场 + A 场", "A 场 + B 场", "A 场 + C 场", "只打A 场", "只打B 场", "只打C 场"]
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

        XCTAssertEqual(view.loopChoices.map(\.title), ["A 场 + A 场", "A 场 + B 场", "只打A 场", "只打B 场"])
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
        XCTAssertEqual(view.loopChoices.map(\.detail), ["同一球场打两轮", "A 场"])
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
        XCTAssertEqual(cached.startActionLabel, "开始")

        let firstDownload = WatchRoundSetupView(
            front: front,
            courses: [front],
            ensureGeometry: true
        )
        XCTAssertEqual(firstDownload.availabilityText, "可立即开局")
        XCTAssertEqual(firstDownload.availabilityDetail, "球场与地图后台补齐")
        XCTAssertEqual(firstDownload.startActionLabel, "立即开始")
    }

    /// B4b-2 §7 (owner P1): a normal 18-hole row from `/api/v2/mobile/courses/options` — the CI
    /// fixture's Black Knight shape `holes: 18, segmentHoles: 18, segmentLabel: null` — must present
    /// explicit 前九 / 后九 tiles and start one ordered half, never `G:front+G:back`.
    @MainActor
    func testRoundSetupForANormalEighteenHoleRowOffersFrontAndBackNineTiles() throws {
        let options = try WatchBackendClient(baseURL: URL(string: "https://caddie.example")!)
            .decodeCourseOptions(Data(
                #"{"schema":"ai-caddie-mobile-course-options-v1","dataMode":"ci_fixture","total":1,"courses":[{"globalId":31795,"courseKey":"31795","name":"Black Knight B/C","roundCount":1,"holes":18,"teeBox":"blue","geometryCoverage":"ready","sourceRefs":[],"venueName":"Black Knight","segmentLabel":null,"segmentHoles":18,"latitude":39.9,"longitude":116.4,"tees":["blue","white"]}],"generatedAt":"2026-08-27T00:00:00Z"}"#.utf8
            ))
        let option = try XCTUnwrap(options.first)
        XCTAssertEqual(option.holes, 18)
        XCTAssertEqual(option.segmentHoles, 18)
        XCTAssertNil(option.segmentLabel)

        let view = WatchRoundSetupView(front: option, courses: options)

        XCTAssertEqual(view.initialStage, .holes, "an 18-hole row must not skip straight to Tee selection")
        XCTAssertEqual(
            view.halfChoices.map(\.id),
            ["watch-setup-half-front", "watch-setup-half-back"]
        )
        XCTAssertEqual(view.halfChoices.map(\.title), ["前九", "后九"])
        XCTAssertEqual(view.halfChoices.map(\.detail), ["第 1–9 洞", "第 10–18 洞"])
        XCTAssertEqual(view.halfChoices.map(\.isSelected), [true, false], "前九 is preselected")
        XCTAssertEqual(view.startSelection.firstHalf, "front")
        XCTAssertNil(view.startSelection.secondHalf)
        XCTAssertEqual(view.startSelection.loopKey, "31795:front")
        XCTAssertEqual(view.startSelection.loopsQuery, "31795:front")
        XCTAssertEqual(view.startSelection.holeCount, 9)
        XCTAssertEqual(view.startActionLabel, "从 前九 开始 · 蓝 T")
        XCTAssertEqual(
            WatchRoundSetupView.halfStartTitle(globalId: 31795, half: "back", teeName: "蓝 T"),
            "从 后九 开始 · 蓝 T"
        )
        XCTAssertEqual(
            WatchRoundSetupView.halfStartTitle(globalId: 31795, half: "back", teeName: nil),
            "从 后九 开始"
        )

        // Nine-hole loops keep the existing A/B choices and never show half tiles.
        let loopA = WatchCourseOption(
            globalId: 301, name: "黑骑士 ~ A", holes: 9, teeBox: "Blue",
            venueName: "黑骑士", segmentLabel: "A", segmentHoles: 9, tees: ["Blue"]
        )
        let nine = WatchRoundSetupView(front: loopA, courses: [loopA])
        XCTAssertTrue(nine.halfChoices.isEmpty)
        XCTAssertEqual(nine.startSelection.loopKey, "301:all")
    }

    /// Rendered start tiles for a normal 18-hole row (前九 selected). The production hole stage wraps
    /// this content in a ScrollView, which ImageRenderer does not materialize on watchOS.
    @MainActor
    func testRenderWatchCourseSetupHalves() throws {
        let option = WatchCourseOption(
            globalId: 31795,
            name: "Black Knight B/C",
            holes: 18,
            teeBox: "blue",
            venueName: "Black Knight",
            segmentLabel: nil,
            segmentHoles: 18,
            tees: ["blue", "white"]
        )
        let setup = WatchRoundSetupView(front: option, courses: [option])
        XCTAssertEqual(setup.halfChoices.map(\.isSelected), [true, false])
        let view = setup.holeSelectionContent
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Color.black)
            .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-course-setup-halves")
    }

    /// Rendered turn after round hole 9 of a `G:back` round: 前九 preselected, 后九 allowed again,
    /// 只打 9 洞 visible.
    @MainActor
    func testRenderWatchCourseTurn() throws {
        let plan = try XCTUnwrap(WatchRoundModel.makeTurnPlan(loopKey: "31795:back"))
        let turn = WatchTurnView(plan: plan)
        XCTAssertEqual(WatchTurnView.choices(for: plan).map(\.isSelected), [true, false, false])
        let view = turn.content
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Color.black)
            .watchSnapshotFrame(width: 198, height: 300)
        try render(view, named: "watch-course-turn")
    }

    /// The Watch turn offers 前九 / 后九 through the shared `NineLoopPlan`: the other half is
    /// preselected, the same half is allowed, and 只打 9 洞 ends the round.
    @MainActor
    func testTurnOffersBothHalvesWithTheOtherHalfPreselectedAndStopAfterNine() throws {
        var plan = try XCTUnwrap(WatchRoundModel.makeTurnPlan(loopKey: "31795:back"))
        XCTAssertEqual(plan.phase, .atTurn)
        XCTAssertEqual(plan.first, "31795:back")
        XCTAssertEqual(plan.second, .loop("31795:front"))
        XCTAssertEqual(plan.turnTitle, "后九打完了")
        XCTAssertEqual(plan.turnActionTitle, "接着打 前九")
        XCTAssertEqual(
            WatchTurnView.choices(for: plan).map(\.id),
            ["watch-turn-half-front", "watch-turn-half-back", "watch-turn-stop-after-nine"]
        )
        XCTAssertEqual(WatchTurnView.choices(for: plan).map(\.title), ["前九", "后九", "只打 9 洞"])
        XCTAssertEqual(WatchTurnView.choices(for: plan).map(\.isSelected), [true, false, false])

        plan.chooseSecond(.loop("31795:back"))
        XCTAssertEqual(plan.turnActionTitle, "接着打 后九", "the same half is allowed")
        XCTAssertEqual(WatchTurnView.choices(for: plan).map(\.isSelected), [false, true, false])

        plan.chooseSecond(.stopAfterNine)
        XCTAssertEqual(plan.turnActionTitle, "结束 · 只打 9 洞")
        XCTAssertEqual(WatchTurnView.choices(for: plan).map(\.isSelected), [false, false, true])

        let frontFirst = try XCTUnwrap(WatchRoundModel.makeTurnPlan(loopKey: "31795:front"))
        XCTAssertEqual(frontFirst.second, .loop("31795:back"))
        XCTAssertNil(WatchRoundModel.makeTurnPlan(loopKey: "31795:front+31795:back"))
        XCTAssertNil(WatchRoundModel.makeTurnPlan(loopKey: "301:all"))
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
        // A real 45 mm face: 本洞成绩 sizes itself to the display it is given (compact below 236 pt).
        let view = WatchRoundContainerView(model: model)
            .background(Color.black)
            .watchSnapshotFrame(width: 198, height: 242)
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
            globalId: 31669, sourceLocalHole: 4, courseHoleNumber: 4, holeMap: hm,
            elevationDeltaM: 7,   // real mesh slope ⇒ 实打 shown
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        // A few scored holes so the KEPT scoring ring has real pips (owner 2026-07-08).
        let holes = [
            WatchRoundState(roundId: "r1", hole: 1, par: 4, distanceM: 0, selectedClub: nil,
                            globalId: 31669, sourceLocalHole: 1, courseHoleNumber: 1,
                            score: 4, putts: 2, penaltyCount: 0, caddieConfidence: "offline"),
            WatchRoundState(roundId: "r1", hole: 2, par: 3, distanceM: 0, selectedClub: nil,
                            globalId: 31669, sourceLocalHole: 2, courseHoleNumber: 2,
                            score: 2, putts: 1, penaltyCount: 0, caddieConfidence: "offline"),
            WatchRoundState(roundId: "r1", hole: 3, par: 5, distanceM: 0, selectedClub: nil,
                            globalId: 31669, sourceLocalHole: 3, courseHoleNumber: 3,
                            score: 6, putts: 2, penaltyCount: 0, caddieConfidence: "offline"),
            state,
        ] + (5...9).map { number in
            // A course round holds its whole 前九 table (production identity gate).
            WatchRoundState(roundId: "r1", hole: number, par: 4, distanceM: nil, selectedClub: nil,
                            globalId: 31669, sourceLocalHole: number, courseHoleNumber: number,
                            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline")
        }
        model.seedRound(holes, activeHole: 4, courseName: "测试球场", courseGlobalId: 31669, loopKey: "31669:front")
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
            holeNumber: 4, par: 5, frontGreen: 552, centerGreen: 567, backGreen: 581,
            lastShot: 0,
            ringPips: [],
            showTextOverlay: false,
            showHoleIdentity: false,
            fullMap: true,
            geometry: WatchHoleMapSample.teeGeometry,
            measuredPxOverride: WatchHoleMapSample.youPx,
            interactionMode: .touchTarget
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-holemap-measured")
    }

    @MainActor
    func testRenderWatchGreenPreview() throws {
        let base = WatchHoleMapSample.geometry
        let outline = WatchHoleMapSample.greenOutlinePx
        let detailCrop = GreenDetailCrop.around(
            points: outline.map { [Double($0.x), Double($0.y)] },
            imageWidth: Double(base.imageSize.width),
            imageHeight: Double(base.imageSize.height)
        )
        let geometry = WatchHoleMapGeometry(
            image: base.image,
            greenDetailImage: WatchHoleMapSample.greenDetailImage,
            greenDetailRectPx: detailCrop?.rect,
            imageSize: base.imageSize,
            youPx: base.youPx,
            pinPx: base.pinPx,
            layupPx: base.layupPx,
            apexPx: base.apexPx,
            greenCtrlPx: base.greenCtrlPx,
            greenOutlinePx: outline
        )
        let view = WatchGreenPreviewView(
            geometry: geometry,
            centerGreenYards: 287,
            initialPin: WatchHoleMapSample.movedPinPx
        )
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
                fairway: .right,
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
