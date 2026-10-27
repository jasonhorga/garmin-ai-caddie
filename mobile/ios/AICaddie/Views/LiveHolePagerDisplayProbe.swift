import Foundation
import SwiftUI
import UIKit

/// A non-owning render acknowledgement: the callback runs after SwiftUI has delivered this
/// selection to the existing TabView in the same update pass. It never replaces a controller.
struct LiveHolePagerDisplayProbe: UIViewRepresentable {
    let selection: Int?
    let requestID: UUID
    let didUpdate: (UUID, Int?) -> Void

    final class Coordinator {
        var lastSelection: Int?
        var lastRequestID: UUID?
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> UIView {
        let view = UIView(frame: .zero)
        view.isUserInteractionEnabled = false
        view.isAccessibilityElement = false
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        #if DEBUG
        UITestPagerTrace.shared.metric(.displayProbeUpdate)
        #endif
        let displayed = selection
        let request = requestID
        guard context.coordinator.lastSelection != displayed
            || context.coordinator.lastRequestID != request else { return }
        context.coordinator.lastSelection = displayed
        context.coordinator.lastRequestID = request
        DispatchQueue.main.async { didUpdate(request, displayed) }
    }

    /// Requested-sheet preferences cover the frame before UIKit presents. This check also covers
    /// UIKit's dismissal animation after a sheet's binding/content have already disappeared.
    @MainActor static var presentationIsActive: Bool {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows).filter { !$0.isHidden }
            .contains { window in
                window.rootViewController.map { hasPresentation($0) } ?? false
            }
    }

    @MainActor private static func hasPresentation(_ controller: UIViewController) -> Bool {
        controller.presentedViewController != nil || controller.isBeingPresented
            || controller.isBeingDismissed || controller.children.contains { hasPresentation($0) }
    }
}

struct LiveHolePagerPresentationKey: PreferenceKey {
    static let defaultValue = false

    static func reduce(value: inout Bool, nextValue: () -> Bool) {
        value = value || nextValue()
    }
}
