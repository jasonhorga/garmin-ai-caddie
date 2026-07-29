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
        continueAfterFailure = true
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
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
            settle(7); save("02-stats"); dump("02-stats")
        }

        // ---- Section 2: history list → a round review → shot-map → review-edit (merged #276) ----
        launchFresh()
        if tapContaining(["历史复盘", "逐场逐洞"]) {
            settle(6); save("03-history-list"); dump("03-history-list")
            if tapFirstRoundRow() {
                settle(6); save("04-round-review"); dump("04-round-review")
                // Tap a hole row (label like "1, 推 2, P5, 8") → that hole's shot-map (has the 编辑 toggle).
                let holeRow = app.buttons.matching(NSPredicate(format: "label CONTAINS ', P'")).firstMatch
                if holeRow.waitForExistence(timeout: 5), holeRow.isHittable {
                    holeRow.tap()
                    settle(6); save("04b-shot-map"); dump("04b-shot-map")
                    if tapContaining(["编辑"]) {
                        settle(3); save("04c-edit-mode"); dump("04c-edit-mode")
                        // Tap the map render area to open the 补一杆/改杆 sheet (best-effort centre tap).
                        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.42)).tap()
                        settle(2); save("04d-edit-sheet"); dump("04d-edit-sheet")
                    }
                }
            }
        }

        // ---- Section 3: last-round review shortcut from home ----
        launchFresh()
        if tapContaining(["上一场"]) {
            settle(6); save("05-last-round-review"); dump("05-last-round-review")
        }

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

        // Enter the first real installed course. CourseReviewView itself is the per-hole review; the
        // old test looked for obsolete `逐洞攻略` / `针对你` buttons and silently produced no evidence.
        XCTAssertTrue(tapCourseSegment(), "course picker must expose an installed real course")
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
        XCTAssertTrue(
            app.buttons["返回球局首页"].waitForExistence(timeout: 5),
            "immersive live play must retain an explicit way back to the round home"
        )
        XCTAssertLessThan(
            visibleStatusChromePixelFraction(in: XCUIScreen.main.screenshot()),
            0.005,
            "the live-play NavigationStack must not render the black-on-black system time, Wi-Fi, or battery chrome"
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
        for label in ["稳妥打法", "标准打法", "进攻打法"] {
            XCTAssertTrue(
                app.staticTexts[label].waitForExistence(timeout: 5),
                "a Par 4 tee decision must expose all three complete club-to-club strategy chains: \(label)"
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
        settle(1); save("11b-caddie-hazards"); dump("11b-caddie-hazards")

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
        for distance in ["110", "119", "137"] {
            XCTAssertTrue(
                app.staticTexts[distance].waitForExistence(timeout: 60),
                "the ordered next hole must load its real front/middle/back distance \(distance)"
            )
        }
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
        settle(1); save("17-scorecard-after-edit"); dump("17-scorecard-after-edit")

        app.buttons["关闭计分卡"].tap()
        let manageRound = app.buttons["球局调整 · 加打 / 结束本场"]
        XCTAssertTrue(scrollTo(manageRound, maxSwipes: 16), "test round must expose local cleanup")
        manageRound.tap()
        let finishRound = app.buttons["结束本场"].firstMatch
        XCTAssertTrue(scrollTo(finishRound, maxSwipes: 4), "local test round must be discardable")
        finishRound.tap()
        let confirmFinish = app.sheets.buttons["结束本场"]
        XCTAssertTrue(confirmFinish.waitForExistence(timeout: 3), "ending the local test round must ask for confirmation")
        confirmFinish.tap()
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
    /// black time / Wi-Fi / battery glyphs over this app's near-black top inset. Inspect the two status
    /// chrome lanes in the actual screen pixels instead. Mirrored bottom lanes make this independent
    /// of CGImage's row orientation; those corner lanes contain no pure-black app content.
    private func visibleStatusChromePixelFraction(in screenshot: XCUIScreenshot) -> Double {
        let lanes = [
            CGRect(x: 0.08, y: 0.015, width: 0.19, height: 0.06),
            CGRect(x: 0.68, y: 0.015, width: 0.26, height: 0.06),
            CGRect(x: 0.08, y: 0.925, width: 0.19, height: 0.06),
            CGRect(x: 0.68, y: 0.925, width: 0.26, height: 0.06),
        ]
        return lanes.map { nearBlackPixelFraction(in: screenshot, normalizedRect: $0) }.max() ?? 1
    }

    private func nearBlackPixelFraction(
        in screenshot: XCUIScreenshot,
        normalizedRect: CGRect
    ) -> Double {
        guard let image = screenshot.image.cgImage else {
            XCTFail("screen capture must expose CGImage pixels")
            return 1
        }
        let cropRect = CGRect(
            x: normalizedRect.minX * CGFloat(image.width),
            y: normalizedRect.minY * CGFloat(image.height),
            width: normalizedRect.width * CGFloat(image.width),
            height: normalizedRect.height * CGFloat(image.height)
        ).integral
        guard let crop = image.cropping(to: cropRect) else {
            XCTFail("status-chrome pixel crop must be valid")
            return 1
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
            return 1
        }

        var nearBlack = 0
        for offset in stride(from: 0, to: pixels.count, by: bytesPerPixel) {
            if pixels[offset] <= 1, pixels[offset + 1] <= 1, pixels[offset + 2] <= 1 {
                nearBlack += 1
            }
        }
        return Double(nearBlack) / Double(crop.width * crop.height)
    }

    private func waitUntilGone(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if !element.exists { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    /// Tap the first button/cell/text whose label CONTAINS any of the given fragments.
    @discardableResult
    private func tapContaining(_ fragments: [String]) -> Bool {
        for fragment in fragments {
            let predicate = NSPredicate(format: "label CONTAINS %@", fragment)
            for query in [app.buttons, app.cells, app.staticTexts, app.otherElements] {
                let match = query.matching(predicate).firstMatch
                if match.waitForExistence(timeout: 4), match.isHittable { match.tap(); return true }
            }
        }
        return false
    }

    /// Tap a course-segment row BUTTON (not the inner static text — that wouldn't fire the NavigationLink)
    /// so the prep detail actually opens. Exact labels first (黑骑士 A 场 / a 全场), then any "…场" button.
    @discardableResult
    private func tapCourseSegment() -> Bool {
        // Prefer the stable accessibilityIdentifier (now a full-row tap target) → reliable navigation.
        let byId = app.buttons.matching(identifier: "prep-course-row").firstMatch
        if byId.waitForExistence(timeout: 6) { byId.tap(); return true }
        for label in ["A 场, 9 洞", "全场, 18 洞"] {
            let button = app.buttons[label]
            if button.waitForExistence(timeout: 4) { button.tap(); return true }
        }
        return false
    }

    /// First list row in a history list — try cells then buttons (SwiftUI List rows surface either way).
    @discardableResult
    private func tapFirstRoundRow() -> Bool {
        let cell = app.cells.firstMatch
        if cell.waitForExistence(timeout: 6), cell.isHittable { cell.tap(); return true }
        // a date/score-bearing button row
        let predicate = NSPredicate(format: "label CONTAINS '杆' OR label CONTAINS '20' OR label MATCHES '.*[0-9]+.*'")
        let row = app.buttons.matching(predicate).firstMatch
        if row.waitForExistence(timeout: 4), row.isHittable { row.tap(); return true }
        return false
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
