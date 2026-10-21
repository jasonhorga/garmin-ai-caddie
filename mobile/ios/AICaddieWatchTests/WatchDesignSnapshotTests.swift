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
    @MainActor
    func testTeeChoicesListTheDefaultTeeFirstAndHighlighted() {
        let front = WatchCourseOption(
            globalId: 301, name: "黑骑士 ~ A", holes: 9, teeBox: "White",
            venueName: "黑骑士", segmentLabel: "A", segmentHoles: 9,
            tees: ["Blue", "White", "Red"]
        )
        let setup = WatchRoundSetupView(front: front, courses: [front])
        XCTAssertEqual(setup.orderedTeeChoices.map(\.title), ["白 T", "蓝 T", "红 T"])
        XCTAssertEqual(setup.orderedTeeChoices.map(\.isSelected), [true, false, false])

        let redDefault = WatchCourseOption(
            globalId: 301, name: "黑骑士 ~ A", holes: 9, teeBox: "Red",
            venueName: "黑骑士", segmentLabel: "A", segmentHoles: 9,
            tees: ["Blue", "White", "Red"]
        )
        let redSetup = WatchRoundSetupView(front: redDefault, courses: [redDefault])
        XCTAssertEqual(redSetup.orderedTeeChoices.map(\.title), ["红 T", "蓝 T", "白 T"])
        XCTAssertEqual(redSetup.orderedTeeChoices.map(\.isSelected), [true, false, false])

        let noDefault = WatchCourseOption(
            globalId: 301, name: "黑骑士 ~ A", holes: 9,
            venueName: "黑骑士", segmentLabel: "A", segmentHoles: 9,
            tees: ["Blue", "White", "Red"]
        )
        let noDefaultSetup = WatchRoundSetupView(front: noDefault, courses: [noDefault])
        XCTAssertEqual(noDefaultSetup.orderedTeeChoices.map(\.title), ["蓝 T", "白 T", "红 T"])
        XCTAssertEqual(noDefaultSetup.orderedTeeChoices.map(\.isSelected), [true, false, false])
    }

    @MainActor
    func testATeeLessCourseOffersTheCourseDefaultRow() {
        let course = WatchCourseOption(globalId: 301, name: "测试球场", holes: 9)
        let setup = WatchRoundSetupView(front: course, courses: [course])
        XCTAssertTrue(setup.orderedTeeChoices.isEmpty)
        XCTAssertEqual(setup.teeChoices.map(\.title), ["球场默认 T"])
        XCTAssertEqual(setup.teeChoices.map(\.isSelected), [true])
    }

    @MainActor
    func testTeeTapSelectionCarriesTheChosenLoopHalfAndTee() {
        let nine = WatchCourseOption(globalId: 301, name: "黑骑士 ~ A", holes: 9, teeBox: "White", venueName: "黑骑士", segmentLabel: "A", segmentHoles: 9, tees: ["Blue", "White"])
        let nineSetup = WatchRoundSetupView(front: nine, courses: [nine], ensureGeometry: true)
        let nineSelection = nineSetup.selection(teeBox: "Red")
        XCTAssertEqual(nineSelection.teeBox, "Red")
        XCTAssertEqual(nineSelection.loopKey, "301:all")
        XCTAssertNil(nineSelection.firstHalf)
        let eighteen = WatchCourseOption(globalId: 31795, name: "黑骑士", holes: 18, teeBox: "White", venueName: "黑骑士", segmentHoles: 18, tees: ["Blue", "White"])
        let eighteenSetup = WatchRoundSetupView(front: eighteen, courses: [eighteen], ensureGeometry: true)
        let eighteenSelection = eighteenSetup.selection(teeBox: "Blue")
        XCTAssertEqual(eighteenSelection.firstHalf, "front")
        XCTAssertEqual(eighteenSelection.loopKey, "31795:front")
    }

    @MainActor
    func testTappingATeeStartsTheRoundWithThatTee() {
        let front = WatchCourseOption(
            globalId: 301, name: "黑骑士 ~ A", holes: 9, teeBox: "White",
            venueName: "黑骑士", segmentLabel: "A", segmentHoles: 9,
            tees: ["Blue", "White", "Red"]
        )
        var captured: WatchCourseSelection?
        let setup = WatchRoundSetupView(front: front, courses: [front], onStart: { captured = $0 })
        setup.start(teeBox: "Red")
        XCTAssertEqual(captured?.teeBox, "Red")
        XCTAssertEqual(captured?.loopKey, "301:all")
        XCTAssertNil(captured?.firstHalf)
    }

    @MainActor
    func testRenderWatchCourseSetupTees() throws {
        let front = WatchCourseOption(globalId: 301, name: "黑骑士 ~ A", holes: 9, teeBox: "White", venueName: "黑骑士", segmentLabel: "A", segmentHoles: 9, tees: ["Blue", "White", "Red"])
        let setup = WatchRoundSetupView(front: front, courses: [front])
        XCTAssertEqual(setup.orderedTeeChoices.map(\.title), ["白 T", "蓝 T", "红 T"])
        try render(setup.teeSelectionContent.watchSnapshotFrame(width: 198, height: 242), named: "watch-course-setup-tees")
    }
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

    /// The 球童 detail for a real prepared (offline) plan: no measured dispersion, yet every leg of
    /// the plan is drawn, not only the first (Codex review on #367).
    @MainActor
    func testRenderWatchCaddieOptionsForAPreparedPlan() throws {
        let route: [[Double]] = [[504, 702, 0], [506, 403, 210], [435, 279, 400]]
        let options = WatchCourseTemplateBuilder.preparedCaddieOptions(
            clubs: [
                WatchClubOption(clubName: "1W", medianM: 220, source: "course-prep"),
                WatchClubOption(clubName: "3W", medianM: 190, source: "course-prep"),
                WatchClubOption(clubName: "5I", medianM: 160, source: "course-prep"),
                WatchClubOption(clubName: "8I", medianM: 125, source: "course-prep"),
            ],
            suggestedClub: "3W",
            routeDistanceM: 400,
            landingM: nil
        )
        let stock = try XCTUnwrap(options.first { $0.optionId == "stock" })
        XCTAssertNil(stock.carryP10M, "prepared plans carry no measured dispersion")
        let geometry = WatchHoleMapSample.geometry
        let legs = WatchCaddieOptionsView.planLegs(for: stock, route: route, geometry: geometry)
        XCTAssertGreaterThan(legs.count, 1, "the later shots are drawn too")
        XCTAssertEqual(legs.count, stock.plan?.count)
        // Every landing with its label, and the pin with its flag, sit inside the face between the
        // header and the strategy row on both the 46 mm and the 41 mm face; no labels overlap.
        let labelSizes = legs.map { WatchPlanLegs.labelSize($0.label) }
        for labelSize in labelSizes {
            XCTAssertGreaterThan(labelSize.width, 20)
            XCTAssertLessThanOrEqual(labelSize.width, 60)
        }
        for size in [CGSize(width: 198, height: 242), CGSize(width: 176, height: 215)] {
            let viewport = try XCTUnwrap(WatchCaddieOptionsView.planViewport(
                points: [geometry.youPx] + legs.map(\.landing) + [geometry.pinPx],
                labelSizes: labelSizes,
                size: size,
                maxScale: CGFloat(WatchHoleMapView.maximumCrownScale)
            ))
            let rest = WatchCaddieOptionsView.planRestFrame(in: size)
            func canvas(_ point: CGPoint) -> CGPoint {
                CGPoint(
                    x: (point.x - viewport.focusImage.x) * viewport.scale + viewport.focusFraction.x * size.width,
                    y: (point.y - viewport.focusImage.y) * viewport.scale + viewport.focusFraction.y * size.height
                )
            }
            let landings = legs.map { canvas($0.landing) }
            for (landing, leg) in zip(landings, legs) {
                XCTAssertTrue(rest.contains(landing), "landing \(leg.label) at \(landing) in \(rest) for \(size)")
            }
            // The production layout drawFullPlan draws: measured boxes inside the rest frame.
            let labels = WatchPlanLegs.layoutLabels(legs.map(\.label), landings: landings, in: size, bounds: rest)
            XCTAssertEqual(labels.count, legs.count, "every leg keeps its label")
            for (label, leg) in zip(labels, legs) {
                XCTAssertTrue(rest.contains(label), "label \(leg.label) \(label) in \(rest) for \(size)")
            }
            for i in labels.indices { for j in labels.indices where j > i {
                XCTAssertFalse(labels[i].intersects(labels[j]), "labels \(legs[i].label) / \(legs[j].label) overlap")
            } }
            let pin = canvas(geometry.pinPx)
            XCTAssertTrue(rest.contains(pin), "pin in the rest frame for \(size)")
            XCTAssertGreaterThanOrEqual(pin.y - 13, rest.minY, "the flag clears the header for \(size)")
        }

        let view = WatchCaddieOptionsView(
            hole: 4,
            par: 5,
            options: options,
            recommendedId: "stock",
            geometry: WatchHoleMapSample.geometry,
            route: route,
            onBack: {}
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-caddie-options-prepared")
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
        // D02: the resting root shows only the prepared first-shot aim, never the full plan.
        let tee = WatchHoleMapSample.teeGeometry
        let geometry = WatchHoleMapGeometry(
            image: tee.image, imageSize: tee.imageSize, youPx: tee.youPx, pinPx: tee.pinPx,
            layupPx: try XCTUnwrap(WatchHazardMapLayout.imagePoint(on: route, atMetres: 205)),
            apexPx: try XCTUnwrap(WatchHazardMapLayout.imagePoint(on: route, atMetres: 102.5)),
            greenCtrlPx: tee.greenCtrlPx
        )
        for (name, measured) in [("watch-hole-page-plan", nil), ("watch-hole-page-plan-measure", CGPoint(x: 520, y: 470))] as [(String, CGPoint?)] {
            try render(
                WatchHoleMapView(
                    holeNumber: 7,
                    par: 4,
                    frontGreen: 552,
                    centerGreen: 567,
                    backGreen: 581,
                    lastShot: 0,
                    showCaddieRecommendation: true,
                    showPreparedPlan: true,
                    ringPips: [],
                    geometry: geometry,
                    measuredPxOverride: measured,
                    interactionMode: .measure,
                    measureOriginImagePx: geometry.youPx
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
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0, snapshotInsets: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-hole")
    }

    @MainActor
    func testRenderWatchScoreTotalStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0, fairway: .hit, snapshotInsets: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-total")
    }

    @MainActor
    func testRenderWatchScorePuttsStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            selected: .putts, snapshotInsets: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-putts")
    }

    @MainActor
    func testRenderWatchScoreFairwayStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0, fairway: .left,
            showsFairway: true, snapshotInsets: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-fairway")
    }

    @MainActor
    func testRenderWatchScorePenaltyStep() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            selected: .penalty, snapshotInsets: true
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-score-penalty")
    }

    @MainActor
    func testRenderWatchScoreWithNextTeeCandidate() throws {
        let view = WatchScoreHoleView(
            hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
            candidateNextHole: 8, snapshotInsets: true
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

        let firstDownload = WatchRoundSetupView(
            front: front,
            courses: [front],
            ensureGeometry: true
        )
        XCTAssertEqual(firstDownload.availabilityText, "可立即开局")
        XCTAssertEqual(firstDownload.availabilityDetail, "球场与地图后台补齐")
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
        // A nine-hole loop has a turn too (#424): with no known siblings, the same loop again or 只打 9 洞.
        let nine = try XCTUnwrap(WatchRoundModel.makeTurnPlan(loopKey: "301:all"))
        XCTAssertEqual(nine.course.loops.map(\.id), ["301:all"])
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
    func testRenderWatchHoleRootAimLine() throws {
        let geometry = WatchHoleMapSample.geometry
        let layout = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: [
                [435.0, 981.0, 0.0],
                [504.0, 702.0, 200.0],
                [556.0, 562.0, 303.0],
                [506.0, 403.0, 419.0],
                [435.0, 279.0, 518.8],
            ],
            playerImagePoint: geometry.youPx,
            aimCarryM: 205,
            carryP10M: 188,
            carryP90M: 220
        ))
        let view = WatchHoleMapView(
            holeNumber: 4, par: 5,
            frontGreen: 248, centerGreen: 262, backGreen: 274,
            caddieClub: "3号木",
            showCaddieRecommendation: true,
            currentShotLayout: layout,
            fullMap: false,
            restingPlayerAnchorFraction: nil,
            playerMarker: .chevron,
            lastShotPlacement: .facts,
            geometry: geometry,
            interactionMode: .measure
        )
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-hole-root-aim-line", requiresMapPixels: true)
    }

    @MainActor
    func testHoleRootPixelCheckRejectsPlaceholderWithGreenControls() throws {
        // A native-view placeholder can still sit under real green root controls, so neither
        // colour diversity nor the presence of a few green pixels proves that the map rendered.
        let placeholder = ZStack {
            Color.yellow
            Image(systemName: "nosign")
                .font(.system(size: 50))
                .foregroundStyle(.red)
            Circle().fill(.green)
                .frame(width: 30, height: 30)
                .offset(x: 60, y: 85)
        }
        .frame(width: 198, height: 242)
        let image = try XCTUnwrap(ImageRenderer(content: placeholder).cgImage)
        XCTAssertLessThanOrEqual(greenMapPixelFraction(image), 0.05)
        let topo = try XCTUnwrap(WatchHoleMapSample.image?.cgImage)
        XCTAssertGreaterThan(greenMapPixelFraction(topo), 0.05)
    }

    @MainActor
    func testRenderWatchContainerRootAimLine() throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("wsnap-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        // Timestamps are not drawn. Use a current fix so the production rangefinder gate is real.
        let now = Date()
        let formatter = ISO8601DateFormatter()
        let timestamp = formatter.string(from: now)
        let model = WatchRoundModel(store: WatchRoundStore(directoryURL: dir), now: { timestamp })
        let fix = WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0, longitude: 116.0),
            horizontalAccuracyM: 5,
            capturedAt: timestamp
        )
        let holeMap = WatchHoleMap(
            w: Int(WatchHoleMapSample.imageSize.width), h: Int(WatchHoleMapSample.imageSize.height),
            you: [504, 702], pin: [435, 279], layup: [506, 403], apex: [556, 562], greenCtrl: [498, 375],
            route: [
                [435, 981, 0], [504, 702, 200], [556, 562, 303],
                [506, 403, 419], [435, 279, 518.8],
            ]
        )
        let recommendation = WatchRootCaddieRecommendation(
            decisionId: "decision-434", clubName: "3W",
            aimCarryM: 205, carryP10M: 188, carryP90M: 220,
            sampleSize: 24, confidence: "high", source: "live", mode: "automatic",
            generatedAt: timestamp, validUntil: formatter.string(from: now.addingTimeInterval(12)),
            originLatitude: 40.0, originLongitude: 116.0, originAccuracyM: 5,
            maximumMovementM: 25, evidenceCount: 2
        )
        let state = WatchRoundState(
            roundId: "root-434", hole: 4, par: 5, distanceM: 240,
            suggestedClub: "3W", selectedClub: nil,
            offlineOptionId: "stock", decisionId: "decision-434",
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap,
            caddieOptions: [WatchCaddieOption(
                optionId: "stock", label: "标准", clubName: "3W",
                plan: [
                    WatchCaddiePlanStep(clubName: "3W", carryM: 205),
                    WatchCaddiePlanStep(clubName: "9I", carryM: 114),
                ]
            )],
            rootCaddieRecommendation: recommendation,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high"
        )
        model.seedRound([state], activeHole: 4, courseName: "测试球场")
        XCTAssertEqual(model.screen, .home)
        XCTAssertTrue(model.rootCaddieLayerAvailable(at: fix))
        XCTAssertTrue(WatchRoundContainerView.rangeFixIsQualified(
            shotLocation: fix, watchGreenYards: (front: 248, center: 262, back: 274)
        ))
        let geometry = try XCTUnwrap(WatchHoleMapGeometry.from(holeMap: holeMap, image: WatchHoleMapSample.image))
        let view = WatchRoundContainerView(
            model: model,
            holeGeometry: geometry,
            watchGreenYards: (front: 248, center: 262, back: 274),
            shotLocation: fix
        )
        .snapshottingHoleRoot()
        .watchSnapshotFrame(width: 198, height: 242)
        try render(view, named: "watch-container-root-aim-line", requiresMapPixels: true)
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
                candidateNextHole: 1,
                snapshotInsets: true
            )
            .watchSnapshotFrame(width: 176, height: 215),
            named: "watch-compact-score-fairway"
        )
        // 推杆 / 罚杆 selected (the Crown's row) on the 41 mm face.
        for field in [WatchScoreField.putts, .penalty] {
            try render(
                WatchScoreHoleView(
                    hole: 7, par: 4, score: 5, putts: 2, penalty: 1, fairway: .hit,
                    selected: field, snapshotInsets: true
                )
                .watchSnapshotFrame(width: 176, height: 215),
                named: "watch-compact-score-\(field.rawValue)"
            )
        }
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
    private func render(_ view: some View, named name: String, requiresMapPixels: Bool = false) throws {
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
        if requiresMapPixels {
            // The unsupported native TabView renders a yellow/red placeholder that passes the
            // size and colour-diversity checks above. Require actual green topo content, beyond
            // the small green club/menu controls, on both direct and container root snapshots.
            XCTAssertGreaterThan(
                greenMapPixelFraction(cgImage), 0.05,
                "\(name) is missing the topo map; ImageRenderer may have captured a native-view placeholder"
            )
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

    private func greenMapPixelFraction(_ image: CGImage) -> Double {
        let width = image.width, height = image.height
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        let rendered = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: width, height: height,
                bitsPerComponent: 8, bytesPerRow: width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGBitmapInfo.byteOrder32Big.rawValue | CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        XCTAssertTrue(rendered, "could not decode snapshot pixels")
        var greenPixels = 0
        for index in stride(from: 0, to: pixels.count, by: 4) {
            let red = Int(pixels[index]), green = Int(pixels[index + 1]), blue = Int(pixels[index + 2])
            if green > 24, green * 5 > red * 6, green * 5 > blue * 6 {
                greenPixels += 1
            }
        }
        return Double(greenPixels) / Double(width * height)
    }

    @MainActor
    func testHoleRootPixelsIgnoreTheRouteThePlanAndTheContinuation() throws {
        let route = [
            [435.0, 981.0, 0.0], [504.0, 702.0, 200.0], [556.0, 562.0, 303.0],
            [506.0, 403.0, 419.0], [435.0, 279.0, 518.8],
        ]
        let geometry = WatchHoleMapGeometry(
            image: WatchHoleMapSample.image,
            imageSize: WatchHoleMapSample.imageSize,
            youPx: WatchHoleMapSample.youPx,
            pinPx: WatchHoleMapSample.pinPx,
            layupPx: WatchHoleMapSample.layupPx,
            apexPx: WatchHoleMapSample.apexPx,
            greenCtrlPx: WatchHoleMapSample.greenCtrlPx,
            routePx: []
        )
        let routeGeometry = WatchHoleMapGeometry(
            image: WatchHoleMapSample.image,
            imageSize: WatchHoleMapSample.imageSize,
            youPx: WatchHoleMapSample.youPx,
            pinPx: WatchHoleMapSample.pinPx,
            layupPx: WatchHoleMapSample.layupPx,
            apexPx: WatchHoleMapSample.apexPx,
            greenCtrlPx: WatchHoleMapSample.greenCtrlPx,
            routePx: route.map { CGPoint(x: $0[0], y: $0[1]) }
        )
        let shot = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: geometry.youPx,
            aimCarryM: 205,
            carryP10M: 188,
            carryP90M: 220
        ))
        let continuationShot = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: geometry.youPx,
            aimCarryM: 205,
            carryP10M: 188,
            carryP90M: 220,
            continuation: [CGPoint(x: 490, y: 650), CGPoint(x: 470, y: 520)]
        ))
        let planLegs = [
            WatchPlanLeg(start: geometry.youPx, control: CGPoint(x: 470, y: 820), landing: CGPoint(x: 504, y: 702), label: "D 224"),
            WatchPlanLeg(start: CGPoint(x: 504, y: 702), control: CGPoint(x: 535, y: 620), landing: CGPoint(x: 556, y: 562), label: "3W 205"),
        ]
        let rootBase = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: shot,
            fullMap: false,
            geometry: geometry,
            interactionMode: .measure,
            planLegs: []
        )
        let rootWithRoute = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: shot,
            fullMap: false,
            geometry: routeGeometry,
            interactionMode: .measure,
            planLegs: []
        )
        let rootWithPlan = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: shot,
            fullMap: false,
            geometry: geometry,
            interactionMode: .measure,
            planLegs: planLegs
        )
        let rootWithContinuation = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: continuationShot,
            fullMap: false,
            geometry: geometry,
            interactionMode: .measure,
            planLegs: []
        )
        let fullMapBase = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: shot,
            fullMap: true,
            geometry: geometry,
            interactionMode: .measure,
            planLegs: []
        )
        let fullMapWithRoute = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: shot,
            fullMap: true,
            geometry: routeGeometry,
            interactionMode: .measure,
            planLegs: []
        )
        let fullMapWithPlan = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: shot,
            fullMap: true,
            geometry: geometry,
            interactionMode: .measure,
            planLegs: planLegs
        )
        let fullMapWithContinuation = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: continuationShot,
            fullMap: true,
            geometry: geometry,
            interactionMode: .measure,
            planLegs: []
        )
        let rootBasePixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: rootBase.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        let rootRoutePixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: rootWithRoute.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        let rootPlanPixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: rootWithPlan.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        let rootContinuationPixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: rootWithContinuation.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        XCTAssertEqual(rootBasePixels, rootRoutePixels)
        XCTAssertEqual(rootBasePixels, rootPlanPixels)
        XCTAssertEqual(rootBasePixels, rootContinuationPixels)
        let fullBasePixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: fullMapBase.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        let fullRoutePixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: fullMapWithRoute.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        let fullPlanPixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: fullMapWithPlan.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        let fullContinuationPixels = renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: fullMapWithContinuation.watchSnapshotFrame(width: 198, height: 242)).cgImage))
        XCTAssertNotEqual(fullBasePixels, fullRoutePixels)
        XCTAssertNotEqual(fullBasePixels, fullPlanPixels)
        XCTAssertNotEqual(fullBasePixels, fullContinuationPixels)
    }

    @MainActor
    func testRootRecommendationNeedsALiveOrPreparedTeeGateNotAPlan() throws {
        let timestamp = "2026-10-20T10:00:00Z"
        let fix = WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5,
            capturedAt: timestamp
        )
        let holeMap = WatchHoleMap(
            w: Int(WatchHoleMapSample.imageSize.width), h: Int(WatchHoleMapSample.imageSize.height),
            you: [435, 981], pin: [435, 279], layup: [506, 403], apex: [556, 562], greenCtrl: [498, 375],
            route: [[435, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]]
        )
        let geometry = WatchHoleMapSample.teeGeometry
        let plan = [
            WatchCaddiePlanStep(clubName: "3W", carryM: 205),
            WatchCaddiePlanStep(clubName: "9I", carryM: 114),
        ]
        let options = [WatchCaddieOption(optionId: "stock", label: "标准", clubName: "3W", plan: plan, confidence: "offline", routeOffsetBasis: .tee)]
        let recommendation = WatchRootCaddieRecommendation(
            decisionId: "d02-live", clubName: "3W", aimCarryM: 205, carryP10M: 188, carryP90M: 220,
            sampleSize: 24, confidence: "high", source: "live", mode: "automatic",
            generatedAt: timestamp, validUntil: "2026-10-20T10:05:00Z",
            originLatitude: 40, originLongitude: 116, originAccuracyM: 5, maximumMovementM: 25, evidenceCount: 2
        )
        let liveState = WatchRoundState(
            roundId: "d02", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            decisionId: "d02-live", frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            rootCaddieRecommendation: recommendation, score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high"
        )
        let liveDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-live-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: liveDir) }
        let liveModel = WatchRoundModel(store: WatchRoundStore(directoryURL: liveDir), now: { timestamp })
        liveModel.seedRound([liveState], activeHole: 4, courseName: "测试球场")
        let liveContainer = WatchRoundContainerView(model: liveModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)
        XCTAssertTrue(liveContainer.showsRootRecommendation(liveState, geometry: geometry))

        let preparedState = WatchRoundState(
            roundId: "d02-prepared", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 40, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let preparedDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-prepared-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: preparedDir) }
        let preparedModel = WatchRoundModel(store: WatchRoundStore(directoryURL: preparedDir), now: { timestamp })
        preparedModel.seedRound([preparedState], activeHole: 4, courseName: "测试球场")
        let preparedContainer = WatchRoundContainerView(model: preparedModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)
        XCTAssertTrue(preparedContainer.showsRootRecommendation(preparedState, geometry: geometry))

        let noGeometryOptions = [WatchCaddieOption(
            optionId: "no-geometry", label: "标准", clubName: "3W",
            plan: [WatchCaddiePlanStep(clubName: "3W", carryM: 0)],
            confidence: "offline", routeOffsetBasis: .tee
        )]
        let noGeometryState = WatchRoundState(
            roundId: "d02-no-geometry", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 40, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: noGeometryOptions,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let noGeometryDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-no-geometry-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: noGeometryDir) }
        let noGeometryModel = WatchRoundModel(store: WatchRoundStore(directoryURL: noGeometryDir), now: { timestamp })
        noGeometryModel.seedRound([noGeometryState], activeHole: 4, courseName: "测试球场")
        let noGeometryContainer = WatchRoundContainerView(model: noGeometryModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)
        XCTAssertFalse(noGeometryContainer.showsRootRecommendation(noGeometryState, geometry: geometry))

        let planOnlyState = WatchRoundState(
            roundId: "d02-plan", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let planOnlyDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-plan-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: planOnlyDir) }
        let planOnlyModel = WatchRoundModel(store: WatchRoundStore(directoryURL: planOnlyDir), now: { timestamp })
        planOnlyModel.seedRound([planOnlyState], activeHole: 4, courseName: "测试球场")
        let planOnlyContainer = WatchRoundContainerView(model: planOnlyModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)
        XCTAssertFalse(planOnlyContainer.showsRootRecommendation(planOnlyState, geometry: geometry))

        let noClubState = WatchRoundState(
            roundId: "d02-no-club", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 40, teeLongitude: 116, suggestedClub: nil, selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let noClubDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-no-club-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: noClubDir) }
        let noClubModel = WatchRoundModel(store: WatchRoundStore(directoryURL: noClubDir), now: { timestamp })
        noClubModel.seedRound([noClubState], activeHole: 4, courseName: "测试球场")
        let noClubContainer = WatchRoundContainerView(model: noClubModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)
        XCTAssertFalse(noClubContainer.showsRootRecommendation(noClubState, geometry: geometry))
    }

    @MainActor
    func testRootCallbacksOpenTheirIntendedScreens() throws {
        let timestamp = "2026-10-20T10:00:00Z"
        let holeMap = WatchHoleMap(
            w: Int(WatchHoleMapSample.imageSize.width), h: Int(WatchHoleMapSample.imageSize.height),
            you: [435, 981], pin: [435, 279], layup: [506, 403], apex: [556, 562], greenCtrl: [498, 375],
            route: [[435, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]]
        )
        let state = WatchRoundState(
            roundId: "d02-callbacks", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 40, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: [WatchCaddieOption(
                optionId: "stock", label: "标准", clubName: "3W",
                plan: [WatchCaddiePlanStep(clubName: "3W", carryM: 205)],
                confidence: "offline", routeOffsetBasis: .tee
            )],
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("d02-callbacks-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let model = WatchRoundModel(store: WatchRoundStore(directoryURL: directory), now: { timestamp })
        model.seedRound([state], activeHole: 4, courseName: "测试球场")
        let container = WatchRoundContainerView(
            model: model,
            holeGeometry: WatchHoleMapSample.teeGeometry,
            watchGreenYards: (227, 240, 251)
        )
        let rootMap = container.holeMapView(state, WatchHoleMapSample.teeGeometry)

        rootMap.invokeOpenCaddieForTesting()
        XCTAssertEqual(model.screen, .caddie)
        model.screen = .home
        rootMap.invokeOpenMapDetailForTesting()
        XCTAssertEqual(model.screen, .holeMap)
        model.screen = .home
        container.invokeRootMenuForTesting()
        XCTAssertEqual(model.screen, .menu)
    }

    @MainActor
    func testContainerRootWithoutAGateDrawsNoPlanAndNoClubTag() throws {
        // The container qualifies the wrist fix against the real clock, so a fixed date makes the
        // fix stale and the root a "waiting for location" face, which (#438 row 8) draws no
        // recommendation. Use the current time so the live state really is live.
        let formatter = ISO8601DateFormatter()
        let started = Date()
        let timestamp = formatter.string(from: started)
        let validUntil = formatter.string(from: started.addingTimeInterval(300))
        let fix = WatchLocationFix(coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116), horizontalAccuracyM: 5, capturedAt: timestamp)
        let holeMap = WatchHoleMap(
            w: Int(WatchHoleMapSample.imageSize.width), h: Int(WatchHoleMapSample.imageSize.height),
            you: [435, 981], pin: [435, 279], layup: [506, 403], apex: [556, 562], greenCtrl: [498, 375],
            route: [[435, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]]
        )
        let geometry = WatchHoleMapSample.teeGeometry
        let options = [WatchCaddieOption(optionId: "stock", label: "标准", clubName: "3W", plan: [
            WatchCaddiePlanStep(clubName: "3W", carryM: 205),
            WatchCaddiePlanStep(clubName: "9I", carryM: 114),
        ], confidence: "offline", routeOffsetBasis: .tee)]
        let noPlanState = WatchRoundState(
            roundId: "d02-empty", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: nil, selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251, holeMap: holeMap,
            geometryCoverage: "ready", caddieOptions: [], rootCaddieRecommendation: nil,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let planOnlyState = WatchRoundState(
            roundId: "d02-plan", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251, holeMap: holeMap,
            geometryCoverage: "ready", caddieOptions: options, rootCaddieRecommendation: nil,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let recommendation = WatchRootCaddieRecommendation(
            decisionId: "d02-pixels", clubName: "3W", aimCarryM: 205, carryP10M: 188, carryP90M: 220,
            sampleSize: 24, confidence: "high", source: "live", mode: "automatic",
            generatedAt: timestamp, validUntil: validUntil,
            originLatitude: 40, originLongitude: 116, originAccuracyM: 5, maximumMovementM: 25, evidenceCount: 2
        )
        let liveState = WatchRoundState(
            roundId: "d02-live", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            decisionId: "d02-pixels", frontGreenM: 227, centerGreenM: 240, backGreenM: 251, holeMap: holeMap,
            geometryCoverage: "ready", caddieOptions: options, rootCaddieRecommendation: recommendation,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high"
        )
        func renderRoot(_ state: WatchRoundState) throws -> [UInt8] {
            let stateDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-pixels-\(UUID().uuidString)", isDirectory: true)
            defer { try? FileManager.default.removeItem(at: stateDir) }
            let model = WatchRoundModel(store: WatchRoundStore(directoryURL: stateDir), now: { timestamp })
            model.seedRound([state], activeHole: 4, courseName: "测试球场")
            let view = WatchRoundContainerView(model: model, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)
                .snapshottingHoleRoot()
                .watchSnapshotFrame(width: 198, height: 242)
            return renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: view).cgImage))
        }
        let noPlanPixels = try renderRoot(noPlanState)
        let planOnlyPixels = try renderRoot(planOnlyState)
        let livePixels = try renderRoot(liveState)
        XCTAssertEqual(noPlanPixels, planOnlyPixels)
        XCTAssertNotEqual(noPlanPixels, livePixels)
    }

    @MainActor
    func testRestingRootWithoutTopoDrawsFallbackFacts() throws {
        let base = WatchHoleMapSample.geometry
        let route = [CGPoint(x: 435, y: 981), CGPoint(x: 435, y: 279)]
        let noFacts = WatchHoleMapGeometry(
            image: nil, imageSize: base.imageSize, youPx: base.youPx, pinPx: base.pinPx,
            layupPx: base.layupPx, apexPx: base.apexPx, greenCtrlPx: base.greenCtrlPx
        )
        let withFacts = WatchHoleMapGeometry(
            image: nil, imageSize: base.imageSize, youPx: base.youPx, pinPx: base.pinPx,
            layupPx: base.layupPx, apexPx: base.apexPx, greenCtrlPx: base.greenCtrlPx,
            routePx: route
        )

        func render(_ geometry: WatchHoleMapGeometry) throws -> [UInt8] {
            let view = WatchHoleMapView(
                fullMap: false,
                geometry: geometry,
                interactionMode: .measure
            ).watchSnapshotFrame(width: 198, height: 242)
            return renderedPixelBytes(try XCTUnwrap(ImageRenderer(content: view).cgImage))
        }

        XCTAssertNotEqual(
            try render(noFacts),
            try render(withFacts),
            "a bitmapless resting root must retain its fallback route facts"
        )
    }

    @MainActor
    func testContainerRootIsARestingMapWithoutThePlan() throws {
        let timestamp = "2026-10-20T10:00:00Z"
        let fix = WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5,
            capturedAt: timestamp
        )
        let holeMap = WatchHoleMap(
            w: Int(WatchHoleMapSample.imageSize.width), h: Int(WatchHoleMapSample.imageSize.height),
            you: [435, 981], pin: [435, 279], layup: [506, 403], apex: [556, 562], greenCtrl: [498, 375],
            route: [[435, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]]
        )
        let geometry = WatchHoleMapSample.teeGeometry
        let plan = [
            WatchCaddiePlanStep(clubName: "3W", carryM: 205),
            WatchCaddiePlanStep(clubName: "9I", carryM: 114),
        ]
        let options = [WatchCaddieOption(optionId: "stock", label: "标准", clubName: "3W", plan: plan, confidence: "offline", routeOffsetBasis: .tee)]
        let recommendation = WatchRootCaddieRecommendation(
            decisionId: "d02-live", clubName: "3W", aimCarryM: 205, carryP10M: 188, carryP90M: 220,
            sampleSize: 24, confidence: "high", source: "live", mode: "automatic",
            generatedAt: timestamp, validUntil: "2026-10-20T10:05:00Z",
            originLatitude: 40, originLongitude: 116, originAccuracyM: 5, maximumMovementM: 25, evidenceCount: 2
        )
        let liveState = WatchRoundState(
            roundId: "d02", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            decisionId: "d02-live", frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            rootCaddieRecommendation: recommendation, score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high"
        )
        let liveDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-live-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: liveDir) }
        let liveModel = WatchRoundModel(store: WatchRoundStore(directoryURL: liveDir), now: { timestamp })
        liveModel.seedRound([liveState], activeHole: 4, courseName: "测试球场")
        let liveContainer = WatchRoundContainerView(model: liveModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)

        let preparedState = WatchRoundState(
            roundId: "d02-prepared", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 40, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let preparedDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-prepared-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: preparedDir) }
        let preparedModel = WatchRoundModel(store: WatchRoundStore(directoryURL: preparedDir), now: { timestamp })
        preparedModel.seedRound([preparedState], activeHole: 4, courseName: "测试球场")
        let preparedContainer = WatchRoundContainerView(model: preparedModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)

        let planOnlyState = WatchRoundState(
            roundId: "d02-plan", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let planOnlyDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-plan-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: planOnlyDir) }
        let planOnlyModel = WatchRoundModel(store: WatchRoundStore(directoryURL: planOnlyDir), now: { timestamp })
        planOnlyModel.seedRound([planOnlyState], activeHole: 4, courseName: "测试球场")
        let planOnlyContainer = WatchRoundContainerView(model: planOnlyModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)

        let liveRoot = liveContainer.holeMapView(liveState, geometry)
        XCTAssertFalse(liveRoot.fullMap)
        XCTAssertTrue(liveRoot.planLegs.isEmpty)
        XCTAssertEqual(liveRoot.interactionMode, .measure)
        XCTAssertTrue(liveRoot.showCaddieRecommendation)
        XCTAssertNotNil(liveRoot.currentShotLayout)
        let liveShot = try XCTUnwrap(liveRoot.currentShotLayout)
        let expectedRoute = try XCTUnwrap(holeMap.route)
        let expectedShot = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: expectedRoute,
            playerImagePoint: geometry.youPx,
            aimCarryM: recommendation.aimCarryM,
            carryP10M: recommendation.carryP10M,
            carryP90M: recommendation.carryP90M
        ))
        XCTAssertEqual(liveShot.carryP10, expectedShot.carryP10)
        XCTAssertEqual(liveShot.carryP90, expectedShot.carryP90)
        XCTAssertNotEqual(liveShot.carryP10, liveShot.target, "the container must preserve real p10 depth")
        XCTAssertNotEqual(liveShot.carryP90, liveShot.target, "the container must preserve real p90 depth")

        let preparedRoot = preparedContainer.holeMapView(preparedState, geometry)
        XCTAssertFalse(preparedRoot.fullMap)
        XCTAssertTrue(preparedRoot.planLegs.isEmpty)
        XCTAssertEqual(preparedRoot.interactionMode, .measure)
        XCTAssertTrue(preparedRoot.showCaddieRecommendation)
        XCTAssertTrue(preparedRoot.showPreparedPlan)

        let planOnlyRoot = planOnlyContainer.holeMapView(planOnlyState, geometry)
        XCTAssertFalse(planOnlyRoot.fullMap)
        XCTAssertTrue(planOnlyRoot.planLegs.isEmpty)
        XCTAssertEqual(planOnlyRoot.interactionMode, .measure)
        XCTAssertFalse(planOnlyRoot.showCaddieRecommendation)
        XCTAssertNil(planOnlyRoot.currentShotLayout)
        XCTAssertFalse(planOnlyRoot.showPreparedPlan)
    }

    @MainActor
    func testPlanTagTapTargetFollowsTheRootRecommendation() throws {
        let timestamp = "2026-10-20T10:00:00Z"
        let fix = WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5,
            capturedAt: timestamp
        )
        let holeMap = WatchHoleMap(
            w: Int(WatchHoleMapSample.imageSize.width), h: Int(WatchHoleMapSample.imageSize.height),
            you: [435, 981], pin: [435, 279], layup: [506, 403], apex: [556, 562], greenCtrl: [498, 375],
            route: [[435, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]]
        )
        let geometry = WatchHoleMapSample.teeGeometry
        let plan = [
            WatchCaddiePlanStep(clubName: "3W", carryM: 205),
            WatchCaddiePlanStep(clubName: "9I", carryM: 114),
        ]
        let options = [WatchCaddieOption(optionId: "stock", label: "标准", clubName: "3W", plan: plan, confidence: "offline", routeOffsetBasis: .tee)]
        let recommendation = WatchRootCaddieRecommendation(
            decisionId: "d02-live", clubName: "3W", aimCarryM: 205, carryP10M: 188, carryP90M: 220,
            sampleSize: 24, confidence: "high", source: "live", mode: "automatic",
            generatedAt: timestamp, validUntil: "2026-10-20T10:05:00Z",
            originLatitude: 40, originLongitude: 116, originAccuracyM: 5, maximumMovementM: 25, evidenceCount: 2
        )
        let liveState = WatchRoundState(
            roundId: "d02", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            decisionId: "d02-live", frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            rootCaddieRecommendation: recommendation, score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "high"
        )
        let liveDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-live-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: liveDir) }
        let liveModel = WatchRoundModel(store: WatchRoundStore(directoryURL: liveDir), now: { timestamp })
        liveModel.seedRound([liveState], activeHole: 4, courseName: "测试球场")
        let liveContainer = WatchRoundContainerView(model: liveModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)

        let preparedState = WatchRoundState(
            roundId: "d02-prepared", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 40, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let preparedDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-prepared-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: preparedDir) }
        let preparedModel = WatchRoundModel(store: WatchRoundStore(directoryURL: preparedDir), now: { timestamp })
        preparedModel.seedRound([preparedState], activeHole: 4, courseName: "测试球场")
        let preparedContainer = WatchRoundContainerView(model: preparedModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)

        let planOnlyState = WatchRoundState(
            roundId: "d02-plan", hole: 4, par: 5, distanceM: 240,
            teeLatitude: 41, teeLongitude: 116, suggestedClub: "3W", selectedClub: nil,
            frontGreenM: 227, centerGreenM: 240, backGreenM: 251,
            holeMap: holeMap, geometryCoverage: "ready", caddieOptions: options,
            score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
        )
        let planOnlyDir = FileManager.default.temporaryDirectory.appendingPathComponent("d02-plan-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: planOnlyDir) }
        let planOnlyModel = WatchRoundModel(store: WatchRoundStore(directoryURL: planOnlyDir), now: { timestamp })
        planOnlyModel.seedRound([planOnlyState], activeHole: 4, courseName: "测试球场")
        let planOnlyContainer = WatchRoundContainerView(model: planOnlyModel, holeGeometry: geometry, watchGreenYards: (227, 240, 251), shotLocation: fix)

        XCTAssertTrue(liveContainer.showsPlanTagTapTarget())
        XCTAssertTrue(preparedContainer.showsPlanTagTapTarget())
        XCTAssertFalse(planOnlyContainer.showsPlanTagTapTarget())
        let noMapContainer = WatchRoundContainerView(
            model: liveModel, holeGeometry: nil, watchGreenYards: (227, 240, 251), shotLocation: fix
        )
        XCTAssertFalse(noMapContainer.showsPlanTagTapTarget())
    }

    @MainActor
    func testHoleRootDrawsTheAimLineAndRealDispersionOnlyWhenShown() throws {
        let geometry = WatchHoleMapSample.teeGeometry
        let shot = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: [[435, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]],
            playerImagePoint: geometry.youPx, aimCarryM: 205, carryP10M: 188, carryP90M: 220
        ))
        let noAim = WatchCurrentShotLayout(
            player: shot.target, target: shot.target,
            carryP10: shot.carryP10, carryP90: shot.carryP90, continuation: []
        )
        let noSpread = WatchCurrentShotLayout(
            player: shot.player, target: shot.target,
            carryP10: shot.target, carryP90: shot.target, continuation: []
        )
        func pixels(currentShotLayout: WatchCurrentShotLayout?, showCaddieRecommendation: Bool) throws -> [UInt8] {
            let view = WatchHoleMapView(
                showCaddieRecommendation: showCaddieRecommendation,
                currentShotLayout: currentShotLayout,
                showTextOverlay: false, fullMap: false, geometry: geometry, interactionMode: .measure
            ).watchSnapshotFrame(width: 198, height: 242)
                .environment(\.colorScheme, .dark)
            let renderer = ImageRenderer(content: view)
            renderer.scale = 1
            return renderedPixelBytes(try XCTUnwrap(renderer.cgImage))
        }
        let shown = try pixels(currentShotLayout: shot, showCaddieRecommendation: true)
        XCTAssertNotEqual(shown, try pixels(currentShotLayout: noAim, showCaddieRecommendation: true))
        XCTAssertNotEqual(shown, try pixels(currentShotLayout: noSpread, showCaddieRecommendation: true))
        let hidden = try pixels(currentShotLayout: shot, showCaddieRecommendation: false)
        XCTAssertNotEqual(shown, hidden)
        XCTAssertEqual(hidden, try pixels(currentShotLayout: nil, showCaddieRecommendation: false))
    }

    @MainActor
    func testCurrentShotFootprintUsesCarryDepthForBothSquareAxes() throws {
        // The route is straight so p10–p90 is unambiguously the longitudinal depth. The S70 box
        // deliberately uses that depth for its width because no lateral measurement is available.
        let geometry = WatchHoleMapGeometry(
            image: WatchHoleMapSample.image, imageSize: CGSize(width: 200, height: 240),
            youPx: CGPoint(x: 100, y: 200), pinPx: CGPoint(x: 100, y: 0),
            layupPx: CGPoint(x: 100, y: 100), apexPx: CGPoint(x: 100, y: 100),
            greenCtrlPx: CGPoint(x: 100, y: 20), routePx: []
        )
        let shot = try XCTUnwrap(WatchCurrentShotLayout.resolve(
            route: [[100, 200, 0], [100, 0, 200]], playerImagePoint: geometry.youPx,
            aimCarryM: 100, carryP10M: 80, carryP90M: 120
        ))
        func pixels(shown: Bool, decorativeEllipse: Bool = false) throws -> [UInt8] {
            let view = WatchHoleMapView(
                showCaddieRecommendation: shown, currentShotLayout: shot,
                showTextOverlay: false, fullMap: false, mapScale: 0.56,
                restingPlayerAnchorFraction: 0.8, geometry: geometry, interactionMode: .measure
            )
            .overlay {
                if decorativeEllipse {
                    Ellipse().stroke(Color.green, lineWidth: 2)
                        .frame(width: 36, height: 18).position(x: 100, y: 120)
                }
            }
            .watchSnapshotFrame(width: 200, height: 240)
            .environment(\.colorScheme, .dark)
            let renderer = ImageRenderer(content: view)
            renderer.scale = 1
            let image = try XCTUnwrap(renderer.cgImage)
            XCTAssertEqual(image.width, 200)
            XCTAssertEqual(image.height, 240)
            return renderedPixelBytes(image)
        }
        let hidden = try pixels(shown: false)
        let shown = try pixels(shown: true)
        func changedPixelsOutsideShotStrip(_ pixels: [UInt8]) -> Int {
            stride(from: 0, to: hidden.count, by: 4).filter { offset in
                let x = (offset / 4) % 200
                return abs(x - 100) > 4 && pixels[offset..<(offset + 4)] != hidden[offset..<(offset + 4)]
            }.count
        }
        XCTAssertNotEqual(shown, hidden, "the real aim line and carry-depth marks must be visible")
        XCTAssertGreaterThan(changedPixelsOutsideShotStrip(shown), 0, "the square has the same side across the aim")
        XCTAssertGreaterThan(
            changedPixelsOutsideShotStrip(try pixels(shown: true, decorativeEllipse: true)),
            changedPixelsOutsideShotStrip(shown),
            "the footprint check must still detect an extra lateral ellipse"
        )
    }

    // Card #438: rows 1–8 cover the S70-style Hole Root layer and its fallbacks.
    @MainActor
    func testCard438Row1RootPlanUsesYellowPlayerDiscAndDarkAimArrow() throws {
        let overlay = try XCTUnwrap(card438Overlay())
        let pixels = try card438Pixels()
        let player = overlay.player
        let across = CGPoint(x: -sin(overlay.heading), y: cos(overlay.heading))
        let yellow = card438Pixel(pixels, at: CGPoint(x: player.x + across.x * 5, y: player.y + across.y * 5), width: 198)
        let arrowPoint = CGPoint(x: player.x + cos(overlay.heading) * 3, y: player.y + sin(overlay.heading) * 3)
        let arrow = card438Pixel(pixels, at: arrowPoint, width: 198)
        XCTAssertTrue(card438IsYellow(yellow), "the recommendation marker is a yellow disc")
        XCTAssertLessThan(arrow.red + arrow.green + arrow.blue, 180, "the disc contains a dark aim arrow")
        XCTAssertFalse(card438IsWhite(arrow), "the old white chevron is absent")
    }

    @MainActor
    func testCard438Row2AimLineStopsAtDiscAndSquareEdges() throws {
        let overlay = try XCTUnwrap(card438Overlay())
        let pixels = try card438Pixels()
        let midpoint = CGPoint(
            x: (overlay.aimStart.x + overlay.aimEnd.x) * 0.5,
            y: (overlay.aimStart.y + overlay.aimEnd.y) * 0.5
        )
        // The 1.4 pt line is antialiased at scale 1, so look in the 3x3 neighbourhood.
        XCTAssertTrue(card438HasWhitePixel(pixels, near: midpoint, width: 198), "the aim segment is visible")
        XCTAssertFalse(card438IsWhite(card438Pixel(pixels, at: overlay.player, width: 198)), "the disc owns its interior")
        // Halfway from the square's near edge to its centre, on the aim: the line would be here if
        // it ran through the square. (The centre itself is on the arc, which crosses it by design.)
        let insideSquare = CGPoint(
            x: overlay.landing.x - cos(overlay.heading) * overlay.squareSide / 4,
            y: overlay.landing.y - sin(overlay.heading) * overlay.squareSide / 4
        )
        XCTAssertFalse(card438IsWhite(card438Pixel(pixels, at: insideSquare, width: 198)), "the aim line stops at the square")
        XCTAssertEqual(hypot(overlay.aimStart.x - overlay.player.x, overlay.aimStart.y - overlay.player.y), 8, accuracy: 0.8)
        XCTAssertEqual(hypot(overlay.aimEnd.x - overlay.landing.x, overlay.aimEnd.y - overlay.landing.y), overlay.squareSide / 2, accuracy: 0.8)
    }

    @MainActor
    func testCard438Row3SquareUsesTwentyPointDepthAndIsRotatedTranslucent() throws {
        let overlay = try XCTUnwrap(card438Overlay())
        XCTAssertEqual(overlay.squareSide, 20, accuracy: 1)
        let centre = CGPoint(
            x: overlay.squareCorners.reduce(0) { $0 + $1.x } / CGFloat(overlay.squareCorners.count),
            y: overlay.squareCorners.reduce(0) { $0 + $1.y } / CGFloat(overlay.squareCorners.count)
        )
        XCTAssertEqual(centre.x, overlay.landing.x, accuracy: 0.01)
        XCTAssertEqual(centre.y, overlay.landing.y, accuracy: 0.01)
        let alongEdge = CGPoint(
            x: overlay.squareCorners[3].x - overlay.squareCorners[0].x,
            y: overlay.squareCorners[3].y - overlay.squareCorners[0].y
        )
        XCTAssertGreaterThan(alongEdge.x * cos(overlay.heading) + alongEdge.y * sin(overlay.heading), 18)

        let pixels = try card438Pixels()
        let hidden = try card438Pixels(showRecommendation: false, currentShot: nil)
        XCTAssertNotEqual(
            card438Pixel(pixels, at: overlay.landing, width: 198),
            card438Pixel(hidden, at: overlay.landing, width: 198),
            "the square fill lets the map show through"
        )
        XCTAssertTrue(
            card438IsWhite(card438Pixel(pixels, at: CGPoint(
                x: (overlay.squareCorners[0].x + overlay.squareCorners[3].x) * 0.5,
                y: (overlay.squareCorners[0].y + overlay.squareCorners[3].y) * 0.5
            ), width: 198)),
            "the square has a white outline"
        )
        XCTAssertFalse(card438IsStrongGreen(card438Pixel(pixels, at: overlay.landing, width: 198)), "there is no green landing dot")
    }

    func testCard438Row4SquareSideClampsToFourteenAndTwentyEight() throws {
        let player = CGPoint(x: 0, y: 100)
        let landing = CGPoint(x: 0, y: 0)
        let minimum = try XCTUnwrap(WatchCurrentShotOverlayGeometry.resolve(
            player: player, landing: landing, carryP10: CGPoint(x: 0, y: 3), carryP90: CGPoint(x: 0, y: -3)
        ))
        let maximum = try XCTUnwrap(WatchCurrentShotOverlayGeometry.resolve(
            player: player, landing: landing, carryP10: CGPoint(x: 0, y: 30), carryP90: CGPoint(x: 0, y: -30)
        ))
        XCTAssertEqual(minimum.squareSide, 14, accuracy: 0.01)
        XCTAssertEqual(maximum.squareSide, 28, accuracy: 0.01)
    }

    @MainActor
    func testCard438Row5ArcUsesPlayerLandingRadiusAndTwentyFiveDegreeSpan() throws {
        let overlay = try XCTUnwrap(card438Overlay())
        XCTAssertEqual(overlay.radius, hypot(
            overlay.landing.x - overlay.player.x,
            overlay.landing.y - overlay.player.y
        ), accuracy: 0.01)
        XCTAssertEqual(overlay.heading - overlay.arcStartAngle, 25 * .pi / 180, accuracy: 0.001)
        XCTAssertEqual(overlay.arcEndAngle - overlay.heading, 25 * .pi / 180, accuracy: 0.001)
        let arcPoint = CGPoint(
            x: overlay.player.x + cos(overlay.heading + 12 * .pi / 180) * overlay.radius,
            y: overlay.player.y + sin(overlay.heading + 12 * .pi / 180) * overlay.radius
        )
        XCTAssertTrue(card438HasWhitePixel(try card438Pixels(), near: arcPoint, width: 198))
    }

    @MainActor
    func testCard438Row6RemainingMarkersUseS70SizeAndColours() throws {
        XCTAssertEqual(WatchHoleMapReferenceLayout.remainingMarkerRadius, 5.25, accuracy: 0.01)
        let route = [[100.0, 200.0, 0.0], [100.0, 0.0, 300.0]]
        let markers = WatchHoleMapReferenceLayout.remainingMarkers(
            route: route,
            playerImagePoint: card438Geometry.youPx,
            pinImagePoint: card438Geometry.pinPx
        )
        XCTAssertEqual(markers.map(\.remainingYards), [100, 150, 200])
        let pixels = try card438Pixels(
            showRecommendation: false,
            currentShot: nil,
            showReferenceMarkers: true,
            hazardRoute: route
        )
        for marker in markers {
            let point = card438ScreenPoint(marker.imagePoint)
            let colour = card438Pixel(pixels, at: point, width: 198)
            switch marker.remainingYards {
            case 100: XCTAssertGreaterThan(colour.red, colour.blue * 2, "100 is red")
            case 150: XCTAssertGreaterThan(colour.red + colour.green + colour.blue, 500, "150 is white")
            case 200: XCTAssertGreaterThan(colour.blue, colour.red * 3 / 2, "200 is blue")
            default: break
            }
        }
    }

    @MainActor
    func testCard438Row7CompactChipSitsRightOfPlayerAndKeepsItsCaddieCallback() throws {
        let size = CGSize(width: 198, height: 242)
        let frame = WatchHoleMapView.rootCaddieChipFrame(in: size)
        let safe = WatchDisplayGeometry.contentRect(in: size)
        let railBottom = WatchHoleMapView.rootRailBottom(in: size)
        let railTop = railBottom - WatchDisplayGeometry.instrumentControlSize
        let menu = CGRect(x: safe.minX, y: railTop, width: 50, height: 50)
        let plus = CGRect(x: safe.maxX - 50, y: railTop, width: 50, height: 50)
        // Bottom centre is the player's position between the rail buttons, so the card's fallback
        // applies: smaller than the old 50x36 pill, on the right of the player.
        XCTAssertGreaterThan(frame.minX, size.width * 0.5 + 6)
        XCTAssertLessThanOrEqual(frame.width, 50)
        XCTAssertLessThan(frame.height, 36)
        XCTAssertLessThan(frame.maxY, railTop)
        XCTAssertFalse(frame.intersects(menu))
        XCTAssertFalse(frame.intersects(plus))

        let chip = try card438Pixels(showTextOverlay: true)
        let noChip = try card438Pixels(showRecommendation: false, currentShot: nil, showTextOverlay: true)
        XCTAssertGreaterThan(card438ChangedPixels(chip, noChip, in: frame, width: 198), 0)

        var opened = false
        let view = WatchHoleMapView(
            showCaddieRecommendation: true,
            currentShotLayout: card438Shot,
            showTextOverlay: false,
            geometry: card438Geometry,
            onOpenCaddie: { opened = true }
        )
        view.invokeOpenCaddieForTesting()
        XCTAssertTrue(opened, "tapping the chip keeps the existing caddie callback")
    }

    @MainActor
    func testCard438Row8FallbacksDrawNoRecommendationLayer() throws {
        let noPlan = try card438Pixels(showRecommendation: false, currentShot: nil)
        let staleLayout = try card438Pixels(showRecommendation: false, currentShot: card438Shot)
        XCTAssertEqual(noPlan, staleLayout, "a hidden recommendation does not leak its overlay")
        XCTAssertEqual(
            try card438Pixels(showRecommendation: false, currentShot: card438Shot, rangeUnavailable: true),
            try card438Pixels(showRecommendation: false, currentShot: nil, rangeUnavailable: true),
            "waiting for location keeps the old map state"
        )
        XCTAssertEqual(
            try card438Pixels(rangeUnavailable: true),
            try card438Pixels(showRecommendation: false, currentShot: nil, rangeUnavailable: true),
            "waiting for location hides a stale recommendation layer"
        )
        XCTAssertEqual(
            WatchHoleMapRouteOverlay.resolve(
                measuredPoint: nil,
                showCaddieRecommendation: false,
                hasCurrentShot: true,
                showPreparedPlan: true
            ),
            .none
        )
        XCTAssertNotEqual(noPlan, try card438Pixels())
    }

    @MainActor
    func testCaddiePageMapDrawsTheWholePlan() throws {
        let geometry = WatchHoleMapSample.teeGeometry
        let route = [[435.0, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]]
        let option = WatchCaddieOption(optionId: "stock", label: "标准", clubName: "3W", plan: [
            WatchCaddiePlanStep(clubName: "3W", carryM: 205),
            WatchCaddiePlanStep(clubName: "9I", carryM: 114),
        ], confidence: "offline", routeOffsetBasis: .tee)
        let caddie = WatchCaddieOptionsView(options: [option], geometry: geometry, route: route)
        let map = try XCTUnwrap(caddie.optionMap(option, size: CGSize(width: 198, height: 242)))
        XCTAssertTrue(map.fullMap)
        XCTAssertTrue(map.showCaddieRecommendation)
        XCTAssertGreaterThanOrEqual(map.planLegs.count, 2)
        let withoutGeometry = WatchCaddieOptionsView(options: [option], geometry: nil, route: route)
        XCTAssertNil(withoutGeometry.optionMap(option, size: CGSize(width: 198, height: 242)))
    }

    @MainActor
    func testCaddieInstrumentRendersTheMapAndAllPlanLegs() throws {
        let geometry = WatchHoleMapSample.teeGeometry
        let route = [[435.0, 981, 0], [504, 702, 200], [556, 562, 303], [506, 403, 419], [435, 279, 518.8]]
        let option = WatchCaddieOption(optionId: "stock", label: "标准", clubName: "3W", plan: [
            WatchCaddiePlanStep(clubName: "3W", carryM: 205),
            WatchCaddiePlanStep(clubName: "9I", carryM: 114),
        ], confidence: "offline", routeOffsetBasis: .tee)
        let oneStep = WatchCaddieOption(optionId: "stock", label: "标准", clubName: "3W", plan: [
            WatchCaddiePlanStep(clubName: "3W", carryM: 205),
        ], confidence: "offline", routeOffsetBasis: .tee)
        let size = CGSize(width: 198, height: 242)

        func instrumentPixels(option: WatchCaddieOption, geometry: WatchHoleMapGeometry?) throws -> [UInt8] {
            let view = WatchCaddieOptionsView(options: [option], geometry: geometry, route: route)
                .environment(\.colorScheme, .dark)
                .watchSnapshotFrame(width: size.width, height: size.height)
            let renderer = ImageRenderer(content: view)
            renderer.scale = 2
            let image = try XCTUnwrap(renderer.cgImage)
            XCTAssertEqual(image.width, 396)
            XCTAssertEqual(image.height, 484)
            // Exclude the club-chain header and strategy row: changed text cannot prove that the
            // instrument actually renders its map or the later legs and their landing labels.
            let mapFrame = WatchCaddieOptionsView.planRestFrame(in: size)
                .applying(CGAffineTransform(scaleX: renderer.scale, y: renderer.scale))
                .integral
            let mapImage = try XCTUnwrap(image.cropping(to: mapFrame))
            return renderedPixelBytes(mapImage)
        }

        let fullPlanPixels = try instrumentPixels(option: option, geometry: geometry)
        XCTAssertNotEqual(
            fullPlanPixels, try instrumentPixels(option: option, geometry: nil),
            "the caddie instrument must render the returned map, not its placeholder"
        )
        XCTAssertNotEqual(
            fullPlanPixels, try instrumentPixels(option: oneStep, geometry: geometry),
            "the instrument's map area must include the later plan leg and label"
        )
    }

    private var card438Geometry: WatchHoleMapGeometry {
        WatchHoleMapGeometry(
            image: nil,
            imageSize: CGSize(width: 200, height: 240),
            youPx: CGPoint(x: 100, y: 190),
            pinPx: CGPoint(x: 100, y: 20),
            layupPx: CGPoint(x: 140, y: 145),
            apexPx: CGPoint(x: 120, y: 165),
            greenCtrlPx: CGPoint(x: 100, y: 40)
        )
    }

    private var card438Shot: WatchCurrentShotLayout {
        let player = card438Geometry.youPx
        let along = CGPoint(x: 0.8, y: -0.6)
        let landing = CGPoint(x: player.x + along.x * 100, y: player.y + along.y * 100)
        return WatchCurrentShotLayout(
            player: player,
            target: landing,
            carryP10: CGPoint(x: landing.x - along.x * 10, y: landing.y - along.y * 10),
            carryP90: CGPoint(x: landing.x + along.x * 10, y: landing.y + along.y * 10),
            continuation: []
        )
    }

    private func card438ScreenPoint(_ imagePoint: CGPoint) -> CGPoint {
        let size = CGSize(width: 198, height: 242)
        let anchor = CGPoint(x: size.width * 0.5, y: size.height * 0.8)
        return CGPoint(
            x: (imagePoint.x - card438Geometry.youPx.x) + anchor.x,
            y: (imagePoint.y - card438Geometry.youPx.y) + anchor.y
        )
    }

    private func card438Overlay() -> WatchCurrentShotOverlayGeometry? {
        WatchCurrentShotOverlayGeometry.resolve(
            player: card438ScreenPoint(card438Shot.player),
            landing: card438ScreenPoint(card438Shot.target),
            carryP10: card438ScreenPoint(card438Shot.carryP10),
            carryP90: card438ScreenPoint(card438Shot.carryP90)
        )
    }

    @MainActor
    private func card438Pixels(
        showRecommendation: Bool = true,
        currentShot: WatchCurrentShotLayout? = nil,
        rangeUnavailable: Bool = false,
        showReferenceMarkers: Bool = false,
        hazardRoute: [[Double]] = [],
        showTextOverlay: Bool = false
    ) throws -> [UInt8] {
        let view = WatchHoleMapView(
            showCaddieRecommendation: showRecommendation,
            currentShotLayout: currentShot ?? (showRecommendation ? card438Shot : nil),
            showReferenceMarkers: showReferenceMarkers,
            hazardRoute: hazardRoute,
            ringPips: [],
            showTextOverlay: showTextOverlay,
            rangeUnavailable: rangeUnavailable,
            showHoleIdentity: false,
            mapScale: 1,
            restingPlayerAnchorFraction: 0.8,
            playerMarker: .chevron,
            geometry: card438Geometry,
            interactionMode: .measure
        )
        let renderer = ImageRenderer(
            content: view.watchSnapshotFrame(width: 198, height: 242).environment(\.colorScheme, .dark)
        )
        renderer.scale = 1
        return renderedPixelBytes(try XCTUnwrap(renderer.cgImage))
    }

    private struct Card438RGBA: Equatable {
        let red: Int
        let green: Int
        let blue: Int
        let alpha: Int
    }

    private func card438Pixel(_ pixels: [UInt8], at point: CGPoint, width: Int) -> Card438RGBA {
        let x = min(max(Int(point.x.rounded()), 0), width - 1)
        let y = min(max(Int(point.y.rounded()), 0), pixels.count / (width * 4) - 1)
        let offset = (y * width + x) * 4
        return Card438RGBA(
            red: Int(pixels[offset]), green: Int(pixels[offset + 1]),
            blue: Int(pixels[offset + 2]), alpha: Int(pixels[offset + 3])
        )
    }

    private func card438IsYellow(_ colour: Card438RGBA) -> Bool {
        colour.red > 190 && colour.green > 130 && colour.blue < 120 && Double(colour.red) > Double(colour.blue) * 1.8
    }

    private func card438IsWhite(_ colour: Card438RGBA) -> Bool {
        colour.red > 205 && colour.green > 205 && colour.blue > 205
    }

    private func card438HasWhitePixel(_ pixels: [UInt8], near point: CGPoint, width: Int) -> Bool {
        for dy in -1...1 {
            for dx in -1...1 {
                if card438IsWhite(card438Pixel(
                    pixels,
                    at: CGPoint(x: point.x + CGFloat(dx), y: point.y + CGFloat(dy)),
                    width: width
                )) {
                    return true
                }
            }
        }
        return false
    }

    private func card438IsStrongGreen(_ colour: Card438RGBA) -> Bool {
        colour.green > 160 && colour.red < 130 && Double(colour.green) > Double(colour.blue) * 1.35
    }

    private func card438ChangedPixels(_ lhs: [UInt8], _ rhs: [UInt8], in rect: CGRect, width: Int) -> Int {
        let height = min(lhs.count, rhs.count) / (width * 4)
        let x0 = max(0, Int(rect.minX.rounded(.down)))
        let x1 = min(width, Int(rect.maxX.rounded(.up)))
        let y0 = max(0, Int(rect.minY.rounded(.down)))
        let y1 = min(height, Int(rect.maxY.rounded(.up)))
        return (y0..<y1).reduce(0) { count, y in
            count + (x0..<x1).reduce(0) { inner, x in
                let offset = (y * width + x) * 4
                return inner + (lhs[offset..<(offset + 4)] == rhs[offset..<(offset + 4)] ? 0 : 1)
            }
        }
    }

    private func renderedPixelBytes(_ image: CGImage) -> [UInt8] {
        var pixels = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let rendered = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: image.width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGBitmapInfo.byteOrder32Big.rawValue | CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
            return true
        }
        XCTAssertTrue(rendered, "could not decode rendered pixels")
        return pixels
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
