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

    /// A fixed bottom area as the viewport rule sees it. `ownsTarget` is true only when the element
    /// being checked is a real accessibility descendant of the area (the Start action itself), never
    /// because its frame merely lies inside the area: a row scrolled behind the band overlaps it
    /// completely and is exactly what must be excluded (Codex review 6030036864).
    struct PinnedArea {
        let frame: CGRect
        let ownsTarget: Bool
    }

    /// Bottom edge of the tappable viewport: the window above the home-indicator lane, cut at the
    /// top of every pinned area that does not own the target.
    static func usableBottom(windowMaxY: CGFloat, pinnedAreas: [PinnedArea]) -> CGFloat {
        var bottom = windowMaxY - homeIndicatorLane
        for area in pinnedAreas where !area.frame.isNull && !area.frame.isEmpty && !area.ownsTarget {
            bottom = min(bottom, area.frame.minY)
        }
        return bottom
    }

    /// True only when `element` is found in `area`'s own accessibility subtree (same type, identity
    /// and frame). A scrolling row behind the band is not in that subtree whatever its frame.
    static func isDescendant(_ element: XCUIElement, of area: XCUIElement) -> Bool {
        let frame = element.frame
        guard !frame.isNull, !frame.isEmpty else { return false }
        let identifier = element.identifier
        let label = element.label
        return area.descendants(matching: element.elementType).allElementsBoundByIndex.contains {
            $0.identifier == identifier && $0.label == label && $0.frame == frame
        }
    }

    /// The tappable rect for `element`. Only a pinned area whose accessibility subtree holds
    /// `element` (the Start action itself) does not exclude it.
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
        var pinned: [PinnedArea] = []
        for identifier in pinnedBottomAreas {
            let area = app.descendants(matching: .any).matching(identifier: identifier).firstMatch
            guard area.exists else { continue }
            let owns = element.map { $0.exists && isDescendant($0, of: area) } ?? false
            pinned.append(PinnedArea(frame: area.frame, ownsTarget: owns))
        }
        let bottom = usableBottom(windowMaxY: window.maxY, pinnedAreas: pinned)
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
