import XCTest

/// Real running-app watch touch test (watchOS XCUITest — supported since Xcode 12.5). Launches the watch
/// app straight into the hole map via `-uitest-screen hole-map`, then drives the three touch affordances
/// that the design-snapshot tests can only fake with static override params:
///   01 选点测距 — tap the map → crosshair + 码 distance pill
///   02 拖旗     — press-drag from the pin → 到旗 pill from the moved flag
///   03 大字     — long-press → the host's 大字 badge
/// PNGs land in the runner's Documents/watch-touch-screenshots/; native-mobile.yml collects them, and a
/// simctl recording of the same run is uploaded as watch-touch-video. Non-fatal by design (no asserts):
/// a missed gesture yields a still-useful frame, never a red run.
final class WatchTouchUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = true
        app.launchArguments = ["-uitest-screen", "hole-map"]
    }

    func testHoleMapTouch() throws {
        // --- 01 选点测距: tap map center (far from "you" at ~0.69,0.72 → registers a measurement) ---
        // ONE app session — a relaunch between gestures flashes the watchOS watch face into the recording
        // (the earlier version did that and looked like a crash). Each gesture's result stays on screen
        // (measure crosshair → dragged flag → 大字 badge); the 3.5s settles give the video a beat per step.
        launchMap()
        map(0.5, 0.5).tap()
        settle(3.5); save("01-measure")

        // 02 拖旗: press-drag from the pin (canvas ≈ (0.58,0.17) for the baked sample; grab radius widened
        // to 80pt under -uitest-screen so the synthesized drag lands on the flag).
        map(0.58, 0.17).press(forDuration: 0.6, thenDragTo: map(0.66, 0.30))
        settle(3.5); save("02-dragflag")

        // 03 大字: long-press toggles the host badge.
        map(0.5, 0.55).press(forDuration: 0.6)
        settle(3.5); save("03-bigtext")
    }

    // MARK: - helpers

    private func launchMap() {
        if app.state == .runningForeground { app.terminate() }
        app.launch()
        _ = app.wait(for: .runningForeground, timeout: 30)
        // Best-effort deterministic wait on the map's identifier; falls through to a fixed settle if the
        // Canvas container doesn't surface as an element on watchOS — screenshots still capture.
        _ = app.otherElements["watch-hole-map"].waitForExistence(timeout: 12)
        settle(2)
    }

    private func settle(_ s: TimeInterval) { Thread.sleep(forTimeInterval: s) }

    private func map(_ dx: Double, _ dy: Double) -> XCUICoordinate {
        app.coordinate(withNormalizedOffset: CGVector(dx: dx, dy: dy))
    }

    private func shotsDir() -> URL {
        let base = (try? FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("watch-touch-screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func save(_ name: String) {
        let shot = app.screenshot()   // app.screenshot() is the watchOS-safe equivalent of XCUIScreen.main.screenshot()
        try? shot.pngRepresentation.write(to: shotsDir().appendingPathComponent("\(name).png"))
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_WATCH_TOUCH_SHOT \(name)")
    }
}
