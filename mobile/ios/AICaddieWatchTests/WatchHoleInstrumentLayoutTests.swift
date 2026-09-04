import CoreGraphics
import XCTest
@testable import AICaddieWatch

final class WatchHoleInstrumentLayoutTests: XCTestCase {
    private let supportedFaces: [(name: String, size: CGSize)] = [
        ("41 mm", CGSize(width: 176, height: 215)),
        ("45 mm", CGSize(width: 198, height: 242)),
        ("49 mm", CGSize(width: 205, height: 251)),
    ]

    func testAdaptiveGlanceBudgetFitsEverySupportedFace() {
        var previousGlanceHeight: CGFloat = 0

        for face in supportedFaces {
            let layout = WatchHoleInstrumentLayout.resolve(for: face.size)
            let density = WatchCaddieGlanceView.compactDensity(for: layout.glanceHeight)

            XCTAssertTrue(layout.fitsInSafeArea, "\(face.name) root content must stay in its safe rect")
            XCTAssertEqual(layout.usedHeight, layout.safeRect.height, accuracy: 0.01)
            XCTAssertGreaterThanOrEqual(
                layout.glanceHeight,
                WatchCaddieGlanceView.compactContentHeight(for: density),
                "\(face.name) compact rows must fit their selected density"
            )
            XCTAssertGreaterThanOrEqual(
                layout.safeRect.width,
                WatchCaddieGlanceView.compactInstrumentMinimumWidth,
                "\(face.name) must leave room for F/M/B distances"
            )
            XCTAssertGreaterThan(layout.glanceHeight, previousGlanceHeight, "\(face.name) should receive its measured height")
            previousGlanceHeight = layout.glanceHeight
        }
    }

    func testCompactDensityDropsLowerPriorityRowsBeforeClipping() {
        XCTAssertEqual(WatchCaddieGlanceView.compactDensity(for: 112), .regular)
        XCTAssertEqual(WatchCaddieGlanceView.compactDensity(for: 90), .tight)
        XCTAssertEqual(WatchCaddieGlanceView.compactDensity(for: 60), .minimal)
        XCTAssertLessThan(
            WatchCaddieGlanceView.compactContentHeight(for: WatchCaddieGlanceView.CompactDensity.minimal),
            WatchCaddieGlanceView.compactContentHeight(for: WatchCaddieGlanceView.CompactDensity.tight)
        )
        XCTAssertLessThan(
            WatchCaddieGlanceView.compactContentHeight(for: WatchCaddieGlanceView.CompactDensity.tight),
            WatchCaddieGlanceView.compactContentHeight(for: WatchCaddieGlanceView.CompactDensity.regular)
        )
    }

    func testMeasuredHeightNeverBecomesNegativeForAConstrainedViewport() {
        let layout = WatchHoleInstrumentLayout.resolve(for: CGSize(width: 150, height: 100))

        XCTAssertGreaterThanOrEqual(layout.glanceHeight, 0)
        XCTAssertGreaterThanOrEqual(
            WatchCaddieGlanceView.compactInstrumentHeight(for: -10),
            0
        )
    }
}
