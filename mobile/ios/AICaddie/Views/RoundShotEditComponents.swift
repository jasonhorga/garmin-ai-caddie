import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - shared options

/// Where this shot was played from. `endLie` is a separate observed landing fact, so the editor
/// never offers water/green as a start lie for the non-putt shots this product records.
public let roundEditLieOptions: [(String, String)] = [
    ("teebox", "发球台"), ("fairway", "球道"), ("rough", "长草"),
    ("bunker", "沙坑"), ("fringe", "果岭边"), ("trees", "树下"), ("unknown", "未知"),
]

/// Fallback club list when the player's real bag hasn't loaded (the picker prefers the real bag,
/// passed in from the screen). These are choices to pick from — not fabricated shot data.
public let roundEditCommonClubs: [String] = [
    "一号木", "三号木", "五号木", "三号铁", "四号铁", "五号铁", "六号铁",
    "七号铁", "八号铁", "九号铁", "PW", "GW", "SW", "LW", "推杆",
]

/// Picker state always uses the same display spelling as its rows. Garmin history may contain raw
/// tokens such as `1W` / `7I`, while the real bag and fallback choices are Chinese display names.
/// Keeping a raw token as the selection when no row has that tag makes SwiftUI render an empty value.
public func roundEditClubSelection(_ raw: String?) -> String {
    guard let raw else { return "" }
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty, trimmed.lowercased() != "unknown" else { return "" }
    return zhClubName(trimmed)
}

/// Normalise and deduplicate the choices, and retain the recorded club even when it is no longer in
/// the player's current bag. That makes every historical shot visible and still lets the player pick
/// a current club to replace it.
public func roundEditClubOptions(current: String?, clubs: [String]) -> [String] {
    var seen = Set<String>()
    return ([roundEditClubSelection(current)] + clubs.map { roundEditClubSelection($0) })
        .filter { !$0.isEmpty && seen.insert($0).inserted }
}

// MARK: - edit overlay (tap-to-add + long-press move + numbered handles + magnifier)

#if canImport(UIKit)
/// The edit affordance layer, overlaid on the read-only shot map when editing. A short tap on empty
/// ground immediately adds one numbered point to the local whole-hole draft; a short tap on a number
/// selects it for details. A deliberate long press on an existing number moves it. Finger-up never
/// writes the server — the parent Save action owns persistence.
/// Pixel↔view conversion uses the fitted map size from GeometryReader (same projection as the canvas).
public struct RoundShotEditLayer: View {
    @ObservedObject var editModel: RoundEditModel
    let overlay: CoursePrepOverlay
    let clubs: [String]
    /// The map's own base bitmap (flat fallback) + topo URL — reused by the magnifier so it shows the
    /// real course under the finger, not just the shot lines.
    let baseImage: UIImage?
    let topoURL: URL?

    @State private var editingShot: RoundShot?
    /// Optional precision surface for a selected landing. The draft is already local at this point;
    /// the precision surface only refines its pixel position and never performs a network write.
    @State private var precisionRequest: RoundShotPrecisionRequest?
    /// Current finger location (view coords) during a drag — drives the magnifier + the committed px.
    @State private var dragLocation: CGPoint?
    /// The existing shot whose numbered handle this long-press gesture owns.
    @State private var grabbedShotId: String?
    @State private var gestureActive = false
    /// A completed long-press can deliver a `SpatialTapGesture` in the same run loop as its end.
    /// Keep selection/addition suppressed until that delivery has drained.
    @State private var suppressSelectionTap = false

    private let hitRadius: CGFloat = 24
    private let loupeDiameter: CGFloat = 116

    public init(editModel: RoundEditModel, overlay: CoursePrepOverlay, clubs: [String],
                baseImage: UIImage?, topoURL: URL?) {
        self.editModel = editModel
        self.overlay = overlay
        self.clubs = clubs
        self.baseImage = baseImage
        self.topoURL = topoURL
    }

    public var body: some View {
        GeometryReader { geo in
            if let frame = mapFrame(in: geo.size) {
                ZStack {
                    Canvas { ctx, _ in
                        for (index, shot) in editModel.map.shots.enumerated() {
                            guard let p = screenPoint(for: shot.end, frame: frame) else { continue }
                            let dragging = editModel.draggingShotId == shot.id
                            let selected = editModel.selectedShotId == shot.id
                            let r: CGFloat = dragging ? 16 : (selected ? 15 : 13)
                            let ring = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
                            ctx.fill(ring, with: .color(.black.opacity(selected || dragging ? 0.88 : 0.72)))
                            ctx.stroke(
                                ring,
                                with: .color(selected ? LiveHoleStyle.green : .white),
                                lineWidth: dragging ? 3.5 : (selected ? 3 : 2)
                            )
                            ctx.stroke(ring, with: .color(.black.opacity(0.45)), lineWidth: 0.5)
                            ctx.draw(
                                Text("\(index + 1)")
                                    .font(.caption2.monospacedDigit().weight(.heavy))
                                    .foregroundColor(.white),
                                at: p
                            )
                        }
                    }
                    .contentShape(Rectangle())
                    .gesture(longPressDragGesture(frame: frame))
                    .simultaneousGesture(selectionTapGesture(frame: frame))

                    // Magnifier loupe: floats ABOVE the finger while dragging (设计 §5), showing the
                    // area the finger covers, magnified + crosshair, so the landing lands precisely.
                    if let loc = dragLocation, editModel.draggingShotId != nil, gestureActive {
                        MagnifierLoupe(
                            overlay: overlay,
                            shots: editModel.map.shots,
                            baseImage: baseImage,
                            topoURL: topoURL,
                            mapSize: frame.size,
                            focus: CGPoint(x: loc.x - frame.minX, y: loc.y - frame.minY),
                            diameter: loupeDiameter
                        )
                        .position(loupePosition(loc, in: geo.size))
                        .allowsHitTesting(false)
                    }

                    // A system sheet covers the lower half of the map. Keep the exact tapped/selected
                    // landing visible in the uncovered area instead of making the player remember which
                    // dot is being edited. This reuses the real topo + current route rather than drawing
                    // a detached synthetic thumbnail.
                    if let focus = sheetFocus(frame: frame) {
                        VStack(spacing: 3) {
                            MagnifierLoupe(
                                overlay: overlay,
                                shots: editModel.map.shots,
                                baseImage: baseImage,
                                topoURL: topoURL,
                                mapSize: frame.size,
                                focus: CGPoint(x: focus.x - frame.minX, y: focus.y - frame.minY),
                                diameter: 98,
                                magnification: 2.35
                            )
                            Text(sheetFocusLabel)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(.black.opacity(0.72), in: Capsule())
                        }
                        .frame(width: 122)
                        .position(x: max(66, geo.size.width - 68), y: 72)
                        .allowsHitTesting(false)
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel(sheetFocusLabel)
                    }

                    if let selectedShot {
                        VStack {
                            Spacer()
                            HStack {
                                Spacer()
                                Button {
                                    openPrecisionEditor(for: selectedShot)
                                } label: {
                                    Label("放大", systemImage: "plus.magnifyingglass")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.white)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 7)
                                        .background(.black.opacity(0.78), in: Capsule())
                                }
                                .buttonStyle(.plain)
                                .accessibilityLabel(
                                    selectedShot.id.hasPrefix("draft-") ? "放大定位这一杆" : "放大调整这一杆位置"
                                )
                                .accessibilityIdentifier("round-shot-precision-open")
                                Button {
                                    editingShot = selectedShot
                                } label: {
                                    Label("详情", systemImage: "slider.horizontal.3")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.white)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 7)
                                        .background(.black.opacity(0.78), in: Capsule())
                                }
                                .buttonStyle(.plain)
                                .accessibilityLabel(selectedShotLabel)
                                .accessibilityHint("修改球杆、球位或删除这一杆")
                            }
                        }
                        .padding(10)
                    }
                }
            } else {
                Color.clear
            }
        }
        .sheet(item: $editingShot) { shot in
            ShotEditSheet(
                shot: shot, clubs: effectiveClubs,
                onClub: { editModel.editClub(shotId: shot.id, $0) },
                onLie: { editModel.editLie(shotId: shot.id, $0) },
                onDelete: {
                    editModel.delete(shotId: shot.id)
                    editModel.selectedShotId = nil
                }
            )
        }
        .fullScreenCover(item: $precisionRequest) { request in
            RoundShotPrecisionEditor(
                overlay: overlay,
                shots: editModel.map.shots,
                shotId: request.shotId,
                baseImage: baseImage,
                topoURL: topoURL,
                initialPixel: request.initialPixel,
                title: request.title,
                onCommit: { px in
                    editModel.move(shotId: request.shotId, px: px)
                    editModel.selectedShotId = request.shotId
                },
                onCancel: {
                    if request.discardOnCancel {
                        editModel.delete(shotId: request.shotId)
                        editModel.selectedShotId = nil
                    }
                }
            )
        }
        .onChange(of: editModel.precisionShotRequest, initial: true) { _, shotId in
            guard precisionRequest == nil,
                  let shotId,
                  let shot = editModel.map.shots.first(where: { $0.id == shotId }) else {
                return
            }
            // Consume before presenting so a second tap after dismissal can request the same shot.
            editModel.clearPrecisionRequest()
            openPrecisionEditor(for: shot)
        }
    }

    private func longPressDragGesture(frame: CGRect) -> some Gesture {
        LongPressGesture(minimumDuration: 0.38, maximumDistance: 18)
            .sequenced(before: DragGesture(minimumDistance: 0))
            .onChanged { value in
                guard case .second(true, let drag?) = value else { return }
                if !gestureActive {
                    gestureActive = true
                    suppressSelectionTap = true
                    guard let hit = nearestHit(to: drag.startLocation, frame: frame) else {
                        grabbedShotId = nil
                        return
                    }
                    let id = hit.id
                    grabbedShotId = id
                    editModel.selectedShotId = id
                    editModel.draggingShotId = id
                }
                dragLocation = drag.location
                if let id = grabbedShotId {
                    guard let px = pixel(at: drag.location, frame: frame, clampToMap: true) else { return }
                    editModel.previewMove(shotId: id, px: px)
                }
            }
            .onEnded { value in
                if case .second(true, let drag?) = value, let id = grabbedShotId {
                    if let px = pixel(at: drag.location, frame: frame, clampToMap: true) {
                        editModel.move(shotId: id, px: px)
                    }
                }
                resetGesture()
                DispatchQueue.main.async { suppressSelectionTap = false }
            }
    }

    private func selectionTapGesture(frame: CGRect) -> some Gesture {
        SpatialTapGesture()
            .onEnded { value in
                guard !gestureActive, !suppressSelectionTap else { return }
                if let hit = nearestHit(to: value.location, frame: frame) {
                    editModel.selectedShotId = hit.id
                } else {
                    // Letterboxed margins are outside the factual map and must never become a
                    // clamped course coordinate when the player taps to add a landing.
                    guard let px = pixel(at: value.location, frame: frame, clampToMap: false) else { return }
                    let id = editModel.addShot(px: px, afterShotId: editModel.selectedShotId)
                    guard !id.isEmpty,
                          let added = editModel.map.shots.first(where: { $0.id == id }) else { return }
                    editModel.selectedShotId = id
                    // S70-style focused placement: a new landing goes straight into the precision
                    // surface, and cancelling that surface removes only this unconfirmed draft.
                    openPrecisionEditor(for: added, discardOnCancel: true)
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                }
            }
    }

    private func resetGesture() {
        editModel.draggingShotId = nil
        grabbedShotId = nil
        gestureActive = false
        dragLocation = nil
    }

    /// Place the loupe centered horizontally on the finger but ABOVE it, clamped inside the map.
    private func loupePosition(_ loc: CGPoint, in size: CGSize) -> CGPoint {
        let half = loupeDiameter / 2
        let y = max(half + 6, loc.y - half - 26)
        let x = min(max(half + 6, loc.x), size.width - half - 6)
        return CGPoint(x: x, y: y)
    }

    private var effectiveClubs: [String] { clubs.isEmpty ? roundEditCommonClubs : clubs }

    private func openPrecisionEditor(for shot: RoundShot, discardOnCancel: Bool = false) {
        // History shot pixels are integer overlay coordinates; unlike a GPS-derived Double they
        // cannot carry NaN/Infinity. The count check is the only validity gate needed here.
        guard let end = shot.end, end.count >= 2 else { return }
        let number = (editModel.map.shots.firstIndex(where: { $0.id == shot.id }) ?? 0) + 1
        precisionRequest = RoundShotPrecisionRequest(
            shotId: shot.id,
            initialPixel: [Double(end[0]), Double(end[1])],
            title: shot.id.hasPrefix("draft-") ? "放大定位第 \(number) 杆" : "放大调整第 \(number) 杆",
            discardOnCancel: discardOnCancel
        )
    }

    private var selectedShot: RoundShot? {
        guard let selectedShotId = editModel.selectedShotId else { return nil }
        return editModel.map.shots.first { $0.id == selectedShotId }
    }

    private var selectedShotLabel: String {
        guard let selectedShot,
              let index = editModel.map.shots.firstIndex(where: { $0.id == selectedShot.id }) else {
            return "编辑这一杆"
        }
        return "第 \(index + 1) 杆详情"
    }

    private var sheetFocusLabel: String {
        guard let editingShot,
              let index = editModel.map.shots.firstIndex(where: { $0.id == editingShot.id }) else {
            return "当前落点"
        }
        return "正在改第 \(index + 1) 杆"
    }

    private func sheetFocus(frame: CGRect) -> CGPoint? {
        let px: [Double]?
        if let end = editingShot?.end, end.count >= 2 {
            px = [Double(end[0]), Double(end[1])]
        } else {
            px = nil
        }
        guard let px, px.count >= 2 else { return nil }
        return screenPoint(for: px, frame: frame)
    }

    private func hitTest(_ s: RoundShot, _ loc: CGPoint, frame: CGRect) -> Bool {
        guard let p = screenPoint(for: s.end, frame: frame) else { return false }
        return hypot(p.x - loc.x, p.y - loc.y) <= hitRadius
    }

    private func nearestHit(to location: CGPoint, frame: CGRect) -> RoundShot? {
        guard frame.contains(location) else { return nil }
        return editModel.map.shots
            .filter { hitTest($0, location, frame: frame) }
            .min { lhs, rhs in
                viewDistance(lhs, to: location, frame: frame)
                    < viewDistance(rhs, to: location, frame: frame)
            }
    }

    private func viewDistance(
        _ shot: RoundShot,
        to location: CGPoint,
        frame: CGRect
    ) -> CGFloat {
        guard let end = screenPoint(for: shot.end, frame: frame) else { return .greatestFiniteMagnitude }
        return hypot(end.x - location.x, end.y - location.y)
    }

    private func mapFrame(in size: CGSize) -> CGRect? {
        LivePlayMapOverlayLayout.mapFrame(
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            in: size
        )
    }

    private func screenPoint(for pixel: [Int]?, frame: CGRect) -> CGPoint? {
        guard let pixel, pixel.count >= 2 else { return nil }
        return screenPoint(for: [Double(pixel[0]), Double(pixel[1])], frame: frame)
    }

    private func screenPoint(for pixel: [Double]?, frame: CGRect) -> CGPoint? {
        guard let pixel, pixel.count >= 2,
              pixel[0].isFinite, pixel[1].isFinite,
              overlay.w > 0, overlay.h > 0 else { return nil }
        let scale = frame.width / CGFloat(overlay.w)
        guard scale.isFinite, scale > 0 else { return nil }
        return CGPoint(
            x: frame.minX + CGFloat(pixel[0]) * scale,
            y: frame.minY + CGFloat(pixel[1]) * scale
        )
    }

    private func pixel(
        at location: CGPoint,
        frame: CGRect,
        clampToMap: Bool
    ) -> [Double]? {
        guard location.x.isFinite, location.y.isFinite else { return nil }
        return LivePlayMapOverlayLayout.unproject(
            screenPoint: CGPoint(x: location.x - frame.minX, y: location.y - frame.minY),
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            from: frame.size,
            clampToMap: clampToMap
        )
    }

}

// MARK: - magnifier loupe (设计 §5)

/// A circular magnifier that floats above the finger during a landing drag. Renders the SAME base map
/// + shot overlay (via ``drawRoundShotPath``), magnified and centered on the finger's map point, with
/// a crosshair — so the point being placed stays visible even though the finger covers it. Fixed-size
/// + `Circle` mask = ImageRenderer / window-snapshot friendly (no ScrollView).
public struct MagnifierLoupe: View {
    let overlay: CoursePrepOverlay
    let shots: [RoundShot]
    let baseImage: UIImage?
    let topoURL: URL?
    /// Fitted map size in view coordinates (the edit layer's GeometryReader size).
    let mapSize: CGSize
    /// Finger location in that same view space (the point to magnify + center under the crosshair).
    let focus: CGPoint
    var diameter: CGFloat = 116
    var magnification: CGFloat = 2.2

    public init(overlay: CoursePrepOverlay, shots: [RoundShot], baseImage: UIImage?, topoURL: URL?,
                mapSize: CGSize, focus: CGPoint, diameter: CGFloat = 116, magnification: CGFloat = 2.2) {
        self.overlay = overlay
        self.shots = shots
        self.baseImage = baseImage
        self.topoURL = topoURL
        self.mapSize = mapSize
        self.focus = focus
        self.diameter = diameter
        self.magnification = magnification
    }

    public var body: some View {
        // Scale about the top-left, then translate so `focus` lands at the loupe center.
        let dx = diameter / 2 - focus.x * magnification
        let dy = diameter / 2 - focus.y * magnification
        ZStack(alignment: .topLeading) {
            ZStack {
                TopoHoleBaseImage(topoURL: topoURL, fallback: baseImage)
                Canvas { ctx, size in
                    drawRoundShotPath(&ctx, size: size, overlay: overlay, shots: shots)
                }
            }
            .frame(width: mapSize.width, height: mapSize.height)
            .scaleEffect(magnification, anchor: .topLeading)
            .offset(x: dx, y: dy)
        }
        .frame(width: diameter, height: diameter, alignment: .topLeading)
        .clipShape(Circle())
        .overlay {
            ZStack {
                Rectangle().fill(.white.opacity(0.9)).frame(width: 1.2, height: 15)
                Rectangle().fill(.white.opacity(0.9)).frame(width: 15, height: 1.2)
            }
            .shadow(color: .black.opacity(0.55), radius: 0.5)
        }
        .overlay(Circle().strokeBorder(.white, lineWidth: 3))
        .overlay(Circle().strokeBorder(.black.opacity(0.2), lineWidth: 1))
        .compositingGroup()
        .shadow(color: .black.opacity(0.3), radius: 6, y: 3)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("拖动这一杆落点时的放大视图")
        .accessibilityIdentifier("round-shot-drag-magnifier")
    }
}

/// The full-screen precision surface used after a landing is selected. It mirrors the S70
/// workflow: a stable course frame, explicit zoom controls, pinch/pan, and a crosshair that can be
/// dragged independently of the map viewport. All edits stay in the parent draft until Confirm.
public struct RoundShotPrecisionRequest: Identifiable {
    public let id: String
    public let shotId: String
    public let initialPixel: [Double]
    public let title: String
    /// New tap-to-add drafts are provisional until the player confirms the enlarged editor.
    public let discardOnCancel: Bool

    public init(
        shotId: String,
        initialPixel: [Double],
        title: String,
        discardOnCancel: Bool = false
    ) {
        self.id = shotId
        self.shotId = shotId
        self.initialPixel = initialPixel
        self.title = title
        self.discardOnCancel = discardOnCancel
    }
}

/// A reversible, map-only editor for one landing. The map's pixel frame is calculated once from the
/// overlay dimensions and the available viewport; both drawing and hit testing use that same frame.
public struct RoundShotPrecisionEditor: View {
    @Environment(\.dismiss) private var dismiss

    public let overlay: CoursePrepOverlay
    public let shots: [RoundShot]
    public let shotId: String
    public let baseImage: UIImage?
    public let topoURL: URL?
    public let initialPixel: [Double]
    public let title: String
    public let onCommit: ([Double]) -> Void
    public let onCancel: () -> Void

    @State private var pixel: CGPoint
    @State private var scale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var transientOffset: CGSize = .zero
    @State private var interactionMode: InteractionMode?
    @State private var didDrag = false
    /// View-space location of the finger while the precision crosshair is being moved. The
    /// precision surface has its own zoom/pan transform, so this stays separate from `pixel`.
    @State private var markerDragLocation: CGPoint?
    @GestureState private var pinchScale: CGFloat = 1

    private static let headerInset: CGFloat = 72
    private static let bottomInset: CGFloat = 112
    private static let markerLoupeDiameter: CGFloat = 124

    private enum InteractionMode {
        case point
        case pan
    }

    public init(
        overlay: CoursePrepOverlay,
        shots: [RoundShot],
        shotId: String,
        baseImage: UIImage?,
        topoURL: URL?,
        initialPixel: [Double],
        title: String,
        onCommit: @escaping ([Double]) -> Void,
        onCancel: @escaping () -> Void
    ) {
        self.overlay = overlay
        self.shots = shots
        self.shotId = shotId
        self.baseImage = baseImage
        self.topoURL = topoURL
        self.initialPixel = initialPixel
        self.title = title
        self.onCommit = onCommit
        self.onCancel = onCancel
        let x = initialPixel.indices.contains(0) && initialPixel[0].isFinite ? initialPixel[0] : 0
        let y = initialPixel.indices.contains(1) && initialPixel[1].isFinite ? initialPixel[1] : 0
        _pixel = State(initialValue: CGPoint(x: x, y: y))
    }

    public var body: some View {
        ZStack {
            LivePlayStyle.base.ignoresSafeArea()
            GeometryReader { proxy in
                precisionViewport(in: proxy.size)
            }
            header
        }
        .preferredColorScheme(.dark)
        // A new landing is provisional until the explicit Confirm/Cancel action. Prevent a
        // swipe-to-dismiss from leaving an unconfirmed point behind without running onCancel.
        .interactiveDismissDisabled(true)
    }

    private var header: some View {
        HStack(spacing: 10) {
            Button {
                markerDragLocation = nil
                onCancel()
                dismiss()
            } label: {
                Image(systemName: "chevron.backward")
                    .font(.system(size: 15, weight: .bold))
                    .frame(width: 40, height: 40)
                    .background(Color.black.opacity(0.68), in: Circle())
                    .overlay(Circle().stroke(Color.white.opacity(0.2)))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("取消精确定位")
            .accessibilityIdentifier("round-shot-precision-cancel")
            Text(title)
                .font(.headline.weight(.heavy))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Spacer(minLength: 0)
            Text("拖动准星")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.72))
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
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
    private func precisionViewport(in size: CGSize) -> some View {
        if let frame = mapFrame(in: size), frame.width > 0, frame.height > 0 {
            precisionViewportContent(in: size, frame: frame)
        } else {
            Color.black.opacity(0.2)
                .frame(width: size.width, height: size.height)
        }
    }

    @ViewBuilder
    private func precisionViewportContent(in size: CGSize, frame: CGRect) -> some View {
        let displayedScale = min(max(scale * pinchScale, 1), 4)
        let displayedOffset = CGSize(
            width: offset.width + transientOffset.width,
            height: offset.height + transientOffset.height
        )

        ZStack {
            ZStack {
                TopoHoleBaseImage(topoURL: topoURL, fallback: baseImage)
                    .frame(width: frame.width, height: frame.height)
                    .position(x: frame.midX, y: frame.midY)
                Canvas { context, _ in
                    drawRoundShotPath(&context, size: frame.size, overlay: overlay, shots: shots)
                }
                .frame(width: frame.width, height: frame.height)
                .position(x: frame.midX, y: frame.midY)
                precisionMarker(in: frame)
            }
            .frame(width: size.width, height: size.height)
            .scaleEffect(displayedScale)
            .offset(displayedOffset)

            // A one-finger crosshair drag is the precision version of S70's flag placement. Keep a
            // live loupe above the finger so the landing remains visible at any viewport zoom/pan.
            if let focus = markerDragLocation {
                RoundShotPrecisionMagnifierLoupe(
                    mapSize: size,
                    focus: focus,
                    displayedScale: displayedScale,
                    displayedOffset: displayedOffset,
                    diameter: Self.markerLoupeDiameter,
                    magnification: 2.35
                ) {
                    ZStack {
                        TopoHoleBaseImage(topoURL: topoURL, fallback: baseImage)
                            .frame(width: frame.width, height: frame.height)
                            .position(x: frame.midX, y: frame.midY)
                        Canvas { context, _ in
                            drawRoundShotPath(&context, size: frame.size, overlay: overlay, shots: shots)
                        }
                        .frame(width: frame.width, height: frame.height)
                        .position(x: frame.midX, y: frame.midY)
                        precisionMarker(in: frame)
                    }
                    .frame(width: size.width, height: size.height)
                }
                .position(precisionLoupePosition(focus, in: size))
                .allowsHitTesting(false)
            }

            // Keep drag/tap/pinch handling on the map-only layer. The zoom controls and the
            // cancel/confirm bar remain independent SwiftUI buttons above this surface.
            precisionInteractionLayer(size: size, frame: frame)

            VStack(spacing: 9) {
                precisionControl(system: "plus.magnifyingglass", label: "放大落点", identifier: "round-shot-precision-zoom-in") {
                    changeScale(by: 0.5, in: size)
                }
                precisionControl(system: "minus.magnifyingglass", label: "缩小落点", identifier: "round-shot-precision-zoom-out") {
                    changeScale(by: -0.5, in: size)
                }
                precisionControl(system: "scope", label: "还原地图", identifier: "round-shot-precision-fit") {
                    resetViewport()
                }
            }
            .padding(.top, Self.headerInset + 8)
            .padding(.trailing, 12)

            VStack {
                Spacer()
                HStack(spacing: 10) {
                    Button {
                        markerDragLocation = nil
                        onCancel()
                        dismiss()
                    } label: {
                        Label("取消", systemImage: "xmark")
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(.bordered)
                    .tint(.white.opacity(0.82))
                    .accessibilityIdentifier("round-shot-precision-cancel-action")

                    Button {
                        markerDragLocation = nil
                        onCommit(clampedPixel())
                        dismiss()
                    } label: {
                        Label("确认位置", systemImage: "checkmark")
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(LiveHoleStyle.green)
                    .accessibilityIdentifier("round-shot-precision-confirm")
                }
                .padding(.horizontal, 14)
                .padding(.bottom, 18)
            }
        }
        .frame(width: size.width, height: size.height)
        .clipped()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("round-shot-precision-editor")
    }

    private func precisionInteractionLayer(size: CGSize, frame: CGRect) -> some View {
        Rectangle()
            .fill(.clear)
            .frame(width: size.width, height: size.height)
            .contentShape(Rectangle())
            .gesture(mapGesture(size: size, frame: frame))
            .simultaneousGesture(
                MagnificationGesture()
                    .updating($pinchScale) { value, state, _ in state = value }
                    .onEnded { value in
                        scale = min(max(scale * value, 1), 4)
                        offset = clamped(offset, in: size, scale: scale)
                    }
            )
            .simultaneousGesture(
                SpatialTapGesture()
                    .onEnded { value in
                        guard !didDrag,
                              let next = pixel(at: value.location, size: size, frame: frame, clampToMap: false) else {
                            return
                        }
                        pixel = next
                    }
            )
            .accessibilityHidden(true)
    }

    private func precisionMarker(in frame: CGRect) -> some View {
        let fitScale = frame.width / CGFloat(max(overlay.w, 1))
        let local = CGPoint(
            x: CGFloat(pixel.x) * fitScale,
            y: CGFloat(pixel.y) * fitScale
        )
        let point = CGPoint(x: frame.minX + local.x, y: frame.minY + local.y)
        return ZStack {
            Circle()
                .fill(Color.orange.opacity(0.24))
                .frame(width: 58, height: 58)
                .overlay(Circle().stroke(Color.orange, lineWidth: 2.5))
            Rectangle().fill(.white).frame(width: 1.5, height: 26)
            Rectangle().fill(.white).frame(width: 26, height: 1.5)
        }
        .position(point)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("第 \(shotNumber) 杆落点")
        .accessibilityIdentifier("round-shot-precision-marker")
    }

    private var shotNumber: Int {
        (shots.firstIndex(where: { $0.id == shotId }) ?? 0) + 1
    }

    private func precisionControl(
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

    private func mapFrame(in size: CGSize) -> CGRect? {
        let availableHeight = max(size.height - Self.headerInset - Self.bottomInset, 1)
        let available = CGSize(width: size.width, height: availableHeight)
        guard let local = LivePlayMapOverlayLayout.mapFrame(
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            in: available
        ) else { return nil }
        return local.offsetBy(dx: 0, dy: Self.headerInset)
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
            markerDragLocation = nil
        }
    }

    private func mapGesture(size: CGSize, frame: CGRect) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                if interactionMode == nil {
                    let marker = screenPoint(for: pixel, frame: frame, size: size, scale: scale, offset: offset)
                    if let marker,
                       hypot(marker.x - value.startLocation.x, marker.y - value.startLocation.y) <= 46 {
                        interactionMode = .point
                    } else if scale > 1.01 {
                        interactionMode = .pan
                    } else {
                        interactionMode = .point
                    }
                }
                didDrag = true
                switch interactionMode {
                case .point:
                    markerDragLocation = value.location
                    if let next = pixel(at: value.location, size: size, frame: frame, clampToMap: true) {
                        pixel = next
                    }
                case .pan:
                    markerDragLocation = nil
                    transientOffset = value.translation
                case nil:
                    break
                }
            }
            .onEnded { value in
                defer {
                    interactionMode = nil
                    transientOffset = .zero
                    markerDragLocation = nil
                    DispatchQueue.main.async { didDrag = false }
                }
                switch interactionMode {
                case .point:
                    if let next = pixel(at: value.location, size: size, frame: frame, clampToMap: true) {
                        pixel = next
                    }
                case .pan:
                    offset = clamped(
                        CGSize(width: offset.width + value.translation.width, height: offset.height + value.translation.height),
                        in: size,
                        scale: scale
                    )
                case nil:
                    break
                }
            }
    }

    private func pixel(
        at screenPoint: CGPoint,
        size: CGSize,
        frame: CGRect,
        clampToMap: Bool
    ) -> CGPoint? {
        let base = inverseTransform(screenPoint, in: size, scale: scale, offset: offset)
        let fitted = LivePlayMapOverlayLayout.unproject(
            screenPoint: CGPoint(x: base.x - frame.minX, y: base.y - frame.minY),
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            from: frame.size,
            clampToMap: clampToMap
        )
        guard let fitted else { return nil }
        return CGPoint(x: fitted[0], y: fitted[1])
    }

    private func screenPoint(
        for pixel: CGPoint,
        frame: CGRect,
        size: CGSize,
        scale: CGFloat,
        offset: CGSize
    ) -> CGPoint? {
        guard overlay.w > 0, overlay.h > 0 else { return nil }
        let base = CGPoint(
            x: frame.minX + pixel.x / CGFloat(overlay.w) * frame.width,
            y: frame.minY + pixel.y / CGFloat(overlay.h) * frame.height
        )
        return transformed(base, in: size, scale: scale, offset: offset)
    }

    private func transformed(_ base: CGPoint, in size: CGSize, scale: CGFloat, offset: CGSize) -> CGPoint {
        CGPoint(
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

    private func clampedPixel() -> [Double] {
        [
            min(max(Double(pixel.x), 0), Double(max(overlay.w - 1, 0))),
            min(max(Double(pixel.y), 0), Double(max(overlay.h - 1, 0))),
        ]
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

    /// Place the precision loupe above the finger when possible, with a stable fallback below the
    /// finger near the header. Keeping it inside the map viewport prevents clipping and avoids the
    /// bottom confirm/cancel rail.
    private func precisionLoupePosition(_ location: CGPoint, in size: CGSize) -> CGPoint {
        let half = Self.markerLoupeDiameter / 2
        let minX = half + 8
        let maxX = max(minX, size.width - half - 8)
        let x = min(max(location.x, minX), maxX)
        let minimumY = Self.headerInset + half + 8
        let maximumY = max(minimumY, size.height - Self.bottomInset - half - 8)
        let above = location.y - half - 26
        let below = location.y + half + 26
        let candidate = above >= minimumY ? above : below
        return CGPoint(x: x, y: min(max(candidate, minimumY), maximumY))
    }
}

/// A transform-aware loupe for the precision landing editor. The main map applies
/// `C + s(p-C) + O`; applying the same transform before the extra magnification keeps the exact
/// source point under the finger at the loupe crosshair after pinch/pan zooming.
private struct RoundShotPrecisionMagnifierLoupe<Content: View>: View {
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
        .accessibilityLabel("拖动落点时的放大视图")
        .accessibilityIdentifier("round-shot-precision-magnifier")
    }
}
#endif

// MARK: - edit an existing shot (club / lie / delete)

public struct ShotEditSheet: View {
    let shot: RoundShot
    let clubs: [String]
    let onClub: (String?) -> Void
    let onLie: (String?) -> Void
    let onDelete: () -> Void
    let showsMapContext: Bool
    @State private var selectedClub: String
    @State private var selectedLie: String
    @Environment(\.dismiss) private var dismiss

    public init(shot: RoundShot, clubs: [String], onClub: @escaping (String?) -> Void,
                onLie: @escaping (String?) -> Void, onDelete: @escaping () -> Void,
                showsMapContext: Bool = true) {
        self.shot = shot
        self.clubs = clubs
        self.onClub = onClub
        self.onLie = onLie
        self.onDelete = onDelete
        self.showsMapContext = showsMapContext
        self._selectedClub = State(initialValue: roundEditClubSelection(shot.club))
        let rawLie = (shot.lie ?? "unknown").lowercased()
        let validLies = Set(roundEditLieOptions.map(\.0))
        self._selectedLie = State(initialValue: validLies.contains(rawLie) ? rawLie : "unknown")
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Form {
                    if showsMapContext {
                        Section {
                            Label(shotSummary, systemImage: "scope")
                                .font(.subheadline.weight(.semibold))
                                .accessibilityLabel("地图位置，\(shotSummary)")
                                .accessibilityHint("上方放大镜持续显示当前落点")
                        }
                    } else {
                        Section {
                            Label("原始位置保持不变", systemImage: "location.fill")
                                .font(.subheadline.weight(.semibold))
                            Text(shotSummary).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Section("球杆") {
                        Picker("球杆", selection: Binding(
                            get: { selectedClub },
                            set: {
                                selectedClub = $0
                                onClub($0.isEmpty ? nil : $0)
                            })) {
                            Text("未知").tag("")
                            ForEach(clubOptions, id: \.self) { Text($0).tag($0) }
                        }
                        .accessibilityIdentifier("shot-edit-club-picker")
                        .accessibilityValue(selectedClub.isEmpty ? "未知" : selectedClub)
                    }
                    Section("击球时球位") {
                        Picker("击球时球位", selection: Binding(
                            get: { selectedLie },
                            set: {
                                selectedLie = $0
                                onLie($0 == "unknown" ? nil : $0)
                            })) {
                            ForEach(roundEditLieOptions, id: \.0) { Text($0.1).tag($0.0) }
                        }
                    }
                }
                Divider()
                VStack {
                    Button(role: .destructive) { onDelete(); dismiss() } label: {
                        Label("删除这一杆", systemImage: "trash")
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            .padding(.horizontal, 16)
                            .background(
                                Color(uiColor: .secondarySystemGroupedBackground),
                                in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                            )
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.red)
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 8)
                .background(Color(uiColor: .systemGroupedBackground))
            }
            .navigationTitle("改这一杆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
        .presentationDetents([.medium])
    }

    private var clubOptions: [String] {
        roundEditClubOptions(current: shot.club, clubs: clubs)
    }

    private var shotSummary: String {
        let number = shot.order.map { "第 \(max($0, 1)) 杆" } ?? "当前这一杆"
        let club = shot.club.flatMap { value in
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty || trimmed.lowercased() == "unknown" ? nil : zhClubName(trimmed)
        }
        let lie = shotLieLabel(shot.lie)
        return [number, club, lie == "—" ? nil : lie].compactMap { $0 }.joined(separator: " · ")
    }
}

// MARK: - edit-mode content (observes the edit model so optimistic changes redraw)

/// The whole edit-mode body for one hole. Every visible value comes from the same unsaved draft.
public struct RoundShotEditContent: View {
    @ObservedObject var editModel: RoundEditModel
    let topoURL: URL?

    public init(editModel: RoundEditModel, topoURL: URL?) {
        self.editModel = editModel
        self.topoURL = topoURL
    }

    public var body: some View {
        VStack(spacing: 12) {
            RoundShotMapView(shotMap: editModel.map, topoURL: topoURL, editModel: editModel)
            PenaltyStepper(value: editModel.map.manualPenalty) { editModel.setPenalty($0) }
                .hubCard()
            Text("点空白添加 · 长按编号拖动 · 点编号看详情")
                .font(.caption).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, alignment: .center)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            RoundShotReorderList(
                editModel: editModel,
                ppm: editModel.map.map?.overlay.ppm,
                // Keep list and map selection bidirectional.  The selected map handle exposes the
                // same S70-style precision entry used after a tap/drag, so a landing never becomes
                // a dead-end just because it was chosen from the ordered list.
                onEdit: { shot in
                    editModel.selectedShotId = shot.id
                },
                onPrecision: { shot in
                    editModel.requestPrecision(for: shot.id)
                }
            )
            RoundShotMapLegend()
            if let err = editModel.saveError {
                Text(err).font(.caption2).foregroundStyle(.orange).multilineTextAlignment(.center)
            }
        }
    }
}

/// Fact-only fallback while precise topo is unavailable. The player can still fix the counted list,
/// club, start lie and penalty, but there is deliberately no add/move gesture without an authority
/// pixel frame. Save persists only stable ids + facts, leaving every source GPS coordinate untouched.
public struct RoundShotFactEditContent: View {
    @ObservedObject var editModel: RoundEditModel
    @State private var editingShot: RoundShot?

    public init(editModel: RoundEditModel) {
        self.editModel = editModel
    }

    public var body: some View {
        VStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Label("精确地图准备中", systemImage: "location.fill")
                    .font(.subheadline.weight(.semibold))
                Text("已有 GPS 原样保留；现在可改球杆、击球时球位、顺序、删除和罚杆，位置稍后在精确地图上调整。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .hubCard()
            PenaltyStepper(value: editModel.map.manualPenalty) { editModel.setPenalty($0) }
                .hubCard()
            RoundShotReorderList(
                editModel: editModel,
                ppm: nil,
                onEdit: { shot in editingShot = shot }
            )
            if let err = editModel.saveError {
                Text(err).font(.caption2).foregroundStyle(.orange).multilineTextAlignment(.center)
            }
        }
        .sheet(item: $editingShot) { shot in
            ShotEditSheet(
                shot: shot,
                clubs: roundEditCommonClubs,
                onClub: { editModel.editClub(shotId: shot.id, $0) },
                onLie: { editModel.editLie(shotId: shot.id, $0) },
                onDelete: {
                    editModel.delete(shotId: shot.id)
                    editModel.selectedShotId = nil
                },
                showsMapContext: false
            )
        }
    }
}

// MARK: - 逐杆 row (shared) + editable reorder list (设计 §6)

/// One row of the 逐杆 list: order # + club (or 自动补 / —) + distance(码) + 起始球位 → 落点球位.
/// Shared by the read-only card and the edit-mode reorderable list, so a dragged distance and a
/// reordered position render identically in both.
public struct RoundShotRow: View {
    let shot: RoundShot
    let ppm: Double?
    /// Explicit 1-based number to show (the live list position); falls back to the shot's raw order.
    let displayNumber: Int?

    public init(shot: RoundShot, ppm: Double?, displayNumber: Int? = nil) {
        self.shot = shot
        self.ppm = ppm
        self.displayNumber = displayNumber
    }

    public var body: some View {
        HStack(spacing: 8) {
            Text("\(displayNumber ?? shot.order ?? 0)")
                .font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 22, alignment: .leading)
            if let club = shot.club, !club.isEmpty, club.lowercased() != "unknown" {
                Text(zhClubName(club)).font(.subheadline)
            } else if shot.synthetic {
                Text("开球(自动补)").font(.subheadline).foregroundStyle(.secondary)
            } else {
                Text("—").font(.subheadline).foregroundStyle(.secondary)
            }
            if let yards = roundShotYards(shot, ppm: ppm) {
                Text("\(yards) 码").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }
            Spacer()
            Text(shotLieLabel(shot.lie) + " → " + shotLieLabel(shot.endLie))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// 编辑态逐杆列表:拖动系统右侧手柄重排，点行内垃圾桶删除。列表编号和地图编号共用数组顺序。
/// (唯一能长按拖动重排的容器);外层是 `ScrollView`,故 `.scrollDisabled` 让外层滚、行仍能拖。
/// ⚠️ ImageRenderer / 窗口快照不渲 `List` 内容 → 编辑态快照里这块是空的,真机 / XCUITest 才验交互。
public struct RoundShotReorderList: View {
    @ObservedObject var editModel: RoundEditModel
    let ppm: Double?
    let onEdit: ((RoundShot) -> Void)?
    let onPrecision: ((RoundShot) -> Void)?

    public init(
        editModel: RoundEditModel,
        ppm: Double?,
        onEdit: ((RoundShot) -> Void)? = nil,
        onPrecision: ((RoundShot) -> Void)? = nil
    ) {
        self.editModel = editModel
        self.ppm = ppm
        self.onEdit = onEdit
        self.onPrecision = onPrecision
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("共 \(editModel.map.shots.count) 杆 · 点一杆修改 · 拖动排序 · 垃圾桶删除")
                .font(.caption).foregroundStyle(.secondary)
            List {
                ForEach(Array(editModel.map.shots.enumerated()), id: \.element.id) { idx, shot in
                    HStack(spacing: 8) {
                        RoundShotRow(shot: shot, ppm: ppm, displayNumber: idx + 1)
                            .accessibilityElement(children: .combine)
                            .accessibilityIdentifier("shot-draft-row-\(idx + 1)")
                            .contentShape(Rectangle())
                            .onTapGesture {
                                editModel.selectedShotId = shot.id
                                onEdit?(shot)
                            }
                        Button(role: .destructive) {
                            editModel.delete(shotId: shot.id)
                        } label: {
                            Image(systemName: "trash")
                                .frame(width: 28, height: 32)
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("删除第 \(idx + 1) 杆")
                        .accessibilityIdentifier("shot-draft-delete-\(idx + 1)")
                        if editModel.canEditPositions {
                            Button {
                                onPrecision?(shot)
                            } label: {
                                Image(systemName: "plus.magnifyingglass")
                                    .frame(width: 32, height: 32)
                            }
                            .buttonStyle(.borderless)
                            .accessibilityLabel("放大调整第 \(idx + 1) 杆位置")
                            .accessibilityHint("打开精确定位地图")
                            .accessibilityIdentifier("shot-draft-precision-\(idx + 1)")
                        }
                    }
                    .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
                    .listRowBackground(
                        editModel.selectedShotId == shot.id
                            ? LiveHoleStyle.green.opacity(0.12)
                            : Color.clear
                    )
                }
                .onMove { indices, newOffset in
                    var ids = editModel.map.shots.map { $0.id }
                    ids.move(fromOffsets: indices, toOffset: newOffset)
                    editModel.reorder(ids)
                }
            }
            .listStyle(.plain)
            .scrollDisabled(true)
            .scrollContentBackground(.hidden)
            .environment(\.editMode, .constant(.active))
            .frame(height: CGFloat(max(1, editModel.map.shots.count)) * 50 + 8)
        }
        .hubCard()
    }
}

// MARK: - per-hole manual penalty stepper

public struct PenaltyStepper: View {
    let value: Int
    let onChange: (Int) -> Void

    public init(value: Int, onChange: @escaping (Int) -> Void) {
        self.value = value
        self.onChange = onChange
    }

    public var body: some View {
        HStack {
            Text("本洞罚杆").font(.subheadline.weight(.medium))
            Spacer()
            Button { onChange(max(0, value - 1)) } label: {
                Image(systemName: "minus.circle.fill").font(.title2)
            }
            .buttonStyle(.plain).foregroundStyle(value > 0 ? Color.accentColor : Color.secondary)
            Text("\(value)").font(.title3.monospacedDigit().weight(.bold)).frame(minWidth: 28)
            Button { onChange(value + 1) } label: {
                Image(systemName: "plus.circle.fill").font(.title2)
            }
            .buttonStyle(.plain).foregroundStyle(Color.accentColor)
        }
        .padding(.vertical, 4)
    }
}
