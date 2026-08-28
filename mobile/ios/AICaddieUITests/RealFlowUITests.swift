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
    /// 北京丽宫体育公园高尔夫俱乐部 in the live Garmin catalogue.
    private let approvedJourneyCourseGlobalId = 31793

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
        app.launchEnvironment["AI_CADDIE_FIXTURE_MODE"] = cfg("AI_CADDIE_FIXTURE_MODE") ?? "0"
        app.launchEnvironment["AI_CADDIE_DATA_MODE"] = cfg("AI_CADDIE_DATA_MODE") ?? ""
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
        let reviewEvidence = try resolveReviewEvidence()
        let captureScope = cfg("UITEST_CAPTURE_SCOPE") ?? "full"
        let newCourseEvidence: NewCourseEvidence?
        if captureScope == "full" {
            newCourseEvidence = try resolveNewCourseEvidence()
        } else {
            newCourseEvidence = nil
        }
        // ---- Section 1: home + the unified 成绩 destination ----
        launchFresh()
        let resultsTile = app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "成绩")
        ).firstMatch
        XCTAssertTrue(
            resultsTile.waitForExistence(timeout: 60),
            "01-home may be captured only after the real home replaces the launch screen"
        )
        settle(2)
        save("01-home"); dump("01-home")
        XCTAssertFalse(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", "Unknown course")).firstMatch.exists,
            "UI-test bootstrap must load the real home course, not auto-activate the implicit DEBUG round 900001"
        )
        XCTAssertTrue(resultsTile.isHittable, "the loaded home results tile must be tappable")
        resultsTile.tap()
        XCTAssertTrue(app.staticTexts["我的高尔夫生涯"].waitForExistence(timeout: 15))
        settle(3); save("02-results"); dump("02-results")
        XCTAssertTrue(scrollAndTapContaining(["时间趋势", "近 10 / 20 场"]))
        XCTAssertTrue(app.navigationBars["时间趋势"].waitForExistence(timeout: 10))
        settle(4); save("02b-trends"); dump("02b-trends")
        // Performance is now a first-screen feature destination above the trend/library rows.
        // Relaunch from a known top position instead of inheriting the old trend-row scroll offset
        // and swiping in the wrong direction after Back.
        launchFresh()
        let reopenedResults = tapContaining(["成绩", "球局 · 统计"])
            && app.staticTexts["我的高尔夫生涯"].waitForExistence(timeout: 15)
        XCTAssertTrue(reopenedResults, "the real home must reopen the Garmin-style activity surface")
        XCTAssertTrue(scrollAndTapContaining(["表现分析", "四阶段空间分析"]))
        XCTAssertTrue(app.navigationBars["表现分析"].waitForExistence(timeout: 10))
        settle(5); save("02c-analysis"); dump("02c-analysis")

        // ---- Section 2: 成绩 → 全部球局 → round review → shot-map → review-edit ----
        launchFresh()
        let openedResults = tapContaining(["成绩", "球局 · 统计"])
        // A fresh launch can still be committing the NavigationStack transition after the home tile
        // receives its tap. Do not start swiping the old home ScrollView while the results page is
        // entering; wait for the same live-data root marker already proved in Section 1.
        let resultsReady = openedResults
            && app.staticTexts["我的高尔夫生涯"].waitForExistence(timeout: 15)
        let enteredHistory = resultsReady
            && scrollAndTapContaining(["全部球局", "搜索 · 年份"])
        XCTAssertTrue(enteredHistory, "the real home must expose 成绩 and its complete archive")
        if enteredHistory {
            settle(6); save("03-history-list"); dump("03-history-list")
            // The low-value per-hole “规律” section was deliberately removed from history review.
            // Continue with the real round instead of requiring a chip from that retired UI.
            let enteredRoundReview = openEvidenceRound(
                roundRef: reviewEvidence.roundRef,
                courseName: reviewEvidence.courseName,
                date: reviewEvidence.date,
                score: reviewEvidence.score
            ) {
                save("03b-history-real-round"); dump("03b-history-real-round")
            }
            XCTAssertTrue(
                enteredRoundReview,
                "review evidence must open the dynamically verified spatially separated Garmin round"
            )
            if enteredRoundReview {
                // The history response can finish while the navigation transition is still committing.
                // Leave one quiet window before XCUITest starts taking repeated accessibility snapshots;
                // otherwise those snapshots can starve the already-loaded SwiftUI scorecard update.
                settle(8)
                // Match the approved edit render with a real Garmin hole whose recorded positions
                // are spatially separated and retain their actual clubs.
                let reviewNavigation = app.navigationBars["单场复盘"]
                XCTAssertTrue(
                    reviewNavigation.waitForExistence(timeout: 5),
                    "the Garmin-style review must expose its compact navigation title"
                )
                // A normally visible archive row is pushed from “全部球局”. If the verified
                // Garmin evidence row is outside the bounded archive scan, openEvidenceRound uses
                // the DEBUG-only seed whose parent is the compatibility “球场回顾” screen. Both
                // routes exercise the same production RoundReviewView, so verify the actual back
                // control and constrain it to those two legitimate parents instead of guessing
                // which evidence route the current owner history will require.
                let historyBackButton = app.navigationBars["单场复盘"].buttons.firstMatch
                XCTAssertTrue(historyBackButton.waitForExistence(timeout: 5))
                XCTAssertTrue(
                    ["全部球局", "球场回顾"].contains(historyBackButton.label),
                    "round review must return to the archive or the bounded evidence fallback"
                )
                XCTAssertTrue(historyBackButton.isHittable)
                let holeRow = app.buttons["round-review-hole-\(reviewEvidence.hole)"]
                let loadedRound = holeRow.waitForExistence(timeout: 60)
                XCTAssertTrue(loadedRound, "the real round must load its verified evidence hole")
                if loadedRound {
                    settle(2); save("04-round-review"); dump("04-round-review")
                }
                let reachableHole = loadedRound && scrollTo(holeRow, maxSwipes: 4)
                XCTAssertTrue(reachableHole, "the verified evidence hole must be tappable")
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
                        XCTAssertFalse(
                            app.staticTexts["逐杆"].exists,
                            "a drawable Garmin-style shot map must keep shot facts on the map, not repeat a list below it"
                        )
                        let layerControl = app.buttons["round-map-layer"]
                        let fitControl = app.buttons["round-map-fit"]
                        let zoomControl = app.buttons["round-map-zoom"]
                        XCTAssertTrue(
                            layerControl.waitForExistence(timeout: 5) && layerControl.isHittable,
                            "the Garmin-style review map must expose its layer menu on the map"
                        )
                        XCTAssertTrue(
                            fitControl.waitForExistence(timeout: 5) && fitControl.isHittable,
                            "the review map must expose a one-tap full-hole reset"
                        )
                        XCTAssertTrue(
                            zoomControl.waitForExistence(timeout: 5) && zoomControl.isHittable,
                            "the visible zoom affordance must be a real button"
                        )
                        zoomControl.tap()
                        let zoomedControl = app.buttons.matching(
                            NSPredicate(format: "identifier == %@ AND label CONTAINS %@", "round-map-zoom", "缩小")
                        ).firstMatch
                        XCTAssertTrue(
                            zoomedControl.waitForExistence(timeout: 3),
                            "tapping the zoom button must change the live viewport state"
                        )
                        fitControl.tap()
                        let resetZoomControl = app.buttons.matching(
                            NSPredicate(format: "identifier == %@ AND label CONTAINS %@", "round-map-zoom", "放大")
                        ).firstMatch
                        XCTAssertTrue(
                            resetZoomControl.waitForExistence(timeout: 3),
                            "full-hole reset must restore the fitted viewport before capture"
                        )
                        settle(2); save("04b-shot-map"); dump("04b-shot-map")
                    }
                    XCTAssertTrue(
                        editButton.isHittable,
                        "the loaded real shot map must expose a tappable edit action"
                    )
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
                            // The dedicated ReviewEditUITests journey exercises continuous add,
                            // move, delete and reorder. This broad journey only verifies that the
                            // old tap-to-write modal is gone and Cancel exits with zero mutation.
                            XCTAssertFalse(
                                app.navigationBars["补一杆"].exists,
                                "whole-hole draft editing must not retain the old per-shot add modal"
                            )
                            let cancelDraft = app.descendants(matching: .any)
                                .matching(identifier: "round-edit-cancel").firstMatch
                            XCTAssertTrue(cancelDraft.waitForExistence(timeout: 5) && cancelDraft.isHittable)
                            cancelDraft.tap()
                            XCTAssertTrue(
                                app.buttons["编辑"].waitForExistence(timeout: 12),
                                "Cancel must restore the read-only shot map"
                            )
                            settle(2); save("04d-edit-cancelled"); dump("04d-edit-cancelled")
                        }
                    }
                }
            }
        }

        // ---- Section 3: last-round review shortcut from home ----
        launchFresh()
        let lastRound = app.buttons.matching(identifier: "home-last-round").firstMatch
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
        XCTAssertTrue(tapContaining(["备战", "搜索 · 球童试算"]), "home must expose pre-round prep")
        XCTAssertTrue(
            app.navigationBars["备战球场"].waitForExistence(timeout: 12),
            "pre-round entry must navigate directly to the prep course picker"
        )
        XCTAssertTrue(
            app.buttons["course-catalog-nearby-action"].waitForExistence(timeout: 5),
            "pre-round planning must offer the explicit nearby-course action"
        )
        XCTAssertTrue(app.textFields["course-catalog-city-field"].exists)
        XCTAssertTrue(app.textFields["course-catalog-keyword-field"].exists)
        XCTAssertTrue(app.buttons["course-catalog-search-action"].exists)
        save("06-prep-course-search"); dump("06-prep-course-search")

        // Search for the same 北京丽宫 course used by the approved live journey. Selecting the
        // provider result enters CourseReviewView directly; no nearby/history picker sits between.
        let prepQuery = app.textFields["course-catalog-keyword-field"]
        XCTAssertTrue(scrollTo(prepQuery, maxSwipes: 8))
        prepQuery.tap()
        prepQuery.typeText("北京丽宫")
        let prepSearch = app.buttons["course-catalog-search-action"]
        XCTAssertTrue(waitUntilEnabled(prepSearch, timeout: 5))
        prepSearch.tap()
        XCTAssertTrue(waitUntilGone(app.keyboards.firstMatch, timeout: 8))
        let prepResult = app.buttons["course-catalog-result-\(approvedJourneyCourseGlobalId)"]
        XCTAssertTrue(
            scrollTo(prepResult, maxSwipes: 30),
            "pre-round name search must return the approved 北京丽宫 course"
        )
        prepResult.tap()
        XCTAssertTrue(
            app.navigationBars["备战球场"].waitForExistence(timeout: 8),
            "selecting a pre-round search result must stay in the download library"
        )
        XCTAssertFalse(
            app.navigationBars["赛前球场攻略"].exists,
            "an incomplete course package must never open the prep map"
        )

        // The course download belongs to the app, not to a detail screen. The retained row stays
        // visible immediately, then survives a process relaunch before the player opens it.
        let retainedDownload = app.buttons.matching(NSPredicate(
            format: "identifier BEGINSWITH %@",
            "prep-download-row-\(approvedJourneyCourseGlobalId):"
        )).firstMatch
        XCTAssertTrue(
            scrollTo(retainedDownload, maxSwipes: 12),
            "leaving course prep must retain the selected course in 最近选择"
        )
        XCTAssertTrue(
            nonEmptyAccessibilityValue(retainedDownload),
            "the retained course must expose its current durable download state"
        )
        settle(1); save("06b-prep-download-retained"); dump("06b-prep-download-retained")

        launchFresh()
        XCTAssertTrue(tapContaining(["备战", "搜索 · 球童试算"]))
        XCTAssertTrue(app.navigationBars["备战球场"].waitForExistence(timeout: 12))
        let relaunchedDownload = app.buttons.matching(NSPredicate(
            format: "identifier BEGINSWITH %@",
            "prep-download-row-\(approvedJourneyCourseGlobalId):"
        )).firstMatch
        XCTAssertTrue(
            scrollTo(relaunchedDownload, maxSwipes: 12),
            "process relaunch must restore the same selected course instead of restarting search"
        )
        XCTAssertTrue(
            nonEmptyAccessibilityValue(relaunchedDownload),
            "process relaunch must restore a visible queued, active, ready, or retryable state"
        )
        XCTAssertTrue(
            waitForValue("已完整下载到本机", on: relaunchedDownload, timeout: 240),
            "the prep map must remain locked until all local facts and topo assets are installed"
        )
        relaunchedDownload.tap()
        XCTAssertTrue(
            app.navigationBars["赛前球场攻略"].waitForExistence(timeout: 20),
            "the restored row must reopen the same course preparation"
        )
        let loading = app.staticTexts["加载中…"]
        _ = loading.waitForExistence(timeout: 5) // fast cache hits may finish before this appears
        let firstPrepHeader = app.descendants(matching: .any)["prep-hole-header-1"].firstMatch
        XCTAssertTrue(firstPrepHeader.waitForExistence(timeout: 60), "real course prep must load the first map header")
        XCTAssertTrue(
            waitUntilGone(loading, timeout: 60),
            "pre-round screenshot must wait for the live prep request to finish"
        )
        // Bind readiness to the selected hole. Preparation now renders one large map at a time;
        // background batches must never substitute a different hole's readiness.
        let firstPrepMap = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "prep-hole-map-1")
        ).firstMatch
        XCTAssertTrue(
            firstPrepMap.waitForExistence(timeout: 60),
            "the first visible prep card must lazily load its real single-hole map"
        )
        XCTAssertTrue(
            scrollTo(firstPrepMap, maxSwipes: 3),
            "first real prep map must be fully inside the simulator safe viewport"
        )
        let firstPrepTopoReady = firstPrepMap.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-ready")
        ).firstMatch
        XCTAssertTrue(
            firstPrepTopoReady.waitForExistence(timeout: 75),
            "pre-round evidence must wait for the real topo bitmap, not capture its loading overlay"
        )
        let firstPrepTopoLoading = firstPrepMap.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-loading")
        ).firstMatch
        XCTAssertTrue(
            waitUntilGone(firstPrepTopoLoading, timeout: 5),
            "the prep screenshot is valid only after the topo loading overlay disappears"
        )
        // SwiftUI can publish the accessibility tree one frame before the rendered hierarchy commits.
        settle(2)
        save("07-prep-card"); dump("07-prep-card")

        // The initial viewport must accept a pinch; a reset control proves that the gesture changed
        // view state rather than merely producing a transient accessibility event.
        firstPrepMap.pinch(withScale: 2.0, velocity: 1.0)
        let prepMapReset = app.buttons["prep-map-reset-rotation"]
        XCTAssertTrue(
            prepMapReset.waitForExistence(timeout: 3),
            "the precise prep map must leave its fitted state after a pinch"
        )
        prepMapReset.tap()
        XCTAssertTrue(
            waitUntilGone(prepMapReset, timeout: 3),
            "reset must return the prep viewport to its fitted state"
        )

        // I08 now proves the product rule directly: spatial facts stay on the map instead of being
        // repeated as a list below it. Accessibility binds the same measured near/far obstacle to
        // its map annotation, while additional hazards remain available through map navigation.
        let firstMapHazard = app.descendants(matching: .any)["prep-map-hazard-1"].firstMatch
        XCTAssertTrue(
            firstMapHazard.waitForExistence(timeout: 10),
            "the real prep map must expose its nearest measured 到/过 obstacle as a map overlay"
        )
        XCTAssertTrue(
            firstMapHazard.label.contains("到") && firstMapHazard.label.contains("过"),
            "the map obstacle must retain both measured near-edge and far-edge semantics"
        )
        let greenRange = app.descendants(matching: .any)["prep-map-green-range"].firstMatch
        XCTAssertTrue(
            greenRange.waitForExistence(timeout: 5),
            "the real prep map must carry F/M/B on the green rather than in a duplicate row"
        )
        settle(1)
        save("08-prep-map-overlays"); dump("08-prep-map-overlays")

        // I08b independently proves that the progressive real-course response continues to hole 2
        // and renders that hole's actual topo after explicit next-hole navigation.
        let nextPrepHole = app.buttons["prep-next-hole"]
        XCTAssertTrue(nextPrepHole.waitForExistence(timeout: 5), "prep must expose compact next-hole navigation")
        nextPrepHole.tap()
        let secondPrepHeader = app.descendants(matching: .any)["prep-hole-header-2"].firstMatch
        XCTAssertTrue(secondPrepHeader.waitForExistence(timeout: 10), "next-hole navigation must select hole 2")
        let secondPrepMap = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "prep-hole-map-2")
        ).firstMatch
        XCTAssertTrue(
            secondPrepMap.waitForExistence(timeout: 75),
            "the second prep card must finish its real rendered-map request before capture"
        )
        let secondPrepTopoReady = secondPrepMap.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-ready")
        ).firstMatch
        XCTAssertTrue(
            secondPrepTopoReady.waitForExistence(timeout: 75),
            "the scrolled prep evidence must wait for hole 2's real topo bitmap"
        )
        let secondPrepTopoLoading = secondPrepMap.descendants(matching: .any).matching(
            NSPredicate(format: "identifier == %@", "topo-hole-base-loading")
        ).firstMatch
        XCTAssertTrue(
            waitUntilGone(secondPrepTopoLoading, timeout: 5),
            "the scrolled prep evidence must not include hole 2's topo loading overlay"
        )
        settle(1)
        XCTAssertTrue(
            fullyVisible(secondPrepHeader),
            "the next-hole header must remain inside the safe viewport after the rendered map settles"
        )
        settle(1)
        save("08b-prep-next-hole"); dump("08b-prep-next-hole")

        // ---- Section 4b (full only): nearby + name search → uninstalled course → lightweight/precise map ----
        if let newCourseEvidence {
            try exerciseNewCourseDiscovery(newCourseEvidence)
        }

        // ---- Section 5: start the selected real course — GET package only, no score/backend write ----
        launchFresh()
        XCTAssertTrue(tapContaining(["打球", "开始一场"]), "home must expose the real start-round path")
        settle(9)
        // Provider-wide nearby discovery can legitimately change the form's default course. The
        // approved 18-hole evidence is Beijing Ligong, so select its stable globalId explicitly
        // instead of mistaking a visible, unselected course name for the active choice.
        let ligongSegment = app.buttons[
            "start-round-course-segment-\(approvedJourneyCourseGlobalId)"
        ]
        XCTAssertTrue(
            scrollTo(ligongSegment, maxSwipes: 24),
            "the full journey must expose the approved 北京丽宫 course segment"
        )
        if ligongSegment.value as? String != "已选择" {
            ligongSegment.tap()
            settle(1)
        }
        XCTAssertEqual(ligongSegment.value as? String, "已选择")
        let ligongPrimary = app.buttons["start-round-primary-action"]
        XCTAssertTrue(
            waitUntilEnabled(ligongPrimary, timeout: 90),
            "explicitly selected 北京丽宫 must finish loading its real Tee metadata"
        )
        XCTAssertTrue(scrollTo(ligongPrimary, maxSwipes: 20))
        ligongPrimary.tap()
        let enteredFirstHole = app.staticTexts["第 1 洞"].waitForExistence(timeout: 90)
        if !enteredFirstHole {
            save("10-live-start-failed")
            dump("10-live-start-failed")
        }
        XCTAssertTrue(
            enteredFirstHole,
            "cold-loaded 北京丽宫 must enter its factual first hole"
        )
        try assertLiveGreenDistancesMatchPrep(
            globalId: approvedJourneyCourseGlobalId,
            hole: 1,
            timeout: 30
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
            liveWindowFrame.height * 0.60,
            "the approved map-first live screen keeps at least three fifths of the first glance for the factual hole map"
        )
        XCTAssertLessThanOrEqual(
            livePlayPanel.frame.minY,
            liveWindowFrame.height * 0.68,
            "the data panel must still begin soon enough for every primary live action to remain in the first glance"
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
        let liveCaddieLoading = app.activityIndicators["正在更新球童建议"]
        _ = liveCaddieLoading.waitForExistence(timeout: 2) // a warm backend may finish before this appears
        XCTAssertTrue(
            waitUntilGone(liveCaddieLoading, timeout: 75),
            "live-hole evidence must wait for the structured caddie decision instead of freezing its loading spinner"
        )
        save("10-live-hole"); dump("10-live-hole")
        XCTAssertTrue(app.staticTexts["第 1 洞"].exists, "starting 北京丽宫 must enter its real first hole")
        for identifier in ["live-green-front", "live-green-middle", "live-green-back"] {
            XCTAssertTrue(
                waitForWholeYardValue(app.staticTexts[identifier], timeout: 5),
                "settled live-hole evidence must retain all three identified green distances"
            )
        }
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
        for label in ["推荐打法", "保守打法", "进攻打法"] {
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
            scrollTo(app.staticTexts["推荐打法"], maxSwipes: 12),
            "the selected full-hole club chain must be visible in the simulator evidence"
        )
        settle(1); save("11-caddie-plan"); dump("11-caddie-plan")

        let avoidZones = app.buttons["备选打法 · 避开区"]
        XCTAssertTrue(scrollTo(avoidZones, maxSwipes: 8), "full caddie plan must expose avoid zones")
        avoidZones.tap()
        let avoidZonesHeading = app.staticTexts["避开区"]
        XCTAssertTrue(scrollTo(avoidZonesHeading, maxSwipes: 8), "expanded avoid zones must be visible")
        for label in ["推荐打法", "保守打法", "进攻打法"] {
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

        // Looking at a recommendation must never commit it. Cancel once, prove the recorded GPS shot
        // and active hole are intact, then reopen the same confirmation and accept it.
        let cancelScore = app.buttons["取消"]
        XCTAssertTrue(cancelScore.waitForExistence(timeout: 3))
        cancelScore.tap()
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["已记第 1 杆"].exists)
        XCTAssertTrue(saveHoleButton.waitForExistence(timeout: 5) && saveHoleButton.isHittable)
        settle(1); save("12b-score-cancelled"); dump("12b-score-cancelled")
        saveHoleButton.tap()
        XCTAssertTrue(acceptRecommendation.waitForExistence(timeout: 5))
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
        try assertLiveGreenDistancesMatchPrep(
            globalId: approvedJourneyCourseGlobalId,
            hole: 2,
            timeout: 30
        )
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

        let selectFirstHole = app.buttons["选择第 1 洞"].firstMatch
        XCTAssertTrue(
            selectFirstHole.waitForExistence(timeout: 5) && selectFirstHole.isHittable,
            "editing a historical score must start by selecting that hole in the scorecard"
        )
        selectFirstHole.tap()
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
        XCTAssertTrue(
            app.staticTexts["当前正在记录"].exists,
            "scorecard must still describe its selected hole as the active playing hole"
        )
        let goToCurrentHole = app.buttons["live-scorecard-go-hole"]
        XCTAssertTrue(goToCurrentHole.exists)
        XCTAssertEqual(goToCurrentHole.label, "去第 2 洞")
        XCTAssertFalse(
            goToCurrentHole.isEnabled,
            "saving a historical score edit must keep hole 2 active, so going to hole 2 remains disabled"
        )
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
        var didManualFairwayRight = false
        var didPersistAdjustedPuttsAndPenalty = false
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
            } else if par != 3, !didManualFairwayRight {
                didManualFairwayRight = true
                manual = true
                fairwayLabel = "偏右"
            } else {
                manual = false
                fairwayLabel = nil
            }
            try confirmJourneyHole(
                hole: holeNumber,
                par: par,
                manual: manual,
                fairwayLabel: fairwayLabel,
                puttsAdjustment: holeNumber == 2 ? -1 : 0,
                penaltyAdjustment: holeNumber == 2 ? 1 : 0
            )
            if holeNumber == 2 {
                didPersistAdjustedPuttsAndPenalty = true
            }

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
        XCTAssertTrue(didManualFairwayRight, "the real journey must save the missed-right fairway branch")
        XCTAssertTrue(
            didPersistAdjustedPuttsAndPenalty,
            "the real journey must change and save putts and penalties instead of only visiting their steps"
        )
        XCTAssertTrue(
            app.staticTexts["本场汇总"].waitForExistence(timeout: 8),
            "the ordered last hole must open the shared finish summary automatically"
        )
        XCTAssertTrue(app.staticTexts["已完成 18/18 洞"].exists)
        XCTAssertTrue(app.buttons["保存并结束"].exists)
        XCTAssertTrue(app.buttons["继续打球"].exists)
        XCTAssertEqual(
            app.descendants(matching: .any)["live-finish-putts"].label,
            "推杆 35",
            "the adjusted putt count must survive every hole transition and the hole-10 relaunch"
        )
        XCTAssertEqual(
            app.descendants(matching: .any)["live-finish-penalties"].label,
            "罚杆 1",
            "the non-zero penalty must survive every hole transition and the hole-10 relaunch"
        )
        XCTAssertEqual(
            app.descendants(matching: .any)["live-finish-fairways"].label,
            "球道 2/4",
            "the earlier history edit plus hit, missed-left and missed-right must all persist"
        )
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

        // The last home package deliberately still describes 北京丽宫.  Starting that same course
        // immediately must create a distinct round and enter hole 1 instead of comparing the home
        // package id, deciding “not new”, and remaining forever on the preparation screen.
        XCTAssertTrue(tapContaining(["打球", "开始一场"]))
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 12))
        let repeatSegment = app.buttons[
            "start-round-course-segment-\(approvedJourneyCourseGlobalId)"
        ]
        XCTAssertTrue(scrollTo(repeatSegment, maxSwipes: 24))
        if repeatSegment.value as? String != "已选择" {
            repeatSegment.tap()
        }
        XCTAssertEqual(repeatSegment.value as? String, "已选择")
        let repeatStart = app.buttons["start-round-primary-action"]
        XCTAssertTrue(waitUntilEnabled(repeatStart, timeout: 90))
        XCTAssertTrue(scrollTo(repeatStart, maxSwipes: 20))
        repeatStart.tap()
        XCTAssertTrue(
            app.staticTexts["第 1 洞"].waitForExistence(timeout: 90),
            "the same course must be startable again immediately after finish"
        )
        try assertLiveGreenDistancesMatchPrep(
            globalId: approvedJourneyCourseGlobalId,
            hole: 1,
            timeout: 60
        )
        settle(1); save("journey-same-course-restarted"); dump("journey-same-course-restarted")
    }

    /// Proves the complete empty-cache path without replacing the existing 北京丽宫 18-hole
    /// journey: nearby and name search must resolve the same provider row; only the selected row is
    /// prepared; its factual lightweight map appears first and upgrades in place; a force-quit keeps
    /// the same course/hole; one real local score remains editable; explicit finish removes it again.
    private func exerciseNewCourseDiscovery(_ evidence: NewCourseEvidence) throws {
        launchFresh()
        XCTAssertTrue(tapContaining(["打球", "开始一场"]), "home must expose the new-course start path")
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 12))

        let openSearch = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(scrollTo(openSearch, maxSwipes: 20), "start form must expose full-catalogue search")
        openSearch.tap()
        let openedCourseSearch = app.navigationBars["找球场"].waitForExistence(timeout: 8)
        if !openedCourseSearch {
            save("09-course-search-sheet-missing")
            dump("09-course-search-sheet-missing")
        }
        XCTAssertTrue(openedCourseSearch, "the visible catalogue action must present the course-search sheet")

        let radius = app.segmentedControls.firstMatch.buttons["\(evidence.radiusKm) km"]
        XCTAssertTrue(radius.waitForExistence(timeout: 5), "nearby search must expose the resolver radius")
        radius.tap()
        let nearby = app.buttons["course-catalog-nearby-action"]
        XCTAssertTrue(waitUntilEnabled(nearby, timeout: 20), "simulated GPS must enable nearby discovery")
        nearby.tap()

        // Do not start scrolling the lazy result List while the provider request is still in
        // flight. If the first swipes happen against the empty state, a top-ranked row can be
        // inserted above the current viewport and never enter XCUITest's accessibility tree. Wait
        // for the stable result section instead of requiring the transient loading label: a cache
        // hit can legitimately complete too quickly for XCUITest to observe "正在查找".
        XCTAssertTrue(
            app.staticTexts["附近结果"].waitForExistence(timeout: 90),
            "nearby discovery must populate its result section before result navigation"
        )

        let result = app.buttons["course-catalog-result-\(evidence.globalId)"]
        XCTAssertTrue(
            scrollTo(result, maxSwipes: 60),
            "nearby results must contain the resolver-verified uninstalled course"
        )
        XCTAssertEqual(
            result.value as? String,
            "选择后下载",
            "a provider-wide row must remain metadata-only until selected"
        )
        settle(1); save("09-new-course-nearby"); dump("09-new-course-nearby")
        result.tap()

        let selectedSegment = app.buttons["start-round-course-segment-\(evidence.globalId)"]
        XCTAssertTrue(selectedSegment.waitForExistence(timeout: 12))
        XCTAssertEqual(selectedSegment.value as? String, "已选择")
        let primary = app.buttons["start-round-primary-action"]
        XCTAssertTrue(
            waitUntilEnabled(primary, timeout: 90),
            "selecting one nearby row must fetch only that course's real Tee metadata and enable start"
        )

        // Re-open the same product search and prove the identical globalId is also discoverable by
        // name. Re-selecting it must retain the Tee authority already fetched above.
        XCTAssertTrue(scrollTo(openSearch, maxSwipes: 20))
        openSearch.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        let queryField = app.textFields["course-catalog-keyword-field"]
        XCTAssertTrue(scrollTo(queryField, maxSwipes: 12))
        queryField.tap()
        queryField.typeText(evidence.searchQuery)
        let manualSearch = app.buttons["course-catalog-search-action"]
        XCTAssertTrue(waitUntilEnabled(manualSearch, timeout: 5))
        manualSearch.tap()
        XCTAssertTrue(
            waitUntilGone(app.keyboards.firstMatch, timeout: 8),
            "submitting a course search must dismiss the keyboard so results are visible"
        )
        let namedResult = app.buttons["course-catalog-result-\(evidence.globalId)"]
        XCTAssertTrue(
            scrollTo(namedResult, maxSwipes: 60),
            "name search must return the same provider globalId selected from nearby"
        )
        XCTAssertEqual(namedResult.value as? String, "选择后下载")
        settle(1); save("09b-new-course-name-search"); dump("09b-new-course-name-search")
        namedResult.tap()
        XCTAssertTrue(selectedSegment.waitForExistence(timeout: 12))
        XCTAssertEqual(selectedSegment.value as? String, "已选择")
        XCTAssertTrue(
            waitUntilEnabled(primary, timeout: 20),
            "re-selecting the same course must not clear Tees and strand the start action"
        )
        XCTAssertTrue(scrollTo(primary, maxSwipes: 20))
        settle(1); save("09c-new-course-ready-to-start"); dump("09c-new-course-ready-to-start")
        primary.tap()

        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 90))
        let partialMap = app.descendants(matching: .any)["live-hole-map-partial"].firstMatch
        let topoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        let firstFactualMap = app.descendants(matching: .any).matching(
            NSPredicate(
                format: "identifier IN %@",
                ["live-hole-map-partial", "topo-hole-base-ready"]
            )
        ).firstMatch
        XCTAssertTrue(
            firstFactualMap.waitForExistence(timeout: 90),
            "a new course must render either factual CourseView vectors or an already-finished precise topo"
        )
        let observedLightweightMap = partialMap.exists
        if observedLightweightMap {
            XCTAssertTrue(
                app.descendants(matching: .any)["live-map-preparing"].firstMatch
                    .waitForExistence(timeout: 5),
                "a partial Garmin map must disclose that precise hazard facts are still preparing"
            )
            XCTAssertFalse(
                app.staticTexts.matching(
                    NSPredicate(format: "label CONTAINS ' · 到 ' AND (label BEGINSWITH '水域' OR label BEGINSWITH '沙坑')")
                ).firstMatch.exists,
                "an incomplete CourseView hazard subset must not masquerade as the nearest precise hazard"
            )
            settle(1); save("09d-new-course-lightweight-map"); dump("09d-new-course-lightweight-map")
        }

        XCTAssertTrue(
            topoReady.waitForExistence(timeout: 300),
            "the same live hole must finish with the precise topo"
        )
        if observedLightweightMap {
            XCTAssertTrue(
                waitUntilGone(partialMap, timeout: 10),
                "the precise topo must replace the observed lightweight map in place"
            )
            XCTAssertTrue(
                waitUntilGone(app.descendants(matching: .any)["live-map-preparing"].firstMatch, timeout: 10),
                "the preparing disclosure must leave with the partial map"
            )
        }
        settle(1); save("09e-new-course-precise-map"); dump("09e-new-course-precise-map")

        // No score has been written yet. The durable live cursor created by Start must still restore
        // this exact selected course at hole 1 after process death.
        app.terminate()
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30))
        let inProgress = app.buttons["home-in-progress-round"]
        XCTAssertTrue(inProgress.waitForExistence(timeout: 60), "new-course round must survive force-quit")
        XCTAssertTrue(inProgress.label.contains(evidence.name), "restored card must retain the selected course")
        XCTAssertTrue(inProgress.label.contains("第 1 洞"), "unplayed restored round must remain on hole 1")
        settle(1); save("09f-new-course-restored-home"); dump("09f-new-course-restored-home")
        inProgress.tap()
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 20))
        XCTAssertTrue(
            app.descendants(matching: .any)
                .matching(identifier: "topo-hole-base-ready").firstMatch
                .waitForExistence(timeout: 90),
            "restored new-course round must reopen the same precise first-hole map"
        )

        let parText = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Par '")).firstMatch
        XCTAssertTrue(parText.waitForExistence(timeout: 8))
        let par = try XCTUnwrap(
            parText.label.split(separator: " ").dropFirst().first.flatMap { Int($0) },
            "new-course hole 1 Par must be factual"
        )
        try recordJourneyShot(selectActualClub: false)
        try confirmJourneyHole(hole: 1, par: par, manual: false, fairwayLabel: nil)
        let restoredFirstHoleHeading = app.staticTexts["第 1 洞"]
        let restoredSecondHoleHeading = app.staticTexts["第 2 洞"]
        XCTAssertTrue(restoredSecondHoleHeading.waitForExistence(timeout: 20))
        XCTAssertTrue(
            waitUntilGone(restoredFirstHoleHeading, timeout: 12),
            "accepting the restored first-hole score must finish replacing the old live-hole view"
        )
        XCTAssertTrue(
            fullyVisible(restoredSecondHoleHeading),
            "the replacement second-hole view must finish resetting to its visible map/header before navigation"
        )

        // Re-query the action only after the id-keyed CurrentHoleView replacement and score-sheet
        // dismissal have both completed. Tapping the outgoing view can synthesize successfully while
        // losing the presentation request with that view's lifecycle.
        let scorecard = app.buttons["本场计分卡"]
        XCTAssertTrue(scrollTo(scorecard, maxSwipes: 18))
        scorecard.tap()
        let scorecardEdit = app.buttons["live-scorecard-edit-hole"]
        XCTAssertTrue(
            scorecardEdit.waitForExistence(timeout: 5),
            "the unique scorecard edit action must prove the scorecard sheet was presented"
        )
        XCTAssertEqual(
            scorecardEdit.label,
            "编辑第 2 洞成绩",
            "a newly opened scorecard must select the active playing hole"
        )
        let selectCompletedFirstHole = app.buttons["选择第 1 洞"].firstMatch
        XCTAssertTrue(
            selectCompletedFirstHole.waitForExistence(timeout: 5) && selectCompletedFirstHole.isHittable,
            "the completed first hole must remain selectable from the active second hole"
        )
        selectCompletedFirstHole.tap()
        let editCompletedFirstHole = app.buttons["编辑第 1 洞成绩"]
        XCTAssertTrue(
            editCompletedFirstHole.waitForExistence(timeout: 5),
            "selecting the completed first hole must retarget the unique edit action"
        )
        settle(1); save("09g-new-course-scorecard"); dump("09g-new-course-scorecard")
        editCompletedFirstHole.tap()
        XCTAssertTrue(app.staticTexts["手动确认 · 总杆"].waitForExistence(timeout: 5))
        settle(1); save("09h-new-course-score-edit"); dump("09h-new-course-score-edit")
        app.buttons["取消"].tap()
        XCTAssertTrue(app.staticTexts["第 2 洞"].waitForExistence(timeout: 8))

        let manageRound = app.buttons["球局调整 · 加打 / 结束本场"]
        XCTAssertTrue(scrollTo(manageRound, maxSwipes: 18))
        manageRound.tap()
        let finishRound = app.buttons["结束本场"].firstMatch
        XCTAssertTrue(scrollTo(finishRound, maxSwipes: 6))
        finishRound.tap()
        XCTAssertTrue(app.staticTexts["本场汇总"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["已完成 1/\(evidence.holes) 洞"].exists)
        app.buttons["保存并结束"].tap()
        XCTAssertTrue(app.staticTexts["打球"].waitForExistence(timeout: 10))
        XCTAssertTrue(
            waitUntilGone(app.buttons["home-in-progress-round"], timeout: 8),
            "local UI-test cleanup must remove only the temporary new-course round"
        )
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

    @discardableResult
    private func tapBackButton(_ label: String) -> Bool {
        let button = app.navigationBars.buttons[label].firstMatch
        guard button.waitForExistence(timeout: 6), button.isHittable else { return false }
        button.tap()
        settle(2)
        return true
    }

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

    private func waitUntilEnabled(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if element.exists, element.isEnabled { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND enabled == true"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func waitForValue(_ expected: String, on element: XCUIElement, timeout: TimeInterval) -> Bool {
        if element.exists, (element.value as? String) == expected { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND value == %@", expected),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func nonEmptyAccessibilityValue(_ element: XCUIElement) -> Bool {
        guard element.exists, let value = element.value as? String else { return false }
        return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
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
        let topoReady = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        XCTAssertTrue(
            topoReady.waitForExistence(timeout: 90),
            "hole \(hole) must finish its precise topo instead of treating a fallback map as complete"
        )
        let topoLoading = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-loading").firstMatch
        XCTAssertTrue(
            waitUntilGone(topoLoading, timeout: 5),
            "hole \(hole) must not retain the topo loading overlay in its runtime evidence"
        )
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

    /// Compare the identified live WGS84 ranges with the Garmin mesh-plane benchmark for the same
    /// hole. They should identify the same Tee and green, but are not expected to be byte-identical:
    /// Beijing Ligong hole 1, for example, is 365 yd live versus 363 yd in the static prep mesh.
    private func assertLiveGreenDistancesMatchPrep(
        globalId: Int,
        hole: Int,
        timeout: TimeInterval
    ) throws {
        let staticYards = try XCTUnwrap(
            fetchPrepGreenYards(globalId: globalId, hole: hole),
            "the live backend must expose real static F/M/B facts for course \(globalId) hole \(hole)"
        )
        let identifiers = ["live-green-front", "live-green-middle", "live-green-back"]
        for (identifier, benchmark) in zip(identifiers, staticYards) {
            let distance = app.staticTexts[identifier]
            XCTAssertTrue(
                waitForWholeYardValue(distance, timeout: timeout),
                "hole \(hole) must settle its identified live F/M/B distance \(identifier) to whole yards"
            )
            let liveYards = try XCTUnwrap(Int(distance.label), "\(identifier) must expose whole yards")
            let tolerance = max(8, Int(ceil(Double(benchmark) * 0.02)))
            XCTAssertLessThanOrEqual(
                abs(liveYards - benchmark),
                tolerance,
                "hole \(hole) must use its own Tee/green (live \(liveYards), static \(benchmark))"
            )
        }
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
        fairwayLabel: String?,
        puttsAdjustment: Int = 0,
        penaltyAdjustment: Int = 0
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
        XCTAssertTrue(app.staticTexts["手动确认 · 推杆"].waitForExistence(timeout: 3))
        for _ in 0..<abs(puttsAdjustment) {
            let button = app.buttons[puttsAdjustment < 0 ? "−" : "＋"]
            XCTAssertTrue(button.waitForExistence(timeout: 2))
            button.tap()
        }

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

        XCTAssertTrue(app.staticTexts["手动确认 · 罚杆"].waitForExistence(timeout: 3))
        for _ in 0..<abs(penaltyAdjustment) {
            let button = app.buttons[penaltyAdjustment < 0 ? "−" : "＋"]
            XCTAssertTrue(button.waitForExistence(timeout: 2))
            button.tap()
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

    /// Results drill-down rows sit below the first viewport. Scroll deliberately so the journey
    /// does not pass only when an earlier section failed to load and made the page artificially short.
    @discardableResult
    private func scrollAndTapContaining(_ fragments: [String], maxSwipes: Int = 4) -> Bool {
        for attempt in 0...maxSwipes {
            for fragment in fragments {
                let predicate = NSPredicate(format: "label CONTAINS %@", fragment)
                for query in [app.buttons, app.cells, app.staticTexts, app.otherElements] {
                    let match = query.matching(predicate).firstMatch
                    // SwiftUI can report the bottom feature cards hittable while their last few
                    // points still sit under the home-indicator lane. Bring the whole target into
                    // the safe viewport before tapping the same card a player sees.
                    if match.exists, scrollTo(match, maxSwipes: 1) { match.tap(); return true }
                }
            }
            guard attempt < maxSwipes else { break }
            app.swipeUp()
            settle(1)
        }
        return false
    }

    /// Prefer the normal visible history row. When the five newest owner rows are CI-polluted rounds,
    /// relaunch through a DEBUG-only navigation seed so visual evidence still renders this unchanged
    /// production review surface with a known real Garmin round instead of fabricating shot geometry.
    @discardableResult
    private func openEvidenceRound(
        roundRef: String,
        courseName: String,
        date: String?,
        score: Int?,
        beforeOpen: () -> Void = {}
    ) -> Bool {
        if let date, let score {
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
        }

        beforeOpen()
        app.launchEnvironment["UITEST_REVIEW_ROUND_REF"] = roundRef
        app.launchEnvironment["UITEST_REVIEW_COURSE_NAME"] = courseName
        launchFresh()
        app.launchEnvironment.removeValue(forKey: "UITEST_REVIEW_ROUND_REF")
        app.launchEnvironment.removeValue(forKey: "UITEST_REVIEW_COURSE_NAME")
        return app.navigationBars["单场复盘"].waitForExistence(timeout: 12)
    }

    private func resolveReviewEvidence() throws -> RealEvidenceRound {
        let resolver = try RealEvidenceRoundResolver(
            baseURL: cfg("AI_CADDIE_API_BASE_URL") ?? "",
            adminToken: cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        )
        let evidence: RealEvidenceRound
        do {
            evidence = try resolver.resolve(preferredRoundRef: cfg("UITEST_REVIEW_ROUND_REF"))
        } catch {
            if let data = resolver.diagnosticsText.data(using: .utf8) {
                try? data.write(to: realShotsDir().appendingPathComponent("review-evidence-rejections.txt"))
            }
            throw error
        }
        if let data = evidence.diagnosticText.data(using: .utf8) {
            try data.write(to: realShotsDir().appendingPathComponent("review-evidence-round.txt"))
        }
        return evidence
    }

    private func resolveNewCourseEvidence() throws -> NewCourseEvidence {
        let latitude = try XCTUnwrap(
            Double(cfg("UITEST_GPS_LAT") ?? ""),
            "new-course evidence requires the simulated latitude"
        )
        let longitude = try XCTUnwrap(
            Double(cfg("UITEST_GPS_LON") ?? ""),
            "new-course evidence requires the simulated longitude"
        )
        let resolver = try NewCourseEvidenceResolver(
            baseURL: cfg("AI_CADDIE_API_BASE_URL") ?? "",
            adminToken: cfg("AI_CADDIE_ADMIN_TOKEN") ?? "",
            latitude: latitude,
            longitude: longitude
        )
        let evidence = try resolver.resolve()
        if let data = evidence.diagnosticText.data(using: .utf8) {
            try data.write(to: realShotsDir().appendingPathComponent("new-course-evidence.txt"))
        }
        return evidence
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
        // Probe liveness only. `/history/summary` performs a full owner statistics build and can
        // take longer than the product flow itself when another real-course run is active.
        if let probeURL = URL(string: url + "/api/v2/health") {
            var request = URLRequest(url: probeURL)
            request.timeoutInterval = 10
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
            _ = semaphore.wait(timeout: .now() + 15)
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
