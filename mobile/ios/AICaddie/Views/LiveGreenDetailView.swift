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
    /// Viewport offset from the finger to the flag foot captured when a drag grabs the flag. The
    /// flag keeps that relative position for the whole drag, so it stays visible beside the finger
    /// (there is deliberately no loupe here: it would cover the edge distances above the flag).
    @State private var flagGrabOffset: CGSize = .zero
    /// Keeps previews and older callers useful when they pass a constant binding. Production callers
    /// pass the round-owned binding above, so reopening View Green retains the selected pixel.
    @State private var fallbackTargetPixel: CGPoint?
    @State private var didDrag = false
    /// Leaving the putting surface pauses flag updates instead of cancelling the held gesture.
    @State private var flagDragOutsideGreen = false
    @State private var lastValidFlagPixel: [Double]?
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
        let rawDisplayedOffset = CGSize(
            width: offset.width + transientOffset.width,
            height: offset.height + transientOffset.height
        )
        let displayedOffset = clamped(rawDisplayedOffset, in: size, scale: displayedScale)

        ZStack(alignment: .topTrailing) {
            greenMapContent(size: size, baseRect: baseRect)
            .scaleEffect(displayedScale)
            .offset(displayedOffset)

            // Edge guides and the flag are drawn in viewport space on top of the zoomed map, so lines
            // stay hairline and labels stay legible at every zoom level.
            Canvas { context, _ in
                drawEdgeGuides(&context, size: size, baseRect: baseRect, scale: displayedScale, offset: displayedOffset)
            }
            .frame(width: size.width, height: size.height)
            .allowsHitTesting(false)
            .accessibilityHidden(true)

            // The transparent interaction surface is below controls and the distance panel. A map
            // drag therefore cannot win the hit test for a button layered above it.
            greenInteractionLayer(size: size, baseRect: baseRect)

            if scale > 1.01 {
                VStack(spacing: 9) {
                    mapControl(system: "minus.magnifyingglass", label: "缩小果岭", identifier: "live-green-zoom-out") {
                        changeScale(by: -0.5, in: size)
                    }
                    mapControl(system: "scope", label: "还原果岭", identifier: "live-green-fit") {
                        resetViewport()
                    }
                }
                .padding(.top, 92)
                .padding(.trailing, 12)
            }

            VStack {
                Spacer()
                distancePanel
                    .padding(.horizontal, 14)
                    .padding(.bottom, 18)
            }
        }
        .frame(width: size.width, height: size.height)
        .clipped()
        // A held pan is a direct-manipulation gesture. Do not let an inherited animation defer the
        // bitmap until finger-up; the map must track each DragGesture update like the distance view.
        .animation(nil, value: transientOffset)
    }

    /// The zoomable base bitmap. The green is not outlined (B1: no ring on the green); only the flag
    /// and its four edge guides are drawn, in viewport space, by `drawEdgeGuides`.
    @ViewBuilder
    private func greenMapContent(size: CGSize, baseRect: CGRect) -> some View {
        ZStack {
            if activeDetailCrop != nil, baseRect.width > 0 {
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
                    showsFactualRoute: true,
                    showsRecommendedRoute: false,
                    // Green view is a putting instrument; obstacle overlays belong to the explicit
                    // hazard picker and should not appear as incidental red spans here.
                    showsHazards: false
                )
                .frame(width: size.width, height: size.height)
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
        let toFlag = hasPixelOverride
            ? (pixelDistances?.referenceToTargetYards
                ?? distanceYards(from: referenceCoordinate, to: selectedFlag))
            : (distanceYards(from: referenceCoordinate, to: selectedFlag)
                ?? pixelDistances?.referenceToTargetYards)
        let edges = edgeDistances()
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                // Without a live fix the range is measured from the Tee; never claim "current position".
                Text(referenceIsLive ? "到旗" : "发球台到旗")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.62))
                Text(toFlag.map { GeoDistance.greenRangeText($0) } ?? "—")
                    .font(.system(size: 48, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .accessibilityIdentifier("live-green-to-flag")
                Text("码")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.62))
            }
            HStack(spacing: 0) {
                edgeCell("前沿", edges?.front.yards, identifier: "live-green-edge-front")
                edgeDivider
                edgeCell("后沿", edges?.back.yards, identifier: "live-green-edge-back")
                edgeDivider
                edgeCell("左边", edges?.left.yards, identifier: "live-green-edge-left")
                edgeDivider
                edgeCell("右边", edges?.right.yards, identifier: "live-green-edge-right")
            }
            .padding(.top, 9)
            .overlay(alignment: .top) { Rectangle().fill(Color.white.opacity(0.14)).frame(height: 0.5) }
            .accessibilityElement(children: .contain)
            .accessibilityLabel("旗到果岭四边的距离（码）")
            Text(flagPositionText(edges))
                .font(.system(size: 12.5, weight: .medium))
                .monospacedDigit()
                .foregroundStyle(.white.opacity(0.62))
                .accessibilityIdentifier("live-green-flag-position")
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.78), in: RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 26).stroke(Color.white.opacity(0.18)))
        .accessibilityIdentifier("live-green-distance-panel")
    }

    private var edgeDivider: some View {
        Rectangle().fill(Color.white.opacity(0.14)).frame(width: 0.5, height: 34)
    }

    private func edgeCell(_ label: String, _ yards: Int?, identifier: String) -> some View {
        VStack(spacing: 1) {
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(.white.opacity(0.62))
            Text(yards.map(String.init) ?? "—")
                .font(.system(size: 22, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label) \(yards.map { "\($0) 码" } ?? "未知")")
        .accessibilityIdentifier(identifier)
    }

    /// "旗在果岭中心" / "旗在果岭中心后 4 码、偏右 3 码" (front/back along the play axis, left/right as
    /// seen facing the green).
    private func flagPositionText(_ edges: GreenEdgeDistances?) -> String {
        guard let edges else { return "拖动或点果岭调整本轮旗位" }
        var parts: [String] = []
        if edges.behindCentreYards != 0 {
            parts.append("中心\(edges.behindCentreYards > 0 ? "后" : "前") \(abs(edges.behindCentreYards)) 码")
        }
        if edges.rightOfCentreYards != 0 {
            parts.append("\(edges.rightOfCentreYards > 0 ? "偏右" : "偏左") \(abs(edges.rightOfCentreYards)) 码")
        }
        return parts.isEmpty ? "旗在果岭中心" : "旗在果岭" + parts.joined(separator: "、")
    }

    private func edgeDistances() -> GreenEdgeDistances? {
        guard let flag = effectiveFlagPixel,
              let outline = hole.greenOutline,
              outline.available,
              let ppm = hole.resolvedMapOverlay?.ppm else { return nil }
        return GreenEdgeDistances.resolve(
            flagPx: flag,
            outlinePx: outline.pointsPx,
            referencePx: referencePixel(),
            pixelsPerMetre: ppm
        )
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

    /// The affine crop is authoritative whenever the hole has a factual green outline. The remote
    /// high-resolution asset is an enhancement; if it is unavailable (offline, uncached, or the
    /// API is still warming up), the decoded whole-hole bitmap is cropped into the same frame so
    /// the interaction does not silently fall back to a tiny full-hole thumbnail.
    private var activeDetailCrop: GreenDetailCrop? {
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

    /// Four thin lines from the flag to the front / back / left / right edges, a short cross tick at
    /// each edge point and the yardage in a small dark capsule just beyond it, then the flag itself.
    private func drawEdgeGuides(
        _ context: inout GraphicsContext,
        size: CGSize,
        baseRect: CGRect,
        scale: CGFloat,
        offset: CGSize
    ) {
        guard let flagPx = effectiveFlagPixel,
              let flagBase = fullPixelPoint(flagPx, baseRect: baseRect),
              let flag = transformed(flagBase, in: size, scale: scale, offset: offset) else { return }
        if let edges = edgeDistances() {
            let front = CGPoint(x: edges.frontDirection[0], y: edges.frontDirection[1])
            let right = CGPoint(x: edges.rightDirection[0], y: edges.rightDirection[1])
            let guides: [(GreenEdgeDistances.Edge, CGPoint)] = [
                (edges.front, front),
                (edges.back, CGPoint(x: -front.x, y: -front.y)),
                (edges.left, CGPoint(x: -right.x, y: -right.y)),
                (edges.right, right),
            ]
            for (edge, direction) in guides {
                guard let base = fullPixelPoint(edge.pointPx, baseRect: baseRect),
                      let end = transformed(base, in: size, scale: scale, offset: offset) else { continue }
                var line = Path()
                line.move(to: flag)
                line.addLine(to: end)
                context.stroke(line, with: .color(.white.opacity(0.9)), lineWidth: 1.3)
                let normal = CGPoint(x: -direction.y * 5, y: direction.x * 5)
                var tick = Path()
                tick.move(to: CGPoint(x: end.x - normal.x, y: end.y - normal.y))
                tick.addLine(to: CGPoint(x: end.x + normal.x, y: end.y + normal.y))
                context.stroke(tick, with: .color(.white), style: StrokeStyle(lineWidth: 2, lineCap: .round))

                let text = String(edge.yards)
                let width = 10 + CGFloat(text.count) * 8
                let height: CGFloat = 20
                let gap = 10 + abs(direction.x) * width / 2 + abs(direction.y) * height / 2
                let centre = CGPoint(
                    x: min(max(end.x + direction.x * gap, width / 2 + 6), size.width - width / 2 - 6),
                    y: min(max(end.y + direction.y * gap, 104 + height / 2), size.height - 250)
                )
                let capsule = Path(
                    roundedRect: CGRect(x: centre.x - width / 2, y: centre.y - height / 2, width: width, height: height),
                    cornerRadius: height / 2
                )
                context.fill(capsule, with: .color(.black.opacity(0.64)))
                context.draw(
                    Text(text)
                        .font(.system(size: 13, weight: .bold))
                        .monospacedDigit()
                        .foregroundColor(.white),
                    at: centre
                )
            }
        }
        drawFlag(&context, at: flag)
    }

    private func drawFlag(_ context: inout GraphicsContext, at point: CGPoint) {
        LiveMapFlagRenderer.draw(&context, at: point)
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

    /// Keep the persisted pole-foot on the factual putting surface. For an outside touch this is a
    /// nearest-segment projection, not a rectangular clamp, so a curved edge remains draggable in
    /// the unconstrained direction.
    private func constrainedFlagPixel(_ row: [Double]) -> [Double]? {
        guard row.count >= 2,
              row[0].isFinite,
              row[1].isFinite,
              validPixel(CGPoint(x: row[0], y: row[1])) else { return nil }
        guard let outline = hole.greenOutline,
              outline.available,
              outline.pointsPx.count >= 3 else {
            return [row[0], row[1]]
        }
        guard let projected = LivePolygonGeometry.nearestPoint(
            CGPoint(x: row[0], y: row[1]),
            on: outline.pointsPx.compactMap { point in
                guard point.count >= 2,
                      point[0].isFinite,
                      point[1].isFinite else { return nil }
                return CGPoint(x: point[0], y: point[1])
            }
        ) else { return nil }
        return [Double(projected.x), Double(projected.y)]
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
    /// pixel frame. This is the single source used by tap, drag and hit testing.
    private func pixel(
        at point: CGPoint,
        size: CGSize,
        baseRect: CGRect,
        scale: CGFloat,
        offset: CGSize,
        requireInsideGreen: Bool = true
    ) -> [Double]? {
        let untransformed = CGPoint(
            x: (point.x - size.width / 2 - offset.width) / max(scale, 0.001) + size.width / 2,
            y: (point.y - size.height / 2 - offset.height) / max(scale, 0.001) + size.height / 2
        )
        let fullPx: [Double]?
        let allowOutsideMap = !requireInsideGreen
        if let crop = activeDetailCrop {
            guard baseRect.width > 0, baseRect.height > 0 else { return nil }
            if !allowOutsideMap {
                guard baseRect.contains(untransformed) else { return nil }
            }
            guard crop.width > 0, crop.height > 0 else { return nil }
            let raw = [
                crop.x + Double((untransformed.x - baseRect.minX) / baseRect.width) * crop.width,
                crop.y + Double((untransformed.y - baseRect.minY) / baseRect.height) * crop.height,
            ]
            fullPx = allowOutsideMap ? clampedImagePixel(raw) : raw
        } else if let overlay = hole.resolvedMapOverlay {
            fullPx = LivePlayMapOverlayLayout.unproject(
                screenPoint: CGPoint(x: untransformed.x - baseRect.minX, y: untransformed.y - baseRect.minY),
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                from: baseRect.size,
                clampToMap: allowOutsideMap
            )
        } else if let dimensions = imageDimensions {
            guard baseRect.width > 0, baseRect.height > 0 else { return nil }
            if !allowOutsideMap {
                guard baseRect.contains(untransformed) else { return nil }
            }
            let raw = [
                Double((untransformed.x - baseRect.minX) / baseRect.width) * dimensions.width,
                Double((untransformed.y - baseRect.minY) / baseRect.height) * dimensions.height,
            ]
            fullPx = allowOutsideMap ? clampedImagePixel(raw) : raw
        } else {
            fullPx = nil
        }
        guard let fullPx,
              fullPx.count >= 2,
              validPixel(CGPoint(x: fullPx[0], y: fullPx[1])) else { return nil }
        if requireInsideGreen, !validFlagPixel(fullPx) {
            return nil
        }
        return fullPx
    }

    private func clampedImagePixel(_ row: [Double]) -> [Double] {
        guard row.count >= 2,
              let dimensions = imageDimensions else { return row }
        return [
            min(max(row[0], 0), dimensions.width),
            min(max(row[1], 0), dimensions.height),
        ]
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
        // Keep the first-shot detail marker on the exact overlay Tee anchor. The normal map, Touch
        // Target and View Green surfaces must share one origin even when package GPS metadata was
        // rounded independently from the route projection.
        if !referenceIsLive, let tee = routePixel(hole.resolvedMapOverlay?.route.first) {
            return tee
        }
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
                if !draggingFlag && !flagDragOutsideGreen {
                    if let base = effectiveFlagPixel.flatMap({ fullPixelPoint($0, baseRect: baseRect) }),
                       let screen = transformed(base, in: size, scale: scale, offset: offset),
                       hypot(screen.x - value.startLocation.x, screen.y - value.startLocation.y) <= 44 {
                        draggingFlag = true
                        flagDragOutsideGreen = false
                        lastValidFlagPixel = effectiveFlagPixel.flatMap(constrainedFlagPixel) ?? effectiveFlagPixel
                        flagGrabOffset = CGSize(
                            width: screen.x - value.startLocation.x,
                            height: screen.y - value.startLocation.y
                        )
                    } else if scale <= 1.01 {
                        // At fit scale only the putting surface is an actionable flag target. A
                        // drag that begins on the fairway/header is deliberately inert instead of
                        // turning every part of the map into a flag-placement gesture.
                        if let startPixel = pixel(
                            at: value.startLocation,
                            size: size,
                            baseRect: baseRect,
                            scale: scale,
                            offset: offset,
                            requireInsideGreen: true
                        ) {
                            draggingFlag = true
                            flagDragOutsideGreen = false
                            lastValidFlagPixel = startPixel
                            flagGrabOffset = .zero
                        } else {
                            draggingFlag = false
                            flagDragOutsideGreen = true
                        }
                    } else if scale > 1.01 {
                        draggingFlag = false
                        flagDragOutsideGreen = false
                    } else {
                        draggingFlag = false
                        flagDragOutsideGreen = true
                    }
                }
                didDrag = true
                if draggingFlag {
                    // The flag keeps its grab offset from the finger; only the committed pole-foot is
                    // constrained to the nearest legal boundary point when the finger leaves the green.
                    let heldPoint = CGPoint(
                        x: value.location.x + flagGrabOffset.width,
                        y: value.location.y + flagGrabOffset.height
                    )
                    if let pixel = pixel(
                        at: heldPoint,
                        size: size,
                        baseRect: baseRect,
                        scale: scale,
                        offset: offset,
                        requireInsideGreen: false
                    ) {
                        flagDragOutsideGreen = !validFlagPixel(pixel)
                        if let constrained = constrainedFlagPixel(pixel) {
                            lastValidFlagPixel = constrained
                            applyFlag(pixel: constrained, committed: false)
                        }
                    } else {
                        flagDragOutsideGreen = true
                    }
                } else if !flagDragOutsideGreen {
                    transientOffset = value.translation
                }
            }
            .onEnded { value in
                let wasDraggingFlag = draggingFlag
                let finalFlagPixel = lastValidFlagPixel
                defer {
                    draggingFlag = false
                    flagDragOutsideGreen = false
                    lastValidFlagPixel = nil
                    flagGrabOffset = .zero
                    transientOffset = .zero
                    DispatchQueue.main.async { didDrag = false }
                }
                if wasDraggingFlag, let finalFlagPixel {
                    // Releasing outside the green commits the last valid in-green point. Releasing
                    // inside has already updated this same point on the final onChanged frame.
                    applyFlag(pixel: finalFlagPixel, committed: true)
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

    private func clamped(_ value: CGSize, in size: CGSize, scale: CGFloat) -> CGSize {
        let mapFrame: CGRect?
        if activeDetailCrop == nil,
           let overlay = hole.resolvedMapOverlay {
            mapFrame = LivePlayMapOverlayLayout.mapFrame(
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                in: size
            )
        } else {
            mapFrame = detailRect(in: size)
        }
        guard let mapFrame else { return scale > 1 ? value : .zero }
        return LivePlayMapOverlayLayout.clampedOffset(
            value,
            mapFrame: mapFrame,
            viewportSize: size,
            scale: scale
        )
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

enum WatchGreenPolygon {
    static func contains(_ point: [Double], outline: [[Double]]) -> Bool {
        guard point.count >= 2 else { return false }
        let polygon = outline.compactMap { row -> CGPoint? in
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            return CGPoint(x: row[0], y: row[1])
        }
        return LivePolygonGeometry.contains(CGPoint(x: point[0], y: point[1]), polygon: polygon)
    }
}
#endif
