import XCTest

/// C16f V coverage: the production Watch pager exposes the same three D02 pages in order.
final class WatchC16fPagesUITests: XCTestCase {
    private let app = XCUIApplication()

    func testD02PagesArePlanHazardAndGreen() {
        continueAfterFailure = false
        app.launchArguments = ["-uitest-screen", "standalone-course-page-plan"]
        app.launchEnvironment["UITEST_GPS_LAT"] = "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = "116.5461531"
        app.launch()

        let marker = app.staticTexts["watch-hole-page-current"]
        XCTAssertTrue(marker.waitForExistence(timeout: 20))
        XCTAssertEqual(marker.label, "方案")
        let pager = app.collectionViews["PUICPageViewController_collectionView"]
        XCTAssertTrue(pager.waitForExistence(timeout: 5))
        pager.swipeUp()
        XCTAssertEqual(marker.label, "障碍")
        pager.swipeUp()
        XCTAssertEqual(marker.label, "果岭")
    }
}
