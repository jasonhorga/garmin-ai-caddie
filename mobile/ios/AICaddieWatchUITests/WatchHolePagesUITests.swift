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

    func testVerticalSwipesWalkTheThreeHolePagesAndBack() {
        app.launch()
        let marker = app.descendants(matching: .any)["watch-hole-page-current"]
        XCTAssertTrue(marker.waitForExistence(timeout: 20), "the production 本洞 pages are showing")
        assertPage("方案", marker)

        // Swipes start away from the screen centre so none of them begins on the green's flag.
        swipe(up: true)
        assertPage("障碍", marker)
        swipe(up: true)
        assertPage("果岭", marker)
        swipe(up: false)
        assertPage("障碍", marker)
    }

    private func swipe(up: Bool) {
        let left = 0.2
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: left, dy: up ? 0.72 : 0.3))
        let end = app.coordinate(withNormalizedOffset: CGVector(dx: left, dy: up ? 0.2 : 0.85))
        start.press(forDuration: 0.05, thenDragTo: end)
    }

    private func assertPage(_ name: String, _ marker: XCUIElement, file: StaticString = #filePath, line: UInt = #line) {
        let shown = NSPredicate(format: "value == %@", name)
        let expectation = XCTNSPredicateExpectation(predicate: shown, object: marker)
        let result = XCTWaiter().wait(for: [expectation], timeout: 6)
        XCTAssertEqual(result, .completed, "expected the \(name) page, saw \(String(describing: marker.value))", file: file, line: line)
    }
}
