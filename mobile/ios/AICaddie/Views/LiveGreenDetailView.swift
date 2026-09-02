import CoreLocation
import SwiftUI
import AICaddieDomain
#if canImport(UIKit)
import UIKit
#endif

#if canImport(UIKit)
/// Phone equivalent of Garmin S70's View Green page. The boundary and flag coordinates stay in the
/// full-hole affine frame; only the viewport/crop changes, so moving the flag never invents a new
/// green shape or loses alignment with the normal hole map.
public struct LiveGreenDetailView: View {
    @Environment(\.dismiss) private var dismiss

    public let hole: CoursePrepHole
    public let detailURL: URL?
    public let topoURL: URL?
    @Binding public var targetCoordinate: CLLocationCoordinate2D?
    /// Full-hole topo pixel for the edited flag.  This remains authoritative when a searched
    /// course has a drawable map but no geo projection anchors yet.
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
    @State private var transientOffset: CGSize = .zero
    @State private var draggingFlag = false
    /// The finger's viewport coordinate while the flag is being moved.  This is separate from the
    /// persisted coordinate so the loupe can follow a provisional point without creating another
    /// target event or changing the map's source of truth.
    @State private var flagDragLocation: CGPoint?
    /// Keeps previews and older callers useful when they pass a constant binding. Production callers
    /// pass the round-owned binding above, so reopening View Green retains the selected pixel.
    @State private var fallbackTargetPixel: CGPoint?
    @State private var didDrag = false
    @GestureState private var pinchScale: CGFloat = 1

    public init(
        hole: CoursePrepHole,
        detailURL: URL?,
        topoURL: URL?,
        targetCoordinate: Binding<CLLocationCoordinate2D?>,
        targetPixel: Binding<CGPoint?> = .constant(nil),
        referenceCoordinate: CLLocationCoordinate2D?,
        referenceIsLive: Bool,
        pinCoordinate: CLLocationCoordinate2D?,
        onTargetChanged: @escaping (CLLocationCoordinate2D?) -> Void = { _ in },
        onTargetCommitted: @escaping (CLLocationCoordinate2D?) -> Void = { _ in },
        onTargetPixelChanged: @escaping (CGPoint?) -> Void = { _ in },
        onTargetPixelCommitted: @escaping (CGPoint?) -> Void = { _ in }
    ) {
        self.hole = hole
        self.detailURL = detailURL
        self.topoURL = topoURL
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
            GeometryReader { proxy in
                greenViewport(in: proxy.size)
            }
            header
        }
        .preferredColorScheme(.dark)
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
            .accessibilityLabel("关闭果岭地图")
            Text("第 \(hole.hole) 洞 · 果岭")
                .font(.headline.weight(.heavy))
                .foregroundStyle(.white)
            Spacer(minLength: 0)
            if activeDetailCrop != nil {
                Label("高清", systemImage: "sparkles")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white.opacity(0.75))
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .background(
            LinearGradient(
                colors: [LivePlayStyle.base.opacity(0.96), LivePlayStyle.base.opacity(0)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea(edges: .top)
        )
    }

    @ViewBuilder
    private func greenViewport(in size: CGSize) -> some View {
        let baseRect = activeDetailCrop == nil
            ? CGRect(origin: .zero, size: size)
            : detailRect(in: size)
        let displayedScale = min(max(scale * pinchScale, 1), 4)
        let displayedOffset = CGSize(
            width: offset.width + transientOffset.width,
            height: offset.height + transientOffset.height
        )

        ZStack(alignment: .topTrailing) {
            greenMapContent(size: size, baseRect: baseRect)
            .scaleEffect(displayedScale)
            .offset(displayedOffset)

            // The transparent interaction surface is below controls and the distance panel. A map
            // drag therefore cannot win the hit test for a button layered above it.
            greenInteractionLayer(size: size, baseRect: baseRect)

            // S70-style precision affordance: keep the same transformed map under a circular loupe
            // while the flag is held.  The loupe is display-only and never steals the map gesture.
            if let focus = flagDragLocation, draggingFlag {
                LiveGreenMagnifierLoupe(
                    mapSize: size,
                    focus: focus,
                    displayedScale: displayedScale,
                    displayedOffset: displayedOffset,
                    diameter: 124,
                    magnification: 2.35
                ) {
                    greenMapContent(size: size, baseRect: baseRect)
                }
                .position(loupePosition(focus, in: size))
                .allowsHitTesting(false)
            }

            VStack(spacing: 9) {
                mapControl(system: "plus.magnifyingglass", label: "放大果岭", identifier: "live-green-zoom-in") {
                    changeScale(by: 0.5, in: size)
                }
                mapControl(system: "minus.magnifyingglass", label: "缩小果岭", identifier: "live-green-zoom-out") {
                    changeScale(by: -0.5, in: size)
                }
                mapControl(system: "scope", label: "还原果岭", identifier: "live-green-fit") {
                    resetViewport()
                }
            }
            .padding(.top, 92)
            .padding(.trailing, 12)

            VStack {
                Spacer()
                distancePanel
                    .padding(.horizontal, 14)
                    .padding(.bottom, 18)
            }
        }
        .frame(width: size.width, height: size.height)
        .clipped()
    }

    /// The base bitmap and factual green/flag overlay are intentionally one reusable view.  The
    /// main viewport and the loupe therefore share an identical crop, fallback and vector frame.
    @ViewBuilder
    private func greenMapContent(size: CGSize, baseRect: CGRect) -> some View {
        ZStack {
            if let detailURL, activeDetailCrop != nil, baseRect.width > 0 {
                // Keep the fallback in the same crop coordinate system as the high-resolution
                // response, so an offline/404 request still leaves a usable green map.
                TopoHoleBaseImage(topoURL: detailURL, fallback: detailFallbackImage)
                    .frame(width: baseRect.width, height: baseRect.height)
                    .position(x: baseRect.midX, y: baseRect.midY)
            } else {
                HoleImageMapView(
                    hole: hole,
                    topoURL: topoURL,
                    showsCardChrome: false,
                    showsRecommendedRoute: false,
                    showsHazards: true
                )
                .frame(width: size.width, height: size.height)
            }

            Canvas { context, _ in
                drawGreenOverlay(&context, size: size, baseRect: baseRect)
            }
        }
        .frame(width: size.width, height: size.height)
    }

    private func greenInteractionLayer(size: CGSize, baseRect: CGRect) -> some View {
        Rectangle()
            .fill(.clear)
            .frame(width: size.width, height: size.height)
            .contentShape(Rectangle())
            .gesture(flagOrPanGesture(size: size, baseRect: baseRect))
            .simultaneousGesture(
                MagnificationGesture()
                    .updating($pinchScale) { value, state, _ in state = value }
                    .onEnded { value in
                        scale = min(max(scale * value, 1), 4)
                        offset = clamped(offset, in: size, scale: scale)
                    }
            )
            .simultaneousGesture(
                SpatialTapGesture().onEnded { value in
                    guard !didDrag,
                          let pixel = pixel(
                              at: value.location,
                              size: size,
                              baseRect: baseRect,
                              scale: scale,
                              offset: offset
                          ) else { return }
                    applyFlag(pixel: pixel, committed: true)
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                }
            )
            .accessibilityHidden(true)
    }

    private var distancePanel: some View {
        let pixelDistances = pixelDistances()
        let selectedFlag = targetCoordinate ?? pinCoordinate
        // A pixel-only flag is common while a searched course is still missing projection refs. Its
        // pixel distance must win over any stale/factual pin coordinate supplied by the caller.
        let hasPixelOverride = targetPixel != nil || fallbackTargetPixel != nil
        let firstDistance = hasPixelOverride
            ? (pixelDistances?.referenceToTargetYards
                ?? distanceYards(from: referenceCoordinate, to: selectedFlag))
            : (distanceYards(from: referenceCoordinate, to: selectedFlag)
                ?? pixelDistances?.referenceToTargetYards)
        let secondDistance = hasEditedFlag
            ? (hasPixelOverride
                ? (pixelDistances?.targetToPinYards
                    ?? distanceYards(from: targetCoordinate, to: pinCoordinate))
                : (distanceYards(from: targetCoordinate, to: pinCoordinate)
                    ?? pixelDistances?.targetToPinYards))
            : nil
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 14) {
                distanceValue(
                    label: referenceIsLive ? "当前位置 → 旗位" : "发球台 → 旗位",
                    value: firstDistance,
                    tint: .white
                )
                Divider().frame(height: 32).overlay(Color.white.opacity(0.25))
                distanceValue(
                    label: "旗位 → 果岭中",
                    value: secondDistance,
                    tint: LivePlayStyle.front
                )
            }
            Text(hasEditedFlag ? "旗位只对当前球局生效" : "拖动旗帜可调整本轮旗位")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.68))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.78), in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 15).stroke(Color.white.opacity(0.18)))
        .accessibilityIdentifier("live-green-distance-panel")
    }

    private func distanceValue(label: String, value: Int?, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.system(size: 10, weight: .semibold)).foregroundStyle(.white.opacity(0.62))
            Text(value.map { "\(GeoDistance.greenRangeText($0)) 码" } ?? "—")
                .font(.system(size: 21, weight: .heavy, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.68)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func mapControl(system: String, label: String, identifier: String, action: @escaping () -> Void) -> some View {
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

    private func detailRect(in size: CGSize) -> CGRect {
        let side = min(max(size.width - 20, 1), max(size.height - 178, 1))
        return CGRect(
            x: (size.width - side) / 2,
            y: 66 + max(0, (size.height - 178 - side) / 2),
            width: side,
            height: side
        )
    }

    private func crop() -> GreenDetailCrop? {
        guard let projection = hole.holeImageProjection,
              let width = projection.widthPx,
              let height = projection.heightPx,
              let outline = hole.greenOutline,
              outline.available,
              width > 1,
              height > 1 else { return nil }
        return GreenDetailCrop.around(
            points: outline.pointsPx,
            imageWidth: Double(width),
            imageHeight: Double(height)
        )
    }

    /// A detail URL alone is not enough to switch coordinate systems. The focused asset and the
    /// affine crop must both be valid; otherwise every renderer and touch conversion falls back to
    /// the complete topo frame together.
    private var activeDetailCrop: GreenDetailCrop? {
        guard detailURL != nil else { return nil }
        return crop()
    }

    private var decodedHoleImage: UIImage? {
        guard let uri = hole.map?.image,
              let comma = uri.firstIndex(of: ","),
              let data = Data(base64Encoded: String(uri[uri.index(after: comma)...])) else {
            return nil
        }
        return UIImage(data: data)
    }

    private var detailFallbackImage: UIImage? {
        guard let image = decodedHoleImage,
              let cgImage = image.cgImage,
              let projection = hole.holeImageProjection,
              let width = projection.widthPx,
              let height = projection.heightPx,
              width > 1,
              height > 1,
              let crop = activeDetailCrop else {
            return nil
        }
        // The fallback may be encoded at a different pixel density than the geometry frame. Scale
        // the crop before clipping so the projected outline remains aligned in either case.
        let scaleX = CGFloat(cgImage.width) / CGFloat(width)
        let scaleY = CGFloat(cgImage.height) / CGFloat(height)
        let bounds = CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height)
        let cropRect = CGRect(
            x: CGFloat(crop.x) * scaleX,
            y: CGFloat(crop.y) * scaleY,
            width: CGFloat(crop.width) * scaleX,
            height: CGFloat(crop.height) * scaleY
        ).integral.intersection(bounds)
        guard cropRect.width >= 1,
              cropRect.height >= 1,
              let cropped = cgImage.cropping(to: cropRect) else {
            return nil
        }
        return UIImage(cgImage: cropped, scale: image.scale, orientation: image.imageOrientation)
    }

    private func drawGreenOverlay(_ context: inout GraphicsContext, size: CGSize, baseRect: CGRect) {
        let polygon = hole.greenOutline?.pointsPx ?? []
        let points = polygon.compactMap { fullPixelPoint($0, baseRect: baseRect) }
        if points.count >= 3 {
            var outline = Path()
            outline.move(to: points[0])
            for point in points.dropFirst() { outline.addLine(to: point) }
            outline.closeSubpath()
            context.fill(outline, with: .color(Color.green.opacity(0.18)))
            context.stroke(outline, with: .color(Color.white.opacity(0.86)), style: StrokeStyle(lineWidth: 2.2, lineJoin: .round))
        }

        // The route endpoint is the factual pin fallback when no coordinate projection exists. A
        // pixel-only edited flag must still be visible on a vector map, so this never depends on
        // `projectedPoint` returning a geo coordinate.
        if let flagPoint = effectiveFlagPixel,
           let screen = fullPixelPoint(flagPoint, baseRect: baseRect) {
            context.stroke(
                Path { path in
                    path.move(to: CGPoint(x: screen.x, y: screen.y + 25))
                    path.addLine(to: CGPoint(x: screen.x, y: screen.y - 18))
                    path.addLine(to: CGPoint(x: screen.x + 16, y: screen.y - 11))
                    path.addLine(to: CGPoint(x: screen.x, y: screen.y - 4))
                },
                with: .color(.red),
                style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round)
            )
            context.fill(Path(ellipseIn: CGRect(x: screen.x - 8, y: screen.y - 8, width: 16, height: 16)), with: .color(.red))
            context.stroke(Path(ellipseIn: CGRect(x: screen.x - 11, y: screen.y - 11, width: 22, height: 22)), with: .color(.white), lineWidth: 2)
        }
    }

    private var imageDimensions: (width: Double, height: Double)? {
        if let overlay = hole.resolvedMapOverlay, overlay.w > 1, overlay.h > 1 {
            return (Double(overlay.w), Double(overlay.h))
        }
        if let projection = hole.holeImageProjection,
           let width = projection.widthPx,
           let height = projection.heightPx,
           width > 1,
           height > 1 {
            return (Double(width), Double(height))
        }
        return nil
    }

    private var effectiveFlagPixel: [Double]? {
        if let targetPixel, validPixel(targetPixel) {
            return [Double(targetPixel.x), Double(targetPixel.y)]
        }
        if let fallbackTargetPixel, validPixel(fallbackTargetPixel) {
            return [Double(fallbackTargetPixel.x), Double(fallbackTargetPixel.y)]
        }
        if let targetCoordinate, let projected = projectedPoint(targetCoordinate) {
            return projected
        }
        if let pinCoordinate, let projected = projectedPoint(pinCoordinate) {
            return projected
        }
        return routePixel(hole.resolvedMapOverlay?.route.last)
    }

    private var hasEditedFlag: Bool {
        targetPixel != nil || fallbackTargetPixel != nil || targetCoordinate != nil
    }

    private func routePixel(_ row: [Double]?) -> [Double]? {
        guard let row,
              row.count >= 2,
              row[0].isFinite,
              row[1].isFinite else { return nil }
        return [row[0], row[1]]
    }

    private func validPixel(_ pixel: CGPoint) -> Bool {
        guard pixel.x.isFinite, pixel.y.isFinite else { return false }
        guard let dimensions = imageDimensions else { return true }
        return pixel.x >= 0
            && pixel.y >= 0
            && pixel.x <= CGFloat(dimensions.width)
            && pixel.y <= CGFloat(dimensions.height)
    }

    private func validFlagPixel(_ row: [Double]) -> Bool {
        guard row.count >= 2,
              row[0].isFinite,
              row[1].isFinite else { return false }
        let point = CGPoint(x: row[0], y: row[1])
        guard validPixel(point) else { return false }
        // A malformed/absent outline should not make an otherwise drawable course impossible to
        // edit. When a factual outline exists, keep the flag on its putting surface.
        guard let outline = hole.greenOutline,
              outline.available,
              outline.pointsPx.count >= 3 else { return true }
        return WatchGreenPolygon.contains(row, outline: outline.pointsPx)
    }

    private func pinPixel() -> [Double]? {
        if let pinCoordinate, let projected = projectedPoint(pinCoordinate) {
            return projected
        }
        return routePixel(hole.resolvedMapOverlay?.route.last)
    }

    private func projectedPoint(_ coordinate: CLLocationCoordinate2D) -> [Double]? {
        guard let refs = hole.holeImageProjection?.refs else { return nil }
        return WatchEventBridge.projectToTopoPx(
            lat: coordinate.latitude,
            lon: coordinate.longitude,
            refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
        )
    }

    private func fullPixelPoint(_ row: [Double], baseRect: CGRect) -> CGPoint? {
        guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
        if let crop = activeDetailCrop {
            guard crop.width > 0, crop.height > 0 else { return nil }
            return CGPoint(
                x: baseRect.minX + (CGFloat(row[0] - crop.x) / CGFloat(crop.width)) * baseRect.width,
                y: baseRect.minY + (CGFloat(row[1] - crop.y) / CGFloat(crop.height)) * baseRect.height
            )
        }
        if let overlay = hole.resolvedMapOverlay {
            return LivePlayMapOverlayLayout.project(
                overlayPoint: row,
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                into: baseRect.size
            ).map { CGPoint(x: baseRect.minX + $0.x, y: baseRect.minY + $0.y) }
        }
        guard let dimensions = imageDimensions else { return nil }
        return CGPoint(
            x: baseRect.minX + CGFloat(row[0] / dimensions.width) * baseRect.width,
            y: baseRect.minY + CGFloat(row[1] / dimensions.height) * baseRect.height
        )
    }

    /// Convert a viewport touch through the active zoom/pan and crop back into the full-hole topo
    /// pixel frame. This is the single source used by tap, drag, hit testing, and the loupe.
    private func pixel(
        at point: CGPoint,
        size: CGSize,
        baseRect: CGRect,
        scale: CGFloat,
        offset: CGSize
    ) -> [Double]? {
        let untransformed = CGPoint(
            x: (point.x - size.width / 2 - offset.width) / max(scale, 0.001) + size.width / 2,
            y: (point.y - size.height / 2 - offset.height) / max(scale, 0.001) + size.height / 2
        )
        let fullPx: [Double]?
        if let crop = activeDetailCrop {
            guard baseRect.contains(untransformed) else { return nil }
            guard crop.width > 0, crop.height > 0 else { return nil }
            fullPx = [
                crop.x + Double((untransformed.x - baseRect.minX) / baseRect.width) * crop.width,
                crop.y + Double((untransformed.y - baseRect.minY) / baseRect.height) * crop.height,
            ]
        } else if let overlay = hole.resolvedMapOverlay {
            fullPx = LivePlayMapOverlayLayout.unproject(
                screenPoint: CGPoint(x: untransformed.x - baseRect.minX, y: untransformed.y - baseRect.minY),
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                from: baseRect.size,
                clampToMap: false
            )
        } else if let dimensions = imageDimensions {
            guard baseRect.contains(untransformed) else { return nil }
            fullPx = [
                Double((untransformed.x - baseRect.minX) / baseRect.width) * dimensions.width,
                Double((untransformed.y - baseRect.minY) / baseRect.height) * dimensions.height,
            ]
        } else {
            fullPx = nil
        }
        guard let fullPx, validFlagPixel(fullPx) else { return nil }
        return fullPx
    }

    private func coordinate(for pixel: [Double]) -> CLLocationCoordinate2D? {
        guard pixel.count >= 2,
              let refs = hole.holeImageProjection?.refs,
              let coordinate = WatchEventBridge.projectFromTopoPx(
                  px: pixel[0],
                  py: pixel[1],
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ) else { return nil }
        return CLLocationCoordinate2D(latitude: coordinate.latitude, longitude: coordinate.longitude)
    }

    private func pixelDistances() -> LiveMapPixelDistances? {
        guard let overlay = hole.resolvedMapOverlay,
              let reference = referencePixel(),
              let target = effectiveFlagPixel,
              let pin = pinPixel() else { return nil }
        return LiveMapPixelDistanceLayout.resolve(
            referencePx: CGPoint(x: reference[0], y: reference[1]),
            targetPx: CGPoint(x: target[0], y: target[1]),
            pinPx: CGPoint(x: pin[0], y: pin[1]),
            pixelsPerMetre: overlay.ppm
        )
    }

    private func referencePixel() -> [Double]? {
        if let referenceCoordinate,
           let projected = projectedPoint(referenceCoordinate) {
            return projected
        }
        return routePixel(hole.resolvedMapOverlay?.route.first)
    }

    private func applyFlag(pixel: [Double], committed: Bool) {
        guard validFlagPixel(pixel) else { return }
        let point = CGPoint(x: pixel[0], y: pixel[1])
        let coordinate = coordinate(for: pixel)

        // Resolve the projection before callbacks. A missing projection clears a prior coordinate
        // while preserving the full-hole pixel, so the flag remains draggable/measurable offline
        // without emitting a fabricated location.
        fallbackTargetPixel = point
        targetCoordinate = coordinate
        onTargetChanged(coordinate)
        targetPixel = point
        onTargetPixelChanged(point)

        if committed {
            if let coordinate {
                onTargetCommitted(coordinate)
            }
            // Pixel-only commits are intentionally session-local; the parent still refreshes its
            // distance/caddie surface from the pixel callback above.
            onTargetPixelCommitted(point)
        }
    }

    private func flagOrPanGesture(size: CGSize, baseRect: CGRect) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                if !draggingFlag {
                    if let base = effectiveFlagPixel.flatMap({ fullPixelPoint($0, baseRect: baseRect) }),
                       let screen = transformed(base, in: size, scale: scale, offset: offset),
                       hypot(screen.x - value.startLocation.x, screen.y - value.startLocation.y) <= 44 {
                        draggingFlag = true
                    } else if scale > 1.01 {
                        draggingFlag = false
                    } else {
                        // At fit scale a drag in the green is an intuitive flag placement gesture.
                        draggingFlag = true
                    }
                }
                didDrag = true
                if draggingFlag {
                    flagDragLocation = value.location
                    if let pixel = pixel(
                        at: value.location,
                        size: size,
                        baseRect: baseRect,
                        scale: scale,
                        offset: offset
                    ) {
                        applyFlag(pixel: pixel, committed: false)
                    }
                } else {
                    flagDragLocation = nil
                    transientOffset = value.translation
                }
            }
            .onEnded { value in
                let wasDraggingFlag = draggingFlag
                defer {
                    draggingFlag = false
                    flagDragLocation = nil
                    transientOffset = .zero
                    DispatchQueue.main.async { didDrag = false }
                }
                if wasDraggingFlag {
                    if let pixel = pixel(
                        at: value.location,
                        size: size,
                        baseRect: baseRect,
                        scale: scale,
                        offset: offset
                    ) {
                        applyFlag(pixel: pixel, committed: true)
                    }
                } else {
                    offset = clamped(
                        CGSize(width: offset.width + value.translation.width, height: offset.height + value.translation.height),
                        in: size,
                        scale: scale
                    )
                }
            }
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
            transientOffset = .zero
        }
    }

    /// Keep the loupe above the held finger when there is room; near the top edge, place it below
    /// the finger instead of covering the navigation control.  The bounds remain stable so the
    /// overlay never changes the map's layout while a drag is in flight.
    private func loupePosition(_ location: CGPoint, in size: CGSize) -> CGPoint {
        let diameter: CGFloat = 124
        let half = diameter / 2
        let minX = half + 8
        let maxX = max(minX, size.width - half - 8)
        let x = min(max(location.x, minX), maxX)
        let minimumY = half + 8
        let maximumY = max(minimumY, size.height - half - 8)
        let above = location.y - half - 26
        let below = location.y + half + 26
        let y = above >= minimumY
            ? above
            : min(max(below, minimumY), maximumY)
        return CGPoint(x: x, y: min(max(y, minimumY), maximumY))
    }

    private func clamped(_ value: CGSize, in size: CGSize, scale: CGFloat) -> CGSize {
        guard scale > 1 else { return .zero }
        let maxX = size.width * (scale - 1) / 2
        let maxY = size.height * (scale - 1) / 2
        return CGSize(width: min(max(value.width, -maxX), maxX), height: min(max(value.height, -maxY), maxY))
    }

    private func distanceYards(from start: CLLocationCoordinate2D?, to end: CLLocationCoordinate2D?) -> Int? {
        guard let start, let end else { return nil }
        return GeoDistance.yards(from: start.latitude, start.longitude, to: end.latitude, end.longitude)
    }

    private func transformed(
        _ base: CGPoint,
        in size: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) -> CGPoint? {
        guard base.x.isFinite, base.y.isFinite,
              size.width > 0, size.height > 0,
              scale.isFinite, scale > 0,
              offset.width.isFinite, offset.height.isFinite else { return nil }
        return CGPoint(
            x: (base.x - size.width / 2) * scale + size.width / 2 + offset.width,
            y: (base.y - size.height / 2) * scale + size.height / 2 + offset.height
        )
    }
}

/// Circular, transform-aware loupe used by the phone View Green surface.  `content` is rendered in
/// the same full viewport coordinate system as the main map; the combined affine translation below
/// makes the point under the finger land at the loupe centre even after pinch/pan zooming.
private struct LiveGreenMagnifierLoupe<Content: View>: View {
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
        let totalScale = safeScale * safeMagnification
        // Main map: C + s(p-C) + O.  Loupe: D/2 + m(mainMap - focus).  Written in a top-leading
        // coordinate frame, this offset keeps the exact source pixel under the finger centred.
        let dx = diameter / 2
            + safeMagnification * ((1 - safeScale) * center.x + displayedOffset.width - safeFocus.x)
        let dy = diameter / 2
            + safeMagnification * ((1 - safeScale) * center.y + displayedOffset.height - safeFocus.y)

        ZStack(alignment: .topLeading) {
            content
                .frame(width: mapSize.width, height: mapSize.height)
                .scaleEffect(totalScale, anchor: .topLeading)
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
        .accessibilityLabel("拖动旗位时的放大视图")
        .accessibilityIdentifier("live-green-flag-magnifier")
    }
}

private enum WatchGreenPolygon {
    static func contains(_ point: [Double], outline: [[Double]]) -> Bool {
        guard point.count >= 2 else { return false }
        let polygon = outline.compactMap { row -> CGPoint? in
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            return CGPoint(x: row[0], y: row[1])
        }
        guard polygon.count >= 3 else { return false }
        let p = CGPoint(x: point[0], y: point[1])
        // Treat a point on the factual outline as inside. Touch coordinates are rounded to image
        // pixels, and rejecting the boundary makes a drag near the green edge snap back on release.
        let edgeTolerance = 0.75
        for index in polygon.indices {
            let a = polygon[index]
            let b = polygon[(index + 1) % polygon.count]
            let dx = b.x - a.x
            let dy = b.y - a.y
            let lengthSquared = dx * dx + dy * dy
            guard lengthSquared > 0 else { continue }
            let cross = (p.x - a.x) * dy - (p.y - a.y) * dx
            if abs(cross) <= edgeTolerance * sqrt(lengthSquared) {
                let projection = (p.x - a.x) * dx + (p.y - a.y) * dy
                if projection >= -edgeTolerance,
                   projection <= lengthSquared + edgeTolerance {
                    return true
                }
            }
        }
        var inside = false
        var previous = polygon.count - 1
        for current in polygon.indices {
            let a = polygon[current]
            let b = polygon[previous]
            if (a.y > p.y) != (b.y > p.y) {
                let denominator = b.y - a.y
                if abs(denominator) > 0.000001 {
                    let x = (b.x - a.x) * (p.y - a.y) / denominator + a.x
                    if p.x < x { inside.toggle() }
                }
            }
            previous = current
        }
        return inside
    }
}
#endif
