import SwiftUI
import UIKit
import XCTest
@testable import AICaddie

@MainActor
final class ProductGreenEntryTests: XCTestCase {
    /// J5.4: the putting surface owns its touches, without stealing the surrounding map.
    func testGreenContourAcceptsInteriorTouchesAndRejectsTheRestOfItsBoundingBox() {
        let control = LiveGreenEntryButton.Control(frame: CGRect(x: 0, y: 0, width: 80, height: 80))
        let contour = CGMutablePath()
        contour.move(to: CGPoint(x: 0, y: 0))
        contour.addLine(to: CGPoint(x: 80, y: 0))
        contour.addLine(to: CGPoint(x: 0, y: 80))
        contour.closeSubpath()
        control.hitPath = contour
        XCTAssertTrue(control.point(inside: CGPoint(x: 20, y: 20), with: nil))
        XCTAssertFalse(control.point(inside: CGPoint(x: 70, y: 70), with: nil))
        XCTAssertFalse(control.point(inside: CGPoint(x: -10, y: 20), with: nil))
    }

    /// J5.4: the actual hosted control exposes and dispatches the default accessibility action.
    func testAccessibleGreenActivationDispatchesTheSameFlagPlacementActionAsTouch() throws {
        var opened = 0
        let host = UIHostingController(rootView:
            LiveGreenEntryButton(hitPath: Path(CGRect(x: 0, y: 0, width: 76, height: 76))) {
                opened += 1
            }
            .frame(width: 76, height: 76)
        )
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 200, height: 200))
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer { window.isHidden = true }
        host.view.layoutIfNeeded()
        func control(in view: UIView) -> LiveGreenEntryButton.Control? {
            if let button = view as? LiveGreenEntryButton.Control { return button }
            return view.subviews.lazy.compactMap { control(in: $0) }.first
        }
        let button = try XCTUnwrap(control(in: host.view))
        XCTAssertTrue(button.isAccessibilityElement)
        XCTAssertTrue(button.accessibilityTraits.contains(.button))
        XCTAssertEqual(button.accessibilityLabel, "调整旗位")
        XCTAssertEqual(button.alpha, 1)
        let centre = button.convert(CGPoint(x: 38, y: 38), to: nil)
        let coveringChrome = CGRect(x: centre.x - 10, y: centre.y - 10, width: 20, height: 20)
        button.activationExclusions = [coveringChrome]
        let activation = button.accessibilityActivationPoint
        XCTAssertFalse(coveringChrome.contains(activation), "the accessible tap avoids floating chrome")
        XCTAssertTrue(button.point(inside: button.convert(activation, from: nil), with: nil), "the accessible tap remains inside the green")
        XCTAssertTrue(button.accessibilityActivate())
        XCTAssertEqual(opened, 1, "accessibility activation opens flag placement exactly once")
        button.sendActions(for: .touchUpInside)
        XCTAssertEqual(opened, 2, "touch dispatches the same flag placement action")
        button.isEnabled = false
        XCTAssertFalse(button.accessibilityActivate())
        XCTAssertEqual(opened, 2, "disabled controls cannot activate")
    }
}
