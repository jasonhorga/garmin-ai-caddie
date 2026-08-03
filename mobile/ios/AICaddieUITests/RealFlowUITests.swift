import UIKit
import XCTest

/// Real running-app screenshots from the iOS Simulator (XCUITest) — NOT ImageRenderer view snapshots.
/// Launches the ACTUAL app pointed at the live backend (funnel) with the owner admin token and a
/// simulated on-course GPS fix (all via launchEnvironment), navigates the real UI, and captures real
/// screens with `XCUIScreen.main.screenshot()`. PNGs + per-screen accessibility-tree dumps are written
/// to the test process Documents dir; native-mobile.yml collects `*Documents/real-screenshots/*`.
///
/// Each section relaunches from a known home state (back-navigation in SwiftUI is fragile), captures the
/// screen, and dumps its element tree so any tap that misses is fixable next iteration without guessing.
final class RealFlowUITests: XCTestCase {
    private let app = XCUIApplication()

    /// Read a config value the test runner may receive either plain or TEST_RUNNER_-prefixed (xcodebuild
    /// reliably forwards TEST_RUNNER_<VAR> into the UI-test runner environment; the plain form is a
    /// fallback in case it propagates too).
    private func cfg(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        return env[key] ?? env["TEST_RUNNER_\(key)"]
    }

    override func setUpWithError() throws {
        // A failed prerequisite makes every later screenshot untrustworthy. Stop at the first
        // product assertion instead of tapping through the wrong screen and reporting a cascade.
        continueAfterFailure = false
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
        app.launchEnvironment["UITEST_FOLLOW_HOLE_TEE"] = "1"
        app.launchEnvironment["UITEST_TRACE_EVENT_LATENCY"] = "1"
    }

    func testCaptureRealAppFlow() throws {
        // Read every screen from the live backend, but keep the synthetic simulator round local.
        // This lets the score flow use real 北京丽宫 data without polluting the owner's history.
        app.launchEnvironment["UITEST_DISABLE_EVENT_SYNC"] = "1"
        writeDiagnostics()
        // ---- Section 1: home + the two macro tiles (stats) ----
        launchFresh()
        save("01-home"); dump("01-home")
        XCTAssertFalse(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Unknown course")).firstMatch.exists,
            "UI-test bootstrap must load the real home course, not auto-activate the implicit DEBUG round 900001"
        )
        if tapContaining(["数据统计", "均杆 · 趋势"]) {
            let scoreComposition = app.staticTexts["成绩构成 · 按洞"]
            let trendHeading = app.staticTexts.matching(
                NSPredicate(format: "label BEGINSWITH '近 ' AND label CONTAINS '场走势'")
            ).firstMatch
            XCTAssertTrue(
                scoreComposition.waitForExistence(timeout: 20),
                "the approved scoring composition must be the statistics landing"
            )
            XCTAssertTrue(
                trendHeading.waitForExistence(timeout: 8),
                "the trend remains available below the approved scoring facts"
            )
            XCTAssertLessThan(
                scoreComposition.frame.minY,
                trendHeading.frame.minY,
                "trend must not displace the approved scoring hierarchy from the first viewport"
            )
            XCTAssertTrue(
                fullyVisible(scoreComposition),
                "the first screenshot must show the scoring composition heading inside the safe viewport"
            )
            settle(2); save("02-stats"); dump("02-stats")
        }

        // ---- Section 2: history list → a round review → shot-map → review-edit (merged #276) ----
        launchFresh()
        if tapContaining(["历史复盘", "逐场逐洞"]) {
            settle(6); save("03-history-list"); dump("03-history-list")
            let longPatternChip = app.staticTexts.matching(
                NSPredicate(format: "label BEGINSWITH %@", "双柏忌或更差")
            ).firstMatch
            XCTAssertTrue(longPatternChip.waitForExistence(timeout: 5))
            XCTAssertLessThanOrEqual(
                longPatternChip.frame.height,
                20,
                "history pattern chips must keep long labels on one readable line"
            )
            let enteredRoundReview = openEvidenceRound(
                roundRef: "17534238",
                courseName: "北京天竺黑骑士球员俱乐部",
                date: "2026-07-16",
                score: 97
            ) {
                save("03b-history-real-round"); dump("03b-history-real-round")
            }
            XCTAssertTrue(
                enteredRoundReview,
                "review evidence must open the known spatially separated Garmin round 17534238"
            )
            if enteredRoundReview {
                // The history response can finish while the navigation transition is still committing.
                // Leave one quiet window before XCUITest starts taking repeated accessibility snapshots;
                // otherwise those snapshots can starve the already-loaded SwiftUI scorecard update.
                settle(8)
                // Match the approved edit render's first-hole state with a real Garmin round whose
                // recorded positions are spatially separated and retain their actual clubs.
                let reviewTitle = app.staticTexts["单场复盘"]
                XCTAssertTrue(reviewTitle.waitForExistence(timeout: 5))
                XCTAssertGreaterThan(
                    reviewTitle.frame.height,
                    30,
                    "the approved review uses a large navigation title, not a centred inline title"
                )
                let historyBackButton = app.buttons["历史复盘"]
                XCTAssertTrue(historyBackButton.waitForExistence(timeout: 5))
                XCTAssertGreaterThan(
                    historyBackButton.frame.width,
                    60,
                    "the approved review keeps the visible 历史复盘 return label beside its chevron"
                )
                let holeRow = app.buttons["round-review-hole-1"]
                let loadedRound = holeRow.waitForExistence(timeout: 60)
                XCTAssertTrue(loadedRound, "the real round must load its first hole")
                if loadedRound {
                    settle(2); save("04-round-review"); dump("04-round-review")
                }
                let reachableHole = loadedRound && scrollTo(holeRow, maxSwipes: 4)
                XCTAssertTrue(reachableHole, "the first hole must be tappable")
                if reachableHole {
                    holeRow.tap()
                    // The pager's navigationTitle is intentionally not visible in this sheet style.
                    // Its explicit close action is the stable, user-visible proof that presentation occurred.
                    let enteredShotMap = app.buttons["关闭"].waitForExistence(timeout: 12)
                    XCTAssertTrue(enteredShotMap, "shot-map evidence must enter the pager before capture")
                    if enteredShotMap {
                        // Give the real network/decode/render task one quiet window before asking
                        // XCUITest for another accessibility snapshot. Repeated `waitForExistence`
                        // snapshots can monopolize the main thread and prevent SwiftUI from
                        // committing the already-decoded map state on the simulator.
                        settle(12)
                    }
                    let topoReady = app.descendants(matching: .any)
                        .matching(identifier: "topo-hole-base-ready").firstMatch
                    let editButton = app.buttons["编辑"]
                    let loading = app.staticTexts["载入落点…"]
                    let loadingFinished = enteredShotMap && waitUntilGone(loading, timeout: 20)
                    XCTAssertTrue(loadingFinished, "shot-map request must leave its loading state")
                    let loadedShotMap = loadingFinished
                        && editButton.waitForExistence(timeout: 20)
                        && topoReady.waitForExistence(timeout: 30)
                    XCTAssertTrue(loadedShotMap, "shot-map evidence must finish loading the real topo before capture")
                    if loadedShotMap {
                        XCTAssertTrue(app.staticTexts["一号木"].exists, "the real shot map must retain the Driver label")
                        XCTAssertTrue(app.staticTexts["三号木"].exists, "the real shot map must retain the 3W label")
                        settle(2); save("04b-shot-map"); dump("04b-shot-map")
                    }
                    if loadedShotMap, editButton.isHittable {
                        editButton.tap()
                        let editTopoReady = app.descendants(matching: .any)
                            .matching(identifier: "topo-hole-base-ready").firstMatch
                        let secondReorderHandle = app.buttons["Reorder 2"]
                        let loadedEditMap = editTopoReady.waitForExistence(timeout: 75)
                            && secondReorderHandle.waitForExistence(timeout: 12)
                        XCTAssertTrue(loadedEditMap, "edit evidence requires the real topo and the two real recorded shots returned for this hole")
                        if loadedEditMap {
                            settle(2); save("04c-edit-mode"); dump("04c-edit-mode")
                            // Tap an empty part of the map. 04d is acceptable evidence only when this
                            // actually opens the add-shot sheet, never when the tap missed or hit a handle.
                            app.coordinate(withNormalizedOffset: CGVector(dx: 0.18, dy: 0.42)).tap()
                            let addShotSheet = app.navigationBars["补一杆"]
                            let openedAddShotSheet = addShotSheet.waitForExistence(timeout: 5)
                            XCTAssertTrue(openedAddShotSheet, "04d must show the add-shot sheet titled 补一杆")
                            let liePicker = app.staticTexts["击球时球位"]
                            let exposedLiePicker = openedAddShotSheet && liePicker.waitForExistence(timeout: 3)
                            XCTAssertTrue(exposedLiePicker, "04d must expose the shot-origin lie picker")
                            if exposedLiePicker {
                                settle(2); save("04d-edit-sheet"); dump("04d-edit-sheet")
                            } else {
                                save("04d-edit-sheet-missing"); dump("04d-edit-sheet-missing")
                            }
                        }
                    }
                }
            }
        }

        // ---- Section 3: last-round review shortcut from home ----
        launchFresh()
        let lastRound = app.buttons.matching(identifier: "home-last-round-row").firstMatch
        let tappedLastRound = lastRound.waitForExistence(timeout: 8) && lastRound.isHittable
        XCTAssertTrue(tappedLastRound, "home must expose a stable last-round link")
        if tappedLastRound {
            lastRound.tap()
            let roundReview = app.navigationBars["单场复盘"]
            let enteredRoundReview = roundReview.waitForExistence(timeout: 12)
            XCTAssertTrue(enteredRoundReview, "last-round evidence must enter 单场复盘 before capture")
            if enteredRoundReview {
                // The newest honest round may contain a summary without per-hole scorecard rows
                // (for example a historical Watch upload). Readiness must mean that the content
                // finished loading, not that the backend invented a tappable hole for missing data.
                let content = app.descendants(matching: .any)["round-review-content-ready"].firstMatch
                let loadedRound = content.waitForExistence(timeout: 60)
                XCTAssertTrue(loadedRound, "last-round evidence must finish loading honest review content before capture")
                if loadedRound {
                    settle(2); save("05-last-round-review"); dump("05-last-round-review")
                }
            }
        }
        if cfg("UITEST_CAPTURE_SCOPE") == "review" { return }

        // ---- Section 4: pre-round prep on a real downloaded course ----
        // READ-ONLY (GET /courses/{id}/prep) — shows real geometry F/M/B + caddie + hazards WITHOUT
        // starting a live round, so CI never writes a junk round into the owner's real history.
        launchFresh()
        XCTAssertTrue(tapContaining(["备战", "选场 · 球童试算"]), "home must expose pre-round prep")
        XCTAssertTrue(
            app.navigationBars["选球场备战"].waitForExistence(timeout: 12),
            "pre-round entry must navigate to the real course picker"
        )
        save("06-prep-course-picker"); dump("06-prep-course-picker")

        // Enter the same installed 北京丽宫 course used by the approved live journey. CourseReviewView
        // itself is the per-hole review; no obsolete intermediate `逐洞攻略` button is required.
        XCTAssertTrue(
            tapCourseSegment(globalId: 31669),
            "course picker must expose the installed 北京丽宫 course used by the approved live flow"
        )
        XCTAssertTrue(
            app.navigationBars["赛前球场攻略"].waitForExistence(timeout: 20),
            "installed course must navigate to its per-hole prep cards"
        )
        let loading = app.staticTexts["加载中…"]
        _ = loading.waitForExistence(timeout: 5) // fast cache hits may finish before this appears
        let firstPrepCard = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Par '")).firstMatch
        XCTAssertTrue(firstPrepCard.waitForExistence(timeout: 60), "real course prep must load at least one hole")
        XCTAssertTrue(
            waitUntilGone(loading, timeout: 60),
            "pre-round screenshot must wait for the live prep request to finish"
        )
        // Bind readiness to the visible first card. LazyVStack may finish an off-screen hole first;
        // accepting any `prep-hole-map-*` lets this card still be a 72pt loading placeholder, then
        // expand after scrollTo and push the requested hazard below the screenshot.
        let firstPrepMap = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "prep-hole-map-1")
        ).firstMatch
        XCTAssertTrue(
            firstPrepMap.waitForExistence(timeout: 60),
            "the first visible prep card must lazily load its real single-hole map"
        )
        XCTAssertTrue(
            scrollTo(firstPrepCard, maxSwipes: 3),
            "first real prep card must be fully inside the simulator safe viewport"
        )
        let firstPrepTopoReady = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-ready")
        ).firstMatch
        XCTAssertTrue(
            firstPrepTopoReady.waitForExistence(timeout: 75),
            "pre-round evidence must wait for the real topo bitmap, not capture its loading overlay"
        )
        let firstPrepTopoLoading = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-loading")
        ).firstMatch
        XCTAssertTrue(
            waitUntilGone(firstPrepTopoLoading, timeout: 5),
            "the prep screenshot is valid only after the topo loading overlay disappears"
        )
        // SwiftUI can publish the accessibility tree one frame before the rendered hierarchy commits.
        settle(2)
        save("07-prep-card"); dump("07-prep-card")

        // A valid hazard screenshot must show the real front/back contract, not merely the top of a
        // long scroll view. Find the first course card that exposes both `到` and `过` and bring it on-screen.
        let prepHazard = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "：到 ", " · 过 ")
        ).firstMatch
        XCTAssertTrue(
            scrollTo(prepHazard, maxSwipes: 24),
            "real pre-round cards must expose a fully visible measured hazard with 到前沿 / 过后沿"
        )
        settle(1)
        XCTAssertTrue(
            fullyVisible(prepHazard),
            "hazard evidence must remain inside the safe viewport after the rendered map settles"
        )
        let visiblePrepTopoLoading = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-loading")
        ).firstMatch
        XCTAssertTrue(
            waitUntilGone(visiblePrepTopoLoading, timeout: 75),
            "hazard evidence must not include the next visible hole's topo loading overlay"
        )
        settle(1)
        save("08-prep-hazards"); dump("08-prep-hazards")

        // ---- Section 5: start the selected real course — GET package only, no score/backend write ----
        launchFresh()
        XCTAssertTrue(tapContaining(["打球", "开始一场"]), "home must expose the real start-round path")
        settle(9)
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "北京丽宫")).firstMatch.exists,
            "simulated course location must select 北京丽宫"
        )
        XCTAssertTrue(tapContaining(["开始记分"]), "selected real course must be startable")
        XCTAssertTrue(
            app.staticTexts["363"].waitForExistence(timeout: 60),
            "cold-loaded 北京丽宫 hole prep must expose the blue-tee center-green distance"
        )
        let liveTopoReady = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-ready")
        ).firstMatch
        XCTAssertTrue(
            liveTopoReady.waitForExistence(timeout: 75),
            "live-hole evidence must wait for the real topo bitmap, never capture the loading fallback as complete"
        )
        let liveBackButton = app.buttons["返回球局首页"]
        XCTAssertTrue(
            liveBackButton.waitForExistence(timeout: 5),
            "immersive live play must retain an explicit way back to the round home"
        )
        let liveHoleHeading = app.staticTexts["第 1 洞"]
        XCTAssertTrue(liveHoleHeading.waitForExistence(timeout: 5))
        let liveWindowFrame = app.windows.firstMatch.frame
        XCTAssertLessThan(
            liveBackButton.frame.maxX,
            liveHoleHeading.frame.minX,
            "the approved circular return control sits to the left of the hole heading"
        )
        XCTAssertGreaterThan(
            liveBackButton.frame.maxY,
            liveHoleHeading.frame.minY,
            "the approved return control and hole heading share one compact header row"
        )
        XCTAssertGreaterThan(
            liveHoleHeading.frame.minX,
            liveWindowFrame.width * 0.13,
            "the approved hole heading leaves room for the inline circular return control"
        )
        XCTAssertLessThan(
            liveBackButton.frame.width,
            liveWindowFrame.width * 0.16,
            "the approved return control is a compact circle, not a separate blue text row"
        )
        let livePlayPanel = app.descendants(matching: .any)["live-play-panel-anchor"].firstMatch
        XCTAssertTrue(livePlayPanel.waitForExistence(timeout: 5))
        XCTAssertGreaterThanOrEqual(
            livePlayPanel.frame.minY,
            liveWindowFrame.height * 0.50,
            "the approved map keeps the upper half of the first screen before the data panel begins"
        )
        XCTAssertLessThanOrEqual(
            livePlayPanel.frame.minY,
            liveWindowFrame.height * 0.55,
            "the data panel must still begin in the approved lower-map band, not drift below the first glance"
        )
        XCTAssertLessThan(
            visibleStatusChromeBrightPixelFraction(in: XCUIScreen.main.screenshot()),
            0.005,
            "the approved immersive live screen does not show system time, Wi-Fi, or battery chrome"
        )
        XCTAssertFalse(
            app.buttons["晚上好"].exists || app.buttons["早上好"].exists
                || app.buttons["中午好"].exists || app.buttons["下午好"].exists,
            "live play must not inherit the home greeting as navigation chrome"
        )
        XCTAssertTrue(
            fullyVisible(app.buttons["记一杆"]),
            "phone-only play must expose a fully visible GPS shot action"
        )
        XCTAssertTrue(
            fullyVisible(app.buttons["确认本洞成绩"]),
            "score confirmation must remain fully visible beside the shot action"
        )
        XCTAssertTrue(
            fullyVisible(app.buttons["本场计分卡"]),
            "the real scorecard action must be fully visible above the home-indicator boundary"
        )
        save("10-live-hole"); dump("10-live-hole")
        XCTAssertTrue(app.staticTexts["第 1 洞"].exists, "starting 北京丽宫 must enter its real first hole")
        XCTAssertTrue(app.staticTexts["342"].exists, "front-green distance must render")
        XCTAssertTrue(app.staticTexts["379"].exists, "back-green distance must render")
        XCTAssertTrue(tapContaining(["展开"]), "live caddie strip must expose its full plan")
        let planHeading = app.staticTexts["球童完整方案"]
        XCTAssertTrue(
            scrollTo(planHeading, maxSwipes: 8),
            "expanded caddie plan must be scrolled into the visible simulator viewport"
        )
        let caddieLoading = app.activityIndicators["正在更新球童建议"]
        _ = caddieLoading.waitForExistence(timeout: 2) // a warm backend may finish before this appears
        XCTAssertTrue(
            waitUntilGone(caddieLoading, timeout: 75),
            "structured on-course caddie options must not be blocked by an unused LLM explanation"
        )
        XCTAssertFalse(
            app.staticTexts["联网球童暂不可用 · 已切换到离线缓存建议。"].exists,
            "the real course screenshot must prove the online structured decision, not an offline fallback"
        )
        let closeCaddiePlan = app.buttons["关闭球童方案"]
        XCTAssertTrue(
            closeCaddiePlan.waitForExistence(timeout: 3),
            "the complete caddie plan must be its own focused surface instead of an inline extension below the live controls"
        )
        XCTAssertLessThan(
            planHeading.frame.minY,
            120,
            "the complete caddie plan heading must start in the first-glance band, not below a duplicated distance panel"
        )
        for label in ["稳妥打法", "标准打法", "进攻打法"] {
            XCTAssertTrue(
                app.staticTexts[label].waitForExistence(timeout: 5),
                "a Par 4 tee decision must expose all three complete club-to-club strategy chains: \(label)"
            )
        }
        XCTAssertFalse(
            app.segmentedControls.firstMatch.exists,
            "the three route cards are the strategy controls; a duplicate segmented control wastes map-height"
        )
        for strategy in ["protect_score", "stock", "attack"] {
            XCTAssertTrue(
                app.buttons["caddie-strategy-\(strategy)"].waitForExistence(timeout: 5),
                "each complete route card must directly select the \(strategy) strategy"
            )
        }
        XCTAssertTrue(
            scrollTo(app.staticTexts["标准打法"], maxSwipes: 12),
            "the selected full-hole club chain must be visible in the simulator evidence"
        )
        settle(1); save("11-caddie-plan"); dump("11-caddie-plan")

        let avoidZones = app.buttons["备选打法 · 避开区"]
        XCTAssertTrue(scrollTo(avoidZones, maxSwipes: 8), "full caddie plan must expose avoid zones")
        avoidZones.tap()
        let avoidZonesHeading = app.staticTexts["避开区"]
        XCTAssertTrue(scrollTo(avoidZonesHeading, maxSwipes: 8), "expanded avoid zones must be visible")
        for label in ["稳妥打法", "标准打法", "进攻打法"] {
            XCTAssertEqual(
                app.staticTexts.matching(NSPredicate(format: "label == %@", label)).count,
                1,
                "a complete route must appear once; the avoid-zone disclosure must not repeat a second single-shot option table: \(label)"
            )
        }
        settle(1); save("11b-caddie-hazards"); dump("11b-caddie-hazards")

        closeCaddiePlan.tap()
        XCTAssertTrue(
            waitUntilGone(planHeading, timeout: 3),
            "closing the caddie plan must return to the same live-hole controls"
        )

        let recordShotButton = app.buttons["记一杆"]
        XCTAssertTrue(scrollTo(recordShotButton, maxSwipes: 14), "real hole must expose independent shot capture")
        recordShotButton.tap()
        XCTAssertTrue(
            app.staticTexts["这一杆用了什么球杆？"].waitForExistence(timeout: 5),
            "recording must capture GPS first and then ask for the actual club"
        )
        settle(1); save("11c-shot-club-prompt"); dump("11c-shot-club-prompt")
        let skipClub = app.buttons["跳过球杆（位置已记录）"]
        XCTAssertTrue(skipClub.waitForExistence(timeout: 3), "club may be skipped without discarding the GPS shot")
        skipClub.tap()
        XCTAssertTrue(app.staticTexts["已记第 1 杆"].waitForExistence(timeout: 5))
        let recordedShotHoleHeading = app.staticTexts["第 1 洞"]
        XCTAssertTrue(
            recordedShotHoleHeading.waitForExistence(timeout: 5) && fullyVisible(recordedShotHoleHeading),
            "closing the actual-club sheet must restore the live-hole map/header instead of retaining the sheet-trigger scroll offset"
        )
        settle(1); save("11d-shot-recorded"); dump("11d-shot-recorded")

        let saveHoleButton = app.buttons["确认本洞成绩"]
        XCTAssertTrue(scrollTo(saveHoleButton, maxSwipes: 14), "real hole must return to score confirmation")
        XCTAssertTrue(saveHoleButton.waitForExistence(timeout: 8), "hole root must expose score confirmation")
        saveHoleButton.tap()

        let acceptRecommendation = app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "接受推荐")
        ).firstMatch
        XCTAssertTrue(
            acceptRecommendation.waitForExistence(timeout: 5),
            "saving a hole must ask for one-tap recommended-score acceptance before recording"
        )
        XCTAssertEqual(acceptRecommendation.label, "接受推荐 3 杆", "one recorded shot should recommend shot + two putts")
        settle(1); save("12-score-confirmation"); dump("12-score-confirmation")
        acceptRecommendation.tap()
        let nextHoleHeading = app.staticTexts["第 2 洞"]
        XCTAssertTrue(
            nextHoleHeading.waitForExistence(timeout: 12),
            "accepting the recommended score must move phone-only play to the ordered next hole"
        )
        XCTAssertTrue(
            fullyVisible(nextHoleHeading),
            "the ordered next hole must reset live play to its map/header instead of inheriting the prior scroll offset"
        )
        let nextHoleShotButton = app.buttons["记一杆"]
        XCTAssertTrue(nextHoleShotButton.waitForExistence(timeout: 5), "the next hole must retain shot capture")
        XCTAssertTrue(
            nextHoleShotButton.isEnabled,
            "changing holes must retain the latest GPS fix instead of leaving shot capture permanently disabled"
        )
        XCTAssertFalse(
            app.staticTexts["等待 GPS 定位后即可记杆"].exists,
            "a valid simulated live GPS fix must remain available after changing holes"
        )

        // A hole heading alone is not evidence that the new hole has loaded. The prior run captured
        // an empty reticle and blank F/M/B, then navigated away while two caddie requests raced. Hold
        // this gate until the real hole-2 prep and the final structured caddie response are visible.
        let hole2TeeGreenYards = try XCTUnwrap(
            fetchPrepGreenYards(globalId: 31669, hole: 2),
            "the live backend must expose real static F/M/B facts for 北京丽宫 hole 2"
        )
        continueAfterFailure = false
        let liveDistanceIdentifiers = ["live-green-front", "live-green-middle", "live-green-back"]
        for (identifier, staticYards) in zip(liveDistanceIdentifiers, hole2TeeGreenYards) {
            let distance = app.staticTexts[identifier]
            XCTAssertTrue(
                distance.waitForExistence(timeout: 20),
                "the ordered next hole must expose its identified live F/M/B distance \(identifier)"
            )
            let liveYards = try XCTUnwrap(Int(distance.label), "\(identifier) must expose whole yards")
            // Static prep is measured in the decoded mesh plane; the live readout ranges between
            // WGS84 points. They need to identify the same Tee/green, not be byte-identical metres.
            let tolerance = max(8, Int(ceil(Double(staticYards) * 0.02)))
            XCTAssertLessThanOrEqual(
                abs(liveYards - staticYards),
                tolerance,
                "the ordered next hole must move simulated GPS to its own Tee (live \(liveYards), static \(staticYards))"
            )
        }
        continueAfterFailure = true
        let nextHoleCaddieLoading = app.activityIndicators["正在更新球童建议"]
        _ = nextHoleCaddieLoading.waitForExistence(timeout: 2)
        XCTAssertTrue(
            waitUntilGone(nextHoleCaddieLoading, timeout: 75),
            "the ordered next hole must settle its structured caddie request before screenshot or navigation"
        )
        XCTAssertFalse(
            app.staticTexts["联网球童暂不可用 · 已切换到离线缓存建议。"].exists,
            "task cancellation during a hole transition must not be presented as a connectivity failure"
        )
        settle(1); save("13-next-hole"); dump("13-next-hole")

        let scorecard = app.buttons["本场计分卡"]
        XCTAssertTrue(scrollTo(scorecard, maxSwipes: 8), "real hole must expose its scorecard action")
        XCTAssertTrue(scorecard.waitForExistence(timeout: 5), "live play must expose a real scorecard action")
        scorecard.tap()
        XCTAssertTrue(app.staticTexts["本场计分卡"].waitForExistence(timeout: 5))
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "北京丽宫")).firstMatch.exists,
            "in-round scorecard must retain the real selected course"
        )
        XCTAssertTrue(
            app.descendants(matching: .any)["live-scorecard-hole-index-1"].waitForExistence(timeout: 5),
            "the scorecard must expose a neutral hole index separate from score semantics"
        )
        XCTAssertTrue(
            app.descendants(matching: .any)["live-scorecard-score-chip-1"].waitForExistence(timeout: 5),
            "the recorded score must own the birdie/bogey shape"
        )
        settle(1); save("14-live-scorecard"); dump("14-live-scorecard")

        let editFirstHole = app.buttons["编辑第 1 洞成绩"]
        XCTAssertTrue(editFirstHole.waitForExistence(timeout: 5), "any completed hole must be editable")
        editFirstHole.tap()
        XCTAssertTrue(app.staticTexts["手动确认 · 总杆"].waitForExistence(timeout: 5))
        settle(1); save("15-edit-previous-hole"); dump("15-edit-previous-hole")

        XCTAssertTrue(app.buttons["下一步 · 推杆"].waitForExistence(timeout: 3))
        app.buttons["下一步 · 推杆"].tap()
        XCTAssertTrue(app.buttons["下一步 · 开球结果"].waitForExistence(timeout: 3))
        app.buttons["下一步 · 开球结果"].tap()
        XCTAssertTrue(app.buttons["上球道"].waitForExistence(timeout: 3))
        app.buttons["上球道"].tap()
        XCTAssertTrue(app.buttons["保存本洞"].waitForExistence(timeout: 3))
        app.buttons["保存本洞"].tap()
        XCTAssertTrue(
            app.staticTexts["第 2 洞"].waitForExistence(timeout: 5),
            "saving a historical score edit must not move the active playing hole"
        )
        settle(1); save("16-saved-previous-hole"); dump("16-saved-previous-hole")

        XCTAssertTrue(scrollTo(scorecard, maxSwipes: 8), "scorecard must remain available after historical save")
        scorecard.tap()
        XCTAssertTrue(app.staticTexts["本场计分卡"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["当前"].exists, "scorecard must still mark hole 2 as the playing hole")
        XCTAssertTrue(app.descendants(matching: .any)["live-scorecard-hole-index-1"].exists)
        XCTAssertTrue(app.descendants(matching: .any)["live-scorecard-score-chip-1"].exists)
        settle(1); save("17-scorecard-after-edit"); dump("17-scorecard-after-edit")

        app.buttons["关闭计分卡"].tap()
        let manageRound = app.buttons["球局调整 · 加打 / 结束本场"]
        XCTAssertTrue(scrollTo(manageRound, maxSwipes: 16), "test round must expose local cleanup")
        manageRound.tap()
        let finishRound = app.buttons["结束本场"].firstMatch
        XCTAssertTrue(scrollTo(finishRound, maxSwipes: 4), "menu finish must open the shared round summary")
        finishRound.tap()
        XCTAssertTrue(
            app.staticTexts["本场汇总"].waitForExistence(timeout: 5),
            "ending from the menu must show the same non-destructive summary used after the final hole"
        )
        XCTAssertTrue(app.staticTexts["已完成 1/18 洞"].exists)
        XCTAssertTrue(app.buttons["保存并结束"].exists)
        XCTAssertTrue(app.buttons["继续打球"].exists)
        settle(1); save("18-round-summary"); dump("18-round-summary")

        app.buttons["继续打球"].tap()
        XCTAssertTrue(
            app.staticTexts["第 2 洞"].waitForExistence(timeout: 5),
            "continuing from the summary must preserve the active round and playing hole"
        )
        settle(1); save("19-journey-02-after-summary"); dump("19-journey-02-after-summary")

        // ---- Section 6: one persisted real-course round, hole 2 → hole 18 ----
        // Do not replace this with independent seeded screenshots. Every score below appends to the
        // same local round started above; the app is force-quit at hole 10 and must resume that identity.
        var didManualPar3 = false
        var didManualPar4 = false
        var didManualPar5 = false
        for holeNumber in 2...18 {
            var par = try waitForJourneyHole(holeNumber)

            if holeNumber == 10 {
                settle(1); save("journey-10-before-force-quit"); dump("journey-10-before-force-quit")
                app.terminate()
                app.launch()
                XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app must relaunch at mid-round")
                let inProgress = app.buttons.matching(
                    NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "进行中", "第 10 洞")
                ).firstMatch
                XCTAssertTrue(
                    inProgress.waitForExistence(timeout: 30),
                    "a force-quit must restore the same real course and active hole on the home card"
                )
                XCTAssertTrue(
                    app.staticTexts["已打 9 洞 · 共 18 洞"].exists,
                    "the restored round must retain all nine completed holes"
                )
                settle(1); save("journey-10-restored-home"); dump("journey-10-restored-home")
                inProgress.tap()
                par = try waitForJourneyHole(holeNumber)
                settle(1); save("journey-10-restored-hole"); dump("journey-10-restored-hole")
            }

            let rootName = String(format: "journey-%02d-hole-root", holeNumber)
            settle(1); save(rootName); dump(rootName)
            try recordJourneyShot(selectActualClub: holeNumber == 2)

            let manual: Bool
            let fairwayLabel: String?
            if holeNumber == 2 {
                XCTAssertEqual(par, 4, "北京丽宫第 2 洞 must retain its real Par")
                didManualPar4 = true
                manual = true
                fairwayLabel = "上球道"
            } else if par == 3, !didManualPar3 {
                didManualPar3 = true
                manual = true
                fairwayLabel = nil
            } else if par == 5, !didManualPar5 {
                didManualPar5 = true
                manual = true
                fairwayLabel = "偏左"
            } else {
                manual = false
                fairwayLabel = nil
            }
            try confirmJourneyHole(
                hole: holeNumber,
                par: par,
                manual: manual,
                fairwayLabel: fairwayLabel
            )

            if holeNumber < 18 {
                XCTAssertTrue(
                    app.staticTexts["第 \(holeNumber + 1) 洞"].waitForExistence(timeout: 15),
                    "saving hole \(holeNumber) must advance the same round to hole \(holeNumber + 1)"
                )
            }
        }

        XCTAssertTrue(didManualPar3, "the real 18-hole course must exercise Par 3's no-fairway branch")
        XCTAssertTrue(didManualPar4, "the real 18-hole course must exercise Par 4 fairway confirmation")
        XCTAssertTrue(didManualPar5, "the real 18-hole course must exercise Par 5 fairway confirmation")
        XCTAssertTrue(
            app.staticTexts["本场汇总"].waitForExistence(timeout: 8),
            "the ordered last hole must open the shared finish summary automatically"
        )
        XCTAssertTrue(app.staticTexts["已完成 18/18 洞"].exists)
        XCTAssertTrue(app.buttons["保存并结束"].exists)
        XCTAssertTrue(app.buttons["继续打球"].exists)
        settle(1); save("journey-18-complete-summary"); dump("journey-18-complete-summary")

        app.buttons["保存并结束"].tap()
        XCTAssertTrue(
            app.staticTexts["打球"].waitForExistence(timeout: 8),
            "a finished round must return to the approved product home"
        )
        XCTAssertTrue(app.staticTexts["新开一场 · 选起始 9 洞"].exists)
        XCTAssertFalse(app.navigationBars["开始一场"].exists, "finish must not strand the player in the setup form")
        XCTAssertFalse(app.staticTexts["进行中"].exists, "the explicitly finished round must no longer be active")
        settle(1); save("journey-finished-home"); dump("journey-finished-home")
    }

    // MARK: - navigation helpers

    private func launchFresh() {
        if app.state == .runningForeground { app.terminate() }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not foreground")
        // Home renders cached/fixture instantly, then the funnel fetch (Phase 2) swaps in real data.
        settle(20)
    }

    private func settle(_ seconds: TimeInterval) { Thread.sleep(forTimeInterval: seconds) }

    /// Bring the whole element into the visible safe viewport. `exists` and even `isHittable` are
    /// insufficient for a SwiftUI ScrollView: the prior prep hazard was reported hittable at y=848
    /// on an 852pt screen, leaving the actual row below the screenshot/home-indicator boundary.
    @discardableResult
    private func scrollTo(_ element: XCUIElement, maxSwipes: Int) -> Bool {
        for _ in 0..<maxSwipes {
            if element.exists, element.isHittable, fullyVisible(element) { return true }
            if element.exists, element.frame.minY < visibleSafeRect().minY {
                app.swipeDown()
            } else {
                app.swipeUp()
            }
            settle(0.6)
        }
        return element.exists && element.isHittable && fullyVisible(element)
    }

    private func visibleSafeRect() -> CGRect {
        let windowFrame = app.windows.firstMatch.frame
        var top = windowFrame.minY + 8
        let navigationBar = app.navigationBars.firstMatch
        if navigationBar.exists {
            top = max(top, navigationBar.frame.maxY + 8)
        }
        let bottom = windowFrame.maxY - 34
        return CGRect(
            x: windowFrame.minX + 8,
            y: top,
            width: max(0, windowFrame.width - 16),
            height: max(0, bottom - top)
        )
    }

    private func fullyVisible(_ element: XCUIElement) -> Bool {
        let frame = element.frame
        return !frame.isNull && !frame.isEmpty && visibleSafeRect().contains(frame)
    }

    /// `app.statusBars` is empty on the iPhone 16 simulator even while SpringBoard visibly draws the
    /// white time / Wi-Fi / battery glyphs over this app's near-black top inset. Inspect only the two
    /// top status lanes in the actual screen pixels. Mirroring these lanes at the bottom produced a
    /// false positive whenever the approved scorecard/actions occupied the lower corners.
    private func visibleStatusChromeBrightPixelFraction(in screenshot: XCUIScreenshot) -> Double {
        let lanes = [
            CGRect(x: 0.08, y: 0.015, width: 0.19, height: 0.045),
            CGRect(x: 0.68, y: 0.015, width: 0.26, height: 0.045),
        ]
        return lanes.map { brightPixelFraction(in: screenshot, normalizedRect: $0) }.max() ?? 0
    }

    private func brightPixelFraction(
        in screenshot: XCUIScreenshot,
        normalizedRect: CGRect
    ) -> Double {
        guard let image = screenshot.image.cgImage else {
            XCTFail("screen capture must expose CGImage pixels")
            return 0
        }
        let cropRect = CGRect(
            x: normalizedRect.minX * CGFloat(image.width),
            y: normalizedRect.minY * CGFloat(image.height),
            width: normalizedRect.width * CGFloat(image.width),
            height: normalizedRect.height * CGFloat(image.height)
        ).integral
        guard let crop = image.cropping(to: cropRect) else {
            XCTFail("status-chrome pixel crop must be valid")
            return 0
        }

        let bytesPerPixel = 4
        let bytesPerRow = crop.width * bytesPerPixel
        var pixels = [UInt8](repeating: 0, count: bytesPerRow * crop.height)
        let rendered = pixels.withUnsafeMutableBytes { bytes -> Bool in
            guard let context = CGContext(
                data: bytes.baseAddress,
                width: crop.width,
                height: crop.height,
                bitsPerComponent: 8,
                bytesPerRow: bytesPerRow,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.draw(crop, in: CGRect(x: 0, y: 0, width: crop.width, height: crop.height))
            return true
        }
        guard rendered else {
            XCTFail("status-chrome pixel crop must render")
            return 0
        }

        var bright = 0
        for offset in stride(from: 0, to: pixels.count, by: bytesPerPixel) {
            if pixels[offset] >= 180, pixels[offset + 1] >= 180, pixels[offset + 2] >= 180 {
                bright += 1
            }
        }
        return Double(bright) / Double(crop.width * crop.height)
    }

    private func waitUntilGone(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if !element.exists { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    /// Wait for one ordered real hole to be screenshot-ready and return its actual Par. F/M/B are
    /// identified live WGS84 readings, so a heading alone or a stale prior-hole map cannot pass.
    private func waitForJourneyHole(_ hole: Int) throws -> Int {
        let heading = app.staticTexts["第 \(hole) 洞"]
        XCTAssertTrue(heading.waitForExistence(timeout: 20), "journey must reach real hole \(hole)")
        XCTAssertTrue(scrollTo(heading, maxSwipes: 18), "hole \(hole) root must return to its map header")

        let parText = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Par '")).firstMatch
        XCTAssertTrue(parText.waitForExistence(timeout: 8), "hole \(hole) must expose its real Par")
        let tokens = parText.label.split(separator: " ")
        let par = try XCTUnwrap(tokens.dropFirst().first.flatMap { Int($0) }, "hole \(hole) Par must be numeric")

        for identifier in ["live-green-front", "live-green-middle", "live-green-back"] {
            let distance = app.staticTexts[identifier]
            XCTAssertTrue(
                waitForWholeYardValue(distance, timeout: 30),
                "hole \(hole) \(identifier) must settle to a real whole-yard range"
            )
        }
        let loading = app.activityIndicators["正在更新球童建议"]
        _ = loading.waitForExistence(timeout: 1)
        XCTAssertTrue(
            waitUntilGone(loading, timeout: 75),
            "hole \(hole) must settle its real structured caddie response before capture"
        )
        let caddieReady = app.descendants(matching: .any).matching(
            NSPredicate(format: "label == %@", "球童建议已就绪")
        ).firstMatch
        XCTAssertTrue(
            caddieReady.waitForExistence(timeout: 75),
            "hole \(hole) must expose a settled caddie-ready state before capture"
        )
        XCTAssertFalse(
            app.staticTexts["联网球童暂不可用 · 已切换到离线缓存建议。"].exists,
            "hole \(hole) must not silently replace the real journey with an offline suggestion"
        )
        return par
    }

    private func waitForWholeYardValue(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate { object, _ in
                guard let element = object as? XCUIElement, element.exists else { return false }
                return Int(element.label) != nil
            },
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    /// Record exactly the first GPS shot on each hole. Hole 2 selects an actual club; every other hole
    /// skips the optional club while retaining the location, proving both paths and per-hole order reset.
    private func recordJourneyShot(selectActualClub: Bool) throws {
        let record = app.buttons["记一杆"]
        XCTAssertTrue(scrollTo(record, maxSwipes: 18), "each journey hole must expose GPS shot capture")
        record.tap()
        XCTAssertTrue(app.staticTexts["这一杆用了什么球杆？"].waitForExistence(timeout: 5))
        XCTAssertTrue(
            app.staticTexts["第 1 杆的位置已经保存"].exists,
            "the first recorded shot order must reset to 1 on every hole"
        )
        if selectActualClub {
            let recommendedClub = app.buttons.matching(
                NSPredicate(format: "label CONTAINS %@", "球童建议")
            ).firstMatch
            XCTAssertTrue(recommendedClub.waitForExistence(timeout: 5), "actual-club prompt must expose a recommendation")
            recommendedClub.tap()
        } else {
            let skip = app.buttons["跳过球杆（位置已记录）"]
            XCTAssertTrue(skip.waitForExistence(timeout: 5))
            skip.tap()
        }
        XCTAssertTrue(app.staticTexts["已记第 1 杆"].waitForExistence(timeout: 5))
    }

    /// Complete one hole either through the one-tap recommendation or the locked manual order:
    /// total → putts → (Par 4/5 fairway only) → penalties.
    private func confirmJourneyHole(
        hole: Int,
        par: Int,
        manual: Bool,
        fairwayLabel: String?
    ) throws {
        let confirm = app.buttons["确认本洞成绩"]
        XCTAssertTrue(scrollTo(confirm, maxSwipes: 18), "hole \(hole) must expose score confirmation")
        confirm.tap()
        let accept = app.buttons.matching(NSPredicate(format: "label BEGINSWITH '接受推荐 '")).firstMatch
        XCTAssertTrue(accept.waitForExistence(timeout: 5), "hole \(hole) must offer one-tap recommendation")
        if !manual {
            accept.tap()
            return
        }

        let manualButton = app.buttons["手动确认"]
        XCTAssertTrue(manualButton.waitForExistence(timeout: 3))
        manualButton.tap()
        XCTAssertTrue(app.staticTexts["手动确认 · 总杆"].waitForExistence(timeout: 3))
        // One recorded non-putt shot recommends 3. Raise the representative manual holes to par.
        for _ in 0..<max(0, par - 3) {
            let plus = app.buttons["＋"]
            XCTAssertTrue(plus.waitForExistence(timeout: 2))
            plus.tap()
        }
        app.buttons["下一步 · 推杆"].tap()

        if par == 3 {
            XCTAssertTrue(app.buttons["下一步 · 罚杆"].waitForExistence(timeout: 3))
            XCTAssertFalse(app.buttons["下一步 · 开球结果"].exists)
            app.buttons["下一步 · 罚杆"].tap()
        } else {
            XCTAssertTrue(app.buttons["下一步 · 开球结果"].waitForExistence(timeout: 3))
            app.buttons["下一步 · 开球结果"].tap()
            let fairway = try XCTUnwrap(fairwayLabel, "Par 4/5 manual flow requires a fairway result")
            XCTAssertTrue(app.buttons[fairway].waitForExistence(timeout: 3))
            app.buttons[fairway].tap()
        }

        let saveScore = app.buttons.matching(NSPredicate(format: "label BEGINSWITH '保存'")).firstMatch
        XCTAssertTrue(saveScore.waitForExistence(timeout: 3), "hole \(hole) penalty step must save the score")
        saveScore.tap()
    }

    /// Tap the first button/cell/text whose label CONTAINS any of the given fragments.
    @discardableResult
    private func tapContaining(_ fragments: [String]) -> Bool {
        for fragment in fragments {
            let predicate = NSPredicate(format: "label CONTAINS %@", fragment)
            for query in [app.buttons, app.cells, app.staticTexts, app.otherElements] {
                let match = query.matching(predicate).firstMatch
                guard match.waitForExistence(timeout: 4) else { continue }
                let frame = match.frame
                guard !frame.isNull, !frame.isEmpty else { continue }
                if match.isHittable { match.tap(); return true }
            }
        }
        return false
    }

    /// Tap a course-segment row BUTTON (not the inner static text — that wouldn't fire the NavigationLink).
    /// The visual journey is locked to 北京丽宫, so a changing catalogue order cannot silently switch
    /// the evidence to a cold, unrelated course and block on generating a different topo bitmap.
    @discardableResult
    private func tapCourseSegment(globalId: Int) -> Bool {
        let row = app.buttons["prep-course-row-\(globalId)"]
        guard row.waitForExistence(timeout: 6), scrollTo(row, maxSwipes: 24) else { return false }
        row.tap()
        return true
    }

    /// Prefer the normal visible history row. When the five newest owner rows are CI-polluted rounds,
    /// relaunch through a DEBUG-only navigation seed so visual evidence still renders this unchanged
    /// production review surface with a known real Garmin round instead of fabricating shot geometry.
    @discardableResult
    private func openEvidenceRound(
        roundRef: String,
        courseName: String,
        date: String,
        score: Int,
        beforeOpen: () -> Void = {}
    ) -> Bool {
        let row = app.buttons.matching(
            NSPredicate(
                format: "label CONTAINS %@ AND label CONTAINS %@ AND label CONTAINS %@",
                courseName,
                date,
                String(score)
            )
        ).firstMatch
        if row.waitForExistence(timeout: 3), scrollTo(row, maxSwipes: 12) {
            beforeOpen()
            row.tap()
            return app.navigationBars["单场复盘"].waitForExistence(timeout: 12)
        }

        beforeOpen()
        app.launchEnvironment["UITEST_REVIEW_ROUND_REF"] = roundRef
        app.launchEnvironment["UITEST_REVIEW_COURSE_NAME"] = courseName
        launchFresh()
        app.launchEnvironment.removeValue(forKey: "UITEST_REVIEW_ROUND_REF")
        app.launchEnvironment.removeValue(forKey: "UITEST_REVIEW_COURSE_NAME")
        return app.navigationBars["单场复盘"].waitForExistence(timeout: 12)
    }

    // MARK: - diagnostics

    /// Writes what the test runner resolved for backend config + a live probe of the funnel, so a
    /// "still showing fixtures" result is immediately diagnosable as env-not-propagated vs.
    /// funnel-unreachable vs. bad-token (without leaking the token — only its length is recorded).
    private func writeDiagnostics() {
        let url = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        let token = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        var lines = [
            "resolvedURL=\(url)",
            "tokenLen=\(token.count)",
            "gps=\(cfg("UITEST_GPS_LAT") ?? "-"),\(cfg("UITEST_GPS_LON") ?? "-")",
        ]
        if let probeURL = URL(string: url + "/api/v2/history/summary") {
            var request = URLRequest(url: probeURL)
            request.timeoutInterval = 40
            request.setValue(token, forHTTPHeaderField: "x-ai-caddie-admin-token")
            let semaphore = DispatchSemaphore(value: 0)
            URLSession.shared.dataTask(with: request) { data, response, error in
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                lines.append("probe.status=\(code)")
                if let error { lines.append("probe.error=\(error.localizedDescription)") }
                if let data, let body = String(data: data, encoding: .utf8) {
                    lines.append("probe.body=\(String(body.prefix(240)))")
                }
                semaphore.signal()
            }.resume()
            _ = semaphore.wait(timeout: .now() + 45)
        } else {
            lines.append("probe.skipped=invalid-url")
        }
        try? lines.joined(separator: "\n").data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("diagnostics.txt"))
    }

    /// Fetches a lightweight static Tee→green benchmark from the same real prep endpoint the app
    /// consumes. Live WGS84 rangefinding may differ by a few yards from mesh-plane measurements, but
    /// a fixed prior-hole coordinate is hundreds of yards outside that small calibration tolerance.
    private func fetchPrepGreenYards(globalId: Int, hole: Int) -> [Int]? {
        guard let base = cfg("AI_CADDIE_API_BASE_URL"),
              var components = URLComponents(string: base + "/api/v2/courses/\(globalId)/prep") else {
            return nil
        }
        components.queryItems = [
            URLQueryItem(name: "holes", value: String(hole)),
            URLQueryItem(name: "render", value: "false"),
        ]
        guard let url = components.url else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 60
        request.setValue(cfg("AI_CADDIE_ADMIN_TOKEN") ?? "", forHTTPHeaderField: "x-ai-caddie-admin-token")

        var result: [Int]?
        let semaphore = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: request) { data, response, _ in
            defer { semaphore.signal() }
            guard (response as? HTTPURLResponse)?.statusCode == 200,
                  let data,
                  let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let prep = (root["holes"] as? [[String: Any]])?.first,
                  let green = prep["greenDistances"] as? [String: Any],
                  green["available"] as? Bool == true,
                  let front = green["frontM"] as? Double,
                  let middle = green["middleM"] as? Double,
                  let back = green["backM"] as? Double else { return }
            result = [front, middle, back].map { Int(($0 * 1.09361).rounded()) }
        }.resume()
        _ = semaphore.wait(timeout: .now() + 65)
        return result
    }

    // MARK: - capture helpers

    private func realShotsDir() -> URL {
        let base = (try? FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("real-screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func save(_ name: String) {
        let shot = XCUIScreen.main.screenshot()
        try? shot.pngRepresentation.write(to: realShotsDir().appendingPathComponent("\(name).png"))
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_REAL_SCREENSHOT \(name)")
    }

    private func dump(_ name: String) {
        try? app.debugDescription.data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("tree-\(name).txt"))
    }
}
