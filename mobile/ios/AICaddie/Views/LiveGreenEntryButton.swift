import SwiftUI
import UIKit

enum LiveGreenEntryTapDestination: Equatable {
    case greenDetail
    case mapTarget
}

enum LiveGreenEntryHitRegion {
    static let fallbackDiameter: CGFloat = 76

    // This preserves the current contour-only behavior until the fallback region is wired in.
    static func path(greenPath: Path?, fallbackCenter: CGPoint?) -> Path? {
        greenPath
    }

    static func destination(at location: CGPoint, path: Path?) -> LiveGreenEntryTapDestination {
        path?.contains(location) == true ? .greenDetail : .mapTarget
    }
}

/// A real, full-alpha control over the already drawn green. Its clear background leaves the
/// map intact; UIKit owns both contour hit testing and the default accessibility action.
struct LiveGreenEntryButton: UIViewRepresentable {
    let hitPath: Path
    var exclusions: [CGRect] = []
    let action: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(action: action) }

    func makeUIView(context: Context) -> Container {
        let container = Container(frame: .zero)
        let control = container.control
        control.backgroundColor = .clear
        control.isAccessibilityElement = true
        control.accessibilityLabel = "调整旗位"
        control.accessibilityIdentifier = "live-open-green-from-hero"
        control.accessibilityTraits = .button
        control.addTarget(context.coordinator, action: #selector(Coordinator.activate), for: .touchUpInside)
        return container
    }

    func updateUIView(_ container: Container, context: Context) {
        let control = container.control
        control.hitPath = hitPath.cgPath
        // Nested reports include both a padded chrome group and its real control. Only the
        // innermost frame blocks touch; counting the padded group would hide exposed map space.
        control.activationExclusions = exclusions.filter { rect in
            !exclusions.contains { other in other != rect && rect.contains(other) }
        }
        context.coordinator.action = action
    }

    final class Coordinator: NSObject {
        var action: () -> Void
        init(action: @escaping () -> Void) { self.action = action; super.init() }
        @objc func activate() { action() }
    }

    /// Keep the UIKit button as a child: SwiftUI supplies accessibility for a representable's
    /// root view, while this child retains UIKit's own hit geometry and activation semantics.
    final class Container: UIView {
        let control = Control(frame: .zero)

        override init(frame: CGRect) {
            super.init(frame: frame)
            // Keep the element hittable for VoiceOver/XCTest. Physical touches are routed to
            // the SwiftUI map gesture layer by point(inside:with:) below.
            isUserInteractionEnabled = true
            isAccessibilityElement = false
            addSubview(control)
            accessibilityElements = [control]
        }

        required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

        override func layoutSubviews() {
            super.layoutSubviews()
            control.frame = bounds
        }

        override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {
            // Keep the contour available to UIKit accessibility/XCTest hit testing.
            return control.point(inside: convert(point, to: control), with: event)
        }

        override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
            // Physical touches belong to the SwiftUI map gesture layer. Returning nil after
            // point(inside:) has exposed the contour preserves accessibility hit testing while
            // preventing this sibling from winning the map's touch sequence.
            guard event == nil else { return nil }
            return super.hitTest(point, with: event)
        }
    }

    final class Control: UIButton {
        var hitPath: CGPath?
        var activationExclusions: [CGRect] = []

        override var accessibilityFrame: CGRect {
            get {
                // Accessibility hit testing also uses the frame's centre. Report the exposed
                // part of the contour rather than a centre hidden by a floating control.
                let full = super.accessibilityFrame
                var visible = [full]
                for chrome in activationExclusions {
                    visible = visible.flatMap { rect -> [CGRect] in
                        let cut = rect.intersection(chrome)
                        guard !cut.isNull, !cut.isEmpty else { return [rect] }
                        return [
                            CGRect(x: rect.minX, y: rect.minY, width: rect.width, height: cut.minY - rect.minY),
                            CGRect(x: rect.minX, y: cut.maxY, width: rect.width, height: rect.maxY - cut.maxY),
                            CGRect(x: rect.minX, y: rect.minY, width: cut.minX - rect.minX, height: rect.height),
                            CGRect(x: cut.maxX, y: rect.minY, width: rect.maxX - cut.maxX, height: rect.height),
                        ].filter { !$0.isEmpty }
                    }
                }
                return visible.filter {
                    point(inside: convert(CGPoint(x: $0.midX, y: $0.midY), from: nil), with: nil)
                }.max(by: { $0.width * $0.height < $1.width * $1.height }) ?? full
            }
            set { super.accessibilityFrame = newValue }
        }

        override var accessibilityActivationPoint: CGPoint {
            get {
                let exposed = accessibilityFrame
                let centre = CGPoint(x: exposed.midX, y: exposed.midY)
                if point(inside: convert(centre, from: nil), with: nil),
                   !activationExclusions.contains(where: { $0.contains(centre) }) {
                    return centre
                }
                // Prefer the centre, then nearby contour points. Floating controls can cover
                // part of a small green; the accessible tap must land on its visible surface.
                let fractions: [CGFloat] = [0.5, 0.25, 0.75, 0.125, 0.875]
                for y in fractions {
                    for x in fractions {
                        let local = CGPoint(x: bounds.width * x, y: bounds.height * y)
                        let screen = convert(local, to: nil)
                        if point(inside: local, with: nil),
                           !activationExclusions.contains(where: { $0.contains(screen) }) {
                            return screen
                        }
                    }
                }
                return super.accessibilityActivationPoint
            }
            set { super.accessibilityActivationPoint = newValue }
        }

        override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {
            super.point(inside: point, with: event) && (hitPath?.contains(point) ?? false)
        }

        override func accessibilityActivate() -> Bool {
            guard isEnabled else { return false }
            sendActions(for: .touchUpInside)
            return true
        }
    }
}
