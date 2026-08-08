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

// MARK: - edit overlay (handles + drag-to-move + magnifier + tap → add/edit)

#if canImport(UIKit)
/// The edit affordance layer, overlaid on the read-only shot map when editing. Draws a drag-handle
/// ring on each landing, and disambiguates ONE single-finger gesture (设计 §2/§5):
///   • **tap** a handle → select and keep that landing highlighted,
///   • drag the selected (or newly touched) handle → move it (live lines + magnifier),
///   • **tap** empty → add a shot there.
/// Club/lie/delete are a secondary button after selection, so tapping a landing never unexpectedly
/// replaces the map with a sheet before the player has a chance to drag it.
/// Pixel↔view conversion uses the fitted map size from GeometryReader (same projection as the canvas).
public struct RoundShotEditLayer: View {
    @ObservedObject var editModel: RoundEditModel
    let overlay: CoursePrepOverlay
    let clubs: [String]
    /// The map's own base bitmap (flat fallback) + topo URL — reused by the magnifier so it shows the
    /// real course under the finger, not just the shot lines.
    let baseImage: UIImage
    let topoURL: URL?

    @State private var editingShot: RoundShot?
    @State private var addAtPx: [Double]?
    @State private var selectedShotId: String?
    /// Current finger location (view coords) during a drag — drives the magnifier + the committed px.
    @State private var dragLocation: CGPoint?
    /// The shot whose handle this gesture grabbed (nil = started on empty), and whether it has
    /// travelled past the tap↔drag threshold yet.
    @State private var grabbedShotId: String?
    @State private var movedFar = false
    @State private var gestureActive = false

    private let hitRadius: CGFloat = 24
    private let dragThreshold: CGFloat = 10
    private let loupeDiameter: CGFloat = 116

    public init(editModel: RoundEditModel, overlay: CoursePrepOverlay, clubs: [String],
                baseImage: UIImage, topoURL: URL?) {
        self.editModel = editModel
        self.overlay = overlay
        self.clubs = clubs
        self.baseImage = baseImage
        self.topoURL = topoURL
    }

    public var body: some View {
        GeometryReader { geo in
            let sx = geo.size.width / CGFloat(max(overlay.w, 1))
            let sy = geo.size.height / CGFloat(max(overlay.h, 1))
            ZStack {
                Canvas { ctx, _ in
                    for shot in editModel.map.shots {
                        guard let e = shot.end, e.count >= 2 else { continue }
                        let p = CGPoint(x: CGFloat(e[0]) * sx, y: CGFloat(e[1]) * sy)
                        let dragging = editModel.draggingShotId == shot.id
                        let selected = selectedShotId == shot.id
                        let r: CGFloat = dragging ? 15 : (selected ? 13 : 11)
                        let ring = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
                        ctx.stroke(
                            ring,
                            with: .color(selected ? LiveHoleStyle.green : .white),
                            lineWidth: dragging ? 3.5 : (selected ? 3 : 2)
                        )
                        ctx.stroke(ring, with: .color(.black.opacity(0.45)), lineWidth: 0.5)
                        if dragging || selected {
                            ctx.fill(Path(ellipseIn: CGRect(x: p.x - 2.5, y: p.y - 2.5, width: 5, height: 5)),
                                     with: .color(.white))
                        }
                    }
                }
                .contentShape(Rectangle())
                .gesture(dragGesture(sx: sx, sy: sy))

                // Magnifier loupe: floats ABOVE the finger while dragging (设计 §5), showing the
                // area the finger covers, magnified + crosshair, so the landing lands precisely.
                // Gated on `movedFar` so a mere tap-to-edit doesn't flash the loupe.
                if let loc = dragLocation, editModel.draggingShotId != nil, movedFar {
                    MagnifierLoupe(overlay: overlay, shots: editModel.map.shots,
                                   baseImage: baseImage, topoURL: topoURL,
                                   mapSize: geo.size, focus: loc, diameter: loupeDiameter)
                        .position(loupePosition(loc, in: geo.size))
                        .allowsHitTesting(false)
                }

                // A system sheet covers the lower half of the map. Keep the exact tapped/selected
                // landing visible in the uncovered area instead of making the player remember which
                // dot is being edited. This reuses the real topo + current route rather than drawing
                // a detached synthetic thumbnail.
                if let focus = sheetFocus(sx: sx, sy: sy) {
                    VStack(spacing: 3) {
                        MagnifierLoupe(
                            overlay: overlay,
                            shots: editModel.map.shots,
                            baseImage: baseImage,
                            topoURL: topoURL,
                            mapSize: geo.size,
                            focus: focus,
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
                                editingShot = selectedShot
                            } label: {
                                Label(selectedShotLabel, systemImage: "slider.horizontal.3")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 7)
                                    .background(.black.opacity(0.78), in: Capsule())
                            }
                            .buttonStyle(.plain)
                            .accessibilityHint("修改球杆、球位或删除这一杆")
                        }
                    }
                    .padding(10)
                }
            }
        }
        .sheet(item: $editingShot) { shot in
            ShotEditSheet(
                shot: shot, clubs: effectiveClubs,
                onClub: { editModel.editClub(shotId: shot.id, $0) },
                onLie: { editModel.editLie(shotId: shot.id, $0) },
                onDelete: {
                    editModel.delete(shotId: shot.id)
                    selectedShotId = nil
                }
            )
        }
        .sheet(isPresented: Binding(get: { addAtPx != nil }, set: { if !$0 { addAtPx = nil } })) {
            if let px = addAtPx {
                AddShotSheet(clubs: effectiveClubs) { club, lie in
                    editModel.addShot(px: px, club: club, lie: lie, afterShotId: insertAfter(px))
                    addAtPx = nil
                }
            }
        }
    }

    /// One `DragGesture(minimumDistance:0)` handling both tap and drag. First frame decides if we
    /// grabbed a handle; past the threshold it's a drag (live preview, commit on release); otherwise
    /// it's a tap (select a landing / add on empty). No pan/zoom in this view, so no gesture contention.
    private func dragGesture(sx: CGFloat, sy: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { v in
                if !gestureActive {
                    gestureActive = true
                    movedFar = false
                    if let hit = nearestHit(to: v.startLocation, sx: sx, sy: sy) {
                        grabbedShotId = hit.id
                        selectedShotId = hit.id
                        editModel.draggingShotId = hit.id
                    } else {
                        grabbedShotId = nil
                    }
                }
                dragLocation = v.location
                if hypot(v.location.x - v.startLocation.x, v.location.y - v.startLocation.y) > dragThreshold {
                    movedFar = true
                }
                // Live rubber-band the grabbed landing (local only, no network) once clearly dragging.
                if let id = grabbedShotId, movedFar {
                    editModel.previewMove(shotId: id, px: clampedPixel(v.location, sx: sx, sy: sy))
                }
            }
            .onEnded { v in
                if let id = grabbedShotId, movedFar {
                    editModel.move(shotId: id, px: clampedPixel(v.location, sx: sx, sy: sy))
                } else if !movedFar {
                    if let hit = nearestHit(to: v.location, sx: sx, sy: sy) {
                        selectedShotId = hit.id
                    } else {
                        selectedShotId = nil
                        addAtPx = clampedPixel(v.location, sx: sx, sy: sy)
                    }
                }
                editModel.draggingShotId = nil
                grabbedShotId = nil
                movedFar = false
                gestureActive = false
                dragLocation = nil
            }
    }

    /// Place the loupe centered horizontally on the finger but ABOVE it, clamped inside the map.
    private func loupePosition(_ loc: CGPoint, in size: CGSize) -> CGPoint {
        let half = loupeDiameter / 2
        let y = max(half + 6, loc.y - half - 26)
        let x = min(max(half + 6, loc.x), size.width - half - 6)
        return CGPoint(x: x, y: y)
    }

    private var effectiveClubs: [String] { clubs.isEmpty ? roundEditCommonClubs : clubs }

    private var selectedShot: RoundShot? {
        guard let selectedShotId else { return nil }
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
        if let editingShot,
           let index = editModel.map.shots.firstIndex(where: { $0.id == editingShot.id }) {
            return "正在改第 \(index + 1) 杆"
        }
        return "补杆位置"
    }

    private func sheetFocus(sx: CGFloat, sy: CGFloat) -> CGPoint? {
        let px: [Double]?
        if let end = editingShot?.end, end.count >= 2 {
            px = [Double(end[0]), Double(end[1])]
        } else {
            px = addAtPx
        }
        guard let px, px.count >= 2 else { return nil }
        return CGPoint(x: CGFloat(px[0]) * sx, y: CGFloat(px[1]) * sy)
    }

    private func hitTest(_ s: RoundShot, _ loc: CGPoint, _ sx: CGFloat, _ sy: CGFloat) -> Bool {
        guard let e = s.end, e.count >= 2 else { return false }
        let p = CGPoint(x: CGFloat(e[0]) * sx, y: CGFloat(e[1]) * sy)
        return hypot(p.x - loc.x, p.y - loc.y) <= hitRadius
    }

    private func nearestHit(to location: CGPoint, sx: CGFloat, sy: CGFloat) -> RoundShot? {
        editModel.map.shots
            .filter { hitTest($0, location, sx, sy) }
            .min { lhs, rhs in
                viewDistance(lhs, to: location, sx: sx, sy: sy)
                    < viewDistance(rhs, to: location, sx: sx, sy: sy)
            }
    }

    private func viewDistance(
        _ shot: RoundShot,
        to location: CGPoint,
        sx: CGFloat,
        sy: CGFloat
    ) -> CGFloat {
        guard let end = shot.end, end.count >= 2 else { return .greatestFiniteMagnitude }
        return hypot(CGFloat(end[0]) * sx - location.x, CGFloat(end[1]) * sy - location.y)
    }

    private func clampedPixel(_ location: CGPoint, sx: CGFloat, sy: CGFloat) -> [Double] {
        [
            min(max(Double(location.x / sx), 0), Double(overlay.w)),
            min(max(Double(location.y / sy), 0), Double(overlay.h)),
        ]
    }

    /// Insert the new shot after the existing landing nearest the tap (a sensible "which gap"; the
    /// backend re-sequences by this id). Forward-play assumption keeps the two connecting lines sane.
    private func insertAfter(_ px: [Double]) -> String? {
        editModel.map.shots.min(by: { pxDist($0, px) < pxDist($1, px) })?.id
    }

    private func pxDist(_ s: RoundShot, _ px: [Double]) -> CGFloat {
        guard let e = s.end, e.count >= 2 else { return .greatestFiniteMagnitude }
        return hypot(CGFloat(e[0]) - CGFloat(px[0]), CGFloat(e[1]) - CGFloat(px[1]))
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
    let baseImage: UIImage
    let topoURL: URL?
    /// Fitted map size in view coordinates (the edit layer's GeometryReader size).
    let mapSize: CGSize
    /// Finger location in that same view space (the point to magnify + center under the crosshair).
    let focus: CGPoint
    var diameter: CGFloat = 116
    var magnification: CGFloat = 2.2

    public init(overlay: CoursePrepOverlay, shots: [RoundShot], baseImage: UIImage, topoURL: URL?,
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
    }
}
#endif

// MARK: - edit an existing shot (club / lie / delete)

public struct ShotEditSheet: View {
    let shot: RoundShot
    let clubs: [String]
    let onClub: (String) -> Void
    let onLie: (String) -> Void
    let onDelete: () -> Void
    @State private var selectedClub: String
    @State private var selectedLie: String
    @Environment(\.dismiss) private var dismiss

    public init(shot: RoundShot, clubs: [String], onClub: @escaping (String) -> Void,
                onLie: @escaping (String) -> Void, onDelete: @escaping () -> Void) {
        self.shot = shot
        self.clubs = clubs
        self.onClub = onClub
        self.onLie = onLie
        self.onDelete = onDelete
        self._selectedClub = State(initialValue: roundEditClubSelection(shot.club))
        let rawLie = (shot.lie ?? "unknown").lowercased()
        let validLies = Set(roundEditLieOptions.map(\.0))
        self._selectedLie = State(initialValue: validLies.contains(rawLie) ? rawLie : "unknown")
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Form {
                    Section {
                        Label(shotSummary, systemImage: "scope")
                            .font(.subheadline.weight(.semibold))
                            .accessibilityLabel("地图位置，\(shotSummary)")
                            .accessibilityHint("上方放大镜持续显示当前落点")
                    }
                    Section("球杆") {
                        Picker("球杆", selection: Binding(
                            get: { selectedClub },
                            set: {
                                selectedClub = $0
                                if !$0.isEmpty { onClub($0) }
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
                                if !$0.isEmpty { onLie($0) }
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

// MARK: - add a shot (club default-highlighted by nothing yet; lie)

public struct AddShotSheet: View {
    let clubs: [String]
    let onAdd: (String?, String?) -> Void
    @State private var club: String = ""
    @State private var lie: String = "unknown"
    @Environment(\.dismiss) private var dismiss

    public init(clubs: [String], onAdd: @escaping (String?, String?) -> Void) {
        self.clubs = clubs
        self.onAdd = onAdd
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section("地图位置") {
                    Label("上方放大镜已标记补杆位置", systemImage: "scope")
                        .font(.subheadline.weight(.semibold))
                }
                Section("这一杆用什么杆") {
                    Picker("球杆", selection: $club) {
                        Text("未知").tag("")
                        ForEach(clubOptions, id: \.self) { Text($0).tag($0) }
                    }
                }
                Section("击球时球位") {
                    Picker("击球时球位", selection: $lie) {
                        ForEach(roundEditLieOptions, id: \.0) { Text($0.1).tag($0.0) }
                    }
                }
            }
            .navigationTitle("补一杆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("加上") { onAdd(club.isEmpty ? nil : club, lie.isEmpty ? nil : lie); dismiss() }
                }
            }
        }
        .presentationDetents([.medium])
    }

    private var clubOptions: [String] {
        roundEditClubOptions(current: nil, clubs: clubs)
    }
}

// MARK: - edit-mode content (observes the edit model so optimistic changes redraw)

/// The whole edit-mode body for one hole: the map with the edit overlay + the penalty stepper +
/// a hint. Observes ``RoundEditModel`` so every optimistic change redraws instantly.
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
            Text("点中落点后直接拖动 · 点空白补杆 · 详情可改球杆/球位")
                .font(.caption).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, alignment: .center)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            RoundShotReorderList(editModel: editModel, ppm: editModel.map.map?.overlay.ppm)
            RoundShotMapLegend()
            if let err = editModel.pendingError {
                Text(err).font(.caption2).foregroundStyle(.orange).multilineTextAlignment(.center)
            }
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

/// 编辑态逐杆列表:长按行拖动重排(设计 §6)→ `editModel.reorder(新 shotId 顺序)`。用 `List` + `.onMove`
/// (唯一能长按拖动重排的容器);外层是 `ScrollView`,故 `.scrollDisabled` 让外层滚、行仍能拖。
/// ⚠️ ImageRenderer / 窗口快照不渲 `List` 内容 → 编辑态快照里这块是空的,真机 / XCUITest 才验交互。
public struct RoundShotReorderList: View {
    @ObservedObject var editModel: RoundEditModel
    let ppm: Double?

    public init(editModel: RoundEditModel, ppm: Double?) {
        self.editModel = editModel
        self.ppm = ppm
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("逐杆 · 长按拖动可调整顺序").font(.caption).foregroundStyle(.secondary)
            List {
                ForEach(Array(editModel.map.shots.enumerated()), id: \.element.id) { idx, shot in
                    RoundShotRow(shot: shot, ppm: ppm, displayNumber: idx + 1)
                        .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
                        .listRowBackground(Color.clear)
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
