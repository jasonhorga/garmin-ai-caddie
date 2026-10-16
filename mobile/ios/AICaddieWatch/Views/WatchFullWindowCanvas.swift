import SwiftUI

/// Safe-area geometry per face, measured by the #417 / #422 simulator audits (watchOS 26.2). The
/// top inset is the band the system clock (top right) shares with a title (top left).
public enum WatchFaceInsets {
    /// Bottom safe-area inset in points by window height; measured except 40 mm.
    public static func bottom(forHeight height: CGFloat) -> CGFloat {
        switch height {
        case ..<206: return 24     // 40 mm (estimate)
        case ..<219: return 26     // 41 mm
        case ..<232: return 31     // 42 / 44 mm
        case ..<245: return 27     // 45 mm
        case ..<249.5: return 36   // 46 mm
        default: return 39         // 49 mm
        }
    }

    /// Top safe-area inset (the clock band) in points by window height; measured except 40 mm.
    public static func top(forHeight height: CGFloat) -> CGFloat {
        switch height {
        case ..<206: return 44     // 40 mm (estimate)
        case ..<219: return 46     // 41 mm
        case ..<232: return 48     // 42 / 44 mm
        case ..<245: return 51     // 45 mm
        case ..<249.5: return 53   // 46 mm
        default: return 55         // 49 mm
        }
    }

    public static let edge: CGFloat = 10
    /// Room the system clock takes at the right of the top band.
    public static let clockWidth: CGFloat = 56
}

/// A full-window screen, the hierarchy the #422 audit proved: every control fired 5/5 at centre and
/// +8 pt on 41/42/45/46/49 mm, where the older safe-area-bound screens lost taps near the bottom.
/// Content gets the window size, the clock band's height and the lowest y a control should use.
/// Design snapshots (no safe area under ImageRenderer) pass `snapshotInsets`.
struct WatchFullWindowCanvas<Content: View>: View {
    let snapshotInsets: Bool
    let content: (CGSize, CGFloat, CGFloat) -> Content

    init(snapshotInsets: Bool = false, @ViewBuilder content: @escaping (CGSize, CGFloat, CGFloat) -> Content) {
        self.snapshotInsets = snapshotInsets
        self.content = content
    }

    var body: some View {
        GeometryReader { outer in
            GeometryReader { full in
                let size = full.size
                let liveTop = outer.safeAreaInsets.top
                let liveBottom = outer.safeAreaInsets.bottom
                // A container that reports no inset falls back to the measured table.
                let top = !snapshotInsets && liveTop > 0 ? liveTop : WatchFaceInsets.top(forHeight: size.height)
                let bottom = !snapshotInsets && liveBottom > 0 ? liveBottom : WatchFaceInsets.bottom(forHeight: size.height)
                content(size, top, size.height - bottom)
                    .frame(width: size.width, height: size.height, alignment: .topLeading)
            }
            .ignoresSafeArea()
        }
        .background(Color.black.ignoresSafeArea())
    }
}

/// A title in the top band, left of the system clock (where watchOS puts navigation titles).
func watchTitleBand(_ title: some View, size: CGSize, safeTop: CGFloat) -> some View {
    title
        .frame(
            width: max(0, size.width - WatchFaceInsets.clockWidth - WatchFaceInsets.edge - 4),
            height: safeTop,
            alignment: .leading
        )
        .padding(.leading, WatchFaceInsets.edge + 4)
}
