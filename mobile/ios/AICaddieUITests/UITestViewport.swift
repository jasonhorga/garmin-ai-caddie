import XCTest

/// The part of the screen where a scrolled element can really be tapped: below the navigation bar,
/// above the home-indicator lane, and above any fixed bottom area pinned over the scroll content
/// (a `safeAreaInset`, padding included).
///
/// Live Native 37534118109: the white Tee (y 730.7–787.0) was judged fully visible while the pinned
/// 开始一场 action (759.7–810.0) covered it; the tap landed on "从 前九 开始 · 蓝 T" and started a
/// Blue round. Shared by every UI test that scrolls an element into view, so the occlusion rule
/// lives in one place.
enum UITestViewport {
    /// Accessibility identifiers of fixed bottom areas the app draws over scrolling content.
    static let pinnedBottomAreas = ["start-round-pinned-actions"]
    /// The iPhone home-indicator lane.
    static let homeIndicatorLane: CGFloat = 34

    /// The tappable rect for `element`. A pinned area that contains `element` (the Start action
    /// itself) does not exclude it.
    static func usableRect(
        in app: XCUIApplication,
        for element: XCUIElement? = nil,
        topBar: XCUIElement? = nil
    ) -> CGRect {
        let window = app.windows.firstMatch.frame
        var top = window.minY + 8
        let bar = (topBar?.exists == true ? topBar : nil) ?? app.navigationBars.firstMatch
        if bar.exists {
            top = max(top, bar.frame.maxY + 8)
        }
        var bottom = window.maxY - homeIndicatorLane
        let target = element.map(\.frame)
        for identifier in pinnedBottomAreas {
            let area = app.descendants(matching: .any).matching(identifier: identifier).firstMatch
            guard area.exists else { continue }
            let frame = area.frame
            guard !frame.isNull, !frame.isEmpty else { continue }
            if let target, !target.isNull, frame.contains(target) { continue }
            bottom = min(bottom, frame.minY)
        }
        return CGRect(
            x: window.minX + 8,
            y: top,
            width: max(0, window.width - 16),
            height: max(0, bottom - top)
        )
    }

    static func fullyVisible(
        _ element: XCUIElement,
        in app: XCUIApplication,
        topBar: XCUIElement? = nil
    ) -> Bool {
        let frame = element.frame
        return !frame.isNull && !frame.isEmpty
            && usableRect(in: app, for: element, topBar: topBar).contains(frame)
    }
}
