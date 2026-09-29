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
    /// Captured from the product's selected-course row so the relaunch assertion follows the
    /// same localized display name that the player saw, rather than duplicating the app's alias map
    /// in the UI test.
    private var selectedNewCourseDisplayName: String?
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
        for key in UITestBackendLaunchConfiguration.markerKeys {
            app.launchEnvironment.removeValue(forKey: key)
        }
        app.launchEnvironment.merge(
            UITestBackendLaunchConfiguration.markers(
                fixtureMode: cfg("AI_CADDIE_FIXTURE_MODE"),
                dataMode: cfg("AI_CADDIE_DATA_MODE")
            )
        ) { _, new in new }
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
                    // B3 presents the hole full screen with the navigation bar hidden. Its glass close
                    // button is the stable, user-visible proof that presentation occurred.
                    let closeButton = app.buttons["round-shot-map-close"]
                    let enteredShotMap = closeButton.waitForExistence(timeout: 12)
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
                    let editButton = app.buttons["round-edit-begin"]
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
                        XCTAssertTrue(
                            app.descendants(matching: .any).matching(identifier: "round-shot-score-box").firstMatch.exists,
                            "the full-screen hole must show its glass score box"
                        )
                        // The 18-hole strip replaces the old previous/next controls; the open hole is selected.
                        let stripCell = app.buttons["round-hole-strip-\(reviewEvidence.hole)"]
                        XCTAssertTrue(
                            stripCell.waitForExistence(timeout: 5) && stripCell.isSelected,
                            "the bottom score strip must mark the open evidence hole"
                        )
                        // B3 keeps exactly one control on the read-only map: show / hide labels.
                        for retired in ["round-map-layer", "round-map-fit", "round-map-zoom"] {
                            XCTAssertFalse(
                                app.buttons[retired].exists,
                                "the review map must not bring back the retired \(retired) control"
                            )
                        }
                        let labelsControl = app.buttons["round-map-labels"]
                        XCTAssertTrue(
                            labelsControl.waitForExistence(timeout: 5) && labelsControl.isHittable,
                            "the review map must expose its show / hide labels control on the map"
                        )
                        XCTAssertEqual(labelsControl.label, "隐藏标签", "shot labels must start visible")
                        let shotLabels = app.descendants(matching: .any).matching(
                            NSPredicate(format: "identifier BEGINSWITH %@", "round-map-shot-")
                        )
                        XCTAssertTrue(
                            shotLabels.firstMatch.waitForExistence(timeout: 5),
                            "club-labelled evidence landings must show their 球杆 码数 labels"
                        )
                        // B3 label contract: club plus the shot's yards ("一号木 221"), computed from
                        // the shot's real start and landing. A club-only label means the geometry is
                        // missing an endpoint.
                        let yardLabels = shotLabels.allElementsBoundByIndex.filter { label in
                            label.label.range(of: #"\S+ \d{1,3}$"#, options: .regularExpression) != nil
                        }
                        XCTAssertFalse(
                            yardLabels.isEmpty,
                            "shot labels must carry the club and the yards, got \(shotLabels.allElementsBoundByIndex.map(\.label))"
                        )
                        labelsControl.tap()
                        let hiddenLabels = app.buttons.matching(
                            NSPredicate(format: "identifier == %@ AND label == %@", "round-map-labels", "显示标签")
                        ).firstMatch
                        XCTAssertTrue(
                            hiddenLabels.waitForExistence(timeout: 3),
                            "tapping the labels control must hide the shot labels"
                        )
                        XCTAssertTrue(
                            waitUntilGone(shotLabels.firstMatch, timeout: 3),
                            "hidden labels must leave the map"
                        )
                        labelsControl.tap()
                        let shownLabels = app.buttons.matching(
                            NSPredicate(format: "identifier == %@ AND label == %@", "round-map-labels", "隐藏标签")
                        ).firstMatch
                        XCTAssertTrue(
                            shownLabels.waitForExistence(timeout: 3),
                            "tapping the labels control again must restore the shot labels"
                        )
                        // Pinch / double-tap zoom stays on the map itself; double-tap zooms in and
                        // a second double-tap restores the fitted full hole before capture.
                        // The accessibility frame does not follow `scaleEffect`, so the viewport
                        // publishes its zoom state on a dedicated marker.
                        let zoomState = app.descendants(matching: .any)["round-map-zoom-state"]
                        XCTAssertTrue(zoomState.waitForExistence(timeout: 3))
                        XCTAssertEqual(zoomState.value as? String, "全洞")
                        topoReady.doubleTap()
                        XCTAssertTrue(
                            waitForValue("已放大", on: zoomState, timeout: 3),
                            "a double-tap must zoom the live viewport"
                        )
                        topoReady.doubleTap()
                        XCTAssertTrue(
                            waitForValue("全洞", on: zoomState, timeout: 3),
                            "a second double-tap must restore the fitted full hole"
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
                        let editMap = app.descendants(matching: .any)
                            .matching(identifier: "round-shot-edit-map").firstMatch
                        let puttsPlus = app.buttons["round-edit-putts-plus"]
                        let loadedEditMap = editTopoReady.waitForExistence(timeout: 75)
                            && editMap.waitForExistence(timeout: 12)
                            && puttsPlus.waitForExistence(timeout: 12)
                        XCTAssertTrue(loadedEditMap, "edit evidence requires the real topo, the in-place edit map and the bottom edit bar")
                        if loadedEditMap {
                            XCTAssertFalse(closeButton.exists, "editing must hide the close button; Cancel and Save are the only exits")
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
                                app.buttons["round-edit-begin"].waitForExistence(timeout: 12),
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
            // This section deliberately removes the injected fix for its restore/no-GPS proof.
            // Keep the following approved-course journey deterministic instead of letting that
            // scenario's launch environment hide the nearby catalogue row.
            defer { restoreDefaultGPSLaunchEnvironment() }
            try exerciseNewCourseDiscovery(newCourseEvidence)
        }

        // ---- Section 5: start the selected real course — GET package only, no score/backend write ----
        launchFresh()
        XCTAssertTrue(openStartRound(), "home must expose the real start-round path")
        settle(9)
        // Provider-wide nearby discovery can legitimately change the form's default course. The
        // approved 18-hole evidence is Beijing Ligong, so select its stable globalId explicitly
        // (its row in the one course list, then its "18 洞" tile) instead of mistaking a visible,
        // unselected course name for the active choice.
        let ligongSegment = selectStartCourse(approvedJourneyCourseGlobalId)
        XCTAssertTrue(
            ligongSegment.exists,
            "the full journey must expose the approved 北京丽宫 course"
        )
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
        // B1: the top-left circle opens the round scorecard (which also holds 回到首页 / 结束本场).
        let liveBackButton = app.buttons["计分卡"]
        XCTAssertTrue(
            liveBackButton.waitForExistence(timeout: 5),
            "immersive live play must retain an explicit way back through the scorecard"
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
        // B1 (live-play.html): the factual hole map fills the screen. No bottom panel or action dock;
        // 完成本洞 (记分) floats bottom-left and the single white 记一杆 bottom-right.
        XCTAssertFalse(app.descendants(matching: .any)["live-play-panel-anchor"].firstMatch.exists)
        XCTAssertFalse(app.descendants(matching: .any)["live-action-dock"].firstMatch.exists)
        let liveRecordShot = app.buttons["记一杆"]
        let liveScoreHole = app.buttons["完成本洞"]
        XCTAssertTrue(liveRecordShot.waitForExistence(timeout: 5) && liveScoreHole.exists)
        XCTAssertGreaterThan(liveRecordShot.frame.minX, liveWindowFrame.width * 0.6, "记一杆 sits bottom-right")
        XCTAssertGreaterThan(liveRecordShot.frame.minY, liveWindowFrame.height * 0.78, "记一杆 sits bottom-right")
        XCTAssertLessThan(liveScoreHole.frame.maxX, liveWindowFrame.width * 0.4, "完成本洞 sits bottom-left")
        XCTAssertGreaterThan(liveScoreHole.frame.minY, liveWindowFrame.height * 0.78, "完成本洞 sits bottom-left")
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
            fullyVisible(app.buttons["完成本洞"]),
            "score confirmation must remain fully visible beside the shot action"
        )
        XCTAssertTrue(
            fullyVisible(app.buttons["计分卡"]),
            "the real scorecard action must be fully visible in the top-left corner"
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
        let firstSelectedHazard = app.descendants(matching: .any)["selected-hazard-1"].firstMatch
        let hazardToggle = app.buttons["live-hazard-toggle"]
        XCTAssertTrue(
            hazardToggle.waitForExistence(timeout: 8),
            "the live map must expose an explicit obstacle control"
        )
        XCTAssertFalse(
            firstSelectedHazard.exists,
            "obstacle geometry and distances stay hidden until the player selects one"
        )
        hazardToggle.tap()
        XCTAssertTrue(
            firstSelectedHazard.waitForExistence(timeout: 8),
            "the obstacle control must expose one selected outline without navigating away"
        )
        XCTAssertFalse(
            firstSelectedHazard.frame.intersects(liveRecordShot.frame)
                || firstSelectedHazard.frame.intersects(liveScoreHole.frame),
            "the obstacle bar must sit between the corner actions, never under them"
        )
        XCTAssertFalse(
            app.descendants(matching: .any)["selected-hazard-2"].firstMatch.exists,
            "only the selected obstacle may have an active distance panel"
        )
        let nextHazard = app.buttons["hazard-next"]
        if nextHazard.isEnabled {
            nextHazard.tap()
            XCTAssertTrue(
                app.descendants(matching: .any)["selected-hazard-2"].firstMatch.waitForExistence(timeout: 3),
                "down navigation must replace the selected obstacle instead of stacking another one"
            )
            XCTAssertFalse(
                app.descendants(matching: .any)["selected-hazard-2"].firstMatch.frame.intersects(liveRecordShot.frame),
                "switching obstacles must keep the replacement bar clear of 记一杆"
            )
            XCTAssertFalse(firstSelectedHazard.exists)
        }
        settle(1); save("10b-live-hazard"); dump("10b-live-hazard")
        _ = openCaddiePlan(timeout: 75)
        XCTAssertFalse(
            app.staticTexts["联网球童暂不可用 · 已切换到离线缓存建议。"].exists,
            "the real course screenshot must prove the online structured decision, not an offline fallback"
        )
        XCTAssertTrue(
            app.descendants(matching: .any)["live-caddie-complete-route"].firstMatch.label.hasPrefix("球童路线：第 1 杆"),
            "the route drawn on the map must read out its complete remaining club chain"
        )
        XCTAssertFalse(
            app.descendants(matching: .any)["live-caddie-panel"].firstMatch.exists,
            "B1: no plan card; the route is on the map and 打法 switches routes"
        )
        for label in ["推荐打法", "保守打法", "进攻打法"] {
            XCTAssertFalse(app.staticTexts[label].exists, "legacy strategy labels must not replace physical club choices")
        }
        XCTAssertFalse(
            app.segmentedControls.firstMatch.exists,
            "legacy strategy modes must not consume the focused recommendation surface"
        )
        settle(1); save("11-caddie-plan"); dump("11-caddie-plan")

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
        XCTAssertTrue(waitForValue("已记第 1 杆", on: recordShotButton, timeout: 5))
        let recordedShotHoleHeading = app.staticTexts["第 1 洞"]
        XCTAssertTrue(
            recordedShotHoleHeading.waitForExistence(timeout: 5) && fullyVisible(recordedShotHoleHeading),
            "closing the actual-club sheet must restore the live-hole map/header instead of retaining the sheet-trigger scroll offset"
        )
        settle(1); save("11d-shot-recorded"); dump("11d-shot-recorded")

        let saveHoleButton = app.buttons["完成本洞"]
        XCTAssertTrue(scrollTo(saveHoleButton, maxSwipes: 14), "real hole must return to score confirmation")
        XCTAssertTrue(saveHoleButton.waitForExistence(timeout: 8), "hole root must expose score confirmation")
        saveHoleButton.tap()

        // B2: one preselected score sheet; saving the preselection is the one-tap acceptance.
        let acceptRecommendation = app.buttons["score-save"]
        XCTAssertTrue(
            acceptRecommendation.waitForExistence(timeout: 5),
            "saving a hole must ask for one-tap preselected-score acceptance before recording"
        )
        XCTAssertEqual(
            acceptRecommendation.label,
            "保存 3 杆 · 去第 2 洞",
            "one recorded shot should preselect shot + two putts"
        )
        XCTAssertTrue(
            app.buttons["score-choice-3"].isSelected,
            "the preselected total must be shot + two putts"
        )
        XCTAssertTrue(app.buttons["score-putts-2"].isSelected, "the preselection must assume two putts")
        settle(1); save("12-score-confirmation"); dump("12-score-confirmation")

        // Looking at a preselection must never commit it. Cancel once, prove the recorded GPS shot
        // and active hole are intact, then reopen the same confirmation and accept it.
        let cancelScore = app.buttons["score-cancel"]
        XCTAssertTrue(cancelScore.waitForExistence(timeout: 3))
        cancelScore.tap()
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 5))
        XCTAssertEqual(recordShotButton.value as? String, "已记第 1 杆")
        XCTAssertTrue(saveHoleButton.waitForExistence(timeout: 5) && saveHoleButton.isHittable)
        settle(1); save("12b-score-cancelled"); dump("12b-score-cancelled")
        saveHoleButton.tap()
        XCTAssertTrue(acceptRecommendation.waitForExistence(timeout: 5))
        acceptRecommendation.tap()
        let nextHoleHeading = app.staticTexts["第 2 洞"]
        XCTAssertTrue(
            nextHoleHeading.waitForExistence(timeout: 12),
            "accepting the preselected score must move phone-only play to the ordered next hole"
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
        XCTAssertNotEqual(
            nextHoleShotButton.value as? String,
            "等待 GPS",
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

        let scorecard = app.buttons["计分卡"]
        XCTAssertTrue(scrollTo(scorecard, maxSwipes: 8), "real hole must expose its scorecard action")
        XCTAssertTrue(scorecard.waitForExistence(timeout: 5), "live play must expose a real scorecard action")
        scorecard.tap()
        XCTAssertTrue(app.staticTexts["计分卡"].waitForExistence(timeout: 5))
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
        let editFirstHole = app.buttons["改第 1 洞成绩"]
        XCTAssertTrue(editFirstHole.waitForExistence(timeout: 5), "any completed hole must be editable")
        editFirstHole.tap()
        // The scorecard's own selection title is also "第 1 洞 · Par P", so prove the score sheet
        // by its unique save control instead of the header text.
        XCTAssertTrue(
            app.buttons["score-save"].waitForExistence(timeout: 5),
            "a scorecard edit must reopen the one-screen score sheet for the selected hole"
        )
        XCTAssertTrue(
            app.buttons["score-choice-3"].isSelected,
            "a scorecard edit must reopen the saved total, not a fresh preselection"
        )
        settle(1); save("15-edit-previous-hole"); dump("15-edit-previous-hole")

        // Keep the saved total and putts; only record the tee result as on the fairway.
        let editTeeHit = app.buttons["score-tee-hit"]
        XCTAssertTrue(editTeeHit.waitForExistence(timeout: 3))
        editTeeHit.tap()
        let editSave = app.buttons["score-save"]
        XCTAssertTrue(editSave.waitForExistence(timeout: 3))
        XCTAssertEqual(editSave.label, "保存 3 杆", "a scorecard edit must save in place without advancing")
        editSave.tap()
        XCTAssertTrue(
            app.staticTexts["第 2 洞"].waitForExistence(timeout: 5),
            "saving a historical score edit must not move the active playing hole"
        )
        settle(1); save("16-saved-previous-hole"); dump("16-saved-previous-hole")

        XCTAssertTrue(scrollTo(scorecard, maxSwipes: 8), "scorecard must remain available after historical save")
        scorecard.tap()
        XCTAssertTrue(app.staticTexts["计分卡"].waitForExistence(timeout: 5))
        XCTAssertTrue(
            app.staticTexts["正在打这一洞"].exists,
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

        // B1: 结束本场 lives on the scorecard (the live screen's 返回 destination).
        let endMenu = app.buttons["live-round-end-menu"]
        XCTAssertTrue(scrollTo(endMenu, maxSwipes: 6), "the scorecard must expose the single finish entry")
        endMenu.tap()
        XCTAssertTrue(
            app.buttons["live-finish-save"].waitForExistence(timeout: 5),
            "ending from the menu must show the same non-destructive summary used after the final hole"
        )
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "· 1/18 洞")).firstMatch.exists,
            "the summary must count the one completed hole of 18"
        )
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
                    app.staticTexts["已打 9 洞"].exists,
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
            // B2 tee tile id suffix: `score-tee-hit` / `score-tee-left` / `score-tee-right`.
            let fairwayLabel: String?
            if holeNumber == 2 {
                XCTAssertEqual(par, 4, "北京丽宫第 2 洞 must retain its real Par")
                didManualPar4 = true
                manual = true
                fairwayLabel = "hit"
            } else if par == 3, !didManualPar3 {
                didManualPar3 = true
                manual = true
                fairwayLabel = nil
            } else if par == 5, !didManualPar5 {
                didManualPar5 = true
                manual = true
                fairwayLabel = "left"
            } else if par != 3, !didManualFairwayRight {
                didManualFairwayRight = true
                manual = true
                fairwayLabel = "right"
            } else {
                manual = false
                fairwayLabel = nil
            }
            try confirmJourneyHole(
                hole: holeNumber,
                par: par,
                manual: manual,
                expectedPreselectedScore: 3,
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
            app.buttons["live-finish-save"].waitForExistence(timeout: 8),
            "the ordered last hole must open the shared finish summary automatically"
        )
        XCTAssertTrue(
            app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "· 18/18 洞")).firstMatch.exists,
            "the summary must count all 18 completed holes"
        )
        XCTAssertTrue(app.buttons["保存并结束"].exists)
        XCTAssertTrue(app.buttons["继续打球"].exists)
        // Every hole in this journey records one 记一杆 shot, so each preselection is `phone_shots`
        // (or `manual_edit`), never an untouched `default`: all 18 holes count toward putting.
        // 18 × 2 putts, minus the one putt removed on hole 2 = 35 (35/18 ≈ 1.9 per hole).
        let finishPutts = app.descendants(matching: .any)["live-finish-putts"]
        XCTAssertTrue(
            finishPutts.label.hasPrefix("推杆 35 "),
            "the adjusted putt count must survive every hole transition and the hole-10 relaunch (got \(finishPutts.label))"
        )
        XCTAssertTrue(finishPutts.label.contains("1.9/洞"), "all 18 holes must count toward putts per hole")
        let finishPenalties = app.descendants(matching: .any)["live-finish-penalties"]
        XCTAssertTrue(
            finishPenalties.label.hasPrefix("罚杆 1 ") || finishPenalties.label == "罚杆 1",
            "the non-zero penalty must survive every hole transition and the hole-10 relaunch (got \(finishPenalties.label))"
        )
        let finishFairways = app.descendants(matching: .any)["live-finish-fairways"]
        XCTAssertTrue(
            finishFairways.label.hasPrefix("球道命中 ") && finishFairways.label.contains("2/4"),
            "the earlier history edit plus hit, missed-left and missed-right must all persist (got \(finishFairways.label))"
        )
        settle(1); save("journey-18-complete-summary"); dump("journey-18-complete-summary")

        app.buttons["保存并结束"].tap()
        XCTAssertTrue(
            app.buttons["home-new-round"].waitForExistence(timeout: 8),
            "a finished round must return to the approved product home with a new-round entry"
        )
        XCTAssertFalse(app.navigationBars["开始一场"].exists, "finish must not strand the player in the setup form")
        XCTAssertFalse(app.staticTexts["进行中"].exists, "the explicitly finished round must no longer be active")
        settle(1); save("journey-finished-home"); dump("journey-finished-home")

        // The last home package deliberately still describes 北京丽宫.  Starting that same course
        // immediately must create a distinct round and enter hole 1 instead of comparing the home
        // package id, deciding “not new”, and remaining forever on the preparation screen.
        XCTAssertTrue(openStartRound())
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 12))
        let repeatSegment = selectStartCourse(approvedJourneyCourseGlobalId)
        XCTAssertTrue(repeatSegment.exists)
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
        XCTAssertTrue(openStartRound(), "home must expose the new-course start path")
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 12))

        let openSearch = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(scrollTo(openSearch, maxSwipes: 20), "start form must expose full-catalogue search")
        openSearch.tap()
        let courseSearchNavigationBar = app.navigationBars["找球场"]
        var openedCourseSearch = courseSearchNavigationBar.waitForExistence(timeout: 8)
        if !openedCourseSearch, scrollTo(openSearch, maxSwipes: 2) {
            // A long XCUITest journey can occasionally synthesize the first tap while SwiftUI is
            // committing the start screen's live nearby update. Retry the still-visible user action
            // once, but keep the same sheet assertion so a real presentation failure remains fatal.
            settle(1)
            openSearch.tap()
            openedCourseSearch = courseSearchNavigationBar.waitForExistence(timeout: 8)
        }
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
        // B4b: the selected venue is the checked row of the one course list; its label starts
        // with the localized venue name ("北京丽宫, 18 洞").
        let selectedVenue = app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@ AND value == %@", "start-round-venue-", "已选择")
        ).firstMatch
        XCTAssertTrue(
            selectedVenue.waitForExistence(timeout: 5),
            "the selected course must retain a visible localized venue name"
        )
        selectedNewCourseDisplayName = selectedVenue.label
            .components(separatedBy: ", ")
            .first?
            .trimmingCharacters(in: .whitespacesAndNewlines)
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
        let preparing = app.descendants(matching: .any)["live-map-preparing"].firstMatch
        let topoLoading = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-loading").firstMatch
        // `firstFactualMap` can observe the lightweight map just as the precise topo commits. A
        // retained XCUI query may still report the old partial snapshot for one turn. The route is
        // deliberately usable in this state, so a loading/preparing disclosure is optional; the
        // contract is that the factual map remains visible and eventually upgrades to precise
        // geometry without exposing an unselected hazard overlay.
        let observedLightweightMap = partialMap.exists && !topoReady.exists
        if observedLightweightMap {
            XCTAssertTrue(partialMap.exists, "the factual route map must remain visible while precise geometry loads")
            XCTAssertFalse(
                app.descendants(matching: .any)["live-hazard-detail"].firstMatch.exists,
                "hazards are opt-in and must stay hidden until the player selects one"
            )
            if !topoReady.exists && !topoLoading.exists && !preparing.exists {
                settle(1); save("09d-new-course-lightweight-map"); dump("09d-new-course-lightweight-map")
            }
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
        // this exact selected course at hole 1 after process death. Remove the journey's default
        // Beijing Palace fix before relaunching: this deliberately exercises the searched-course,
        // authorized-but-fixless contract instead of turning a Tee reference into a shot location.
        app.terminate()
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LAT")
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LON")
        app.launchEnvironment["UITEST_LOCATION_AUTHORIZATION"] = "authorized"
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30))
        let inProgress = app.buttons["home-in-progress-round"]
        XCTAssertTrue(inProgress.waitForExistence(timeout: 60), "new-course round must survive force-quit")
        let expectedCourseName = selectedNewCourseDisplayName ?? evidence.name
        XCTAssertTrue(
            inProgress.label.contains(expectedCourseName),
            "restored card must retain the selected course (expected \(expectedCourseName), got \(inProgress.label))"
        )
        XCTAssertTrue(inProgress.label.contains("第 1 洞"), "unplayed restored round must remain on hole 1")
        settle(1); save("09f-new-course-restored-home"); dump("09f-new-course-restored-home")
        inProgress.tap()
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 20))
        let restoredTopo = app.descendants(matching: .any)
            .matching(identifier: "topo-hole-base-ready").firstMatch
        XCTAssertTrue(
            restoredTopo.waitForExistence(timeout: 90),
            "restored new-course round must reopen the same precise first-hole map"
        )
        let restoredMap = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'live-hole-map-'"))
            .firstMatch
        XCTAssertTrue(
            restoredMap.waitForExistence(timeout: 12),
            "a searched course must show its factual map immediately even without a GPS fix"
        )
        let restoredPlan = openCaddiePlan(timeout: 75)
        XCTAssertTrue(
            restoredPlan.exists,
            "a searched course without GPS must still expose the static-map caddie recommendation"
        )
        let parText = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Par '")).firstMatch
        XCTAssertTrue(parText.waitForExistence(timeout: 8))
        let par = try XCTUnwrap(
            parText.label.split(separator: " ").dropFirst().first.flatMap { Int($0) },
            "new-course hole 1 Par must be factual"
        )
        let noGPSRecord = app.buttons["记一杆"]
        XCTAssertTrue(
            scrollTo(noGPSRecord, maxSwipes: 18),
            "a no-GPS round must still expose the shot action in the live controls"
        )
        XCTAssertFalse(
            noGPSRecord.isEnabled,
            "a no-GPS round must not record a fabricated current position"
        )
        XCTAssertTrue(
            waitForValue("等待 GPS", on: noGPSRecord, timeout: 5),
            "the disabled shot action must explain that a factual GPS fix is required"
        )
        XCTAssertFalse(
            app.staticTexts["这一杆用了什么球杆？"].exists,
            "no-GPS shot capture must not open the actual-club prompt"
        )
        // No shot could be recorded without GPS, so the sheet preselects the default par.
        try confirmJourneyHole(
            hole: 1,
            par: par,
            manual: false,
            expectedPreselectedScore: par,
            fairwayLabel: nil
        )
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
        let scorecard = app.buttons["计分卡"]
        XCTAssertTrue(scrollTo(scorecard, maxSwipes: 18))
        scorecard.tap()
        let scorecardEdit = app.buttons["live-scorecard-edit-hole"]
        XCTAssertTrue(
            scorecardEdit.waitForExistence(timeout: 5),
            "the unique scorecard edit action must prove the scorecard sheet was presented"
        )
        XCTAssertEqual(
            scorecardEdit.label,
            "改第 2 洞成绩",
            "a newly opened scorecard must select the active playing hole"
        )
        let selectCompletedFirstHole = app.buttons["选择第 1 洞"].firstMatch
        XCTAssertTrue(
            selectCompletedFirstHole.waitForExistence(timeout: 5) && selectCompletedFirstHole.isHittable,
            "the completed first hole must remain selectable from the active second hole"
        )
        selectCompletedFirstHole.tap()
        let editCompletedFirstHole = app.buttons["改第 1 洞成绩"]
        XCTAssertTrue(
            editCompletedFirstHole.waitForExistence(timeout: 5),
            "selecting the completed first hole must retarget the unique edit action"
        )
        settle(1); save("09g-new-course-scorecard"); dump("09g-new-course-scorecard")
        editCompletedFirstHole.tap()
        let editSave = app.buttons["score-save"]
        XCTAssertTrue(editSave.waitForExistence(timeout: 5))
        XCTAssertEqual(editSave.label, "保存 \(par) 杆", "a scorecard edit must reopen the saved default-par score")
        settle(1); save("09h-new-course-score-edit"); dump("09h-new-course-score-edit")
        app.buttons["score-cancel"].tap()
        XCTAssertTrue(app.staticTexts["第 2 洞"].waitForExistence(timeout: 8))

        // B1: 结束本场 lives on the scorecard (the live screen's 返回 destination).
        let reopenScorecard = app.buttons["计分卡"]
        XCTAssertTrue(reopenScorecard.waitForExistence(timeout: 5))
        reopenScorecard.tap()
        let endMenu = app.buttons["live-round-end-menu"]
        XCTAssertTrue(scrollTo(endMenu, maxSwipes: 6))
        endMenu.tap()
        XCTAssertTrue(app.buttons["live-finish-save"].waitForExistence(timeout: 5))
        XCTAssertTrue(
            app.staticTexts.matching(
                NSPredicate(format: "label CONTAINS %@", "· 1/\(evidence.holes) 洞")
            ).firstMatch.exists
        )
        app.buttons["保存并结束"].tap()
        XCTAssertTrue(app.buttons["home-new-round"].waitForExistence(timeout: 10))
        XCTAssertTrue(
            waitUntilGone(app.buttons["home-in-progress-round"], timeout: 8),
            "local UI-test cleanup must remove only the temporary new-course round"
        )
    }

    // MARK: - navigation helpers

    private func restoreDefaultGPSLaunchEnvironment() {
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment.removeValue(forKey: "UITEST_LOCATION_AUTHORIZATION")
    }

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
        _ = openCaddiePlan(timeout: 75)
        XCTAssertFalse(
            app.staticTexts["联网球童暂不可用 · 已切换到离线缓存建议。"].exists,
            "hole \(hole) must not silently replace the real journey with an offline suggestion"
        )
        return par
    }

    /// The live root exposes the complete route directly; readiness never depends on presenting a
    /// second sheet or returning from it before the golfer can record the next shot.
    @discardableResult
    private func openCaddiePlan(timeout: TimeInterval) -> XCUIElement {
        // B1: the selected route is drawn on the full-screen map; its accessible summary is the
        // evidence that the structured recommendation arrived.
        let route = app.descendants(matching: .any)["live-caddie-complete-route"].firstMatch
        XCTAssertTrue(
            route.waitForExistence(timeout: timeout),
            "the live map must carry the complete caddie route"
        )
        return route
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
            let promptChoices = app.buttons.matching(
                NSPredicate(format: "identifier BEGINSWITH %@", "actual-club-choice-")
            )
            let recommendedClub = promptChoices.matching(
                NSPredicate(format: "label CONTAINS %@", "球童建议")
            ).firstMatch
            let actualClub = recommendedClub.waitForExistence(timeout: 1)
                ? recommendedClub
                : promptChoices.firstMatch
            XCTAssertTrue(
                scrollTo(actualClub, maxSwipes: 6),
                "actual-club prompt must expose a selectable bag club even when the route is infeasible"
            )
            actualClub.tap()
        } else {
            let skip = app.buttons["跳过球杆（位置已记录）"]
            XCTAssertTrue(skip.waitForExistence(timeout: 5))
            skip.tap()
        }
        XCTAssertTrue(waitForValue("已记第 1 杆", on: record, timeout: 5))
    }

    /// Complete one hole on the B2 one-screen score sheet: either save the preselection with one
    /// tap, or set total / putts / (Par 4/5 only) tee result / penalties directly and then save.
    /// `fairwayLabel` is the tee tile id suffix: "hit", "left" or "right".
    private func confirmJourneyHole(
        hole: Int,
        par: Int,
        manual: Bool,
        expectedPreselectedScore: Int? = nil,
        fairwayLabel: String?,
        puttsAdjustment: Int = 0,
        penaltyAdjustment: Int = 0
    ) throws {
        let confirm = app.buttons["完成本洞"]
        XCTAssertTrue(scrollTo(confirm, maxSwipes: 18), "hole \(hole) must expose score confirmation")
        confirm.tap()
        let saveScore = app.buttons["score-save"]
        XCTAssertTrue(saveScore.waitForExistence(timeout: 5), "hole \(hole) must offer one-tap preselected save")
        if let expectedPreselectedScore {
            XCTAssertTrue(
                saveScore.label.hasPrefix("保存 \(expectedPreselectedScore) 杆"),
                "hole \(hole) must preselect \(expectedPreselectedScore) strokes (got \(saveScore.label))"
            )
        }
        if !manual {
            saveScore.tap()
            return
        }

        // One recorded non-putt shot preselects 3 (+2 putts). Set the representative manual holes to par.
        let total = app.buttons["score-choice-\(par)"]
        XCTAssertTrue(total.waitForExistence(timeout: 3), "hole \(hole) score strip must offer par")
        total.tap()
        XCTAssertTrue(total.isSelected, "hole \(hole) must select par as the total")

        // The preselection assumes two putts; adjust from there by tapping the target segment.
        let puttsValue = 2 + puttsAdjustment
        let putts = app.buttons["score-putts-\(puttsValue)"]
        XCTAssertTrue(putts.waitForExistence(timeout: 2))
        if puttsAdjustment != 0 {
            putts.tap()
        }
        XCTAssertTrue(putts.isSelected, "hole \(hole) must record \(puttsValue) putts")

        if par == 3 {
            XCTAssertFalse(
                app.buttons["score-tee-hit"].exists,
                "a Par 3 must not ask for a tee result"
            )
        } else {
            let fairway = try XCTUnwrap(fairwayLabel, "Par 4/5 manual flow requires a tee result")
            let tee = app.buttons["score-tee-\(fairway)"]
            XCTAssertTrue(tee.waitForExistence(timeout: 3))
            tee.tap()
            XCTAssertTrue(tee.isSelected, "hole \(hole) must record tee result \(fairway)")
        }

        for _ in 0..<abs(penaltyAdjustment) {
            let button = app.buttons[penaltyAdjustment < 0 ? "罚杆减一" : "罚杆加一"]
            XCTAssertTrue(button.waitForExistence(timeout: 2))
            button.tap()
        }
        XCTAssertEqual(
            app.staticTexts["score-penalty-value"].label,
            "\(max(0, penaltyAdjustment))",
            "hole \(hole) must show the adjusted penalty count before saving"
        )
        XCTAssertTrue(
            saveScore.label.hasPrefix("保存 \(par) 杆"),
            "hole \(hole) must save the chosen par total (got \(saveScore.label))"
        )
        saveScore.tap()
    }

    /// B4b home main card: "换球场或组合" (a known course) or the search card both open 开始一场
    /// without a preselected course; the main card's "开始" would preselect it.
    @discardableResult
    private func openStartRound() -> Bool {
        let change = app.buttons["home-change-course"]
        if change.waitForExistence(timeout: 4), change.isHittable {
            change.tap()
            return true
        }
        let entry = app.buttons["home-new-round"]
        if entry.waitForExistence(timeout: 4), entry.isHittable {
            entry.tap()
            return true
        }
        return tapContaining(["换球场或组合", "今天去哪打"])
    }

    /// B4b 开始一场: select a course by its row in the one course list, then its loop tile.
    @discardableResult
    private func selectStartCourse(_ globalId: Int) -> XCUIElement {
        let tile = app.buttons["start-round-course-segment-\(globalId)"]
        if tile.exists, tile.value as? String == "已选择" { return tile }
        let row = app.buttons["start-round-venue-\(globalId)"]
        if scrollTo(row, maxSwipes: 24) {
            row.tap()
            settle(1)
        }
        if scrollTo(tile, maxSwipes: 8), tile.value as? String != "已选择" {
            tile.tap()
            settle(1)
        }
        return tile
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
