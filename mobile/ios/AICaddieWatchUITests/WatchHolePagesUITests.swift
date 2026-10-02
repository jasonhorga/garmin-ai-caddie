import XCTest

/// B6 本洞 pages driven for real (Codex review on #367): the production `WatchRoundContainerView`
/// with the outlined standalone fixture, paged by actual vertical swipes. Proves 方案 → 障碍 → 果岭
/// and back 果岭 → 障碍, i.e. that the unzoomed green page hands every drag that does not start on
/// the flag to the page swipe instead of swallowing it.
final class WatchHolePagesUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launchArguments = ["-uitest-screen", "standalone-course-page-plan"]
        app.launchEnvironment["UITEST_GPS_LAT"] = "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = "116.5461531"
    }

    /// The page modes draw the cached hole image, which only `standalone-course-seed` stores (the
    /// runtime workflow seeds the same way). Seed once, wait for its 本洞 pages, then relaunch.
    private func seedTheCourseImage() {
        app.launchArguments = ["-uitest-screen", "standalone-course-seed"]
        app.launch()
        let pages = app.staticTexts["watch-hole-page-current"]
        if !pages.waitForExistence(timeout: 30) {
            print("WatchHolePagesUITests seed hierarchy:\n\(app.debugDescription)")
        }
        app.terminate()
    }

    func testVerticalSwipesWalkTheThreeHolePagesAndBack() {
        seedTheCourseImage()
        app.launchArguments = ["-uitest-screen", "standalone-course-page-plan"]
        app.launch()
        let marker = app.staticTexts["watch-hole-page-current"]
        guard marker.waitForExistence(timeout: 20) else {
            // Into the job log: what the app is showing instead.
            print("WatchHolePagesUITests hierarchy:\n\(app.debugDescription)")
            return XCTFail("the production 本洞 pages are showing")
        }
        assertPage("方案", marker)

        swipe(up: true)
        assertPage("障碍", marker)
        swipe(up: true)
        assertPage("果岭", marker)
        swipe(up: false)
        assertPage("障碍", marker)
    }

    /// The prepared plan after the tee shot (the production container, real prepared options): the
    /// 方案 page still shows the next club's tag, never the Driver again, and tapping it switches plan.
    func testAfterTheTeeShotThePlanTagShowsTheNextClubAndSwitchesPlans() {
        seedTheCourseImage()
        app.launchArguments = ["-uitest-screen", "standalone-course-page-plan-after-tee"]
        app.launch()
        let tag = app.buttons["watch-plan-club-tag"]
        guard tag.waitForExistence(timeout: 20) else {
            print("WatchHolePagesUITests hierarchy:\n\(app.debugDescription)")
            return XCTFail("the plan page shows the next club's tag after the tee shot")
        }
        XCTAssertFalse(tag.label.contains("一号木"), "the tee shot is not offered again: \(tag.label)")
        let before = String(describing: tag.value ?? "")
        let switched = NSPredicate(format: "value != %@", before)
        tag.tap()
        var result = XCTWaiter().wait(
            for: [XCTNSPredicateExpectation(predicate: switched, object: tag)],
            timeout: 4
        )
        if result != .completed {
            // A system alert (the simulator's location prompt) can swallow the first tap while
            // XCTest dismisses it; tap once more on the now-unobstructed tag.
            tag.tap()
            result = XCTWaiter().wait(
                for: [XCTNSPredicateExpectation(predicate: switched, object: tag)],
                timeout: 6
            )
        }
        if result != .completed {
            print("WatchHolePagesUITests hierarchy:\n\(app.debugDescription)")
        }
        XCTAssertEqual(result, .completed, "tapping the tag switches plan (was \(before))")
        XCTAssertFalse(tag.label.contains("一号木"), "the switched plan does not offer the tee shot either: \(tag.label)")
    }

    /// A flick on the system page view (the vertical TabView), the way a wrist swipe reaches it.
    private func swipe(up: Bool) {
        let pager = app.collectionViews["PUICPageViewController_collectionView"]
        XCTAssertTrue(pager.waitForExistence(timeout: 5), "the 本洞 pager is on screen")
        if up { pager.swipeUp() } else { pager.swipeDown() }
    }

    private func assertPage(_ name: String, _ marker: XCUIElement, file: StaticString = #filePath, line: UInt = #line) {
        let shown = NSPredicate(format: "label == %@", name)
        let expectation = XCTNSPredicateExpectation(predicate: shown, object: marker)
        let result = XCTWaiter().wait(for: [expectation], timeout: 6)
        if result != .completed {
            print("WatchHolePagesUITests hierarchy:\n\(app.debugDescription)")
        }
        XCTAssertEqual(result, .completed, "expected the \(name) page, saw \(marker.label)", file: file, line: line)
    }
}
