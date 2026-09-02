import CoreLocation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

#if canImport(UIKit)
/// S70-style Touch Target surface for the phone. The whole-hole map remains the factual source; this
/// view only adds a reversible viewport transform and a target coordinate. A target is never treated
/// as a GPS fix, so the same surface works when the player is at home or has no satellite lock.
public struct LivePlayMapDetailView: View {
    @Environment(\.dismiss) private var dismiss

    public let hole: CoursePrepHole
    public let topoURL: URL?
    public let selectedClub: String?
    public let selectedClubMetres: Double?
    @Binding public var targetCoordinate: CLLocationCoordinate2D?
    /// The map pixel is a separate fact from `targetCoordinate`.  It keeps Touch Target usable for
    /// a searched/off-course course whose projection anchors have not arrived yet.
    @Binding public var targetPixel: CGPoint?
    public let referenceCoordinate: CLLocationCoordinate2D?
    public let referenceIsLive: Bool
    public let pinCoordinate: CLLocationCoordinate2D?
    public let onTargetChanged: (CLLocationCoordinate2D?) -> Void
    public let onTargetCommitted: (CLLocationCoordinate2D?) -> Void
    public let onTargetPixelChanged: (CGPoint?) -> Void
    public let onTargetPixelCommitted: (CGPoint?) -> Void

    @State private var scale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var transientDragOffset: CGSize = .zero
    @State private var interactionMode: InteractionMode?
    /// Screen-space focus while the Touch Target is being fine-tuned. This is transient display
    /// state; the coordinate binding remains the sole source of truth for the selected point.
    @State private var targetDragLocation: CGPoint?
    /// Local fallback makes the view useful even for callers that do not persist a pixel binding
    /// (including previews). Production passes the parent round's binding so reopening the detail
    /// surface keeps the selected map point visible.
    @State private var fallbackTargetPixel: CGPoint?
    @State private var didDrag = false
    @GestureState private var pinchScale: CGFloat = 1

    private enum InteractionMode {
        case target
        case pan
    }

    public init(
        hole: CoursePrepHole,
        topoURL: URL?,
        selectedClub: String? = nil,
        selectedClubMetres: Double? = nil,
        targetCoordinate: Binding<CLLocationCoordinate2D?>,
        referenceCoordinate: CLLocationCoordinate2D?,
        referenceIsLive: Bool,
        pinCoordinate: CLLocationCoordinate2D?,
        onTargetChanged: @escaping (CLLocationCoordinate2D?) -> Void = { _ in },
        onTargetCommitted: @escaping (CLLocationCoordinate2D?) -> Void = { _ in },
        targetPixel: Binding<CGPoint?> = .constant(nil),
        onTargetPixelChanged: @escaping (CGPoint?) -> Void = { _ in },
        onTargetPixelCommitted: @escaping (CGPoint?) -> Void = { _ in }
    ) {
        self.hole = hole
        self.topoURL = topoURL
        self.selectedClub = selectedClub
        self.selectedClubMetres = selectedClubMetres
        _targetCoordinate = targetCoordinate
        _targetPixel = targetPixel
        self.referenceCoordinate = referenceCoordinate
        self.referenceIsLive = referenceIsLive
        self.pinCoordinate = pinCoordinate
        self.onTargetChanged = onTargetChanged
        self.onTargetCommitted = onTargetCommitted
        self.onTargetPixelChanged = onTargetPixelChanged
        self.onTargetPixelCommitted = onTargetPixelCommitted
    }

    public var body: some View {
        ZStack(alignment: .top) {
            LivePlayStyle.base.ignoresSafeArea()
            if let overlay = hole.resolvedMapOverlay, overlay.w > 0, overlay.h > 0 {
                GeometryReader { proxy in
                    mapViewport(overlay: overlay, size: proxy.size)
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "map")
                        .font(.system(size: 34, weight: .semibold))
                    Text("这洞暂时没有可交互地图")
                        .font(.headline)
                    Text("地图数据准备好后可重新打开")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.65))
                }
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }

            header
        }
        .preferredColorScheme(.dark)
        .statusBarHidden(false)
    }

    private var header: some View {
        HStack(spacing: 10) {
            Button { dismiss() } label: {
                Image(systemName: "chevron.backward")
                    .font(.system(size: 15, weight: .bold))
                    .frame(width: 40, height: 40)
                    .background(Color.black.opacity(0.68), in: Circle())
                    .overlay(Circle().stroke(Color.white.opacity(0.2)))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("关闭详细地图")
            Text("第 \(hole.hole) 洞 · Touch Target")
                .font(.headline.weight(.heavy))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Spacer(minLength: 0)
            Text("点图放置目标")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.72))
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [LivePlayStyle.base.opacity(0.95), LivePlayStyle.base.opacity(0)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea(edges: .top)
        )
    }

    @ViewBuilder
    private func mapViewport(overlay: CoursePrepOverlay, size: CGSize) -> some View {
        let displayedOffset = CGSize(
            width: offset.width + transientDragOffset.width,
            height: offset.height + transientDragOffset.height
        )
        let displayedScale = min(max(scale * pinchScale, 1), 4)

        ZStack(alignment: .topTrailing) {
            mapContent(overlay: overlay, size: size)
            .frame(width: size.width, height: size.height)
            .scaleEffect(displayedScale)
            .offset(displayedOffset)

            // S70-style precision affordance: while the target handle is held, show the same
            // transformed course map in a circular loupe. The crosshair is centered on the finger,
            // so a small movement is observable without hiding the source point under the fingertip.
            if let focus = targetDragLocation, interactionMode == .target {
                LiveMapTargetMagnifierLoupe(
                    mapSize: size,
                    focus: focus,
                    displayedScale: displayedScale,
                    displayedOffset: displayedOffset,
                    diameter: 124,
                    magnification: 2.35
                ) {
                    mapContent(overlay: overlay, size: size)
                }
                .position(targetLoupePosition(focus, in: size))
                .allowsHitTesting(false)
            }

            // Keep map gestures on a dedicated layer. Controls and the distance sheet are siblings
            // above it, so a pan or tap can never steal their button hit tests.
            mapInteractionLayer(overlay: overlay, size: size)

            VStack(spacing: 9) {
                mapControl(system: "plus.magnifyingglass", label: "放大地图", identifier: "live-map-zoom-in") {
                    changeScale(by: 0.5, in: size)
                }
                mapControl(system: "minus.magnifyingglass", label: "缩小地图", identifier: "live-map-zoom-out") {
                    changeScale(by: -0.5, in: size)
                }
                mapControl(system: "scope", label: "还原全洞", identifier: "live-map-fit") {
                    resetViewport()
                }
            }
            .padding(.trailing, 12)
            .padding(.top, 92)

            VStack {
                Spacer()
                distancePanel(overlay: overlay)
                    .padding(.horizontal, 14)
                    .padding(.bottom, 18)
            }
        }
        .frame(width: size.width, height: size.height)
        .clipped()
    }

    private func mapInteractionLayer(overlay: CoursePrepOverlay, size: CGSize) -> some View {
        Rectangle()
            .fill(.clear)
            .frame(width: size.width, height: size.height)
            .contentShape(Rectangle())
            .gesture(dragGesture(overlay: overlay, size: size))
            .simultaneousGesture(
                MagnificationGesture()
                    .updating($pinchScale) { value, state, _ in
                        state = value
                    }
                    .onEnded { value in
                        scale = min(max(scale * value, 1), 4)
                        offset = clamped(offset, in: size, scale: scale)
                    }
            )
            .simultaneousGesture(
                SpatialTapGesture()
                    .onEnded { value in
                        guard !didDrag else { return }
                        guard let pixel = pixel(
                            at: value.location,
                            overlay: overlay,
                            size: size,
                            scale: scale,
                            offset: offset
                        ) else { return }
                        applyTarget(pixel: pixel, overlay: overlay, committed: true)
                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    }
            )
            .accessibilityHidden(true)
    }

    /// The base map and its target/reference vectors are rendered once for the main viewport and
    /// once for the loupe. Keeping this in one builder prevents the two surfaces from drifting when
    /// a club recommendation or target coordinate changes during a drag.
    @ViewBuilder
    private func mapContent(overlay: CoursePrepOverlay, size: CGSize) -> some View {
        ZStack {
            HoleImageMapView(
                hole: hole,
                selectedClub: selectedClub,
                selectedClubMetres: selectedClubMetres,
                topoURL: topoURL,
                showsCardChrome: false,
                showsRecommendedRoute: true,
                showsHazards: true
            )
            .frame(width: size.width, height: size.height)

            Canvas { context, _ in
                drawTargetLine(&context, size: size, overlay: overlay)
            }

            if let target = targetBasePoint(overlay: overlay, size: size) {
                Circle()
                    .fill(Color.orange.opacity(0.22))
                    .frame(width: 64, height: 64)
                    .overlay(Circle().stroke(Color.orange, lineWidth: 2.5))
                    .overlay(
                        Image(systemName: "scope")
                            .font(.system(size: 21, weight: .bold))
                            .foregroundStyle(.white)
                    )
                    .position(target)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("目标点")
                    .accessibilityIdentifier("live-map-target-marker")
            }

            if let reference = referenceBasePoint(overlay: overlay, size: size) {
                Circle()
                    .fill(referenceIsLive ? Color.blue : Color.white)
                    .frame(width: 18, height: 18)
                    .overlay(Circle().stroke(Color.black.opacity(0.7), lineWidth: 2))
                    .position(reference)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(referenceIsLive ? "当前位置" : "发球台参考点")
            }
        }
        .frame(width: size.width, height: size.height)
    }

    private func distancePanel(overlay: CoursePrepOverlay) -> some View {
        let resolvedPixelDistances = pixelDistances(overlay: overlay)
        let hasTarget = effectiveTargetPixel(overlay: overlay) != nil || targetCoordinate != nil
        let firstDistance = referenceIsLive
            ? distanceYards(from: referenceCoordinate, to: targetCoordinate)
                ?? resolvedPixelDistances?.referenceToTargetYards
            : resolvedPixelDistances?.referenceToTargetYards
                ?? distanceYards(from: referenceCoordinate, to: targetCoordinate)
        let secondDistance = resolvedPixelDistances?.targetToPinYards
            ?? distanceYards(from: targetCoordinate, to: pinCoordinate)
        VStack(alignment: .leading, spacing: 7) {
            if hasTarget {
                HStack(spacing: 14) {
                    distanceValue(
                        label: referenceIsLive ? "当前位置 → 目标" : "发球台 → 目标",
                        value: firstDistance,
                        tint: .white
                    )
                    Divider().frame(height: 32).overlay(Color.white.opacity(0.25))
                    distanceValue(
                        label: "目标 → 旗位",
                        value: secondDistance,
                        tint: LivePlayStyle.front
                    )
                }
                Button {
                    clearTarget()
                } label: {
                    Label("清除目标点", systemImage: "xmark.circle")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white.opacity(0.78))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("live-map-clear-target")
            } else {
                Label("点击地图放置目标点", systemImage: "scope")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                Text("可拖动目标圈；地图外区域不会产生目标点")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.65))
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.78), in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 15).stroke(Color.white.opacity(0.18)))
        .accessibilityIdentifier("live-map-distance-panel")
    }

    private func distanceValue(label: String, value: Int?, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.white.opacity(0.62))
            Text(value.map { "\(GeoDistance.greenRangeText($0)) 码" } ?? "—")
                .font(.system(size: 22, weight: .heavy, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func mapControl(
        system: String,
        label: String,
        identifier: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: system)
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(.black)
                .frame(width: 42, height: 42)
                .background(Color.white.opacity(0.95), in: Circle())
                .shadow(color: .black.opacity(0.28), radius: 4, y: 2)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }

    private func changeScale(by delta: CGFloat, in size: CGSize) {
        withAnimation(.easeInOut(duration: 0.18)) {
            scale = min(max(scale + delta, 1), 4)
            offset = clamped(offset, in: size, scale: scale)
        }
    }

    private func resetViewport() {
        withAnimation(.easeInOut(duration: 0.18)) {
            scale = 1
            offset = .zero
            transientDragOffset = .zero
        }
    }

    private func dragGesture(overlay: CoursePrepOverlay, size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 5)
            .onChanged { value in
                if interactionMode == nil {
                    let targetPoint = targetScreenPoint(
                        overlay: overlay,
                        size: size,
                        scale: scale,
                        offset: offset
                    )
                    if let targetPoint,
                       hypot(targetPoint.x - value.startLocation.x, targetPoint.y - value.startLocation.y) <= 42 {
                        interactionMode = .target
                    } else if scale > 1.01 {
                        interactionMode = .pan
                    } else {
                        interactionMode = .target
                    }
                }
                didDrag = true
                switch interactionMode {
                case .target:
                    targetDragLocation = value.location
                    if let pixel = pixel(
                        at: value.location,
                        overlay: overlay,
                        size: size,
                        scale: scale,
                        offset: offset,
                        clampToMap: true
                    ) {
                        applyTarget(pixel: pixel, overlay: overlay, committed: false)
                    }
                case .pan:
                    targetDragLocation = nil
                    transientDragOffset = value.translation
                case nil:
                    break
                }
            }
            .onEnded { value in
                defer {
                    interactionMode = nil
                    targetDragLocation = nil
                    transientDragOffset = .zero
                    // A SpatialTapGesture can be delivered in the same run loop as DragGesture.
                    // Keep it suppressed for that delivery so a drag does not create a second point.
                    DispatchQueue.main.async { didDrag = false }
                }
                switch interactionMode {
                case .target:
                    if let pixel = pixel(
                        at: value.location,
                        overlay: overlay,
                        size: size,
                        scale: scale,
                        offset: offset,
                        clampToMap: true
                    ) {
                        applyTarget(pixel: pixel, overlay: overlay, committed: true)
                    }
                case .pan:
                    offset = clamped(
                        CGSize(
                            width: offset.width + value.translation.width,
                            height: offset.height + value.translation.height
                        ),
                        in: size,
                        scale: scale
                    )
                case nil:
                    break
                }
            }
    }

    private func drawTargetLine(
        _ context: inout GraphicsContext,
        size: CGSize,
        overlay: CoursePrepOverlay
    ) {
        guard let target = targetBasePoint(overlay: overlay, size: size),
              let pinPx = pinPixel(overlay: overlay),
              let pin = LivePlayMapOverlayLayout.project(
                  overlayPoint: [pinPx.x, pinPx.y],
                  overlayWidth: overlay.w,
                  overlayHeight: overlay.h,
                  into: size
              ) else { return }
        var path = Path()
        path.move(to: target)
        path.addLine(to: pin)
        context.stroke(
            path,
            with: .color(Color.orange.opacity(0.92)),
            style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [7, 5])
        )
    }

    /// The currently selected point in the overlay's factual pixel frame.  Prefer the explicit pixel
    /// binding/local fallback; a coordinate is projected only when the course supplied anchors.
    private func effectiveTargetPixel(overlay: CoursePrepOverlay) -> CGPoint? {
        if let targetPixel, validPixel(targetPixel, overlay: overlay) {
            return targetPixel
        }
        if let fallbackTargetPixel, validPixel(fallbackTargetPixel, overlay: overlay) {
            return fallbackTargetPixel
        }
        guard let targetCoordinate,
              let projected = project(coordinate: targetCoordinate) else { return nil }
        return CGPoint(x: projected[0], y: projected[1])
    }

    private func referencePixel(overlay: CoursePrepOverlay) -> CGPoint? {
        if let referenceCoordinate,
           let projected = project(coordinate: referenceCoordinate) {
            return CGPoint(x: projected[0], y: projected[1])
        }
        return routePixel(overlay.route.first)
    }

    private func pinPixel(overlay: CoursePrepOverlay) -> CGPoint? {
        if let pinCoordinate,
           let projected = project(coordinate: pinCoordinate) {
            return CGPoint(x: projected[0], y: projected[1])
        }
        return routePixel(overlay.route.last)
    }

    private func routePixel(_ row: [Double]?) -> CGPoint? {
        guard let row, row.count >= 2,
              row[0].isFinite, row[1].isFinite else { return nil }
        return CGPoint(x: row[0], y: row[1])
    }

    private func validPixel(_ pixel: CGPoint, overlay: CoursePrepOverlay) -> Bool {
        pixel.x.isFinite && pixel.y.isFinite
            && overlay.w > 0 && overlay.h > 0
            && pixel.x >= 0 && pixel.y >= 0
            && pixel.x <= CGFloat(overlay.w)
            && pixel.y <= CGFloat(overlay.h)
    }

    private func pixelDistances(overlay: CoursePrepOverlay) -> LiveMapPixelDistances? {
        guard let reference = referencePixel(overlay: overlay),
              let target = effectiveTargetPixel(overlay: overlay),
              let pin = pinPixel(overlay: overlay) else { return nil }
        return LiveMapPixelDistanceLayout.resolve(
            referencePx: reference,
            targetPx: target,
            pinPx: pin,
            pixelsPerMetre: overlay.ppm
        )
    }

    private func applyTarget(pixel: CGPoint, overlay: CoursePrepOverlay, committed: Bool) {
        guard validPixel(pixel, overlay: overlay) else { return }
        let coordinate = coordinate(for: pixel)

        // Resolve the geo projection before publishing either binding. If the searched course has
        // no refs, explicitly clear a coordinate left by an earlier map revision; the pixel remains
        // a valid session-local target and distance source, but it can never masquerade as WGS84.
        fallbackTargetPixel = pixel
        targetCoordinate = coordinate
        onTargetChanged(coordinate)
        targetPixel = pixel
        onTargetPixelChanged(pixel)

        if committed {
            // A coordinate commit is the durable source when projection is available. Pixel-only
            // commits stay local and merely refresh the caddie/distance surface in the parent.
            if let coordinate {
                onTargetCommitted(coordinate)
            }
            onTargetPixelCommitted(pixel)
        }
    }

    private func clearTarget() {
        fallbackTargetPixel = nil
        targetPixel = nil
        targetCoordinate = nil
        onTargetChanged(nil)
        onTargetPixelChanged(nil)
        // Coordinate commit owns the explicit clear. Do not also commit the pixel binding, or the
        // parent would append two identical nil target events and trigger two caddie refreshes.
        onTargetCommitted(nil)
    }

    private func targetScreenPoint(
        overlay: CoursePrepOverlay,
        size: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) -> CGPoint? {
        guard let pixel = effectiveTargetPixel(overlay: overlay),
              let base = LivePlayMapOverlayLayout.project(
                overlayPoint: [pixel.x, pixel.y],
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                into: size
              ) else { return nil }
        return transformed(base: base, in: size, scale: scale, offset: offset)
    }

    private func targetBasePoint(overlay: CoursePrepOverlay, size: CGSize) -> CGPoint? {
        guard let pixel = effectiveTargetPixel(overlay: overlay) else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: [pixel.x, pixel.y],
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: size
        )
    }

    private func referenceScreenPoint(
        overlay: CoursePrepOverlay,
        size: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) -> CGPoint? {
        guard let pixel = referencePixel(overlay: overlay),
              let base = LivePlayMapOverlayLayout.project(
                  overlayPoint: [pixel.x, pixel.y],
                  overlayWidth: overlay.w,
                  overlayHeight: overlay.h,
                  into: size
              ) else { return nil }
        return transformed(base: base, in: size, scale: scale, offset: offset)
    }

    private func referenceBasePoint(overlay: CoursePrepOverlay, size: CGSize) -> CGPoint? {
        guard let pixel = referencePixel(overlay: overlay) else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: [pixel.x, pixel.y],
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: size
        )
    }

    private func pixel(
        at screenPoint: CGPoint,
        overlay: CoursePrepOverlay,
        size: CGSize,
        scale: CGFloat,
        offset: CGSize,
        clampToMap: Bool = false
    ) -> CGPoint? {
        let basePoint = inverseTransform(screenPoint, in: size, scale: scale, offset: offset)
        guard let px = LivePlayMapOverlayLayout.unproject(
            screenPoint: basePoint,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            from: size,
            clampToMap: clampToMap
        ) else { return nil }
        return CGPoint(x: px[0], y: px[1])
    }

    private func coordinate(for pixel: CGPoint) -> CLLocationCoordinate2D? {
        guard pixel.x.isFinite, pixel.y.isFinite,
              let refs = hole.holeImageProjection?.refs,
              let coordinate = WatchEventBridge.projectFromTopoPx(
                  px: pixel.x,
                  py: pixel.y,
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ) else { return nil }
        return CLLocationCoordinate2D(latitude: coordinate.latitude, longitude: coordinate.longitude)
    }

    private func project(coordinate: CLLocationCoordinate2D) -> [Double]? {
        guard let refs = hole.holeImageProjection?.refs else { return nil }
        return WatchEventBridge.projectToTopoPx(
            lat: coordinate.latitude,
            lon: coordinate.longitude,
            refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
        )
    }

    private func transformed(base: CGPoint?, in size: CGSize, scale: CGFloat, offset: CGSize) -> CGPoint? {
        guard let base else { return nil }
        return CGPoint(
            x: (base.x - size.width / 2) * scale + size.width / 2 + offset.width,
            y: (base.y - size.height / 2) * scale + size.height / 2 + offset.height
        )
    }

    private func inverseTransform(_ point: CGPoint, in size: CGSize, scale: CGFloat, offset: CGSize) -> CGPoint {
        let safeScale = max(scale, 0.001)
        return CGPoint(
            x: (point.x - size.width / 2 - offset.width) / safeScale + size.width / 2,
            y: (point.y - size.height / 2 - offset.height) / safeScale + size.height / 2
        )
    }

    private func clamped(_ value: CGSize, in size: CGSize, scale: CGFloat) -> CGSize {
        guard scale > 1 else { return .zero }
        let maxX = size.width * (scale - 1) / 2
        let maxY = size.height * (scale - 1) / 2
        return CGSize(
            width: min(max(value.width, -maxX), maxX),
            height: min(max(value.height, -maxY), maxY)
        )
    }

    /// Keep the loupe fully visible, clear of the header and the bottom distance sheet. The target
    /// itself may be near any edge because the map coordinate is still allowed to move there.
    private func targetLoupePosition(_ location: CGPoint, in size: CGSize) -> CGPoint {
        let diameter: CGFloat = 124
        let half = diameter / 2
        let minX = half + 8
        let maxX = max(minX, size.width - half - 8)
        let minY = half + 78
        let maxY = max(minY, size.height - half - 132)
        let x = min(max(location.x, minX), maxX)
        let above = location.y - half - 26
        let below = location.y + half + 26
        let preferred = above >= minY ? above : below
        return CGPoint(x: x, y: min(max(preferred, minY), maxY))
    }

    private func distanceYards(
        from start: CLLocationCoordinate2D?,
        to end: CLLocationCoordinate2D?
    ) -> Int? {
        guard let start, let end else { return nil }
        return GeoDistance.yards(
            from: start.latitude,
            start.longitude,
            to: end.latitude,
            end.longitude
        )
    }
}

/// Circular, transform-aware loupe used by the phone Touch Target surface. The main map applies
/// `C + s(p-C) + O`; the extra magnification keeps the exact source pixel under the finger at the
/// loupe crosshair even after pinch zooming or map panning.
private struct LiveMapTargetMagnifierLoupe<Content: View>: View {
    let content: Content
    let mapSize: CGSize
    let focus: CGPoint
    let displayedScale: CGFloat
    let displayedOffset: CGSize
    let diameter: CGFloat
    let magnification: CGFloat

    init(
        mapSize: CGSize,
        focus: CGPoint,
        displayedScale: CGFloat,
        displayedOffset: CGSize,
        diameter: CGFloat,
        magnification: CGFloat,
        @ViewBuilder content: () -> Content
    ) {
        self.content = content()
        self.mapSize = mapSize
        self.focus = focus
        self.displayedScale = displayedScale
        self.displayedOffset = displayedOffset
        self.diameter = diameter
        self.magnification = magnification
    }

    var body: some View {
        let safeScale = max(displayedScale.isFinite ? displayedScale : 1, 0.001)
        let safeMagnification = max(magnification.isFinite ? magnification : 1, 1)
        let safeFocus = CGPoint(
            x: focus.x.isFinite ? focus.x : mapSize.width / 2,
            y: focus.y.isFinite ? focus.y : mapSize.height / 2
        )
        let center = CGPoint(x: mapSize.width / 2, y: mapSize.height / 2)
        let dx = diameter / 2
            + safeMagnification * ((1 - safeScale) * center.x + displayedOffset.width - safeFocus.x)
        let dy = diameter / 2
            + safeMagnification * ((1 - safeScale) * center.y + displayedOffset.height - safeFocus.y)

        ZStack(alignment: .topLeading) {
            content
                .frame(width: mapSize.width, height: mapSize.height)
                .scaleEffect(safeScale * safeMagnification, anchor: .topLeading)
                .offset(x: dx, y: dy)
        }
        .frame(width: diameter, height: diameter, alignment: .topLeading)
        .clipShape(Circle())
        .overlay {
            ZStack {
                Rectangle().fill(.white.opacity(0.95)).frame(width: 1.4, height: 18)
                Rectangle().fill(.white.opacity(0.95)).frame(width: 18, height: 1.4)
            }
            .shadow(color: .black.opacity(0.6), radius: 0.6)
        }
        .overlay(Circle().strokeBorder(.white, lineWidth: 3))
        .overlay(Circle().strokeBorder(.black.opacity(0.24), lineWidth: 1))
        .compositingGroup()
        .shadow(color: .black.opacity(0.38), radius: 7, y: 3)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("拖动目标点时的放大视图")
        .accessibilityIdentifier("live-map-target-magnifier")
    }
}
#endif
