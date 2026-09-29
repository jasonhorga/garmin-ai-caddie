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

// MARK: - edit overlay (drag handles + tap-to-add + magnifier)

#if canImport(UIKit)
/// The edit layer over the hole map (README §7 同屏改杆). In edit mode the numbered landings are drag
/// handles: dragging one moves it with a magnifier above the finger; a tap on a handle selects it
/// (tap it again to deselect); a tap on empty ground adds a shot after the selected one (at the end
/// when none is selected) with its club guessed from the distance. Finger-up never writes the server
/// — Save owns persistence. Pixel↔view conversion uses the fitted map frame (same projection as the
/// canvas underneath).
public struct RoundShotEditLayer: View {
    @ObservedObject var editModel: RoundEditModel
    let overlay: CoursePrepOverlay
    /// The map's own base bitmap (flat fallback) + topo URL — reused by the magnifier so it shows the
    /// real course under the finger, not just the shot lines.
    let baseImage: UIImage?
    let topoURL: URL?

    /// Current finger location (view coords) during a drag — drives the magnifier + the committed px.
    @State private var dragLocation: CGPoint?
    /// The handle this touch started on (nil = empty ground).
    @State private var touchedShotId: String?
    @State private var touchStarted = false
    @State private var isDragging = false

    private let hitRadius: CGFloat = 24
    private let dragThreshold: CGFloat = 6
    private let loupeDiameter: CGFloat = 100
    private static let selectedFill = Color(red: 1, green: 216 / 255, blue: 74 / 255)

    public init(editModel: RoundEditModel, overlay: CoursePrepOverlay, baseImage: UIImage?, topoURL: URL?) {
        self.editModel = editModel
        self.overlay = overlay
        self.baseImage = baseImage
        self.topoURL = topoURL
    }

    public var body: some View {
        GeometryReader { geo in
            if let frame = mapFrame(in: geo.size) {
                ZStack {
                    Canvas { ctx, _ in
                        // Putts are counted by 推杆 −/+, not dragged: only full shots get a handle,
                        // numbered as in read mode.
                        for (index, shot) in fullShots.enumerated() {
                            guard let p = screenPoint(for: shot.end, frame: frame) else { continue }
                            let selected = editModel.selectedShotId == shot.id
                            let dragging = editModel.draggingShotId == shot.id
                            let r: CGFloat = dragging ? 15 : 13
                            let handle = Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
                            ctx.fill(handle, with: .color(selected ? Self.selectedFill : Color(red: 16 / 255, green: 20 / 255, blue: 18 / 255)))
                            ctx.stroke(handle, with: .color(selected ? .black.opacity(0.35) : .white), lineWidth: 2)
                            ctx.draw(
                                Text("\(index + 1)")
                                    .font(.system(size: 12, weight: .heavy))
                                    .monospacedDigit()
                                    .foregroundColor(selected ? .black : .white),
                                at: p
                            )
                        }
                    }
                    .contentShape(Rectangle())
                    .gesture(touchGesture(frame: frame))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("编辑地图，共 \(fullShots.count) 杆")
                    .accessibilityHint("拖动编号改落点，点空白加一杆")
                    .accessibilityIdentifier("round-shot-edit-map")

                    if let loc = dragLocation, isDragging {
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
                }
            } else {
                Color.clear
            }
        }
    }

    private var fullShots: [RoundShot] {
        editModel.map.shots.filter(roundShotIsFullShot)
    }

    /// One gesture for tap and drag: a drag that starts on a handle moves it, a drag that starts on
    /// empty ground does nothing, and only a real tap (the finger barely moved) selects or adds.
    /// The dragged shot is selected on finger-up, so the bottom bar does not change height (and the
    /// map does not shift) under the finger mid-drag.
    private func touchGesture(frame: CGRect) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                if !touchStarted {
                    touchStarted = true
                    touchedShotId = nearestHit(to: value.startLocation, frame: frame)?.id
                }
                guard let id = touchedShotId else { return }
                let distance = hypot(value.translation.width, value.translation.height)
                if !isDragging, distance >= dragThreshold {
                    isDragging = true
                    editModel.draggingShotId = id
                }
                guard isDragging else { return }
                dragLocation = value.location
                if let px = pixel(at: value.location, frame: frame, clampToMap: true) {
                    editModel.previewMove(shotId: id, px: px)
                }
            }
            .onEnded { value in
                defer { resetGesture() }
                if isDragging, let id = touchedShotId {
                    if let px = pixel(at: value.location, frame: frame, clampToMap: true) {
                        editModel.move(shotId: id, px: px)
                    }
                    editModel.selectedShotId = id
                    return
                }
                guard hypot(value.translation.width, value.translation.height) < dragThreshold else { return }
                if let id = touchedShotId {
                    editModel.selectedShotId = editModel.selectedShotId == id ? nil : id
                    return
                }
                // Letterboxed margins are outside the factual map and must never become a clamped
                // course coordinate.
                guard let px = pixel(at: value.location, frame: frame, clampToMap: false) else { return }
                let id = editModel.addShot(px: px, afterShotId: editModel.selectedShotId)
                guard !id.isEmpty else { return }
                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            }
    }

    private func resetGesture() {
        editModel.draggingShotId = nil
        touchedShotId = nil
        touchStarted = false
        isDragging = false
        dragLocation = nil
    }

    /// Keep the loupe well clear of the finger, using the lower side only when the upper edge would
    /// clip it. This distance is intentional for real-device use where a fingertip hides the map.
    private func loupePosition(_ loc: CGPoint, in size: CGSize) -> CGPoint {
        let half = loupeDiameter / 2
        let fingerClearance: CGFloat = 72
        let minimumY = half + 6
        let maximumY = max(minimumY, size.height - half - 6)
        let above = loc.y - half - fingerClearance
        let below = loc.y + half + fingerClearance
        let candidate = above >= minimumY ? above : below
        let y = min(max(candidate, minimumY), maximumY)
        let x = min(max(half + 6, loc.x), size.width - half - 6)
        return CGPoint(x: x, y: y)
    }

    private func nearestHit(to location: CGPoint, frame: CGRect) -> RoundShot? {
        guard frame.contains(location) else { return nil }
        var best: (shot: RoundShot, distance: CGFloat)?
        for shot in fullShots {
            guard let end = screenPoint(for: shot.end, frame: frame) else { continue }
            let distance = hypot(end.x - location.x, end.y - location.y)
            guard distance <= hitRadius else { continue }
            if best == nil || distance < best!.distance { best = (shot, distance) }
        }
        return best?.shot
    }

    private func mapFrame(in size: CGSize) -> CGRect? {
        LivePlayMapOverlayLayout.mapFrame(
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            in: size
        )
    }

    private func screenPoint(for pixel: [Int]?, frame: CGRect) -> CGPoint? {
        guard let pixel, pixel.count >= 2, overlay.w > 0, overlay.h > 0 else { return nil }
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

// MARK: - magnifier loupe

/// A compact map window that floats above the finger during a landing drag (100 pt, 2.35×), so the
/// landing stays visible under the fingertip.
public struct MagnifierLoupe: View {
    let overlay: CoursePrepOverlay
    let shots: [RoundShot]
    let baseImage: UIImage?
    let topoURL: URL?
    /// Fitted map size in view coordinates (the edit layer's GeometryReader size).
    let mapSize: CGSize
    /// Finger location in that same view space (the point to magnify + center under the crosshair).
    let focus: CGPoint
    var diameter: CGFloat = 100
    var magnification: CGFloat = 2.35

    public init(overlay: CoursePrepOverlay, shots: [RoundShot], baseImage: UIImage?, topoURL: URL?,
                mapSize: CGSize, focus: CGPoint, diameter: CGFloat = 100, magnification: CGFloat = 2.35) {
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
                    drawRoundShotPath(&ctx, size: size, overlay: overlay, shots: shots, numbered: false)
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
        .overlay(Circle().strokeBorder(.white.opacity(0.9), lineWidth: 1.5))
        .compositingGroup()
        .shadow(color: .black.opacity(0.35), radius: 6, y: 3)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("拖动这一杆落点时的放大视图")
        .accessibilityIdentifier("round-shot-drag-magnifier")
    }
}
#endif

// MARK: - bottom edit bar

/// The edit bar under the map (README §7). Nothing selected: 推杆 and 罚杆 −/+. A shot selected:
/// ‹ 第 N 杆 · D 码 › (moves it one place earlier / later) + 删除, the club pills (the club guessed
/// from the distance first) and the five-column 击球时球位 grid.
public struct RoundShotEditBar: View {
    @ObservedObject var editModel: RoundEditModel

    public init(editModel: RoundEditModel) {
        self.editModel = editModel
    }

    private var selectedIndex: Int? {
        guard let id = editModel.selectedShotId else { return nil }
        return editModel.map.shots.firstIndex { $0.id == id }
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let index = selectedIndex {
                selectedShotControls(editModel.map.shots[index], index: index)
            } else {
                holeCounters
            }
            if let error = editModel.saveError {
                Text(error)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.hazard)
                    .accessibilityIdentifier("round-edit-error")
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 12)
        .padding(.bottom, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.ultraThinMaterial)
        .environment(\.colorScheme, .dark)
    }

    // MARK: nothing selected

    private var holeCounters: some View {
        HStack(spacing: 10) {
            counter(
                title: "推杆",
                value: editModel.putts.map(String.init) ?? "–",
                canDecrease: (editModel.putts ?? 0) > 0,
                canIncrease: (editModel.putts ?? 0) < RoundEditModel.maximumPutts,
                identifier: "round-edit-putts",
                onChange: { editModel.adjustPutts(by: $0) }
            )
            counter(
                title: "罚杆",
                value: "\(editModel.map.manualPenalty)",
                canDecrease: editModel.map.manualPenalty > 0,
                canIncrease: editModel.map.manualPenalty < 100,
                identifier: "round-edit-penalty",
                onChange: { editModel.adjustPenalty(by: $0) }
            )
        }
    }

    private func counter(
        title: String,
        value: String,
        canDecrease: Bool,
        canIncrease: Bool,
        identifier: String,
        onChange: @escaping (Int) -> Void
    ) -> some View {
        HStack(spacing: 6) {
            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(LivePlayStyle.ink78)
            Spacer(minLength: 4)
            stepButton("minus", label: "\(title)减一", enabled: canDecrease, identifier: "\(identifier)-minus") { onChange(-1) }
            Text(value)
                .font(.system(size: 20, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .frame(minWidth: 26)
                .accessibilityLabel("\(title) \(value)")
                .accessibilityIdentifier("\(identifier)-value")
            stepButton("plus", label: "\(title)加一", enabled: canIncrease, identifier: "\(identifier)-plus") { onChange(1) }
        }
        .padding(.horizontal, 12)
        .frame(height: 52)
        .frame(maxWidth: .infinity)
        .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func stepButton(_ system: String, label: String, enabled: Bool, identifier: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: system)
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(enabled ? LivePlayStyle.ink : LivePlayStyle.ink45)
                .frame(width: 32, height: 32)
                .background(LivePlayStyle.fill12, in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }

    // MARK: a shot selected

    @ViewBuilder
    private func selectedShotControls(_ shot: RoundShot, index: Int) -> some View {
        let yards = editModel.yards(of: shot.id)
        let number = editModel.displayNumber(of: shot.id) ?? index + 1
        HStack(spacing: 8) {
            orderButton("chevron.left", label: "往前挪一杆", enabled: editModel.canMoveShot(shot.id, by: -1), identifier: "round-edit-order-earlier") {
                editModel.moveShot(shot.id, by: -1)
            }
            Text(yards.map { "第 \(number) 杆 · \($0) 码" } ?? "第 \(number) 杆")
                .font(.system(size: 16, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .lineLimit(1)
                .accessibilityIdentifier("round-edit-selected")
            orderButton("chevron.right", label: "往后挪一杆", enabled: editModel.canMoveShot(shot.id, by: 1), identifier: "round-edit-order-later") {
                editModel.moveShot(shot.id, by: 1)
            }
            Spacer(minLength: 4)
            Button(role: .destructive) {
                editModel.delete(shotId: shot.id)
            } label: {
                Text("删除")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(LiveScoreStyle.bad)
                    .padding(.horizontal, 12)
                    .frame(height: 32)
                    .background(LivePlayStyle.fill08, in: Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("删除第 \(number) 杆")
            .accessibilityIdentifier("round-edit-delete")
            Button {
                editModel.selectedShotId = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .frame(width: 32, height: 32)
                    .background(LivePlayStyle.fill08, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("不选这一杆")
            .accessibilityIdentifier("round-edit-deselect")
        }
        clubPills(shot, yards: yards)
        lieGrid(shot)
    }

    private func orderButton(_ system: String, label: String, enabled: Bool, identifier: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: system)
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(enabled ? LivePlayStyle.ink : LivePlayStyle.ink45)
                .frame(width: 32, height: 32)
                .background(LivePlayStyle.fill12, in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }

    private func clubPills(_ shot: RoundShot, yards: Int?) -> some View {
        let current = roundEditClubSelection(shot.club)
        let options = RoundClubGuess.orderedClubs(
            guess: RoundClubGuess.club(forYards: yards),
            current: shot.club,
            clubs: roundEditCommonClubs
        )
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(options, id: \.self) { club in
                    let selected = club == current
                    Button {
                        editModel.editClub(shotId: shot.id, club)
                    } label: {
                        Text(club)
                            .font(.system(size: 13.5, weight: .semibold))
                            .foregroundStyle(selected ? LiveScoreStyle.primaryInk : LivePlayStyle.ink)
                            .padding(.horizontal, 12)
                            .frame(height: 34)
                            .background(selected ? LiveScoreStyle.primaryFill : LivePlayStyle.fill08, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(selected ? [.isSelected] : [])
                    .accessibilityIdentifier("round-edit-club-\(club)")
                }
            }
        }
        .accessibilityIdentifier("round-edit-clubs")
    }

    /// 击球时球位 of the selected shot (`shot.lie`, where it was played from — never the landing).
    private func lieGrid(_ shot: RoundShot) -> some View {
        let rawLie = (shot.lie ?? "unknown").lowercased()
        let validLies = Set(roundEditLieOptions.map(\.0))
        let current = validLies.contains(rawLie) ? rawLie : "unknown"
        return LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 5), count: 5), spacing: 5) {
            ForEach(roundEditLieOptions, id: \.0) { option in
                let selected = option.0 == current
                Button {
                    editModel.editLie(shotId: shot.id, option.0 == "unknown" ? nil : option.0)
                } label: {
                    HStack(spacing: 5) {
                        if option.0 != "unknown" {
                            Circle().fill(reviewLieColor(option.0)).frame(width: 8, height: 8)
                        }
                        Text(option.1)
                            .font(.system(size: 12.5, weight: .semibold))
                            .foregroundStyle(LivePlayStyle.ink)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 32)
                    .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke(selected ? LiveScoreStyle.primaryFill : .clear, lineWidth: 1.5)
                    )
                }
                .buttonStyle(.plain)
                .accessibilityLabel("击球时球位 \(option.1)")
                .accessibilityAddTraits(selected ? [.isSelected] : [])
                .accessibilityIdentifier("round-edit-lie-\(option.0)")
            }
        }
    }
}

// MARK: - fact-only edit (no precise map yet)

/// Fact-only fallback while precise topo is unavailable: the recorded shots as a list (tap one to
/// select it; the same bottom bar edits club, lie, order, deletion, putts and penalty). There is no
/// add/move without an authoritative pixel frame, and Save leaves every source GPS untouched.
public struct RoundShotFactEditList: View {
    @ObservedObject var editModel: RoundEditModel

    public init(editModel: RoundEditModel) {
        self.editModel = editModel
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Label("精确地图准备中，位置保持不变", systemImage: "location.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(LivePlayStyle.ink60)
                    .padding(.bottom, 4)
                // Putts are the 推杆 counter below, not rows to edit.
                ForEach(Array(editModel.map.shots.filter(roundShotIsFullShot).enumerated()), id: \.element.id) { index, shot in
                    let selected = editModel.selectedShotId == shot.id
                    Button {
                        editModel.selectedShotId = selected ? nil : shot.id
                    } label: {
                        RoundShotRow(shot: shot, ppm: nil, displayNumber: index + 1)
                            .padding(.horizontal, 12)
                            .frame(height: 46)
                            .background(
                                selected ? LivePlayStyle.fill12 : LivePlayStyle.fill08,
                                in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .stroke(selected ? LiveScoreStyle.primaryFill : .clear, lineWidth: 1.2)
                            )
                    }
                    .buttonStyle(.plain)
                    .accessibilityElement(children: .combine)
                    .accessibilityAddTraits(selected ? [.isSelected] : [])
                    .accessibilityIdentifier("shot-draft-row-\(index + 1)")
                }
            }
            .padding(16)
        }
    }
}

/// Read-only list for a hole whose map is not ready: the recorded shots, honestly, without a map.
public struct RoundShotFactList: View {
    let shots: [RoundShot]
    let ppm: Double?

    public init(shots: [RoundShot], ppm: Double?) {
        self.shots = shots
        self.ppm = ppm
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("地图准备中", systemImage: "location.fill")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(LivePlayStyle.ink60)
                .padding(.bottom, 4)
            ForEach(Array(shots.enumerated()), id: \.element.id) { index, shot in
                RoundShotRow(shot: shot, ppm: ppm, displayNumber: index + 1)
                    .padding(.horizontal, 12)
                    .frame(height: 46)
                    .background(LivePlayStyle.fill08, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
    }
}

/// One shot row: number, club (or 开球(自动补) / —), yards, 起始球位 → 落点球位.
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
                .font(.system(size: 15, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(LivePlayStyle.ink)
                .frame(width: 22, alignment: .leading)
            if let club = shot.club, !club.isEmpty, club.lowercased() != "unknown" {
                Text(zhClubName(club)).font(.system(size: 15)).foregroundStyle(LivePlayStyle.ink)
            } else if shot.synthetic {
                Text("开球(自动补)").font(.system(size: 15)).foregroundStyle(LivePlayStyle.ink60)
            } else {
                Text("—").font(.system(size: 15)).foregroundStyle(LivePlayStyle.ink60)
            }
            if let yards = roundShotYards(shot, ppm: ppm) {
                Text("\(yards) 码").font(.caption.monospacedDigit()).foregroundStyle(LivePlayStyle.ink60)
            }
            Spacer()
            Text(shotLieLabel(shot.lie) + " → " + shotLieLabel(shot.endLie))
                .font(.caption)
                .foregroundStyle(LivePlayStyle.ink60)
        }
    }
}
